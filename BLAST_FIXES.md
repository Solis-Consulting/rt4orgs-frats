# Blast Functionality - Best Fixes

## Root Cause Analysis

The blast functionality regressed because:
1. **Complex parameter passing** - Multiple layers of account_sid/auth_token handling
2. **Admin vs Rep logic split** - Different code paths that can fail silently
3. **Missing early validation** - Errors happen deep in the stack
4. **No request verification** - Can't tell if requests reach the endpoint

## Best Fixes (Priority Order)

### 1. **Simplify Parameter Passing** (CRITICAL)
**Problem**: Account SID and Auth Token are passed through multiple layers, can be None
**Fix**: Always use environment variables directly in `send_sms()`, don't pass them through

**Current Flow**:
```
rep_blast() → extracts env vars → run_blast_for_cards() → send_sms(auth_token, account_sid)
```

**Better Flow**:
```
rep_blast() → run_blast_for_cards() → send_sms() [uses env vars directly]
```

**Why**: Eliminates parameter passing bugs, simpler code, fewer failure points

### 2. **Add Request Verification** (CRITICAL)
**Problem**: Can't tell if requests reach the endpoint
**Fix**: Add immediate logging at the very start of the endpoint

**Implementation**: Already added in recent commits - verify it's working

### 3. **Simplify Admin/Rep Logic** (HIGH)
**Problem**: Different code paths for admin vs rep can fail differently
**Fix**: Unify the logic - both use the same system credentials

**Current**:
```python
if rep_user_id:
    rep_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    rep_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
```

**Better**:
```python
# Always use system credentials for all users
system_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
system_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
# Validate immediately
if not system_account_sid or not system_auth_token:
    return error
```

### 4. **Early Validation** (HIGH)
**Problem**: Validation happens deep in the stack
**Fix**: Validate all requirements at the start of the endpoint

**Check**:
- ✅ Messaging Service SID is set
- ✅ Account SID is set
- ✅ Auth Token is set
- ✅ card_ids is not empty
- ✅ User is authenticated

### 5. **Remove Optional Parameters** (MEDIUM)
**Problem**: `auth_token` and `account_sid` are optional in `run_blast_for_cards()`, causing confusion
**Fix**: Remove these parameters, always use env vars in `send_sms()`

### 6. **Better Error Messages** (MEDIUM)
**Problem**: Errors are generic or hidden
**Fix**: Return specific error messages at each validation step

## Recommended Implementation

### Step 1: Simplify `send_sms()` to always use env vars
```python
def send_sms(to_number: str, body: str) -> Dict[str, Any]:
    """Send SMS via Twilio. Always uses environment variables."""
    # Get from env vars directly - no parameters
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
    
    # Validate immediately
    if not account_sid:
        raise ValueError("TWILIO_ACCOUNT_SID not set")
    if not auth_token:
        raise ValueError("TWILIO_AUTH_TOKEN not set")
    if not messaging_service_sid:
        raise ValueError("TWILIO_MESSAGING_SERVICE_SID not set")
    
    # Rest of function...
```

### Step 2: Simplify `run_blast_for_cards()` signature
```python
def run_blast_for_cards(
    conn: Any,
    card_ids: List[str],
    limit: Optional[int],
    owner: str,
    source: str,
    rep_user_id: Optional[str] = None,  # Only for conversation tracking
) -> Dict[str, Any]:
    """Run blast. Uses system Twilio credentials from env vars."""
    # No auth_token or account_sid parameters
    # send_sms() will use env vars directly
```

### Step 3: Simplify `rep_blast()` endpoint
```python
@app.post("/rep/blast")
async def rep_blast(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_owner_or_rep)
):
    """Blast cards. Uses system Twilio credentials."""
    
    # IMMEDIATE VALIDATION
    import os
    if not os.getenv("TWILIO_ACCOUNT_SID"):
        return {"ok": False, "error": "TWILIO_ACCOUNT_SID not configured"}
    if not os.getenv("TWILIO_AUTH_TOKEN"):
        return {"ok": False, "error": "TWILIO_AUTH_TOKEN not configured"}
    if not os.getenv("TWILIO_MESSAGING_SERVICE_SID"):
        return {"ok": False, "error": "TWILIO_MESSAGING_SERVICE_SID not configured"}
    
    # Extract and validate card_ids
    card_ids = payload.get("card_ids")
    if not card_ids or not isinstance(card_ids, list) or len(card_ids) == 0:
        return {"ok": False, "error": "card_ids must be a non-empty array"}
    
    # Enforce assignment boundaries (existing logic)
    # ...
    
    # Call run_blast_for_cards (no auth params)
    result = run_blast_for_cards(
        conn=conn,
        card_ids=card_ids,
        limit=None,
        owner=current_user["id"],
        source="owner_ui" if current_user.get("role") == "admin" else "rep_ui",
        rep_user_id=None if current_user.get("role") == "admin" else current_user["id"],
    )
    
    return result
```

## Testing Checklist

After implementing fixes:
1. ✅ Check Railway logs for `[BLAST_ENDPOINT] 🚀 ENDPOINT CALLED`
2. ✅ Verify all three Twilio env vars are set
3. ✅ Test with admin user
4. ✅ Test with rep user
5. ✅ Check for `[SEND_SMS]` entries in logs
6. ✅ Verify messages appear in Twilio console

## Why These Fixes Work

1. **Simpler = Fewer Bugs**: Removing parameter passing eliminates a whole class of bugs
2. **Early Validation**: Fail fast with clear error messages
3. **Single Source of Truth**: Environment variables are the only source for Twilio credentials
4. **Easier Debugging**: Clear error messages at each step
5. **Less Code**: Fewer lines = fewer places for bugs to hide
