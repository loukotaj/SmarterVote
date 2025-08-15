"""
Content Extraction Engine for SmarterVote Pipeline

This module handles extraction of meaningful text from various content formats:
- HTML parsing and cleaning with readability support
- PDF text extraction with bytes input
- JSON content parsing with structured data support
- Plain text processing with normalization

Design notes (compatibility):
- Public class and method signatures preserved (ContentExtractor, extract_content, etc.).
- Added small robustness tweaks; no breaking behavior changes.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import PyPDF2
from bs4 import BeautifulSoup
from bs4.element import Comment as Bs4Comment
from langdetect.lang_detect_exception import LangDetectException
from nltk.tokenize import sent_tokenize
from providers.base import TaskType
from readability import Document
from simhash import Simhash

from shared.models import CanonicalIssue, ExtractedContent, Source

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Engine for extracting and processing text content from various formats with quality filtering."""

    def __init__(self):
        # Configuration (kept simple; can be overridden by caller if needed)
        self.config = {
            "min_text_length": 100,  # Minimum characters after cleaning
            "max_text_length": 5_000_000,  # Hard ceiling on text size
            "min_word_count": 50,  # Minimum words to consider useful
            "chunk_size_tokens": 1000,  # Target chunk size for LLMs (approx)
            "chunk_overlap_tokens": 100,  # Overlap between chunks
            "remove_html_tags": ["script", "style", "nav", "footer", "header", "aside", "advertisement"],
            "pdf_max_pages": 200,  # Page limit safety
            "language_detection": True,  # Toggle language detection
            "min_language_confidence": 0.7,
            "usefulness_threshold": 0.3,  # Final usefulness cutoff
            "simhash_threshold": 3,  # Bit distance for near-duplicate detection
            "extract_tables": True,
            "extract_metadata": True,
        }

        # Internal state for deduplication
        self._seen_checksums: Set[str] = set()
        self._seen_simhashes: Dict[int, str] = {}  # simhash -> source_url

        # Candidate and issue keywords for entity detection (lightweight heuristics)
        self._candidate_patterns = [
            r"\b[A-Z][a-z]+ [A-Z][a-z]+\b",  # First Last
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

        # NLTK availability flag (avoid implicit downloads here)
        self._has_punkt = self._check_nltk_punkt()

    async def extract_content(self, raw_content: List[Dict[str, Any]]) -> List[ExtractedContent]:
        """
        Extract text from all provided content items with filtering and processing.

        Args:
            raw_content: List of raw content dicts from the fetcher

        Returns:
            List of ExtractedContent objects that pass usefulness criteria
        """
        logger.info("Extracting text from %d items", len(raw_content))

        extracted: List[ExtractedContent] = []
        dropped_reasons: Dict[str, int] = {}

        for item in raw_content:
            try:
                result = await self._extract_single_item(item)
                if not result:
                    continue

                # Exact duplicates
                checksum = result.metadata.get("content_checksum")
                if checksum and checksum in self._seen_checksums:
                    logger.debug("Skipping exact duplicate: %s", getattr(result.source, "url", "unknown"))
                    dropped_reasons["exact_duplicate"] = dropped_reasons.get("exact_duplicate", 0) + 1
                    continue

                # Near-duplicates via SimHash
                simhash_value = result.metadata.get("simhash")
                if simhash_value and self._is_near_duplicate(simhash_value):
                    logger.debug("Skipping near-duplicate: %s", getattr(result.source, "url", "unknown"))
                    dropped_reasons["near_duplicate"] = dropped_reasons.get("near_duplicate", 0) + 1
                    continue

                # Usefulness filter
                if not result.metadata.get("is_useful", False):
                    reasons = result.metadata.get("usefulness_reasons", [])
                    logger.debug("Dropping low-quality content from %s: %s", getattr(result.source, "url", "unknown"), reasons)
                    dropped_reasons["low_quality"] = dropped_reasons.get("low_quality", 0) + 1
                    continue

                # Track uniques
                if checksum:
                    self._seen_checksums.add(checksum)
                if simhash_value:
                    self._seen_simhashes[simhash_value] = str(getattr(result.source, "url", ""))

                extracted.append(result)

            except Exception as e:  # noqa: BLE001
                source = item.get("source")
                source_url = getattr(source, "url", None) or (source.get("url") if isinstance(source, dict) else "unknown")
                logger.error("Failed to extract content from %s: %s", source_url, e)
                dropped_reasons["extraction_error"] = dropped_reasons.get("extraction_error", 0) + 1

        logger.info("Successfully extracted %d/%d items", len(extracted), len(raw_content))
        if dropped_reasons:
            logger.info("Dropped content reasons: %s", dropped_reasons)

        return extracted

    # ------------------------- core extraction ------------------------- #

    async def _extract_single_item(self, item: Dict[str, Any]) -> Optional[ExtractedContent]:
        """Extract text from a single content item with enriched metadata and quality assessment."""
        source = item.get("source")
        content_type = (item.get("content_type") or "").lower()
        content = item.get("content")
        content_bytes: Optional[bytes] = item.get("content_bytes")

        # Early validation
        if content is None and not content_bytes:
            logger.warning("No content found for %s", getattr(source, "url", "unknown"))
            return None

        # Determine extraction method and extract text
        method = "text_parser"
        structured_metadata: Dict[str, Any] = {}

        # HTML
        if "text/html" in content_type or ("html" in str(getattr(source, "url", "")).lower()):
            text, structured_metadata = self._extract_from_html(content if isinstance(content, str) else "")
            method = "html_readability"

        # PDF
        elif "application/pdf" in content_type or str(getattr(source, "url", "")).lower().endswith(".pdf"):
            pdf_data = (
                content_bytes if content_bytes is not None else (content.encode() if isinstance(content, str) else content)
            )
            text, structured_metadata = self._extract_from_pdf(pdf_data)
            method = "pdf_parser"

        # JSON
        elif "application/json" in content_type:
            text, structured_metadata = self._extract_from_json(content)
            method = "json_parser"

        # Plain text (fallback)
        else:
            text, structured_metadata = self._extract_from_text(content)

        # Sanity limits
        text_len = len(text or "")
        if not text or text_len < self.config["min_text_length"]:
            logger.debug("Extracted text too short for %s: %d chars", getattr(source, "url", "unknown"), text_len)
            return None
        if text_len > self.config["max_text_length"]:
            logger.debug("Extracted text too long for %s: %d chars", getattr(source, "url", "unknown"), text_len)
            return None

        # Tables (enable for any HTML-identified extraction)
        tables: List[Dict[str, Any]] = []
        if self.config["extract_tables"] and method.startswith("html"):
            tables = self._extract_tables_from_html(content if isinstance(content, str) else "")

        # Chunking (kept internal; only count is recorded)
        content_blocks = self._create_content_blocks(text)

        # Entities & issues
        entity_hits = self._detect_entities(text)
        issue_hits = self._detect_issues(text)

        # Metrics
        word_count = len(text.split())
        char_count = text_len
        sentence_count = self._safe_sentence_count(text)

        # Language detection
        if self.config.get("language_detection", True):
            language, language_confidence = self._detect_language_with_confidence(text)
        else:
            language, language_confidence = "en", 1.0

        # Checksums
        content_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        content_simhash = Simhash(text).value

        # Usefulness scoring
        usefulness_score, is_useful, usefulness_reasons = self._calculate_usefulness(
            text=text,
            word_count=word_count,
            language=language,
            language_confidence=language_confidence,
            entity_hits=entity_hits,
            issue_hits=issue_hits,
            structured_metadata=structured_metadata,
            tables=tables,
            original_item=item,
        )

        # Build metadata
        original_size = self._get_original_size(item, content, content_bytes)
        enriched_metadata: Dict[str, Any] = {
            # Original fetch headers (if any)
            **(item.get("headers") or {}),
            # Extraction metadata
            "extraction_method": method,
            "original_content_type": content_type,
            "original_size_bytes": original_size,
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
            # Original fetch metadata (pass-through)
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

    # ------------------------- format-specific extractors ------------------------- #

    def _extract_from_html(self, html_content: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from HTML content using readability and structured metadata parsing."""
        if not html_content:
            return "", {}

        structured_metadata: Dict[str, Any] = {}

        soup = BeautifulSoup(html_content, "html.parser")

        # Structured metadata first (robust to lists and missing strings)
        if self.config["extract_metadata"]:
            structured_metadata = self._extract_structured_metadata(soup)

        # Readability-based article extraction
        try:
            doc = Document(html_content)
            article_html = doc.summary()
            article_title = doc.title() or ""

            article_soup = BeautifulSoup(article_html, "html.parser")

            # Remove unwanted tags
            for tag in self.config["remove_html_tags"]:
                for element in article_soup.find_all(tag):
                    element.decompose()

            # Extract text with some structure hints
            text_parts: List[str] = []
            if article_title.strip():
                text_parts.append(f"TITLE: {article_title.strip()}")

            for el in article_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
                t = (el.get_text() or "").strip()
                if not t:
                    continue
                if el.name.startswith("h"):
                    text_parts.append(f"HEADING: {t}")
                elif el.name == "blockquote":
                    text_parts.append(f"QUOTE: {t}")
                elif el.name == "li":
                    text_parts.append(f"LIST_ITEM: {t}")
                else:
                    text_parts.append(t)

            article_text = "\n".join(text_parts)

            # Fallback if too short
            if len(article_text.split()) < 50:
                logger.debug("Readability extraction minimal; using basic extraction")
                article_text = self._basic_html_extraction(soup)
        except Exception as e:  # noqa: BLE001
            logger.warning("Readability extraction failed, using basic method: %s", e)
            article_text = self._basic_html_extraction(soup)
            article_title = (soup.title.string if soup.title else "") or ""

        if article_title and article_title.strip():
            structured_metadata.setdefault("title", article_title.strip())

        cleaned_text = self._clean_text(article_text)
        return cleaned_text, structured_metadata

    def _basic_html_extraction(self, soup: BeautifulSoup) -> str:
        """Basic HTML text extraction as fallback when readability fails."""
        # Remove unwanted elements
        for tag in self.config["remove_html_tags"]:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove comments
        for c in soup.find_all(string=lambda x: isinstance(x, Bs4Comment)):
            c.extract()

        # Get text content
        text = soup.get_text(separator=" ")

        # Collapse whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)
        return text

    def _extract_structured_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract structured metadata from HTML (JSON-LD, OpenGraph, Twitter Cards, common meta)."""
        metadata: Dict[str, Any] = {}

        # JSON-LD (handle dict or list payloads)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or ""
                if not raw.strip():
                    continue
                json_data = json.loads(raw)
                candidates = json_data if isinstance(json_data, list) else [json_data]
                for obj in candidates:
                    if not isinstance(obj, dict):
                        continue
                    metadata.setdefault("schema_type", obj.get("@type"))
                    for k_src, k_dst in [
                        ("headline", "headline"),
                        ("datePublished", "published_at"),
                        ("dateModified", "updated_at"),
                        ("articleSection", "section"),
                        ("keywords", "keywords"),
                    ]:
                        if obj.get(k_src) and k_dst not in metadata:
                            metadata[k_dst] = obj[k_src]
                    # author/publisher
                    if "author" in obj and "author" not in metadata:
                        a = obj["author"]
                        metadata["author"] = a.get("name") if isinstance(a, dict) else str(a)
                    if "publisher" in obj and "publisher" not in metadata:
                        p = obj["publisher"]
                        metadata["publisher"] = p.get("name") if isinstance(p, dict) else str(p)
            except Exception as e:  # noqa: BLE001
                logger.debug("Failed to parse JSON-LD: %s", e)

        # OpenGraph
        for tag in soup.find_all("meta", property=lambda x: x and x.startswith("og:")):
            prop = (tag.get("property") or "").replace("og:", "")
            content = tag.get("content") or ""
            if not prop or not content:
                continue
            if prop == "title":
                metadata.setdefault("title", content)
            elif prop == "description":
                metadata.setdefault("description", content)
            elif prop == "published_time":
                metadata.setdefault("published_at", content)
            elif prop == "modified_time":
                metadata.setdefault("updated_at", content)
            elif prop == "section":
                metadata.setdefault("section", content)
            elif prop == "site_name":
                metadata.setdefault("site_name", content)

        # Twitter
        for tag in soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")}):
            name = (tag.get("name") or "").replace("twitter:", "")
            content = tag.get("content") or ""
            if not name or not content:
                continue
            if name == "title":
                metadata.setdefault("title", content)
            elif name == "description":
                metadata.setdefault("description", content)
            elif name == "site":
                metadata.setdefault("twitter_site", content)

        # Standard meta
        if soup.title and soup.title.string:
            metadata.setdefault("title", soup.title.string.strip())
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag:
            metadata.setdefault("description", (desc_tag.get("content") or "").strip())
        kw_tag = soup.find("meta", attrs={"name": "keywords"})
        if kw_tag:
            metadata.setdefault("keywords", (kw_tag.get("content") or "").strip())
        author_tag = soup.find("meta", attrs={"name": "author"})
        if author_tag:
            metadata.setdefault("author", (author_tag.get("content") or "").strip())

        # Byline hints
        if "author" not in metadata:
            for selector in [
                ".byline",
                ".author",
                ".post-author",
                ".article-author",
                '[rel="author"]',
                ".writer",
                ".journalist",
            ]:
                byline_elem = soup.select_one(selector)
                if byline_elem:
                    metadata["byline"] = byline_elem.get_text(strip=True)
                    break

        # Date hints
        if "published_at" not in metadata:
            for selector in [".date", ".publish-date", ".post-date", ".article-date", "time[datetime]", ".timestamp"]:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get("datetime") or date_elem.get_text(strip=True)
                    if date_text:
                        metadata["published_at"] = date_text
                        break

        return metadata

    def _extract_from_pdf(self, pdf_data: Optional[bytes]) -> Tuple[str, Dict[str, Any]]:
        """Extract text from PDF content with scanned document detection."""
        if PyPDF2 is None:
            logger.debug("PyPDF2 not installed; skipping PDF extraction")
            return "", {"pdf_extraction_error": "PyPDF2 not installed"}
        if not pdf_data:
            return "", {}

        text_parts: List[str] = []
        metadata: Dict[str, Any] = {}

        try:
            pdf_file = BytesIO(pdf_data)
            reader = PyPDF2.PdfReader(pdf_file)

            if reader.is_encrypted:
                try:
                    reader.decrypt("")  # Try empty password
                except Exception:
                    pass  # Continue; extract_text may still work for some PDFs

            # PDF metadata
            if reader.metadata:
                md = reader.metadata
                metadata.update(
                    {
                        "title": md.get("/Title", ""),
                        "author": md.get("/Author", ""),
                        "subject": md.get("/Subject", ""),
                        "creator": md.get("/Creator", ""),
                        "producer": md.get("/Producer", ""),
                        "creation_date": str(md.get("/CreationDate", "")),
                        "modification_date": str(md.get("/ModDate", "")),
                    }
                )

            total_pages = len(reader.pages)
            max_pages = min(total_pages, self.config["pdf_max_pages"])

            text_yield_per_page: List[int] = []
            for page_num in range(max_pages):
                try:
                    page = reader.pages[page_num]
                    page_text = page.extract_text() or ""
                    words = len(page_text.split())
                    text_yield_per_page.append(words)
                    if page_text:
                        text_parts.append(f"PAGE {page_num + 1}:\n{page_text}")
                except Exception as e:  # noqa: BLE001
                    logger.debug("Error extracting text from page %d: %s", page_num, e)
                    text_yield_per_page.append(0)

            avg_words_per_page = sum(text_yield_per_page) / max(len(text_yield_per_page), 1)
            is_likely_scanned = avg_words_per_page < 10

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
                logger.info("PDF appears scanned (avg %.1f words/page), OCR recommended", avg_words_per_page)

        except Exception as e:  # noqa: BLE001
            logger.error("Error extracting PDF: %s", e)
            return "", {"pdf_extraction_error": str(e)}

        full_text = "\n\n".join(text_parts)
        cleaned_text = self._clean_text(full_text.strip())
        return cleaned_text, metadata

    def _extract_from_json(self, json_content: Any) -> Tuple[str, Dict[str, Any]]:
        """Extract relevant text from JSON content with improved structure handling."""
        metadata: Dict[str, Any] = {}

        # Parse JSON if string
        if isinstance(json_content, str):
            try:
                json_data = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON content: %s", e)
                return "", {"json_parse_error": str(e)}
        else:
            json_data = json_content

        def extract_text_recursive(obj: Any, depth: int = 0, max_depth: int = 6) -> List[str]:
            if depth > max_depth:
                return []
            texts: List[str] = []

            if isinstance(obj, dict):
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

                if depth == 0:
                    for field in ["title", "author", "published_at", "updated_at", "tags", "category"]:
                        if field in obj:
                            metadata[field] = obj[field]

                for field in priority_fields:
                    val = obj.get(field)
                    if isinstance(val, str) and len(val) > 20:
                        texts.append(f"{field.upper()}: {val}")

                for k, v in obj.items():
                    if k in priority_fields:
                        continue
                    if isinstance(v, str) and len(v) > 50:
                        texts.append(f"{k}: {v}")
                    elif isinstance(v, (dict, list)):
                        texts.extend(extract_text_recursive(v, depth + 1, max_depth))

            elif isinstance(obj, list):
                for it in obj:
                    texts.extend(extract_text_recursive(it, depth + 1, max_depth))

            elif isinstance(obj, str) and len(obj) > 50:
                texts.append(obj)

            return texts

        extracted_texts = extract_text_recursive(json_data)
        full_text = "\n".join(extracted_texts)
        cleaned_text = self._clean_text(full_text)
        return cleaned_text, metadata

    def _extract_from_text(self, text_content: Any) -> Tuple[str, Dict[str, Any]]:
        """Process plain text content with format detection and normalization."""
        metadata: Dict[str, Any] = {}
        if not isinstance(text_content, str):
            text_content = str(text_content or "")

        # Simple format hints
        if text_content.count("|") > 10 and text_content.count("\n") > 5:
            metadata["detected_format"] = "table_like"
        elif text_content.count("#") > 3 and text_content.count("\n") > 5:
            metadata["detected_format"] = "markdown_like"
        elif text_content.count(",") > max(text_content.count(" "), 1) / 2:
            metadata["detected_format"] = "csv_like"
        else:
            metadata["detected_format"] = "plain_text"

        cleaned_text = self._clean_text(text_content)
        return cleaned_text, metadata

    def _extract_tables_from_html(self, html_content: str) -> List[Dict[str, Any]]:
        """Extract tables from HTML using pandas (best-effort).

        If pandas isn't installed, table extraction is skipped and an empty list is
        returned. The rest of the content extraction pipeline still works, which
        keeps tests independent of the optional dependency.
        """

        tables: List[Dict[str, Any]] = []
        if not html_content or pd is None:
            return tables

        try:
            df_list = pd.read_html(StringIO(html_content), header=0)
            for i, df in enumerate(df_list):
                if len(df) > 1 and len(df.columns) > 1:
                    tables.append(
                        {
                            "table_id": i,
                            "rows": int(len(df)),
                            "columns": int(len(df.columns)),
                            "headers": [str(c) for c in df.columns],
                            "sample_data": df.head(3).to_dict("records") if len(df) > 0 else [],
                        }
                    )
        except Exception as e:  # noqa: BLE001
            logger.debug("Table extraction failed: %s", e)

        return tables

    # ------------------------- analysis helpers ------------------------- #

    def _create_content_blocks(self, text: str) -> List[Dict[str, Any]]:
        """Create content blocks for LLM processing with stable chunking (approx tokens)."""
        if not text:
            return []

        # Sentence split with graceful fallback
        try:
            sentences = sent_tokenize(text) if self._has_punkt else text.split(". ")
        except Exception:
            sentences = text.split(". ")

        blocks: List[Dict[str, Any]] = []
        current: List[str] = []
        current_tokens = 0
        block_id = 0
        cursor = 0  # start_char tracker

        for sentence in sentences:
            sentence_tokens = max(1, len(sentence) // 4)  # rough 4 chars/token
            if current_tokens + sentence_tokens > self.config["chunk_size_tokens"] and current:
                block_text = " ".join(current)
                end_char = cursor + len(block_text)
                blocks.append(
                    {
                        "block_id": f"block_{block_id}",
                        "text": block_text,
                        "start_char": cursor,
                        "end_char": end_char,
                        "token_count": current_tokens,
                        "sentence_count": len(current),
                    }
                )
                # Overlap
                overlap = current[-2:] if len(current) > 2 else current[:]
                current = overlap + [sentence]
                current_tokens = sum(max(1, len(s) // 4) for s in current)
                cursor = end_char - len(" ".join(overlap))  # approximate
                block_id += 1
            else:
                current.append(sentence)
                current_tokens += sentence_tokens

        if current:
            block_text = " ".join(current)
            end_char = cursor + len(block_text)
            blocks.append(
                {
                    "block_id": f"block_{block_id}",
                    "text": block_text,
                    "start_char": cursor,
                    "end_char": end_char,
                    "token_count": current_tokens,
                    "sentence_count": len(current),
                }
            )

        return blocks

    def _detect_entities(self, text: str) -> Dict[str, List[str]]:
        """Detect entities like candidate names and political parties (heuristics)."""
        entities = {"candidates": [], "parties": [], "offices": []}
        text_lower = text.lower()

        for pattern in self._candidate_patterns:
            for match in re.findall(pattern, text):
                if match not in entities["candidates"]:
                    entities["candidates"].append(match)

        for party in self._party_keywords:
            if party in text_lower and party not in entities["parties"]:
                entities["parties"].append(party)

        office_patterns = [
            r"\b(?:senate|senator)\b",
            r"\b(?:house|representative|rep\.)\b",
            r"\b(?:governor|gov\.)\b",
            r"\b(?:mayor)\b",
            r"\b(?:judge|justice)\b",
        ]
        for pattern in office_patterns:
            for m in re.findall(pattern, text_lower):
                if m not in entities["offices"]:
                    entities["offices"].append(m)

        return entities

    def _detect_issues(self, text: str) -> Dict[str, int]:
        """Detect mentions of canonical issues and count occurrences."""
        hits: Dict[str, int] = {}
        text_lower = text.lower()
        for issue, keywords in self._issue_keywords.items():
            count = sum(text_lower.count(kw.lower()) for kw in keywords)
            if count > 0:
                hits[issue.value] = count
        return hits

    def _detect_language_with_confidence(self, text: str) -> Tuple[str, float]:
        """Detect language with confidence score (best-effort)."""
        if not text or len(text.strip()) < 50:
            return "en", 0.5
        try:
            # Import here to avoid hard dependency at module import time
            from langdetect import detect_langs  # type: ignore

            lang_probs = detect_langs(text)
            if lang_probs:
                best = lang_probs[0]
                return best.lang, float(best.prob)
            return "en", 0.5
        except (LangDetectException, Exception) as e:  # noqa: BLE001
            logger.debug("Language detection failed: %s", e)
            # Simple heuristic fallback
            english_indicators = {"the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
            words = text.lower().split()
            english_count = sum(1 for w in words if w in english_indicators)
            confidence = min(1.0, (english_count / max(len(words), 1)) * 10)
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
        """Calculate usefulness score and keep/drop decision."""
        score = 0.0
        reasons: List[str] = []

        # 1) Substance
        if word_count >= self.config["min_word_count"]:
            score += 0.2
            reasons.append("sufficient_length")
        elif word_count >= 20:
            score += 0.1
            reasons.append("minimal_length")
        else:
            reasons.append("too_short")

        if tables:
            score += 0.1
            reasons.append("has_tables")

        # 2) Language
        if language == "en" and language_confidence >= self.config["min_language_confidence"]:
            score += 0.15
            reasons.append("english_high_confidence")
        elif language == "en" and language_confidence >= 0.5:
            score += 0.1
            reasons.append("english_medium_confidence")
        else:
            reasons.append("non_english_or_low_confidence")

        # 3) Topical relevance (fix: consider only candidate list for "has_candidates")
        has_candidates = len(entity_hits.get("candidates", [])) > 0
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

        # 4) Content quality
        if text.strip():
            meaningful = len([w for w in text.split() if len(w) > 3])
            density = meaningful / max(word_count, 1)
            if density > 0.6:
                score += 0.1
                reasons.append("high_content_density")
            elif density > 0.4:
                score += 0.05
                reasons.append("medium_content_density")
            else:
                reasons.append("low_content_density")

        # 5) Source credibility
        source = original_item.get("source")
        source_url = getattr(source, "url", None) or (source.get("url") if isinstance(source, dict) else "")
        detected_source_type = (original_item.get("detected_source_type") or "").lower()

        if any(domain in str(source_url) for domain in [".gov", ".edu", "fec.gov", "ballotpedia"]):
            score += 0.15
            reasons.append("official_source")
        elif detected_source_type in {"government", "news"}:
            score += 0.1
            reasons.append("credible_source_type")
        elif detected_source_type == "social_media":
            score += 0.05
            reasons.append("social_media_source")

        # 6) Freshness & evergreen
        if structured_metadata.get("published_at"):
            score += 0.05
            reasons.append("has_publication_date")
        if any(ind in str(source_url).lower() for ind in ["filing", "statute", "law", "regulation"]):
            score += 0.05
            reasons.append("evergreen_content")

        # Penalties
        if text and (len(set(text.split())) / max(word_count, 1)) < 0.3:
            score -= 0.1
            reasons.append("highly_repetitive")

        if text:
            special_ratio = len(re.findall(r"[^\w\s]", text)) / max(len(text), 1)
            if special_ratio > 0.4:
                score -= 0.1
                reasons.append("too_many_special_chars")

        if (original_item.get("method") or "").lower() == "selenium" and word_count < 50:
            score -= 0.05
            reasons.append("poor_dynamic_extraction")

        final = max(0.0, min(1.0, score))
        is_useful = final >= self.config["usefulness_threshold"]

        # Override for official docs with some content
        if not is_useful and any(domain in str(source_url) for domain in [".gov", "fec.gov"]) and word_count > 10:
            is_useful = True
            reasons.append("official_document_override")

        return final, is_useful, reasons

    def _calculate_extraction_quality(self, text: str, method: str) -> float:
        """Quality score for the extraction process itself."""
        if not text:
            return 0.0

        score = 0.5  # Base
        if len(text) < 100:
            score *= 0.7

        sentence_count = self._safe_sentence_count(text)
        if sentence_count > 0:
            avg_len = len(text.split()) / sentence_count
            if 10 <= avg_len <= 40:
                score *= 1.2
            elif avg_len < 5 or avg_len > 60:
                score *= 0.8

        if method == "html_readability":
            score *= 1.1
        elif method == "pdf_parser":
            score *= 0.9
        elif method == "selenium":
            score *= 0.85

        return min(1.0, score)

    # ------------------------- misc utils ------------------------- #

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text with enhanced processing."""
        if not text:
            return ""

        # Remove control characters (preserve basic whitespace)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]", "", text)

        # Normalize Unicode quotes/dashes (basic set)
        text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        text = text.replace("–", "-").replace("—", "-")

        # Replace URLs/emails with placeholders
        text = re.sub(r"https?://[^\s]+", "[URL]", text)
        text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)

        # Collapse whitespace then normalize punctuation spacing
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = re.sub(r"([,.!?;:])\s*", r"\1 ", text)
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _detect_language(self, text: str) -> str:
        """Simple language detection fallback method (kept for compatibility)."""
        language, _ = self._detect_language_with_confidence(text)
        return language

    def _calculate_quality_score(self, text: str) -> float:
        """Legacy method for backward compatibility."""
        return self._calculate_extraction_quality(text, "unknown")

    # ------------------------- private helpers ------------------------- #

    def _is_near_duplicate(self, simhash_value: int) -> bool:
        """Check if content is a near-duplicate using SimHash distance."""
        for existing_hash in list(self._seen_simhashes.keys()):
            distance = bin(simhash_value ^ existing_hash).count("1")
            if distance <= self.config["simhash_threshold"]:
                return True
        return False

    def _safe_sentence_count(self, text: str) -> int:
        try:
            if self._has_punkt:
                return len(sent_tokenize(text))
        except Exception:
            pass
        # Fallback heuristic
        return max(1, text.count(".") + text.count("!") + text.count("?"))

    def _get_original_size(self, item: Dict[str, Any], content: Any, content_bytes: Optional[bytes]) -> int:
        if item.get("content_length") is not None:
            try:
                return int(item["content_length"])
            except Exception:
                pass
        if isinstance(content_bytes, (bytes, bytearray)):
            return len(content_bytes)
        if isinstance(content, str):
            return len(content.encode("utf-8"))
        if isinstance(content, (bytes, bytearray)):
            return len(content)
        return 0

    def _check_nltk_punkt(self) -> bool:
        try:
            import nltk  # type: ignore

            nltk.data.find("tokenizers/punkt")
            return True
        except Exception:
            # Do not auto-download here to avoid network calls in production
            logger.debug("NLTK punkt not available; falling back to naive sentence split.")
            return False

    # inside ContentExtractor (new helper)
    async def _mini_cleanup(self, providers, text: str, tables: list[dict]) -> tuple[str, list[dict]]:
        if not providers or not text or not tables:
            return text, tables
        prompt = (
            "Normalize table headers to plain English, keep data as-is. "
            "Return JSON {tables:[{headers:[], sample_data:[]}]} with the same row counts as input."
        )
        try:
            resp = await providers.generate_json(
                TaskType.EXTRACT,
                prompt + "\n" + json.dumps({"tables": tables})[:6000],
                response_format={"type": "object", "properties": {"tables": {"type": "array"}}},
                max_tokens=600,
                model_id="gpt-4o-mini",
            )
            new_tables = resp.get("tables") or tables
            return text, new_tables
        except Exception:
            return text, tables
