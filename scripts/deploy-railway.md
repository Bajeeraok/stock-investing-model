# Deploy to Railway

Deploy the Stock Investing Model (backend + web) to [Railway](https://railway.app).

## Prerequisites

- [Railway CLI](https://docs.railway.com/guides/cli) (optional, for CLI deploy)
- GitHub repo connected to Railway (recommended for auto-deploy)

## Option 1: Deploy via Railway Dashboard (Recommended)

### 1. Create a New Project

1. Go to [railway.app](https://railway.app) and sign in
2. **New Project** → **Deploy from GitHub repo**
3. Select `Bajeeraok/stock-investing-model`

### 2. Add Backend Service

1. In your project, click **+ New** → **GitHub Repo** (or **Empty Service** then connect)
2. Select the same repo
3. **Settings** → **Root Directory**: set to `backend`
4. Railway auto-detects the Dockerfile
5. **Settings** → **Networking** → **Generate Domain** (e.g. `backend-production-xxxx.up.railway.app`)
6. **Variables** → Add:
   - `PORT` (Railway sets this automatically)
   - `CORS_ORIGINS`: `https://your-web-domain.up.railway.app` (add after web is deployed)

### 3. Add Web Service

1. **+ New** → **GitHub Repo** → same repo
2. **Settings** → **Root Directory**: set to `web`
3. **Variables** → Add (at build time):
   - `BACKEND_API_URL`: `https://your-backend-domain.up.railway.app` (use the backend URL from step 2)
4. **Settings** → **Networking** → **Generate Domain**

### 4. Update CORS

After both are deployed, update the backend's `CORS_ORIGINS` variable to include your web domain, e.g.:
```
https://stock-investing-model-web-production-xxxx.up.railway.app
```

### 5. Update Frontend API URL

Set `NEXT_PUBLIC_API_URL` on the web service to your backend URL so the client fetches directly (or rely on server-side rewrites—ensure `BACKEND_API_URL` is set at build time).

---

## Option 2: Deploy with Railway CLI

```bash
# Install CLI
npm i -g @railway/cli

# Login
railway login

# Backend
cd backend
railway init
railway up

# Web (new terminal)
cd web
railway init --service web
# Set BACKEND_API_URL in Railway dashboard before deploy
railway up
```

---

## Environment Variables

| Service | Variable | Description |
|---------|----------|-------------|
| Backend | `PORT` | Set by Railway |
| Backend | `CORS_ORIGINS` | Comma-separated frontend URLs |
| Web | `BACKEND_API_URL` | Backend API URL (build & runtime) |
| Web | `NEXT_PUBLIC_API_URL` | Optional: backend URL for client-side fetch |

---

## First Deploy Note

The first dashboard load runs full analysis (signals, portfolio, opportunities) and may take 1–2 minutes. Subsequent requests are faster.
