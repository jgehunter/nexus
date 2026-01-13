"""Sweep data models for registry and API responses."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from ..config.sweep_config import SweepConfig, SweepStatus


class SweepRecord(BaseModel):
    """Persistent sweep metadata stored in JSON.

    Tracks the sweep lifecycle, member runs, and progress.
    """

    sweep_id: str = Field(..., description="Unique sweep identifier")
    status: SweepStatus = SweepStatus.PENDING
    config_hash: str = Field(..., description="SHA-256 hash of sweep config (first 16 chars)")

    # Timestamps (int64 milliseconds since epoch)
    created_at_ms: int
    started_at_ms: int | None = None
    completed_at_ms: int | None = None

    # Config snapshot (immutable after creation)
    config: SweepConfig

    # Member runs (run_ids belonging to this sweep)
    member_run_ids: list[str] = Field(default_factory=list)

    # Progress tracking
    total_configs: int = Field(0, description="Total number of configurations to run")
    completed_configs: int = Field(0, description="Successfully completed configurations")
    failed_configs: int = Field(0, description="Failed configurations")
    skipped_configs: int = Field(0, description="Skipped (already existed via idempotence)")
    current_run_id: str | None = Field(None, description="Currently executing run_id")

    # Error tracking
    error_message: str | None = None

    @property
    def progress_pct(self) -> float:
        """Calculate overall progress percentage."""
        if self.total_configs == 0:
            return 0.0
        processed = self.completed_configs + self.failed_configs + self.skipped_configs
        return (processed / self.total_configs) * 100


# -----------------------------------------------------------------------------
# API Response Models
# -----------------------------------------------------------------------------


class SweepCreateResponse(BaseModel):
    """Response model for sweep creation."""

    sweep_id: str
    status: SweepStatus
    config_hash: str
    total_configs: int
    message: str | None = None


class SweepStatusResponse(BaseModel):
    """Response model for sweep status polling."""

    sweep_id: str
    status: SweepStatus
    total_configs: int
    completed_configs: int
    failed_configs: int
    skipped_configs: int
    progress_pct: float
    current_run_id: str | None = None
    error_message: str | None = None


class SweepDetailResponse(BaseModel):
    """Response model for full sweep details."""

    sweep_id: str
    status: SweepStatus
    config_hash: str
    config: SweepConfig

    # Timestamps
    created_at_ms: int
    started_at_ms: int | None = None
    completed_at_ms: int | None = None

    # Progress
    total_configs: int
    completed_configs: int
    failed_configs: int
    skipped_configs: int
    progress_pct: float

    # Member runs
    member_run_ids: list[str]

    # Error info
    error_message: str | None = None


class SweepListItem(BaseModel):
    """Summary item for sweep listing."""

    sweep_id: str
    status: SweepStatus
    config_hash: str
    name: str | None
    dataset: str
    tradebook: str
    total_configs: int
    completed_configs: int
    failed_configs: int
    skipped_configs: int
    progress_pct: float
    created_at_ms: int
    completed_at_ms: int | None = None


class SweepListResponse(BaseModel):
    """Response model for sweep listing."""

    sweeps: list[SweepListItem]
    total: int
    limit: int
    offset: int


# -----------------------------------------------------------------------------
# Frontier Analysis Models
# -----------------------------------------------------------------------------


class FrontierConstraint(BaseModel):
    """Constraint for frontier filtering.

    Supports comparison operators for numeric metrics.
    Multiple constraints are combined with AND logic.
    """

    metric: Annotated[
        str,
        Field(
            description="Metric to constrain (e.g., 'inventory_risk_score', 'max_drawdown_pct')"
        ),
    ]
    operator: Annotated[
        Literal["lt", "le", "gt", "ge", "eq"],
        Field(description="Comparison operator"),
    ]
    value: Annotated[float, Field(description="Constraint threshold value")]


class FrontierConfig(BaseModel):
    """Configuration row in frontier table.

    Contains the swept parameters, all computed metrics,
    and Pareto optimality status.
    """

    run_id: str = Field(..., description="Run ID for this configuration")
    config_hash: str = Field(..., description="Config hash (first 8 chars for display)")

    # Swept parameters (only the ones that varied)
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Swept parameter values for this config",
    )

    # Frontier metrics (from EfficientFrontierScores)
    total_pnl: float = Field(..., description="Total PnL (reporting currency)")
    pnl_per_volume_bps: float = Field(..., description="PnL per volume in basis points")
    max_drawdown_pct: float = Field(..., description="Max drawdown as percentage")
    inventory_risk_score: float = Field(..., description="Normalized inventory risk (0-1)")
    risk_adjusted_return: float = Field(..., description="Risk-adjusted return score")

    # Additional metrics for comparison
    internalization_ratio: float = Field(
        ..., description="Internalization ratio (0-1)"
    )
    total_client_volume: float = Field(
        default=0.0, description="Total client volume"
    )
    hedge_count: int = Field(default=0, description="Number of hedge trades")

    # Pareto status
    is_pareto_optimal: bool = Field(
        default=False,
        description="True if this config is on the Pareto frontier",
    )


class FrontierTableResponse(BaseModel):
    """Response model for frontier analysis."""

    sweep_id: str
    configs: list[FrontierConfig]
    total_configs: int = Field(..., description="Total configs in sweep (before filtering)")
    filtered_count: int = Field(..., description="Configs after constraint filtering")
    pareto_count: int = Field(..., description="Number of Pareto-optimal configs")

    # Axis metadata for UI
    x_axis: str = Field(
        default="inventory_risk_score",
        description="Default X-axis metric",
    )
    y_axis: str = Field(
        default="pnl_per_volume_bps",
        description="Default Y-axis metric",
    )


class BestConfigsRequest(BaseModel):
    """Request body for best configs endpoint."""

    constraints: list[FrontierConstraint] = Field(
        default_factory=list,
        description="Constraints to filter configs (AND logic)",
    )
    sort_by: str = Field(
        default="risk_adjusted_return",
        description="Metric to sort by",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum configs to return",
    )


class BestConfigsResponse(BaseModel):
    """Response model for best configs by constraints."""

    sweep_id: str
    constraints: list[FrontierConstraint]
    sort_by: str
    configs: list[FrontierConfig]
    count: int = Field(..., description="Total configs satisfying constraints")
