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
    "SUPABASE_SERVICE_ROLE_KEY",
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

    # ── Security ───────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(..., min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12
    AGENT_WEBHOOK_SECRET: str = Field(..., min_length=32)

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
    ELEVENLABS_MODEL_ID: str = "eleven_flash_v2_5"

    # ── Groq LLM ──────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(...)
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_SUMMARY_MODEL: str = "llama-3.1-70b-versatile"

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
    EXPORT_URL_EXPIRY_SECONDS: int = 600

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Rate limiting (slowapi format: "N/period") ─────────────────────────────
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_CAMPAIGN_LAUNCH: str = "10/hour"
    RATE_LIMIT_GLOBAL: str = "100/minute"

    # ── Monitoring ────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Internal service communication ────────────────────────────────────────
    BACKEND_INTERNAL_URL: str = "http://api:8000"
    AGENT_TEMPLATE_CACHE_TTL: int = 60

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
