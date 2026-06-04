"""
app/workers/celery_app.py — Celery application factory.

One worker process handles campaign dispatch. Concurrency is intentionally
low (matches the number of simultaneous campaigns, not simultaneous calls —
calls within a campaign are sequential).
"""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "motmvoice",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.campaign"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Re-queue task if the worker process dies while the task is running.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Fetch only one task at a time — campaign tasks are long-running and we
    # don't want a worker to pre-fetch a second campaign task it can't start.
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Every 60 s: restart any RUNNING campaign whose dispatcher has died.
        "resume-stalled-campaigns": {
            "task": "app.workers.tasks.campaign.resume_stalled_campaigns",
            "schedule": 60.0,
        },
        # Every 60 s: auto-launch SCHEDULED campaigns whose start_time has passed.
        "launch-scheduled-campaigns": {
            "task": "app.workers.tasks.campaign.launch_scheduled_campaigns",
            "schedule": 60.0,
        },
    },
)
