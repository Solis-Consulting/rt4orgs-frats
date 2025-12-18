# Twilio Messaging Service Setup

## Required Environment Variables in Railway

The following environment variables **MUST** be set in Railway for blast functionality to work:

1. **TWILIO_ACCOUNT_SID** - Your Twilio Account SID (starts with `AC`)
2. **TWILIO_AUTH_TOKEN** - Your Twilio Auth Token
3. **TWILIO_MESSAGING_SERVICE_SID** - Your Messaging Service SID (starts with `MG`)

## System Phone Number

All messages are sent via the system phone number **(919) 443-6288** through the Messaging Service.

This phone number must be:
- Added to your Messaging Service in Twilio Console
- The Messaging Service must have "Sticky Sender" enabled (recommended)

## How to Find Your Messaging Service SID

1. Go to Twilio Console → Messaging → Services
2. Find "Low Volume Mixed A2P Messaging Service" (or your Messaging Service name)
3. Click on it to view details
4. Copy the **Service SID** (starts with `MG`)
5. Add it to Railway as `TWILIO_MESSAGING_SERVICE_SID`

## Verification

After setting the environment variables, check Railway logs on startup. You should see:

```
🔍 TWILIO CONFIGURATION CHECK
============================================================
TWILIO_ACCOUNT_SID: ✅ SET
TWILIO_AUTH_TOKEN: ✅ SET
TWILIO_MESSAGING_SERVICE_SID: ✅ SET
  Value: MG...
  System phone: (919) 443-6288 (configured in Messaging Service)
============================================================
```

If you see `❌ NOT SET` for any of these, blast will fail.

## Troubleshooting

### Blast fails with "TWILIO_MESSAGING_SERVICE_SID must be set"
- Go to Railway → Variables tab
- Add `TWILIO_MESSAGING_SERVICE_SID` with your Messaging Service SID (starts with `MG`)
- Redeploy or restart the service

### Messages not delivering
- Check Railway logs for detailed Twilio API responses
- Verify phone number (919) 443-6288 is in the Messaging Service
- Check A2P 10DLC registration status in Twilio Console
- Verify Messaging Service has "Sticky Sender" enabled

### Enhanced Logging
The system now logs:
- Exact parameters sent to Twilio
- Full Twilio API responses
- Message delivery status
- Error codes and messages

Check Railway logs for `[SEND_SMS]` and `[BLAST_SEND_ATTEMPT]` entries.
