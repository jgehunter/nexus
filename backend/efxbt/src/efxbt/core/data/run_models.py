"""Run-related data models for orchestration and persistence."""

from typing import Annotated, Any

from pydantic import BaseModel, Field

from ..config.run_config import RunConfig, RunStatus


# -----------------------------------------------------------------------------
# Phase 5: Risk, Ops, and Internalization Metrics
# -----------------------------------------------------------------------------


class PositionTimeseriesPoint(BaseModel):
    """Single point in position timeseries for a direct pair."""

    timestamp_ms: int = Field(..., description="Timestamp in milliseconds")
    position: float = Field(..., description="Net position in base currency")
    position_usd: float = Field(
        default=0.0, description="Net position value in reporting currency (USD)"
    )


class PairPositionTimeseries(BaseModel):
    """Position timeseries for a single direct pair."""

    pair: str = Field(..., description="Currency pair (e.g., EURUSD)")
    points: list[PositionTimeseriesPoint] = Field(
        default_factory=list, description="Timeseries points"
    )
    max_position: float = Field(
        default=0.0, description="Maximum absolute position"
    )
    max_position_usd: float = Field(
        default=0.0, description="Maximum position in reporting currency"
    )


class AggregatePositionTimeseriesPoint(BaseModel):
    """Single point in aggregate position timeseries."""

    timestamp_ms: int = Field(..., description="Timestamp in milliseconds")
    total_abs_position_usd: float = Field(
        ..., description="Sum of absolute USD positions across all pairs"
    )


class AggregatePositionTimeseries(BaseModel):
    """Aggregate position timeseries across all direct pairs."""

    points: list[AggregatePositionTimeseriesPoint] = Field(
        default_factory=list, description="Timeseries points"
    )
    max_total_abs_position_usd: float = Field(
        default=0.0, description="Maximum total absolute position in USD"
    )


class RiskMetrics(BaseModel):
    """Risk metrics for a completed run.

    All metrics are computed from the simulation's inventory and PnL timeseries.
    """

    # Inventory Risk (aggregate USD exposure across all direct pairs)
    max_abs_inventory: float = Field(
        ..., description="Peak aggregate absolute position in USD (sum of |position * rate| across pairs)"
    )
    inventory_p95: float = Field(
        ..., description="95th percentile of aggregate absolute position in USD"
    )
    inventory_p99: float = Field(
        ..., description="99th percentile of aggregate absolute position in USD"
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

    # Efficient Frontier Score
    cvar_95: float = Field(
        ..., description="Conditional VaR at 95% - average of worst 5% of intervals"
    )

    # Per-pair breakdown (optional)
    pair_risk: list[dict[str, Any]] = Field(
        default_factory=list, description="Risk metrics broken down by pair"
    )

    # Position timeseries by direct pair (EURUSD, GBPUSD, etc.)
    position_timeseries: list[PairPositionTimeseries] = Field(
        default_factory=list,
        description="Position timeseries for each direct currency pair"
    )

    # Aggregate position timeseries (sum of absolute USD across all pairs)
    aggregate_position_timeseries: AggregatePositionTimeseries | None = Field(
        default=None,
        description="Aggregate absolute USD position across all direct pairs"
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
    total_client_volume: float = Field(
        default=0.0, description="Total client volume for hedges per unit calculation"
    )

    # Per-pair breakdown (optional)
    pair_ops: list[dict[str, Any]] = Field(
        default_factory=list, description="Ops metrics broken down by pair"
    )


class DirectPairInternalization(BaseModel):
    """Internalization metrics for a single direct pair (in reporting currency)."""

    pair: str = Field(..., description="Direct currency pair (e.g., EURUSD)")
    client_volume_usd: float = Field(
        ..., description="Client volume normalized to reporting currency"
    )
    internalized_volume_usd: float = Field(
        ..., description="Internalized volume in reporting currency"
    )
    externalized_volume_usd: float = Field(
        ..., description="Externalized (hedged) volume in reporting currency"
    )
    internalization_ratio: float = Field(
        ..., description="Internalization ratio for this pair (0.0 to 1.0)"
    )


class InternalizationMetrics(BaseModel):
    """Detailed internalization breakdown for a completed run.

    Internalization = volume matched between opposing client trades.
    Externalization = volume covered by hedging to the market.

    All volumes are normalized to reporting currency (USD) for consistent aggregation.
    Breakdown is by direct pairs only (decrossed trades).
    """

    # Aggregates in reporting currency (USD)
    total_client_volume_usd: float = Field(
        ..., description="Total client trade volume (reporting currency)"
    )
    total_internalized_volume_usd: float = Field(
        ..., description="Volume internalized between clients (reporting currency)"
    )
    total_externalized_volume_usd: float = Field(
        ..., description="Volume hedged externally (reporting currency)"
    )
    internalization_ratio: float = Field(
        ..., description="Internalized / total client volume (0.0 to 1.0)"
    )

    # Legacy fields (base currency - for backwards compatibility)
    total_client_volume: float = Field(
        default=0.0, description="Total client trade volume (base currency, legacy)"
    )
    total_internalized_volume: float = Field(
        default=0.0, description="Volume internalized (base currency, legacy)"
    )
    total_externalized_volume: float = Field(
        default=0.0, description="Volume hedged (base currency, legacy)"
    )

    # Per direct pair breakdown (in reporting currency)
    direct_pair_breakdown: list[DirectPairInternalization] = Field(
        default_factory=list,
        description="Internalization by direct currency pair (reporting currency)"
    )

    # Legacy field for backwards compatibility
    pair_breakdown: list[dict[str, Any]] = Field(
        default_factory=list, description="Legacy: Internalization by pair (base currency)"
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
        ..., description="Normalized risk score from P99 inventory"
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


class DecrossProgress(BaseModel):
    """Progress tracking for decrossing phase."""

    status: Annotated[
        str,
        Field(description="Decrossing status: pending, running, completed, failed"),
    ] = "pending"
    total_dates: int = Field(0, description="Total number of dates to process")
    completed_dates: int = Field(0, description="Number of dates completed")
    current_date: str | None = Field(None, description="Currently processing date")
    started_at_ms: int | None = Field(None, description="Decrossing start timestamp")
    completed_at_ms: int | None = Field(None, description="Decrossing completion timestamp")
    error: str | None = Field(None, description="Error message if failed")

    @property
    def progress_pct(self) -> float:
        """Calculate decrossing progress percentage."""
        if self.total_dates == 0:
            return 0.0
        return (self.completed_dates / self.total_dates) * 100


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

    # Decrossing progress (Phase: before shard execution)
    decross_progress: DecrossProgress = Field(
        default_factory=DecrossProgress,
        description="Progress tracking for decrossing phase"
    )

    # Shard progress tracking
    total_shards: int = 0
    completed_shards: int = 0
    failed_shards: int = 0

    # Current stage of the run (for UI progress display)
    current_stage: str | None = Field(
        None,
        description="Current stage: decrossing, simulating, computing_metrics, writing_results"
    )

    # Error info
    error_message: str | None = None
    failed_shard_details: list[FailedShardDetail] = Field(default_factory=list)

    # Config snapshot (immutable after creation)
    config: RunConfig

    @property
    def progress_pct(self) -> float:
        """Calculate shard progress percentage."""
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

    # Decrossing progress
    decross_status: str = Field("pending", description="Decrossing status")
    decross_progress_pct: float = Field(0.0, description="Decrossing progress percentage")
    decross_total_dates: int = Field(0, description="Total dates to decross")
    decross_completed_dates: int = Field(0, description="Dates completed decrossing")
    decross_current_date: str | None = Field(None, description="Currently decrossing date")

    # Shard progress
    total_shards: int
    completed_shards: int
    failed_shards: int
    progress_pct: float
    started_at_ms: int | None = None
    current_stage: str | None = Field(None, description="Current stage of the run")
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
