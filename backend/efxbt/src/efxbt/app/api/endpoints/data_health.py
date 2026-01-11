"""Data health and validation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ...services.datasets import DatasetsService, HealthReportResponse
from ..deps import get_datasets_service


router = APIRouter(tags=["data-health"])


@router.get("", response_model=HealthReportResponse)
async def get_data_health(
    dataset: str = Query(..., description="Name of the dataset to check"),
    validate_schemas: bool = Query(
        default=True, description="Whether to validate parquet schemas"
    ),
    service: DatasetsService = Depends(get_datasets_service),
) -> HealthReportResponse:
    """Get health report for a dataset.

    Computes comprehensive data quality metrics including:
    - Tick coverage statistics per pair/day
    - Trade coverage statistics
    - Schema validation (optional)
    - Gap analysis

    Args:
        dataset: Name of the dataset to check
        validate_schemas: Whether to validate parquet file schemas
        service: Datasets service (injected)

    Returns:
        Health report with coverage stats and issues

    Raises:
        HTTPException: 404 if dataset not found
    """
    try:
        return service.compute_health(dataset, validate_schemas=validate_schemas)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}") from e


@router.get("/{dataset_name}", response_model=HealthReportResponse)
async def get_dataset_health(
    dataset_name: str,
    validate_schemas: bool = Query(
        default=True, description="Whether to validate parquet schemas"
    ),
    service: DatasetsService = Depends(get_datasets_service),
) -> HealthReportResponse:
    """Get health status of a specific dataset.

    Alternative endpoint path for dataset health checks.

    Args:
        dataset_name: Name of the dataset to check
        validate_schemas: Whether to validate parquet file schemas
        service: Datasets service (injected)

    Returns:
        Health report with coverage stats and issues

    Raises:
        HTTPException: 404 if dataset not found
    """
    try:
        return service.compute_health(dataset_name, validate_schemas=validate_schemas)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}") from e
