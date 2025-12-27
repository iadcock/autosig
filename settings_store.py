"""
Settings persistence layer.
Loads/saves settings to data/settings.json.
Falls back to environment variables if file is missing.
"""

import os
import json
from typing import Any, Dict
from env_loader import load_env

SETTINGS_FILE = "data/settings.json"

DEFAULT_SETTINGS = {
    "PAPER_MIRROR_ENABLED": False,
    "AUTO_POLL_SECONDS": 30,
    "AUTO_WINDOW_BUFFER_MINUTES": 60,
    "MAX_RISK_PCT_PER_TRADE": 5,
    "MAX_DAILY_RISK_PCT": 10,
    "MAX_OPEN_POSITIONS": 20,
    "ALLOW_0DTE_SPX": False,
    "AUTO_MAX_TRADES_PER_DAY": 10,
    "AUTO_MAX_TRADES_PER_HOUR": 5,
    "RISK_MODE": "aggressive",
    "REQUESTED_EXECUTION_MODE": "paper",
}

FORCED_RISK_MODE = "aggressive"

# Explicit allowlist: Only TRADIER_ONLY is supported in production
VALID_BROKER_MODES = ("TRADIER_ONLY",)
VALID_RISK_MODES = ("conservative", "balanced", "aggressive")
VALID_EXECUTION_MODES = ("paper", "live", "dual")

# Read BROKER_MODE from environment
# If missing: default to TRADIER_ONLY (safe default)
# If set to invalid value: will be caught by startup validation and exit
_broker_mode_env = load_env("BROKER_MODE") or os.getenv("BROKER_MODE", "").strip().upper()
if _broker_mode_env and _broker_mode_env in VALID_BROKER_MODES:
    EXECUTION_BROKER_MODE = _broker_mode_env
else:
    # Default to TRADIER_ONLY if not set (preserves current behavior)
    # Invalid values will be caught by startup validation
    EXECUTION_BROKER_MODE = "TRADIER_ONLY"

_settings_cache: Dict[str, Any] = {}


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs("data", exist_ok=True)


def _load_from_file() -> Dict[str, Any]:
    """Load settings from JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _get_env_value(key: str, default: Any) -> Any:
    """Get value from environment with type conversion."""
    val = load_env(key) or os.getenv(key, "")
    if not val:
        return default
    
    if isinstance(default, bool):
        return val.lower() in ("true", "1", "yes", "on")
    elif isinstance(default, int):
        try:
            return int(val)
        except ValueError:
            return default
    elif isinstance(default, float):
        try:
            return float(val)
        except ValueError:
            return default
    return val


def load_settings() -> Dict[str, Any]:
    """
    Load settings with priority:
    1. Persisted file (data/settings.json)
    2. Environment variables
    3. Default values
    
    NOTE: RISK_MODE is force-locked to AGGRESSIVE during testing.
    """
    global _settings_cache
    
    file_settings = _load_from_file()
    
    settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in file_settings:
            settings[key] = file_settings[key]
        else:
            settings[key] = _get_env_value(key, default)
    
    settings["RISK_MODE"] = FORCED_RISK_MODE
    
    _settings_cache = settings
    return settings


def save_settings(settings: Dict[str, Any]) -> bool:
    """
    Save settings to JSON file.
    Returns True on success.
    """
    global _settings_cache
    
    _ensure_data_dir()
    
    merged = {**DEFAULT_SETTINGS, **settings}
    
    validated = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in merged:
            val = merged[key]
            if isinstance(default, bool):
                validated[key] = bool(val)
            elif isinstance(default, int):
                try:
                    validated[key] = int(val)
                except (ValueError, TypeError):
                    validated[key] = default
            elif key == "RISK_MODE":
                validated[key] = FORCED_RISK_MODE
            elif key == "REQUESTED_EXECUTION_MODE":
                val_str = str(val).lower()
                if val_str in VALID_EXECUTION_MODES:
                    validated[key] = val_str
                else:
                    validated[key] = default
            else:
                validated[key] = val
        else:
            validated[key] = default
    
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(validated, f, indent=2)
        _settings_cache = validated
        return True
    except IOError:
        return False


def get_setting(key: str, default: Any = None) -> Any:
    """Get a single setting value."""
    if not _settings_cache:
        load_settings()
    return _settings_cache.get(key, default)


def reset_to_defaults() -> Dict[str, Any]:
    """Reset all settings to defaults and save."""
    save_settings(DEFAULT_SETTINGS.copy())
    return DEFAULT_SETTINGS.copy()


load_settings()
