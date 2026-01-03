# AutoSig — Replay Data Extension Summary

## Task Completed

Extended local replay data past 2025-12-26 to enable replay mode to display signals dated after that date.

---

## Changes Made

### File Modified: `sample_alerts.txt`

**Location:** Repository root  
**Format:** Plain text alerts separated by double newlines (`\n\n\n`)

**Added 5 new alerts with dates after 2025-12-26:**

1. **AAPL bullish call debit spread** (1/19/2026 exp)
   - Entry signal with 1/19/2026 expiration
   - Unique content to avoid hash duplication

2. **AAPL trim position** (1/19/2026 exp)
   - Exit/trim signal for the same position
   - Demonstrates exit logic in replay

3. **SPY bear put debit spread** (1/5/2026 exp)
   - Entry signal with 1/5/2026 expiration
   - Different instrument (SPY) and strategy

4. **NVDA bullish call debit spread** (1/10/2026 exp)
   - Entry signal with 1/10/2026 expiration
   - Different symbol (NVDA)

5. **MSFT bear call credit spread** (1/12/2026 exp)
   - Entry signal with 1/12/2026 expiration
   - Different symbol (MSFT) and strategy type

---

## Replay File Format

The replay file (`sample_alerts.txt`) uses plain text format:
- Alerts separated by double newlines (`\n\n\n`)
- Each alert contains:
  - Strategy description
  - Expiration date
  - Legs (strikes, option types)
  - Limit price range
  - Position size

**Example format:**
```
STRATEGY_NAME

EXPIRATION_DATE exp

LEGS
Limit PRICE-RANGE debit/credit to open/close

SIZE% size
```

---

## Verification Steps

### 1. Restart Worker Service

After the file is updated, restart only the Worker Service in Railway:
- Railway Dashboard → Worker Service → Settings → Redeploy
- OR: Wait for next polling cycle (if file is already deployed)

### 2. Check Worker Logs

Expected log output:
```
Using local alerts file (USE_LOCAL_ALERTS=true)
Fetched 9 alerts from Whop
Processing cycle: 5 new alerts, 0 duplicates
Parsed N valid signals from 5 new alerts
```

**If logs show:**
- `0 new alerts, all duplicates` → Alerts were already processed (dedup state)
- `Processing cycle: X new alerts` → Success, new alerts detected

### 3. Verify UI Results

**Signal Feed (`/feed`):**
- Should show signals with dates after 2025-12-26
- Dates: 2026-01-05, 2026-01-10, 2026-01-12, 2026-01-19
- Certainty should default to (A) for auto-classified signals

**Signal Review (`/signal-review`):**
- Should show same signals as Feed
- Dates should be after 2025-12-26
- No UNCLASSIFIED states

### 4. Check Parsed Alerts

Verify `logs/alerts_parsed.jsonl` contains new entries:
- Timestamps after 2025-12-26
- Classification: "SIGNAL" or "NON_SIGNAL"
- Parsed signal data for valid signals

---

## Important Notes

### Deduplication

If alerts were already processed in a previous run, they will be marked as duplicates. To force re-processing:

1. **Option A:** Clear dedup state (not recommended - may reprocess all alerts)
2. **Option B:** Modify alert content slightly to generate new hash
3. **Option C:** Wait for natural dedup expiration (if implemented)

### Replay Mode Behavior

- **No live Whop calls:** System reads from `sample_alerts.txt` only
- **No broker connectivity:** All execution is paper/simulated
- **No execution changes:** Replay logic unchanged
- **Timestamps:** Alerts are processed with current time, not historical timestamps

### File Location

The replay file is:
- **Local:** `sample_alerts.txt` (repository root)
- **Railway:** Same file, deployed with code
- **Config:** `config.SAMPLE_ALERTS_FILE = "sample_alerts.txt"`

---

## Success Criteria

✅ **Replay file contains alerts dated after 12/26**  
✅ **Worker logs show new alerts processed**  
✅ **Parsed signals include dates after 12/26**  
✅ **Feed and Review display those signals**  
✅ **System remains in PAPER / REPLAY mode**

---

## Next Steps

1. **Commit and push** the updated `sample_alerts.txt`:
   ```bash
   git add sample_alerts.txt
   git commit -m "Extend replay data past 12/26 with 5 new alerts"
   git push origin main
   ```

2. **Restart Worker Service** in Railway (or wait for auto-deploy)

3. **Monitor logs** for new alert processing

4. **Verify UI** shows signals after 2025-12-26

---

**Last Updated:** 2025-01-02  
**Status:** Ready for deployment

