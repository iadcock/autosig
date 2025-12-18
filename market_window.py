"""
Market Window Detection for AUTO MODE.
Determines if current time is within trading window (market hours ± buffer).
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pytz

from env_loader import load_env

TIMEOUT = 10


def get_alpaca_market_clock() -> Optional[Dict[str, Any]]:
    """
    Get market clock from Alpaca API.
    
    Returns dict with is_open, next_open, next_close, or None on failure.
    """
    api_key = load_env("ALPACA_API_KEY") or ""
    api_secret = load_env("ALPACA_API_SECRET") or ""
    base_url = load_env("ALPACA_PAPER_BASE_URL") or "https://paper-api.alpaca.markets"
    
    if not api_key or not api_secret:
        return None
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    try:
        resp = requests.get(f"{base_url}/v2/clock", headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None


def is_within_auto_trading_window(now_dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Check if current time is within the auto trading window.
    
    Window = market_open - buffer to market_close + buffer
    Default buffer is 60 minutes (configurable via AUTO_WINDOW_BUFFER_MINUTES).
    
    Args:
        now_dt: Current datetime (defaults to now in configured timezone)
    
    Returns:
        {
            "within_window": bool,
            "reason": str,
            "market_open_time": str or None,
            "market_close_time": str or None,
            "window_start": str or None,
            "window_end": str or None,
            "is_market_open": bool,
            "current_time": str
        }
    """
    tz_name = load_env("TIMEZONE") or "America/New_York"
    buffer_minutes = int(load_env("AUTO_WINDOW_BUFFER_MINUTES") or "60")
    
    try:
        tz = pytz.timezone(tz_name)
    except:
        tz = pytz.timezone("America/New_York")
    
    if now_dt is None:
        now_dt = datetime.now(tz)
    elif now_dt.tzinfo is None:
        now_dt = tz.localize(now_dt)
    
    clock = get_alpaca_market_clock()
    
    if not clock:
        return {
            "within_window": False,
            "reason": "Failed to fetch market clock - failing closed for safety",
            "market_open_time": None,
            "market_close_time": None,
            "window_start": None,
            "window_end": None,
            "is_market_open": False,
            "current_time": now_dt.isoformat()
        }
    
    is_open = clock.get("is_open", False)
    next_open_str = clock.get("next_open", "")
    next_close_str = clock.get("next_close", "")
    
    try:
        if is_open and next_close_str:
            close_dt = datetime.fromisoformat(next_close_str.replace("Z", "+00:00"))
            close_local = close_dt.astimezone(tz)
            
            open_local = close_local.replace(hour=9, minute=30)
            
            window_start = open_local - timedelta(minutes=buffer_minutes)
            window_end = close_local + timedelta(minutes=buffer_minutes)
            
            within = window_start <= now_dt <= window_end
            
            return {
                "within_window": within,
                "reason": "Within trading window" if within else f"Outside window ({window_start.strftime('%H:%M')} - {window_end.strftime('%H:%M')})",
                "market_open_time": open_local.strftime("%H:%M"),
                "market_close_time": close_local.strftime("%H:%M"),
                "window_start": window_start.strftime("%H:%M"),
                "window_end": window_end.strftime("%H:%M"),
                "is_market_open": True,
                "current_time": now_dt.strftime("%H:%M:%S")
            }
        
        elif not is_open and next_open_str:
            open_dt = datetime.fromisoformat(next_open_str.replace("Z", "+00:00"))
            open_local = open_dt.astimezone(tz)
            
            window_start = open_local - timedelta(minutes=buffer_minutes)
            
            if now_dt >= window_start:
                return {
                    "within_window": True,
                    "reason": f"Pre-market buffer (market opens at {open_local.strftime('%H:%M')})",
                    "market_open_time": open_local.strftime("%H:%M"),
                    "market_close_time": None,
                    "window_start": window_start.strftime("%H:%M"),
                    "window_end": None,
                    "is_market_open": False,
                    "current_time": now_dt.strftime("%H:%M:%S")
                }
            else:
                return {
                    "within_window": False,
                    "reason": f"Market closed, opens at {open_local.strftime('%H:%M')}",
                    "market_open_time": open_local.strftime("%H:%M"),
                    "market_close_time": None,
                    "window_start": window_start.strftime("%H:%M"),
                    "window_end": None,
                    "is_market_open": False,
                    "current_time": now_dt.strftime("%H:%M:%S")
                }
        
        else:
            return {
                "within_window": False,
                "reason": "Unable to determine market hours",
                "market_open_time": None,
                "market_close_time": None,
                "window_start": None,
                "window_end": None,
                "is_market_open": is_open,
                "current_time": now_dt.strftime("%H:%M:%S")
            }
    
    except Exception as e:
        return {
            "within_window": False,
            "reason": f"Error parsing market times: {str(e)}",
            "market_open_time": None,
            "market_close_time": None,
            "window_start": None,
            "window_end": None,
            "is_market_open": False,
            "current_time": now_dt.isoformat()
        }
