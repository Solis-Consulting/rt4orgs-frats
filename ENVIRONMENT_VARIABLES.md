# Required Environment Variables

## Required Environment Variables

Your Railway deployment must have these environment variables configured:

1. **`TWILIO_ACCOUNT_SID`**
   - Format: Starts with `AC` (34 characters)
   - Used for: Twilio API authentication
   - Required: ✅ Yes
   - Set in: Railway → Variables

2. **`TWILIO_AUTH_TOKEN`**
   - Format: 32 character string
   - Used for: Twilio API authentication
   - Required: ✅ Yes
   - Set in: Railway → Variables

3. **`TWILIO_MESSAGING_SERVICE_SID`**
   - Format: Starts with `MG` (34 characters)
   - Used for: Routing all messages through Messaging Service
   - Required: ✅ Yes
   - Set in: Railway → Variables

4. **`DATABASE_URL`**
   - Format: PostgreSQL connection string
   - Used for: Database connection
   - Required: ✅ Yes
   - Set in: Railway → Variables (or auto-configured if using Railway Postgres)

## How Code Uses These Variables

### `send_sms()` in `scripts/blast.py`
- ✅ Uses `os.getenv("TWILIO_ACCOUNT_SID")`
- ✅ Uses `os.getenv("TWILIO_AUTH_TOKEN")`
- ✅ Uses `os.getenv("TWILIO_MESSAGING_SERVICE_SID")`
- ❌ No hardcoded values
- ❌ No fallback to config files
- ❌ No parameter overrides

### `send_rep_message()` in `backend/rep_messaging.py`
- ✅ Uses `os.getenv("TWILIO_MESSAGING_SERVICE_SID")`
- ✅ Uses system Account SID and Auth Token from env vars
- ❌ No per-rep phone numbers
- ❌ No per-rep credentials

### `rep_blast()` endpoint in `main.py`
- ✅ Validates all three Twilio env vars at startup
- ✅ Validates env vars before each blast
- ✅ Returns clear error if any missing

## Verification

All code paths now:
1. ✅ Read directly from environment variables
2. ✅ Validate immediately with clear errors
3. ✅ No hardcoded credentials
4. ✅ No config file fallbacks
5. ✅ No parameter passing of credentials

## No Additional Variables Needed

The current four variables are sufficient. The code does not require:
- ❌ `TWILIO_PHONE_NUMBER` (not used - Messaging Service handles sender)
- ❌ Per-rep credentials (all use system credentials)
- ❌ Any other Twilio variables

## Architecture

```
Environment Variables (Railway)
    ↓
os.getenv() calls in code
    ↓
Twilio API (using system credentials)
    ↓
Messaging Service (configured via TWILIO_MESSAGING_SERVICE_SID)
    ↓
System Phone Number (configured in Messaging Service)
    ↓
Recipients
```

## Status

✅ **Code is correctly configured** to use only these environment variables.
✅ **No additional variables needed** for current functionality.
✅ **All credential access goes through `os.getenv()`** - no other sources.
