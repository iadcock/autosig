# Immediate Fix: Railway Worker Service Reverting to Gunicorn

## The Problem You're Seeing

Your Railway service keeps reverting the start command to:
```
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Even after you change it to `python main.py`, it snaps back.

**This is because the service was created as a "Web Service" type.**

## The Solution: Create a NEW Service

You **cannot** fix the existing service. You must create a **brand new** one.

---

## Step-by-Step Fix (Do This Now)

### Step 1: Delete the Current Misclassified Service

1. In Railway dashboard, find the service that keeps reverting to Gunicorn
2. Click on the service name
3. Go to **Settings** (gear icon or Settings tab)
4. Scroll to the bottom to **"Danger Zone"** or **"Delete Service"**
5. Click **"Delete Service"** or **"Remove Service"**
6. Confirm deletion

**⚠️ Don't worry** - you'll create a new one immediately.

---

### Step 2: Create a NEW Background Worker Service

1. In your Railway project dashboard, click **"+ New"** or **"Add Service"**
2. Select **"GitHub Repo"** (same repository as your Web Service)
3. **CRITICAL STEP:** When Railway asks what type of service, look for:
   - **"Background Worker"** ← **SELECT THIS**
   - **"Worker"** ← OR THIS
   - **"Background Service"** ← OR THIS
   
   **DO NOT** select:
   - ❌ "Web Service"
   - ❌ "HTTP Service"
   - ❌ "API Service"

4. If Railway doesn't explicitly ask for service type, look for these options:
   - Service settings → Service Type → Change to "Worker" or "Background"
   - Or check if there's a toggle/switch for "Web Service" vs "Worker"

---

### Step 3: Configure the New Service

1. **Name the service:** `autosig-worker` (or any name you prefer)

2. **Go to Settings → Deploy**

3. **Custom Start Command:**
   - Clear the field if it has Gunicorn
   - Enter: `python main.py`
   - Save

4. **Disable Public Networking:**
   - Go to **Settings → Networking**
   - **Public Networking:** Turn OFF / Disable
   - **Domains:** Leave empty
   - **Ports:** Leave empty

5. **Environment Variables:**
   - Go to **Settings → Variables**
   - Copy all variables from your Web Service:
     - `WHOP_ACCESS_TOKEN`
     - `WHOP_SESSION` (if used)
     - `WHOP_ALERTS_URL`
     - `DRY_RUN=true`
     - `LIVE_TRADING=false`
     - `BROKER_MODE=TRADIER_ONLY`
     - Any other required variables

---

### Step 4: Deploy and Verify

1. Railway will auto-deploy the new service
2. Wait for deployment to complete
3. **Check the logs:**
   - Click on the service
   - Go to **"Logs"** tab
   - Look for: `Starting trading bot polling loop...`
   - Look for: `Fetching alerts...`
   - **Should NOT see:** `Starting gunicorn` or `Listening at: http://`

---

## How to Tell if It Worked

✅ **Success Indicators:**
- Start command stays as `python main.py` (doesn't revert)
- Logs show: `Starting trading bot polling loop...`
- Logs show: `Fetching alerts...` (repeating every 30 seconds)
- **NO** Gunicorn messages in logs

❌ **Failure Indicators:**
- Start command reverts to Gunicorn
- Logs show: `Starting gunicorn`
- Logs show: `Listening at: http://0.0.0.0:PORT`
- Logs show: `Failed to find attribute 'app'`

---

## If It Still Reverts to Gunicorn

If the new service **still** reverts to Gunicorn, it means:

1. **You didn't select "Background Worker" type** - Delete and recreate, ensuring you select Worker type
2. **Railway auto-detected it as web** - Check service settings for a "Service Type" option and change it to "Worker"
3. **There's a `PORT` environment variable** - Remove any `PORT` variable from this service's environment variables

---

## Alternative: Check Service Type in Settings

Some Railway interfaces allow you to change service type after creation:

1. Go to **Settings → General** or **Settings → Service**
2. Look for **"Service Type"** or **"Application Type"**
3. If you see **"Web Service"**, try changing it to **"Worker"** or **"Background Worker"**
4. Save and redeploy

**If this option doesn't exist or doesn't work, delete and recreate as described above.**

---

## Quick Checklist

- [ ] Deleted old misclassified service
- [ ] Created NEW service
- [ ] Selected "Background Worker" type (not Web Service)
- [ ] Set start command to `python main.py`
- [ ] Disabled Public Networking
- [ ] Copied all environment variables
- [ ] Verified logs show polling loop (not Gunicorn)
- [ ] Verified logs show `Fetching alerts...` messages

---

## Why This Happens

Railway classifies services at creation time:
- **Web Service** = Expects HTTP server (Gunicorn, Flask, etc.)
- **Background Worker** = Expects long-running process (Python script)

Once classified as "Web Service", Railway:
- Forces Gunicorn/HTTP assumptions
- Overrides start commands
- Ignores worker configurations

**The classification is effectively immutable** - that's why you must create a new service.

---

**Last Updated:** 2025-01-02  
**Status:** Ready for immediate implementation

