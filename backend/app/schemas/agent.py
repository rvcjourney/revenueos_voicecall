from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.core.contacts_file import normalize_phone


def _transfer_number(v: str | None) -> str | None:
    """'' clears it; otherwise E.164 (+91 assumed when no country code is given)."""
    if v is None or not v.strip():
        return v if v is None else ""
    phone = normalize_phone(v.replace("(", "").replace(")", ""))
    if not (phone[1:].isdigit() and 8 <= len(phone) - 1 <= 15):
        raise ValueError("Enter a valid phone number, e.g. +91 98765 43210")
    return phone


class AgentOut(BaseModel):
    id: str
    name: str
    description: str | None
    language: str
    welcome_message: str
    system_prompt: str
    variables: dict[str, str] = {}
    voice_id: str
    llm_temperature: float
    speech_pace: float
    max_call_duration_seconds: int
    transfer_number: str = ""
    created_at: datetime
    # Brochure emailed when a customer agrees on a call (None = no brochure uploaded).
    brochure_filename: str | None = None
    brochure_email_subject: str | None = None
    brochure_email_body: str | None = None
    # access_status: "approved" (admin / access granted), "pending" (requested), "locked" (not requested)
    access_status: str = "approved"
    access_request_id: str | None = None  # used by admin to approve/reject
    can_edit: bool = False


class AgentListResponse(BaseModel):
    items: list[AgentOut]
    total: int


class AgentAccessRequestOut(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    user_id: str
    user_name: str
    user_email: str
    status: str
    created_at: datetime


class AgentCreationRequestOut(BaseModel):
    id: str
    agent_name: str
    company_name: str
    status: str   # pending | reviewed
    admin_notes: str | None
    has_file: bool
    file_name: str | None
    created_at: datetime


class AgentCreationRequestAdminOut(AgentCreationRequestOut):
    user_id: str
    user_name: str
    user_email: str
    product_service: str
    target_customers: str
    key_points: str
    file_url: str | None = None   # presigned download URL


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    language: str = "hinglish"
    welcome_message: str = ""
    system_prompt: str = ""
    variables: dict[str, str] = {}
    voice_id: str = ""  # "" = the language's default voice
    llm_temperature: float = 0.7
    speech_pace: float = Field(1.0, ge=0.7, le=1.5)
    max_call_duration_seconds: int = 600
    transfer_number: str = ""

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        return v.lower()

    _check_transfer = field_validator("transfer_number")(_transfer_number)


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    language: str | None = None
    welcome_message: str | None = None
    system_prompt: str | None = None
    variables: dict[str, str] | None = None
    voice_id: str | None = None
    llm_temperature: float | None = None
    speech_pace: float | None = Field(None, ge=0.7, le=1.5)
    max_call_duration_seconds: int | None = None
    brochure_email_subject: str | None = Field(None, max_length=255)
    brochure_email_body: str | None = Field(None, max_length=20_000)
    transfer_number: str | None = None

    _check_transfer = field_validator("transfer_number")(_transfer_number)
