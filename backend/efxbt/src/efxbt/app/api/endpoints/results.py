"""Results retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ....core.data.run_models import (
    InternalizationResponse,
    KPIDefinitionsResponse,
    PnLBreakdownResponse,
    RiskMetricsResponse,
    RunComparisonResponse,
    RunSummary,
    TimeseriesResponse,
    TradeRecord,
    TradesResponse,
)
from ....core.data.run_registry import (
    InvalidRunStateError as RegistryInvalidRunStateError,
)
from ....core.data.run_registry import (
    RunNotFoundError as RegistryRunNotFoundError,
)
from ....core.kpi import KPI_REGISTRY
from ...services.runs import RunService
from ..deps import get_runs_service
from ..errors import (
    InvalidRunStateError,
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
async def get_risk_metrics(
    run_id: str,
    service: RunServiceDep,
) -> RiskMetricsResponse:
    """Get risk metrics for a run.

    Returns inventory peaks, time above band, drawdowns, CVaR, and
    operational metrics like hedge count and volume ratio.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        RiskMetricsResponse with risk and ops metrics

    Raises:
        404: Run not found
        409: Run not completed
    """
    try:
        summary = service.get_summary(run_id)
        return RiskMetricsResponse(
            run_id=run_id,
            risk=summary.risk_metrics,
            ops=summary.ops_metrics,
        )
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


@router.get("/{run_id}/internalization")
async def get_internalization_metrics(
    run_id: str,
    service: RunServiceDep,
) -> InternalizationResponse:
    """Get internalization metrics for a run.

    Returns detailed internalized vs externalized volume breakdown,
    including per-pair analysis.

    Args:
        run_id: Unique run identifier
        service: Run service instance

    Returns:
        InternalizationResponse with detailed breakdown

    Raises:
        404: Run not found
        409: Run not completed
    """
    try:
        summary = service.get_summary(run_id)
        return InternalizationResponse(
            run_id=run_id,
            metrics=summary.internalization_metrics,
        )
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


@router.get("/{run_id}/trades")
async def get_trades(
    run_id: str,
    service: RunServiceDep,
    limit: int = Query(default=100, ge=1, le=1000, description="Max trades to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    pair: str | None = Query(default=None, description="Filter by currency pair"),
    event_type: str | None = Query(
        default=None,
        pattern="^(client_fill|hedge_fill)$",
        description="Filter by event type: 'client_fill' or 'hedge_fill'",
    ),
) -> TradesResponse:
    """Get trade-level details for a run.

    Returns paginated list of all trades with PnL attribution.

    Args:
        run_id: Unique run identifier
        service: Run service instance
        limit: Maximum number of trades to return
        offset: Pagination offset
        pair: Optional pair filter (e.g., "EURUSD")
        event_type: Optional event type filter ('client_fill' or 'hedge_fill')

    Returns:
        TradesResponse with paginated trade records

    Raises:
        404: Run not found
        409: Run not completed
    """
    try:
        trades, total = service.get_trades(
            run_id, limit=limit, offset=offset, pair=pair, event_type=event_type
        )
        return TradesResponse(
            run_id=run_id,
            trades=trades,
            total=total,
            limit=limit,
            offset=offset,
        )
    except RegistryRunNotFoundError:
        raise RunNotFoundError(run_id)
    except RegistryInvalidRunStateError as e:
        raise InvalidRunStateError(run_id, str(e.current_status), str(e))


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
