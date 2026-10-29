from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt as pyjwt
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import google_signin
from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.rate_limit import client_ip, enforce_rate_limit
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
    AccessTokenResponse,
    ForgotPasswordRequest,
    GoogleCompleteRequest,
    GoogleSignInRequest,
    LoginRequest,
    MemberRegisterRequest,
    ProfileUpdateRequest,
    RefreshRequest,
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


async def _new_org(db: AsyncSession, company_name: str, phone: str) -> Organization:
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-") or "org"
    if await db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{slug}-{uuid4().hex[:6]}"

    org = Organization(
        name=company_name,
        slug=slug,
        phone=phone,
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
    return org


async def _org_by_code(db: AsyncSession, org_code: str) -> Organization:
    # Find org by code prefix (first 8 hex chars of org UUID without dashes)
    code = org_code.strip().lower().replace("-", "")
    if len(code) < 8:
        raise AppValidationError("Invalid org code", errors=[])

    # Fetch all orgs and match by the first 8 chars of their id (hex, no dashes)
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
    return org


async def _session(db: AsyncSession, user: User) -> TokenResponse:
    """Issue the access + refresh tokens for a user who just proved who they are."""
    org = await db.get(Organization, user.org_id)
    return TokenResponse(
        access_token=create_access_token(str(user.id), str(user.org_id), user.role),
        refresh_token=create_refresh_token(str(user.id), str(user.org_id)),
        user=UserOut(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            org_id=str(user.org_id),
            org_name=org.name if org else "",
        ),
    )


@router.post("/register", response_model=RegisterPendingResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit("register", client_ip(request), limit=5, window_seconds=3600)

    if len(body.password) < 6:
        raise AppValidationError("Password must be at least 6 characters", errors=[])

    existing = await db.scalar(select(User.id).where(User.email == body.email))
    if existing:
        raise ConflictError("Email already registered")

    org = await _new_org(db, body.company_name, body.phone)

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


@router.post("/register-member", response_model=RegisterPendingResponse, status_code=201)
async def register_member(body: MemberRegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Sales team member self-registers using the 8-char org code shown on the
    admin Users page. Creates a MEMBER-role account inside that org.

    Mirrors register()'s flow: no session is issued yet, and email_verified_at
    stays NULL until POST /verify-otp — same OTP step new organizations go
    through, so /login's `email_verified_at is None` check applies uniformly
    to every account instead of only ones created via /register.
    """
    await enforce_rate_limit("register-member", client_ip(request), limit=5, window_seconds=3600)

    org = await _org_by_code(db, body.org_code)

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
        email_verified_at=None,
    )
    db.add(user)
    await db.commit()

    try:
        await send_otp(body.email)
    except SupabaseOtpError as exc:
        raise AppValidationError(str(exc), errors=[]) from exc
    return RegisterPendingResponse(email=body.email)


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

    return await _session(db, user)


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
async def forgot_password(body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Always 204 regardless of whether the email exists, to avoid leaking
    which addresses have accounts. Only actually sends an OTP if one does."""
    await enforce_rate_limit("forgot-password", f"{client_ip(request)}:{body.email}", limit=5, window_seconds=3600)

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
async def reset_password(body: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Also caps how many OTP codes can be guessed against one email from one
    # source -- reset-password is the endpoint that actually redeems the code.
    await enforce_rate_limit("reset-password", f"{client_ip(request)}:{body.email}", limit=10, window_seconds=3600)

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
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Two separate windows: a per-account cap (stops brute-forcing one
    # specific email's password) and a coarser per-IP cap (stops one source
    # spraying many emails). Checked before touching the DB/password hash.
    ip = client_ip(request)
    await enforce_rate_limit("login-ip", ip, limit=30, window_seconds=600)
    await enforce_rate_limit("login-account", f"{ip}:{body.email}", limit=8, window_seconds=600)

    result = await db.execute(
        select(User).where(User.email == body.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")
    if not user.is_active:
        raise AuthenticationError("Account is inactive. Contact your admin.")
    if settings.REQUIRE_EMAIL_VERIFICATION and user.email_verified_at is None:
        raise AuthenticationError("Please verify your email before logging in", code="EMAIL_NOT_VERIFIED")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return await _session(db, user)


@router.get("/google/url")
async def google_signin_url(origin: str, nonce: str):
    """Where the "Sign in with Google" button sends the browser. Google sends it back to
    <origin>/auth/google; origin must be one of our own frontends (CORS_ORIGINS)."""
    if not google_signin.configured():
        raise AppValidationError("Google sign-in isn't set up on this server yet", errors=[])
    if origin.rstrip("/") not in [o.rstrip("/") for o in settings.CORS_ORIGINS]:
        raise AppValidationError("Unknown site", errors=[])
    redirect = google_signin.redirect_uri(origin)
    # The nonce stays in the browser's sessionStorage, so a code+state pasted into someone
    # else's browser (login CSRF) won't match theirs.
    state = pyjwt.encode({
        "type": "google_signin", "redirect": redirect, "nonce": nonce,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }, settings.SECRET_KEY, algorithm="HS256")
    return {"url": google_signin.auth_url(redirect, state)}


@router.post("/google/signin")
async def google_signin_callback(body: GoogleSignInRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Existing account → session (same body as /login, plus status "ok").
    Unknown email → status "signup" with a short-lived token for /google/complete."""
    await enforce_rate_limit("login-ip", client_ip(request), limit=30, window_seconds=600)
    try:
        state = pyjwt.decode(body.state, settings.SECRET_KEY, algorithms=["HS256"])
    except pyjwt.InvalidTokenError:
        raise AuthenticationError("Google sign-in expired. Please try again.")
    if state.get("type") != "google_signin" or not body.nonce or state.get("nonce") != body.nonce:
        raise AuthenticationError("Google sign-in expired. Please try again.")
    try:
        email, name = await google_signin.exchange_code(body.code, state["redirect"])
    except google_signin.GoogleSignInError as exc:
        raise AuthenticationError(str(exc))

    user = await db.scalar(select(User).where(func.lower(User.email) == email, User.deleted_at.is_(None)))
    if not user:
        signup_token = pyjwt.encode({
            "type": "google_signup", "email": email,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }, settings.SECRET_KEY, algorithm="HS256")
        return {"status": "signup", "signup_token": signup_token, "email": email, "full_name": name}
    if not user.is_active:
        raise AuthenticationError("Account is inactive. Contact your admin.")
    # Google has confirmed they own this inbox, which is all the OTP step proves.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok", **(await _session(db, user)).model_dump()}


@router.post("/google/complete", response_model=TokenResponse, status_code=201)
async def google_complete_signup(body: GoogleCompleteRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create the account for a first-time Google user: a new org, or join one by invite code."""
    await enforce_rate_limit("register", client_ip(request), limit=5, window_seconds=3600)
    try:
        claims = pyjwt.decode(body.signup_token, settings.SECRET_KEY, algorithms=["HS256"])
    except pyjwt.InvalidTokenError:
        raise AuthenticationError("Google sign-up expired. Please sign in with Google again.")
    if claims.get("type") != "google_signup":
        raise AuthenticationError("Google sign-up expired. Please sign in with Google again.")
    email = claims["email"]
    if len(body.full_name.strip()) < 2:
        raise AppValidationError("Enter your full name", errors=[])
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ConflictError("Email already registered")

    if body.org_code:
        org, role = await _org_by_code(db, body.org_code), UserRole.MEMBER
    elif body.company_name and len(body.company_name.strip()) >= 2 and body.phone:
        org, role = await _new_org(db, body.company_name.strip(), body.phone), UserRole.ADMIN
    else:
        raise AppValidationError("Enter your company name and phone, or a team invite code", errors=[])

    now = datetime.now(timezone.utc)
    user = User(
        org_id=org.id,
        email=email,
        # No password yet: they log in with Google, or set one via "Forgot password".
        hashed_password=hash_password(uuid4().hex + uuid4().hex),
        full_name=body.full_name.strip(),
        role=role,
        is_active=True,
        email_verified_at=now,
        last_login_at=now,
    )
    db.add(user)
    await db.commit()
    return await _session(db, user)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchanges a still-valid refresh token for a new access token.

    Access tokens are deliberately short-lived (settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    currently 15 minutes) and refresh tokens were already being issued and
    stored by the frontend at login/verify-otp — but until this endpoint
    existed, nothing ever redeemed one. Every user was being force-logged-out
    on the 15-minute timer with no way to silently renew a session.
    """
    try:
        payload = decode_token(body.refresh_token)
    except InvalidTokenError:
        raise AuthenticationError("Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise AuthenticationError("Not a refresh token")

    # Same Redis blocklist get_current_user checks for access tokens — lets a
    # refresh token be revoked (e.g. logout) without waiting out its full
    # 7-day expiry. Fails open on Redis errors, same tradeoff as elsewhere.
    jti = payload.get("jti")
    if jti:
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            if await r.exists(f"motm:auth:blocklist:{jti}"):
                raise AuthenticationError("Token has been revoked")
        except AuthenticationError:
            raise
        except Exception:
            pass

    try:
        user = await db.get(User, UUID(payload["sub"]))
    except (KeyError, ValueError):
        raise AuthenticationError("Invalid refresh token")
    if not user or user.deleted_at or not user.is_active:
        raise AuthenticationError("Account no longer active")

    access_token = create_access_token(str(user.id), str(user.org_id), user.role)
    return AccessTokenResponse(access_token=access_token)


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
