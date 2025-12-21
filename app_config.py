"""
Centralized application configuration with safe defaults.
All settings default to PAPER-ONLY, safe operation.
"""

import os
from env_loader import load_env


def get_bool(key: str, default: bool = False) -> bool:
    """Get a boolean config value from environment."""
    val = load_env(key) or os.getenv(key, "")
    return val.lower() in ("true", "1", "yes", "on") if val else default


def get_int(key: str, default: int) -> int:
    """Get an integer config value from environment."""
    val = load_env(key) or os.getenv(key, "")
    try:
        return int(val) if val else default
    except ValueError:
        return default


def get_str(key: str, default: str = "") -> str:
    """Get a string config value from environment."""
    return load_env(key) or os.getenv(key, default) or default


class AppConfig:
    """Application configuration with safe defaults."""
    
    # Environment
    APP_ENV = get_str("APP_ENV", "production")
    DEBUG = get_bool("DEBUG", False)
    
    # SAFETY: Trading is OFF by default
    LIVE_TRADING = get_bool("LIVE_TRADING", False)
    AUTO_MODE_ENABLED = get_bool("AUTO_MODE_ENABLED", False)
    PAPER_MIRROR_ENABLED = get_bool("PAPER_MIRROR_ENABLED", False)
    DRY_RUN = get_bool("DRY_RUN", True)
    
    # Trading limits
    MAX_CONTRACTS_PER_TRADE = get_int("MAX_CONTRACTS_PER_TRADE", 10)
    MAX_OPEN_POSITIONS = get_int("MAX_OPEN_POSITIONS", 20)
    MAX_DAILY_RISK_PCT = get_int("MAX_DAILY_RISK_PCT", 10)
    
    # Auto mode
    AUTO_POLL_SECONDS = get_int("AUTO_POLL_SECONDS", 30)
    AUTO_WINDOW_BUFFER_MINUTES = get_int("AUTO_WINDOW_BUFFER_MINUTES", 60)
    AUTO_MAX_TRADES_PER_DAY = get_int("AUTO_MAX_TRADES_PER_DAY", 10)
    AUTO_MAX_TRADES_PER_HOUR = get_int("AUTO_MAX_TRADES_PER_HOUR", 3)
    
    # Brokers
    PRIMARY_LIVE_BROKER = get_str("PRIMARY_LIVE_BROKER", "tradier")
    
    # Auth
    APP_PASSWORD = get_str("APP_PASSWORD", "")
    SESSION_SECRET = get_str("SESSION_SECRET", os.urandom(24).hex())
    
    # Server
    PORT = get_int("PORT", 5000)
    
    @classmethod
    def is_production(cls) -> bool:
        return cls.APP_ENV.lower() == "production"
    
    @classmethod
    def requires_auth(cls) -> bool:
        return bool(cls.APP_PASSWORD)
    
    @classmethod
    def get_warnings(cls) -> list:
        """Return list of warnings for unsafe configurations."""
        warnings = []
        if cls.LIVE_TRADING:
            warnings.append("LIVE TRADING IS ENABLED - Real money at risk!")
        if cls.AUTO_MODE_ENABLED and cls.LIVE_TRADING:
            warnings.append("AUTO MODE + LIVE TRADING is extremely risky!")
        if not cls.DRY_RUN and cls.LIVE_TRADING:
            warnings.append("DRY_RUN is disabled with LIVE_TRADING - orders will execute!")
        return warnings
    
    @classmethod
    def to_dict(cls) -> dict:
        """Return safe config (no secrets) as dictionary."""
        return {
            "app_env": cls.APP_ENV,
            "live_trading": cls.LIVE_TRADING,
            "auto_mode_enabled": cls.AUTO_MODE_ENABLED,
            "paper_mirror_enabled": cls.PAPER_MIRROR_ENABLED,
            "dry_run": cls.DRY_RUN,
            "max_contracts_per_trade": cls.MAX_CONTRACTS_PER_TRADE,
            "max_open_positions": cls.MAX_OPEN_POSITIONS,
            "auto_poll_seconds": cls.AUTO_POLL_SECONDS,
            "auto_window_buffer_minutes": cls.AUTO_WINDOW_BUFFER_MINUTES,
            "auto_max_trades_per_day": cls.AUTO_MAX_TRADES_PER_DAY,
            "auto_max_trades_per_hour": cls.AUTO_MAX_TRADES_PER_HOUR,
            "primary_live_broker": cls.PRIMARY_LIVE_BROKER,
            "requires_auth": cls.requires_auth(),
            "warnings": cls.get_warnings()
        }


config = AppConfig()
