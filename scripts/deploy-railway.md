# Deploy to Railway

Deploy the Stock Investing Model (backend + web) to [Railway](https://railway.app).

## Prerequisites

- [Railway CLI](https://docs.railway.com/guides/cli) (optional, for CLI deploy)
- GitHub repo connected to Railway (recommended for auto-deploy)

---

## Redis: Not Required

**Redis is optional.** The app runs without it. When `REDIS_URL` is unset, the cache layer is a no-op and all features work. Redis only speeds up repeated fetches (backtest, price targets, fundamentals). For Railway deploy you can skip Redis to keep it simple.

---

## Ports: Use Railway’s PORT

Both services use `PORT` from the environment. Railway sets this automatically per service. The backend and web Dockerfiles use `${PORT:-8002}` and `${PORT:-3000}` as fallbacks only when `PORT` is not set (e.g. local runs).

---

## Required Config for Railway

Ensure these variables are set in Railway **Variables**:

| Service | Variable | Required | Description |
|---------|----------|----------|-------------|
| **Backend** | `PORT` | ✅ Set by Railway | Do not override. |
| **Backend** | `CORS_ORIGINS` | ✅ Yes | Comma-separated frontend URLs, e.g. `https://your-web-domain.up.railway.app` |
| **Web** | `PORT` | ✅ Set by Railway | Do not override. |
| **Web** | `BACKEND_API_URL` | ✅ Yes | Backend API base URL (e.g. `https://your-backend-domain.up.railway.app`) |

Optional:

| Service | Variable | Description |
|---------|----------|-------------|
| Backend | `REDIS_URL` | Optional. If set, enables caching. |
| Web | `NEXT_PUBLIC_API_URL` | Only if you need client-side direct API calls. Server-side rewrites use `BACKEND_API_URL`. |

---

## Option 1: Deploy via Railway Dashboard (Recommended)

### 1. Create a New Project

1. Go to [railway.app](https://railway.app) and sign in
2. **New Project** → **Deploy from GitHub repo**
3. Select your repo

### 2. Add Backend Service

1. **+ New** → **GitHub Repo** → select repo
2. **Settings** → **Root Directory**: `backend`
3. Railway auto-detects the Dockerfile
4. **Settings** → **Networking** → **Generate Domain** (e.g. `backend-production-xxxx.up.railway.app`)
5. **Variables** → Add:
   - `CORS_ORIGINS`: `https://your-web-domain.up.railway.app` (add after web is deployed)

### 3. Add Web Service

1. **+ New** → **GitHub Repo** → same repo
2. **Settings** → **Root Directory**: `web`
3. **Variables** → Add:
   - `BACKEND_API_URL`: `https://your-backend-domain.up.railway.app` (backend URL from step 2)
4. **Settings** → **Networking** → **Generate Domain**

### 4. Update CORS

After both are deployed, set the backend’s `CORS_ORIGINS` to include your web domain, e.g.:

```
https://stock-investing-model-web-production-xxxx.up.railway.app
```

### 5. Deploy

Both services use Railway’s generated `PORT`; no extra port config is needed.

---

## Option 2: Deploy with Railway CLI

```bash
npm i -g @railway/cli
railway login

# Backend
cd backend
railway init
# Add CORS_ORIGINS in dashboard
railway up

# Web (new terminal)
cd web
railway init --service web
# Add BACKEND_API_URL in dashboard
railway up
```

---

## railway.toml (per service)

Each service has a `railway.toml` in its root:

- `backend/railway.toml` – builder `DOCKERFILE`, healthcheck `/api/health`
- `web/railway.toml` – builder `DOCKERFILE`, healthcheck `/`

Config in these files overrides dashboard settings. Env vars (e.g. `CORS_ORIGINS`, `BACKEND_API_URL`) are still set in Railway **Variables**.

---

## Checklist Before Going Live

- [ ] Backend: `CORS_ORIGINS` includes web domain(s)
- [ ] Web: `BACKEND_API_URL` points to backend URL (no trailing slash)
- [ ] Both services have generated domains (Railway sets `PORT` automatically)

---

## First Deploy Note

The first dashboard load runs full analysis (signals, portfolio, opportunities) and may take 1–2 minutes. Subsequent requests are faster.
