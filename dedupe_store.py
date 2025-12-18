"""
Dedupe Store: Track executed signals to prevent duplicate executions.

Stores executed signal IDs in a JSONL file and provides lookup functions.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional

EXECUTED_SIGNALS_FILE = "data/executed_signals.jsonl"


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs(os.path.dirname(EXECUTED_SIGNALS_FILE), exist_ok=True)


def get_signal_key(post_id: Optional[str] = None, raw_text: Optional[str] = None) -> str:
    """
    Get a unique key for a signal.
    
    Uses post_id if available, otherwise generates a hash from raw text.
    
    Args:
        post_id: The post ID from the alert
        raw_text: Raw alert text (fallback for hashing)
        
    Returns:
        Unique string key for the signal
    """
    if post_id:
        return post_id
    
    if raw_text:
        return hashlib.sha256(raw_text.encode()).hexdigest()[:32]
    
    return ""


def is_executed(post_id: str) -> bool:
    """
    Check if a signal has already been executed.
    
    Args:
        post_id: The post ID or signal key to check
        
    Returns:
        True if already executed, False otherwise
    """
    if not post_id:
        return False
    
    if not os.path.exists(EXECUTED_SIGNALS_FILE):
        return False
    
    try:
        with open(EXECUTED_SIGNALS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("post_id") == post_id:
                        return True
                except json.JSONDecodeError:
                    continue
    except Exception:
        return False
    
    return False


def get_execution_info(post_id: str) -> Optional[dict]:
    """
    Get execution info for a signal if it was executed.
    
    Args:
        post_id: The post ID or signal key
        
    Returns:
        Execution info dict or None if not found
    """
    if not post_id:
        return None
    
    if not os.path.exists(EXECUTED_SIGNALS_FILE):
        return None
    
    try:
        with open(EXECUTED_SIGNALS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("post_id") == post_id:
                        return entry
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None
    
    return None


def mark_executed(
    post_id: str,
    execution_mode: str,
    trade_intent_id: str,
    result_status: str,
    underlying: Optional[str] = None,
    action: Optional[str] = None
) -> None:
    """
    Mark a signal as executed.
    
    Args:
        post_id: The post ID or signal key
        execution_mode: "paper" or "live"
        trade_intent_id: The trade intent ID
        result_status: Execution result status (e.g., "SIMULATED", "FILLED")
        underlying: Optional ticker/underlying
        action: Optional action type
    """
    if not post_id:
        return
    
    _ensure_data_dir()
    
    entry = {
        "post_id": post_id,
        "executed_at": datetime.utcnow().isoformat() + "Z",
        "execution_mode": execution_mode,
        "trade_intent_id": trade_intent_id,
        "result_status": result_status,
        "underlying": underlying,
        "action": action
    }
    
    with open(EXECUTED_SIGNALS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_all_executed() -> list:
    """
    Get all executed signals.
    
    Returns:
        List of execution records
    """
    if not os.path.exists(EXECUTED_SIGNALS_FILE):
        return []
    
    entries = []
    try:
        with open(EXECUTED_SIGNALS_FILE, "r") as f:
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
    
    return entries


def get_executed_count_today() -> int:
    """
    Get count of signals executed today.
    
    Returns:
        Number of signals executed today
    """
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    count = 0
    
    for entry in get_all_executed():
        executed_at = entry.get("executed_at", "")
        if executed_at.startswith(today_str):
            count += 1
    
    return count
