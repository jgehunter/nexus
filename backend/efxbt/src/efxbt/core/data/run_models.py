"""Run-related data models for orchestration and persistence."""

from typing import Annotated, Any

from pydantic import BaseModel, Field

from ..config.run_config import RunConfig, RunStatus


# -----------------------------------------------------------------------------
# Phase 5: Risk, Ops, and Internalization Metrics
# -----------------------------------------------------------------------------


class RiskMetrics(BaseModel):
    """Risk metrics for a completed run.

    All metrics are computed from the simulation's inventory and PnL timeseries.
    """

    # Inventory Risk
    max_abs_inventory: float = Field(
        ..., description="Peak absolute position across all timestamps (base currency)"
    )
    inventory_p95: float = Field(
        ..., description="95th percentile of absolute position (base currency)"
    )
    inventory_p99: float = Field(
        ..., description="99th percentile of absolute position (base currency)"
    )

    # Drawdown
    max_drawdown: float = Field(
        ..., description="Maximum peak-to-trough cumulative PnL drop (reporting currency)"
    )
    max_drawdown_pct: float = Field(
        ..., description="Max drawdown as percentage of peak PnL"
    )

    # Interval Risk (5-minute intervals)
    worst_interval_pnl: float = Field(
        ..., description="Worst 5-minute period PnL (reporting currency)"
    )
    worst_interval_start_ms: int = Field(
        ..., description="Start timestamp of worst interval (ms since epoch)"
    )

    # Time-Based Risk
    time_above_risk_band_pct: float = Field(
        ..., description="Percentage of time position exceeded risk band threshold"
    )

    # Efficient Frontier Score
    cvar_95: float = Field(
        ..., description="Conditional VaR at 95% - average of worst 5% of intervals"
    )

    # Per-pair breakdown (optional)
    pair_risk: list[dict[str, Any]] = Field(
        default_factory=list, description="Risk metrics broken down by pair"
    )


class OpsMetrics(BaseModel):
    """Operational metrics for a completed run.

    Tracks hedge execution statistics and efficiency.
    """

    hedge_count: int = Field(..., description="Total number of hedge trades executed")
    total_hedge_volume: float = Field(
        ..., description="Sum of all hedge trade quantities (base currency)"
    )
    hedge_volume_ratio: float = Field(
        ..., description="Ratio of hedge volume to client volume"
    )
    avg_hedge_size: float = Field(
        ..., description="Average hedge trade size (base currency)"
    )

    # Per-pair breakdown (optional)
    pair_ops: list[dict[str, Any]] = Field(
        default_factory=list, description="Ops metrics broken down by pair"
    )


class InternalizationMetrics(BaseModel):
    """Detailed internalization breakdown for a completed run.

    Internalization = volume matched between opposing client trades.
    Externalization = volume covered by hedging to the market.
    """

    total_client_volume: float = Field(
        ..., description="Total client trade volume (base currency)"
    )
    total_internalized_volume: float = Field(
        ..., description="Volume internalized between clients (base currency)"
    )
    total_externalized_volume: float = Field(
        ..., description="Volume hedged externally (base currency)"
    )
    internalization_ratio: float = Field(
        ..., description="Internalized / total client volume (0.0 to 1.0)"
    )

    # Per-pair breakdown
    pair_breakdown: list[dict[str, Any]] = Field(
        default_factory=list, description="Internalization by currency pair"
    )


class EfficientFrontierScores(BaseModel):
    """Scalar scores for efficient frontier analysis and run comparison.

    These scores enable quick comparison of runs on a risk-return basis.
    """

    # Return Metrics (higher = better)
    total_pnl: float = Field(..., description="Total PnL (reporting currency)")
    pnl_per_volume_bps: float = Field(
        ..., description="PnL per unit volume in basis points (total_pnl / client_volume * 10000)"
    )

    # Risk Metrics (lower = better)
    max_drawdown_pct: float = Field(
        ..., description="Maximum drawdown as percentage of peak"
    )
    inventory_risk_score: float = Field(
        ..., description="Composite risk score from P99 inventory and time above band"
    )

    # Composite Score
    risk_adjusted_return: float = Field(
        ..., description="PnL per volume divided by inventory risk score"
    )


class ShardProgress(BaseModel):
    """Progress tracking for a single shard."""

    pair: str
    date: str
    status: Annotated[
        str,
        Field(description="Shard status: pending, running, completed, failed"),
    ]
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    error: str | None = None


class FailedShardDetail(BaseModel):
    """Details about a failed shard."""

    pair: str
    date: str
    error: str
    traceback: str | None = None


class RunRecord(BaseModel):
    """Persistent run metadata stored in JSON."""

    run_id: str = Field(..., description="Unique run identifier")
    config_hash: Annotated[
        str,
        Field(description="SHA-256 hash of config for idempotence detection"),
    ]
    status: RunStatus = RunStatus.CREATED

    # Timestamps (int64 milliseconds since epoch)
    created_at_ms: int
    started_at_ms: int | None = None
    completed_at_ms: int | None = None

    # Progress tracking
    total_shards: int = 0
    completed_shards: int = 0
    failed_shards: int = 0

    # Error info
    error_message: str | None = None
    failed_shard_details: list[FailedShardDetail] = Field(default_factory=list)

    # Config snapshot (immutable after creation)
    config: RunConfig

    @property
    def progress_pct(self) -> float:
        """Calculate progress percentage."""
        if self.total_shards == 0:
            return 0.0
        return (self.completed_shards + self.failed_shards) / self.total_shards * 100


class RunCreateResponse(BaseModel):
    """Response model for run creation."""

    run_id: str
    status: RunStatus
    is_new: bool
    config_hash: str


class RunStatusResponse(BaseModel):
    """Response model for run status polling."""

    run_id: str
    status: RunStatus
    total_shards: int
    completed_shards: int
    failed_shards: int
    progress_pct: float
    started_at_ms: int | None = None
    error_message: str | None = None


class RunDetailResponse(BaseModel):
    """Response model for full run details."""

    run_id: str
    status: RunStatus
    config_hash: str
    config: RunConfig

    # Timestamps (int64 milliseconds since epoch)
    created_at_ms: int
    started_at_ms: int | None = None
    completed_at_ms: int | None = None

    # Progress
    total_shards: int
    completed_shards: int
    failed_shards: int
    progress_pct: float

    # Error info
    error_message: str | None = None
    failed_shard_details: list[FailedShardDetail] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Summary results for a completed run."""

    run_id: str
    status: RunStatus

    # Scope
    pairs: list[str]
    date_range: tuple[str, str] | None = None
    total_shards: int

    # Aggregate PnL (reporting currency)
    total_execution_pnl: float
    total_inventory_pnl: float
    total_hedge_pnl: float
    total_pnl: float

    # Volume metrics
    total_client_volume: float
    total_internalized_volume: float
    total_externalized_volume: float
    internalization_ratio: float

    # Per-pair breakdown
    pair_summaries: list[dict[str, Any]] = Field(default_factory=list)

    # Phase 5: Extended metrics (optional for backwards compatibility)
    risk_metrics: RiskMetrics | None = Field(
        default=None, description="Risk metrics (inventory, drawdown, CVaR)"
    )
    ops_metrics: OpsMetrics | None = Field(
        default=None, description="Operational metrics (hedge count, volume ratio)"
    )
    internalization_metrics: InternalizationMetrics | None = Field(
        default=None, description="Detailed internalization breakdown"
    )
    frontier_scores: EfficientFrontierScores | None = Field(
        default=None, description="Scalar scores for efficient frontier analysis"
    )


class TimeseriesPoint(BaseModel):
    """Single point in downsampled time series."""

    timestamp_ms: int
    cumulative_pnl: float
    net_position: float = 0.0
    unrealized_pnl: float = 0.0


class TimeseriesResponse(BaseModel):
    """Response model for time series data."""

    run_id: str
    sample_points: int
    points: list[TimeseriesPoint]


class PnLBreakdownResponse(BaseModel):
    """Response model for PnL breakdown."""

    run_id: str
    group_by: str  # "total", "pair", "date"
    breakdown: list[dict[str, Any]]


class RunListResponse(BaseModel):
    """Response model for run listing."""

    runs: list[RunDetailResponse]
    total: int
    limit: int
    offset: int


class CancelResponse(BaseModel):
    """Response model for cancellation request."""

    run_id: str
    cancelled: bool
    message: str | None = None


# -----------------------------------------------------------------------------
# Phase 5: API Response Models
# -----------------------------------------------------------------------------


class RiskMetricsResponse(BaseModel):
    """Response model for risk metrics endpoint."""

    run_id: str
    risk: RiskMetrics | None = None
    ops: OpsMetrics | None = None


class InternalizationResponse(BaseModel):
    """Response model for internalization metrics endpoint."""

    run_id: str
    metrics: InternalizationMetrics | None = None


class TradeRecord(BaseModel):
    """Single trade record for trades endpoint."""

    timestamp_ms: int
    pair: str
    event_type: str  # "client_fill", "hedge_fill"
    side: int
    qty: float
    price: float
    execution_pnl: float
    inventory_pnl: float
    hedge_pnl: float
    source_trade_id: str | None = None


class TradesResponse(BaseModel):
    """Response model for paginated trades endpoint."""

    run_id: str
    trades: list[TradeRecord]
    total: int
    limit: int
    offset: int


class RunComparisonResponse(BaseModel):
    """Response model for run comparison endpoint."""

    runs: list[EfficientFrontierScores]
    run_ids: list[str]


class KPIDefinition(BaseModel):
    """Definition of a single KPI for tooltips and documentation."""

    id: str
    name: str
    category: str  # "pnl", "risk", "ops", "internalization"
    description: str
    formula: str | None = None
    unit: str
    interpretation: str  # "higher_better", "lower_better", "neutral"


class KPIDefinitionsResponse(BaseModel):
    """Response model for KPI definitions endpoint."""

    definitions: list[KPIDefinition]
