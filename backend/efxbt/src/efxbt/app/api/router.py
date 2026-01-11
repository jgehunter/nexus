"""Main API router aggregating all endpoint routers."""

from fastapi import APIRouter

from .endpoints import (
    data_health,
    datasets,
    decross,
    health,
    results,
    runs,
    sweeps,
    tradebooks,
)


api_router = APIRouter(prefix="/api/v1")

# Health endpoints (no prefix - directly under /api/v1)
api_router.include_router(health.router)

# Resource endpoints with prefixes
api_router.include_router(datasets.router, prefix="/datasets")
api_router.include_router(tradebooks.router, prefix="/tradebooks")
api_router.include_router(data_health.router, prefix="/data-health")
api_router.include_router(decross.router, prefix="/decross")
api_router.include_router(runs.router, prefix="/runs")
api_router.include_router(results.router, prefix="/results")
api_router.include_router(sweeps.router, prefix="/sweeps")
