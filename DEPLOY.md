# Deployment Guide

## Backend Deployment (Railway)

### 1. Push to GitHub
```bash
git add .
git commit -m "Unified FastAPI backend + CRM UI"
git push origin main
```

### 2. Deploy on Railway

1. Go to [Railway](https://railway.app) and create a new project
2. Select "Deploy from GitHub" → choose `rt4orgs-frats`
3. In the service settings:
   - **Root Directory**: `backend`
   - **Start Command**: `uvicorn twilio_server:app --host 0.0.0.0 --port $PORT`
   - Railway will auto-detect Python and install from `requirements.txt`

4. Once deployed, you'll get a URL like:
   ```
   https://rt4-backend.up.railway.app
   ```

5. **Update UI files**: Replace `YOUR-RAILWAY-DOMAIN` in:
   - `ui/index.html` (line with `const BACKEND = ...`)
   - `ui/lead.html` (line with `const BACKEND = ...`)

   Replace with your actual Railway domain (e.g., `rt4-backend.up.railway.app`)

6. **Set Twilio Webhook**:
   - Go to Twilio Console → Phone Numbers → Your number
   - Set webhook URL to: `https://YOUR-RAILWAY-DOMAIN.up.railway.app/twilio`
   - Method: POST

### 3. Verify Backend

- Open `https://YOUR-RAILWAY-DOMAIN.up.railway.app/all` → should return JSON
- Open `https://YOUR-RAILWAY-DOMAIN.up.railway.app/lead/TestName` → should return lead or error

---

## UI Deployment (Vercel)

### 1. Install Vercel CLI (if not installed)
```bash
npm i -g vercel
```

### 2. Deploy UI
```bash
cd ui
vercel
```

When prompted:
- **Framework**: Select "Other" (static files)
- **Root Directory**: `ui` (or just `.` if already in ui/)
- Vercel will deploy and give you a URL like:
  ```
  https://rt4-console.vercel.app
  ```

### 3. Verify UI

- Open the Vercel URL in your browser
- Should show the lead console pulling data from Railway backend
- If you see "Error loading leads", check that the BACKEND URL in the HTML files matches your Railway domain

---

## Local Testing

### Test Backend Locally
```bash
cd backend
uvicorn twilio_server:app --host 0.0.0.0 --port 8000
```

Then visit:
- `http://localhost:8000/all` → JSON with all leads
- `http://localhost:8000/lead/TestName` → specific lead

### Test UI Locally
```bash
cd ui
python3 -m http.server 3000
```

Then visit `http://localhost:3000` (update BACKEND URL in HTML to `http://localhost:8000` for local testing)

---

## Environment Variables (if needed)

If you need to set environment variables in Railway:
- Go to Railway project → Variables tab
- Add any needed vars (Twilio credentials, etc.)

The backend will read from environment variables or use defaults from `config.py`.

---

## Troubleshooting

### Backend not responding
- Check Railway logs: Railway dashboard → Service → Logs
- Verify `requirements.txt` has all dependencies
- Check that port is set to `$PORT` (Railway auto-assigns)

### UI can't connect to backend
- Verify BACKEND URL in `ui/index.html` and `ui/lead.html` matches Railway domain
- Check CORS is enabled (it is in the FastAPI middleware)
- Check browser console for errors

### Twilio webhook not working
- Verify webhook URL in Twilio console matches Railway domain
- Check Railway logs for incoming requests
- Test with: `curl -X POST https://YOUR-RAILWAY-DOMAIN.up.railway.app/twilio -d "From=+1234567890&Body=test"`

