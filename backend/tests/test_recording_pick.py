"""fetch_recording_for_call must hand each call its OWN recording, not the first one for that number."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.vobiz import fetch_recording_for_call

T0 = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)


def _rec(url: str, minutes: float) -> dict:
    return {"to_number": "917558791006", "recording_url": url, "add_time": (T0 + timedelta(minutes=minutes)).isoformat()}


class _Resp:
    status = 200

    def __init__(self, objs):
        self.objs = objs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return {"objects": self.objs, "meta": {"total_count": len(self.objs)}}


class _Http:
    def __init__(self, objs):
        self.objs = objs

    def get(self, *a, **k):
        return _Resp(self.objs)


async def _pick(objs, near_min, exclude=()):
    return await fetch_recording_for_call(
        _Http(objs), auth_id="a", auth_token="t", to_number="+917558791006", called_after=T0 - timedelta(minutes=30),
        retries=1, retry_delay=0, near=T0 + timedelta(minutes=near_min), exclude_urls=set(exclude))


@pytest.mark.asyncio
async def test_each_call_gets_the_recording_closest_to_it():
    objs = [_rec("A", 2), _rec("B", 5), _rec("C", 9)]  # oldest first, three test calls to one number
    assert await _pick(objs, 1) == "A"
    assert await _pick(objs, 4) == "B"
    assert await _pick(objs, 8) == "C"


@pytest.mark.asyncio
async def test_recordings_already_on_other_calls_are_skipped():
    objs = [_rec("A", 2), _rec("B", 3)]
    assert await _pick(objs, 2, exclude={"A"}) == "B"
    assert await _pick(objs, 2, exclude={"A", "B"}) is None
