# Options Trading Bot Project

## Overview
This project is an automated options trading bot designed to process trade alerts from Whop and execute paper trades via the Alpaca API. Its primary purpose is educational, with paper trading as the default and highly emphasized mode. The bot features comprehensive risk management, a review queue for signals, and a Flask-based dashboard for monitoring and interaction. It supports various option strategies, including debit/credit spreads and single-leg options, with the capability for future expansion to live trading with the Tradier API. The project aims to provide a safe, controlled environment for learning automated trading strategies, emphasizing transparency, configurability, and robust error handling.

## User Preferences
- Python 3.11+ with type hints
- Pydantic for data validation
- DRY_RUN mode by default for safety
- Comprehensive logging to both console and file

## System Architecture

### UI/UX Decisions
The project features a Flask-based dashboard accessible via a web interface, running on port 5000. It utilizes Jinja2 templates (`base.html`, `dashboard.html`, `review.html`, `brokers.html`, `settings.html`, `logs.html`) for structure and `styles.css` and `app.js` for styling and interactivity. The dashboard provides tabbed navigation for different functionalities: Dashboard, Review Queue, Brokers, Settings, and Logs. It offers visual indicators for pre-flight checks, broker health, and auto-mode status. A red warning banner is displayed if live trading is enabled, emphasizing the inherent risks.

### Technical Implementations
The bot is built around a modular architecture with distinct components for scraping, parsing, risk management, execution, and logging.
- **Alert Scraping**: Uses Playwright with system Chromium to fetch JavaScript-rendered alerts from Whop.
- **Signal Processing**: Employs regex-based parsing to convert raw alerts into `ParsedSignal` objects, followed by conversion to broker-agnostic `TradeIntent` objects.
- **Risk Management**: Implements configurable risk limits (e.g., max contracts per trade, daily risk percentage) and pre-flight safety checks (completeness, supported assets, DTE guard, deduplication) before execution.
- **Execution System**: Features a broker-agnostic `TradeIntent` and `ExecutionResult` model. It routes trades based on `execution_mode` (PAPER, LIVE, HISTORICAL) to dedicated executors (`PaperExecutor`, `TradierExecutor`, `HistoricalExecutor`).
- **Position Tracking**: Maintains a JSONL-backed store for tracking paper trading positions, including opening and closing of trades.
- **Idempotency**: Prevents duplicate executions of signals using a JSONL-backed deduplication store.
- **Review Queue**: Allows manual review and approval/rejection of signals before execution.
- **Configuration Management**: Centralized configuration via environment variables with a fallback mechanism and an `env_loader.py` for reliable secret detection.
- **Logging & Reporting**: Comprehensive logging to various files (trade logs, parsed signals, raw/parsed alerts, execution plans) and daily trade summaries generated at market close. A DOCX report generation utility is also included.
- **Broker Health Checks**: Modules for verifying connectivity and status of integrated brokers (Alpaca, Tradier) without placing actual trades.
- **Auto Mode**: An automated paper trading mode with configurable rate limits, active only during market hours, and enforced by Alpaca's market clock.

### Feature Specifications
- **Alert Parsing**: Supports various options strategies including debit/credit spreads and single-leg options, as well as stock and ETF trades.
- **Trade Execution**: Capable of executing market and limit orders for stocks and options.
- **Safety Features**: `DRY_RUN` mode (default), paper trading only (default), risk limits, duplicate alert detection, graceful error handling, and local alert file fallback.
- **Daily Summary**: Automatically generates a detailed daily trade summary using NYSE market calendar for accurate timing.
- **Broker Smoke Tests**: Dashboard includes buttons to perform connectivity and basic order flow tests for integrated brokers.

### System Design Choices
- **Modularity**: Codebase is highly modular, separating concerns into dedicated files and directories (e.g., `executors/`).
- **Data Models**: Utilizes Pydantic for robust data validation and clear definition of data structures.
- **Environment-based Configuration**: All sensitive information and configurable parameters are managed through environment variables, promoting secure deployment.
- **Playwright for Scraping**: Chosen for its ability to handle modern, JavaScript-rendered web pages, ensuring reliable alert fetching.
- **JSONL for Data Storage**: Used for persistent storage of paper positions, deduplication records, and execution plans due to its append-only nature and ease of parsing.

## External Dependencies
- **Whop**: Source for trade alerts (requires `WHOP_ALERTS_URL`, `WHOP_ACCESS_TOKEN`, `WHOP_REFRESH_TOKEN`, `WHOP_UID_TOKEN`, `WHOP_USER_ID`, `WHOP_SSK`, `WHOP_CSRF` cookies for scraping).
- **Alpaca API**: Used for paper trading execution and market data (requires `ALPACA_API_KEY`, `ALPACA_API_SECRET`).
- **Tradier API**: Integrated for potential live trading and market data (requires `TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID`).
- **Playwright**: Browser automation library for scraping Whop alerts.
- **Flask**: Web framework for the dashboard.
- **Gunicorn**: WSGI HTTP Server for deploying the Flask dashboard.
- **Pydantic**: Data validation library.
- **pandas_market_calendars**: Library for accurate NYSE market calendar operations, used for daily summaries.
- **Pytest**: Testing framework.