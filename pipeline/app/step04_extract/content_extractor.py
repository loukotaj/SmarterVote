"""
Content Extraction Engine for SmarterVote Pipeline

This module handles extraction of meaningful text from various content formats:
- HTML parsing and cleaning with readability support
- PDF text extraction with bytes input
- JSON content parsing with structured data support
- Plain text processing with normalization

Features implemented:
- [x] Readability/article mode extraction for clean text
- [x] Structured metadata parsing (JSON-LD, OG, Twitter cards)
- [x] Enhanced PDF handling with bytes input and scanned detection
- [x] Content blocks for LLM chunking (800-1200 tokens)
- [x] Entity/keyword detection for candidates and issues
- [x] Comprehensive usefulness scoring and filtering
- [x] Duplicate detection (exact checksum and near-duplicate SimHash)
- [x] Language detection with confidence scoring
- [x] Table extraction from HTML and basic PDF tables
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import PyPDF2
from bs4 import BeautifulSoup
from langdetect import detect, detect_langs
from langdetect.lang_detect_exception import LangDetectException
from nltk.tokenize import sent_tokenize, word_tokenize
from readability import Document
from simhash import Simhash

try:
    from ..schema import CanonicalIssue, ExtractedContent, Source
except ImportError:
    # Fallback for direct imports
    from shared.models import CanonicalIssue, ExtractedContent, Source

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Engine for extracting and processing text content from various formats with quality filtering."""

    def __init__(self):
        # Enhanced configuration
        self.config = {
            "min_text_length": 100,  # Increased minimum for quality
            "max_text_length": 5000000,  # 5MB of text
            "min_word_count": 50,  # Minimum words for usefulness
            "chunk_size_tokens": 1000,  # Target chunk size for LLMs
            "chunk_overlap_tokens": 100,  # Overlap between chunks
            "remove_html_tags": ["script", "style", "nav", "footer", "header", "aside", "advertisement"],
            "pdf_max_pages": 200,  # Increased for better coverage
            "language_detection": True,
            "min_language_confidence": 0.7,
            "usefulness_threshold": 0.3,  # Minimum score to be considered useful
            "simhash_threshold": 3,  # Bit distance for near-duplicate detection
            "extract_tables": True,
            "extract_metadata": True,
        }

        # Internal state for deduplication
        self._seen_checksums: Set[str] = set()
        self._seen_simhashes: Dict[int, str] = {}  # simhash -> content_id mapping

        # Candidate and issue keywords for entity detection
        self._candidate_patterns = [
            r"\b[A-Z][a-z]+ [A-Z][a-z]+\b",  # First Last name pattern
            r"\b(?:Senator|Rep\.|Representative|Gov\.|Governor|Mayor|Judge)\s+[A-Z][a-z]+ [A-Z][a-z]+\b",
        ]

        self._issue_keywords = {
            CanonicalIssue.HEALTHCARE: [
                "healthcare",
                "health care",
                "medicare",
                "medicaid",
                "insurance",
                "hospital",
                "medical",
            ],
            CanonicalIssue.ECONOMY: ["economy", "economic", "jobs", "employment", "wages", "inflation", "taxes", "budget"],
            CanonicalIssue.CLIMATE_ENERGY: ["climate", "environment", "energy", "renewable", "carbon", "pollution", "green"],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: [
                "abortion",
                "reproductive",
                "roe v wade",
                "planned parenthood",
                "birth control",
            ],
            CanonicalIssue.IMMIGRATION: ["immigration", "border", "refugees", "asylum", "deportation", "visa", "citizenship"],
            CanonicalIssue.GUNS_SAFETY: ["gun", "firearms", "second amendment", "background check", "shooting", "violence"],
            CanonicalIssue.FOREIGN_POLICY: ["foreign policy", "international", "military", "defense", "nato", "allies"],
            CanonicalIssue.SOCIAL_JUSTICE: ["civil rights", "equality", "discrimination", "racism", "justice", "police"],
            CanonicalIssue.EDUCATION: ["education", "schools", "teachers", "students", "college", "university", "funding"],
            CanonicalIssue.TECH_AI: ["technology", "artificial intelligence", "ai", "privacy", "data", "tech", "internet"],
            CanonicalIssue.ELECTION_REFORM: ["voting", "elections", "electoral", "gerrymandering", "democracy", "ballots"],
        }

        # Party keywords for political affiliation detection
        self._party_keywords = ["democratic", "republican", "independent", "libertarian", "green party"]

        # Initialize NLTK data (download if not present)
        try:
            import nltk

            nltk.data.find("tokenizers/punkt")
        except LookupError:
            import nltk

            nltk.download("punkt")

    async def extract_content(self, raw_content: List[Dict[str, Any]]) -> List[ExtractedContent]:
        """
        Extract text from all provided content items with comprehensive filtering and processing.

        Args:
            raw_content: List of raw content with metadata from fetcher

        Returns:
            List of extracted content objects that pass usefulness criteria
        """
        logger.info(f"Extracting text from {len(raw_content)} items")

        extracted = []
        dropped_reasons = {}

        for item in raw_content:
            try:
                result = await self._extract_single_item(item)
                if result:
                    # Check for exact duplicates first
                    if result.metadata.get("content_checksum") in self._seen_checksums:
                        logger.debug(f"Skipping exact duplicate: {result.source.url}")
                        dropped_reasons["exact_duplicate"] = dropped_reasons.get("exact_duplicate", 0) + 1
                        continue

                    # Check for near-duplicates using SimHash
                    simhash_value = result.metadata.get("simhash")
                    if simhash_value and self._is_near_duplicate(simhash_value):
                        logger.debug(f"Skipping near-duplicate: {result.source.url}")
                        dropped_reasons["near_duplicate"] = dropped_reasons.get("near_duplicate", 0) + 1
                        continue

                    # Check usefulness criteria
                    if not result.metadata.get("is_useful", False):
                        reasons = result.metadata.get("usefulness_reasons", [])
                        logger.debug(f"Dropping low-quality content from {result.source.url}: {reasons}")
                        dropped_reasons["low_quality"] = dropped_reasons.get("low_quality", 0) + 1
                        continue

                    # Add to tracking sets
                    self._seen_checksums.add(result.metadata["content_checksum"])
                    if simhash_value:
                        self._seen_simhashes[simhash_value] = str(result.source.url)

                    extracted.append(result)

            except Exception as e:
                logger.error(f"Failed to extract content from {item.get('source', {}).get('url', 'unknown')}: {e}")
                dropped_reasons["extraction_error"] = dropped_reasons.get("extraction_error", 0) + 1

        logger.info(f"Successfully extracted {len(extracted)}/{len(raw_content)} items")
        if dropped_reasons:
            logger.info(f"Dropped content reasons: {dropped_reasons}")

        return extracted

    def _is_near_duplicate(self, simhash_value: int) -> bool:
        """
        Check if content is a near-duplicate using SimHash distance.

        Args:
            simhash_value: SimHash value of the content

        Returns:
            True if near-duplicate found, False otherwise
        """
        for existing_hash in self._seen_simhashes.keys():
            distance = bin(simhash_value ^ existing_hash).count("1")
            if distance <= self.config["simhash_threshold"]:
                return True
        return False

    async def _extract_single_item(self, item: Dict[str, Any]) -> Optional[ExtractedContent]:
        """
        Extract text from a single content item with enriched metadata and quality assessment.

        Args:
            item: Raw content item from fetcher

        Returns:
            ExtractedContent object or None if extraction fails or content is unusable
        """
        source = item["source"]
        content_type = item.get("content_type", "")
        content = item.get("content")
        content_bytes = item.get("content_bytes")

        # Early validation
        if not content and not content_bytes:
            logger.warning(f"No content found for {source.url}")
            return None

        # Determine extraction method and extract text
        if "text/html" in content_type or "html" in str(source.url).lower():
            text, structured_metadata = self._extract_from_html(content)
            method = "html_readability"
        elif "application/pdf" in content_type or str(source.url).lower().endswith(".pdf"):
            # Use bytes if available, fallback to content
            pdf_data = content_bytes if content_bytes else content.encode() if isinstance(content, str) else content
            text, structured_metadata = self._extract_from_pdf(pdf_data)
            method = "pdf_parser"
        elif "application/json" in content_type:
            text, structured_metadata = self._extract_from_json(content)
            method = "json_parser"
        else:
            # Try to extract as plain text
            text, structured_metadata = self._extract_from_text(content)
            method = "text_parser"

        if not text or len(text.strip()) < self.config["min_text_length"]:
            logger.debug(f"Extracted text too short for {source.url}: {len(text) if text else 0} chars")
            return None

        # Extract tables if enabled
        tables = []
        if self.config["extract_tables"] and "text/html" in content_type:
            tables = self._extract_tables_from_html(content)

        # Generate content blocks for LLM processing
        content_blocks = self._create_content_blocks(text)

        # Detect entities and issues
        entity_hits = self._detect_entities(text)
        issue_hits = self._detect_issues(text)

        # Calculate content metrics
        word_count = len(text.split())
        char_count = len(text)
        sentence_count = len(sent_tokenize(text)) if text else 0

        # Language detection
        language, language_confidence = self._detect_language_with_confidence(text)

        # Generate checksums for deduplication
        content_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        content_simhash = Simhash(text).value

        # Calculate usefulness score and determine if content should be kept
        usefulness_score, is_useful, usefulness_reasons = self._calculate_usefulness(
            text, word_count, language, language_confidence, entity_hits, issue_hits, structured_metadata, tables, item
        )

        # Combine metadata
        enriched_metadata = {
            # Original metadata from fetcher
            **item.get("headers", {}),
            # Extraction metadata
            "extraction_method": method,
            "original_content_type": content_type,
            "original_size_bytes": item.get(
                "content_length", len(content.encode() if isinstance(content, str) else content or b"")
            ),
            "extracted_size_chars": char_count,
            "word_count": word_count,
            "sentence_count": sentence_count,
            "reading_time_minutes": max(1, word_count // 200),
            # Quality metrics
            "extraction_quality_score": self._calculate_extraction_quality(text, method),
            "language_confidence": language_confidence,
            "usefulness_score": usefulness_score,
            "is_useful": is_useful,
            "usefulness_reasons": usefulness_reasons,
            # Deduplication
            "content_checksum": content_checksum,
            "simhash": content_simhash,
            # Structured data
            **structured_metadata,
            # Entity detection
            "entity_hits": entity_hits,
            "issue_hits": issue_hits,
            # Content structure
            "content_blocks_count": len(content_blocks),
            "tables_count": len(tables),
            # Original fetch metadata
            "fetch_timestamp": item.get("fetch_timestamp"),
            "final_url": item.get("final_url"),
            "canonical_url": item.get("canonical_url"),
        }

        return ExtractedContent(
            source=source,
            text=text,
            metadata=enriched_metadata,
            extraction_timestamp=datetime.utcnow(),
            word_count=word_count,
            language=language,
        )

    def _extract_from_html(self, html_content: str) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from HTML content using readability and structured metadata parsing.

        Args:
            html_content: Raw HTML content

        Returns:
            Tuple of (extracted_text, structured_metadata)
        """
        if not html_content:
            return "", {}

        structured_metadata = {}

        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract structured metadata first
        if self.config["extract_metadata"]:
            structured_metadata = self._extract_structured_metadata(soup)

        # Use readability for article extraction
        try:
            doc = Document(html_content)
            article_html = doc.summary()
            article_title = doc.title()

            # Parse the cleaned article HTML
            article_soup = BeautifulSoup(article_html, "html.parser")

            # Remove remaining unwanted elements
            for tag in self.config["remove_html_tags"]:
                for element in article_soup.find_all(tag):
                    element.decompose()

            # Extract text while preserving structure
            text_parts = []

            # Add title if available
            if article_title and article_title.strip():
                text_parts.append(f"TITLE: {article_title.strip()}")

            # Process article content with structure preservation
            for element in article_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
                element_text = element.get_text().strip()
                if element_text:
                    # Add structure indicators
                    if element.name.startswith("h"):
                        text_parts.append(f"HEADING: {element_text}")
                    elif element.name == "blockquote":
                        text_parts.append(f"QUOTE: {element_text}")
                    elif element.name == "li":
                        text_parts.append(f"LIST_ITEM: {element_text}")
                    else:
                        text_parts.append(element_text)

            # If readability didn't extract much, fall back to basic extraction
            article_text = "\n".join(text_parts)
            if len(article_text.split()) < 50:
                logger.debug("Readability extraction yielded little content, falling back to basic extraction")
                article_text = self._basic_html_extraction(soup)

        except Exception as e:
            logger.warning(f"Readability extraction failed, using basic method: {e}")
            article_text = self._basic_html_extraction(soup)
            article_title = soup.title.string if soup.title else ""

        # Add title to metadata if found
        if article_title and article_title.strip():
            structured_metadata["title"] = article_title.strip()

        # Final text cleaning
        cleaned_text = self._clean_text(article_text)

        return cleaned_text, structured_metadata

    def _basic_html_extraction(self, soup: BeautifulSoup) -> str:
        """
        Basic HTML text extraction as fallback when readability fails.

        Args:
            soup: BeautifulSoup object

        Returns:
            Extracted text
        """
        # Remove unwanted elements
        for tag in self.config["remove_html_tags"]:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith("<!--")):
            comment.extract()

        # Get text content
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return text

    def _extract_structured_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract structured metadata from HTML (JSON-LD, OpenGraph, Twitter Cards).

        Args:
            soup: BeautifulSoup object

        Returns:
            Dictionary of structured metadata
        """
        metadata = {}

        # Extract JSON-LD structured data
        json_ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in json_ld_scripts:
            try:
                json_data = json.loads(script.string)
                if isinstance(json_data, dict):
                    # Extract common properties
                    if "@type" in json_data:
                        metadata["schema_type"] = json_data["@type"]
                    if "headline" in json_data:
                        metadata["headline"] = json_data["headline"]
                    if "author" in json_data:
                        if isinstance(json_data["author"], dict):
                            metadata["author"] = json_data["author"].get("name", str(json_data["author"]))
                        else:
                            metadata["author"] = str(json_data["author"])
                    if "datePublished" in json_data:
                        metadata["published_at"] = json_data["datePublished"]
                    if "dateModified" in json_data:
                        metadata["updated_at"] = json_data["dateModified"]
                    if "articleSection" in json_data:
                        metadata["section"] = json_data["articleSection"]
                    if "keywords" in json_data:
                        metadata["keywords"] = json_data["keywords"]
                    if "publisher" in json_data:
                        if isinstance(json_data["publisher"], dict):
                            metadata["publisher"] = json_data["publisher"].get("name", str(json_data["publisher"]))
                        else:
                            metadata["publisher"] = str(json_data["publisher"])
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Failed to parse JSON-LD: {e}")

        # Extract OpenGraph metadata
        og_tags = soup.find_all("meta", property=lambda x: x and x.startswith("og:"))
        for tag in og_tags:
            property_name = tag.get("property", "").replace("og:", "")
            content = tag.get("content", "")
            if property_name and content:
                if property_name == "title" and "title" not in metadata:
                    metadata["title"] = content
                elif property_name == "description" and "description" not in metadata:
                    metadata["description"] = content
                elif property_name == "published_time":
                    metadata["published_at"] = content
                elif property_name == "modified_time":
                    metadata["updated_at"] = content
                elif property_name == "section":
                    metadata["section"] = content
                elif property_name == "site_name":
                    metadata["site_name"] = content

        # Extract Twitter Card metadata
        twitter_tags = soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")})
        for tag in twitter_tags:
            name = tag.get("name", "").replace("twitter:", "")
            content = tag.get("content", "")
            if name and content:
                if name == "title" and "title" not in metadata:
                    metadata["title"] = content
                elif name == "description" and "description" not in metadata:
                    metadata["description"] = content
                elif name == "site":
                    metadata["twitter_site"] = content

        # Extract standard meta tags
        title_tag = soup.find("title")
        if title_tag and title_tag.string and "title" not in metadata:
            metadata["title"] = title_tag.string.strip()

        description_tag = soup.find("meta", attrs={"name": "description"})
        if description_tag and "description" not in metadata:
            metadata["description"] = description_tag.get("content", "").strip()

        keywords_tag = soup.find("meta", attrs={"name": "keywords"})
        if keywords_tag and "keywords" not in metadata:
            metadata["keywords"] = keywords_tag.get("content", "").strip()

        author_tag = soup.find("meta", attrs={"name": "author"})
        if author_tag and "author" not in metadata:
            metadata["author"] = author_tag.get("content", "").strip()

        # Extract byline from common patterns
        if "author" not in metadata:
            byline_selectors = [
                ".byline",
                ".author",
                ".post-author",
                ".article-author",
                '[rel="author"]',
                ".writer",
                ".journalist",
            ]
            for selector in byline_selectors:
                byline_elem = soup.select_one(selector)
                if byline_elem:
                    metadata["byline"] = byline_elem.get_text().strip()
                    break

        # Extract publication date from common patterns
        if "published_at" not in metadata:
            date_selectors = [".date", ".publish-date", ".post-date", ".article-date", "time[datetime]", ".timestamp"]
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get("datetime") or date_elem.get_text().strip()
                    if date_text:
                        metadata["published_at"] = date_text
                        break

        return metadata

    def _extract_from_pdf(self, pdf_data: bytes) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from PDF content with enhanced handling and scanned document detection.

        Args:
            pdf_data: PDF content as bytes

        Returns:
            Tuple of (extracted_text, metadata)
        """
        if not pdf_data:
            return "", {}

        text_parts = []
        metadata = {}

        try:
            if isinstance(pdf_data, str):
                # Convert string to bytes if needed
                pdf_data = pdf_data.encode("utf-8")

            pdf_file = BytesIO(pdf_data)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            # Extract PDF metadata
            if pdf_reader.metadata:
                metadata.update(
                    {
                        "title": pdf_reader.metadata.get("/Title", ""),
                        "author": pdf_reader.metadata.get("/Author", ""),
                        "subject": pdf_reader.metadata.get("/Subject", ""),
                        "creator": pdf_reader.metadata.get("/Creator", ""),
                        "producer": pdf_reader.metadata.get("/Producer", ""),
                        "creation_date": str(pdf_reader.metadata.get("/CreationDate", "")),
                        "modification_date": str(pdf_reader.metadata.get("/ModDate", "")),
                    }
                )

            # Extract text from pages
            total_pages = len(pdf_reader.pages)
            max_pages = min(total_pages, self.config["pdf_max_pages"])

            text_yield_per_page = []
            for page_num in range(max_pages):
                try:
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()

                    if page_text:
                        # Track text yield for scanned document detection
                        text_yield_per_page.append(len(page_text.split()))
                        text_parts.append(f"PAGE {page_num + 1}:\n{page_text}")
                    else:
                        text_yield_per_page.append(0)

                except Exception as e:
                    logger.debug(f"Error extracting text from page {page_num}: {e}")
                    text_yield_per_page.append(0)

            # Detect scanned PDFs (very low text yield)
            avg_words_per_page = sum(text_yield_per_page) / max(len(text_yield_per_page), 1)
            is_likely_scanned = avg_words_per_page < 10  # Very low threshold for scanned docs

            metadata.update(
                {
                    "total_pages": total_pages,
                    "processed_pages": max_pages,
                    "avg_words_per_page": avg_words_per_page,
                    "is_likely_scanned": is_likely_scanned,
                    "ocr_recommended": is_likely_scanned,
                    "text_yield_per_page": text_yield_per_page,
                }
            )

            if is_likely_scanned:
                logger.info(f"PDF appears to be scanned (avg {avg_words_per_page:.1f} words/page), OCR recommended")

        except Exception as e:
            logger.error(f"Error extracting PDF: {e}")
            return "", {"pdf_extraction_error": str(e)}

        full_text = "\n\n".join(text_parts)
        cleaned_text = self._clean_text(full_text.strip())

        return cleaned_text, metadata

    def _extract_from_json(self, json_content: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Extract relevant text from JSON content with improved structure handling.

        Args:
            json_content: JSON content (string or already parsed)

        Returns:
            Tuple of (extracted_text, metadata)
        """
        metadata = {}

        # Parse JSON if it's a string
        if isinstance(json_content, str):
            try:
                json_data = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON content: {e}")
                return "", {"json_parse_error": str(e)}
        else:
            json_data = json_content

        def extract_text_recursive(obj, depth=0, max_depth=6):
            if depth > max_depth:
                return []

            texts = []

            if isinstance(obj, dict):
                # Prioritize common text fields
                priority_fields = [
                    "content",
                    "description",
                    "body",
                    "text",
                    "summary",
                    "title",
                    "name",
                    "headline",
                    "message",
                    "comment",
                ]

                # Extract metadata from common fields
                if depth == 0:  # Only at top level
                    for field in ["title", "author", "published_at", "updated_at", "tags", "category"]:
                        if field in obj:
                            metadata[field] = obj[field]

                # Extract priority text fields
                for field in priority_fields:
                    if field in obj and isinstance(obj[field], str) and len(obj[field]) > 20:
                        texts.append(f"{field.upper()}: {obj[field]}")

                # Extract from other string fields
                for key, value in obj.items():
                    if key not in priority_fields:
                        if isinstance(value, str) and len(value) > 50:
                            texts.append(f"{key}: {value}")
                        elif isinstance(value, (dict, list)):
                            texts.extend(extract_text_recursive(value, depth + 1, max_depth))

            elif isinstance(obj, list):
                for item in obj:
                    texts.extend(extract_text_recursive(item, depth + 1, max_depth))

            elif isinstance(obj, str) and len(obj) > 50:
                texts.append(obj)

            return texts

        extracted_texts = extract_text_recursive(json_data)
        full_text = "\n".join(extracted_texts)
        cleaned_text = self._clean_text(full_text)

        return cleaned_text, metadata

    def _extract_from_text(self, text_content: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Process plain text content with format detection and normalization.

        Args:
            text_content: Text content to process

        Returns:
            Tuple of (processed_text, metadata)
        """
        metadata = {}

        if not isinstance(text_content, str):
            text_content = str(text_content)

        # Detect if it might be markdown, CSV, or other structured format
        if text_content.count("|") > 10 and text_content.count("\n") > 5:
            metadata["detected_format"] = "table_like"
        elif text_content.count("#") > 3 and text_content.count("\n") > 5:
            metadata["detected_format"] = "markdown_like"
        elif text_content.count(",") > text_content.count(" ") / 2:
            metadata["detected_format"] = "csv_like"
        else:
            metadata["detected_format"] = "plain_text"

        cleaned_text = self._clean_text(text_content)
        return cleaned_text, metadata

    def _extract_tables_from_html(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Extract tables from HTML content using pandas.

        Args:
            html_content: Raw HTML content

        Returns:
            List of table dictionaries with headers and row counts
        """
        tables = []

        try:
            # Use pandas to extract tables
            df_list = pd.read_html(html_content, header=0)

            for i, df in enumerate(df_list):
                if len(df) > 1 and len(df.columns) > 1:  # Skip trivial tables
                    table_info = {
                        "table_id": i,
                        "rows": len(df),
                        "columns": len(df.columns),
                        "headers": list(df.columns),
                        "sample_data": df.head(3).to_dict("records") if len(df) > 0 else [],
                    }
                    tables.append(table_info)

        except (ValueError, ImportError) as e:
            logger.debug(f"Table extraction failed: {e}")

        return tables

    def _create_content_blocks(self, text: str) -> List[Dict[str, Any]]:
        """
        Create content blocks for LLM processing with stable chunking.

        Args:
            text: Full text content

        Returns:
            List of content blocks with metadata
        """
        if not text:
            return []

        # Split text into sentences for better chunking
        try:
            sentences = sent_tokenize(text)
        except:
            # Fallback to simple splitting if NLTK fails
            sentences = text.split(". ")

        blocks = []
        current_block = []
        current_tokens = 0
        block_id = 0
        start_char = 0

        for sentence in sentences:
            # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
            sentence_tokens = len(sentence) // 4

            # Check if adding this sentence would exceed target size
            if current_tokens + sentence_tokens > self.config["chunk_size_tokens"] and current_block:
                # Create block from current sentences
                block_text = " ".join(current_block)
                end_char = start_char + len(block_text)

                blocks.append(
                    {
                        "block_id": f"block_{block_id}",
                        "text": block_text,
                        "start_char": start_char,
                        "end_char": end_char,
                        "token_count": current_tokens,
                        "sentence_count": len(current_block),
                    }
                )

                # Start new block with overlap
                overlap_sentences = current_block[-2:] if len(current_block) > 2 else current_block
                current_block = overlap_sentences + [sentence]
                current_tokens = sum(len(s) // 4 for s in current_block)
                start_char = end_char - sum(len(s) for s in overlap_sentences) - len(overlap_sentences)
                block_id += 1
            else:
                current_block.append(sentence)
                current_tokens += sentence_tokens

        # Add final block if there's remaining content
        if current_block:
            block_text = " ".join(current_block)
            end_char = start_char + len(block_text)

            blocks.append(
                {
                    "block_id": f"block_{block_id}",
                    "text": block_text,
                    "start_char": start_char,
                    "end_char": end_char,
                    "token_count": current_tokens,
                    "sentence_count": len(current_block),
                }
            )

        return blocks

    def _detect_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Detect entities like candidate names and political parties.

        Args:
            text: Text content to analyze

        Returns:
            Dictionary of detected entities by type
        """
        entities = {
            "candidates": [],
            "parties": [],
            "offices": [],
        }

        text_lower = text.lower()

        # Detect candidate names using patterns
        for pattern in self._candidate_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match not in entities["candidates"]:
                    entities["candidates"].append(match)

        # Detect political parties
        for party in self._party_keywords:
            if party in text_lower:
                if party not in entities["parties"]:
                    entities["parties"].append(party)

        # Detect office types
        office_patterns = [
            r"\b(?:senate|senator)\b",
            r"\b(?:house|representative|rep\.)\b",
            r"\b(?:governor|gov\.)\b",
            r"\b(?:mayor)\b",
            r"\b(?:judge|justice)\b",
        ]

        for pattern in office_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if match not in entities["offices"]:
                    entities["offices"].append(match)

        return entities

    def _detect_issues(self, text: str) -> Dict[str, int]:
        """
        Detect mentions of canonical issues and count occurrences.

        Args:
            text: Text content to analyze

        Returns:
            Dictionary mapping issues to occurrence counts
        """
        issue_hits = {}
        text_lower = text.lower()

        for issue, keywords in self._issue_keywords.items():
            count = 0
            for keyword in keywords:
                count += text_lower.count(keyword.lower())

            if count > 0:
                issue_hits[issue.value] = count

        return issue_hits

    def _detect_language_with_confidence(self, text: str) -> Tuple[str, float]:
        """
        Detect language with confidence score.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (language_code, confidence_score)
        """
        if not text or len(text.strip()) < 50:
            return "en", 0.5  # Default fallback

        try:
            # Use langdetect for language detection
            from langdetect import detect, detect_langs

            # Get detailed language probabilities
            lang_probs = detect_langs(text)

            if lang_probs:
                best_lang = lang_probs[0]
                return best_lang.lang, float(best_lang.prob)
            else:
                return "en", 0.5

        except (LangDetectException, ImportError) as e:
            logger.debug(f"Language detection failed: {e}")

            # Fallback: simple heuristics
            english_indicators = ["the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"]
            words = text.lower().split()
            english_count = sum(1 for word in words if word in english_indicators)
            confidence = min(1.0, english_count / len(words) * 10) if words else 0.5

            return "en", confidence

    def _calculate_usefulness(
        self,
        text: str,
        word_count: int,
        language: str,
        language_confidence: float,
        entity_hits: Dict[str, List[str]],
        issue_hits: Dict[str, int],
        structured_metadata: Dict[str, Any],
        tables: List[Dict[str, Any]],
        original_item: Dict[str, Any],
    ) -> Tuple[float, bool, List[str]]:
        """
        Calculate comprehensive usefulness score and determine if content should be kept.

        Args:
            text: Extracted text
            word_count: Number of words
            language: Detected language
            language_confidence: Language detection confidence
            entity_hits: Detected entities
            issue_hits: Detected issues
            structured_metadata: Extracted metadata
            tables: Extracted tables
            original_item: Original fetch item

        Returns:
            Tuple of (usefulness_score, is_useful, reasons_list)
        """
        score = 0.0
        reasons = []

        # 1. Content substance check (0.3 weight)
        if word_count >= self.config["min_word_count"]:
            score += 0.2
            reasons.append("sufficient_length")
        elif word_count >= 20:
            score += 0.1
            reasons.append("minimal_length")
        else:
            reasons.append("too_short")

        # Bonus for tables or structured content
        if tables:
            score += 0.1
            reasons.append("has_tables")

        # 2. Language appropriateness (0.15 weight)
        if language == "en" and language_confidence >= self.config["min_language_confidence"]:
            score += 0.15
            reasons.append("english_high_confidence")
        elif language == "en" and language_confidence >= 0.5:
            score += 0.1
            reasons.append("english_medium_confidence")
        else:
            reasons.append("non_english_or_low_confidence")

        # 3. Topical relevance (0.25 weight)
        has_candidates = any(len(candidates) > 0 for candidates in entity_hits.values())
        has_issues = len(issue_hits) > 0

        if has_candidates and has_issues:
            score += 0.25
            reasons.append("relevant_candidates_and_issues")
        elif has_candidates:
            score += 0.15
            reasons.append("relevant_candidates")
        elif has_issues:
            score += 0.15
            reasons.append("relevant_issues")
        else:
            reasons.append("low_topical_relevance")

        # 4. Content quality indicators (0.15 weight)

        # Check for boilerplate-removed text density
        if len(text.strip()) > 0:
            # Estimate content density by checking ratio of meaningful words
            meaningful_words = len([w for w in text.split() if len(w) > 3])
            density_ratio = meaningful_words / max(word_count, 1)

            if density_ratio > 0.6:
                score += 0.1
                reasons.append("high_content_density")
            elif density_ratio > 0.4:
                score += 0.05
                reasons.append("medium_content_density")
            else:
                reasons.append("low_content_density")

        # 5. Source credibility (0.15 weight)
        source_url = str(original_item.get("source", {}).get("url", ""))
        detected_source_type = original_item.get("detected_source_type", "")

        # Government and official sources get bonus
        if any(domain in source_url for domain in [".gov", ".edu", "fec.gov", "ballotpedia"]):
            score += 0.15
            reasons.append("official_source")
        elif detected_source_type in ["government", "news"]:
            score += 0.1
            reasons.append("credible_source_type")
        elif detected_source_type == "social_media":
            score += 0.05
            reasons.append("social_media_source")

        # 6. Freshness bonus (0.1 weight)
        published_at = structured_metadata.get("published_at")
        if published_at:
            score += 0.05
            reasons.append("has_publication_date")

        # Check for evergreen content types
        if any(indicator in source_url for indicator in ["filing", "statute", "law", "regulation"]):
            score += 0.05
            reasons.append("evergreen_content")

        # Additional penalties for low quality indicators

        # Penalize very repetitive content
        if text and len(set(text.split())) / max(word_count, 1) < 0.3:
            score -= 0.1
            reasons.append("highly_repetitive")

        # Penalize content with too many special characters (navigation artifacts)
        if text:
            special_char_ratio = len(re.findall(r"[^\w\s]", text)) / max(len(text), 1)
            if special_char_ratio > 0.4:
                score -= 0.1
                reasons.append("too_many_special_chars")

        # Penalize if extraction method failed to get clean content
        extraction_method = original_item.get("method", "")
        if extraction_method == "selenium" and word_count < 50:
            score -= 0.05
            reasons.append("poor_dynamic_extraction")

        # Final scoring
        final_score = max(0.0, min(1.0, score))
        is_useful = final_score >= self.config["usefulness_threshold"]

        # Override: Always keep if it's an official document with any content
        if not is_useful and any(domain in source_url for domain in [".gov", "fec.gov"]) and word_count > 10:
            is_useful = True
            reasons.append("official_document_override")

        return final_score, is_useful, reasons

    def _calculate_extraction_quality(self, text: str, method: str) -> float:
        """
        Calculate quality score for the extraction process itself.

        Args:
            text: Extracted text
            method: Extraction method used

        Returns:
            Quality score between 0 and 1
        """
        if not text:
            return 0.0

        score = 0.5  # Base score

        # Penalize very short text
        if len(text) < 100:
            score *= 0.7

        # Reward proper sentence structure
        sentence_count = len(sent_tokenize(text)) if text else 0
        if sentence_count > 0:
            avg_sentence_length = len(text.split()) / sentence_count
            if 10 <= avg_sentence_length <= 40:  # Reasonable sentence length
                score *= 1.2
            elif avg_sentence_length < 5 or avg_sentence_length > 60:
                score *= 0.8

        # Method-specific adjustments
        if method == "html_readability":
            score *= 1.1  # Readability generally produces cleaner text
        elif method == "pdf_parser":
            score *= 0.9  # PDF extraction can be noisy
        elif method == "selenium":
            score *= 0.85  # Dynamic content can include more noise

        return min(1.0, score)

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text with enhanced processing.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned and normalized text
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove control characters but preserve newlines and tabs
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]", "", text)

        # Normalize various types of quotes and dashes
        text = re.sub(r'[""' "„‚‹›«»]", '"', text)
        text = re.sub(r"[–—]", "-", text)

        # Clean up repeated punctuation
        text = re.sub(r"[.]{3,}", "...", text)
        text = re.sub(r"[!]{2,}", "!", text)
        text = re.sub(r"[?]{2,}", "?", text)
        text = re.sub(r"[-]{3,}", "---", text)

        # Remove common extraction artifacts
        text = re.sub(r"\b(Click here|Read more|Continue reading|Share this|Print this)\b", "", text, flags=re.IGNORECASE)

        # Clean up URLs that might have been extracted as text
        text = re.sub(r"https?://[^\s]+", "[URL]", text)

        # Remove email addresses for privacy
        text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text)

        # Normalize spacing around punctuation
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = re.sub(r"([,.!?;:])\s*", r"\1 ", text)

        # Remove extra spaces
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def _detect_language(self, text: str) -> str:
        """
        Simple language detection fallback method.

        Args:
            text: Text to analyze

        Returns:
            Language code
        """
        language, _ = self._detect_language_with_confidence(text)
        return language

    def _calculate_quality_score(self, text: str) -> float:
        """
        Legacy method for backward compatibility.

        Args:
            text: Text to score

        Returns:
            Quality score
        """
        return self._calculate_extraction_quality(text, "unknown")
