"""Health check endpoints."""

import psutil
from fastapi import APIRouter

from ....core.config import Defaults
from ....core.data.duck import check_duckdb_health, get_duckdb_version
from ....util.time import now_ms
from ..models import DetailedHealthResponse, HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Basic health check.

    Returns service status and verifies core dependencies are operational.
    """
    checks = {
        "duckdb": check_duckdb_health(),
    }

    # Determine overall status
    if all(checks.values()):
        status = "healthy"
    elif any(checks.values()):
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        timestamp_ms=now_ms(),
        version=Defaults.VERSION,
        checks=checks,
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def get_detailed_health() -> DetailedHealthResponse:
    """Detailed health check with system metrics.

    Returns service status, dependency checks, and system resource information.
    """
    checks = {
        "duckdb": check_duckdb_health(),
    }

    # Determine overall status
    if all(checks.values()):
        status = "healthy"
    elif any(checks.values()):
        status = "degraded"
    else:
        status = "unhealthy"

    # Gather system metrics
    memory = psutil.virtual_memory()

    return DetailedHealthResponse(
        status=status,
        timestamp_ms=now_ms(),
        version=Defaults.VERSION,
        checks=checks,
        system={
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": memory.percent,
            "memory_available_mb": memory.available // (1024 * 1024),
            "duckdb_version": get_duckdb_version(),
        },
    )
