"""
Extract Service for SmarterVote Pipeline

This module handles content extraction from HTML, PDF, and JSON sources.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from bs4 import BeautifulSoup
import PyPDF2
from io import BytesIO

from ..schema import ExtractedContent, Source


logger = logging.getLogger(__name__)


class ExtractService:
    """Service for extracting text content from various formats."""
    
    def __init__(self):
        pass
    
    async def extract_all(self, raw_content: List[Dict[str, Any]]) -> List[ExtractedContent]:
        """
        Extract text from all provided content items.
        
        Args:
            raw_content: List of raw content with metadata
            
        Returns:
            List of extracted content objects
        """
        logger.info(f"Extracting text from {len(raw_content)} items")
        
        extracted = []
        for item in raw_content:
            try:
                result = await self._extract_single_item(item)
                if result:
                    extracted.append(result)
            except Exception as e:
                logger.error(f"Failed to extract content from {item.get('source', {}).get('url', 'unknown')}: {e}")
        
        logger.info(f"Successfully extracted {len(extracted)} items")
        return extracted
    
    async def _extract_single_item(self, item: Dict[str, Any]) -> Optional[ExtractedContent]:
        """Extract text from a single content item."""
        source = item["source"]
        content_type = item.get("content_type", "")
        content = item["content"]
        
        if "text/html" in content_type or source.type.value in ["website", "news"]:
            text = self._extract_from_html(content)
        elif "application/pdf" in content_type:
            text = self._extract_from_pdf(content)
        elif "application/json" in content_type:
            text = self._extract_from_json(content)
        else:
            # Try to extract as plain text
            text = str(content) if content else ""
        
        if not text or len(text.strip()) < 10:
            logger.warning(f"Extracted text too short for {source.url}")
            return None
        
        # Count words
        word_count = len(text.split())
        
        return ExtractedContent(
            source=source,
            text=text,
            metadata={
                "original_content_type": content_type,
                "extraction_method": self._get_extraction_method(content_type, source.type.value),
                "original_size_bytes": item.get("size_bytes", 0)
            },
            extraction_timestamp=datetime.utcnow(),
            word_count=word_count,
            language="en"  # TODO: Implement language detection
        )
    
    def _extract_from_html(self, html_content: str) -> str:
        """Extract text from HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    
    def _extract_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF content."""
        text = ""
        try:
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
                
        except Exception as e:
            logger.error(f"Error extracting PDF: {e}")
            return ""
        
        return text.strip()
    
    def _extract_from_json(self, json_content: Any) -> str:
        """Extract relevant text from JSON content."""
        if isinstance(json_content, dict):
            # Look for common text fields
            text_fields = ["description", "content", "body", "text", "summary", "title"]
            texts = []
            
            for field in text_fields:
                if field in json_content and isinstance(json_content[field], str):
                    texts.append(json_content[field])
            
            # Also extract from nested structures
            for key, value in json_content.items():
                if isinstance(value, str) and len(value) > 50:  # Likely meaningful text
                    texts.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and len(item) > 50:
                            texts.append(item)
            
            return " ".join(texts)
        
        elif isinstance(json_content, list):
            texts = []
            for item in json_content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict):
                    texts.append(self._extract_from_json(item))
            return " ".join(texts)
        
        else:
            return str(json_content)
    
    def _get_extraction_method(self, content_type: str, source_type: str) -> str:
        """Determine the extraction method used."""
        if "text/html" in content_type:
            return "beautifulsoup"
        elif "application/pdf" in content_type:
            return "pypdf2"
        elif "application/json" in content_type:
            return "json_parser"
        else:
            return "plain_text"
