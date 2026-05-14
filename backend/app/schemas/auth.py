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
