"""
tests/test_sentry_init.py — app/core/sentry.py + the Celery worker/beat
Sentry+logging wiring in app/workers/celery_app.py.

Previously only app/main.py (the API process) initialized Sentry -- the
worker and beat processes never did, so every task error (including the
deliberate log.error() Redis-fail-open branches in
app/workers/tasks/campaign.py) was invisible to it.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.config import settings
from app.core.sentry import init_sentry


def test_init_sentry_noop_when_dsn_unset(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    with patch("app.core.sentry.sentry_sdk.init") as mock_init:
        init_sentry(integrations=[], component="test")
    mock_init.assert_not_called()


def test_init_sentry_initializes_when_dsn_set(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@sentry.example/1")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    fake_integration = object()
    with patch("app.core.sentry.sentry_sdk.init") as mock_init:
        init_sentry(integrations=[fake_integration], component="worker")
    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://fake@sentry.example/1"
    assert kwargs["environment"] == "production"
    assert kwargs["integrations"] == [fake_integration]
    assert kwargs["send_default_pii"] is False


def test_worker_process_init_configures_logging_and_sentry(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@sentry.example/1")
    import app.workers.celery_app as celery_app_module

    with patch("app.core.logging.configure_logging") as mock_configure, \
         patch("app.core.sentry.init_sentry") as mock_init_sentry:
        celery_app_module._on_worker_process_init()

    mock_configure.assert_called_once()
    mock_init_sentry.assert_called_once()
    assert mock_init_sentry.call_args.kwargs["component"] == "worker"


def test_beat_init_configures_logging_and_sentry(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@sentry.example/1")
    import app.workers.celery_app as celery_app_module

    with patch("app.core.logging.configure_logging") as mock_configure, \
         patch("app.core.sentry.init_sentry") as mock_init_sentry:
        celery_app_module._on_beat_init()

    mock_configure.assert_called_once()
    mock_init_sentry.assert_called_once()
    assert mock_init_sentry.call_args.kwargs["component"] == "beat"


def test_worker_and_beat_signals_are_connected():
    from celery.signals import beat_init, worker_process_init
    import app.workers.celery_app  # noqa: F401 -- ensures @signal.connect decorators ran

    assert len(worker_process_init.receivers) > 0
    assert len(beat_init.receivers) > 0
