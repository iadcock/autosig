# Options Trading Bot

An automated trading bot that processes options trade alerts and executes paper trades via Alpaca API.

---

## IMPORTANT DISCLAIMER

**THIS PROJECT IS FOR EDUCATIONAL PURPOSES ONLY.**

- All trading is done on **PAPER (simulated) accounts** by default
- This is NOT financial advice
- You are solely responsible for any trading decisions and potential losses
- Never trade with money you cannot afford to lose
- Past performance does not guarantee future results

**By using this code, you acknowledge that:**
1. You understand the risks involved in options trading
2. You will not hold the authors liable for any financial losses
3. You will thoroughly test any modifications before using real money

---

## What This Bot Does

1. **Fetches Alerts**: Reads trade alerts from a Whop "Trade Alerts" feed (or a local sample file)
2. **Parses Signals**: Extracts structured trade information (ticker, strategy, expiration, legs, limits)
3. **Applies Risk Rules**: Calculates position size based on account equity and configurable risk limits
4. **Executes Paper Trades**: Sends orders to Alpaca's paper trading API
5. **Logs Everything**: Records all trade decisions for review

### Supported Strategies

- **Call Debit Spreads** (bullish)
- **Call Credit Spreads** (bearish)
- **Exit/Close** positions

---

## Quick Start

### 1. Set Up Environment Variables

In Replit, go to **Secrets** (lock icon) and add:

| Secret Name | Description |
|-------------|-------------|
| `ALPACA_API_KEY` | Your Alpaca paper trading API key |
| `ALPACA_API_SECRET` | Your Alpaca paper trading API secret |
| `WHOP_SESSION` | (Optional) Your Whop session cookie |
| `WHOP_ALERTS_URL` | (Optional) URL to your Whop alerts feed |

### 2. Get Alpaca Paper Trading Credentials

1. Create a free account at [Alpaca](https://alpaca.markets)
2. Go to **Paper Trading** section
3. Generate API keys
4. Add them to Replit Secrets

### 3. Choose Your Mode

#### DRY_RUN Mode (Default - Safest)
```
DRY_RUN=true
```
- No API calls are made
- All trades are logged only
- Perfect for testing the parser and risk calculations

#### Paper Trading Mode
```
DRY_RUN=false
LIVE_TRADING=true
```
- Sends real orders to Alpaca PAPER account
- No real money is used
- Good for testing the full flow

---

## Configuration Options

Set these as environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | If true, only log trades without sending to Alpaca |
| `LIVE_TRADING` | `false` | Must be true to actually send orders |
| `POLL_INTERVAL_SECONDS` | `30` | How often to check for new alerts |
| `USE_LOCAL_ALERTS` | `true` | Use local sample_alerts.txt instead of Whop |
| `MAX_CONTRACTS_PER_TRADE` | `10` | Maximum contracts per single trade |
| `MAX_OPEN_POSITIONS` | `20` | Maximum number of open positions |
| `MAX_DAILY_RISK_PCT` | `0.10` | Maximum daily risk as percentage (10%) |
| `DEFAULT_SIZE_PCT` | `0.01` | Default position size if not in alert (1%) |

---

## Using Local Alerts

For testing without Whop access:

1. Set `USE_LOCAL_ALERTS=true` (default)
2. Edit `sample_alerts.txt` with your test alerts
3. Run the bot

Example alert format:
```
GLD leap bullish call debit spread

6/17/2027 exp

+1 415 C / -1 420 C
Limit 1.85-1.9 debit to open

2% size
```

---

## Project Structure

```
.
├── main.py              # Main entry point and polling loop
├── config.py            # Configuration and settings
├── parser.py            # Alert text parsing
├── risk.py              # Risk management and position sizing
├── broker_alpaca.py     # Alpaca API integration
├── scraper_whop.py      # Whop alert fetching
├── models.py            # Pydantic data models
├── sample_alerts.txt    # Sample alerts for testing
├── state.json           # Runtime state (auto-generated)
├── logs/
│   └── trades.log       # Trade log file
└── tests/
    ├── test_parser.py   # Parser unit tests
    └── test_risk.py     # Risk manager unit tests
```

---

## Running the Bot

### Continuous Polling Mode
```bash
python main.py
```
Runs continuously, checking for new alerts every POLL_INTERVAL_SECONDS.

### Single Cycle Mode
```bash
python main.py --once
```
Processes alerts once and exits. Good for testing.

### Run Tests
```bash
pytest tests/ -v
```

---

## How Risk Management Works

### Position Sizing

For **Debit Spreads**:
```
max_contracts = floor(account_equity * size_pct / (limit_max * 100))
```

For **Credit Spreads**:
```
max_loss_per_contract = (spread_width - credit_received) * 100
max_contracts = floor(account_equity * size_pct / max_loss_per_contract)
```

### Safety Caps

The bot enforces multiple safety limits:
- Maximum contracts per trade
- Maximum open positions
- Maximum daily risk percentage

If any limit is violated, the trade is **skipped** (not crashed).

---

## Logs and Monitoring

All trades are logged to:
- Console output (stdout)
- `logs/trades.log` file

The `state.json` file tracks:
- Previously processed alerts (to prevent duplicates)
- Daily trade counts and risk used

---

## Troubleshooting

### "Alpaca API credentials not configured"
Add `ALPACA_API_KEY` and `ALPACA_API_SECRET` to Replit Secrets.

### "Trade rejected: Position size too small"
The calculated position size is less than 1 contract. Either:
- Increase account equity
- Increase position size percentage
- Decrease the limit price

### "Max open positions limit reached"
Increase `MAX_OPEN_POSITIONS` or wait for positions to close.

---

## Safety Reminders

1. **Always start with DRY_RUN=true**
2. **Test thoroughly with paper trading before any real money**
3. **Monitor your trades regularly**
4. **Understand every trade the bot makes**
5. **Never trade more than you can afford to lose**

---

## License

MIT License - Use at your own risk.
