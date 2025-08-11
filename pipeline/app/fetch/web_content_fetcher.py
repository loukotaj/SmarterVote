"""
HTTP and Web Content Fetcher for SmarterVote Pipeline

This module handles downloading content from various web sources including:
- Static websites using httpx
- Dynamic JavaScript-heavy sites using Selenium
- PDF documents
- API endpoints

TODO: Implement the following features:
- [ ] Add retry logic with exponential backoff
- [ ] Implement rate limiting to respect robots.txt
- [ ] Add caching mechanism for repeated requests
- [ ] Support for different authentication methods (OAuth, API keys)
- [ ] Better error handling for different HTTP status codes
- [ ] Add support for POST requests and form submissions
- [ ] Implement proxy rotation for large-scale scraping
- [ ] Add content type validation before download
- [ ] Support for streaming large files
- [ ] Implement content deduplication based on URL/checksum
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from ..schema import Source, SourceType

logger = logging.getLogger(__name__)


class WebContentFetcher:
    """Service for fetching content from various web sources."""

    def __init__(self):
        self.session = None
        self.selenium_driver = None
        # TODO: Add configuration for timeouts, user agents, rate limits
        self.config = {
            "timeout": 30.0,
            "user_agent": "SmarterVote/1.0 (Educational Research)",
            "max_retries": 3,
            "selenium_wait_time": 3,
        }

    async def fetch_content(self, sources: List[Source]) -> List[Dict[str, Any]]:
        """
        Fetch content from all provided sources.

        Args:
            sources: List of sources to fetch content from

        Returns:
            List of fetched content with metadata

        TODO:
        - [ ] Add parallel processing limits to avoid overwhelming servers
        - [ ] Implement priority queue for high-priority sources
        - [ ] Support for batch processing with checkpoints
        """
        start_time = datetime.utcnow()
        logger.info(f"📥 Starting content fetch for {len(sources)} sources")
        
        # Log source breakdown by type
        source_types = {}
        for source in sources:
            source_type = source.type.value if hasattr(source.type, 'value') else str(source.type)
            source_types[source_type] = source_types.get(source_type, 0) + 1
        
        type_breakdown = ", ".join([f"{count} {stype}" for stype, count in source_types.items()])
        logger.info(f"📊 Source breakdown: {type_breakdown}")

        async with httpx.AsyncClient(timeout=self.config["timeout"]) as client:
            self.session = client

            tasks = []
            for source in sources:
                task = self._fetch_single_source(source)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Analyze results with detailed logging
            successful_results = []
            failed_count = 0
            total_size = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_count += 1
                    source_url = sources[i].url
                    error_type = type(result).__name__
                    logger.warning(f"❌ Fetch failed for {source_url}: {error_type} - {str(result)[:100]}")
                else:
                    successful_results.append(result)
                    if 'size_bytes' in result:
                        total_size += result['size_bytes']

            # Log final statistics
            duration = (datetime.utcnow() - start_time).total_seconds()
            success_rate = (len(successful_results) / len(sources)) * 100 if sources else 0
            avg_size = total_size / len(successful_results) if successful_results else 0
            
            logger.info(f"✅ Fetch completed: {len(successful_results)}/{len(sources)} sources ({success_rate:.1f}% success)")
            logger.info(f"📊 Total size: {total_size:,} bytes, Average: {avg_size:,.0f} bytes/source")
            logger.info(f"⏱️  Fetch duration: {duration:.1f}s ({duration/len(sources):.2f}s per source)")
            
            if failed_count > 0:
                logger.warning(f"⚠️  {failed_count} sources failed to fetch - check network connectivity and source availability")
            
            return successful_results

    async def _fetch_single_source(self, source: Source) -> Dict[str, Any]:
        """
        Fetch content from a single source.

        TODO:
        - [ ] Add source type detection based on URL patterns
        - [ ] Implement content-type specific handling
        - [ ] Add metrics collection (response time, size, etc.)
        """
        try:
            if source.type in [SourceType.WEBSITE] and self._requires_javascript(source):
                # Use Selenium for dynamic content
                return await self._fetch_with_selenium(source)
            else:
                # Use httpx for static content
                return await self._fetch_with_httpx(source)
        except Exception as e:
            # Add context to the error for better debugging
            raise Exception(f"Failed to fetch {source.url} ({source.type}): {str(e)}") from e

    def _requires_javascript(self, source: Source) -> bool:
        """
        Determine if a source requires JavaScript rendering.

        TODO:
        - [ ] Add heuristics based on URL patterns
        - [ ] Check for common JS frameworks in initial request
        - [ ] Maintain a database of known dynamic sites
        """
        # Simple heuristic for now
        dynamic_domains = ["twitter.com", "facebook.com", "instagram.com"]
        return any(domain in str(source.url) for domain in dynamic_domains)

    async def _fetch_with_httpx(self, source: Source) -> Dict[str, Any]:
        """
        Fetch content using httpx (for static websites).

        TODO:
        - [ ] Add support for different HTTP methods
        - [ ] Implement session management and cookie handling
        - [ ] Add custom headers based on source type
        - [ ] Support for compressed responses
        """
        headers = {
            "User-Agent": self.config["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        response = await self.session.get(str(source.url), headers=headers)
        response.raise_for_status()

        return {
            "source": source,
            "content": response.text,
            "content_type": response.headers.get("content-type", ""),
            "status_code": response.status_code,
            "size_bytes": len(response.content),
            "fetch_timestamp": datetime.utcnow(),
            "method": "httpx",
            "headers": dict(response.headers),
            "encoding": response.encoding,
        }

    async def _fetch_with_selenium(self, source: Source) -> Dict[str, Any]:
        """
        Fetch content using Selenium (for dynamic websites).

        TODO:
        - [ ] Add support for different browsers (Firefox, Safari)
        - [ ] Implement smart waiting for specific elements
        - [ ] Add screenshot capture for debugging
        - [ ] Support for form interactions and clicks
        - [ ] Add mobile user agent simulation
        """
        if not self.selenium_driver:
            self._init_selenium_driver()

        self.selenium_driver.get(str(source.url))

        # Wait for dynamic content to load
        # TODO: Replace with smart waiting for specific elements
        await asyncio.sleep(self.config["selenium_wait_time"])

        content = self.selenium_driver.page_source

        return {
            "source": source,
            "content": content,
            "content_type": "text/html",
            "status_code": 200,
            "size_bytes": len(content.encode("utf-8")),
            "fetch_timestamp": datetime.utcnow(),
            "method": "selenium",
            "page_title": self.selenium_driver.title,
            "current_url": self.selenium_driver.current_url,
        }

    def _init_selenium_driver(self):
        """
        Initialize Selenium Chrome driver with proper options.

        TODO:
        - [ ] Add driver pooling for better performance
        - [ ] Support for custom Chrome binary paths
        - [ ] Add extension support (ad blockers, etc.)
        - [ ] Implement driver health checks and auto-restart
        """
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.selenium_driver = webdriver.Chrome(options=options)
        # Hide automation indicators
        self.selenium_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def __del__(self):
        """Clean up Selenium driver."""
        if hasattr(self, "selenium_driver") and self.selenium_driver:
            try:
                self.selenium_driver.quit()
            except:
                pass
