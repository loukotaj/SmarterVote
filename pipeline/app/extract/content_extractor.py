"""
Content Extraction Engine for SmarterVote Pipeline

This module handles extraction of meaningful text from various content formats:
- HTML parsing and cleaning
- PDF text extraction
- JSON content parsing
- Plain text processing

TODO: Implement the following features:
- [ ] Add OCR support for image-based PDFs
- [ ] Implement table extraction from HTML and PDFs
- [ ] Add support for Word documents (.docx)
- [ ] Implement language detection and multi-language support
- [ ] Add content quality scoring
- [ ] Support for structured data extraction (microdata, JSON-LD)
- [ ] Add image alt-text extraction
- [ ] Implement automatic content categorization
- [ ] Add support for email (mbox, eml) formats
- [ ] Implement content deduplication algorithms
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from bs4 import BeautifulSoup
import PyPDF2
from io import BytesIO

from ..schema import ExtractedContent, Source


logger = logging.getLogger(__name__)


class ContentExtractor:
    """Engine for extracting text content from various formats."""

    def __init__(self):
        # TODO: Add configuration for extraction parameters
        self.config = {
            "min_text_length": 10,
            "max_text_length": 1000000,  # 1MB of text
            "remove_html_tags": ["script", "style", "nav", "footer", "header", "aside"],
            "pdf_max_pages": 100,
            "language_detection": True,
        }

    async def extract_content(
        self, raw_content: List[Dict[str, Any]]
    ) -> List[ExtractedContent]:
        """
        Extract text from all provided content items.

        Args:
            raw_content: List of raw content with metadata

        Returns:
            List of extracted content objects

        TODO:
        - [ ] Add parallel processing for large content lists
        - [ ] Implement content validation and sanitization
        - [ ] Add extraction quality metrics
        """
        logger.info(f"Extracting text from {len(raw_content)} items")

        extracted = []
        for item in raw_content:
            try:
                result = await self._extract_single_item(item)
                if result:
                    extracted.append(result)
            except Exception as e:
                logger.error(
                    f"Failed to extract content from {item.get('source', {}).get('url', 'unknown')}: {e}"
                )

        logger.info(f"Successfully extracted {len(extracted)} items")
        return extracted

    async def _extract_single_item(
        self, item: Dict[str, Any]
    ) -> Optional[ExtractedContent]:
        """
        Extract text from a single content item.

        TODO:
        - [ ] Add content type auto-detection
        - [ ] Implement extraction confidence scoring
        - [ ] Add metadata preservation from original content
        """
        source = item["source"]
        content_type = item.get("content_type", "")
        content = item["content"]

        # Determine extraction method
        if "text/html" in content_type or source.type.value in ["website", "news"]:
            text = self._extract_from_html(content)
            method = "html_parser"
        elif "application/pdf" in content_type:
            text = self._extract_from_pdf(content)
            method = "pdf_parser"
        elif "application/json" in content_type:
            text = self._extract_from_json(content)
            method = "json_parser"
        else:
            # Try to extract as plain text
            text = self._extract_from_text(content)
            method = "text_parser"

        if not text or len(text.strip()) < self.config["min_text_length"]:
            logger.warning(f"Extracted text too short for {source.url}")
            return None

        # Count words and estimate reading time
        word_count = len(text.split())
        reading_time_minutes = max(1, word_count // 200)  # Average reading speed

        return ExtractedContent(
            source=source,
            text=text,
            metadata={
                "original_content_type": content_type,
                "extraction_method": method,
                "original_size_bytes": item.get("size_bytes", 0),
                "word_count": word_count,
                "reading_time_minutes": reading_time_minutes,
                "character_count": len(text),
                "extraction_quality_score": self._calculate_quality_score(text),
            },
            extraction_timestamp=datetime.utcnow(),
            word_count=word_count,
            language=(
                self._detect_language(text)
                if self.config["language_detection"]
                else "en"
            ),
        )

    def _extract_from_html(self, html_content: str) -> str:
        """
        Extract text from HTML content.

        TODO:
        - [ ] Add support for preserving link context
        - [ ] Implement article content detection (readability algorithms)
        - [ ] Add support for extracting image captions
        - [ ] Preserve important structural information (headers, lists)
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove unwanted elements
        for tag in self.config["remove_html_tags"]:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove comments
        for element in soup(
            text=lambda text: isinstance(text, str) and text.strip().startswith("<!--")
        ):
            element.extract()

        # Get text content
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return self._clean_text(text)

    def _extract_from_pdf(self, pdf_content: bytes) -> str:
        """
        Extract text from PDF content.

        TODO:
        - [ ] Add support for encrypted PDFs
        - [ ] Implement OCR for image-based PDFs
        - [ ] Add table extraction capabilities
        - [ ] Support for PDF metadata extraction
        """
        text = ""
        try:
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            # Limit pages to avoid memory issues
            max_pages = min(len(pdf_reader.pages), self.config["pdf_max_pages"])

            for page_num in range(max_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        except Exception as e:
            logger.error(f"Error extracting PDF: {e}")
            return ""

        return self._clean_text(text.strip())

    def _extract_from_json(self, json_content: Any) -> str:
        """
        Extract relevant text from JSON content.

        TODO:
        - [ ] Add schema-aware extraction for known APIs
        - [ ] Implement nested object traversal with depth limits
        - [ ] Add support for JSON-LD structured data
        - [ ] Implement field importance scoring
        """

        def extract_text_recursive(obj, depth=0, max_depth=5):
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
                ]

                for field in priority_fields:
                    if (
                        field in obj
                        and isinstance(obj[field], str)
                        and len(obj[field]) > 10
                    ):
                        texts.append(obj[field])

                # Extract from other string fields
                for key, value in obj.items():
                    if key not in priority_fields:
                        if isinstance(value, str) and len(value) > 50:
                            texts.append(value)
                        elif isinstance(value, (dict, list)):
                            texts.extend(
                                extract_text_recursive(value, depth + 1, max_depth)
                            )

            elif isinstance(obj, list):
                for item in obj:
                    texts.extend(extract_text_recursive(item, depth + 1, max_depth))

            elif isinstance(obj, str) and len(obj) > 50:
                texts.append(obj)

            return texts

        extracted_texts = extract_text_recursive(json_content)
        return self._clean_text(" ".join(extracted_texts))

    def _extract_from_text(self, text_content: Any) -> str:
        """
        Process plain text content.

        TODO:
        - [ ] Add encoding detection and conversion
        - [ ] Implement text format detection (markdown, etc.)
        - [ ] Add support for structured text formats
        """
        if not isinstance(text_content, str):
            text_content = str(text_content)

        return self._clean_text(text_content)

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text.

        TODO:
        - [ ] Add more sophisticated text cleaning
        - [ ] Implement spell checking and correction
        - [ ] Add normalization for different encodings
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove control characters
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]", "", text)

        # Normalize quotes
        text = re.sub(r'[""' "„‚‹›«»]", '"', text)

        # Remove repeated punctuation
        text = re.sub(r"[.]{3,}", "...", text)
        text = re.sub(r"[!]{2,}", "!", text)
        text = re.sub(r"[?]{2,}", "?", text)

        return text.strip()

    def _detect_language(self, text: str) -> str:
        """
        Detect the language of the text.

        TODO:
        - [ ] Implement actual language detection using langdetect or spacy
        - [ ] Add confidence scoring for language detection
        - [ ] Support for multi-language documents
        """
        # Placeholder implementation
        # TODO: Implement real language detection
        return "en"

    def _calculate_quality_score(self, text: str) -> float:
        """
        Calculate a quality score for extracted text.

        TODO:
        - [ ] Implement comprehensive quality metrics
        - [ ] Add readability scoring
        - [ ] Check for extraction artifacts
        """
        if not text:
            return 0.0

        score = 1.0

        # Penalize very short text
        if len(text) < 100:
            score *= 0.5

        # Penalize text with too many special characters
        special_char_ratio = len(re.findall(r"[^\w\s]", text)) / len(text)
        if special_char_ratio > 0.3:
            score *= 0.7

        # Reward proper sentence structure
        sentence_count = len(re.findall(r"[.!?]+", text))
        if sentence_count > 0:
            avg_sentence_length = len(text.split()) / sentence_count
            if 10 <= avg_sentence_length <= 30:  # Reasonable sentence length
                score *= 1.2

        return min(1.0, score)
