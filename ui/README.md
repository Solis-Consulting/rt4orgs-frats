# UI Deployment

## ⚠️ IMPORTANT: Update Backend URL

Before deploying, you **must** update the backend URL in both HTML files:

1. **`index.html`** - Line ~47: Replace `YOUR-RAILWAY-DOMAIN` with your actual Railway domain
2. **`lead.html`** - Line ~30: Replace `YOUR-RAILWAY-DOMAIN` with your actual Railway domain

Example:
```javascript
const BACKEND = "https://rt4-backend.up.railway.app";
```

## Quick Deploy

```bash
cd ui
vercel
```

When prompted, select "Other" as the framework (static files).

## Testing Locally

1. Update BACKEND URL in both HTML files to `http://localhost:8000`
2. Start backend: `cd backend && uvicorn twilio_server:app --host 0.0.0.0 --port 8000`
3. Serve UI: `cd ui && python3 -m http.server 3000`
4. Open `http://localhost:3000`

