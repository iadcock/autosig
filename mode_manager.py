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


def get_effective_behavior_summary() -> Dict[str, Any]:
    """
    Get a comprehensive summary of the effective trading behavior.
    
    Combines execution mode and risk mode to produce a single
    authoritative view of what the system will actually do.
    
    Returns:
        Dict with:
        - execution_mode: Effective execution mode (paper/live/dual)
        - risk_mode: Current risk mode (conservative/balanced/aggressive)
        - paper_mirror_enabled: Whether paper mirror is active
        - allow_0dte_spx: Whether 0DTE SPX is allowed (forced off if not aggressive)
        - auto_mode_behavior: What auto mode will do
        - live_trading_active: Whether live trades will execute
        - summary_text: Human-readable summary
        - warnings: List of warning messages
    """
    from settings_store import load_settings, VALID_RISK_MODES
    
    mode_info = get_effective_execution_mode()
    settings = load_settings()
    
    risk_mode = settings.get("RISK_MODE", "balanced")
    if risk_mode not in VALID_RISK_MODES:
        risk_mode = "balanced"
    
    effective_mode = mode_info["effective"]
    paper_mirror = settings.get("PAPER_MIRROR_ENABLED", False)
    allow_0dte_requested = settings.get("ALLOW_0DTE_SPX", False)
    
    allow_0dte_effective = allow_0dte_requested and risk_mode == "aggressive"
    
    live_trading_active = effective_mode in ("live", "dual")
    
    auto_mode_info = get_effective_execution_mode(for_auto=True)
    auto_live = auto_mode_info["effective"] in ("live", "dual")
    
    warnings = []
    summary_parts = []
    
    if effective_mode == "paper":
        summary_parts.append("Paper trading mode - no real money at risk.")
    elif effective_mode == "live":
        summary_parts.append(f"LIVE trading on {mode_info['primary_broker'].upper()} - real money at risk!")
    else:
        summary_parts.append(f"DUAL mode - live on {mode_info['primary_broker'].upper()} with paper mirror.")
    
    if risk_mode == "conservative":
        summary_parts.append("Conservative risk: spreads only, 1% max per trade.")
    elif risk_mode == "balanced":
        summary_parts.append("Balanced risk: stocks + options, 2% max per trade.")
    else:
        summary_parts.append("Aggressive risk: all trades allowed, 5% max per trade.")
    
    if allow_0dte_requested and not allow_0dte_effective:
        warnings.append("0DTE SPX is disabled because Risk Mode is not Aggressive.")
    
    if live_trading_active:
        warnings.append("LIVE TRADING IS ACTIVE - Real money trades will execute!")
    
    if auto_live:
        warnings.append("Auto mode will execute LIVE trades when running.")
    else:
        summary_parts.append("Auto mode is paper-only.")
    
    return {
        "execution_mode": effective_mode,
        "requested_mode": mode_info["requested"],
        "risk_mode": risk_mode,
        "paper_mirror_enabled": paper_mirror,
        "allow_0dte_spx": allow_0dte_effective,
        "allow_0dte_requested": allow_0dte_requested,
        "auto_mode_live": auto_live,
        "live_trading_active": live_trading_active,
        "primary_broker": mode_info["primary_broker"],
        "summary_text": " ".join(summary_parts),
        "warnings": warnings,
        "mode_message": mode_info["message"]
    }


def validate_settings_safety(proposed_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate proposed settings for safety invariants.
    
    Enforces:
    - 0DTE SPX can only be enabled in aggressive mode (forced off otherwise)
    - Execution mode is validated against environment flags
    - Returns warnings for potentially dangerous combinations
    
    Args:
        proposed_settings: Settings to validate
        
    Returns:
        Dict with:
        - validated_settings: Settings with invariants enforced
        - warnings: List of warning messages
        - forced_changes: Dict of settings that were force-changed
    """
    warnings = []
    forced_changes = {}
    validated = dict(proposed_settings)
    
    risk_mode = str(validated.get("RISK_MODE", "balanced")).lower()
    if risk_mode not in ("conservative", "balanced", "aggressive"):
        risk_mode = "balanced"
        validated["RISK_MODE"] = risk_mode
        forced_changes["RISK_MODE"] = risk_mode
    
    allow_0dte = validated.get("ALLOW_0DTE_SPX", False)
    if allow_0dte and risk_mode != "aggressive":
        validated["ALLOW_0DTE_SPX"] = False
        forced_changes["ALLOW_0DTE_SPX"] = False
        warnings.append(f"0DTE SPX disabled: only allowed in Aggressive risk mode (current: {risk_mode.title()}).")
    
    exec_mode = str(validated.get("REQUESTED_EXECUTION_MODE", "paper")).lower()
    live_allowed = is_live_allowed()
    dual_allowed = is_dual_allowed()
    
    if exec_mode == "dual":
        if not dual_allowed:
            if live_allowed:
                warnings.append("DUAL mode not available (ALLOW_DUAL_MODE not set). Request saved, but trades will execute as LIVE only.")
            else:
                warnings.append("DUAL mode not available (live trading not enabled). Request saved, but trades will execute as PAPER.")
        else:
            warnings.append("WARNING: DUAL mode selected - real money trades will execute with paper mirror!")
    elif exec_mode == "live":
        if not live_allowed:
            warnings.append("LIVE mode not available (LIVE_TRADING=false or DRY_RUN=true). Request saved, but trades will execute as PAPER.")
        else:
            warnings.append("WARNING: LIVE mode selected - real money trades will execute!")
    
    return {
        "validated_settings": validated,
        "warnings": warnings,
        "forced_changes": forced_changes
    }
