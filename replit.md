# Options Trading Bot Project

## Overview

An automated trading bot that processes options trade alerts from Whop and executes paper trades via Alpaca API. Designed for educational purposes with paper trading as the default mode.

## Recent Changes

- 2024-12-12: Upgraded Whop scraper to use Playwright for JavaScript-rendered pages
  - Added system chromium browser for headless rendering
  - Cookie authentication with `whop-core.access-token`
  - Successfully fetching live alerts from Whop
- 2024-12-11: Initial project creation with full implementation of:
  - Alert parsing for debit/credit spreads
  - Risk management with configurable limits
  - Alpaca paper trading integration
  - DRY_RUN mode for safe testing

## Project Architecture

### Core Modules

| File | Purpose |
|------|---------|
| `main.py` | Entry point, polling loop, orchestration |
| `config.py` | Centralized configuration from environment |
| `parser.py` | Regex-based alert text parsing |
| `risk.py` | Position sizing and risk limits |
| `broker_alpaca.py` | Alpaca API integration |
| `scraper_whop.py` | Playwright-based alert fetching (Whop or local file) |
| `models.py` | Pydantic data models |

### Data Flow

1. `scraper_whop.py` → fetches alert posts via Playwright (List[str])
2. `parser.py` → converts each alert to `ParsedSignal` objects
3. `risk.py` → calculates position size
4. `broker_alpaca.py` → executes orders (or logs in DRY_RUN)
5. `main.py` → orchestrates and logs results

### Configuration

All settings via environment variables:
- `DRY_RUN`: true/false (default: true)
- `LIVE_TRADING`: true/false (default: false)
- `USE_LOCAL_ALERTS`: true/false (default: true)
- `POLL_INTERVAL_SECONDS`: integer (default: 30)
- `MAX_CONTRACTS_PER_TRADE`: integer (default: 10)

### Secrets Required

- `ALPACA_API_KEY`: Alpaca paper trading API key
- `ALPACA_API_SECRET`: Alpaca paper trading API secret
- `WHOP_SESSION`: Value of `whop-core.access-token` cookie from Whop
- `WHOP_ALERTS_URL`: URL to your Whop Trade Alerts feed

### Playwright Setup

The scraper uses Playwright with system Chromium:

```bash
pip install playwright
# System chromium is installed via Nix packages
```

System dependencies installed:
- chromium, nspr, nss, libxkbcommon, libgbm
- X11 libraries, GTK3, Mesa, etc.

## User Preferences

- Python 3.11+ with type hints
- Pydantic for data validation
- DRY_RUN mode by default for safety
- Comprehensive logging to both console and file

## Development Notes

- Run tests with: `pytest tests/ -v`
- Single run mode: `python main.py --once`
- Continuous mode: `python main.py`

## Safety Features

1. DRY_RUN mode (default) - no orders sent
2. Paper trading only (no live trading by default)
3. Risk limits enforced (max contracts, positions, daily risk)
4. Duplicate alert detection via hashing
5. Graceful error handling - skips bad alerts, keeps running
6. Fallback to local alerts file if Whop fetch fails
