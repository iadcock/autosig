"""
Market Session Detection for Smoke Tests.

Provides a simple interface to determine if market is open,
used by smoke tests to auto-select NO_FILL or FILL mode.
"""

from datetime import datetime
from typing import Dict, Any

from market_window import get_alpaca_market_clock


def get_market_session_status() -> Dict[str, Any]:
    """
    Get current market session status for smoke test mode selection.
    
    Uses Alpaca clock endpoint to determine if market is open.
    Fails closed (reports market closed) if clock unavailable.
    
    Returns:
        {
            "is_open": bool,
            "timestamp": str (ISO format),
            "next_open": str or None,
            "next_close": str or None,
            "session_label": str ("MARKET_OPEN", "MARKET_CLOSED", "UNKNOWN")
        }
    """
    clock = get_alpaca_market_clock()
    
    if not clock:
        return {
            "is_open": False,
            "timestamp": datetime.utcnow().isoformat(),
            "next_open": None,
            "next_close": None,
            "session_label": "UNKNOWN",
            "error": "Failed to fetch market clock - treating as closed for safety"
        }
    
    is_open = clock.get("is_open", False)
    next_open = clock.get("next_open")
    next_close = clock.get("next_close")
    timestamp = clock.get("timestamp", datetime.utcnow().isoformat())
    
    if is_open:
        session_label = "MARKET_OPEN"
    else:
        session_label = "MARKET_CLOSED"
    
    return {
        "is_open": is_open,
        "timestamp": timestamp,
        "next_open": next_open,
        "next_close": next_close,
        "session_label": session_label
    }


def get_smoke_test_mode() -> str:
    """
    Determine smoke test mode based on market session.
    
    Returns:
        "FILL" if market is open (can test real order fills)
        "NO_FILL" if market is closed (test order placement and cancellation only)
    """
    session = get_market_session_status()
    return "FILL" if session["is_open"] else "NO_FILL"
