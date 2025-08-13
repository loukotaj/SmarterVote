"""
HTTP and Web Content Fetcher for SmarterVote Pipeline

This module handles downloading content from various web sources including:
- Static websites using httpx
- Dynamic JavaScript-heavy sites using Selenium
- PDF documents
- API endpoints

Features implemented:
- [x] Content-type sniffing and bytes storage for non-text content
- [x] Retry logic with exponential backoff
- [x] Per-host rate limiting with semaphores
- [x] Short-TTL caching for identical requests
- [x] URL canonicalization and tracking parameter removal
- [x] Rich metadata capture (ETag, Last-Modified, etc.)
- [x] Enhanced Selenium handling with smart waits
- [x] Source type detection based on content and URL patterns
"""

import asyncio
import hashlib
import logging
import mimetypes
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from ..schema import Source, SourceType
except ImportError:
    # Fallback for direct imports
    from shared.models import Source, SourceType

logger = logging.getLogger(__name__)


class WebContentFetcher:
    """Service for fetching content from various web sources with robust error handling and metadata capture."""

    def __init__(self):
        self.session = None
        self.selenium_driver = None
        self.executor = ThreadPoolExecutor(max_workers=2)  # For non-blocking Selenium

        # Enhanced configuration
        self.config = {
            "timeout": 30.0,
            "user_agent": "SmarterVote/1.0 (Educational Research)",
            "max_retries": 3,
            "base_retry_delay": 1.0,  # Base delay for exponential backoff
            "selenium_wait_time": 10,  # Smart wait timeout
            "cache_ttl_minutes": 15,  # Short TTL cache
            "max_content_size": 50 * 1024 * 1024,  # 50MB limit
            "rate_limit_per_host": 5,  # Max concurrent requests per host
        }

        # Internal state
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._host_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._seen_checksums: Set[str] = set()

        # Tracking parameters to remove from URLs
        self._tracking_params = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "gclid",
            "fbclid",
            "msclkid",
            "igshid",
            "_ga",
            "_gid",
        }

    async def fetch_content(self, sources: List[Source]) -> List[Dict[str, Any]]:
        """
        Fetch content from all provided sources with robust error handling and deduplication.

        Args:
            sources: List of sources to fetch content from

        Returns:
            List of fetched content with enriched metadata
        """
        logger.info(f"Fetching content from {len(sources)} sources")

        async with httpx.AsyncClient(
            timeout=self.config["timeout"],
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=True,  # Ensure redirects are followed automatically
        ) as client:
            self.session = client

            # Process sources with rate limiting
            tasks = []
            for source in sources:
                # Canonicalize URL and check for duplicates
                canonical_url = self._canonicalize_url(str(source.url))
                url_checksum = hashlib.sha256(canonical_url.encode()).hexdigest()

                if url_checksum in self._seen_checksums:
                    logger.info(f"Skipping duplicate URL: {canonical_url}")
                    continue

                self._seen_checksums.add(url_checksum)

                # Create rate-limited task
                task = self._rate_limited_fetch(source, canonical_url)
                tasks.append(task)

            if not tasks:
                logger.warning("No unique sources to fetch")
                return []

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter and process results
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to fetch source: {result}")
                elif result is not None:
                    successful_results.append(result)

            logger.info(f"Successfully fetched {len(successful_results)}/{len(sources)} sources")
            return successful_results

    def _canonicalize_url(self, url: str) -> str:
        """
        Canonicalize URL by expanding redirects, removing tracking params, and normalizing.

        Args:
            url: Original URL

        Returns:
            Canonicalized URL string
        """
        parsed = urlparse(url)

        # Remove tracking parameters
        query_params = parse_qs(parsed.query)
        filtered_params = {k: v for k, v in query_params.items() if k not in self._tracking_params}

        # Rebuild query string
        new_query = "&".join(f"{k}={v[0]}" for k, v in filtered_params.items())

        # Normalize scheme and host
        scheme = parsed.scheme.lower() if parsed.scheme else "https"
        netloc = parsed.netloc.lower()

        # Reconstruct URL
        canonical = urlunparse(
            (scheme, netloc, parsed.path.rstrip("/") or "/", parsed.params, new_query, "")  # Remove fragment
        )

        return canonical

    async def _rate_limited_fetch(self, source: Source, canonical_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single source with per-host rate limiting.

        Args:
            source: Source object to fetch
            canonical_url: Canonicalized URL

        Returns:
            Fetched content with metadata or None if failed
        """
        host = urlparse(canonical_url).netloc

        # Get or create semaphore for this host
        if host not in self._host_semaphores:
            self._host_semaphores[host] = asyncio.Semaphore(self.config["rate_limit_per_host"])

        async with self._host_semaphores[host]:
            return await self._fetch_single_source_with_retry(source, canonical_url)

    async def _fetch_single_source_with_retry(self, source: Source, canonical_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single source with retry logic and caching.

        Args:
            source: Source object to fetch
            canonical_url: Canonicalized URL

        Returns:
            Fetched content with metadata or None if failed
        """
        cache_key = hashlib.sha256(canonical_url.encode()).hexdigest()

        # Check cache first
        if cache_key in self._cache:
            cached_item = self._cache[cache_key]
            cache_time = cached_item.get("cached_at", datetime.min)
            ttl = timedelta(minutes=self.config["cache_ttl_minutes"])

            if datetime.utcnow() - cache_time < ttl:
                logger.debug(f"Using cached content for {canonical_url}")
                return cached_item["data"]

        # Attempt fetch with retries
        last_exception = None
        for attempt in range(self.config["max_retries"]):
            try:
                if attempt > 0:
                    delay = self.config["base_retry_delay"] * (2 ** (attempt - 1))
                    logger.debug(f"Retrying {canonical_url} after {delay}s delay (attempt {attempt + 1})")
                    await asyncio.sleep(delay)

                result = await self._fetch_single_source(source, canonical_url)

                if result:
                    # Cache successful result
                    self._cache[cache_key] = {"data": result, "cached_at": datetime.utcnow()}
                    return result

            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1} failed for {canonical_url}: {e}")

        logger.error(f"All {self.config['max_retries']} attempts failed for {canonical_url}: {last_exception}")
        return None

    async def _fetch_single_source(self, source: Source, canonical_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch content from a single source with enhanced metadata capture.

        Args:
            source: Source object to fetch
            canonical_url: Canonicalized URL to fetch

        Returns:
            Fetched content with enriched metadata
        """
        logger.debug(f"Fetching {canonical_url}")

        # Determine fetch method
        if self._requires_javascript(source):
            # Use Selenium for dynamic content
            return await self._fetch_with_selenium(source, canonical_url)
        else:
            # Use httpx for static content
            return await self._fetch_with_httpx(source, canonical_url)

    def _requires_javascript(self, source: Source) -> bool:
        """
        Determine if a source requires JavaScript rendering based on URL patterns and source type.
        """
        url_str = str(source.url).lower()

        # Known dynamic domains
        dynamic_domains = [
            "twitter.com",
            "x.com",
            "facebook.com",
            "instagram.com",
            "linkedin.com",
            "tiktok.com",
            "youtube.com",
        ]

        # Check for dynamic indicators
        has_dynamic_domain = any(domain in url_str for domain in dynamic_domains)
        has_social_type = source.type == SourceType.SOCIAL_MEDIA
        has_js_indicators = any(indicator in url_str for indicator in ["#", "spa", "app"])

        return has_dynamic_domain or has_social_type or has_js_indicators

    def _detect_source_type(self, url: str, content_type: str, content: bytes) -> SourceType:
        """
        Detect source type based on URL patterns, content type, and content analysis.

        Args:
            url: Source URL
            content_type: HTTP Content-Type header
            content: Raw content bytes

        Returns:
            Detected SourceType
        """
        url_lower = url.lower()

        # PDF detection
        if "application/pdf" in content_type or url_lower.endswith(".pdf"):
            return SourceType.PDF

        # Government sources
        gov_domains = [".gov", ".mil", "fec.gov", "ballotpedia.org"]
        if any(domain in url_lower for domain in gov_domains):
            return SourceType.GOVERNMENT

        # Social media
        social_domains = ["twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com"]
        if any(domain in url_lower for domain in social_domains):
            return SourceType.SOCIAL_MEDIA

        # News sites (basic heuristic)
        news_indicators = ["news", "times", "post", "herald", "journal", "tribune", "gazette"]
        if any(indicator in url_lower for indicator in news_indicators):
            return SourceType.NEWS

        # API endpoints
        api_indicators = ["api", "json", "rest"]
        if any(indicator in url_lower for indicator in api_indicators) or "application/json" in content_type:
            return SourceType.API

        # Default to website
        return SourceType.WEBSITE

    async def _fetch_with_httpx(self, source: Source, canonical_url: str) -> Dict[str, Any]:
        """
        Fetch content using httpx with enhanced metadata capture and content-type handling.

        Args:
            source: Source object
            canonical_url: Canonicalized URL to fetch

        Returns:
            Fetched content with enriched metadata
        """
        headers = {
            "User-Agent": self.config["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        # Add conditional request headers if available
        if hasattr(source, "etag") and source.etag:
            headers["If-None-Match"] = source.etag
        if hasattr(source, "last_modified") and source.last_modified:
            headers["If-Modified-Since"] = source.last_modified

        start_time = datetime.utcnow()
        response = await self.session.get(canonical_url, headers=headers)
        fetch_duration = (datetime.utcnow() - start_time).total_seconds()

        # Handle different response scenarios
        if response.status_code == 304:
            logger.debug(f"Content not modified: {canonical_url}")
            return None

        # Manual redirect handling for FEC or other 3xx loops (if follow_redirects fails)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if location:
                logger.warning(f"Manual redirect for {canonical_url} to {location} (status {response.status_code})")
                # Only reissue once to avoid infinite loops
                redirected_url = urljoin(canonical_url, location)
                response = await self.session.get(redirected_url, headers=headers)
                fetch_duration = (datetime.utcnow() - start_time).total_seconds()

        response.raise_for_status()

        # Content type detection and handling
        content_type = response.headers.get("content-type", "").lower()
        content_bytes = response.content
        content_size = len(content_bytes)

        # Size limit check
        if content_size > self.config["max_content_size"]:
            raise ValueError(f"Content too large: {content_size} bytes > {self.config['max_content_size']} limit")

        # Determine if content should be stored as bytes or text
        is_text_content = any(
            text_type in content_type for text_type in ["text/", "application/json", "application/xml", "application/xhtml"]
        )

        # Extract content appropriately
        if is_text_content:
            content = response.text
            encoding = response.encoding or "utf-8"
        else:
            # Store non-text content as bytes (PDFs, images, etc.)
            content = content_bytes
            encoding = None

        # Calculate content checksum
        content_checksum = hashlib.sha256(content_bytes).hexdigest()

        # Detect source type
        detected_source_type = self._detect_source_type(canonical_url, content_type, content_bytes)

        return {
            "source": source,
            "content": content,
            "content_bytes": content_bytes,  # Always store raw bytes
            "content_type": content_type,
            "mime_type": content_type.split(";")[0].strip(),
            "charset": encoding,
            "content_length": content_size,
            "content_checksum": content_checksum,
            "status_code": response.status_code,
            "final_url": str(response.url),
            "canonical_url": canonical_url,
            "fetch_timestamp": datetime.utcnow(),
            "fetch_duration_seconds": fetch_duration,
            "method": "httpx",
            "detected_source_type": detected_source_type,
            # Rich HTTP metadata
            "headers": dict(response.headers),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "cache_control": response.headers.get("cache-control"),
            "expires": response.headers.get("expires"),
            "x_robots_tag": response.headers.get("x-robots-tag"),
            # Response analysis
            "redirected": str(response.url) != canonical_url,
            "redirect_count": len(response.history),
            "is_text_content": is_text_content,
        }

    async def _fetch_with_selenium(self, source: Source, canonical_url: str) -> Dict[str, Any]:
        """
        Fetch content using Selenium with smart waits and non-blocking execution.

        Args:
            source: Source object
            canonical_url: Canonicalized URL to fetch

        Returns:
            Fetched content with enriched metadata
        """
        # Run Selenium in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self.executor, self._selenium_fetch_sync, source, canonical_url)
        return result

    def _selenium_fetch_sync(self, source: Source, canonical_url: str) -> Dict[str, Any]:
        """
        Synchronous Selenium fetch with smart waits and error capture.

        Args:
            source: Source object
            canonical_url: Canonicalized URL to fetch

        Returns:
            Fetched content with metadata
        """
        if not self.selenium_driver:
            self._init_selenium_driver()

        start_time = datetime.utcnow()
        console_errors = []

        try:
            # Navigate to page
            self.selenium_driver.get(canonical_url)

            # Smart wait for content to load
            wait = WebDriverWait(self.selenium_driver, self.config["selenium_wait_time"])

            # Wait for basic page structure (try multiple selectors)
            selectors_to_try = ["body", "main", "[role='main']", ".content", "#content", "article"]

            content_loaded = False
            for selector in selectors_to_try:
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    content_loaded = True
                    break
                except:
                    continue

            if not content_loaded:
                logger.warning(f"No content selectors found for {canonical_url}, using basic wait")
                import time

                time.sleep(3)  # Fallback wait

            # Additional wait for dynamic content
            try:
                # Wait for any loading indicators to disappear
                wait.until_not(EC.presence_of_element_located((By.CSS_SELECTOR, ".loading, .spinner, [data-loading]")))
            except:
                pass  # No loading indicators found, which is fine

            # Capture page information
            page_title = self.selenium_driver.title
            final_url = self.selenium_driver.current_url
            page_source = self.selenium_driver.page_source

            # Capture console errors
            try:
                logs = self.selenium_driver.get_log("browser")
                console_errors = [log for log in logs if log["level"] in ["SEVERE", "ERROR"]]
            except:
                pass  # Some drivers don't support console logs

            fetch_duration = (datetime.utcnow() - start_time).total_seconds()

            # Calculate content metrics
            content_bytes = page_source.encode("utf-8")
            content_checksum = hashlib.sha256(content_bytes).hexdigest()

            return {
                "source": source,
                "content": page_source,
                "content_bytes": content_bytes,
                "content_type": "text/html",
                "mime_type": "text/html",
                "charset": "utf-8",
                "content_length": len(content_bytes),
                "content_checksum": content_checksum,
                "status_code": 200,  # Selenium doesn't provide HTTP status
                "final_url": final_url,
                "canonical_url": canonical_url,
                "fetch_timestamp": datetime.utcnow(),
                "fetch_duration_seconds": fetch_duration,
                "method": "selenium",
                "detected_source_type": (
                    SourceType.SOCIAL_MEDIA if source.type == SourceType.SOCIAL_MEDIA else SourceType.WEBSITE
                ),
                # Selenium-specific metadata
                "page_title": page_title,
                "console_errors": console_errors,
                "content_loaded": content_loaded,
                "redirected": final_url != canonical_url,
                "is_text_content": True,
                # Placeholder metadata (not available in Selenium)
                "headers": {"content-type": "text/html; charset=utf-8"},
                "etag": None,
                "last_modified": None,
                "cache_control": None,
                "expires": None,
                "x_robots_tag": None,
                "redirect_count": 0,
            }

        except Exception as e:
            logger.error(f"Selenium fetch failed for {canonical_url}: {e}")
            raise

    def _init_selenium_driver(self):
        """
        Initialize Selenium Chrome driver with enhanced options and error handling.
        """
        options = Options()

        # Basic headless options
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # Enhanced stealth and performance options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-images")  # Faster loading
        options.add_argument("--disable-javascript")  # Only enable if needed
        options.add_argument("--no-first-run")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-background-networking")

        # User agent and stealth
        options.add_argument(f"--user-agent={self.config['user_agent']}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Logging preferences
        options.add_experimental_option(
            "prefs",
            {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
            },
        )

        # Enable browser logging
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

        try:
            self.selenium_driver = webdriver.Chrome(options=options)

            # Hide automation indicators
            self.selenium_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Set timeouts
            self.selenium_driver.set_page_load_timeout(self.config["selenium_wait_time"] * 2)
            self.selenium_driver.implicitly_wait(5)

            logger.info("Selenium Chrome driver initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Selenium driver: {e}")
            raise

    async def cleanup(self):
        """Clean up resources including Selenium driver and executor."""
        if hasattr(self, "selenium_driver") and self.selenium_driver:
            try:
                # Run cleanup in executor to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self.executor, self._cleanup_selenium)
            except Exception as e:
                logger.warning(f"Error during Selenium cleanup: {e}")

        if hasattr(self, "executor"):
            self.executor.shutdown(wait=True)

    def _cleanup_selenium(self):
        """Synchronous Selenium cleanup."""
        if self.selenium_driver:
            try:
                self.selenium_driver.quit()
                self.selenium_driver = None
            except Exception as e:
                logger.warning(f"Error quitting Selenium driver: {e}")

    def __del__(self):
        """Clean up Selenium driver on object destruction."""
        if hasattr(self, "selenium_driver") and self.selenium_driver:
            try:
                self.selenium_driver.quit()
            except:
                pass
