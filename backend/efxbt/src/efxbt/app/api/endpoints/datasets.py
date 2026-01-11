"""Dataset management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ...services.datasets import (
    DatasetDetail,
    DatasetSummary,
    DatasetsService,
)
from ..deps import get_datasets_service


router = APIRouter(tags=["datasets"])


@router.get("", response_model=list[DatasetSummary])
async def list_datasets(
    service: DatasetsService = Depends(get_datasets_service),
) -> list[DatasetSummary]:
    """List available datasets.

    Returns a list of all datasets found in the data directory with summary info.
    """
    return service.list_datasets()


@router.get("/{dataset_name}", response_model=DatasetDetail)
async def get_dataset(
    dataset_name: str,
    service: DatasetsService = Depends(get_datasets_service),
) -> DatasetDetail:
    """Get details of a specific dataset.

    Args:
        dataset_name: Name of the dataset

    Returns:
        Detailed dataset information including pair-date inventory

    Raises:
        HTTPException: 404 if dataset not found
    """
    try:
        return service.get_dataset(dataset_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{dataset_name}/pairs", response_model=list[str])
async def list_dataset_pairs(
    dataset_name: str,
    service: DatasetsService = Depends(get_datasets_service),
) -> list[str]:
    """List pairs available in a dataset.

    Args:
        dataset_name: Name of the dataset

    Returns:
        Sorted list of currency pairs

    Raises:
        HTTPException: 404 if dataset not found
    """
    try:
        return service.get_dataset_pairs(dataset_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{dataset_name}/dates", response_model=list[str])
async def list_dataset_dates(
    dataset_name: str,
    service: DatasetsService = Depends(get_datasets_service),
) -> list[str]:
    """List dates available in a dataset.

    Args:
        dataset_name: Name of the dataset

    Returns:
        Sorted list of dates in YYYYMMDD format

    Raises:
        HTTPException: 404 if dataset not found
    """
    try:
        return service.get_dataset_dates(dataset_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
