"""
Company profile for Prime Calling — the org's own "who we are" info that the
LLM combines with each contact's CSV row (see app/services/prime_prompt.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, require_admin
from app.database import get_db
from app.models.company_profile import OrgCompanyProfile

router = APIRouter()


class CompanyProfileIn(BaseModel):
    company_name: str = Field("", max_length=255)
    website: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=255)
    what_we_offer: str | None = Field(None, max_length=5000)
    value_proposition: str | None = Field(None, max_length=5000)
    target_customers: str | None = Field(None, max_length=5000)
    key_points: str | None = Field(None, max_length=5000)
    call_objective: str | None = Field(None, max_length=2000)
    tone_notes: str | None = Field(None, max_length=2000)
    extra_info: str | None = Field(None, max_length=10000)


class CompanyProfileOut(CompanyProfileIn):
    is_complete: bool = False
    updated_at: str | None = None


_FIELDS = list(CompanyProfileIn.model_fields)


def _to_out(p: OrgCompanyProfile | None) -> CompanyProfileOut:
    if p is None:
        return CompanyProfileOut()
    return CompanyProfileOut(
        **{f: getattr(p, f) for f in _FIELDS},
        is_complete=p.is_complete,
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
    )


async def get_org_profile(db: AsyncSession, org_id) -> OrgCompanyProfile | None:
    return await db.scalar(select(OrgCompanyProfile).where(OrgCompanyProfile.org_id == org_id))


@router.get("", response_model=CompanyProfileOut)
async def get_company_profile(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _to_out(await get_org_profile(db, token.org_id))


@router.put("", response_model=CompanyProfileOut)
async def save_company_profile(
    body: CompanyProfileIn,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_org_profile(db, token.org_id)
    if profile is None:
        profile = OrgCompanyProfile(org_id=token.org_id)
        db.add(profile)
    for field, value in body.model_dump().items():
        setattr(profile, field, value.strip() if isinstance(value, str) else value)
    profile.company_name = profile.company_name or ""
    await db.commit()
    await db.refresh(profile)
    return _to_out(profile)
