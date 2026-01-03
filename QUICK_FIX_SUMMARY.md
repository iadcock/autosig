# Railway Worker Misclassification — Quick Fix Summary

## The Problem

Railway is forcing Gunicorn on your Worker Service because it was created as a "Web Service" type. The start command keeps reverting to Gunicorn.

## The Solution

**Delete the misclassified service and create a NEW one as "Background Worker" type.**

## Quick Steps

1. **Delete** the old "Worker Service" that keeps reverting to Gunicorn
2. **Create** a new service in Railway
3. **Select "Background Worker"** (NOT "Web Service") when prompted
4. **Set start command:** `python main.py`
5. **Disable** Public Networking
6. **Copy** all environment variables from Web Service
7. **Deploy**

## Verification

✅ Worker logs show: `Starting trading bot polling loop...`  
✅ Worker logs show: `Fetching alerts...` (repeating)  
✅ **NO** Gunicorn messages in worker logs  
✅ New alerts appear in `alerts_raw.jsonl` (timestamp > 2025-12-26)

## Full Guide

See **[RAILWAY_WORKER_FIX.md](./RAILWAY_WORKER_FIX.md)** for detailed step-by-step instructions.

---

**Key Rule:** Railway service type is immutable. If it was born web, replace it.

