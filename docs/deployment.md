# Deployment Guide

## Prerequisites

- Docker 24+ + Docker Compose v2
- Ollama running on host: https://ollama.ai
- Groq API key: https://console.groq.com
- GPU recommended for Ollama (CPU works but slow)

## Pre-deploy checklist

1. Generate strong `ADMIN_PASSWORD` (16+ chars)
2. Generate strong `JWT_SECRET_KEY` (32+ chars, base64) — used for JWT signing
3. Update `CORS_ORIGINS` to production domain
4. Set `APP_ENV=production`
5. Pull Ollama model: `ollama pull bge-m3`

## First-time deploy

```bash
# Clone
git clone <repo-url> chatbot-rag
cd chatbot-rag

# Create .env
cp .env.example .env
$EDITOR .env   # fill GROQ_API_KEY, ADMIN_PASSWORD

# Build + start
docker compose up --build -d

# Wait for healthy (all 6 services)
docker compose ps
docker compose logs -f backend | grep "Application startup"
```

## Health checks

```bash
# Liveness (always 200 if process alive)
curl http://localhost:8000/healthz/live

# Readiness (200 only when DB + Qdrant reachable)
curl http://localhost:8000/healthz/ready

# Full health
curl http://localhost:8000/health

# Prometheus metrics
curl http://localhost:8000/metrics
```

## Login + first user

Default admin seeded on startup from `ADMIN_USERNAME`/`ADMIN_PASSWORD` env.

```bash
# Get token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}'

# Use token
curl http://localhost:8000/api/v1/chat/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"apa itu SOP cuti?"}'
```

## Updating

```bash
git pull
docker compose up --build -d
# Worker picks up new code on restart (graceful — finishes current job first)
```

## Rollback

```bash
docker tag chatbot-backend:latest chatbot-backend:backup-$(date +%Y%m%d)
docker compose down
git checkout <previous-commit>
docker compose up --build -d
```

## Reverse proxy (nginx example)

```nginx
server {
    listen 80;
    server_name chatbot.example.com;
    client_max_body_size 60M;  # max upload + margin

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }

    location /metrics {
        allow 10.0.0.0/8;  # only internal scrapers
        deny all;
        proxy_pass http://localhost:8000;
    }
}
```

## Production hardening

1. **Change default password** — admin user seeded with `admin123` if `ADMIN_PASSWORD` not set
2. **Set `JWT_SECRET_KEY`** — used as HMAC secret for token signing. Minimum 32 bytes.
3. **Restrict CORS** — remove `localhost` from `CORS_ORIGINS`
4. **TLS** — terminate at reverse proxy, not in app
5. **Rate limiting** — adjust `RATE_LIMIT_*` for expected traffic
6. **Backups** — see backup-restore.md
7. **Monitoring** — scrape `/metrics` with Prometheus, alert on:
   - `http_requests_total{status=~"5.."}` rate
   - `http_request_duration_seconds` p95 > 8s
   - `chat_queries_total{outcome="abstain"}` rate spike
   - `answerability_abstains_total` rate spike

## Common issues

| Issue | Fix |
|---|---|
| "could not translate host name 'db'" | Docker compose not running. Start with `docker compose up -d` |
| Ollama connection refused | Ollama not running on host, or wrong `OLLAMA_BASE_URL` |
| 401 on all requests | Token expired (24h) or wrong JWT_SECRET_KEY. Re-login |
| 429 rate limit | Lower request rate, or raise `RATE_LIMIT_*` env vars |
| Upload fails silently | Check `MAX_FILE_SIZE_MB` and nginx `client_max_body_size` |
| Embedding slow | First time loads model into VRAM. Subsequent calls fast |
| 500 on chat query | Run `python backfill_access_level.py` if Qdrant has 0 hits |
| "supersecret" warning in logs | Set `JWT_SECRET_KEY` to 32+ char random value in `.env` |

## Log locations

```bash
# Backend (JSON logs to stdout)
docker compose logs backend -f

# Worker
docker compose logs worker -f

# Postgres
docker compose logs db -f | grep ERROR

# Frontend (Vite dev server)
docker compose logs frontend -f
```

## Access control matrix

| Role | Endpoints | Qdrant access |
|------|-----------|---------------|
| `viewer` | chat, feedback | `internal` only |
| `document_admin` | + upload/list/delete documents | `internal` + `restricted` |
| `system_admin` | + register users | all (incl. `confidential`) |
| `auditor` | list documents | all (read-only) |
