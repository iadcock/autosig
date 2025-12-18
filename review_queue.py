"""
Review Queue: List and manage parsed signals for approval/rejection.

Provides functions to list recent signals, build trade intents with preflight checks,
and record review actions (approve/reject).
"""

import os
import json
from datetime import datetime
from typing import Optional, Tuple, Literal

from signal_to_intent import (
    build_trade_intent,
    classify_signal_type,
    has_complete_leg_details,
    resolve_exit_to_trade_intent
)
from preflight import preflight_check
from dedupe_store import is_executed, get_execution_info

ALERTS_PARSED_FILE = "logs/alerts_parsed.jsonl"
REVIEW_ACTIONS_FILE = "data/review_actions.jsonl"


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs("data", exist_ok=True)


def list_recent_signals(limit: int = 25) -> list:
    """
    List recent parsed signals from alerts_parsed.jsonl.
    
    Returns newest signals first.
    
    Args:
        limit: Maximum number of signals to return
        
    Returns:
        List of signal entries with metadata
    """
    if not os.path.exists(ALERTS_PARSED_FILE):
        return []
    
    entries = []
    
    try:
        with open(ALERTS_PARSED_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    post_id = entry.get("post_id", "")
                    parsed_signal = entry.get("parsed_signal", {})
                    
                    signal_type = "UNKNOWN"
                    if entry.get("classification") == "SIGNAL" and parsed_signal:
                        signal_type = classify_signal_type(parsed_signal)
                    
                    already_executed = is_executed(post_id) if post_id else False
                    execution_info = get_execution_info(post_id) if already_executed else None
                    
                    entries.append({
                        "post_id": post_id,
                        "ts_iso": entry.get("ts_iso", ""),
                        "raw_excerpt": entry.get("raw_excerpt", "")[:200],
                        "parsed_signal": parsed_signal,
                        "classification": entry.get("classification", ""),
                        "signal_type": signal_type,
                        "ticker": parsed_signal.get("ticker", ""),
                        "strategy": parsed_signal.get("strategy", ""),
                        "already_executed": already_executed,
                        "execution_info": execution_info
                    })
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    
    entries.reverse()
    return entries[:limit]


def build_intent_and_preflight(
    entry: dict,
    execution_mode: Literal["paper", "live"]
) -> dict:
    """
    Build a TradeIntent and run preflight checks for a signal entry.
    
    Args:
        entry: Signal entry from list_recent_signals()
        execution_mode: "paper" or "live"
        
    Returns:
        {
            "trade_intent": dict | None,
            "trade_intent_error": str | None,
            "preflight_result": dict | None,
            "matched_position_id": str | None
        }
    """
    parsed_signal = entry.get("parsed_signal", {})
    post_id = entry.get("post_id", "")
    classification = entry.get("classification", "")
    
    if classification != "SIGNAL" or not parsed_signal:
        return {
            "trade_intent": None,
            "trade_intent_error": "Not a valid SIGNAL classification",
            "preflight_result": None,
            "matched_position_id": None
        }
    
    signal_type = classify_signal_type(parsed_signal)
    mode_literal: Literal["PAPER", "LIVE", "HISTORICAL"] = "PAPER" if execution_mode.lower() == "paper" else "LIVE"
    
    trade_intent = None
    matched_position_id = None
    intent_error = None
    
    try:
        if signal_type == "EXIT":
            if has_complete_leg_details(parsed_signal):
                intent_obj = build_trade_intent(parsed_signal, execution_mode=mode_literal)
                trade_intent = _intent_to_dict(intent_obj)
            else:
                intent_obj, matched_position_id, error = resolve_exit_to_trade_intent(
                    parsed_signal, execution_mode=mode_literal
                )
                if intent_obj:
                    trade_intent = _intent_to_dict(intent_obj)
                else:
                    intent_error = error or "Could not resolve EXIT to open position"
        else:
            intent_obj = build_trade_intent(parsed_signal, execution_mode=mode_literal)
            trade_intent = _intent_to_dict(intent_obj)
            
    except Exception as e:
        intent_error = str(e)
    
    preflight_result = None
    if trade_intent:
        preflight_result = preflight_check(
            parsed_signal=parsed_signal,
            trade_intent=trade_intent,
            execution_mode=execution_mode,
            post_id=post_id
        )
    
    return {
        "trade_intent": trade_intent,
        "trade_intent_error": intent_error,
        "preflight_result": preflight_result,
        "matched_position_id": matched_position_id
    }


def _intent_to_dict(intent_obj) -> dict:
    """Convert TradeIntent object to dictionary."""
    return {
        "id": intent_obj.id,
        "execution_mode": intent_obj.execution_mode,
        "instrument_type": intent_obj.instrument_type,
        "underlying": intent_obj.underlying,
        "action": intent_obj.action,
        "order_type": intent_obj.order_type,
        "limit_price": intent_obj.limit_price,
        "quantity": intent_obj.quantity,
        "legs": [
            {
                "side": leg.side,
                "quantity": leg.quantity,
                "strike": leg.strike,
                "option_type": leg.option_type,
                "expiration": leg.expiration
            }
            for leg in intent_obj.legs
        ],
        "metadata": intent_obj.metadata
    }


def record_review_action(
    post_id: str,
    action: Literal["APPROVE_PAPER", "APPROVE_LIVE", "REJECT", "AUTO_PAPER"],
    mode: Optional[str] = None,
    notes: Optional[str] = None,
    trade_intent_id: Optional[str] = None,
    preflight: Optional[dict] = None,
    result: Optional[dict] = None,
    ticker: Optional[str] = None
) -> None:
    """
    Record a review action (approve/reject/auto) to the review actions log.
    
    Args:
        post_id: The signal post ID
        action: APPROVE_PAPER, APPROVE_LIVE, REJECT, or AUTO_PAPER
        mode: Execution mode (paper/live)
        notes: Optional notes (required for REJECT)
        trade_intent_id: Trade intent ID if executed
        preflight: Preflight check results
        result: Execution result if executed
        ticker: Ticker symbol
    """
    _ensure_data_dir()
    
    entry = {
        "ts_iso": datetime.utcnow().isoformat() + "Z",
        "post_id": post_id,
        "action": action,
        "mode": mode,
        "notes": notes,
        "trade_intent_id": trade_intent_id,
        "ticker": ticker,
        "preflight_ok": preflight.get("ok") if preflight else None,
        "preflight_blocked_reason": preflight.get("blocked_reason") if preflight else None,
        "result_status": result.get("status") if result else None,
        "result_message": result.get("message") if result else None
    }
    
    with open(REVIEW_ACTIONS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_review_actions(limit: int = 50) -> list:
    """
    Get recent review actions.
    
    Args:
        limit: Maximum number of actions to return
        
    Returns:
        List of review action entries (newest first)
    """
    if not os.path.exists(REVIEW_ACTIONS_FILE):
        return []
    
    entries = []
    try:
        with open(REVIEW_ACTIONS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    
    entries.reverse()
    return entries[:limit]
