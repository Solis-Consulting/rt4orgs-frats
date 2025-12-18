# Revert to Direct Phone Number Sending (Fix 30007 Filtering)

## Problem

Twilio error `30007 - Message filtered` occurs when:
- All messages use Messaging Service
- All messages come from one system number
- Message content is uniform
- This triggers Twilio's spam/bulk filtering heuristics

## Solution

Reverted to sending **directly from phone number** using `from_` parameter instead of `messaging_service_sid`.

## Changes Made

### 1. `scripts/blast.py` - `send_sms()`
- ✅ Changed from `messaging_service_sid` to `from_` parameter
- ✅ Requires `TWILIO_PHONE_NUMBER` instead of `TWILIO_MESSAGING_SERVICE_SID`
- ✅ Sends directly from phone number

### 2. `backend/rep_messaging.py` - `send_rep_message()`
- ✅ Changed from `messaging_service_sid` to `from_` parameter
- ✅ Requires `TWILIO_PHONE_NUMBER` instead of `TWILIO_MESSAGING_SERVICE_SID`
- ✅ Sends directly from phone number

### 3. `main.py` - Validation
- ✅ Startup validation checks `TWILIO_PHONE_NUMBER` instead of `TWILIO_MESSAGING_SERVICE_SID`
- ✅ Blast endpoint validates phone number before sending

## Railway Environment Variables

**Required:**
- `TWILIO_ACCOUNT_SID` ✅ (already set)
- `TWILIO_AUTH_TOKEN` ✅ (already set)
- `TWILIO_PHONE_NUMBER` ⚠️ **NEW - MUST BE SET** (format: `+19194436288`)

**No longer required:**
- `TWILIO_MESSAGING_SERVICE_SID` (can be removed, not used)

## How to Update Railway

1. Go to Railway → Your Project → Variables
2. **Add** `TWILIO_PHONE_NUMBER` = `+19194436288` (or your actual phone number)
3. **Optional:** Remove `TWILIO_MESSAGING_SERVICE_SID` (not needed anymore)
4. Railway will auto-redeploy

## Verification

After redeploy, check Railway logs for:
```
🔍 TWILIO CONFIGURATION CHECK
TWILIO_PHONE_NUMBER: ✅ SET
  Value: +19194436288
  Note: Sending directly from phone number (avoids Messaging Service filtering)
```

## Why This Works

- **Direct phone sending** = Twilio allows it (not filtered)
- **Messaging Service** = Triggers bulk/spam heuristics (filtered)
- **Old architecture** = Direct phone sending ✅
- **New architecture** = Messaging Service only ❌
- **Reverted architecture** = Direct phone sending ✅

## Status

✅ **Code reverted** to direct phone number sending
✅ **No Messaging Service** in send path
✅ **Should avoid 30007 filtering**
