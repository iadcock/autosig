"""
Preflight Gate: Safety checks before any trade execution.

Runs a series of validation checks before allowing a trade to execute.
All trades (paper or live) must pass preflight checks.
"""

import os
from datetime import date, datetime
from typing import Optional, Literal

MAX_RISK_PCT_PER_TRADE = float(os.getenv("MAX_RISK_PCT_PER_TRADE", "0.02"))
MAX_DAILY_RISK_PCT = float(os.getenv("MAX_DAILY_RISK_PCT", "0.05"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "10"))
ALLOW_0DTE_SPX = os.getenv("ALLOW_0DTE_SPX", "false").lower() == "true"
ALLOW_NEXT_DAY_SPX = os.getenv("ALLOW_NEXT_DAY_SPX", "true").lower() == "true"
LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"


def preflight_check(
    parsed_signal: dict,
    trade_intent: dict,
    execution_mode: str,
    post_id: Optional[str] = None
) -> dict:
    """
    Run preflight checks before any execution.
    
    Args:
        parsed_signal: The parsed signal dictionary
        trade_intent: The TradeIntent as a dictionary
        execution_mode: "paper" or "live"
        post_id: Optional post ID for dedupe checking
        
    Returns:
        {
            "ok": bool,
            "checks": [{"name": str, "ok": bool, "summary": str}],
            "blocked_reason": str | None,
            "warnings": [str]
        }
    """
    checks = []
    warnings = []
    blocked_reason = None
    
    check_completeness(trade_intent, parsed_signal, checks)
    check_supported_assets(trade_intent, checks)
    check_risk_controls(parsed_signal, trade_intent, checks, warnings)
    check_dte_guard(trade_intent, checks)
    check_mode_guard(execution_mode, checks)
    check_dedupe(post_id, checks)
    
    all_ok = all(c["ok"] for c in checks)
    
    if not all_ok:
        failed = [c for c in checks if not c["ok"]]
        if failed:
            blocked_reason = failed[0]["summary"]
    
    return {
        "ok": all_ok,
        "checks": checks,
        "blocked_reason": blocked_reason,
        "warnings": warnings
    }


def check_completeness(trade_intent: dict, parsed_signal: dict, checks: list) -> None:
    """Check if trade intent has complete required fields."""
    instrument_type = trade_intent.get("instrument_type", "").lower()
    
    if instrument_type in ("stock", "etf"):
        ticker = trade_intent.get("underlying", "")
        quantity = trade_intent.get("quantity", 0)
        
        if not ticker:
            checks.append({
                "name": "completeness",
                "ok": False,
                "summary": "Missing ticker for stock/ETF order"
            })
        elif quantity < 1:
            checks.append({
                "name": "completeness",
                "ok": False,
                "summary": f"Invalid quantity ({quantity}) for stock/ETF order"
            })
        else:
            checks.append({
                "name": "completeness",
                "ok": True,
                "summary": f"Stock order complete: {ticker} x{quantity}"
            })
            
    elif instrument_type in ("option", "index_option", "spread"):
        underlying = trade_intent.get("underlying", "")
        legs = trade_intent.get("legs", [])
        
        if not underlying:
            checks.append({
                "name": "completeness",
                "ok": False,
                "summary": "Missing underlying for option order"
            })
            return
            
        if not legs:
            action = trade_intent.get("action", "").upper()
            metadata = trade_intent.get("metadata", {})
            signal_type = metadata.get("signal_type", "")
            matched_position_id = metadata.get("matched_position_id")
            
            if signal_type == "EXIT" and not matched_position_id:
                checks.append({
                    "name": "completeness",
                    "ok": False,
                    "summary": "EXIT signal has no legs and no matched position"
                })
                return
        
        for i, leg in enumerate(legs):
            if not leg.get("expiration"):
                checks.append({
                    "name": "completeness",
                    "ok": False,
                    "summary": f"Leg {i+1} missing expiration"
                })
                return
            if leg.get("strike") is None:
                checks.append({
                    "name": "completeness",
                    "ok": False,
                    "summary": f"Leg {i+1} missing strike"
                })
                return
            if not leg.get("option_type"):
                checks.append({
                    "name": "completeness",
                    "ok": False,
                    "summary": f"Leg {i+1} missing option type (CALL/PUT)"
                })
                return
            if not leg.get("side"):
                checks.append({
                    "name": "completeness",
                    "ok": False,
                    "summary": f"Leg {i+1} missing side (BUY/SELL)"
                })
                return
        
        checks.append({
            "name": "completeness",
            "ok": True,
            "summary": f"Option order complete: {underlying} with {len(legs)} leg(s)"
        })
    else:
        checks.append({
            "name": "completeness",
            "ok": False,
            "summary": f"Unknown instrument type: {instrument_type}"
        })


def check_supported_assets(trade_intent: dict, checks: list) -> None:
    """Check if asset type is supported in v1."""
    instrument_type = trade_intent.get("instrument_type", "").lower()
    underlying = trade_intent.get("underlying", "").upper()
    
    supported_types = {"stock", "option", "index_option", "spread", "etf"}
    
    if instrument_type not in supported_types:
        checks.append({
            "name": "supported_asset",
            "ok": False,
            "summary": f"Unsupported instrument type: {instrument_type}"
        })
        return
    
    if instrument_type == "index_option":
        if underlying not in ("SPX", "SPXW"):
            checks.append({
                "name": "supported_asset",
                "ok": False,
                "summary": f"Only SPX index options supported, got: {underlying}"
            })
            return
    
    unsupported_assets = ["BTC", "ETH", "DOGE", "SOL", "/ES", "/NQ", "/CL", "/GC"]
    if underlying in unsupported_assets or underlying.startswith("/"):
        checks.append({
            "name": "supported_asset",
            "ok": False,
            "summary": f"Asset not supported: {underlying} (crypto/futures)"
        })
        return
    
    checks.append({
        "name": "supported_asset",
        "ok": True,
        "summary": f"Asset supported: {underlying} ({instrument_type})"
    })


def check_risk_controls(parsed_signal: dict, trade_intent: dict, checks: list, warnings: list) -> None:
    """Check risk controls and position limits."""
    size_pct = parsed_signal.get("size_pct")
    
    if size_pct is None:
        warnings.append(f"No size_pct in signal, will use max {MAX_RISK_PCT_PER_TRADE*100:.1f}%")
        size_pct = MAX_RISK_PCT_PER_TRADE
    else:
        size_pct = float(size_pct)
    
    if size_pct > MAX_RISK_PCT_PER_TRADE:
        checks.append({
            "name": "risk_per_trade",
            "ok": False,
            "summary": f"Trade risk {size_pct*100:.1f}% exceeds max {MAX_RISK_PCT_PER_TRADE*100:.1f}%"
        })
        return
    
    checks.append({
        "name": "risk_per_trade",
        "ok": True,
        "summary": f"Trade risk {size_pct*100:.1f}% within limit ({MAX_RISK_PCT_PER_TRADE*100:.1f}% max)"
    })


def check_dte_guard(trade_intent: dict, checks: list) -> None:
    """Check DTE restrictions for SPX options."""
    underlying = trade_intent.get("underlying", "").upper()
    legs = trade_intent.get("legs", [])
    
    if underlying not in ("SPX", "SPXW"):
        checks.append({
            "name": "dte_guard",
            "ok": True,
            "summary": "DTE guard not applicable (non-SPX)"
        })
        return
    
    if not legs:
        checks.append({
            "name": "dte_guard",
            "ok": True,
            "summary": "DTE guard: no legs to check"
        })
        return
    
    today = date.today()
    
    for i, leg in enumerate(legs):
        exp_str = leg.get("expiration", "")
        if not exp_str:
            continue
            
        try:
            if isinstance(exp_str, str):
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            else:
                exp_date = exp_str
        except ValueError:
            checks.append({
                "name": "dte_guard",
                "ok": False,
                "summary": f"Invalid expiration format: {exp_str}"
            })
            return
        
        if exp_date == today:
            if not ALLOW_0DTE_SPX:
                checks.append({
                    "name": "dte_guard",
                    "ok": False,
                    "summary": f"0DTE SPX not allowed (leg {i+1} expires today)"
                })
                return
    
    checks.append({
        "name": "dte_guard",
        "ok": True,
        "summary": "DTE guard passed"
    })


def check_mode_guard(execution_mode: str, checks: list) -> None:
    """Check if execution mode is allowed."""
    mode = execution_mode.lower()
    
    if mode == "live":
        if not LIVE_TRADING:
            checks.append({
                "name": "mode_guard",
                "ok": False,
                "summary": "LIVE_TRADING disabled - set LIVE_TRADING=true to enable"
            })
            return
        checks.append({
            "name": "mode_guard",
            "ok": True,
            "summary": "Live trading is enabled"
        })
    elif mode == "paper":
        checks.append({
            "name": "mode_guard",
            "ok": True,
            "summary": "Paper trading mode"
        })
    else:
        checks.append({
            "name": "mode_guard",
            "ok": True,
            "summary": f"Mode: {mode}"
        })


def check_dedupe(post_id: Optional[str], checks: list) -> None:
    """Check if signal has already been executed."""
    if not post_id:
        checks.append({
            "name": "dedupe",
            "ok": True,
            "summary": "No post_id to dedupe"
        })
        return
    
    from dedupe_store import is_executed
    
    if is_executed(post_id):
        checks.append({
            "name": "dedupe",
            "ok": False,
            "summary": f"Signal already executed (post_id: {post_id[:20]}...)"
        })
        return
    
    checks.append({
        "name": "dedupe",
        "ok": True,
        "summary": "Signal not previously executed"
    })
