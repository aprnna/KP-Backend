"""
Unit tests for app.services.scheduler_service — pure logic only.
Scheduler is not actually started; we test state-reading helpers
and the setup function's return value in isolation.
"""

from unittest.mock import MagicMock, patch

from app.services import scheduler_service
from app.services.scheduler_service import (
    get_scheduler,
    get_scheduler_status,
    start_scheduler,
    shutdown_scheduler,
)


class TestGetScheduler:
    def test_returns_none_when_not_initialised(self):
        original = scheduler_service.scheduler
        scheduler_service.scheduler = None
        try:
            assert get_scheduler() is None
        finally:
            scheduler_service.scheduler = original

    def test_returns_instance_when_set(self):
        mock_sched = MagicMock()
        original = scheduler_service.scheduler
        scheduler_service.scheduler = mock_sched
        try:
            assert get_scheduler() is mock_sched
        finally:
            scheduler_service.scheduler = original


class TestGetSchedulerStatus:
    def test_returns_disabled_when_none(self):
        original = scheduler_service.scheduler
        scheduler_service.scheduler = None
        try:
            status = get_scheduler_status()
            assert status["enabled"] is False
            assert status["running"] is False
            assert status["jobs"] == []
        finally:
            scheduler_service.scheduler = original

    def test_returns_running_status(self):
        mock_sched = MagicMock()
        mock_sched.running = True
        mock_sched.get_jobs.return_value = []
        original = scheduler_service.scheduler
        scheduler_service.scheduler = mock_sched
        try:
            status = get_scheduler_status()
            assert status["running"] is True
        finally:
            scheduler_service.scheduler = original


class TestStartScheduler:
    def test_starts_when_not_running(self):
        mock_sched = MagicMock()
        mock_sched.running = False
        original = scheduler_service.scheduler
        scheduler_service.scheduler = mock_sched
        try:
            start_scheduler()
            mock_sched.start.assert_called_once()
        finally:
            scheduler_service.scheduler = original

    def test_does_not_start_when_already_running(self):
        mock_sched = MagicMock()
        mock_sched.running = True
        original = scheduler_service.scheduler
        scheduler_service.scheduler = mock_sched
        try:
            start_scheduler()
            mock_sched.start.assert_not_called()
        finally:
            scheduler_service.scheduler = original


class TestShutdownScheduler:
    def test_shuts_down_when_running(self):
        mock_sched = MagicMock()
        mock_sched.running = True
        original = scheduler_service.scheduler
        scheduler_service.scheduler = mock_sched
        try:
            shutdown_scheduler()
            mock_sched.shutdown.assert_called_once_with(wait=False)
        finally:
            scheduler_service.scheduler = original

    def test_does_not_shutdown_when_not_running(self):
        mock_sched = MagicMock()
        mock_sched.running = False
        original = scheduler_service.scheduler
        scheduler_service.scheduler = mock_sched
        try:
            shutdown_scheduler()
            mock_sched.shutdown.assert_not_called()
        finally:
            scheduler_service.scheduler = original


class TestSetupScheduler:
    def test_returns_none_when_disabled(self):
        with patch("app.services.scheduler_service.settings") as mock_settings:
            mock_settings.scheduler_enabled = False
            result = scheduler_service.setup_scheduler()
            assert result is None

    def test_returns_scheduler_when_enabled(self):
        with patch("app.services.scheduler_service.settings") as mock_settings:
            mock_settings.scheduler_enabled = True
            mock_settings.scrape_day_of_month = 1
            with patch("app.services.scheduler_service.AsyncIOScheduler") as MockSched:
                mock_instance = MagicMock()
                MockSched.return_value = mock_instance
                result = scheduler_service.setup_scheduler()
                assert result is mock_instance
