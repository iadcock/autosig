# AutoSig — Railway Worker Misclassification Fix (AUTHORITATIVE)

> ⚡ **QUICK FIX:** If your start command keeps reverting to Gunicorn even after you change it, see **[IMMEDIATE_FIX_STEPS.md](./IMMEDIATE_FIX_STEPS.md)** for step-by-step instructions.

## Problem Statement

**Current Broken State:**
- Signal ingestion stopped on 2025-12-26
- Web service is healthy and running Gunicorn correctly
- "Worker Service" exists but Railway forces Gunicorn as start command
- Any attempt to set `python main.py` reverts automatically
- Gunicorn logs appear in worker logs
- No new raw alerts are ingested

**Root Cause:**
The existing "Worker Service" was originally created as a Web Service. Railway auto-classifies services at creation time. Once classified as web, Railway will:
- Force HTTP assumptions
- Inject hidden port handling
- Override start commands
- Snap back to Gunicorn
- Ignore attempts to behave like a background worker

**This classification cannot be reliably reversed.**

---

## Required Fix: Create New Background Worker Service

### ⚠️ DO NOT Attempt Workarounds

❌ **DO NOT:**
- Keep trying to change the start command on the existing service
- Add threads or fake Flask apps
- Remove PORT (it is hidden and managed internally)
- Blame GitHub or code structure

These approaches will not stick.

### ✅ Required Action: Clean Worker Service

You must create a **brand-new Railway service** explicitly as a background worker.

---

## Step-by-Step Implementation

### Step 1: Create New Background Worker Service

1. **Open Railway Dashboard**
   - Navigate to your AutoSig project

2. **Create New Service**
   - Click **"+ New"** or **"Add Service"**
   - Select **"GitHub Repo"** (same repository as Web Service)

3. **Service Type Selection (CRITICAL)**
   - When prompted for service type, select:
     - **"Background Worker"** or
     - **"Worker"** or
     - **"Background Service"**
   - **DO NOT** select "Web Service" or "HTTP Service"

4. **Service Configuration**
   - **Name:** `autosig-worker` (or any descriptive name)
   - **Repository:** Same GitHub repository as Web Service
   - **Branch:** `main` (or your default branch)

5. **Service Settings (IMPORTANT)**
   - **Public Networking:** ❌ **DISABLED** (do not enable)
   - **Domains:** ❌ **NONE** (do not add)
   - **Ports:** ❌ **NONE** (do not configure)
   - **Health Checks:** ❌ **DISABLED** (optional, not required)

6. **Start Command**
   - Navigate to **Settings** → **Deploy**
   - Set **Custom Start Command:**
     ```
     python main.py
     ```
   - **DO NOT** use Gunicorn
   - **DO NOT** reference `web.py`

7. **Environment Variables**
   - Copy all environment variables from Web Service:
     - `WHOP_ACCESS_TOKEN`
     - `WHOP_SESSION` (if used)
     - `WHOP_ALERTS_URL`
     - `DRY_RUN=true`
     - `LIVE_TRADING=false`
     - `BROKER_MODE=TRADIER_ONLY`
     - Any other required variables
   - **Settings** → **Variables** → Add each variable

8. **Deploy the Service**
   - Railway will automatically deploy
   - Wait for deployment to complete
   - Check logs for startup messages

---

### Step 2: Delete/Archive Old Misclassified Service

1. **Identify the Old Service**
   - Find the service that was incorrectly classified
   - It likely shows Gunicorn logs or HTTP-related errors

2. **Delete or Archive**
   - **Option A (Recommended):** Delete the service
     - Settings → Danger Zone → Delete Service
   - **Option B:** Archive/Disable the service
     - Settings → Disable Service (if available)

3. **Verify Cleanup**
   - Only **two** services should remain:
     - Web Service (Gunicorn, `web:app`)
     - Worker Service (Python, `python main.py`)

---

## Verification Requirements (MANDATORY)

The fix is successful **only when ALL** of the following are true:

### ✅ Check 1: Worker Logs Contain No Gunicorn Output

**Expected:**
```
2025-01-02T12:00:00.000Z [INFO] Starting trading bot polling loop...
2025-01-02T12:00:00.000Z [INFO] Fetching alerts...
```

**❌ Failure Indicators:**
- `[INFO] Starting gunicorn`
- `[INFO] Listening at: http://0.0.0.0:PORT`
- `[ERROR] Failed to find attribute 'app'`
- Any HTTP server startup messages

---

### ✅ Check 2: Worker Logs Show Polling Loop Activity

**Expected Log Pattern:**
```
[INFO] Starting trading bot polling loop...
[INFO] Fetching alerts...
[INFO] Fetched N alerts from Whop
[INFO] Processed M new alerts (K duplicates skipped)
[INFO] Waiting 30 seconds before next poll...
```

**Repeat every 30 seconds (or configured POLL_INTERVAL_SECONDS)**

---

### ✅ Check 3: Raw Alerts Timestamp Advances Past 2025-12-26

**How to Check:**
1. Access Railway Worker Service logs
2. Look for log entries showing new alerts
3. Or check `alerts_raw.jsonl` file (if accessible)

**Expected:**
- New entries with timestamps after `2025-12-26T20:47:24`
- Timestamps should be current (within last few minutes/hours)

**Verification Command (if file accessible):**
```bash
tail -1 logs/alerts_raw.jsonl | jq -r '.ts_iso'
```

Should show a timestamp **after** `2025-12-26T20:47:24`

---

### ✅ Check 4: Signal Feed Repopulates Automatically

**How to Check:**
1. Open AutoSig dashboard (Web Service URL)
2. Navigate to **Signal Feed** (`/feed`)
3. Check for signals with timestamps after 2025-12-26

**Expected:**
- New signals appear in the feed
- Timestamps are current
- Certainty labels show (A) or (U)

---

### ✅ Check 5: Signal Review Repopulates Automatically

**How to Check:**
1. Open AutoSig dashboard
2. Navigate to **Signal Review** (`/signal-review`)
3. Check for signals with timestamps after 2025-12-26

**Expected:**
- Same signals as Feed are visible
- Manual override buttons work
- Certainty resolution works correctly

---

## Troubleshooting

### Issue: Worker Service Still Shows Gunicorn Logs

**Cause:** Service was created as Web Service type

**Fix:**
1. Delete the service completely
2. Create a **new** service, ensuring you select **"Background Worker"** type
3. Do not enable Public Networking or domains

---

### Issue: Start Command Reverts to Gunicorn

**Cause:** Railway is auto-detecting the service as web

**Fix:**
1. Verify service type is "Background Worker" (not "Web Service")
2. If type cannot be changed, delete and recreate
3. Ensure no `PORT` or HTTP-related environment variables are set

---

### Issue: No Logs Appear

**Possible Causes:**
1. Service is not deployed
2. Service crashed on startup
3. Logs are delayed

**Fix:**
1. Check service status (should be "Active")
2. Check deployment logs for errors
3. Verify `main.py` exists and is executable
4. Check environment variables are set correctly

---

### Issue: Worker Runs But No Alerts Fetched

**Possible Causes:**
1. Whop credentials expired
2. `WHOP_ALERTS_URL` incorrect
3. Whop page structure changed
4. Network connectivity issues

**Fix:**
1. Verify `WHOP_ACCESS_TOKEN` is valid
2. Check `WHOP_ALERTS_URL` is correct
3. Review worker logs for Whop fetch errors
4. Test Whop connection manually (if possible)

---

## Success Criteria Summary

✅ **Worker logs contain no Gunicorn output**  
✅ **Worker logs show polling loop startup**  
✅ **Worker logs show repeated fetch attempts**  
✅ **`alerts_raw.jsonl` timestamps advance past 2025-12-26**  
✅ **Signal Feed repopulates automatically**  
✅ **Signal Review repopulates automatically**

---

## Final Authority Rule

**Railway service type is immutable in practice.**

If it was born web, replace it.

**Do not refactor code to compensate for infrastructure misclassification.**

Implement the clean worker service exactly as described.

---

## Quick Reference

### Web Service Configuration
- **Type:** Web Service
- **Start Command:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app`
- **Public Networking:** ✅ Enabled
- **Purpose:** Serve Flask dashboard, API endpoints, health checks

### Worker Service Configuration
- **Type:** Background Worker
- **Start Command:** `python main.py`
- **Public Networking:** ❌ Disabled
- **Purpose:** Poll Whop, ingest alerts, parse signals

---

## Post-Fix Verification Checklist

After implementing the fix:

- [ ] New Worker Service created as "Background Worker" type
- [ ] Start command set to `python main.py`
- [ ] Public Networking disabled
- [ ] All environment variables copied from Web Service
- [ ] Old misclassified service deleted/archived
- [ ] Worker logs show no Gunicorn output
- [ ] Worker logs show polling loop activity
- [ ] New alerts appear in `alerts_raw.jsonl` (timestamp > 2025-12-26)
- [ ] Signal Feed shows new signals
- [ ] Signal Review shows new signals

---

**Last Updated:** 2025-01-02  
**Status:** Ready for implementation

