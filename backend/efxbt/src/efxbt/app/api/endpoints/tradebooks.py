"""Trade book management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ...services.tradebooks import (
    TradeBookDetail,
    TradeBookHealthResponse,
    TradeBookSummary,
    TradeBooksService,
)
from ..deps import get_tradebooks_service


router = APIRouter(tags=["tradebooks"])


@router.get("", response_model=list[TradeBookSummary])
async def list_tradebooks(
    service: TradeBooksService = Depends(get_tradebooks_service),
) -> list[TradeBookSummary]:
    """List available trade books.

    Returns a list of all trade books found in the data directory with summary info.
    """
    return service.list_tradebooks()


@router.get("/{book_name}", response_model=TradeBookDetail)
async def get_tradebook(
    book_name: str,
    service: TradeBooksService = Depends(get_tradebooks_service),
) -> TradeBookDetail:
    """Get details of a specific trade book.

    Args:
        book_name: Name of the trade book

    Returns:
        Detailed trade book information including pair-date inventory

    Raises:
        HTTPException: 404 if trade book not found
    """
    try:
        return service.get_tradebook(book_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{book_name}/dates", response_model=list[str])
async def list_tradebook_dates(
    book_name: str,
    service: TradeBooksService = Depends(get_tradebooks_service),
) -> list[str]:
    """List dates with trades in a trade book.

    Args:
        book_name: Name of the trade book

    Returns:
        Sorted list of dates in YYYYMMDD format

    Raises:
        HTTPException: 404 if trade book not found
    """
    try:
        return service.get_tradebook_dates(book_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{book_name}/health", response_model=TradeBookHealthResponse)
async def get_tradebook_health(
    book_name: str,
    validate_schemas: bool = True,
    service: TradeBooksService = Depends(get_tradebooks_service),
) -> TradeBookHealthResponse:
    """Get health report for a trade book.

    Args:
        book_name: Name of the trade book
        validate_schemas: Whether to validate parquet schemas (default: True)

    Returns:
        Health report with trade statistics and schema validation results

    Raises:
        HTTPException: 404 if trade book not found
    """
    try:
        return service.compute_health(book_name, validate_schemas=validate_schemas)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
