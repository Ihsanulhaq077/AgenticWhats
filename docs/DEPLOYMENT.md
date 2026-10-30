# Deployment Guide

Three ways to deploy, from easiest demo to production.

---

## Option 1 — Single VPS with Docker Compose (recommended start)

Works on any cheap VPS (Hetzner ~€4/mo, DigitalOcean $6/mo, AWS Lightsail, Contabo).

### 1. Prepare the server (Ubuntu 22.04+)

```bash
ssh root@YOUR_SERVER_IP
apt update && apt install -y docker.io docker-compose-v2 git
# create a non-root user
adduser deploy && usermod -aG docker deploy
```

### 2. Upload the project

```bash
# from your Windows machine (Git Bash):
cd "/d/whatsapps agents works"
rsync -av --exclude .venv --exclude node_modules --exclude .next \
  --exclude backend/agenticwhats.db --exclude .env \
  ./ deploy@YOUR_SERVER_IP:/srv/agenticwhats/
```

Or push to a private GitHub repo and `git clone` on the server.

### 3. Configure production `.env` on the server

```bash
cd /srv/agenticwhats
cp .env.example .env && nano .env
```

Change these for production:

```env
APP_ENV=production
JWT_SECRET=<long random string: python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql+psycopg2://agentic:STRONG_PASSWORD@db:5432/agenticwhats
CORS_ORIGINS=https://yourdomain.com
LLM_PROVIDER=openai            # optional: full agentic LLM path
LLM_API_KEY=sk-...
WHATSAPP_ACCESS_TOKEN=...      # for live sending
WHATSAPP_APP_SECRET=...        # enables webhook signature verification
WHATSAPP_VERIFY_TOKEN=<your own secret string>
```

### 4. Start

```bash
docker compose up -d --build
# seed the demo tenant (optional):
docker compose exec backend python scripts/seed_demo.py
curl http://localhost:8000/health
```

### 5. HTTPS domain (required for the WhatsApp webhook)

Meta only calls webhooks over **public HTTPS**. Simplest is Caddy (automatic Let's Encrypt):

```bash
apt install -y caddy
nano /etc/caddy/Caddyfile
```

```caddy
yourdomain.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:3000
    }
}
```

```bash
systemctl reload caddy
```

Point your domain's DNS A-record at the server IP first. Done: `https://yourdomain.com` is the dashboard, `https://yourdomain.com/api/webhooks/whatsapp` is the webhook.

> Alternatively proxy in front of both apps with one Nginx site the same way.

---

## Option 2 — Managed platforms (no server to maintain)

| Piece | Where | Notes |
|---|---|---|
| Frontend | Vercel (free tier) | Root dir `frontend/`; set `BACKEND_URL=https://api.yourdomain.com` |
| Backend | Railway / Render / Fly.io | Root dir `backend/`, start cmd `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Database | Neon / Supabase / Railway Postgres | Set `DATABASE_URL` to their connection string |
| Redis | Upstash (only needed when you add Celery) | Optional at this stage |

Steps: push the repo to GitHub → connect each service in the platform dashboard → set the env vars from `.env.example` → deploy. Point the frontend `BACKEND_URL` at the backend URL and add the frontend domain to `CORS_ORIGINS`.

---

## Option 3 — Render/Railway blueprint (single commit)

Both platforms detect `docker-compose`-less services via their dashboards; Option 2 is the manual version of this.

---

## Go live with WhatsApp (after the app is deployed)

1. **developers.facebook.com** → Create App → add the **WhatsApp** product.
2. WhatsApp → API Setup: copy the **Phone Number ID** and generate a **permanent access token** (via a System User in Business Settings).
3. In your dashboard: **Settings → WhatsApp connection** → enter the Phone Number ID → Connect.
4. In Meta App → WhatsApp → Configuration:
   - Webhook URL: `https://yourdomain.com/api/webhooks/whatsapp`
   - Verify token: the value of `WHATSAPP_VERIFY_TOKEN` from your server `.env`
   - Subscribe to the **messages** webhook field.
   - Paste the App Secret into `WHATSAPP_APP_SECRET` on the server and `docker compose up -d` again (turns on HMAC signature checks).
5. Send a WhatsApp message to your business number → watch it appear in **Conversations**.

> Test numbers can only message up to 5 verified recipient numbers — add your own phone as a recipient for testing, or complete Meta business verification for production.

---

## Production checklist

- [ ] `APP_ENV=production`, strong `JWT_SECRET`, Postgres password
- [ ] HTTPS enabled (Caddy/Nginx) — Meta webhooks require it
- [ ] `WHATSAPP_APP_SECRET` set → webhook forgery protection active
- [ ] `LLM_PROVIDER=openai` + key (optional but recommended for production quality)
- [ ] `EMBEDDING_PROVIDER=openai` (local-hash embeddings are keyword-level only)
- [ ] Set up **database backups** (e.g. `docker compose exec db pg_dump ...` on a cron, or managed-DB automated backups)
- [ ] Database migrations: the app auto-creates tables on startup in dev; before real production data, initialize Alembic (`alembic init alembic` in `backend/`, autogenerate the first revision) so schema changes are versioned
- [ ] Log rotation / error tracking (e.g. Sentry) and uptime monitoring on `/health`
- [ ] Replace the synthetic demo tenant with real business data **only with the business owner's permission**
