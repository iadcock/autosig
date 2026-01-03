# Railway Configuration Notes

## Why railway.toml Was Removed

The `railway.toml` file was causing Railway to auto-detect **all services** as Web Services, forcing Gunicorn on the Worker Service.

## Current Setup

**Services must be configured manually in Railway dashboard:**

### Web Service
- **Start Command:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web:app`
- Set this in Railway dashboard → Service → Settings → Deploy → Custom Start Command

### Worker Service  
- **Start Command:** `python main.py`
- Set this in Railway dashboard → Service → Settings → Deploy → Custom Start Command
- **Public Networking:** Disabled
- **No PORT variable**

## If You Need railway.toml Back

If you want to restore `railway.toml` for the Web Service only:

1. Create `railway.toml` with web service config
2. Configure Worker Service manually in Railway dashboard (it won't use railway.toml)
3. OR use Railway's service-specific configuration (if available)

## Alternative: Service-Specific Config

Railway may support service-specific config files in the future. For now, manual configuration in the dashboard is required.

