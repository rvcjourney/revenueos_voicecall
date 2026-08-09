from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.supabase_otp import SupabaseOtpError, send_otp, verify_otp
from app.database import get_db
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization, User, UserRole
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MemberRegisterRequest,
    ProfileUpdateRequest,
    RegisterPendingResponse,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyOtpRequest,
)

router = APIRouter()
_bearer_optional = HTTPBearer(auto_error=False)


@router.post("/register", response_model=RegisterPendingResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User.id).where(User.email == body.email))
    if existing:
        raise ConflictError("Email already registered")

    slug = re.sub(r"[^a-z0-9]+", "-", body.company_name.lower()).strip("-") or "org"
    if await db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{slug}-{uuid4().hex[:6]}"

    org = Organization(
        name=body.company_name,
        slug=slug,
        phone=body.phone,
        sip_caller_id=settings.DEFAULT_SIP_CALLER_ID,
        # Self-serve orgs start suspended until a Razorpay subscription
        # payment succeeds — the webhook (POST /webhooks/razorpay:
        # subscription.activated/charged) flips this true. Orgs a superadmin
        # creates directly (app/api/platform.py) are unaffected by this and
        # keep the column's normal default of active.
        is_active=False,
    )
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.ADMIN,
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    await db.commit()

    # No session issued yet — POST /verify-otp is what actually logs the user
    # in, once they've proven they own this email address.
    try:
        await send_otp(body.email)
    except SupabaseOtpError as exc:
        # The account row already exists at this point (org+user committed
        # above) — that's fine, POST /resend-otp lets them retry sending
        # without re-registering.
        raise AppValidationError(str(exc), errors=[]) from exc
    return RegisterPendingResponse(email=body.email)


@router.post("/register-member", response_model=TokenResponse, status_code=201)
async def register_member(body: MemberRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Sales team member self-registers using the 8-char org code shown on the
    admin Users page.  Creates a MEMBER-role account inside that org.
    """
    # Find org by code prefix (first 8 hex chars of org UUID without dashes)
    code = body.org_code.strip().lower().replace("-", "")
    if len(code) < 8:
        raise AppValidationError("Invalid org code", errors=[])

    # Fetch all orgs and match by the first 8 chars of their id (hex, no dashes)
    from sqlalchemy import text
    org = await db.scalar(
        select(Organization).where(
            Organization.deleted_at.is_(None),
        ).where(
            # cast uuid to text, strip dashes, check prefix
            text("replace(cast(id as text), '-', '') LIKE :pattern"),
        ).params(pattern=f"{code[:8]}%")
    )
    if not org:
        raise NotFoundError("Invalid org code — ask your admin for the correct code")

    existing = await db.scalar(select(User.id).where(User.email == body.email))
    if existing:
        raise ConflictError("Email already registered")

    if len(body.password) < 6:
        raise AppValidationError("Password must be at least 6 characters", errors=[])

    user = User(
        org_id=org.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.MEMBER,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(str(user.id), str(user.org_id), user.role)
    refresh_token = create_refresh_token(str(user.id), str(user.org_id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            org_id=str(user.org_id),
            org_name=org.name,
        ),
    )


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp_endpoint(body: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    """Confirms the signup OTP and — since this is what actually completes
    registration — issues the first session (mirrors register()'s old
    immediate-login behavior, just gated on verification now)."""
    user = await db.scalar(select(User).where(User.email == body.email, User.deleted_at.is_(None)))
    if not user:
        raise NotFoundError("No account found for that email")

    try:
        ok = await verify_otp(body.email, body.code)
    except SupabaseOtpError as exc:
        raise AppValidationError(str(exc), errors=[]) from exc
    if not ok:
        raise AuthenticationError("That code is incorrect or has expired")

    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    org = await db.get(Organization, user.org_id)
    access_token = create_access_token(str(user.id), str(user.org_id), user.role)
    refresh_token = create_refresh_token(str(user.id), str(user.org_id))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            org_id=str(user.org_id),
            org_name=org.name if org else "",
        ),
    )


_RESEND_COOLDOWN_SECONDS = 60


@router.post("/resend-otp", status_code=204)
async def resend_otp(body: ResendOtpRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User.id).where(User.email == body.email, User.deleted_at.is_(None)))
    if not user:
        raise NotFoundError("No account found for that email")

    from app.core.redis import get_redis
    r = await get_redis()
    cooldown_key = f"motm:otp:resend-cooldown:{body.email}"
    if not await r.set(cooldown_key, "1", nx=True, ex=_RESEND_COOLDOWN_SECONDS):
        raise ConflictError("Please wait before requesting another code")

    try:
        await send_otp(body.email)
    except SupabaseOtpError as exc:
        raise AppValidationError(str(exc), errors=[]) from exc


@router.post("/forgot-password", status_code=204)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Always 204 regardless of whether the email exists, to avoid leaking
    which addresses have accounts. Only actually sends an OTP if one does."""
    user = await db.scalar(select(User.id).where(User.email == body.email, User.deleted_at.is_(None)))
    if not user:
        return

    try:
        await send_otp(body.email)
    except SupabaseOtpError:
        # Same reasoning as above — don't let a delivery failure leak account
        # existence via a different response than the "no such email" path.
        pass


@router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email, User.deleted_at.is_(None)))
    if not user:
        raise NotFoundError("No account found for that email")

    if len(body.new_password) < 6:
        raise AppValidationError("Password must be at least 6 characters", errors=[])

    try:
        ok = await verify_otp(body.email, body.code)
    except SupabaseOtpError as exc:
        raise AppValidationError(str(exc), errors=[]) from exc
    if not ok:
        raise AuthenticationError("That code is incorrect or has expired")

    user.hashed_password = hash_password(body.new_password)
    await db.commit()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")
    if not user.is_active:
        raise AuthenticationError("Account is inactive. Contact your admin.")
    if user.email_verified_at is None:
        raise AuthenticationError("Please verify your email before logging in", code="EMAIL_NOT_VERIFIED")

    org = await db.get(Organization, user.org_id)

    access_token = create_access_token(str(user.id), str(user.org_id), user.role)
    refresh_token = create_refresh_token(str(user.id), str(user.org_id))

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            org_id=str(user.org_id),
            org_name=org.name if org else "",
        ),
    )


@router.post("/logout", status_code=204)
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
):
    """
    Revoke the current access token by adding its jti to a Redis blocklist.
    The blocklist entry auto-expires when the token would have naturally expired.
    Silent on errors — always returns 204 so the client can clear its local token.
    """
    if credentials is None:
        return
    try:
        payload = decode_token(credentials.credentials)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(1, int(exp - time.time()))
            from app.core.redis import get_redis
            r = await get_redis()
            await r.set(f"motm:auth:blocklist:{jti}", "1", ex=ttl)
    except Exception:
        pass  # silent — client should discard the token regardless


@router.get("/me", response_model=UserOut)
async def me(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, token.user_id)
    if not user or user.deleted_at:
        raise AuthenticationError("User not found")

    org = await db.get(Organization, user.org_id)

    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        org_id=str(user.org_id),
        org_name=org.name if org else "",
    )


@router.get("/org-info")
async def get_my_org_info(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return org quota info available to all authenticated users."""
    org = await db.get(Organization, token.org_id)
    if not org:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Organization not found")

    # org.plan_tier is a legacy column that's never updated after a Razorpay
    # plan change/upgrade -- the real current plan lives on the org's active
    # Subscription -> Plan, same source Billing.tsx and the superadmin
    # Organizations list already use. Fall back to plan_tier only for an org
    # with no Subscription row yet (e.g. registered but never checked out).
    sub = await db.scalar(
        select(Subscription).where(Subscription.org_id == org.id, Subscription.deleted_at.is_(None))
    )
    plan_name = org.plan_tier
    if sub:
        plan = await db.get(Plan, sub.plan_id)
        if plan:
            plan_name = plan.name

    return {
        "id": str(org.id),
        "name": org.name,
        "plan_tier": plan_name,
        "monthly_call_quota": org.monthly_call_quota,
        "calls_used_this_period": org.calls_used_this_period,
    }


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    body: ProfileUpdateRequest,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Any logged-in user can update their own name and password."""
    user = await db.get(User, token.user_id)
    if not user or user.deleted_at:
        raise AuthenticationError("User not found")

    if body.full_name is not None:
        user.full_name = body.full_name.strip()

    if body.password is not None:
        if len(body.password) < 6:
            raise AppValidationError("Password must be at least 6 characters", errors=[])
        user.hashed_password = hash_password(body.password)

    await db.commit()
    await db.refresh(user)

    org = await db.get(Organization, user.org_id)
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        org_id=str(user.org_id),
        org_name=org.name if org else "",
    )
