"""
Execution plan builder and logger for trade execution tracking.

Logs execution plans to logs/execution_plan.jsonl for audit and analysis.
"""

import json
import os
from datetime import datetime
from typing import Optional, Literal

from trade_intent import TradeIntent, ExecutionResult


EXECUTION_PLAN_LOG = "logs/execution_plan.jsonl"


def build_execution_plan(
    trade_intent: TradeIntent,
    execution_result: ExecutionResult,
    source_post_id: str,
    action: Literal["PLACE_ORDER", "SKIP"] = "PLACE_ORDER",
    reason: Optional[str] = None
) -> dict:
    """
    Build a loggable execution plan dictionary.
    
    Args:
        trade_intent: The TradeIntent that was executed
        execution_result: The ExecutionResult from execution
        source_post_id: The post ID from the parsed signal
        action: "PLACE_ORDER" or "SKIP"
        reason: Reason for skipping (if action is SKIP)
        
    Returns:
        Dictionary ready for JSONL logging
    """
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
        "ts_iso": datetime.utcnow().isoformat() + "Z",
        "post_id": source_post_id,
        "action": action,
        "reason": reason,
        "execution_mode": trade_intent.execution_mode,
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
