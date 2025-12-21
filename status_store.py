"""
Status store for tracking service health and execution mode.
Persists to data/status.json for display in global status row.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Literal

STATUS_FILE = "data/status.json"

ServiceStatus = Literal["ok", "fail", "warn", "unknown"]
ModeType = Literal["paper", "live"]

DEFAULT_STATUS: Dict[str, Any] = {
    "whop": {
        "status": "unknown",
        "last_checked": None,
        "summary": "Never checked"
    },
    "alpaca": {
        "status": "unknown",
        "last_checked": None,
        "summary": "Never checked"
    },
    "tradier": {
        "status": "unknown",
        "last_checked": None,
        "summary": "Never checked"
    },
    "mode": {
        "requested": "paper",
        "effective": "paper"
    }
}


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs("data", exist_ok=True)


def _load_status_file() -> Dict[str, Any]:
    """Load status from JSON file."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                data = json.load(f)
                merged = {**DEFAULT_STATUS}
                for key in DEFAULT_STATUS:
                    if key in data:
                        if isinstance(DEFAULT_STATUS[key], dict):
                            merged[key] = {**DEFAULT_STATUS[key], **data[key]}
                        else:
                            merged[key] = data[key]
                return merged
        except (json.JSONDecodeError, IOError):
            return DEFAULT_STATUS.copy()
    return DEFAULT_STATUS.copy()


def _save_status_file(data: Dict[str, Any]) -> bool:
    """Save status to JSON file."""
    _ensure_data_dir()
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except IOError:
        return False


def update_service_status(service: str, status: ServiceStatus, summary: str) -> bool:
    """
    Update status for a service (whop, alpaca, tradier).
    
    Args:
        service: Service name (whop, alpaca, tradier)
        status: Status value (ok, fail, warn, unknown)
        summary: Short description of status
    
    Returns:
        True on success
    """
    if service not in ("whop", "alpaca", "tradier"):
        return False
    
    data = _load_status_file()
    data[service] = {
        "status": status,
        "last_checked": datetime.utcnow().isoformat() + "Z",
        "summary": summary
    }
    return _save_status_file(data)


def update_mode(requested: ModeType, effective: ModeType) -> bool:
    """
    Update execution mode status.
    
    Args:
        requested: User-requested mode (paper or live)
        effective: Actual mode after safety gates (paper or live)
    
    Returns:
        True on success
    """
    data = _load_status_file()
    data["mode"] = {
        "requested": requested,
        "effective": effective
    }
    return _save_status_file(data)


def get_all_statuses() -> Dict[str, Any]:
    """
    Get all service statuses, mode, and risk mode.
    
    Returns:
        Dict with whop, alpaca, tradier, mode, risk_mode status objects
    """
    from settings_store import get_setting
    
    data = _load_status_file()
    data["risk_mode"] = get_setting("RISK_MODE", "balanced")
    return data


def get_service_status(service: str) -> Dict[str, Any]:
    """Get status for a single service."""
    data = _load_status_file()
    return data.get(service, {"status": "unknown", "summary": "Unknown service"})


def get_mode() -> Dict[str, str]:
    """Get current mode settings."""
    data = _load_status_file()
    return data.get("mode", {"requested": "paper", "effective": "paper"})
