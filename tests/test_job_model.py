"""
Unit tests for app.models.job -- enums and ScrapingJob computed properties.
No database connection required; properties are pure Python.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.models.job import JobStatus, JobSource, LogLevel, ScrapingJob


class TestJobStatusEnum:
    def test_all_terminal_states_present(self):
        """Reliability rule: jobs must end in a terminal state."""
        values = {e.value for e in JobStatus}
        assert "pending" in values
        assert "running" in values
        assert "finished" in values
        assert "failed" in values

    def test_is_string_enum(self):
        assert isinstance(JobStatus.PENDING, str)


class TestJobSourceEnum:
    def test_values(self):
        assert JobSource.SINTA_ARTICLES == "sinta_articles"
        assert JobSource.SINTA_AUTHORS == "sinta_authors"
        assert JobSource.BOTH == "both"


class TestLogLevelEnum:
    def test_values(self):
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"


# ---------------------------------------------------------------------------
# Pure-Python property tests.
#
# ScrapingJob.progress_percentage and duration_seconds are plain @property
# definitions that only read primitive instance attributes.  We call them via
# `fget` on a SimpleNamespace so SQLAlchemy ORM instrumentation is never
# triggered (no DB session, no mapped state machine).
# ---------------------------------------------------------------------------

_progress_pct = ScrapingJob.progress_percentage.fget
_duration_secs = ScrapingJob.duration_seconds.fget


def _job(total: int = 0, processed: int = 0, started_at=None, finished_at=None):
    """Return a plain namespace that satisfies the properties' attribute reads."""
    return SimpleNamespace(
        total_records=total,
        processed_records=processed,
        started_at=started_at,
        finished_at=finished_at,
    )


class TestScrapingJobProgressPercentage:
    def test_zero_total_returns_zero(self):
        assert _progress_pct(_job(total=0, processed=0)) == 0.0

    def test_full_progress(self):
        assert _progress_pct(_job(total=100, processed=100)) == 100.0

    def test_partial_progress(self):
        assert _progress_pct(_job(total=200, processed=50)) == 25.0

    def test_result_is_float(self):
        result = _progress_pct(_job(total=4, processed=1))
        assert isinstance(result, float)


class TestScrapingJobDurationSeconds:
    def test_none_when_not_started(self):
        assert _duration_secs(_job(started_at=None)) is None

    def test_duration_with_finished_at(self):
        start = datetime(2024, 1, 1, 12, 0, 0)
        finish = datetime(2024, 1, 1, 12, 0, 30)
        assert _duration_secs(_job(started_at=start, finished_at=finish)) == 30.0

    def test_duration_still_running_is_positive(self):
        """If finished_at is None, duration is measured from now."""
        start = datetime.utcnow() - timedelta(seconds=5)
        duration = _duration_secs(_job(started_at=start, finished_at=None))
        assert duration is not None
        assert duration >= 5.0
