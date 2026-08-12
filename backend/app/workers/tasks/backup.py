"""
app/workers/tasks/backup.py — Database backup (pg_dump) to object storage.

Runs pg_dump against DATABASE_URL and uploads the compressed dump to the
existing motm-backups bucket (StorageBackend, app/storage/backend.py) — that
bucket was declared and auto-created on startup but nothing ever wrote to it,
so it looked like a backup system without being one.

When STORAGE_BACKEND=minio (the production default — see docker-compose.yml)
that bucket lives on this same VPS's disk, so it protects against a bad
migration or an accidental DELETE, but NOT against the VPS/disk itself
failing. OFFSITE_BACKUP_* settings (app/config.py), once configured, also
push a copy to a genuinely separate off-VPS S3-compatible bucket (AWS S3 /
Backblaze B2 / Cloudflare R2 / Wasabi all work) for real disaster recovery —
until then this task still runs and still protects against the more common
failure (a bad deploy/migration/DELETE), just not a lost VPS.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import structlog

from app.config import settings
from app.storage.backend import get_storage
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)

_DUMP_PREFIX = "db-backups/"


def _pg_dump_to_file(dest_path: Path) -> None:
    """
    Runs in a thread (subprocess.run is blocking). DATABASE_URL uses the
    asyncpg driver scheme (postgresql+asyncpg://), which pg_dump's own URL
    parsing doesn't understand, so this connects via discrete -h/-p/-U/-d
    flags instead. The password goes through PGPASSWORD, not argv — argv is
    visible to anything reading this process's command line (e.g. another
    unix user running `ps aux` on the same VPS).

    urlsplit()'s .username/.password are NOT percent-decoded (confirmed:
    urlsplit("postgresql://u:%25%29%26p@host/db").password ==
    "%25%29%26p", the literal encoded string, not "%)&p") -- Supabase
    connection strings routinely contain URL-reserved characters in the
    password (%, &, +, ) etc.), so without unquote() here pg_dump would
    authenticate with the wrong password and fail every single run.
    """
    parsed = urlsplit(settings.DATABASE_URL.replace("+asyncpg", ""))
    env = {**os.environ, "PGPASSWORD": unquote(parsed.password) if parsed.password else ""}
    cmd = [
        "pg_dump",
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", unquote(parsed.username) if parsed.username else "postgres",
        "-d", (parsed.path or "/postgres").lstrip("/"),
        "-Fc",  # custom format: compressed, restorable with pg_restore, supports selective restore
        "-f", str(dest_path),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {result.stderr[-2000:]}")


async def _upload_offsite(key: str, data: bytes) -> None:
    """No-op unless OFFSITE_BACKUP_ENDPOINT_URL/BUCKET are configured (app/config.py)."""
    if not settings.OFFSITE_BACKUP_ENDPOINT_URL or not settings.OFFSITE_BACKUP_BUCKET:
        return
    import boto3

    def _put() -> None:
        client = boto3.client(
            "s3",
            endpoint_url=settings.OFFSITE_BACKUP_ENDPOINT_URL,
            aws_access_key_id=settings.OFFSITE_BACKUP_ACCESS_KEY,
            aws_secret_access_key=settings.OFFSITE_BACKUP_SECRET_KEY,
            region_name=settings.OFFSITE_BACKUP_REGION,
        )
        client.put_object(Bucket=settings.OFFSITE_BACKUP_BUCKET, Key=key, Body=data)

    await asyncio.to_thread(_put)


async def _prune_offsite_old_backups(cutoff: datetime) -> None:
    if not settings.OFFSITE_BACKUP_ENDPOINT_URL or not settings.OFFSITE_BACKUP_BUCKET:
        return
    import boto3

    def _prune() -> list[str]:
        client = boto3.client(
            "s3",
            endpoint_url=settings.OFFSITE_BACKUP_ENDPOINT_URL,
            aws_access_key_id=settings.OFFSITE_BACKUP_ACCESS_KEY,
            aws_secret_access_key=settings.OFFSITE_BACKUP_SECRET_KEY,
            region_name=settings.OFFSITE_BACKUP_REGION,
        )
        deleted: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.OFFSITE_BACKUP_BUCKET, Prefix=_DUMP_PREFIX):
            for obj in page.get("Contents", []):
                if obj["LastModified"] < cutoff:
                    client.delete_object(Bucket=settings.OFFSITE_BACKUP_BUCKET, Key=obj["Key"])
                    deleted.append(obj["Key"])
        return deleted

    for key in await asyncio.to_thread(_prune):
        log.info("backup_pruned_offsite", key=key)


async def _run_backup_async() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{_DUMP_PREFIX}motmvoice-{ts}.dump"

    with tempfile.TemporaryDirectory() as tmp:
        dump_path = Path(tmp) / "backup.dump"
        await asyncio.to_thread(_pg_dump_to_file, dump_path)
        data = dump_path.read_bytes()

    log.info("backup_dump_created", key=key, size_bytes=len(data))

    storage = get_storage()
    await storage.upload(settings.BUCKET_BACKUPS, key, data, content_type="application/octet-stream")
    log.info("backup_uploaded_local", key=key, bucket=settings.BUCKET_BACKUPS)

    try:
        await _upload_offsite(key, data)
        if settings.OFFSITE_BACKUP_ENDPOINT_URL:
            log.info("backup_uploaded_offsite", key=key, bucket=settings.OFFSITE_BACKUP_BUCKET)
    except Exception as exc:
        # The local backup already succeeded — an offsite failure shouldn't
        # mark the whole task failed and trigger Celery retrying a pg_dump
        # that already worked.
        log.error("backup_offsite_upload_failed", key=key, error=str(exc))

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BACKUP_RETENTION_DAYS)
    storage_for_prune = get_storage()
    for old_key in await storage_for_prune.list_keys_older_than(settings.BUCKET_BACKUPS, _DUMP_PREFIX, cutoff):
        await storage_for_prune.delete(settings.BUCKET_BACKUPS, old_key)
        log.info("backup_pruned_local", key=old_key)
    await _prune_offsite_old_backups(cutoff)


@celery_app.task(name="app.workers.tasks.backup.run_database_backup", bind=True)
def run_database_backup(self) -> None:
    """Beat task (daily): pg_dump the database and upload it to object storage."""
    asyncio.run(_run_backup_async())
