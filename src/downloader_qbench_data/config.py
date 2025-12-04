"""Application configuration helpers for environment-driven settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError


class QBenchSettings(BaseModel):
    """Holds credentials and endpoints for QBench API access."""

    base_url: str
    client_id: str
    client_secret: str
    token_url: Optional[str] = None


class DatabaseSettings(BaseModel):
    """Settings required to connect to PostgreSQL."""

    host: str = "localhost"
    port: int = 5432
    name: str
    user: str
    password: str

    def build_sqlalchemy_url(self) -> str:
        """Compose a SQLAlchemy connection URL."""

        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class AppSettings(BaseModel):
    """Aggregated application settings."""

    qbench: QBenchSettings
    database: DatabaseSettings
    auth: "AuthSettings"
    page_size: int = 50
    sync_lookback_days: int = 7


class AuthSettings(BaseModel):
    """Authentication-related settings."""

    secret_key: str
    token_ttl_hours: int = 3


def _load_from_environment() -> AppSettings:
    """Load settings using environment variables and .env file."""

    module_path = Path(__file__).resolve()
    project_root = module_path.parents[2]
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=True, encoding="utf-8-sig")
    load_dotenv(override=False)  # Secondary search path (current working dir)
    try:
        qbench = QBenchSettings(
            base_url=os.environ["QBENCH_BASE_URL"],
            client_id=os.environ["QBENCH_CLIENT_ID"],
            client_secret=os.environ["QBENCH_CLIENT_SECRET"],
            token_url=os.getenv("QBENCH_TOKEN_URL"),
        )
        database = DatabaseSettings(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            name=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
        auth = AuthSettings(
            secret_key=os.environ["AUTH_SECRET_KEY"],
            token_ttl_hours=int(os.getenv("AUTH_TOKEN_TTL_HOURS", "3")),
        )
        page_size = int(os.getenv("PAGE_SIZE", "50"))
        sync_lookback_days = int(os.getenv("SYNC_LOOKBACK_DAYS", "7"))
    except KeyError as exc:
        missing = exc.args[0]
        raise RuntimeError(f"Missing required environment variable: {missing}") from exc
    except ValidationError as exc:
        raise RuntimeError(f"Environment configuration is invalid: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Environment configuration has invalid numeric value: {exc}") from exc
    return AppSettings(
        qbench=qbench,
        database=database,
        auth=auth,
        page_size=page_size,
        sync_lookback_days=sync_lookback_days,
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""

    return _load_from_environment()
