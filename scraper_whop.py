"""
Whop alert scraper module using Playwright.
Fetches trade alerts from Whop's JavaScript-rendered pages.
"""

import os
import logging
import subprocess
from typing import List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

import config

def get_chromium_path() -> str:
    """Find the system chromium executable path."""
    try:
        result = subprocess.run(
            ["which", "chromium"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium"

logger = logging.getLogger(__name__)


class WhopScraperPlaywright:
    """Fetches alerts from Whop Trade Alerts feed using Playwright."""
    
    def __init__(
        self,
        alerts_url: Optional[str] = None,
        access_token: Optional[str] = None
    ):
        self.alerts_url = alerts_url or config.WHOP_ALERTS_URL
        self.access_token = access_token or config.WHOP_SESSION
    
    def fetch_alerts(self) -> List[str]:
        """
        Fetch alerts from Whop URL using Playwright headless browser.
        Returns list of alert text strings.
        """
        if not self.alerts_url:
            logger.warning("WHOP_ALERTS_URL not configured")
            return []
        
        if not self.access_token:
            logger.warning("WHOP_SESSION (access token) not configured")
            return []
        
        logger.info(f"Fetching alerts from Whop using Playwright...")
        logger.debug(f"URL: {self.alerts_url}")
        
        try:
            with sync_playwright() as p:
                chromium_path = get_chromium_path()
                logger.debug(f"Using chromium at: {chromium_path}")
                browser = p.chromium.launch(
                    headless=True,
                    executable_path=chromium_path,
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
                )
                
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                context.add_cookies([{
                    "name": "whop-core.access-token",
                    "value": self.access_token,
                    "domain": ".whop.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                }])
                
                page = context.new_page()
                
                page.goto(self.alerts_url, wait_until="networkidle", timeout=30000)
                
                page.wait_for_timeout(2000)
                
                title = page.title()
                content = page.content()
                
                if self._is_login_page(title, content):
                    logger.error("Whop auth failed or token expired.")
                    browser.close()
                    return []
                
                alerts = self._extract_alerts(page)
                
                if alerts:
                    preview = alerts[0][:300] if len(alerts[0]) > 300 else alerts[0]
                    logger.info(f"First alert preview: {preview}")
                
                logger.info(f"Successfully fetched {len(alerts)} alerts from Whop")
                
                browser.close()
                return alerts
                
        except PlaywrightTimeout as e:
            logger.error(f"Timeout fetching Whop page: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching alerts with Playwright: {e}")
            return []
    
    def _is_login_page(self, title: str, content: str) -> bool:
        """Check if the page is a login/landing page instead of alerts."""
        login_indicators = [
            "log in",
            "sign in",
            "sign up",
            "join now",
            "create account",
        ]
        
        title_lower = title.lower()
        content_lower = content.lower()
        
        for indicator in login_indicators:
            if indicator in title_lower:
                return True
        
        login_matches = sum(1 for ind in login_indicators if ind in content_lower)
        if login_matches >= 2 and "alert" not in content_lower:
            return True
        
        return False
    
    def _extract_alerts(self, page) -> List[str]:
        """
        Extract individual alert posts from the rendered page.
        Tries multiple selectors to find alert content.
        """
        alerts = []
        
        selectors_to_try = [
            "[data-testid='feed-post']",
            "[data-testid='post-content']",
            ".feed-post",
            ".post-card",
            ".alert-card",
            "article",
            "[class*='post']",
            "[class*='feed'] > div",
        ]
        
        for selector in selectors_to_try:
            try:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    logger.debug(f"Found {len(elements)} elements with selector: {selector}")
                    for el in elements:
                        text = el.inner_text().strip()
                        if text and len(text) > 20:
                            alerts.append(text)
                    if alerts:
                        break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        if not alerts:
            logger.debug("No post elements found, extracting main content...")
            try:
                main_selectors = ["main", "[role='main']", ".content", "#content"]
                for sel in main_selectors:
                    main_el = page.query_selector(sel)
                    if main_el:
                        text = main_el.inner_text().strip()
                        if text and len(text) > 50:
                            alerts = self._split_into_alerts(text)
                            break
            except Exception as e:
                logger.debug(f"Main content extraction failed: {e}")
        
        if not alerts:
            try:
                body_text = page.inner_text("body")
                if body_text and len(body_text) > 100:
                    logger.debug(f"Fallback: extracting from body (length: {len(body_text)})")
                    alerts = self._split_into_alerts(body_text)
            except Exception as e:
                logger.debug(f"Body extraction failed: {e}")
        
        return alerts
    
    def _split_into_alerts(self, text: str) -> List[str]:
        """
        Split bulk text into individual alerts.
        Looks for common patterns that separate alerts.
        """
        import re
        
        patterns = [
            r'\n\s*(?=(?:[A-Z]{1,5}\s+(?:Call|Put|Debit|Credit)))',
            r'\n\s*(?=(?:\d{1,2}/\d{1,2}/\d{2,4}\s+exp))',
            r'\n{3,}',
        ]
        
        for pattern in patterns:
            parts = re.split(pattern, text, flags=re.IGNORECASE)
            valid_parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 30]
            if len(valid_parts) > 1:
                return valid_parts
        
        if len(text) > 100:
            return [text]
        
        return []


def fetch_alerts_from_local_file(filepath: Optional[str] = None) -> List[str]:
    """
    Read alerts from a local sample file.
    Returns list of alert strings (split by double newlines).
    """
    filepath = filepath or config.SAMPLE_ALERTS_FILE
    
    if not os.path.exists(filepath):
        logger.warning(f"Sample alerts file not found: {filepath}")
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        alerts = [a.strip() for a in content.split('\n\n\n') if a.strip()]
        if len(alerts) <= 1:
            alerts = [a.strip() for a in content.split('\n\n') if a.strip() and len(a.strip()) > 30]
        
        return alerts
    except IOError as e:
        logger.error(f"Failed to read sample alerts file: {e}")
        return []


def get_alerts() -> List[str]:
    """
    Main function to get alerts.
    Returns list of alert strings.
    Tries Whop first (via Playwright), falls back to local file.
    """
    if config.USE_LOCAL_ALERTS:
        logger.info("Using local alerts file (USE_LOCAL_ALERTS=true)")
        return fetch_alerts_from_local_file()
    
    scraper = WhopScraperPlaywright()
    alerts = scraper.fetch_alerts()
    
    if alerts:
        return alerts
    
    logger.info("Falling back to local sample alerts file")
    return fetch_alerts_from_local_file()


def get_alerts_as_text() -> Optional[str]:
    """
    Legacy function for backwards compatibility.
    Returns alerts as a single joined text string.
    """
    alerts = get_alerts()
    if alerts:
        return "\n\n\n".join(alerts)
    return None
