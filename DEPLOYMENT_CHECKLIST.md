# AutoSig v1.0 — Railway Deployment Checklist

## ✅ Pre-Deployment Verification

### Step 1: Verify web.py Exists and is Committed

```bash
# Check if web.py exists
ls web.py

# Verify it's committed
git status web.py

# Should show: "nothing to commit, working tree clean" or "Changes to be committed"
```

### Step 2: Verify web.py Content

```bash
# Test import locally
python -c "from web import app; print('SUCCESS: web.py imports correctly')"
```

**Expected output:** `SUCCESS: web.py imports correctly`

### Step 3: Push to Repository

```bash
# Push web.py to GitHub
git push origin main
```

**Wait for Railway to auto-deploy** (if auto-deploy is enabled)

## Railway Service Configuration

### Web Service (Gunicorn)

**Service Name:** `web` or `dashboard` (your choice)

**Start Command:**
```
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app
```

**Verify:**
- ✅ Service shows "green" status
- ✅ No errors about "ModuleNotFoundError: No module named 'web'"
- ✅ `/health` endpoint returns "ok"
- ✅ Dashboard loads at Railway URL

### Worker Service (Ingestion)

**Service Name:** `worker` or `ingestion` (your choice)

**Start Command:**
```
python main.py
```

**Verify:**
- ✅ Service shows "green" status
- ✅ Logs show "Starting trading bot polling loop..."
- ✅ Logs show "Fetching alerts..." messages
- ✅ No errors about Gunicorn or Flask app

## Post-Deployment Verification

### Web Service Health

1. Visit Railway URL → Should see AutoSig dashboard
2. Visit `/health` → Should return "ok"
3. Check logs → No "ModuleNotFoundError" errors

### Worker Service Health

1. Check service logs → Should see "Fetching alerts..." every 30 seconds
2. Check `alerts_raw.jsonl` → Should have new entries after deployment
3. Check `alerts_parsed.jsonl` → Should have new entries after deployment
4. Check Signal Feed → Should show new signals (if any fetched)

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'web'"

**Cause:** `web.py` not committed/pushed to repository

**Fix:**
```bash
git add web.py
git commit -m "Add web.py for Railway Gunicorn"
git push origin main
```

Wait for Railway to redeploy.

### Error: "Failed to find attribute 'app' in 'web'"

**Cause:** `web.py` doesn't export `app` correctly

**Fix:** Verify `web.py` contains:
```python
from dashboard import app
```

### Worker Service Not Running

**Cause:** Service not created or wrong start command

**Fix:**
1. Create new service in Railway project
2. Set start command: `python main.py`
3. Do NOT use Gunicorn for worker service

## Success Criteria

✅ **Web Service:**
- Gunicorn starts without errors
- `/health` endpoint responds
- Dashboard loads

✅ **Worker Service:**
- Service runs continuously
- Logs show "Fetching alerts..." messages
- New alerts appear in `alerts_parsed.jsonl`

