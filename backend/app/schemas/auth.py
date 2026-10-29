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


class GoogleSignInRequest(BaseModel):
    code: str
    state: str
    nonce: str


class GoogleCompleteRequest(BaseModel):
    """First Google sign-in for an unknown email: either new org (company_name + phone)
    or join one (org_code). Email comes from the signed signup_token, not the client."""
    signup_token: str
    full_name: str
    company_name: str | None = None
    phone: str | None = None
    org_code: str | None = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        return None if v is None else RegisterRequest.normalize_phone(v)


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


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
