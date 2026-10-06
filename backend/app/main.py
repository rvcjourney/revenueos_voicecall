"""
app/main.py — FastAPI application factory, middleware stack, and exception handlers.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    CampaignStateError,
    ConflictError,
    DNCBlockedError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitedError,
    StorageError,
    ValidationError as AppValidationError,
    WebhookAuthError,
)
from app.core.logging import RequestIDMiddleware, configure_logging
from app.core.sentry import init_sentry
from app.database import check_db_health, dispose_engine

log = structlog.get_logger(__name__)


# ── Sentry ────────────────────────────────────────────────────────────────────

def _init_sentry() -> None:
    init_sentry(integrations=[FastApiIntegration(), StarletteIntegration()], component="api")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Logging must be configured before any log calls
    configure_logging()
    log.info(
        "startup",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    _init_sentry()

    # Storage: ensure all buckets exist (non-fatal — MinIO/S3 may not be running locally)
    try:
        from app.storage import get_storage
        await get_storage().ensure_buckets()
        log.info("storage_ready", backend=settings.STORAGE_BACKEND)
    except Exception as exc:
        log.warning("storage_unavailable", error=str(exc), note="file uploads disabled until storage is reachable")

    # Redis: verify connectivity (non-fatal — caching/queues degrade gracefully)
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.ping()
        log.info("redis_ready")
    except Exception as exc:
        log.warning("redis_unavailable", error=str(exc), note="caching and Celery tasks disabled")

    yield  # ── application running ─────────────────────────────────────────────

    log.info("shutdown_started")
    from app.core.redis import close_redis
    await close_redis()
    await dispose_engine()
    log.info("shutdown_complete")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        redoc_url="/redoc" if settings.DOCS_ENABLED else None,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
        lifespan=lifespan,
    )

    # ── Middleware (outermost runs first on request, last on response) ─────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Total-Count"],
    )
    # RequestIDMiddleware must come after CORS so CORS headers are set before ID
    app.add_middleware(RequestIDMiddleware)

    # ── Prometheus metrics ─────────────────────────────────────────────────────
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/health/ready", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    _register_exception_handlers(app)
    _register_routers(app)

    return app


# ── Exception handlers ────────────────────────────────────────────────────────

def _register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def pydantic_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        if request.url.path.startswith("/api/integrations/"):
            # These requests carry a password and a Vobiz token. Pydantic's
            # errors repeat the rejected input, so keep only where and why.
            errors = [
                {"field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"), "message": e.get("msg", "")}
                for e in errors
            ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Request validation failed.",
                "code": "VALIDATION_ERROR",
                "errors": errors,
            },
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.message, "code": exc.code},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(WebhookAuthError)
    async def webhook_auth_handler(request: Request, exc: WebhookAuthError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(
        request: Request, exc: PermissionDeniedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(CampaignStateError)
    async def campaign_state_handler(
        request: Request, exc: CampaignStateError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(AppValidationError)
    async def app_validation_handler(
        request: Request, exc: AppValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message, "code": exc.code, "errors": exc.errors},
        )

    @app.exception_handler(DNCBlockedError)
    async def dnc_handler(request: Request, exc: DNCBlockedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(QuotaExceededError)
    async def quota_handler(request: Request, exc: QuotaExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(RateLimitedError)
    async def rate_limited_handler(request: Request, exc: RateLimitedError) -> JSONResponse:
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": exc.message, "code": exc.code, "retry_after_seconds": exc.retry_after_seconds},
            headers=headers,
        )

    @app.exception_handler(StorageError)
    async def storage_handler(request: Request, exc: StorageError) -> JSONResponse:
        log.error("storage_error", message=exc.message)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": exc.message, "code": exc.code},
        )

    # Catch-all for AppError subclasses not mapped above
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        log.error("unhandled_app_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal error occurred.", "code": "INTERNAL_ERROR"},
        )


# ── Routers ───────────────────────────────────────────────────────────────────

def _register_routers(app: FastAPI) -> None:
    # System endpoints — no auth, not versioned
    @app.get("/health", tags=["system"], include_in_schema=False)
    async def liveness() -> dict[str, str]:
        """Kubernetes/Docker liveness probe — always returns 200 if process is up."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["system"], include_in_schema=False)
    async def readiness() -> JSONResponse:
        """Readiness probe — checks DB and Redis. Returns 503 if either is down."""
        from app.core.redis import get_redis
        checks: dict[str, bool] = {}

        checks["database"] = await check_db_health()
        try:
            r = await get_redis()
            await r.ping()
            checks["redis"] = True
        except Exception:
            checks["redis"] = False

        ok = all(checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ready" if ok else "degraded", "checks": checks},
        )

    @app.get("/version", tags=["system"], include_in_schema=False)
    async def version() -> dict[str, str]:
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    from app.api.auth import router as auth_router
    from app.api.agents import router as agents_router
    from app.api.campaigns import router as campaigns_router
    from app.api.folders import router as folders_router
    from app.api.calls import router as calls_router
    from app.api.analytics import router as analytics_router
    from app.api.webhooks import router as webhooks_router
    from app.api.admin import router as admin_router
    from app.api.sip_trunks import router as sip_trunks_router
    from app.api.platform import router as platform_router
    from app.api.usage import router as usage_router
    from app.api.voice_cloning import router as voice_cloning_router
    from app.api.inbound_agents import router as inbound_agents_router
    from app.api.agent_internal import router as agent_internal_router
    from app.api.plans import router as plans_router
    from app.api.billing import router as billing_router
    from app.api.prompt_library import router as prompt_library_router
    from app.api.company_profile import router as company_profile_router
    from app.api.revenueos import router as revenueos_router

    app.include_router(auth_router,        prefix="/api/auth",        tags=["auth"])
    app.include_router(admin_router,       prefix="/api/admin",       tags=["admin"])
    app.include_router(platform_router,    prefix="/api/platform",    tags=["platform"])
    app.include_router(usage_router,       prefix="/api/usage",       tags=["usage"])
    app.include_router(voice_cloning_router, prefix="/api/voice-cloning", tags=["voice-cloning"])
    app.include_router(agents_router,      prefix="/api/agents",      tags=["agents"])
    app.include_router(inbound_agents_router, prefix="/api/inbound-agents", tags=["inbound-agents"])
    app.include_router(campaigns_router,   prefix="/api/campaigns",   tags=["campaigns"])
    app.include_router(folders_router,     prefix="/api/folders",     tags=["folders"])
    app.include_router(calls_router,       prefix="/api/calls",       tags=["calls"])
    app.include_router(analytics_router,   prefix="/api/analytics",   tags=["analytics"])
    app.include_router(webhooks_router,    prefix="/webhooks",        tags=["webhooks"])
    app.include_router(sip_trunks_router,  prefix="/api/sip-trunks",  tags=["sip-trunks"])
    app.include_router(agent_internal_router, prefix="/api/internal", tags=["internal"], include_in_schema=False)
    app.include_router(plans_router,       prefix="/api/plans",       tags=["plans"])
    app.include_router(billing_router,     prefix="/api/billing",     tags=["billing"])
    app.include_router(prompt_library_router, prefix="/api/prompt-library", tags=["prompt-library"])
    app.include_router(company_profile_router, prefix="/api/company-profile", tags=["prime-calling"])
    app.include_router(revenueos_router,   prefix="/api/integrations/revenueos", tags=["revenueos"])


app = create_app()
