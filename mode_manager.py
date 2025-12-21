"""
Execution Mode Manager.
Centralizes 3-state execution mode computation with safety gates.

Modes:
- paper: Paper trading only (default, always allowed)
- live: Live trading only (requires LIVE_TRADING=true, DRY_RUN!=true)
- dual: Live trading + paper mirror (requires ALLOW_DUAL_MODE=true)
"""

import os
from typing import Dict, Any, Literal
from settings_store import get_setting
from env_loader import load_env

ExecutionMode = Literal["paper", "live", "dual"]
VALID_MODES = ("paper", "live", "dual")


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean value from environment variable."""
    val = load_env(key) or os.getenv(key, "")
    if not val:
        return default
    return val.lower() in ("true", "1", "yes", "on")


def is_live_allowed() -> bool:
    """
    Check if live trading is allowed.
    
    Returns True if:
    - LIVE_TRADING=true AND
    - DRY_RUN is not true
    """
    live_trading = _get_env_bool("LIVE_TRADING", False)
    dry_run = _get_env_bool("DRY_RUN", True)
    return live_trading and not dry_run


def is_dual_allowed() -> bool:
    """
    Check if dual mode (live + paper mirror) is allowed.
    
    Returns True if:
    - Live trading is allowed AND
    - ALLOW_DUAL_MODE=true
    """
    if not is_live_allowed():
        return False
    return _get_env_bool("ALLOW_DUAL_MODE", False)


def is_auto_live_enabled() -> bool:
    """
    Check if auto mode can execute live trades.
    By default, auto mode is paper-only for safety.
    
    Returns True if AUTO_LIVE_ENABLED=true
    """
    return _get_env_bool("AUTO_LIVE_ENABLED", False)


def get_primary_live_broker() -> str:
    """
    Get the primary broker for live trading.
    Default is 'tradier'.
    """
    return os.getenv("PRIMARY_LIVE_BROKER", "tradier").lower()


def get_requested_mode() -> ExecutionMode:
    """Get the user-requested execution mode from settings."""
    mode = get_setting("REQUESTED_EXECUTION_MODE", "paper")
    if mode not in VALID_MODES:
        return "paper"
    return mode


def get_effective_execution_mode(for_auto: bool = False) -> Dict[str, Any]:
    """
    Compute the effective execution mode with safety gates.
    
    Args:
        for_auto: If True, apply auto-mode safety restrictions
        
    Returns:
        Dict with:
        - requested: User-requested mode
        - effective: Actual mode after safety gates
        - live_allowed: Whether live trading is allowed
        - dual_allowed: Whether dual mode is allowed
        - auto_live_enabled: Whether auto mode can trade live
        - primary_broker: Primary broker for live trades
        - message: Explanation of mode resolution
    """
    requested = get_requested_mode()
    live_allowed = is_live_allowed()
    dual_allowed = is_dual_allowed()
    auto_live_enabled = is_auto_live_enabled()
    primary_broker = get_primary_live_broker()
    
    if for_auto and not auto_live_enabled:
        effective = "paper"
        if requested in ("live", "dual"):
            message = "Auto mode restricted to paper trading. Set AUTO_LIVE_ENABLED=true for live auto trading."
        else:
            message = "Auto mode using paper trading."
    elif requested == "dual":
        if dual_allowed:
            effective = "dual"
            message = f"Dual mode active: Live trades on {primary_broker}, paper mirror for verification."
        elif live_allowed:
            effective = "live"
            message = "Dual mode not allowed. Set ALLOW_DUAL_MODE=true. Falling back to live only."
        else:
            effective = "paper"
            message = "Live trading not enabled. Set LIVE_TRADING=true and DRY_RUN=false."
    elif requested == "live":
        if live_allowed:
            effective = "live"
            message = f"Live trading active on {primary_broker}."
        else:
            effective = "paper"
            message = "Live trading not enabled. Set LIVE_TRADING=true and DRY_RUN=false."
    else:
        effective = "paper"
        message = "Paper trading mode active."
    
    return {
        "requested": requested,
        "effective": effective,
        "live_allowed": live_allowed,
        "dual_allowed": dual_allowed,
        "auto_live_enabled": auto_live_enabled,
        "primary_broker": primary_broker,
        "message": message
    }


def set_requested_mode(mode: str) -> Dict[str, Any]:
    """
    Set the requested execution mode and return effective mode info.
    
    Args:
        mode: Requested mode (paper, live, or dual)
        
    Returns:
        Dict with mode info including effective mode
    """
    from settings_store import save_settings, load_settings
    
    if mode not in VALID_MODES:
        mode = "paper"
    
    current = load_settings()
    current["REQUESTED_EXECUTION_MODE"] = mode
    save_settings(current)
    
    return get_effective_execution_mode()


def should_execute_live() -> bool:
    """Check if current mode should execute live trades."""
    mode_info = get_effective_execution_mode()
    return mode_info["effective"] in ("live", "dual")


def should_execute_paper() -> bool:
    """Check if current mode should execute paper trades."""
    mode_info = get_effective_execution_mode()
    return mode_info["effective"] in ("paper", "dual")


def get_mode_display_info() -> Dict[str, Any]:
    """
    Get display information for the mode badge in the UI.
    
    Returns:
        Dict with:
        - text: Badge text
        - css_class: CSS class for styling
        - tooltip: Tooltip description
        - is_dangerous: Whether mode involves real money
    """
    mode_info = get_effective_execution_mode()
    effective = mode_info["effective"]
    
    if effective == "paper":
        return {
            "text": "PAPER",
            "css_class": "mode-paper",
            "tooltip": "Paper trading only - no real money at risk",
            "is_dangerous": False
        }
    elif effective == "live":
        return {
            "text": "LIVE",
            "css_class": "mode-live",
            "tooltip": f"LIVE TRADING - Real money on {mode_info['primary_broker'].upper()}",
            "is_dangerous": True
        }
    else:
        return {
            "text": "DUAL",
            "css_class": "mode-dual",
            "tooltip": f"DUAL MODE - Live on {mode_info['primary_broker'].upper()} + paper mirror",
            "is_dangerous": True
        }
