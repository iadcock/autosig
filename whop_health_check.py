"""
Whop health check - validates connectivity and authentication WITHOUT trading.
Tests that we can fetch alerts from Whop and parse them.
"""

import logging
from datetime import datetime
from typing import Dict, Any

import config as whop_config

logger = logging.getLogger(__name__)


def _make_step(name: str, ok: bool, status: int = 0, summary: str = "", details: str = "") -> dict:
    """Create a standardized step result dict."""
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "summary": summary,
        "details": details[:200] if details else ""
    }


def whop_health_check() -> Dict[str, Any]:
    """
    Whop health check - NO trades placed.
    
    Steps:
    1) Check configuration (URL + cookies)
    2) Fetch alerts via Playwright
    3) Check for login page (auth failure)
    4) Attempt to parse at least one alert
    
    Returns dict with service, success, timestamp, steps.
    """
    from scraper_whop import WhopScraperPlaywright, _get_whop_cookies
    from parser import parse_alert
    
    steps = []
    alerts_fetched = []
    
    alerts_url = whop_config.WHOP_ALERTS_URL or ""
    cookies = _get_whop_cookies()
    
    if not alerts_url:
        steps.append(_make_step(
            "Config Check",
            False,
            0,
            "Missing WHOP_ALERTS_URL",
            "Set WHOP_ALERTS_URL environment variable"
        ))
        return {
            "service": "whop",
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps,
            "alerts_fetched": 0
        }
    
    if not cookies:
        steps.append(_make_step(
            "Config Check",
            False,
            0,
            "Missing Whop cookies",
            "Set WHOP_ACCESS_TOKEN or other Whop cookie env vars"
        ))
        return {
            "service": "whop",
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps,
            "alerts_fetched": 0
        }
    
    cookie_names = [c["name"] for c in cookies]
    steps.append(_make_step(
        "Config Check",
        True,
        200,
        f"URL configured, {len(cookies)} cookies set",
        f"Cookies: {', '.join(cookie_names)}"
    ))
    
    try:
        scraper = WhopScraperPlaywright(alerts_url)
        alerts_fetched = scraper.fetch_alerts()
        
        if alerts_fetched:
            steps.append(_make_step(
                "Fetch Alerts",
                True,
                200,
                f"Fetched {len(alerts_fetched)} alerts",
                f"First alert preview: {alerts_fetched[0][:100]}..." if alerts_fetched else ""
            ))
        else:
            steps.append(_make_step(
                "Fetch Alerts",
                False,
                0,
                "No alerts returned",
                "May indicate auth failure or empty feed"
            ))
            return {
                "service": "whop",
                "success": False,
                "timestamp": datetime.utcnow().isoformat(),
                "steps": steps,
                "alerts_fetched": 0
            }
    except Exception as e:
        error_msg = str(e)
        if "login" in error_msg.lower() or "auth" in error_msg.lower():
            steps.append(_make_step(
                "Fetch Alerts",
                False,
                401,
                "Authentication failed",
                error_msg
            ))
        else:
            steps.append(_make_step(
                "Fetch Alerts",
                False,
                0,
                f"Error: {error_msg[:50]}",
                error_msg
            ))
        return {
            "service": "whop",
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": steps,
            "alerts_fetched": 0
        }
    
    parsed_count = 0
    parse_errors = []
    
    for i, alert_text in enumerate(alerts_fetched[:3]):
        try:
            signal = parse_alert(alert_text)
            if signal:
                parsed_count += 1
        except Exception as e:
            parse_errors.append(str(e)[:50])
    
    if parsed_count > 0:
        steps.append(_make_step(
            "Parse Alerts",
            True,
            200,
            f"Parsed {parsed_count}/{min(3, len(alerts_fetched))} alerts successfully"
        ))
    elif parse_errors:
        steps.append(_make_step(
            "Parse Alerts",
            False,
            0,
            "Failed to parse any alerts",
            "; ".join(parse_errors)
        ))
    else:
        steps.append(_make_step(
            "Parse Alerts",
            True,
            200,
            "No parseable trading alerts (feed may be quiet)",
            "Non-trading posts are expected"
        ))
    
    fetch_ok = any(s["name"] == "Fetch Alerts" and s["ok"] for s in steps)
    success = fetch_ok
    
    return {
        "service": "whop",
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": steps,
        "alerts_fetched": len(alerts_fetched)
    }
