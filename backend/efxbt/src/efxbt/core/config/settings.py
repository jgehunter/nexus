"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support.

    All settings can be overridden via environment variables with the EFXBT_ prefix.
    Example: EFXBT_HOST=0.0.0.0 sets host to 0.0.0.0
    """

    model_config = SettingsConfigDict(
        env_prefix="EFXBT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server configuration
    host: Annotated[str, Field(description="Server bind host")] = "127.0.0.1"
    port: Annotated[int, Field(description="Server bind port", ge=1, le=65535)] = 8000
    debug: Annotated[bool, Field(description="Enable debug mode")] = True

    # CORS configuration for local development
    cors_origins: Annotated[
        list[str], Field(description="Allowed CORS origins")
    ] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Data paths (relative to backend/efxbt or absolute)
    data_root: Annotated[
        str, Field(description="Root directory for datasets")
    ] = "../../data"
    results_root: Annotated[
        str, Field(description="Root directory for run results")
    ] = "../../results"

    # Run retention settings
    run_retention_days: Annotated[
        int,
        Field(
            description="Days to retain completed runs (0 = forever)",
            ge=0,
        ),
    ] = 30
    max_runs_stored: Annotated[
        int,
        Field(
            description="Maximum runs to keep (oldest deleted first, 0 = unlimited)",
            ge=0,
        ),
    ] = 100

    # Orchestration settings
    max_parallel_workers: Annotated[
        int,
        Field(
            description="Maximum parallel workers for run execution",
            ge=1,
            le=32,
        ),
    ] = 4

    @property
    def data_path(self) -> Path:
        """Resolved absolute path to data directory."""
        return Path(self.data_root).resolve()

    @property
    def results_path(self) -> Path:
        """Resolved absolute path to results directory."""
        return Path(self.results_root).resolve()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
