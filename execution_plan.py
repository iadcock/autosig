"""
Execution plan builder and logger for trade execution tracking.

Logs execution plans to logs/execution_plan.jsonl for audit and analysis.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any, List, Tuple

from trade_intent import TradeIntent, ExecutionResult


EXECUTION_PLAN_LOG = "logs/execution_plan.jsonl"


def _get_settings_snapshot() -> Dict[str, Any]:
    """Get a snapshot of current settings at time of decision."""
    from settings_store import load_settings, FORCED_RISK_MODE, EXECUTION_BROKER_MODE
    from mode_manager import get_effective_execution_mode, is_live_allowed
    from auto_mode import get_auto_status
    
    settings = load_settings()
    mode_info = get_effective_execution_mode()
    auto_status = get_auto_status()
    
    live_armed = is_live_allowed()
    
    return {
        "risk_mode_requested": settings.get("RISK_MODE", "aggressive"),
        "risk_mode_effective": "aggressive",
        "execution_mode_requested": mode_info["requested"],
        "execution_mode_effective": mode_info["effective"],
        "live_armed": live_armed,
        "auto_mode_enabled": auto_status.get("enabled", False),
        "broker_mode": EXECUTION_BROKER_MODE,
    }


def _build_parsed_summary(parsed_signal: Optional[dict]) -> Optional[Dict[str, Any]]:
    """Build a minimal parsed signal summary for hover popup."""
    if not parsed_signal:
        return None
    
    legs = parsed_signal.get("legs", [])
    leg_strs = []
    for leg in legs:
        side = leg.get("side", "")
        strike = leg.get("strike", "")
        option_type = leg.get("option_type", "")
        qty = leg.get("quantity", 1)
        sign = "+" if side == "BUY" else "-"
        leg_strs.append(f"{sign}{qty} {strike}{option_type[0] if option_type else ''}")
    
    limit_str = None
    if parsed_signal.get("limit_price"):
        limit_str = f"${parsed_signal['limit_price']}"
    elif parsed_signal.get("limit_min") and parsed_signal.get("limit_max"):
        limit_str = f"${parsed_signal['limit_min']}-${parsed_signal['limit_max']}"
    
    return {
        "ticker": parsed_signal.get("ticker", ""),
        "strategy": parsed_signal.get("strategy", ""),
        "expiration": parsed_signal.get("expiration", ""),
        "legs": leg_strs if leg_strs else None,
        "limit": limit_str,
        "size_pct": parsed_signal.get("size_pct"),
    }


def build_execution_plan(
    trade_intent: Optional[TradeIntent],
    execution_result: Optional[ExecutionResult],
    source_post_id: str,
    action: Literal["PLACE_ORDER", "SKIP"] = "PLACE_ORDER",
    reason: Optional[str] = None,
    signal_type: Optional[str] = None,
    matched_position_id: Optional[str] = None,
    parsed_signal: Optional[dict] = None
) -> dict:
    """
    Build a loggable execution plan dictionary.
    
    Args:
        trade_intent: The TradeIntent that was executed (or None if skipped)
        execution_result: The ExecutionResult from execution (or None if skipped)
        source_post_id: The post ID from the parsed signal
        action: "PLACE_ORDER" or "SKIP"
        reason: Reason for skipping (if action is SKIP)
        signal_type: ENTRY, EXIT, or UNKNOWN
        matched_position_id: Position ID if EXIT resolved from open position
        parsed_signal: The original parsed signal dict (for summary)
        
    Returns:
        Dictionary ready for JSONL logging
    """
    now_utc = datetime.now(timezone.utc)
    
    intent_dict = None
    result_dict = None
    execution_mode = None
    
    if trade_intent:
        execution_mode = trade_intent.execution_mode
        intent_dict = {
            "id": trade_intent.id,
            "created_at": trade_intent.created_at.isoformat(),
            "execution_mode": trade_intent.execution_mode,
            "instrument_type": trade_intent.instrument_type,
            "underlying": trade_intent.underlying,
            "action": trade_intent.action,
            "order_type": trade_intent.order_type,
            "limit_price": trade_intent.limit_price,
            "limit_min": trade_intent.limit_min,
            "limit_max": trade_intent.limit_max,
            "quantity": trade_intent.quantity,
            "legs": [
                {
                    "side": leg.side,
                    "quantity": leg.quantity,
                    "strike": leg.strike,
                    "option_type": leg.option_type,
                    "expiration": leg.expiration
                }
                for leg in trade_intent.legs
            ],
            "raw_signal": trade_intent.raw_signal,
            "metadata": trade_intent.metadata
        }
    
    if execution_result:
        result_dict = {
            "intent_id": execution_result.intent_id,
            "status": execution_result.status,
            "broker": execution_result.broker,
            "order_id": execution_result.order_id,
            "message": execution_result.message,
            "fill_price": execution_result.fill_price,
            "filled_quantity": execution_result.filled_quantity,
            "submitted_at": execution_result.submitted_at.isoformat(),
            "filled_at": execution_result.filled_at.isoformat() if execution_result.filled_at else None,
            "submitted_payload": execution_result.submitted_payload
        }
    
    return {
        "ts_utc": now_utc.isoformat(),
        "tz": "America/Los_Angeles",
        "ts_iso": now_utc.isoformat(),
        "post_id": source_post_id,
        "signal_type": signal_type,
        "action": action,
        "reason": reason,
        "matched_position_id": matched_position_id,
        "execution_mode": execution_mode,
        "settings_snapshot": _get_settings_snapshot(),
        "parsed_summary": _build_parsed_summary(parsed_signal),
        "order_preview": intent_dict,
        "result": result_dict
    }


def log_execution_plan(execution_plan: dict) -> None:
    """
    Append execution plan to the JSONL log file.
    
    Args:
        execution_plan: Dictionary from build_execution_plan()
    """
    os.makedirs(os.path.dirname(EXECUTION_PLAN_LOG), exist_ok=True)
    
    with open(EXECUTION_PLAN_LOG, "a") as f:
        f.write(json.dumps(execution_plan) + "\n")


def get_latest_signal_entry() -> Optional[dict]:
    """
    Read the most recent SIGNAL entry from alerts_parsed.jsonl.
    
    Returns:
        Dictionary with the parsed alert, or None if no signals found.
    """
    alerts_file = "logs/alerts_parsed.jsonl"
    
    if not os.path.exists(alerts_file):
        return None
    
    entries = []
    with open(alerts_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if entry.get("classification") == "SIGNAL" and entry.get("parsed_signal"):
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    
    if entries:
        return entries[-1]
    
    return None


def get_executable_signal() -> Tuple[Optional[dict], str, Optional[str]]:
    """
    Find the best executable signal from alerts_parsed.jsonl.
    
    Priority:
    1. ENTRY signals (most recent first)
    2. EXIT signals with complete leg details
    3. EXIT signals that can be resolved via open positions
    
    Returns:
        Tuple of (signal_entry or None, signal_type, skip_reason or None)
    """
    from signal_to_intent import classify_signal_type, has_complete_leg_details
    from paper_positions import find_open_position_for_exit
    
    alerts_file = "logs/alerts_parsed.jsonl"
    
    if not os.path.exists(alerts_file):
        return None, "UNKNOWN", "No alerts_parsed.jsonl file found"
    
    entries = []
    with open(alerts_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if entry.get("classification") == "SIGNAL" and entry.get("parsed_signal"):
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    
    if not entries:
        return None, "UNKNOWN", "No parsed signals found in logs/alerts_parsed.jsonl"
    
    # Process from newest to oldest
    entries.reverse()
    
    # First pass: look for ENTRY signals
    for entry in entries:
        parsed_signal = entry.get("parsed_signal", {})
        signal_type = classify_signal_type(parsed_signal)
        
        if signal_type == "ENTRY":
            # Check if it has enough data to execute
            ticker = parsed_signal.get("ticker", "")
            if ticker:
                return entry, "ENTRY", None
    
    # Second pass: look for executable EXIT signals
    for entry in entries:
        parsed_signal = entry.get("parsed_signal", {})
        signal_type = classify_signal_type(parsed_signal)
        
        if signal_type == "EXIT":
            # Check if EXIT has complete leg details
            if has_complete_leg_details(parsed_signal):
                return entry, "EXIT", None
            
            # Check if EXIT can be resolved via open position
            position = find_open_position_for_exit(parsed_signal)
            if position is not None:
                return entry, "EXIT", None
    
    # No executable signal found - return the most recent with reason
    if entries:
        latest = entries[0]
        parsed_signal = latest.get("parsed_signal", {})
        signal_type = classify_signal_type(parsed_signal)
        
        if signal_type == "EXIT":
            ticker = parsed_signal.get("ticker", "UNKNOWN")
            return None, "EXIT", f"EXIT signal for {ticker} has no matching open PAPER position"
        else:
            return None, signal_type, f"Signal type {signal_type} is not executable"
    
    return None, "UNKNOWN", "No executable signals found"
