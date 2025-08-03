"""
Fetch Service for SmarterVote Pipeline

This module handles HTTP download and data collection from discovered sources.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from ..schema import Source, SourceType


logger = logging.getLogger(__name__)


class FetchService:
    """Service for fetching content from various sources."""
    
    def __init__(self):
        self.session = None
        self.selenium_driver = None
    
    async def fetch_all(self, sources: List[Source]) -> List[Dict[str, Any]]:
        """
        Fetch content from all provided sources.
        
        Args:
            sources: List of sources to fetch
            
        Returns:
            List of fetched content with metadata
        """
        logger.info(f"Fetching content from {len(sources)} sources")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            self.session = client
            
            tasks = []
            for source in sources:
                task = self._fetch_single_source(source)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and None results
            content = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to fetch {sources[i].url}: {result}")
                elif result is not None:
                    content.append(result)
            
            logger.info(f"Successfully fetched {len(content)} items")
            return content
    
    async def _fetch_single_source(self, source: Source) -> Optional[Dict[str, Any]]:
        """Fetch content from a single source."""
        try:
            if source.type in [SourceType.WEBSITE, SourceType.NEWS]:
                return await self._fetch_web_content(source)
            elif source.type == SourceType.PDF:
                return await self._fetch_pdf_content(source)
            elif source.type == SourceType.API:
                return await self._fetch_api_content(source)
            else:
                logger.warning(f"Unsupported source type: {source.type}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching {source.url}: {e}")
            return None
    
    async def _fetch_web_content(self, source: Source) -> Dict[str, Any]:
        """Fetch content from a web page."""
        response = await self.session.get(str(source.url))
        response.raise_for_status()
        
        return {
            "source": source,
            "content": response.text,
            "content_type": response.headers.get("content-type", ""),
            "status_code": response.status_code,
            "fetched_at": datetime.utcnow(),
            "size_bytes": len(response.content)
        }
    
    async def _fetch_pdf_content(self, source: Source) -> Dict[str, Any]:
        """Fetch PDF content."""
        response = await self.session.get(str(source.url))
        response.raise_for_status()
        
        return {
            "source": source,
            "content": response.content,
            "content_type": "application/pdf",
            "status_code": response.status_code,
            "fetched_at": datetime.utcnow(),
            "size_bytes": len(response.content)
        }
    
    async def _fetch_api_content(self, source: Source) -> Dict[str, Any]:
        """Fetch content from API endpoints."""
        headers = {"Accept": "application/json"}
        response = await self.session.get(str(source.url), headers=headers)
        response.raise_for_status()
        
        return {
            "source": source,
            "content": response.json(),
            "content_type": "application/json",
            "status_code": response.status_code,
            "fetched_at": datetime.utcnow(),
            "size_bytes": len(response.content)
        }
    
    def _setup_selenium_driver(self) -> webdriver.Chrome:
        """Setup Selenium Chrome driver for JavaScript-heavy sites."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        return webdriver.Chrome(options=chrome_options)
    
    async def fetch_with_selenium(self, source: Source) -> Dict[str, Any]:
        """Fetch content using Selenium for JavaScript-heavy sites."""
        if not self.selenium_driver:
            self.selenium_driver = self._setup_selenium_driver()
        
        self.selenium_driver.get(str(source.url))
        await asyncio.sleep(3)  # Wait for JavaScript to load
        
        content = self.selenium_driver.page_source
        
        return {
            "source": source,
            "content": content,
            "content_type": "text/html",
            "fetched_at": datetime.utcnow(),
            "size_bytes": len(content.encode('utf-8'))
        }
    
    def __del__(self):
        """Cleanup Selenium driver."""
        if self.selenium_driver:
            self.selenium_driver.quit()
