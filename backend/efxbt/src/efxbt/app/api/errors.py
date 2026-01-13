"""Custom exception classes and error handlers."""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str
    detail: str | None = None
    code: str | None = None


class NotImplementedError(HTTPException):
    """Exception for stub endpoints not yet implemented."""

    def __init__(self, endpoint: str) -> None:
        super().__init__(
            status_code=501,
            detail=f"Endpoint '{endpoint}' not implemented in Phase 0",
        )


class DatasetNotFoundError(HTTPException):
    """Exception when a dataset is not found."""

    def __init__(self, dataset_name: str) -> None:
        super().__init__(
            status_code=404,
            detail=f"Dataset '{dataset_name}' not found",
        )


class ValidationError(HTTPException):
    """Exception for validation failures."""

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=400,
            detail=message,
        )


class RunNotFoundError(HTTPException):
    """Exception when a run is not found."""

    def __init__(self, run_id: str) -> None:
        super().__init__(
            status_code=404,
            detail=f"Run '{run_id}' not found",
        )


class InvalidRunStateError(HTTPException):
    """Exception when an operation is invalid for current run state."""

    def __init__(self, run_id: str, current_status: str, message: str) -> None:
        super().__init__(
            status_code=409,
            detail=f"Run '{run_id}' ({current_status}): {message}",
        )


class DuplicateRunError(HTTPException):
    """Exception when duplicate run config is detected."""

    def __init__(self, existing_run_id: str) -> None:
        super().__init__(
            status_code=409,
            detail=f"Duplicate config detected. Existing run: {existing_run_id}",
        )


class RunExecutionError(HTTPException):
    """Exception for run execution failures."""

    def __init__(self, run_id: str, message: str) -> None:
        super().__init__(
            status_code=500,
            detail=f"Run '{run_id}' execution failed: {message}",
        )


class SweepNotFoundError(HTTPException):
    """Exception when a sweep is not found."""

    def __init__(self, sweep_id: str) -> None:
        super().__init__(
            status_code=404,
            detail=f"Sweep '{sweep_id}' not found",
        )


class InvalidSweepStateError(HTTPException):
    """Exception when an operation is invalid for current sweep state."""

    def __init__(self, sweep_id: str, current_status: str, message: str) -> None:
        super().__init__(
            status_code=409,
            detail=f"Sweep '{sweep_id}' ({current_status}): {message}",
        )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Custom handler for HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            code=f"HTTP_{exc.status_code}",
        ).model_dump(),
    )
