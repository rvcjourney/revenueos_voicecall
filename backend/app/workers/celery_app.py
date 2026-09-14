"""
app/workers/celery_app.py — Celery application factory.

One worker process handles campaign dispatch. Concurrency is intentionally
low (matches the number of simultaneous campaigns, not simultaneous calls —
calls within a campaign are sequential).
"""
from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init, worker_process_init

from app.config import settings

celery_app = Celery(
    "motmvoice",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.campaign", "app.workers.tasks.billing",
        "app.workers.tasks.backup", "app.workers.tasks.retention",
        "app.workers.tasks.integrations",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Celery's built-in default queue is literally named "celery" — distinct from
    # the "default" queue the worker listens to (see docker-compose.yml:
    # `--queues calls,campaigns,exports,default`). Any task dispatched without an
    # explicit queue= (both beat_schedule entries below, and run_campaign.delay()
    # in app/workers/tasks/campaign.py) would otherwise silently land in "celery",
    # which nothing consumes, and pile up in the broker forever.
    task_default_queue="default",
    # Re-queue task if the worker process dies while the task is running.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Fetch only one task at a time — campaign tasks are long-running and we
    # don't want a worker to pre-fetch a second campaign task it can't start.
    worker_prefetch_multiplier=1,
    # Both default to True, and both fight the custom structlog setup this
    # app wires in via worker_process_init/beat_init below (app/core/logging.
    # py's configure_logging()) -- confirmed live: with these left at their
    # defaults, that setup silently produced zero visible output in
    # `docker compose logs`, no exception either, even though calling the
    # handler directly worked fine in isolation.
    #   worker_hijack_root_logger: Celery reconfigures the root logger AFTER
    #     worker_process_init fires, discarding whatever handler we just
    #     attached to it.
    #   worker_redirect_stdouts: Celery replaces sys.stdout/sys.stderr with
    #     its own proxy that routes writes into Celery's own logger. Our
    #     handler is built as logging.StreamHandler(sys.stdout) INSIDE
    #     configure_logging() -- if that runs after Celery's redirect has
    #     already swapped sys.stdout for its proxy, every write loops back
    #     into Celery's logging instead of reaching the real stream.
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
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
        # Daily: correct any Subscription/org state that drifted from a missed
        # Razorpay webhook (see app/workers/tasks/billing.py).
        "reconcile-razorpay-subscriptions": {
            "task": "app.workers.tasks.billing.reconcile_razorpay_subscriptions",
            "schedule": 86400.0,
        },
        # Hourly: cut org.is_active for any subscription whose period ended
        # more than BILLING_GRACE_PERIOD_DAYS ago with no renewal charge --
        # backstop independent of Razorpay ever telling us (see
        # app/workers/tasks/billing.py's module docstring).
        "expire-lapsed-subscriptions": {
            "task": "app.workers.tasks.billing.expire_lapsed_subscriptions",
            "schedule": 3600.0,
        },
        # Every 5 min: log any COMPLETED call still stuck at outcome=PENDING
        # (agent-report never arrived) so it doesn't go unnoticed indefinitely.
        "flag-stale-pending-calls": {
            "task": "app.workers.tasks.campaign.flag_stale_pending_calls",
            "schedule": 300.0,
        },
        # Every 5 min: re-attempt CRM/webhook deliveries whose backoff has
        # elapsed. Same division of labour as the campaign tasks -- the push
        # task itself is max_retries=0 and this sweeper owns re-queuing.
        "retry-integration-deliveries": {
            "task": "app.workers.tasks.integrations.retry_failed_deliveries",
            "schedule": 300.0,
        },
        # Daily at 02:17 UTC (quiet hour, avoids the top-of-hour pile-up with
        # every other cron on the box): pg_dump the database to object storage
        # (+ an offsite bucket if OFFSITE_BACKUP_* is configured). See
        # app/workers/tasks/backup.py.
        "run-database-backup": {
            "task": "app.workers.tasks.backup.run_database_backup",
            "schedule": crontab(minute=17, hour=2),
        },
        # Offset an hour after the DB backup above so the two I/O-heavy tasks
        # don't overlap. No-op until OFFSITE_BACKUP_* is configured.
        "sync-storage-offsite": {
            "task": "app.workers.tasks.backup.sync_storage_offsite",
            "schedule": crontab(minute=0, hour=3),
        },
        # Offset another hour after the offsite sync above -- runs after
        # anything that day's backup/sync would still want to see the
        # not-yet-purged data. See app/workers/tasks/retention.py.
        "purge-expired-call-data": {
            "task": "app.workers.tasks.retention.purge_expired_call_data",
            "schedule": crontab(minute=0, hour=4),
        },
    },
)


# app/main.py (the API process) has always called configure_logging() +
# sentry_sdk.init() on its own startup, but nothing ever did the same for the
# worker/beat processes. Two consequences, now fixed here:
#   - structlog was never routed through the stdlib logging bridge in these
#     processes (app/core/logging.py's configure_logging(), whose own
#     docstring already lists "celery" as one of the loggers it bridges --
#     designed to be shared, just never actually wired up here).
#   - Sentry was never initialized at all in these processes, so every task
#     error -- including the deliberate log.error() fail-open branches in
#     app/workers/tasks/campaign.py, meant to be alerting-visible -- was
#     invisible to it even once the logging bridge above is fixed, since
#     Sentry's LoggingIntegration only captures logging records in a process
#     that has actually called sentry_sdk.init().
# worker_process_init fires once per forked prefork child (the worker itself,
# not a per-task hook); beat_init fires once for the scheduler process.
def _init_worker_logging_and_sentry(*, component: str) -> None:
    from app.core.logging import configure_logging
    configure_logging()

    from sentry_sdk.integrations.celery import CeleryIntegration

    from app.core.sentry import init_sentry
    init_sentry(integrations=[CeleryIntegration()], component=component)


@worker_process_init.connect
def _on_worker_process_init(**kwargs) -> None:
    _init_worker_logging_and_sentry(component="worker")


@beat_init.connect
def _on_beat_init(**kwargs) -> None:
    _init_worker_logging_and_sentry(component="beat")
