from __future__ import annotations

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    full_name: str
    company_name: str
    email: EmailStr
    password: str
    phone: str = ""


class MemberRegisterRequest(BaseModel):
    """Sales team member joins an existing org using the org's invite code."""
    full_name: str
    email: EmailStr
    password: str
    org_code: str   # first 8 chars of org_id shown on admin Users page


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    password: str | None = None   # if provided, must be >= 6 chars


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    org_id: str
    org_name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Admin schemas ─────────────────────────────────────────────────────────────

class AdminCreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "member"   # "admin" | "member"


class AdminUpdateUserRequest(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: str | None
    created_at: str
