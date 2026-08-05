from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PromptLibraryVersionOut(BaseModel):
    version: int
    structured_prompt: str
    editor_id: str | None
    editor_name: str
    note: str | None
    created_at: datetime


class PromptLibraryEntryOut(BaseModel):
    id: str
    title: str
    tags: list[str]
    raw_input: str | None
    structured_prompt: str
    is_high_performing: bool
    current_version: int
    source_agent_id: str | None
    source_agent_name: str | None
    created_by_id: str | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime


class PromptLibraryListResponse(BaseModel):
    items: list[PromptLibraryEntryOut]
    total: int


class PromptLibraryCreate(BaseModel):
    title: str
    tags: list[str] = []
    raw_input: str | None = None
    structured_prompt: str


class PromptLibraryUpdate(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    structured_prompt: str | None = None
    # Short edit summary recorded on the new version row when structured_prompt changes.
    note: str | None = None


class MarkPerformingRequest(BaseModel):
    is_high_performing: bool


class RestoreVersionResponse(BaseModel):
    entry: PromptLibraryEntryOut


class SyncFromAgentsResponse(BaseModel):
    created: int
    message: str
