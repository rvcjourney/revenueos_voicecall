"""
app/config.py — Pydantic Settings for MOTMVoice.
All values come from environment variables (or .env in development).
Secrets are masked in __repr__ to prevent accidental log leakage.
"""
from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to this file (backend/.env), regardless of CWD
_ENV_FILE = Path(__file__).parent.parent / ".env"

_SECRET_FIELDS = frozenset({
    "SECRET_KEY", "AGENT_WEBHOOK_SECRET", "LIVEKIT_API_SECRET",
    "MINIO_SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "VOBIZ_PASSWORD",
    "VOBIZ_AUTH_TOKEN", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "GROQ_API_KEY",
    "SUPABASE_SERVICE_ROLE_KEY", "FERNET_KEY",
    "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
    "OFFSITE_BACKUP_SECRET_KEY", "STORAGE_SSE_C_KEY_B64",
    "REVENUEOS_API_KEY",
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "MOTMVoice"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    DOCS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"
    # Public HTTPS origin this backend is reachable at — used to build callback
    # URLs for external services (e.g. Vobiz's recording webhook) that need a
    # real internet-facing address, not the internal docker-network one.
    PUBLIC_BASE_URL: str = ""

    # ── Security ───────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(..., min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12
    AGENT_WEBHOOK_SECRET: str = Field(..., min_length=32)
    # Fernet key for at-rest encryption of SIP/Vobiz credentials (app/core/crypto.py).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = Field(..., min_length=32)

    # ── Database ───────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(...)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False
    DB_SSL_REQUIRED: bool = True
    DB_USE_PGBOUNCER: bool = False

    # ── Supabase ───────────────────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Temporary escape hatch: set to False to let /login through without a
    # verified email (OTP still gets requested/sent everywhere as normal,
    # this only stops login from blocking on it). Meant to be flipped back to
    # True as soon as Supabase's email sending is reliable again — see
    # app/api/auth.py's login() for the one place this is read.
    REQUIRE_EMAIL_VERIFICATION: bool = True

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PREFIX: str = "motm"

    # ── CORS ───────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]

    # ── LiveKit ────────────────────────────────────────────────────────────────
    LIVEKIT_URL: str = Field(...)
    LIVEKIT_API_KEY: str = Field(...)
    LIVEKIT_API_SECRET: str = Field(...)
    # Worker identity dispatches are routed to (must match agent/config.py's own
    # LIVEKIT_AGENT_NAME on whichever process actually runs agent.py). Overridden to
    # a distinct value (e.g. "voice-call-agent-dev") in local/dev .env files so a
    # developer's local agent process and the production VPS agent -- both able to
    # register against the same LiveKit Cloud project -- never receive each other's
    # dispatches; LiveKit round-robins across every worker sharing one agent_name.
    LIVEKIT_AGENT_NAME: str = "voice-call-agent"
    # This LiveKit Cloud project's SIP hostname (Settings -> SIP in the LiveKit
    # dashboard) -- same for every org, used as the destination Vobiz routes
    # inbound calls to. LiveKit itself disambiguates which org/number a call
    # belongs to via each SIPInboundTrunkInfo's own `numbers` list.
    LIVEKIT_SIP_HOSTNAME: str = ""

    # ── SIP / Vobiz ───────────────────────────────────────────────────────────
    DEFAULT_SIP_TRUNK_ID: str = ""
    DEFAULT_SIP_CALLER_ID: str = ""
    DEFAULT_SIP_TRUNK_ID_2: str = ""
    DEFAULT_SIP_CALLER_ID_2: str = ""
    VOBIZ_SIP_DOMAIN: str = ""
    VOBIZ_USERNAME: str = ""
    VOBIZ_PASSWORD: str = ""
    VOBIZ_AUTH_ID: str = ""       # Vobiz API Auth ID for CDR/Recording fetch
    VOBIZ_AUTH_TOKEN: str = ""    # Vobiz API Auth Token

    # ── Deepgram STT ──────────────────────────────────────────────────────────
    DEEPGRAM_API_KEY: str = Field(...)

    # ── ElevenLabs TTS ────────────────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = Field(...)
    ELEVENLABS_VOICE_ID: str = "9BWtsMINqrJLrRacOk9x"
    ELEVENLABS_MODEL_ID: str = "eleven_turbo_v2_5"

    # ── Groq LLM ──────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(...)
    # Unused elsewhere in the backend today (agent.py's own outcome classifier
    # hardcodes its model directly) -- kept in sync with Groq's currently
    # supported models anyway so wiring these up later doesn't inherit a
    # deprecated default. Both llama-3.1-8b-instant and llama-3.1-70b-versatile
    # were deprecated by Groq in 2026.
    GROQ_MODEL: str = "qwen/qwen3.6-27b"
    GROQ_SUMMARY_MODEL: str = "openai/gpt-oss-120b"

    # ── OpenAI (Prime Calling research + prompt writing) ─────────────────────
    # Optional: without a key, Prime Calling uses Groq (no live web search).
    OPENAI_API_KEY: str = ""
    # Cheapest current OpenAI model with web search + structured outputs; the
    # stronger (pricier) options are gpt-5.6-terra, gpt-5.6-sol, gpt-6-astra.
    PRIME_OPENAI_MODEL: str = "gpt-5.6-luna"
    # Output tokens are cheap on luna, so think harder for better sales reasoning
    PRIME_REASONING_EFFORT: Literal["none", "low", "medium", "high", "xhigh", "max"] = "high"
    # Paid OpenAI web search (~$0.01 per search) for each contact's company:
    #   auto   = only when we couldn't read their website ourselves (cheapest useful)
    #   always = every contact (also finds news, expansions, awards)
    #   never  = website text + CSV only
    PRIME_WEB_SEARCH: Literal["auto", "always", "never"] = "auto"

    # ── Payments (Razorpay) ───────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    # Secret configured on the Razorpay Dashboard webhook (Settings -> Webhooks),
    # used to verify X-Razorpay-Signature on incoming webhook requests.
    RAZORPAY_WEBHOOK_SECRET: str = ""
    # Days past Subscription.current_period_end an org keeps access without a
    # renewal charge landing -- our own backstop (app/workers/tasks/billing.py:
    # expire_lapsed_subscriptions), independent of Razorpay's own retry/dunning
    # cadence and of whether its webhook/reconcile ever tells us the charge
    # failed. Past this, org.is_active flips False regardless of what Razorpay's
    # subscription.status still says; a later subscription.charged webhook
    # reactivates it and pushes current_period_end forward again either way.
    BILLING_GRACE_PERIOD_DAYS: int = 3
    # Platform-wide switch for credits and payments. False = no org is ever
    # blocked for credits or an unpaid subscription: new sign-ups start active,
    # has_credits_remaining() (app/core/credits.py) always allows the call, and
    # the Razorpay reconcile/expiry beat tasks do nothing. Call minutes are
    # still counted. A superadmin suspending an org (is_active) still applies.
    BILLING_ENABLED: bool = True

    # ── RevenueOS Brain integration (app/api/revenueos.py) ────────────────────
    # Shared secret Brain sends in the X-RevenueOS-Key header. Blank = every
    # RevenueOS route answers 503.
    REVENUEOS_API_KEY: str = ""
    # Lets the key create accounts, numbers, agents and campaigns (as drafts).
    REVENUEOS_LAUNCH_ENABLED: bool = False
    # Lets a launch with auto_start=true begin dialling real people with no
    # person reviewing it. Needs REVENUEOS_LAUNCH_ENABLED as well.
    REVENUEOS_AUTO_START_ENABLED: bool = False
    # Most contacts accepted in one launch request.
    REVENUEOS_MAX_CONTACTS: int = 500

    # ── Storage ───────────────────────────────────────────────────────────────
    STORAGE_BACKEND: Literal["minio", "s3"] = "minio"

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"

    BUCKET_RECORDINGS: str = "motm-recordings"
    BUCKET_EXPORTS: str = "motm-exports"
    BUCKET_TRANSCRIPTS: str = "motm-transcripts"
    BUCKET_BACKUPS: str = "motm-backups"
    BUCKET_VOICE_CONSENT: str = "motm-voice-consent"
    BUCKET_INVOICES: str = "motm-invoices"
    EXPORT_URL_EXPIRY_SECONDS: int = 600

    # Server-side encryption (SSE-C) for every object this backend stores.
    # Blank disables it (objects upload unencrypted, today's behavior) so this
    # is safe to deploy before it's configured -- set it to actually turn
    # encryption at rest on. Every bucket is read back exclusively through
    # StorageBackend.download() (never a presigned URL handed to a browser --
    # see StorageBackend.presigned_url()'s docstring), so a single
    # server-managed key works cleanly with no MinIO-side KMS/KES setup
    # required. Must be a base64-encoded 32-byte key, generated with:
    #   python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    STORAGE_SSE_C_KEY_B64: str = ""

    # How long a call's recording (recording_url) and transcript (CallTranscript
    # row) are kept before app/workers/tasks/retention.py's daily beat task
    # hard-deletes them. The Call row itself (outcome, duration, summary, etc.)
    # is never touched -- see app/models/call.py's Call docstring. Founder
    # decision (2026-08-23 readiness audit, blocker 3): 45 days, hard delete.
    CALL_DATA_RETENTION_DAYS: int = 45

    # ── Offsite database backups ─────────────────────────────────────────────
    # BUCKET_BACKUPS above (via StorageBackend) lives on the SAME disk as every
    # other bucket -- when STORAGE_BACKEND=minio (the production default, see
    # docker-compose.yml) that's this VPS's own disk, so it protects against a
    # bad migration or accidental delete, but not against the VPS/disk itself
    # failing. These settings point pg_dump's upload at a genuinely separate,
    # off-VPS S3-compatible bucket (AWS S3 / Backblaze B2 / Cloudflare R2 /
    # Wasabi all work) -- see run_database_backup in
    # app/workers/tasks/backup.py. Left blank, offsite upload is a no-op
    # (local-only backup still runs) so this is safe to deploy before it's
    # configured, but real disaster-recovery is not in place until it is.
    OFFSITE_BACKUP_ENDPOINT_URL: str = ""   # e.g. https://s3.us-west-004.backblazeb2.com — blank disables offsite backup
    OFFSITE_BACKUP_ACCESS_KEY: str = ""
    OFFSITE_BACKUP_SECRET_KEY: str = ""
    OFFSITE_BACKUP_BUCKET: str = ""
    OFFSITE_BACKUP_REGION: str = "us-east-1"
    BACKUP_RETENTION_DAYS: int = 14

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Monitoring ────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Internal service communication ────────────────────────────────────────
    BACKEND_INTERNAL_URL: str = "http://api:8000"
    AGENT_TEMPLATE_CACHE_TTL: int = 60

    # ── Concurrency ────────────────────────────────────────────────────────────
    # Queue-then-reject: max seconds a contact waits for a plan-based org-level
    # call slot before being marked QUEUE_TIMEOUT (see app/core/concurrency.py).
    CONCURRENCY_MAX_WAIT_SECONDS: int = 600

    # ── Outbound dialing ───────────────────────────────────────────────────────
    # How long LiveKit keeps an outbound call ringing before cancelling it.
    # LiveKit's own default is 30 s, which is too short for Indian mobile
    # networks: post-dial delay (time before the handset even starts ringing)
    # is often 10–25 s, so 30 s calls were cancelled before or just as the
    # phone rang (seen in Vobiz logs as "Cancelled" after exactly 30 s).
    SIP_RINGING_TIMEOUT_SECONDS: int = 55

    @field_validator("STORAGE_SSE_C_KEY_B64")
    @classmethod
    def _validate_sse_key(cls, v: str) -> str:
        if not v:
            return v
        import base64
        try:
            raw = base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError("STORAGE_SSE_C_KEY_B64 must be valid base64") from exc
        if len(raw) != 32:
            raise ValueError(
                f"STORAGE_SSE_C_KEY_B64 must decode to exactly 32 bytes for AES-256 (got {len(raw)})"
            )
        return v

    @field_validator("REVENUEOS_API_KEY")
    @classmethod
    def _validate_revenueos_key(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("REVENUEOS_API_KEY must be at least 32 characters (or blank to disable)")
        return v

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
            if self.DOCS_ENABLED:
                raise ValueError("DOCS_ENABLED must be False in production")
            if not self.SENTRY_DSN:
                warnings.warn(
                    "SENTRY_DSN is not configured in production — errors will not be tracked",
                    stacklevel=2,
                )
        return self

    def __repr__(self) -> str:
        parts = []
        for name in self.model_fields:
            value = getattr(self, name)
            if name in _SECRET_FIELDS and value:
                value = "***"
            parts.append(f"{name}={value!r}")
        return f"Settings({', '.join(parts)})"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
