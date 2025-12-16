// Backend URL configuration
// Reads from window.BACKEND_URL (can be set via Vercel env var or inline script)
// Falls back to localhost for local development
// Falls back to Railway URL as final default

export const BACKEND_URL =
  window.BACKEND_URL ||
  (location.hostname === "localhost"
    ? "http://localhost:8000"
    : "https://rt4orgs-frats-production.up.railway.app");

