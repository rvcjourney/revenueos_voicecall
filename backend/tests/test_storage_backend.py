"""
tests/test_storage_backend.py — app/storage/backend.py's SSE-C (server-side
encryption with a customer-provided key) wiring.

No real MinIO/S3 in tests: boto3.client() is monkeypatched to a MagicMock so
these only assert on what StorageBackend actually asks boto3 to do, not on
a real object store's behavior.
"""
from __future__ import annotations

import base64
import secrets
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from app.config import Settings, settings
from app.storage.backend import StorageBackend

_VALID_KEY_B64 = base64.b64encode(secrets.token_bytes(32)).decode()


def _make_backend(monkeypatch, *, sse_key_b64: str = "") -> tuple[StorageBackend, MagicMock]:
    monkeypatch.setattr(settings, "STORAGE_SSE_C_KEY_B64", sse_key_b64)
    fake_client = MagicMock()
    with patch("app.storage.backend.boto3.client", return_value=fake_client):
        backend = StorageBackend()
    return backend, fake_client


# ── Config validation ───────────────────────────────────────────────────────

def test_sse_key_blank_is_valid():
    overrides = settings.model_dump()
    overrides["STORAGE_SSE_C_KEY_B64"] = ""
    Settings(**overrides)  # must not raise


def test_sse_key_rejects_invalid_base64():
    overrides = settings.model_dump()
    overrides["STORAGE_SSE_C_KEY_B64"] = "not valid base64!!!"
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_sse_key_rejects_wrong_length():
    overrides = settings.model_dump()
    overrides["STORAGE_SSE_C_KEY_B64"] = base64.b64encode(b"too-short").decode()
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_sse_key_accepts_valid_32_byte_key():
    overrides = settings.model_dump()
    overrides["STORAGE_SSE_C_KEY_B64"] = _VALID_KEY_B64
    Settings(**overrides)  # must not raise


# ── StorageBackend wiring ────────────────────────────────────────────────────

def test_sse_args_empty_when_unconfigured(monkeypatch):
    backend, _client = _make_backend(monkeypatch, sse_key_b64="")
    assert backend._sse_args() == {}


def test_sse_args_present_when_configured(monkeypatch):
    backend, _client = _make_backend(monkeypatch, sse_key_b64=_VALID_KEY_B64)
    args = backend._sse_args()
    assert args["SSECustomerAlgorithm"] == "AES256"
    assert args["SSECustomerKey"] == base64.b64decode(_VALID_KEY_B64)


async def test_upload_passes_sse_extra_args_when_configured(monkeypatch):
    backend, client = _make_backend(monkeypatch, sse_key_b64=_VALID_KEY_B64)
    await backend.upload("bucket", "key", b"hello", content_type="text/plain")

    client.upload_fileobj.assert_called_once()
    extra_args = client.upload_fileobj.call_args.kwargs["ExtraArgs"]
    assert extra_args["ContentType"] == "text/plain"
    assert extra_args["SSECustomerAlgorithm"] == "AES256"
    assert extra_args["SSECustomerKey"] == base64.b64decode(_VALID_KEY_B64)


async def test_upload_omits_sse_args_when_unconfigured(monkeypatch):
    backend, client = _make_backend(monkeypatch, sse_key_b64="")
    await backend.upload("bucket", "key", b"hello")

    extra_args = client.upload_fileobj.call_args.kwargs["ExtraArgs"]
    assert "SSECustomerAlgorithm" not in extra_args


async def test_download_uses_sse_args_when_configured(monkeypatch):
    backend, client = _make_backend(monkeypatch, sse_key_b64=_VALID_KEY_B64)
    client.download_fileobj = MagicMock()

    await backend.download("bucket", "key")

    client.download_fileobj.assert_called_once()
    extra_args = client.download_fileobj.call_args.kwargs["ExtraArgs"]
    assert extra_args["SSECustomerAlgorithm"] == "AES256"


async def test_download_falls_back_for_pre_encryption_objects(monkeypatch):
    """An object uploaded before STORAGE_SSE_C_KEY_B64 was set has no SSE-C
    metadata -- S3/MinIO reject an SSE-C-headered request against it with
    InvalidArgument. download() must retry without the SSE-C headers instead
    of surfacing that as a hard failure."""
    backend, client = _make_backend(monkeypatch, sse_key_b64=_VALID_KEY_B64)

    calls: list[dict] = []

    def _download_fileobj(bucket, key, fileobj, ExtraArgs=None):
        calls.append(ExtraArgs or {})
        if ExtraArgs:  # first attempt, with SSE-C headers -> simulate a plaintext object
            raise ClientError(
                {"Error": {"Code": "InvalidArgument", "Message": "not SSE-C encrypted"}},
                "GetObject",
            )
        fileobj.write(b"plaintext-object-bytes")

    client.download_fileobj = MagicMock(side_effect=_download_fileobj)

    result = await backend.download("bucket", "key")

    assert result == b"plaintext-object-bytes"
    assert len(calls) == 2
    assert "SSECustomerAlgorithm" in calls[0]
    assert calls[1] == {}


async def test_download_reraises_non_invalidargument_errors(monkeypatch):
    backend, client = _make_backend(monkeypatch, sse_key_b64=_VALID_KEY_B64)
    client.download_fileobj = MagicMock(
        side_effect=ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "GetObject")
    )

    with pytest.raises(ClientError):
        await backend.download("bucket", "key")


async def test_presigned_url_raises_when_sse_c_configured(monkeypatch):
    backend, _client = _make_backend(monkeypatch, sse_key_b64=_VALID_KEY_B64)
    with pytest.raises(NotImplementedError):
        await backend.presigned_url("bucket", "key")
