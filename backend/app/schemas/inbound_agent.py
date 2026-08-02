from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class InboundAgentOut(BaseModel):
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


class InboundAgentListResponse(BaseModel):
    items: list[InboundAgentOut]
    total: int


class InboundAgentCreate(BaseModel):
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


class InboundAgentUpdate(BaseModel):
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
