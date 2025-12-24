"""
Strategy rules for trade classification and risk mode enforcement.

Classifies trades into categories and applies risk mode rules.
"""

from datetime import date, datetime
from typing import Literal, Optional, Tuple


RiskBucket = Literal["defined_risk", "undefined_risk"]
RiskMode = Literal["conservative", "balanced", "aggressive"]

RISK_MODE_CAPS = {
    "conservative": {
        "MAX_RISK_PCT_PER_TRADE": 1,
        "AUTO_MAX_TRADES_PER_HOUR": 1,
    },
    "balanced": {
        "MAX_RISK_PCT_PER_TRADE": 2,
        "AUTO_MAX_TRADES_PER_HOUR": 3,
    },
    "aggressive": {
        "MAX_RISK_PCT_PER_TRADE": 5,
        "AUTO_MAX_TRADES_PER_HOUR": 5,
    },
}


def is_exit_signal(parsed_signal: dict, trade_intent: dict) -> bool:
    """Check if this is an exit/close signal."""
    signal_type = parsed_signal.get("signal_type", "").upper()
    if signal_type in ("EXIT", "CLOSE", "STC", "BTC"):
        return True
    
    action = trade_intent.get("action", "").upper()
    if action in ("CLOSE", "STC", "BTC"):
        return True
    
    metadata = trade_intent.get("metadata", {})
    if metadata.get("signal_type", "").upper() in ("EXIT", "CLOSE"):
        return True
    
    return False


def is_long_stock_entry(parsed_signal: dict, trade_intent: dict) -> bool:
    """Check if this is a long stock entry (BTO stock/ETF)."""
    if is_exit_signal(parsed_signal, trade_intent):
        return False
    
    instrument_type = trade_intent.get("instrument_type", "").lower()
    if instrument_type not in ("stock", "etf"):
        return False
    
    action = trade_intent.get("action", "").upper()
    return action in ("BUY", "BTO", "OPEN", "ENTRY")


def is_single_leg_option_entry(parsed_signal: dict, trade_intent: dict) -> bool:
    """Check if this is a single-leg option entry (undefined risk)."""
    if is_exit_signal(parsed_signal, trade_intent):
        return False
    
    instrument_type = trade_intent.get("instrument_type", "").lower()
    if instrument_type not in ("option", "index_option"):
        return False
    
    legs = trade_intent.get("legs", [])
    return len(legs) == 1


def is_spread_entry(parsed_signal: dict, trade_intent: dict) -> bool:
    """Check if this is a spread entry (defined risk)."""
    if is_exit_signal(parsed_signal, trade_intent):
        return False
    
    instrument_type = trade_intent.get("instrument_type", "").lower()
    if instrument_type == "spread":
        return True
    
    if instrument_type in ("option", "index_option"):
        legs = trade_intent.get("legs", [])
        if len(legs) >= 2:
            return True
    
    return False


def is_spx_0dte(trade_intent: dict) -> bool:
    """Check if this is a 0DTE SPX trade."""
    underlying = trade_intent.get("underlying", "").upper()
    if underlying not in ("SPX", "$SPX", "SPXW"):
        return False
    
    legs = trade_intent.get("legs", [])
    if not legs:
        return False
    
    today = date.today()
    
    for leg in legs:
        exp_str = leg.get("expiration", "")
        if not exp_str:
            continue
        
        try:
            if isinstance(exp_str, str):
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            else:
                exp_date = exp_str
            
            if exp_date == today:
                return True
        except (ValueError, TypeError):
            continue
    
    return False


def get_trade_risk_bucket(parsed_signal: dict, trade_intent: dict) -> RiskBucket:
    """
    Classify trade into risk bucket.
    
    - defined_risk: spreads, exits
    - undefined_risk: single-leg options, long stock
    """
    if is_exit_signal(parsed_signal, trade_intent):
        return "defined_risk"
    
    if is_spread_entry(parsed_signal, trade_intent):
        return "defined_risk"
    
    return "undefined_risk"


def check_risk_mode_allows(
    parsed_signal: dict,
    trade_intent: dict,
    risk_mode: RiskMode,
    allow_0dte_spx: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Check if the current risk mode allows this trade.
    
    NOTE: TEMPORARILY LOCKED TO AGGRESSIVE - all trades allowed.
    Conservative/Balanced restrictions are bypassed.
    
    Returns:
        (allowed, block_reason)
        - allowed: True if trade is allowed
        - block_reason: Reason for blocking, or None if allowed
    """
    if is_spx_0dte(trade_intent) and not allow_0dte_spx:
        return (False, "0DTE SPX requires ALLOW_0DTE_SPX=true")
    
    return (True, None)


def get_effective_caps(risk_mode: RiskMode, current_settings: dict) -> dict:
    """
    Get effective risk caps based on risk mode.
    
    NOTE: TEMPORARILY LOCKED TO AGGRESSIVE for testing.
    """
    return {
        "MAX_RISK_PCT_PER_TRADE": 5,
        "AUTO_MAX_TRADES_PER_HOUR": 5,
    }


def get_risk_mode_description(mode: RiskMode) -> str:
    """Get human-readable description of risk mode."""
    return "AGGRESSIVE (locked for testing) - All trades allowed, 5% max risk, 5 trades/hour"
