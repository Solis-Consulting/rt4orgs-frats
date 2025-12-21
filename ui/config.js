// Backend URL configuration
// Reads from window.BACKEND_URL (can be set via Vercel env var or inline script)
// Falls back to localhost for local development
// Falls back to Railway URL as final default

export const BACKEND_URL =
  window.BACKEND_URL ||
  (location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "https://rt4orgs-frats-production.up.railway.app");

// 🔥 CRITICAL: Log the resolved backend URL for debugging
console.log("🌐 [CONFIG] Backend URL resolved to:", BACKEND_URL);
console.log("🌐 [CONFIG] Current hostname:", location.hostname);
console.log("🌐 [CONFIG] Protocol:", location.protocol);

