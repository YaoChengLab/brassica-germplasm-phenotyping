import os
import logging
from pydantic_settings import BaseSettings
from typing import Optional

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    # Database settings
    database_url: str = os.getenv("DATABASE_URL", "")

    # Environment
    environment: str = os.getenv("ENVIRONMENT", "development")

    @property
    def management_enabled(self) -> bool:
        """Admin write features (batch/coordinate management) are enabled
        off-production only. The production VM is browse+analysis; management is
        done locally (coordinate placement needs the local 8T1 image archive).
        Set ENVIRONMENT=production on the VM to disable the /admin write API."""
        return self.environment.lower() != "production"

    # Redis settings
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # API settings
    api_v1_prefix: str = "/api/v1"
    project_name: str = "Plant Phenotyping Platform API"
    version: str = "1.0.0"

    # CORS settings
    backend_cors_origins: list = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ]

    # IP whitelist settings (server-side enforcement)
    # Comma-separated CIDR notation, e.g. "127.0.0.1/32,::1/128"
    allowed_ip_cidrs: str = os.getenv("ALLOWED_IP_CIDRS", "127.0.0.1/32,::1/128")
    # Paths exempt from IP restriction (no leading /api/v1 prefix needed)
    ip_whitelist_exempt_paths: list = ["/health", "/"]

    # Data directory settings.
    logs_dir: str = os.getenv("LOGS_DIR", "/app/logs")
    csv_import_dir: str = os.getenv("CSV_DATA_DIR", "/data/csv-import")

    def __init__(self, **data):
        super().__init__(**data)

        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is not set. Please configure it in environment variables or .env file."
            )

    class Config:
        case_sensitive = False
        env_file = ".env"

settings = Settings()
