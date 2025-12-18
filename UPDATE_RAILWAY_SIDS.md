# Update Railway Environment Variables

## Current Legacy SIDs (from Railway)

These are the **legacy** SIDs currently configured in Railway (check Railway Variables tab to see actual values):

- `TWILIO_ACCOUNT_SID`: `AC...` (starts with AC, 34 characters)
- `TWILIO_AUTH_TOKEN`: `...` (32 characters)
- `TWILIO_MESSAGING_SERVICE_SID`: `MG...` (starts with MG, 34 characters)

## Steps to Update

### 1. Get Your Correct SIDs

**From Twilio Console:**
1. Go to https://console.twilio.com/
2. **Account SID**: Dashboard → Account Info (starts with `AC`)
3. **Auth Token**: Dashboard → Account Info → "Auth Token" (click to reveal)
4. **Messaging Service SID**: Messaging → Services → Select your service → SID (starts with `MG`)

**OR from your local terminal (if you have them set locally):**
```bash
echo $TWILIO_ACCOUNT_SID
echo $TWILIO_AUTH_TOKEN
echo $TWILIO_MESSAGING_SERVICE_SID
```

### 2. Update Railway Environment Variables

1. Go to Railway: https://railway.app
2. Select your project: `rt4orgs-frats-production`
3. Click on your service
4. Go to **Variables** tab
5. For each variable, click **Edit** and update:

   **Update `TWILIO_ACCOUNT_SID`:**
   - Check current value in Railway Variables tab
   - Replace with: `YOUR_CORRECT_ACCOUNT_SID` (starts with AC, 34 chars)

   **Update `TWILIO_AUTH_TOKEN`:**
   - Check current value in Railway Variables tab
   - Replace with: `YOUR_CORRECT_AUTH_TOKEN` (32 characters)

   **Update `TWILIO_MESSAGING_SERVICE_SID`:**
   - Check current value in Railway Variables tab
   - Replace with: `YOUR_CORRECT_MESSAGING_SERVICE_SID` (starts with MG, 34 chars)

6. **Save** each variable (Railway will auto-redeploy)

### 3. Verify Update

After Railway redeploys, check the **Deploy Logs** for:

```
🔍 TWILIO CONFIGURATION CHECK
============================================================
TWILIO_ACCOUNT_SID: ✅ SET
  Value: YOUR_NEW_SID... (length: 34)
TWILIO_AUTH_TOKEN: ✅ SET
  Value: YOUR_NEW_TOKEN... (length: 32)
TWILIO_MESSAGING_SERVICE_SID: ✅ SET
  Value: YOUR_NEW_MESSAGING_SID
  Length: 34
  System phone: (919) 443-6288 (configured in Messaging Service)
============================================================
```

### 4. Test Blast

After updating, test a blast:
- The new SIDs should appear in Twilio Console
- Messages should use the new Messaging Service
- Status should be `sent` or `delivered` (not `accepted`/`queued`)

## Important Notes

- ✅ **Code already uses env vars** - no code changes needed
- ✅ **Railway auto-redeploys** when you update variables
- ⚠️ **Wait for redeploy** before testing (check Deploy Logs)
- ⚠️ **Verify Messaging Service** has phone number (919) 443-6288 configured

## Troubleshooting

**If messages still show legacy SID:**
- Check Railway Deploy Logs to confirm new values loaded
- Verify Messaging Service SID matches Twilio Console
- Check Twilio Console → Messaging → Services → Your Service → Phone Numbers

**If blast fails:**
- Check Railway logs for env var validation errors
- Verify all three variables are set correctly
- Ensure Messaging Service has phone number configured
