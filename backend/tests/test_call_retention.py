"""
tests/test_call_retention.py — app/workers/tasks/retention.py's daily purge
of call recordings/transcripts past CALL_DATA_RETENTION_DAYS.

Founder decision (2026-08-23 readiness audit, blocker 3): 45 days, hard
delete. The Call row itself must never be touched -- only recording_url and
the CallTranscript row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.models.call import Call, CallTranscript
from app.models.user import Organization
from app.workers.tasks.retention import _purge_expired_call_data_async


async def _make_org(db) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def _make_call(db, org: Organization, *, created_at: datetime, with_recording: bool = True) -> Call:
    call = Call(
        org_id=org.id,
        phone_number="+919876543210",
        livekit_room_name=f"room-{uuid.uuid4().hex}",
        recording_url="https://media.vobiz.ai/rec-abc123.mp3" if with_recording else None,
        created_at=created_at,
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)
    if with_recording:
        db.add(CallTranscript(call_id=call.id, segments=[{"speaker": "user", "text": "hi"}], full_text="hi"))
        await db.commit()
    return call


async def test_purges_recording_and_transcript_past_retention_window(db):
    org = await _make_org(db)
    old_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.CALL_DATA_RETENTION_DAYS + 1)
    call = await _make_call(db, org, created_at=old_cutoff)

    await _purge_expired_call_data_async()

    await db.refresh(call)
    assert call.recording_url is None
    assert call.recording_purged_at is not None

    transcript = (await db.execute(
        select(CallTranscript).where(CallTranscript.call_id == call.id)
    )).scalar_one_or_none()
    assert transcript is None


async def test_does_not_purge_calls_within_retention_window(db):
    org = await _make_org(db)
    recent = datetime.now(timezone.utc) - timedelta(days=settings.CALL_DATA_RETENTION_DAYS - 5)
    call = await _make_call(db, org, created_at=recent)

    await _purge_expired_call_data_async()

    await db.refresh(call)
    assert call.recording_url is not None
    assert call.recording_purged_at is None

    transcript = (await db.execute(
        select(CallTranscript).where(CallTranscript.call_id == call.id)
    )).scalar_one_or_none()
    assert transcript is not None


async def test_call_row_itself_is_never_deleted(db):
    org = await _make_org(db)
    old_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.CALL_DATA_RETENTION_DAYS + 30)
    call = await _make_call(db, org, created_at=old_cutoff)
    call_id = call.id

    await _purge_expired_call_data_async()

    still_there = await db.get(Call, call_id)
    assert still_there is not None
    assert still_there.id == call_id


async def test_expired_call_with_no_recording_is_marked_purged_without_error(db):
    """A call that never had a recording/transcript (e.g. no_answer) still
    gets recording_purged_at stamped, so the daily scan doesn't rescan it
    forever."""
    org = await _make_org(db)
    old_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.CALL_DATA_RETENTION_DAYS + 1)
    call = await _make_call(db, org, created_at=old_cutoff, with_recording=False)

    await _purge_expired_call_data_async()

    await db.refresh(call)
    assert call.recording_purged_at is not None


async def test_purge_is_idempotent(db):
    org = await _make_org(db)
    old_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.CALL_DATA_RETENTION_DAYS + 1)
    call = await _make_call(db, org, created_at=old_cutoff)

    await _purge_expired_call_data_async()
    await db.refresh(call)
    first_purged_at = call.recording_purged_at

    await _purge_expired_call_data_async()  # must not error on a re-run
    await db.refresh(call)
    assert call.recording_purged_at == first_purged_at
