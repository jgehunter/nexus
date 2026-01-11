"""KPI definitions endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ....core.data.run_models import (
    EfficientFrontierScores,
    KPIDefinitionsResponse,
    RunComparisonResponse,
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

router = APIRouter(tags=["kpi"])

# Type alias for runs service dependency
RunServiceDep = Annotated[RunService, Depends(get_runs_service)]


@router.get("/definitions")
async def get_kpi_definitions() -> KPIDefinitionsResponse:
    """Get definitions for all KPIs.

    Returns descriptions, formulas, and interpretations for each KPI.
    Useful for populating tooltips in the UI.

    Returns:
        KPIDefinitionsResponse with all KPI definitions
    """
    return KPIDefinitionsResponse(definitions=KPI_REGISTRY)


@router.get("/compare")
async def compare_runs(
    service: RunServiceDep,
    run_ids: list[str] = Query(
        ...,
        min_length=2,
        max_length=5,
        description="Run IDs to compare (2-5 runs)",
    ),
) -> RunComparisonResponse:
    """Compare multiple runs for efficient frontier analysis.

    Returns frontier scores for each run, enabling risk-return comparison.

    Args:
        service: Run service instance
        run_ids: List of 2-5 run IDs to compare

    Returns:
        RunComparisonResponse with frontier scores for each run

    Raises:
        404: One or more runs not found
        409: One or more runs not completed
    """
    scores: list[EfficientFrontierScores] = []

    for run_id in run_ids:
        try:
            summary = service.get_summary(run_id)
            if summary.frontier_scores is not None:
                scores.append(summary.frontier_scores)
            else:
                # Create a basic score if frontier_scores not computed
                scores.append(
                    EfficientFrontierScores(
                        total_pnl=summary.total_pnl,
                        pnl_per_volume_bps=(
                            (summary.total_pnl / summary.total_client_volume * 10000)
                            if summary.total_client_volume > 0
                            else 0.0
                        ),
                        max_drawdown_pct=0.0,
                        inventory_risk_score=0.0,
                        risk_adjusted_return=0.0,
                    )
                )
        except RegistryRunNotFoundError:
            raise RunNotFoundError(run_id)
        except RegistryInvalidRunStateError as e:
            raise InvalidRunStateError(run_id, str(e.current_status), str(e))

    return RunComparisonResponse(runs=scores, run_ids=run_ids)
