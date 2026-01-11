"""Shared Pydantic response models for API endpoints."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Basic health check response."""

    status: str = Field(description="Health status: healthy, degraded, or unhealthy")
    timestamp_ms: int = Field(description="Response timestamp in milliseconds")
    version: str = Field(description="Application version")
    checks: dict[str, bool] = Field(description="Individual health check results")


class DetailedHealthResponse(HealthResponse):
    """Detailed health check with system information."""

    system: dict[str, float | int | str] = Field(description="System metrics")


class StubResponse(BaseModel):
    """Response for stub endpoints."""

    message: str = Field(description="Stub message")
    endpoint: str = Field(description="Endpoint path")


class PaginatedResponse(BaseModel):
    """Base model for paginated responses."""

    total: int = Field(description="Total number of items")
    offset: int = Field(description="Current offset")
    limit: int = Field(description="Page size limit")
