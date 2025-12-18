# Set David's API Token

## Quick Fix (via API)

Use the admin endpoint to set David's token:

```bash
curl -X POST "https://rt4orgs-frats-production.up.railway.app/admin/users/david_lee/set-token" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer Da3XWjpeCVwA5o3f8Vmk3Jh0xuPsVA9r7GCZFdyjPto" \
  -d '{"api_token": "012QosXKsYDECWtyR869YuyMdXLKHjkUXRfDFgf4lgw"}'
```

## Or via Admin UI

1. Go to Admin Dashboard
2. Find user "david_lee" in the users table
3. Use "Set Token" action (if available) or "Regenerate Token" then update manually

## Verify Token Works

After setting, test with:

```bash
curl -X GET "https://rt4orgs-frats-production.up.railway.app/rep/cards" \
  -H "Authorization: Bearer 012QosXKsYDECWtyR869YuyMdXLKHjkUXRfDFgf4lgw"
```

Should return 200 OK with cards list.

## Enhanced Logging

The auth system now logs:
- Token preview and length
- Hashed token value
- Why validation fails (if it does)

Check Railway logs after attempting to use the token to see detailed auth debugging.
