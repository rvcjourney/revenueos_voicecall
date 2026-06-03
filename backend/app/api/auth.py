from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import Organization, User, UserRole
from app.schemas.auth import (
    LoginRequest,
    MemberRegisterRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    raise ConflictError("Registration is currently closed. Contact the administrator.")
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
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
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
