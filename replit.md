# Options Trading Bot Project

## Overview

An automated trading bot that processes options trade alerts from Whop and executes paper trades via Alpaca API. Designed for educational purposes with paper trading as the default mode.

## Recent Changes

- 2024-12-14: Added broker-agnostic TradeIntent schema and execution routing
  - TradeIntent model: Broker-independent trade representation
  - ExecutionResult model: Unified execution outcome
  - Executors: TradierExecutor, PaperExecutor, HistoricalExecutor
  - Router: Routes by execution_mode (PAPER, LIVE, HISTORICAL)
  - Demo script: trade_intent_demo.py
- 2024-12-14: Added Tradier API client (tradier_client.py)
  - Account management, market data, order placement
  - Supports stocks, ETFs, and single-leg options
  - Smoke test: tradier_smoketest.py
- 2024-12-13: Added support for LONG positions (stocks and options)
  - New strategies: LONG_STOCK, LONG_OPTION
  - Parses patterns like "Long AAPL", "Buy 100 shares of TSLA", "Long SPY 480C Jan 2026"
  - TRADING_MODE config: CONSERVATIVE (default) skips long positions, STANDARD allows them
  - Long positions are logged to alerts_parsed.jsonl and execution_plan.jsonl
- 2024-12-12: Added daily trade summary at market close
  - Uses NYSE calendar (pandas_market_calendars) for accurate timing
  - Runs at market close + 5 minutes (handles early closes)
  - Summary files saved to logs/daily_summary_YYYY-MM-DD.txt
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
| `summary.py` | Daily trade summary generation at market close |
| `models.py` | Pydantic data models |
| `trade_intent.py` | TradeIntent and ExecutionResult models |
| `tradier_client.py` | Tradier API client |
| `executors/` | Trade executors (tradier, paper, historical) |
| `execution/router.py` | Execution routing by mode |

### Data Flow

1. `scraper_whop.py` → fetches alert posts via Playwright (List[str])
2. `parser.py` → converts each alert to `ParsedSignal` objects
3. `risk.py` → calculates position size
4. `broker_alpaca.py` → executes orders (or logs in DRY_RUN)
5. `main.py` → orchestrates and logs results
6. `summary.py` → generates daily summary at market close

### Daily Summary

The bot automatically generates a daily trade summary at market close:

- **Timing**: Runs at market close + 5 minutes (4:05 PM ET regular days, 1:05 PM ET early close days)
- **Calendar**: Uses NYSE calendar via `pandas_market_calendars` for accurate trading day detection
- **Early Close Support**: Automatically detects early close days (e.g., day before holidays)
- **Output**: `logs/daily_summary_YYYY-MM-DD.txt`
- **Content**: Trade count, status breakdown, ticker summary, and trade details

### Configuration

All settings via environment variables:
- `DRY_RUN`: true/false (default: true)
- `LIVE_TRADING`: true/false (default: false)
- `TRADING_MODE`: CONSERVATIVE/STANDARD (default: CONSERVATIVE)
  - CONSERVATIVE: Long positions are classified but skipped (not executed)
  - STANDARD: Long positions may be executed (when implemented)
- `USE_LOCAL_ALERTS`: true/false (default: true)
- `POLL_INTERVAL_SECONDS`: integer (default: 30)
- `MAX_CONTRACTS_PER_TRADE`: integer (default: 10)

### TradeIntent Execution System

Broker-agnostic trade execution:

```python
from trade_intent import TradeIntent, OptionLeg
from execution import execute_trade

# Stock order
intent = TradeIntent(
    execution_mode="PAPER",  # PAPER, LIVE, or HISTORICAL
    instrument_type="STOCK",
    underlying="SPY",
    action="BUY",
    order_type="MARKET",
    quantity=1
)
result = execute_trade(intent)

# Option order
intent = TradeIntent(
    execution_mode="PAPER",
    instrument_type="OPTION",
    underlying="SPX",
    action="BUY_TO_OPEN",
    order_type="LIMIT",
    limit_price=15.50,
    quantity=1,
    legs=[OptionLeg(side="BUY", quantity=1, strike=6100.0, option_type="CALL", expiration="2025-01-17")]
)
result = execute_trade(intent)
```

Execution modes:
- **PAPER**: Simulated fills (PaperExecutor)
- **LIVE**: Real orders via Tradier (requires TRADIER_TOKEN)
- **HISTORICAL**: Backtesting with historical prices

### Secrets Required

- `TRADIER_TOKEN`: Tradier sandbox/live API token
- `TRADIER_ACCOUNT_ID`: Tradier account ID (optional, auto-discovered)
- `ALPACA_API_KEY`: Alpaca paper trading API key
- `ALPACA_API_SECRET`: Alpaca paper trading API secret
- `WHOP_ALERTS_URL`: URL to your Whop Trade Alerts feed
- `WHOP_ACCESS_TOKEN`: Value of `whop-core.access-token` cookie
- `WHOP_REFRESH_TOKEN`: Value of `whop-core.refresh-token` cookie
- `WHOP_UID_TOKEN`: Value of `whop-core.uid-token` cookie
- `WHOP_USER_ID`: Value of `whop-core.user-id` cookie
- `WHOP_SSK`: Value of `whop-core.ssk` cookie
- `WHOP_CSRF`: Value of `_Host-whop-core.csrf-token` cookie

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

## Log Files

- `logs/trades.log` - Full trade execution log
- `logs/parsed_signals.csv` - CSV of all parsed signals (downloadable)
- `logs/daily_summary_YYYY-MM-DD.txt` - Daily trade summaries at market close
- `logs/alerts_raw.jsonl` - Raw alerts fetched from Whop (JSONL)
- `logs/alerts_parsed.jsonl` - Parsed alert results with classification (JSONL)
- `logs/execution_plan.jsonl` - Execution plans for each signal (JSONL)

## Reporting System

The bot includes a comprehensive reporting system:

### CLI Report Generation
```bash
python report_docx.py              # Last 24 hours (default)
python report_docx.py --hours 48   # Custom hours
```

### Flask Dashboard
- Runs on port 5000
- "Generate Last 24 Hours Report" button
- Reports saved to `reports/whop_trade_report_<timestamp>.docx`

### Broker Smoke Test Dashboard
The dashboard includes smoke test buttons for each broker:

**Alpaca Test** (paper trading):
- GET account info, market clock, AAPL asset
- BUY 1 share AAPL (market order)
- Confirm position exists
- SELL 1 share AAPL (market order)
- Confirm position closed
- GET recent orders

**Tradier Test** (sandbox):
- GET profile/account info
- GET SPY quote
- GET option expirations (SPX, fallback to SPY)
- GET option chain
- BUY 1 share SPY (if sandbox supports)
- Confirm position, SELL, confirm closed

Required secrets:
- Alpaca: `ALPACA_API_KEY`, `ALPACA_API_SECRET`
- Tradier: `TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID` (optional)

Environment variable sources (checked in order):
1. os.getenv() - Workspace Secrets
2. REPLIT_* prefixed - Deployment env
3. config_local.py - Optional local fallback (gitignored)

Debug endpoint: GET /debug/env - Shows which env vars are detected (no values exposed)

### Report Contents
- Summary metrics (total alerts, signals, executions, skips)
- Table of all trading signals parsed
- Execution plans with contract details
- Non-signal alerts with classification reasons
