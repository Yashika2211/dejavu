# Deploying DejaVu

Two pieces: the **API** (FastAPI, long-lived Server-Sent Events, the simulator) on a container host, and the **war room** (Next.js) on Vercel. The API streams investigations for minutes, so it runs as a container, not as serverless functions.

## 1. API on Render (from this repo)

1. Open https://dashboard.render.com/blueprint/new?repo=https://github.com/Yashika2211/dejavu and connect the repo. Render reads [`render.yaml`](../render.yaml) and builds [`backend/Dockerfile`](../backend/Dockerfile).
2. When asked, paste `GROQ_API_KEY` and `HINDSIGHT_API_KEY`.
3. After the deploy, note the URL, e.g. `https://dejavu-api.onrender.com`. Check it: `curl https://dejavu-api.onrender.com/health`.

The live bank (`kestrel-ops-live`) lives in Hindsight Cloud, so the deployed API sees the same memory as local runs. App state (incidents, runs) is SQLite inside the container and resets on redeploy.

## 2. War room on Vercel

```
cd web
vercel login                     # once, in a terminal
vercel deploy --prod --yes \
  --build-env NEXT_PUBLIC_API_URL=https://dejavu-api.onrender.com
```

The API allows any `https://*.vercel.app` origin (`CORS_ORIGIN_REGEX`).

## 3. Everything locally with Docker

```
cp .env.example .env             # add both keys
docker compose up --build        # API on :8000, war room on :3000
```

## 4. Without Docker

```
make setup && make bank && make dev
```

## Before a demo

- `make health`: Groq and Hindsight reachable with your keys.
- Groq's free tier allows 1,000 requests a day and 8,000 tokens a minute; one investigation uses about 40-66K tokens and takes 7-10 minutes, a race twice that.
