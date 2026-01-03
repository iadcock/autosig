# Railway Worker Service — Force Fix (When Auto-Detection Fails)

## The Persistent Problem

Even after creating a "new" service, Railway keeps reverting to Gunicorn. This happens because Railway auto-detects service type based on:
- Repository contents (sees `web.py`, `dashboard.py`, Flask)
- Start command patterns
- File structure

**Railway doesn't always show an explicit "Background Worker" option** - it infers the type.

---

## Solution: Create "Empty Service" First

Railway's auto-detection is less aggressive when you start with an **Empty Service** instead of connecting GitHub directly.

### Step-by-Step: Empty Service Method

#### Step 1: Delete Current Misclassified Service

1. Railway Dashboard → Your Project
2. Find the service that reverts to Gunicorn
3. Settings → Danger Zone → Delete Service
4. Confirm deletion

---

#### Step 2: Create Empty Service (CRITICAL)

1. In Railway project, click **"+ New"** or **"Add Service"**
2. **DO NOT** select "GitHub Repo" immediately
3. Look for and select **"Empty Service"** or **"Blank Service"**
   - If you don't see this option, look for **"Deploy from GitHub"** but choose **"Empty"** or **"Custom"** first
4. Name it: `autosig-worker` (or any name)

**Why this works:** Starting with an empty service prevents Railway from auto-detecting web service patterns.

---

#### Step 3: Connect GitHub Repository (After Empty Service Created)

1. In the **new empty service**, go to **Settings**
2. Find **"Source"** or **"Service Source"** section
3. Click **"Connect Repository"** or **"Deploy from GitHub"**
4. Select your GitHub repository
5. Select branch: `main` (or your default branch)

**Important:** The service is already created as "empty" at this point, so Railway won't re-classify it.

---

#### Step 4: Configure Build & Deploy

1. **Settings → Deploy**

2. **Custom Build Command (if needed):**
   - Leave empty OR
   - `pip install -r requirements.txt` (if Railway doesn't auto-detect)

3. **Custom Start Command (CRITICAL):**
   ```
   python main.py
   ```
   - Clear any Gunicorn command
   - Save immediately

4. **Settings → Networking:**
   - **Public Networking:** ❌ **OFF** / **Disabled**
   - **Domains:** Leave empty
   - **Ports:** Leave empty

---

#### Step 5: Remove PORT Environment Variable

Railway might inject a `PORT` variable that triggers web service behavior:

1. **Settings → Variables**
2. Look for `PORT` variable
3. If it exists, **DELETE it** (or set it to empty)
4. Railway will try to add it back - you may need to remove it again after deployment

---

#### Step 6: Add Required Environment Variables

1. **Settings → Variables**
2. Add all required variables:
   - `WHOP_ACCESS_TOKEN`
   - `WHOP_SESSION` (if used)
   - `WHOP_ALERTS_URL`
   - `DRY_RUN=true`
   - `LIVE_TRADING=false`
   - `BROKER_MODE=TRADIER_ONLY`
   - Any other required variables

**Important:** Do NOT add `PORT` variable.

---

#### Step 7: Deploy and Verify

1. Railway will auto-deploy
2. Wait for deployment
3. **Check Logs:**
   - Should see: `Starting trading bot polling loop...`
   - Should see: `Fetching alerts...`
   - Should NOT see: `Starting gunicorn` or `Listening at: http://`

---

## Alternative: Use Railway CLI to Force Service Type

If the UI method doesn't work, you can use Railway CLI:

### Install Railway CLI

```bash
npm i -g @railway/cli
railway login
```

### Create Service via CLI

```bash
# Navigate to your project
cd /path/to/Expert-Python-Engineer

# Link to Railway project
railway link

# Create a new service (this might give more control)
railway service create autosig-worker

# Set start command
railway variables set START_COMMAND="python main.py"

# Deploy
railway up
```

**Note:** Railway CLI might give you more control over service type classification.

---

## Nuclear Option: Override with railway.toml

Create a service-specific `railway.toml` that Railway can't override:

### Option 1: Service-Specific Config

Railway supports service-specific configuration. However, `railway.toml` at the root applies to all services.

### Option 2: Remove railway.toml from Worker Service

1. The current `railway.toml` has:
   ```toml
   [deploy]
   startCommand = "gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app"
   ```

2. This applies to **all services** in the project.

3. **Solution:** Create a service-specific override OR remove `railway.toml` and configure each service manually in Railway dashboard.

**To remove railway.toml temporarily:**
```bash
git mv railway.toml railway.toml.backup
git commit -m "Temporarily remove railway.toml to prevent auto-detection"
git push
```

Then configure each service manually in Railway dashboard.

---

## Most Likely Solution: Remove railway.toml

The `railway.toml` file is likely causing Railway to auto-detect web service behavior for ALL services.

### Try This:

1. **Rename railway.toml:**
   ```bash
   git mv railway.toml railway.toml.web-only
   git commit -m "Rename railway.toml to prevent worker service auto-detection"
   git push
   ```

2. **Configure services manually in Railway:**
   - **Web Service:** Set start command in Railway dashboard: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app`
   - **Worker Service:** Set start command in Railway dashboard: `python main.py`

3. **Verify:**
   - Worker service should no longer revert to Gunicorn
   - Web service should still work (configured manually)

---

## Verification Checklist

After implementing the fix:

- [ ] Created service as "Empty Service" first (not GitHub Repo directly)
- [ ] Connected GitHub repository after service creation
- [ ] Set start command to `python main.py` in Railway dashboard
- [ ] Disabled Public Networking
- [ ] Removed `PORT` environment variable (if present)
- [ ] Removed or renamed `railway.toml` (if causing issues)
- [ ] Worker logs show: `Starting trading bot polling loop...`
- [ ] Worker logs show: `Fetching alerts...` (repeating)
- [ ] **NO** Gunicorn messages in worker logs
- [ ] Start command stays as `python main.py` (doesn't revert)

---

## If Still Not Working

If Railway **still** reverts to Gunicorn after all these steps:

1. **Check Railway Service Settings:**
   - Look for a hidden "Service Type" or "Application Type" setting
   - Some Railway interfaces have this buried in Advanced Settings

2. **Contact Railway Support:**
   - This might be a Railway platform limitation
   - Ask: "How do I create a background worker service that doesn't auto-detect as web service?"

3. **Workaround: Use a Different Start Script:**
   - Create `worker.py` that just imports and runs `main.py`
   - Set start command to: `python worker.py`
   - Sometimes different file names help Railway's detection

4. **Check Railway Documentation:**
   - Railway's docs might have changed
   - Look for "Background Workers" or "Worker Services" documentation

---

## Why This Happens

Railway's auto-detection algorithm:
1. Scans repository for common web frameworks (Flask, Django, etc.)
2. Sees `web.py`, `dashboard.py`, `requirements.txt` with Flask/Gunicorn
3. Assumes all services are web services
4. Forces Gunicorn/HTTP behavior
5. Overrides manual start commands

**The `railway.toml` file makes this worse** because it explicitly defines a web service start command that Railway applies globally.

---

**Last Updated:** 2025-01-02  
**Status:** Advanced troubleshooting guide

