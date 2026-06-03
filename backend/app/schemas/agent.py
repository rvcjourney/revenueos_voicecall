from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class AgentOut(BaseModel):
    id: str
    name: str
    description: str | None
    language: str
    welcome_message: str
    system_prompt: str
    voice_id: str
    voice_provider: str
    llm_model: str
    llm_temperature: float
    max_call_duration_seconds: int
    created_at: datetime
    # access_status: "approved" (admin / access granted), "pending" (requested), "locked" (not requested)
    access_status: str = "approved"
    access_request_id: str | None = None  # used by admin to approve/reject


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
    voice_id: str = "9BWtsMINqrJLrRacOk9x"
    voice_provider: str = "elevenlabs"
    llm_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.7
    max_call_duration_seconds: int = 600

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        return v.lower()


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    language: str | None = None
    welcome_message: str | None = None
    system_prompt: str | None = None
    voice_id: str | None = None
    voice_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    max_call_duration_seconds: int | None = None
