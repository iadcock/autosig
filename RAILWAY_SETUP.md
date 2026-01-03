# AutoSig v1.0 — Railway Setup Guide

## Architecture

AutoSig requires **TWO separate Railway services** in the same project:

1. **Web Service** — Flask dashboard (Gunicorn)
2. **Worker Service** — Signal ingestion (Python process)

## Step-by-Step Railway Configuration

### Step 1: Create Web Service

1. In Railway dashboard, add a **new service** to your project
2. Connect it to your GitHub repository
3. Set the **start command**:
   ```
   gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app
   ```
4. Railway will automatically set `$PORT` environment variable
5. Service will be accessible via Railway-generated URL

### Step 2: Create Worker Service

1. In the **same Railway project**, add **another service**
2. Connect it to the **same GitHub repository**
3. Set the **start command**:
   ```
   python main.py
   ```
4. **Important:** Do NOT set a port or use Gunicorn for this service
5. This service runs in the background and doesn't serve HTTP

### Step 3: Configure Environment Variables

1. In Railway project settings, go to **Variables**
2. Add all required environment variables at the **project level** (not service level)
3. Both services will inherit these variables:

**Required Variables:**
```
DRY_RUN=true
LIVE_TRADING=false
BROKER_MODE=TRADIER_ONLY
WHOP_ALERTS_URL=<your-whop-url>
WHOP_ACCESS_TOKEN=<your-token>
WHOP_REFRESH_TOKEN=<your-token>
WHOP_UID_TOKEN=<your-token>
WHOP_USER_ID=<your-id>
WHOP_SSK=<your-ssk>
WHOP_CSRF=<your-csrf>
POLL_INTERVAL_SECONDS=30
```

### Step 4: Verify Services

**Web Service:**
- Check service logs for: `Listening at: http://0.0.0.0:<PORT>`
- Visit Railway URL → Should see AutoSig dashboard
- Visit `/health` endpoint → Should return `{"status": "ok"}`

**Worker Service:**
- Check service logs for: `Starting trading bot polling loop...`
- Check logs for: `Fetching alerts...` (every 30 seconds by default)
- Check logs for: `Fetched X alerts from Whop`
- Verify `alerts_raw.jsonl` and `alerts_parsed.jsonl` are updating

## Troubleshooting

### Web Service Issues

**Error: "Failed to find attribute 'app' in 'main'"**
- **Cause:** Wrong start command (using `main:app` instead of `web:app`)
- **Fix:** Change start command to `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app`

**Error: "Module not found: dashboard"**
- **Cause:** `web.py` can't import from `dashboard.py`
- **Fix:** Ensure both files are in the repository root

### Worker Service Issues

**No logs appearing:**
- **Cause:** Service not starting or crashing immediately
- **Fix:** Check Railway service status, review error logs

**"No alerts fetched" in logs:**
- **Cause:** Whop authentication failed or feed is empty
- **Fix:** Verify Whop auth tokens are set correctly

**Worker crashes on startup:**
- **Cause:** Missing dependencies or config errors
- **Fix:** Check `requirements.txt` is complete, verify environment variables

### No New Signals

**Symptoms:**
- Feed shows no signals after 2025-12-26
- Review shows no signals after 2025-12-26
- `alerts_parsed.jsonl` not updating

**Diagnosis:**
1. Check worker service logs for "Fetching alerts..." messages
2. If missing → Worker service is not running
3. If present but "No alerts fetched" → Whop connection issue
4. If "Fetched X alerts" but no new signals → Parser or deduplication issue

**Fixes:**
- Restart worker service if not running
- Verify Whop auth tokens if connection fails
- Check parser logs if alerts fetched but not parsed

## File Structure

```
Expert-Python-Engineer/
├── web.py              # Web service entry (Gunicorn → web:app)
├── dashboard.py        # Flask app with routes
├── main.py             # Worker service (python main.py)
├── railway.toml        # Railway config (web service)
└── ...
```

## Success Criteria

✅ **Web Service:**
- Dashboard loads at Railway URL
- `/health` endpoint returns 200
- Signal Feed and Review pages load

✅ **Worker Service:**
- Logs show "Fetching alerts..." every poll interval
- Logs show "Fetched X alerts from Whop" when alerts exist
- `alerts_raw.jsonl` grows with new entries
- `alerts_parsed.jsonl` grows with new entries
- Last signal timestamp advances past 2025-12-26

## Important Notes

- **Do NOT** run `main.py` with Gunicorn
- **Do NOT** merge web and worker into one service
- **Do NOT** use threads/workers inside Flask for ingestion
- **DO** monitor both services separately
- **DO** check worker logs to verify ingestion is running

