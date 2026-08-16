"""
app/storage/backend.py — Object storage abstraction (MinIO / AWS S3).

Both backends use the same boto3 S3 API since MinIO is S3-compatible.
Sync boto3 calls are run in a thread pool via asyncio.to_thread so the
event loop is never blocked.

Six buckets are created on startup if they don't exist:
  motm-recordings    — call recordings (set by LiveKit egress, URL stored in DB)
  motm-exports       — generated Excel export files
  motm-transcripts   — raw transcript JSON blobs
  motm-backups       — database backup archives
  motm-voice-consent — voice-cloning audio samples + consent videos (pending review)
  motm-invoices      — generated GST tax invoice PDFs (app/core/invoicing.py)
"""
from __future__ import annotations

import asyncio
import functools
import io
from datetime import datetime
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.exceptions import ClientError

from app.config import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = structlog.get_logger(__name__)


class StorageBackend:
    def __init__(self) -> None:
        if settings.STORAGE_BACKEND == "minio":
            scheme = "https" if settings.MINIO_SECURE else "http"
            endpoint_url = f"{scheme}://{settings.MINIO_ENDPOINT}"
            access_key = settings.MINIO_ACCESS_KEY
            secret_key = settings.MINIO_SECRET_KEY
            region = "us-east-1"          # MinIO ignores region but boto3 requires one
        else:
            endpoint_url = None           # boto3 resolves the AWS endpoint automatically
            access_key = settings.AWS_ACCESS_KEY_ID
            secret_key = settings.AWS_SECRET_ACCESS_KEY
            region = settings.AWS_REGION

        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            use_ssl=settings.MINIO_SECURE if settings.STORAGE_BACKEND == "minio" else True,
        )
        self._buckets = [
            settings.BUCKET_RECORDINGS,
            settings.BUCKET_EXPORTS,
            settings.BUCKET_TRANSCRIPTS,
            settings.BUCKET_BACKUPS,
            settings.BUCKET_VOICE_CONSENT,
            settings.BUCKET_INVOICES,
        ]

    async def ensure_buckets(self) -> None:
        """Create all required buckets if they don't exist. Called at startup."""
        for bucket in self._buckets:
            try:
                await asyncio.to_thread(self._client.head_bucket, Bucket=bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("404", "NoSuchBucket"):
                    kwargs: dict = {"Bucket": bucket}
                    # S3 requires LocationConstraint for non-us-east-1 regions
                    if (
                        settings.STORAGE_BACKEND == "s3"
                        and settings.AWS_REGION != "us-east-1"
                    ):
                        kwargs["CreateBucketConfiguration"] = {
                            "LocationConstraint": settings.AWS_REGION
                        }
                    await asyncio.to_thread(
                        functools.partial(self._client.create_bucket, **kwargs)
                    )
                    log.info("storage_bucket_created", bucket=bucket)
                elif code == "403":
                    # Bucket exists but we lack HeadBucket permission — treat as existing
                    log.warning("storage_bucket_no_head_permission", bucket=bucket)
                else:
                    raise

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes and return the object key."""
        await asyncio.to_thread(
            functools.partial(
                self._client.upload_fileobj,
                io.BytesIO(data),
                bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        )
        log.debug("storage_upload_ok", bucket=bucket, key=key, size=len(data))
        return key

    async def presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int | None = None,
    ) -> str:
        """Generate a presigned GET URL valid for `expiry` seconds."""
        expiry = expiry if expiry is not None else settings.EXPORT_URL_EXPIRY_SECONDS
        url: str = await asyncio.to_thread(
            functools.partial(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiry,
            )
        )
        return url

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's bytes (e.g. to re-feed a stored sample to an external API)."""
        buf = io.BytesIO()
        await asyncio.to_thread(
            functools.partial(self._client.download_fileobj, bucket, key, buf)
        )
        return buf.getvalue()

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(
            functools.partial(self._client.delete_object, Bucket=bucket, Key=key)
        )
        log.debug("storage_delete_ok", bucket=bucket, key=key)

    async def list_keys_older_than(self, bucket: str, prefix: str, cutoff: datetime) -> list[str]:
        """Keys under `prefix` last modified before `cutoff` (UTC) — used to prune old
        backups (see app/workers/tasks/backup.py) without growing storage forever."""
        def _list() -> list[str]:
            keys: list[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if obj["LastModified"] < cutoff:
                        keys.append(obj["Key"])
            return keys

        return await asyncio.to_thread(_list)

    async def exists(self, bucket: str, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=bucket, Key=key
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        _storage = StorageBackend()
    return _storage
