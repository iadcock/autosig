"""
Whop alert scraper module.
Fetches trade alerts from Whop or falls back to local sample file.
"""

import os
import logging
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


class WhopScraper:
    """Fetches alerts from Whop Trade Alerts feed."""
    
    def __init__(
        self,
        alerts_url: Optional[str] = None,
        session_cookie: Optional[str] = None
    ):
        self.alerts_url = alerts_url or config.WHOP_ALERTS_URL
        self.session_cookie = session_cookie or config.WHOP_SESSION
        self.session = requests.Session()
        
        if self.session_cookie:
            self.session.cookies.set("whop_session", self.session_cookie)
    
    def fetch_alerts(self) -> Optional[str]:
        """
        Fetch alerts from Whop URL.
        Returns raw alert text or None if fetch fails.
        """
        if not self.alerts_url:
            logger.warning("WHOP_ALERTS_URL not configured")
            return None
        
        if not self.session_cookie:
            logger.warning("WHOP_SESSION not configured")
            return None
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            
            response = self.session.get(
                self.alerts_url,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            return self._extract_alerts_from_html(response.text)
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch alerts from Whop: {e}")
            return None
    
    def _extract_alerts_from_html(self, html: str) -> str:
        """
        Extract alert text from Whop HTML response.
        This is a simplified extractor - may need adjustment based on actual Whop HTML structure.
        """
        import re
        
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        text = re.sub(r'<[^>]+>', '\n', text)
        
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()


def fetch_alerts_from_local_file(filepath: Optional[str] = None) -> Optional[str]:
    """
    Read alerts from a local sample file.
    Used as fallback when Whop fetching is not configured or fails.
    """
    filepath = filepath or config.SAMPLE_ALERTS_FILE
    
    if not os.path.exists(filepath):
        logger.warning(f"Sample alerts file not found: {filepath}")
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except IOError as e:
        logger.error(f"Failed to read sample alerts file: {e}")
        return None


def get_alerts() -> Optional[str]:
    """
    Main function to get alerts.
    Tries Whop first, falls back to local file.
    """
    if config.USE_LOCAL_ALERTS:
        logger.info("Using local alerts file (USE_LOCAL_ALERTS=true)")
        return fetch_alerts_from_local_file()
    
    scraper = WhopScraper()
    alerts = scraper.fetch_alerts()
    
    if alerts:
        return alerts
    
    logger.info("Falling back to local sample alerts file")
    return fetch_alerts_from_local_file()
