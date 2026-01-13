"""Parameter sweep endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ....core.config.sweep_config import SweepConfig, SweepStatus
from ....core.data.sweep_models import (
    BestConfigsRequest,
    BestConfigsResponse,
    FrontierConstraint,
    FrontierTableResponse,
    SweepCreateResponse,
    SweepDetailResponse,
    SweepListResponse,
    SweepStatusResponse,
)
from ....core.data.sweep_registry import (
    InvalidSweepStateError as RegistryInvalidSweepStateError,
    SweepNotFoundError as RegistrySweepNotFoundError,
)
from ...services.sweeps import SweepService
from ...services.runs import ValidationError as ServiceValidationError
from ..deps import get_sweeps_service
from ..errors import InvalidSweepStateError, SweepNotFoundError, ValidationError

router = APIRouter(tags=["sweeps"])
SweepServiceDep = Annotated[SweepService, Depends(get_sweeps_service)]


@router.get("")
async def list_sweeps(
    service: SweepServiceDep,
    status: SweepStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SweepListResponse:
    """List all parameter sweeps with optional filters.

    Args:
        status: Filter by sweep status (pending, running, completed, partial, cancelled)
        limit: Maximum number of sweeps to return (1-500)
        offset: Pagination offset

    Returns:
        Paginated list of sweeps with status and metadata
    """
    return service.list_sweeps(status=status, limit=limit, offset=offset)


@router.post("")
async def create_sweep(
    config: SweepConfig,
    service: SweepServiceDep,
) -> SweepCreateResponse:
    """Create a new parameter sweep (does NOT start execution).

    Validates the configuration and creates a sweep record.
    Call POST /sweeps/{sweep_id}/start to begin execution.

    Args:
        config: Sweep configuration with base settings and parameter grid

    Returns:
        Created sweep with sweep_id, config_hash, and total_configs count

    Raises:
        400: Invalid configuration (dataset/tradebook not found)
    """
    try:
        return service.create_sweep(config)
    except ServiceValidationError as e:
        raise ValidationError(str(e))


@router.get("/{sweep_id}")
async def get_sweep(
    sweep_id: str,
    service: SweepServiceDep,
) -> SweepDetailResponse:
    """Get full details of a specific sweep.

    Args:
        sweep_id: Unique sweep identifier

    Returns:
        Complete sweep details including config, progress, and member runs

    Raises:
        404: Sweep not found
    """
    try:
        return service.get_sweep_detail(sweep_id)
    except RegistrySweepNotFoundError:
        raise SweepNotFoundError(sweep_id)


@router.post("/{sweep_id}/start")
async def start_sweep(
    sweep_id: str,
    service: SweepServiceDep,
) -> SweepStatusResponse:
    """Start execution of a created sweep.

    Submits the sweep to background execution. Returns immediately.
    Poll GET /sweeps/{sweep_id}/status for progress.

    Args:
        sweep_id: Unique sweep identifier

    Returns:
        Sweep status with RUNNING state

    Raises:
        404: Sweep not found
        409: Sweep not in PENDING status
    """
    try:
        return service.start_sweep(sweep_id)
    except RegistrySweepNotFoundError:
        raise SweepNotFoundError(sweep_id)
    except RegistryInvalidSweepStateError as e:
        raise InvalidSweepStateError(sweep_id, e.current_status.value, str(e))


@router.get("/{sweep_id}/status")
async def get_sweep_status(
    sweep_id: str,
    service: SweepServiceDep,
) -> SweepStatusResponse:
    """Get current status and progress of a sweep.

    Use this endpoint for polling sweep progress.

    Args:
        sweep_id: Unique sweep identifier

    Returns:
        Current status, progress counts, and current run info

    Raises:
        404: Sweep not found
    """
    try:
        return service.get_status(sweep_id)
    except RegistrySweepNotFoundError:
        raise SweepNotFoundError(sweep_id)


@router.delete("/{sweep_id}")
async def delete_sweep(
    sweep_id: str,
    service: SweepServiceDep,
    delete_runs: bool = Query(
        default=False,
        description="Also delete all member runs created by this sweep",
    ),
) -> None:
    """Delete a sweep and optionally its member runs.

    Args:
        sweep_id: Unique sweep identifier
        delete_runs: If true, also deletes all runs created by this sweep

    Raises:
        404: Sweep not found
        409: Sweep is currently running
    """
    try:
        service.delete_sweep(sweep_id, delete_runs=delete_runs)
    except RegistrySweepNotFoundError:
        raise SweepNotFoundError(sweep_id)
    except RegistryInvalidSweepStateError as e:
        raise InvalidSweepStateError(sweep_id, e.current_status.value, str(e))


@router.get("/{sweep_id}/frontier")
async def get_frontier(
    sweep_id: str,
    service: SweepServiceDep,
    max_risk: float | None = Query(
        default=None,
        description="Max inventory_risk_score filter (configs with risk <= this value)",
    ),
    min_internalization: float | None = Query(
        default=None,
        description="Min internalization_ratio filter (configs with ratio >= this value)",
    ),
    max_drawdown: float | None = Query(
        default=None,
        description="Max max_drawdown_pct filter (configs with drawdown <= this value)",
    ),
) -> FrontierTableResponse:
    """Get frontier table with optional constraints.

    Returns all configurations with their computed metrics, filtered by constraints.
    Configs are marked as Pareto-optimal for efficient frontier visualization.

    The efficient frontier plots PnL/Volume (return) vs Inventory Risk Score (risk).
    Pareto-optimal configs are those not dominated by any other config on both axes.

    Args:
        sweep_id: Unique sweep identifier
        max_risk: Filter configs where inventory_risk_score <= max_risk
        min_internalization: Filter configs where internalization_ratio >= min_internalization
        max_drawdown: Filter configs where max_drawdown_pct <= max_drawdown

    Returns:
        Frontier table with configs, metrics, Pareto status, and counts

    Raises:
        404: Sweep not found
    """
    try:
        constraints = []
        if max_risk is not None:
            constraints.append(
                FrontierConstraint(metric="inventory_risk_score", operator="le", value=max_risk)
            )
        if min_internalization is not None:
            constraints.append(
                FrontierConstraint(metric="internalization_ratio", operator="ge", value=min_internalization)
            )
        if max_drawdown is not None:
            constraints.append(
                FrontierConstraint(metric="max_drawdown_pct", operator="le", value=max_drawdown)
            )

        return service.get_frontier(sweep_id, constraints if constraints else None)
    except RegistrySweepNotFoundError:
        raise SweepNotFoundError(sweep_id)


@router.post("/{sweep_id}/best")
async def get_best_configs(
    sweep_id: str,
    service: SweepServiceDep,
    request: BestConfigsRequest,
) -> BestConfigsResponse:
    """Get best configurations satisfying all constraints.

    Constraints use AND logic - configs must satisfy ALL specified constraints.
    Results are sorted by the specified metric.

    Args:
        sweep_id: Unique sweep identifier
        request: Request body with constraints, sort_by, and limit

    Returns:
        Top configs satisfying constraints, sorted by specified metric

    Raises:
        404: Sweep not found
    """
    try:
        return service.get_best_configs(
            sweep_id,
            constraints=request.constraints,
            sort_by=request.sort_by,
            limit=request.limit,
        )
    except RegistrySweepNotFoundError:
        raise SweepNotFoundError(sweep_id)
