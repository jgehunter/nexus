"""Results retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ....core.data.run_models import (
    PnLBreakdownResponse,
    RunSummary,
    TimeseriesResponse,
)
from ....core.data.run_registry import (
    InvalidRunStateError as RegistryInvalidRunStateError,
)
from ....core.data.run_registry import (
    RunNotFoundError as RegistryRunNotFoundError,
)
from ...services.runs import RunService
from ..deps import get_runs_service
from ..errors import (
    InvalidRunStateError,
    NotImplementedError,
    RunNotFoundError,
)

router = APIRouter(tags=["results"])

# Type alias for runs service dependency
RunServiceDep = Annotated[RunService, Depends(get_runs_service)]


@router.get("/{run_id}")
async def get_results_summary(
    run_id: str,
    service: RunServiceDep,
) -> RunSummary:
    """Get summary results for a run.

    Alias for /runs/{id}/summary. Only available for completed runs.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        Summary metrics including PnL breakdown, volume metrics, etc.

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


@router.get("/{run_id}/pnl")
async def get_pnl_breakdown(
    run_id: str,
    service: RunServiceDep,
    by: str = Query(
        default="total",
        pattern="^(total|pair|date)$",
        description="Grouping level for breakdown",
    ),
) -> PnLBreakdownResponse:
    """Get detailed PnL breakdown for a run.

    Args:
        run_id: Unique run identifier
        service: Run service instance
        by: Grouping level: "total", "pair", or "date"

    Returns:
        PnL breakdown with execution, inventory, and hedge components.

    Raises:
        404: Run not found
        409: Run not completed
    """
    try:
        return service.get_pnl_breakdown(run_id, group_by=by)
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


@router.get("/{run_id}/risk")
async def get_risk_metrics(run_id: str) -> None:
    """Get risk metrics for a run.

    Args:
        run_id: Unique run identifier

    Returns inventory peaks, time above band, drawdowns, etc.
    """
    raise NotImplementedError(f"/api/v1/results/{run_id}/risk")


@router.get("/{run_id}/internalization")
async def get_internalization_metrics(run_id: str) -> None:
    """Get internalization metrics for a run.

    Args:
        run_id: Unique run identifier

    Returns internalized vs externalized volume breakdown.
    """
    raise NotImplementedError(f"/api/v1/results/{run_id}/internalization")


@router.get("/{run_id}/trades")
async def get_trades(run_id: str) -> None:
    """Get trade-level details for a run.

    Args:
        run_id: Unique run identifier

    Returns list of all trades with attribution.
    """
    raise NotImplementedError(f"/api/v1/results/{run_id}/trades")


@router.get("/{run_id}/timeseries")
async def get_timeseries(
    run_id: str,
    service: RunServiceDep,
    sample_points: int = Query(
        default=500,
        ge=10,
        le=5000,
        description="Target number of points for downsampling",
    ),
) -> TimeseriesResponse:
    """Get time series data for a run.

    Alias for /runs/{id}/timeseries. Uses LTTB algorithm for downsampling.

    Args:
        run_id: Unique run identifier
        service: Run service instance
        sample_points: Target number of output points (10-5000)

    Returns:
        Downsampled time series with cumulative PnL

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
