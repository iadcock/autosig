"""
Configuration module for the trading bot.
Centralizes all settings and environment variables.

IMPORTANT: Set these environment variables in Replit Secrets:
- WHOP_SESSION: Your Whop session cookie for authentication
- ALPACA_API_KEY: Your Alpaca paper trading API key
- ALPACA_API_SECRET: Your Alpaca paper trading API secret
"""

import os
from typing import Optional


WHOP_ALERTS_URL: Optional[str] = os.getenv("WHOP_ALERTS_URL")

WHOP_SESSION: Optional[str] = os.getenv("WHOP_SESSION")

POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

LIVE_TRADING: bool = os.getenv("LIVE_TRADING", "false").lower() == "true"

DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

ALPACA_API_KEY: Optional[str] = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET: Optional[str] = os.getenv("ALPACA_API_SECRET")
ALPACA_PAPER_BASE_URL: str = os.getenv(
    "ALPACA_PAPER_BASE_URL", 
    "https://paper-api.alpaca.markets"
)

MAX_CONTRACTS_PER_TRADE: int = int(os.getenv("MAX_CONTRACTS_PER_TRADE", "10"))
MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "20"))
MAX_DAILY_RISK_PCT: float = float(os.getenv("MAX_DAILY_RISK_PCT", "0.10"))

DEFAULT_SIZE_PCT: float = float(os.getenv("DEFAULT_SIZE_PCT", "0.01"))

STATE_FILE: str = "state.json"
SAMPLE_ALERTS_FILE: str = "sample_alerts.txt"
TRADE_LOG_FILE: str = "logs/trades.log"

USE_LOCAL_ALERTS: bool = os.getenv("USE_LOCAL_ALERTS", "true").lower() == "true"


def validate_config() -> list[str]:
    """
    Validate configuration and return list of warnings/errors.
    Returns empty list if all critical settings are properly configured.
    """
    warnings = []
    
    if not DRY_RUN and not LIVE_TRADING:
        pass
    
    if LIVE_TRADING and DRY_RUN:
        warnings.append("Both LIVE_TRADING and DRY_RUN are set. DRY_RUN takes precedence.")
    
    if not DRY_RUN:
        if not ALPACA_API_KEY:
            warnings.append("ALPACA_API_KEY not set. Required for paper trading.")
        if not ALPACA_API_SECRET:
            warnings.append("ALPACA_API_SECRET not set. Required for paper trading.")
    
    if not USE_LOCAL_ALERTS:
        if not WHOP_ALERTS_URL:
            warnings.append("WHOP_ALERTS_URL not set. Will fall back to local alerts.")
        if not WHOP_SESSION:
            warnings.append("WHOP_SESSION not set. Cannot authenticate with Whop.")
    
    return warnings


def print_config_summary() -> None:
    """Print current configuration for debugging."""
    print("=" * 50)
    print("TRADING BOT CONFIGURATION")
    print("=" * 50)
    print(f"DRY_RUN: {DRY_RUN} (no actual orders sent)")
    print(f"LIVE_TRADING: {LIVE_TRADING}")
    print(f"USE_LOCAL_ALERTS: {USE_LOCAL_ALERTS}")
    print(f"POLL_INTERVAL_SECONDS: {POLL_INTERVAL_SECONDS}")
    print(f"MAX_CONTRACTS_PER_TRADE: {MAX_CONTRACTS_PER_TRADE}")
    print(f"MAX_OPEN_POSITIONS: {MAX_OPEN_POSITIONS}")
    print(f"MAX_DAILY_RISK_PCT: {MAX_DAILY_RISK_PCT * 100}%")
    print(f"DEFAULT_SIZE_PCT: {DEFAULT_SIZE_PCT * 100}%")
    print(f"Alpaca API Key configured: {bool(ALPACA_API_KEY)}")
    print(f"Whop URL configured: {bool(WHOP_ALERTS_URL)}")
    print("=" * 50)
