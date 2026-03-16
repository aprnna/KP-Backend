"""
Unit tests for app.core.config — Settings defaults and computed properties.
Uses default (env-less) values only; no .env file needed.
"""

import os
import pytest
from app.core.config import Settings


@pytest.fixture
def default_settings() -> Settings:
    """Return a Settings instance with no real .env influence."""
    env_overrides = {
        "APP_NAME": "FastAPI Academic Scraper",
        "ENVIRONMENT": "development",
        "DEBUG": "true",
        "SCRAPE_DAY_OF_MONTH": "1",
        "SCHEDULER_ENABLED": "true",
        "ALLOWED_ORIGINS": "http://localhost:3000,http://localhost:8080",
        "ALLOWED_HOSTS": "localhost,127.0.0.1",
    }
    for key, value in env_overrides.items():
        os.environ.setdefault(key, value)
    return Settings()


class TestSettingsDefaults:
    def test_app_name_has_value(self, default_settings: Settings):
        assert default_settings.app_name

    def test_environment_default(self, default_settings: Settings):
        assert default_settings.environment in ("development", "production", "staging")

    def test_scrape_day_in_valid_range(self, default_settings: Settings):
        assert 1 <= default_settings.scrape_day_of_month <= 31

    def test_sinta_request_delay_positive(self, default_settings: Settings):
        assert default_settings.sinta_request_delay > 0

    def test_sinta_max_retries_positive(self, default_settings: Settings):
        assert default_settings.sinta_max_retries > 0

    def test_sinta_affiliation_id_positive(self, default_settings: Settings):
        assert default_settings.sinta_affiliation_id > 0


class TestSettingsComputedProperties:
    def test_is_development(self, default_settings: Settings):
        assert default_settings.is_development == (
            default_settings.environment.lower() == "development"
        )

    def test_is_production(self, default_settings: Settings):
        assert default_settings.is_production == (
            default_settings.environment.lower() == "production"
        )

    def test_allowed_origins_list_is_list(self, default_settings: Settings):
        result = default_settings.allowed_origins_list
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_allowed_origins_list_strips_whitespace(self):
        s = Settings(allowed_origins=" http://a.com , http://b.com ")
        origins = s.allowed_origins_list
        assert all(o == o.strip() for o in origins)

    def test_allowed_hosts_list_is_list(self, default_settings: Settings):
        result = default_settings.allowed_hosts_list
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_database_url_contains_host(self, default_settings: Settings):
        url = default_settings.database_url
        assert default_settings.db_host in url

    def test_async_database_url_uses_aiomysql(self, default_settings: Settings):
        url = default_settings.async_database_url
        assert "aiomysql" in url
