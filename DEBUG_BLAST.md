# Debugging Blast Not Working

## Current Status

- ✅ Code is simplified and uses only env vars
- ✅ All Twilio credentials are set in Railway
- ✅ A2P campaign is verified and compliant
- ❌ **No POST request to `/rep/blast` appears in logs**

## Hypothesis: Request Not Reaching Backend

The fact that **no POST request appears in logs** suggests:

1. **Frontend not sending request** - JavaScript error or network issue
2. **CORS blocking** - Request blocked before reaching backend
3. **Request failing silently** - Exception in dependency injection
4. **Route not registered** - FastAPI route not matching

## Debugging Steps

### Step 1: Test if POST requests work at all

Try the test endpoint:
```bash
curl -X POST https://rt4orgs-frats-production.up.railway.app/test/blast \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

If this works, POST requests can reach the backend.

### Step 2: Check browser console

Open browser DevTools → Console tab when clicking blast button. Look for:
- JavaScript errors
- Network errors
- CORS errors
- Failed fetch requests

### Step 3: Check Network tab

Open browser DevTools → Network tab:
- Filter by "rep/blast"
- Click blast button
- See if request appears
- Check request status (200, 401, 500, etc.)
- Check request/response headers

### Step 4: Verify backend URL

Check `ui/config.js` - ensure `BACKEND_URL` points to Railway:
```javascript
export const BACKEND_URL = "https://rt4orgs-frats-production.up.railway.app";
```

### Step 5: Test with curl

Try calling the endpoint directly:
```bash
curl -X POST https://rt4orgs-frats-production.up.railway.app/rep/blast \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"card_ids": ["person_alan_solis_elrod_sigchi_alpha"]}'
```

## What the Logs Will Show

After Railway redeploys, you should see:

1. **If request reaches middleware:**
   ```
   [MIDDLEWARE] 🚨 POST /rep/blast REQUEST DETECTED
   ```

2. **If request reaches endpoint:**
   ```
   [BLAST_ENDPOINT] 🚀 ENDPOINT CALLED
   ```

3. **If auth dependency fails:**
   ```
   [AUTH_DEPENDENCY] ❌ Exception in get_current_owner_or_rep
   ```

4. **If endpoint has exception:**
   ```
   [BLAST_ENDPOINT] ❌❌❌ UNHANDLED EXCEPTION IN ENDPOINT ❌❌❌
   ```

## Most Likely Issues

1. **Frontend JavaScript error** - Check browser console
2. **CORS issue** - Check Network tab for CORS errors
3. **Backend URL mismatch** - Verify config.js
4. **Auth token expired** - Check if token is still valid

## Next Steps

1. Wait for Railway to redeploy
2. Open browser DevTools (F12)
3. Go to Console tab
4. Click blast button
5. Check for errors in console
6. Go to Network tab
7. Look for POST request to /rep/blast
8. Share what you see
