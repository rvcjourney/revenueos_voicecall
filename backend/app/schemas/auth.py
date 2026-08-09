from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    full_name: str
    company_name: str
    email: EmailStr
    password: str
    phone: str

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        # Same E.164-ish normalization used elsewhere for phone numbers
        # (e.g. app/api/sip_trunks.py, app/api/agents.py's test-call flow).
        phone = v.strip().replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+91" + phone.lstrip("0")
        if len(phone) < 8:
            raise ValueError("Enter a valid phone number")
        return phone


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str


class ResendOtpRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


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


class RegisterPendingResponse(BaseModel):
    """register()'s response — no session yet, email must be verified via
    POST /verify-otp first (that's what actually issues a TokenResponse)."""
    email: str
    message: str = "Verification code sent — check your email."


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
