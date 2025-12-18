# Blast Function Deep Analysis

## Flow Overview

1. **Frontend** (`ui/rep.html`):
   - User selects cards and clicks "Blast Selected Assigned Leads"
   - JavaScript sends `POST /rep/blast` with `{ card_ids: [...] }`

2. **Backend Endpoint** (`main.py` - `/rep/blast`):
   - Validates user authentication
   - Enforces assignment boundaries (reps can only blast assigned cards)
   - Validates Twilio configuration (Account SID, Auth Token, Messaging Service SID)
   - Calls `run_blast_for_cards()`

3. **Blast Orchestration** (`backend/blast.py` - `run_blast_for_cards`):
   - Fetches cards from database
   - Generates personalized messages using templates
   - For each card, calls `send_sms()`
   - Records conversations in database
   - Returns results

4. **SMS Sending** (`scripts/blast.py` - `send_sms`):
   - Creates Twilio Client with Account SID and Auth Token
   - Sends message via Messaging Service (no `from_` parameter)
   - Returns Twilio response with SID, status, etc.

## Critical Bug Fixed

**Issue**: Admin users were getting `None` for `rep_account_sid` and `rep_auth_token` because:
- `rep_user_id = None` for admin users
- The code only set credentials if `if rep_user_id:` was truthy
- This meant `None` values were passed to `run_blast_for_cards()`

**Fix**: Now explicitly sets system Account SID and Auth Token for **all users** (admin and rep):
```python
rep_account_sid = os.getenv("TWILIO_ACCOUNT_SID")  # Set for all users
rep_auth_token = os.getenv("TWILIO_AUTH_TOKEN")  # Set for all users
```

**Validation**: Added checks to ensure Account SID and Auth Token are set before proceeding.

## Configuration Requirements

All messages route through **(919) 443-6288** via Messaging Service. Required environment variables:

1. `TWILIO_ACCOUNT_SID` - Account SID (starts with `AC`)
2. `TWILIO_AUTH_TOKEN` - Auth Token
3. `TWILIO_MESSAGING_SERVICE_SID` - Messaging Service SID (starts with `MG`)

## Message Routing

- **All users** (admin and reps) use the **same system phone number** via Messaging Service
- **No `from_` parameter** - Messaging Service handles sender selection
- **Rep isolation** maintained via `card_assignments` table (reps only see their assigned cards)
- **Deterministic routing** - Messages from same rep go to same conversation thread

## Enhanced Logging

The system now logs:
- User authentication and role
- Card selection and authorization
- Twilio configuration validation
- Exact parameters sent to Twilio API
- Full Twilio API responses
- Message delivery status
- Error codes and messages

Look for these log prefixes:
- `[BLAST]` - Blast orchestration
- `[BLAST_RUN]` - High-level blast execution
- `[BLAST_SEND_ATTEMPT]` - Individual message send attempts
- `[SEND_SMS]` - Twilio API calls

## Testing

To test blast functionality:

1. **Verify Configuration** (check Railway startup logs):
   ```
   TWILIO_ACCOUNT_SID: ✅ SET
   TWILIO_AUTH_TOKEN: ✅ SET
   TWILIO_MESSAGING_SERVICE_SID: ✅ SET
   ```

2. **Select Cards** in rep dashboard
3. **Click Blast Button**
4. **Check Railway Logs** for:
   - `[BLAST]` entries showing card processing
   - `[SEND_SMS]` entries showing Twilio API calls
   - `[BLAST_SEND_ATTEMPT]` entries showing individual message status

5. **Check Response** - Should show:
   - Number of messages accepted by Twilio
   - Number skipped
   - Individual message statuses

## Common Issues

### Blast button doesn't work
- Check browser console for JavaScript errors
- Verify API token is set in frontend
- Check Railway logs for POST requests to `/rep/blast`

### Messages not sending
- Verify all three Twilio environment variables are set in Railway
- Check Railway logs for `[SEND_SMS]` entries
- Look for error messages in Twilio API responses
- Verify phone number (919) 443-6288 is in Messaging Service

### Admin can't blast
- **FIXED**: Admin users now explicitly get system Account SID and Auth Token
- Verify in logs: `[BLAST] User owner (role: admin) using system Account SID: AC...`

### Rep can't blast assigned cards
- Verify cards are assigned to rep in `card_assignments` table
- Check logs for authorization errors
- Verify rep API token is correct
