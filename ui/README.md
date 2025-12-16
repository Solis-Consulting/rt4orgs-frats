# UI Deployment

## Backend URL Configuration

The UI uses a centralized configuration system via `config.js` that automatically detects the backend URL.

### Production (Vercel)

**Option 1: Edit config.js directly (Recommended for static sites)**
- Edit `ui/config.js` and replace `"https://your-app.up.railway.app"` with your actual Railway URL
- Commit and push to trigger a new Vercel deployment

**Option 2: Use Vercel Environment Variables (if using serverless functions)**
- Go to Vercel Dashboard → Your Project → Settings → Environment Variables
- Add: `BACKEND_URL` = `https://your-app.up.railway.app`
- If using serverless functions, you can inject this via a function that sets `window.BACKEND_URL`
- For pure static sites, Option 1 is simpler

### Local Development

No configuration needed! The UI automatically detects `localhost` and uses `http://localhost:8000` as the backend URL.

### Manual Override

If you need to override the backend URL, you can edit `config.js` directly:

```javascript
export const BACKEND_URL = "https://your-custom-backend-url.com";
```

## Quick Deploy

```bash
cd ui
vercel
```

When prompted, select "Other" as the framework (static files).

## Testing Locally

1. Start backend: `cd .. && uvicorn main:app --host 0.0.0.0 --port 8000`
2. Serve UI: `cd ui && python3 -m http.server 3000`
3. Open `http://localhost:3000`

The UI will automatically connect to `http://localhost:8000` (no configuration needed).

## Files Using Backend URL

All UI files now use the centralized `config.js`:
- `index.html` - Lead console and cards view
- `lead.html` - Individual lead detail
- `upload.html` - Card upload interface
- `card.html` - Card detail view
- `blast.html` - Outbound blast tool
- `webhook.html` - Webhook configuration

## Troubleshooting

### UI can't connect to backend

1. **Check Vercel Environment Variables:**
   - Verify `BACKEND_URL` is set correctly
   - Ensure it's set for the correct environment (Production/Preview)

2. **Check Backend CORS:**
   - The backend should have CORS enabled (already configured in `main.py`)
   - Verify the backend is accessible at the URL you set

3. **Check Browser Console:**
   - Open browser DevTools → Console
   - Look for CORS errors or network errors
   - Verify the backend URL being used

### Local development not working

- Ensure backend is running on `http://localhost:8000`
- Check that `config.js` exists and is accessible
- Verify no browser extensions are blocking requests
