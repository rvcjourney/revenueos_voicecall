from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.campaign import Campaign, CampaignFolder
from app.schemas.campaign import FolderCreate, FolderOut, FolderUpdate

router = APIRouter()


def _to_out(folder: CampaignFolder, count: int) -> FolderOut:
    return FolderOut(
        id=str(folder.id),
        name=folder.name,
        color=folder.color,
        campaign_count=count,
        created_at=folder.created_at,
    )


@router.get("", response_model=list[FolderOut])
async def list_folders(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folders = (await db.execute(
        select(CampaignFolder)
        .where(CampaignFolder.org_id == token.org_id, CampaignFolder.deleted_at.is_(None))
        .order_by(CampaignFolder.created_at)
    )).scalars().all()

    counts: dict[str, int] = {}
    if folders:
        rows = (await db.execute(
            select(Campaign.folder_id, func.count(Campaign.id))
            .where(
                Campaign.folder_id.in_([f.id for f in folders]),
                Campaign.deleted_at.is_(None),
            )
            .group_by(Campaign.folder_id)
        )).all()
        counts = {str(fid): cnt for fid, cnt in rows}

    return [_to_out(f, counts.get(str(f.id), 0)) for f in folders]


@router.post("", response_model=FolderOut, status_code=201)
async def create_folder(
    body: FolderCreate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = CampaignFolder(
        org_id=token.org_id,
        created_by_id=token.user_id,
        name=body.name,
        color=body.color,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return _to_out(folder, 0)


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: UUID,
    body: FolderUpdate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await db.get(CampaignFolder, folder_id)
    if not folder or folder.org_id != token.org_id or folder.deleted_at:
        raise NotFoundError("Folder not found")

    if body.name is not None:
        folder.name = body.name
    if body.color is not None:
        folder.color = body.color

    await db.commit()
    await db.refresh(folder)

    count = await db.scalar(
        select(func.count(Campaign.id))
        .where(Campaign.folder_id == folder_id, Campaign.deleted_at.is_(None))
    ) or 0
    return _to_out(folder, count)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await db.get(CampaignFolder, folder_id)
    if not folder or folder.org_id != token.org_id or folder.deleted_at:
        raise NotFoundError("Folder not found")

    folder.deleted_at = datetime.now(timezone.utc)
    await db.commit()
