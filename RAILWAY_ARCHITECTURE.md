# AutoSig v1.0 — Railway Architecture Guide

## Architecture Overview

AutoSig runs as **ONE Railway project with TWO separate services**:

1. **Web Service** — Serves UI and API endpoints
2. **Worker Service** — Ingests signals from Whop

## Service Configuration

### Service 1: Web Service

**Purpose:** Serve Flask dashboard, API endpoints, health checks

**File:** `web.py` (imports Flask app from `dashboard.py`)

**Railway Start Command:**
```bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app
```

**Environment Variables:**
- All shared config (DRY_RUN, LIVE_TRADING, etc.)
- Web-specific: `PORT` (set by Railway)

**Health Check:**
- `/health` endpoint available
- Service should stay alive and respond to HTTP requests

### Service 2: Worker Service

**Purpose:** Poll Whop, ingest alerts, parse signals

**File:** `main.py` (background worker process)

**Railway Start Command:**
```bash
python main.py
```

**Environment Variables:**
- All shared config (DRY_RUN, LIVE_TRADING, etc.)
- Whop auth: `WHOP_ALERTS_URL`, `WHOP_ACCESS_TOKEN`, etc.

**Behavior:**
- Runs continuously in polling loop
- Fetches alerts from Whop every `POLL_INTERVAL_SECONDS`
- Logs to `logs/app.log` and `logs/alerts_*.jsonl`
- Must NOT be run by Gunicorn

## Critical Rules

### ❌ DO NOT:
- Run `main.py` with Gunicorn
- Merge web and worker into one process
- Use threads/workers inside Flask to run ingestion
- Rely on "green" status as proof of ingestion

### ✅ DO:
- Keep web and worker as separate Railway services
- Share environment variables between services
- Monitor worker logs separately from web logs
- Verify ingestion by checking `alerts_parsed.jsonl` timestamps

## Railway Setup Steps

1. **Create Web Service:**
   - Add new service in Railway project
   - Set start command: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app`
   - Configure port (Railway sets `$PORT` automatically)

2. **Create Worker Service:**
   - Add new service in Railway project
   - Set start command: `python main.py`
   - No port needed (not a web service)

3. **Share Environment Variables:**
   - Set all config vars at project level
   - Both services inherit the same variables

4. **Verify Services:**
   - Web service: Check `/health` endpoint responds
   - Worker service: Check logs show "Fetching alerts..." messages

## Troubleshooting

### Worker Not Running
- Check Railway service status
- Check worker service logs for errors
- Verify start command is `python main.py` (NOT `gunicorn main:app`)

### No New Signals
- Check worker logs for "Fetching alerts..." messages
- Check for Whop authentication errors
- Verify `alerts_raw.jsonl` and `alerts_parsed.jsonl` are updating

### Gunicorn Errors
- Ensure web service uses `web:app` (NOT `main:app`)
- Verify `web.py` exists and imports `app` from `dashboard.py`

## Success Indicators

✅ **Web Service:**
- `/health` endpoint returns 200
- Dashboard loads at Railway URL
- API endpoints respond

✅ **Worker Service:**
- Logs show "Fetching alerts..." every poll interval
- `alerts_raw.jsonl` grows with new entries
- `alerts_parsed.jsonl` grows with new entries
- Last signal timestamp advances past 2025-12-26

## File Structure

```
Expert-Python-Engineer/
├── web.py              # Web service entry point (Gunicorn)
├── dashboard.py        # Flask app with all routes
├── main.py             # Worker service (background process)
├── railway.toml        # Railway config (web service only)
└── ...
```

