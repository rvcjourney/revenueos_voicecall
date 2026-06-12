# MOTMVoice — AI Voice Call Agent Platform

> Production-ready outbound AI voice agent platform. Upload a contact list, launch a campaign, and your AI agent calls every number — speaking naturally, handling silence, detecting voicemail, and logging every outcome in real time.


---

## What It Does

MOTMVoice connects a real phone number to a conversational AI pipeline:

```
Inbound/Outbound Phone Call (SIP/PSTN)
        │
        ▼
  LiveKit Room (WebRTC)
        │
   ┌────┴────────────────────────────┐
   │         Voice Agent             │
   │  Deepgram STT  →  Groq LLM     │
   │  ElevenLabs / Cartesia TTS  ←  │
   └─────────────────────────────────┘
        │
        ▼
  FastAPI Backend  →  Supabase PostgreSQL
        │
  Celery Workers   →  Redis Job Queue
        │
  MinIO / S3       →  Recordings & Exports
        │
        ▼
  TanStack React Dashboard
```

A team member uploads a CSV of phone numbers, picks an AI agent with a custom sales prompt, and clicks **Launch**. Celery dispatches up to 10 concurrent calls. Each call is transcribed, summarised, and outcome-tagged (Interested / Not Interested / Callback / No Answer). Results export to CSV in one click.

---

## Key Features

**Voice Agent**
- Hinglish / multilingual conversation using Groq Llama 3.3 (70B)
- Sub-200ms turn latency via chunked TTS streaming
- Silence detection — probes customer after 12 s of silence, hangs up after 2 unanswered probes
- Voicemail detection — regex-based, hangs up instantly on voicemail greeting
- IVR / bot detection — hangs up instantly on automated phone trees
- Maximum call duration guard (10 minutes)

**Campaign Engine**
- Bulk contact import (CSV / Excel via pandas)
- Concurrent batch calling — up to 10 simultaneous calls per campaign
- DNC (Do Not Call) list enforcement
- Live progress: Dialing / Completed / Failed / Interested counts
- Graceful pause / resume without losing progress
- Per-contact outcome tracking and per-call transcript storage

**Backend & Infrastructure**
- JWT auth with refresh tokens, org-scoped multi-tenancy
- Role-based access: Admin full access, Members request agent access
- Sentry error tracking + Prometheus metrics + structlog structured logging
- Celery Beat for scheduled tasks
- MinIO / AWS S3 for recordings, exports, transcripts
- Webhook callbacks always return HTTP 200 (prevents Vobiz retry storms)
- All raw exception messages sanitised before reaching the client

**Frontend Dashboard**
- React 19 + TanStack Start (SSR-capable)
- Live campaign stats with Recharts charts
- Call detail drawer: transcript, recording player, extracted data
- Admin panel: user management, agent access approvals, creation requests
- AI-powered prompt optimizer (Groq → structured system prompt)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          Docker Compose                          │
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ frontend │   │   api    │   │  worker  │   │    agent     │  │
│  │ :6001    │   │ :7000    │   │ (Celery) │   │ (LiveKit)    │  │
│  │ TanStack │   │ FastAPI  │   │ 10 conc. │   │ Deepgram STT │  │
│  │ React 19 │   │ Gunicorn │   │          │   │ Groq LLM     │  │
│  └──────────┘   └──────────┘   └──────────┘   │ ElevenLabs   │  │
│                      │               │         │ TTS          │  │
│                      └───────────────┘         └──────────────┘  │
│                              │                                   │
│          ┌───────────────────┼──────────────┐                   │
│          │                   │              │                   │
│     ┌────┴─────┐       ┌─────┴────┐   ┌────┴────┐             │
│     │  redis   │       │  minio   │   │  beat   │             │
│     │ :6379    │       │ :9000    │   │(cron)   │             │
│     │ Broker   │       │ S3-compat│   └─────────┘             │
│     └──────────┘       └──────────┘                           │
│                                                                  │
│   Database: Supabase Cloud PostgreSQL (external)                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice pipeline | LiveKit · Deepgram STT · Groq Llama 3.3 · ElevenLabs / Cartesia TTS · Silero VAD |
| Telephony | Vobiz SIP / PSTN · LiveKit SIP trunks |
| Backend API | FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic 2 |
| Task queue | Celery 5 · Redis 7 · Celery Beat |
| Database | Supabase PostgreSQL (cloud-managed) |
| File storage | MinIO (self-hosted) or AWS S3 |
| Frontend | React 19 · TanStack Start · TanStack Router · TanStack Query |
| UI components | Radix UI · Tailwind CSS 4 · Recharts · React Hook Form + Zod |
| Observability | Sentry · Prometheus · structlog |
| Deployment | Docker Compose · Gunicorn + Uvicorn |

---

## Prerequisites

- Docker & Docker Compose
- A [LiveKit Cloud](https://cloud.livekit.io) project (free tier works)
- A [Deepgram](https://console.deepgram.com) account ($200 free credit)
- A [Groq](https://console.groq.com) account (free tier)
- An [ElevenLabs](https://elevenlabs.io) account (or Cartesia)
- A [Vobiz](https://vobiz.ai) SIP account with a DID (phone number)
- A [Supabase](https://supabase.com) project for PostgreSQL

---

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd "My AI Voice Call Agent"
```

### 2. Configure the agent

```bash
cp agent/.env.example agent/.env
```

Edit `agent/.env`:

| Variable | Description |
|---|---|
| `LIVEKIT_URL` | `wss://your-project.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `DEEPGRAM_API_KEY` | Deepgram API key (STT) |
| `ELEVENLABS_API_KEY` | ElevenLabs API key (TTS) |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice ID |
| `GROQ_API_KEY` | Groq API key (LLM) |
| `GROQ_MODEL` | e.g. `llama-3.3-70b-versatile` |
| `SIP_TRUNK_ID` | LiveKit SIP trunk ID (`ST_…`) |
| `SIP_TRUNK_NUMBER` | Your DID e.g. `+91XXXXXXXXXX` |
| `OUTBOUND_SIP_URI` | e.g. `your_number@sip.vobiz.ai` |
| `VOBIZ_SIP_DOMAIN` | e.g. `xxxxxxxx.sip.vobiz.ai` |
| `VOBIZ_USERNAME` / `VOBIZ_PASSWORD` | Vobiz SIP credentials |
| `BACKEND_INTERNAL_URL` | `http://api:8000` (inside Docker) |
| `AGENT_WEBHOOK_SECRET` | 32-char random string — must match backend |

### 3. Configure the backend

```bash
cp backend/.env.example backend/.env
```

Key variables in `backend/.env`:

| Variable | Description |
|---|---|
| `SECRET_KEY` | 32-char random string for JWT signing |
| `AGENT_WEBHOOK_SECRET` | Same value as agent `.env` |
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit credentials |
| `DEFAULT_SIP_TRUNK_ID` | Same trunk ID as agent |
| `VOBIZ_AUTH_ID` / `VOBIZ_AUTH_TOKEN` | Vobiz REST API credentials |
| `DEEPGRAM_API_KEY` | Deepgram key |
| `ELEVENLABS_API_KEY` | ElevenLabs key |
| `GROQ_API_KEY` | Groq key |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO credentials |
| `SENTRY_DSN` | (Optional) Sentry project DSN |
| `CORS_ORIGINS` | e.g. `["http://localhost:6001","https://yourdomain.com"]` |

### 4. Run database migrations

```bash
docker compose run --rm api alembic upgrade head
```

### 5. Start all services

```bash
docker compose up -d --build
```

Services started:

| Service | URL | Purpose |
|---|---|---|
| Frontend | http://localhost:6001 | Web dashboard |
| API | http://localhost:7000 | REST API (also /docs for Swagger) |
| Redis | localhost:6379 | Job queue & cache |
| MinIO | http://localhost:9000 | File storage UI |
| Worker | — | Campaign execution |
| Agent | — | Voice call handler |
| Beat | — | Scheduled tasks |

### 6. Create your first admin account

Register at `http://localhost:6001/register` or POST to `http://localhost:7000/api/auth/register`.

---

## Project Structure

```
.
├── agent/                      # LiveKit voice agent (Python)
│   ├── agent.py                # Voice pipeline: STT → LLM → TTS
│   └── config.py               # Prompts, models, voice settings
│
├── backend/                    # FastAPI REST API + Celery workers
│   ├── app/
│   │   ├── api/                # Route handlers
│   │   │   ├── auth.py         # Login, registration, JWT
│   │   │   ├── agents.py       # Agent CRUD, access requests, prompt optimizer
│   │   │   ├── campaigns.py    # Campaign management, CSV import, launch
│   │   │   ├── calls.py        # Call history, transcripts, recordings
│   │   │   ├── analytics.py    # Dashboard statistics
│   │   │   ├── webhooks.py     # Vobiz recording & hangup callbacks
│   │   │   └── admin.py        # Admin panel
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response types
│   │   ├── workers/
│   │   │   └── tasks/
│   │   │       └── campaign.py # Celery task: batch calling engine
│   │   └── main.py             # App factory, middleware, exception handlers
│   └── alembic/                # Database migrations
│
├── frontend/motmvoice-main/    # React 19 + TanStack Start dashboard
│   └── src/
│       ├── routes/             # Page routes
│       └── components/         # Reusable UI components
│
└── docker-compose.yml          # Production deployment
```

---

## Configuring the Voice Agent

Edit `agent/config.py` to change the agent's personality and behaviour:

| Setting | What it controls |
|---|---|
| `AGENT_SYSTEM_PROMPT` | Agent personality, sales script, language |
| `AGENT_WELCOME_MESSAGE` | First thing the agent says when the call connects |
| `GROQ_MODEL` | LLM model (`llama-3.3-70b-versatile` for best quality) |
| `ELEVENLABS_VOICE_ID` | Voice character |
| `ELEVENLABS_MODEL_ID` | TTS model (`eleven_flash_v2_5` for lowest latency) |

### ElevenLabs voice recommendations

| Voice ID | Character |
|---|---|
| `9BWtsMINqrJLrRacOk9x` | Aria — warm, professional female |
| `EXAVITQu4vr4xnSDxMaL` | Bella — friendly female |
| `pNInz6obpgDQGcFmaJgB` | Adam — clear male |
| `6h2Hja4LgQR8wIIv3XXW` | Custom — configure your own |

---

## Smart Agent Behaviours

### Silence handling
After 12 seconds of silence the agent probes with "Sir, kya aap sun rahe hain?" — after 2 unanswered probes (~28 seconds total) the call ends automatically.

### Voicemail detection
If the STT transcription contains phrases like "please leave a message", "after the beep", or "mailbox full", the agent hangs up immediately without speaking.

### IVR / bot detection
If the STT transcription contains phrases like "press 1 for", "all agents are busy", or "automated message", the agent hangs up immediately.

### Maximum duration guard
Calls are hard-capped at 10 minutes to prevent runaway billing.

---

## API Reference

The full interactive API docs are available at `http://localhost:7000/docs` when `DOCS_ENABLED=true`.

**Core endpoints:**

```
POST   /api/auth/register              Register new organisation
POST   /api/auth/login                 Get access + refresh tokens
GET    /api/agents                     List AI agents
POST   /api/agents                     Create agent (admin)
POST   /api/agents/{id}/optimize-prompt  AI-generate system prompt from raw notes
POST   /api/campaigns                  Create campaign
POST   /api/campaigns/{id}/contacts    Upload contacts CSV/Excel
POST   /api/campaigns/{id}/launch      Start calling
POST   /api/campaigns/{id}/pause       Pause mid-campaign
GET    /api/campaigns/{id}/contacts    Live contact status
GET    /api/calls                      Call history
GET    /api/calls/{id}                 Full detail + transcript
GET    /api/calls/{id}/recording       Stream call recording (proxied)
GET    /api/analytics/dashboard        Aggregated stats
POST   /api/webhooks/vobiz/recording   Vobiz recording callback (internal)
POST   /api/webhooks/vobiz/hangup      Vobiz hangup callback (internal)
```

---

## Deploying Updates

On your VPS, after pushing to `main`:

```bash
git pull origin main
docker compose up -d --build api worker agent frontend
docker compose logs -f agent worker
```

Run migrations if models changed:

```bash
docker compose run --rm api alembic upgrade head
```

---

## Troubleshooting

**Agent doesn't pick up calls**
- Verify `SIP_TRUNK_ID` matches the trunk registered in LiveKit
- Check `docker compose logs agent` for connection errors

**Calls stuck in DIALING**
- This means the Celery worker crashed mid-finalization. The system will auto-recover the contact to FAILED status. Check `docker compose logs worker`.

**Campaign shows RUNNING forever**
- The dispatcher task crashed. Check `docker compose logs worker` — the campaign will be marked FAILED automatically.

**Recording not appearing**
- Vobiz sends the recording webhook a few minutes after call end. Use the **Fetch Recording** button on the call detail page to manually retry.

**No audio / microphone issues (browser test)**
- Allow microphone permissions when the browser prompts
- Browser must be on HTTPS or `localhost`

**Database connection errors**
- Ensure `DATABASE_URL` in `backend/.env` points to your Supabase project
- Supabase free tier pauses after 7 days of inactivity — unpause in the Supabase dashboard

---

## License

Private — all rights reserved.
