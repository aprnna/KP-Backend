from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Basic app settings
    app_name: str = os.getenv("APP_NAME", "FastAPI Academic Scraper")
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    version: str = os.getenv("VERSION", "1.0.0")

    # Server settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", 8000))

    # CORS settings
    allowed_origins: str = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080"
    )

    # Security settings (production)
    allowed_hosts: str = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1")
    secret_key: str = os.getenv("SECRET_KEY", "change-this-in-production")

    # Database settings (MySQL)
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", 3306))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_name: str = os.getenv("DB_NAME", "academic_scraper")

    # API Security
    api_key: str = os.getenv("API_KEY", "")

    # Scheduler settings
    scheduler_enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    scrape_day_of_month: int = int(os.getenv("SCRAPE_DAY_OF_MONTH", 1))

    # Scraping Config
    year_start: int = int(os.getenv("YEAR_START", 2021))
    year_end: int = int(os.getenv("YEAR_END", 2026))

    # Authors API settings
    Authors_rows_per_request: int = 100
    Authors_max_offset: int = 10000
    Authors_request_delay: float = 0.5  # seconds
    Authors_max_retries: int = 3
    Authors_base_url: str = "https://sinta.kemdiktisaintek.go.id/affiliations/authors/528"

    # Articles API settings
    Articles_per_page: int = 10
    Articles_request_delay: float = 0.1  # seconds
    Articles_max_retries: int = 3
    Articles_base_url: str = "https://sinta.kemdiktisaintek.go.id/authors/profile"

    # Logging settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def database_url(self) -> str:
        """Sync database URL for SQLAlchemy"""
        return f"mysql+mysqlconnector://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def async_database_url(self) -> str:
        """Async database URL for SQLAlchemy with aiomysql"""
        return f"mysql+aiomysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated origins into list"""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def allowed_hosts_list(self) -> List[str]:
        """Parse comma-separated hosts into list"""
        return [host.strip() for host in self.allowed_hosts.split(",")]


settings = Settings()