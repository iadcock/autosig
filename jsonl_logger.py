"""
JSONL logging module for trade alerts and execution plans.
Provides atomic append operations for structured logging.
"""

import json
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

LOGS_DIR = Path("logs")
RAW_ALERTS_FILE = LOGS_DIR / "alerts_raw.jsonl"
PARSED_ALERTS_FILE = LOGS_DIR / "alerts_parsed.jsonl"
EXECUTION_PLAN_FILE = LOGS_DIR / "execution_plan.jsonl"


def _ensure_logs_dir():
    """Ensure logs directory exists."""
    LOGS_DIR.mkdir(exist_ok=True)


def _generate_post_id(content: str) -> str:
    """Generate a stable hash ID from content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def _atomic_append(filepath: Path, data: Dict[str, Any]) -> bool:
    """
    Atomically append a JSON line to a file.
    Returns True on success, False on failure.
    """
    try:
        _ensure_logs_dir()
        line = json.dumps(data, default=str) + "\n"
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(line)
        return True
    except Exception as e:
        logger.error(f"Failed to append to {filepath}: {e}")
        return False


def log_raw_alert(
    body: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    source: str = "whop"
) -> str:
    """
    Log a raw alert fetched from source.
    Returns the generated post_id.
    """
    post_id = _generate_post_id(body)
    
    record = {
        "ts_iso": datetime.utcnow().isoformat() + "Z",
        "source": source,
        "post_id": post_id,
        "title": title,
        "body": body[:2000] if body else None,
        "url": url
    }
    
    _atomic_append(RAW_ALERTS_FILE, record)
    return post_id


def log_parsed_alert(
    post_id: str,
    classification: str,
    parsed_signal: Optional[Dict[str, Any]] = None,
    parse_error: Optional[str] = None,
    non_signal_reason: Optional[str] = None,
    raw_excerpt: Optional[str] = None
) -> bool:
    """
    Log the parsing result for an alert.
    classification should be "SIGNAL" or "NON_SIGNAL"
    """
    record = {
        "ts_iso": datetime.utcnow().isoformat() + "Z",
        "post_id": post_id,
        "classification": classification,
        "parsed_signal": parsed_signal,
        "parse_error": parse_error,
        "non_signal_reason": non_signal_reason,
        "raw_excerpt": raw_excerpt[:500] if raw_excerpt else None
    }
    
    return _atomic_append(PARSED_ALERTS_FILE, record)


def log_execution_plan(
    post_id: str,
    action: str,
    reason: str,
    order_preview: Optional[Dict[str, Any]] = None,
    dry_run: bool = True,
    live_trading: bool = False
) -> bool:
    """
    Log the execution plan for a parsed signal.
    action should be "PLACE_ORDER", "SKIP", or "CLOSE_ORDER"
    """
    record = {
        "ts_iso": datetime.utcnow().isoformat() + "Z",
        "post_id": post_id,
        "action": action,
        "reason": reason,
        "order_preview": order_preview,
        "DRY_RUN": dry_run,
        "LIVE_TRADING": live_trading
    }
    
    return _atomic_append(EXECUTION_PLAN_FILE, record)


def read_jsonl_file(filepath: Path, hours: int = 24) -> List[Dict[str, Any]]:
    """
    Read records from a JSONL file within the last N hours.
    """
    if not filepath.exists():
        return []
    
    cutoff = datetime.utcnow().timestamp() - (hours * 3600)
    records = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts_str = record.get("ts_iso", "")
                    if ts_str:
                        ts_str = ts_str.replace("Z", "+00:00")
                        try:
                            from datetime import timezone
                            ts = datetime.fromisoformat(ts_str.replace("+00:00", "")).timestamp()
                            if ts >= cutoff:
                                records.append(record)
                        except:
                            records.append(record)
                    else:
                        records.append(record)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
    
    return records


def get_raw_alerts(hours: int = 24) -> List[Dict[str, Any]]:
    """Get raw alerts from the last N hours."""
    return read_jsonl_file(RAW_ALERTS_FILE, hours)


def get_parsed_alerts(hours: int = 24) -> List[Dict[str, Any]]:
    """Get parsed alerts from the last N hours."""
    return read_jsonl_file(PARSED_ALERTS_FILE, hours)


def get_execution_plans(hours: int = 24) -> List[Dict[str, Any]]:
    """Get execution plans from the last N hours."""
    return read_jsonl_file(EXECUTION_PLAN_FILE, hours)
