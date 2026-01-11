"""Run management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ....core.config.run_config import RunConfig, RunStatus
from ....core.data.run_models import (
    CancelResponse,
    RunCreateResponse,
    RunDetailResponse,
    RunListResponse,
    RunStatusResponse,
    RunSummary,
    TimeseriesResponse,
)
from ....core.data.run_registry import (
    DuplicateRunError as RegistryDuplicateRunError,
)
from ....core.data.run_registry import (
    InvalidRunStateError as RegistryInvalidRunStateError,
)
from ....core.data.run_registry import (
    RunNotFoundError as RegistryRunNotFoundError,
)
from ...services.runs import RunService, ValidationError as ServiceValidationError
from ..deps import get_runs_service
from ..errors import (
    DuplicateRunError,
    InvalidRunStateError,
    RunNotFoundError,
    ValidationError,
)

router = APIRouter(tags=["runs"])

# Type alias for runs service dependency
RunServiceDep = Annotated[RunService, Depends(get_runs_service)]


@router.get("")
async def list_runs(
    service: RunServiceDep,
    status: RunStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    """List all backtest runs with optional filters.

    Args:
        service: Run service instance
        status: Filter by run status (optional)
        limit: Maximum runs to return (1-500)
        offset: Number of runs to skip

    Returns:
        Paginated list of runs
    """
    return service.list_runs(status=status, limit=limit, offset=offset)


@router.post("")
async def create_run(
    config: RunConfig,
    service: RunServiceDep,
    idempotence: str = Query(
        default="error",
        pattern="^(error|reuse|new)$",
        description="Behavior if duplicate config found",
    ),
) -> RunCreateResponse:
    """Create a new backtest run (does NOT start execution).

    Creates a run record with validated configuration. Use POST /runs/{id}/start
    to begin execution.

    Args:
        config: Run configuration
        service: Run service instance
        idempotence: Behavior if duplicate config found:
            - "error": Return 409 Conflict
            - "reuse": Return existing run
            - "new": Create new run anyway

    Returns:
        Run creation response with run_id and status

    Raises:
        400: Validation error (invalid dataset, tradebook, etc.)
        409: Duplicate config detected (when idempotence="error")
    """
    try:
        return service.create_run(config, idempotence=idempotence)
    except ServiceValidationError as e:
        raise ValidationError(str(e))
    except RegistryDuplicateRunError as e:
        raise DuplicateRunError(e.existing_run_id)


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    service: RunServiceDep,
) -> RunDetailResponse:
    """Get full details of a specific run.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        Full run details including configuration

    Raises:
        404: Run not found
    """
    try:
        return service.get_run_detail(run_id)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)


@router.delete("/{run_id}")
async def delete_run(
    run_id: str,
    service: RunServiceDep,
) -> None:
    """Delete a run and all its results.

    Cannot delete runs that are currently running.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Raises:
        404: Run not found
        409: Cannot delete running run
    """
    try:
        service.delete_run(run_id)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


@router.post("/{run_id}/start")
async def start_run(
    run_id: str,
    service: RunServiceDep,
) -> RunStatusResponse:
    """Start execution of a created run.

    Run must be in CREATED status. Execution happens asynchronously;
    use GET /runs/{id}/status to poll for progress.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        Run status response

    Raises:
        404: Run not found
        409: Run not in CREATED status
    """
    try:
        return service.start_run(run_id)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


@router.get("/{run_id}/status")
async def get_run_status(
    run_id: str,
    service: RunServiceDep,
) -> RunStatusResponse:
    """Get current status and progress of a run.

    Use this endpoint for polling during execution.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        Current status and progress information

    Raises:
        404: Run not found
    """
    try:
        return service.get_status(run_id)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    service: RunServiceDep,
) -> CancelResponse:
    """Request cancellation of a running backtest.

    Best-effort cancellation: running shards will complete but
    no new shards will start.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        Cancellation response

    Raises:
        404: Run not found
    """
    try:
        return service.cancel_run(run_id)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)


@router.get("/{run_id}/summary")
async def get_run_summary(
    run_id: str,
    service: RunServiceDep,
) -> RunSummary:
    """Get summary results for a completed run.

    Only available for runs in COMPLETED or FAILED status.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        Summary metrics and aggregated results

    Raises:
        404: Run not found
        409: Run not completed
    """
    try:
        return service.get_summary(run_id)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


@router.get("/{run_id}/timeseries")
async def get_run_timeseries(
    run_id: str,
    service: RunServiceDep,
    sample_points: int = Query(
        default=500,
        ge=10,
        le=5000,
        description="Target number of points for downsampling",
    ),
) -> TimeseriesResponse:
    """Get downsampled time series for visualization.

    Uses LTTB algorithm for intelligent downsampling that preserves
    the visual shape of the data.

    Args:
        run_id: Unique run identifier
        service: Run service instance
        sample_points: Target number of output points (10-5000)

    Returns:
        Downsampled time series data

    Raises:
        404: Run not found
        409: Run not completed
    """
    try:
        return service.get_timeseries(run_id, sample_points)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))
