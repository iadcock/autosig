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
    "MAX_RISK_PCT_PER_TRADE": 2,
    "MAX_DAILY_RISK_PCT": 10,
    "MAX_OPEN_POSITIONS": 20,
    "ALLOW_0DTE_SPX": False,
    "AUTO_MAX_TRADES_PER_DAY": 10,
    "AUTO_MAX_TRADES_PER_HOUR": 3,
}

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
    """
    global _settings_cache
    
    file_settings = _load_from_file()
    
    settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in file_settings:
            settings[key] = file_settings[key]
        else:
            settings[key] = _get_env_value(key, default)
    
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
