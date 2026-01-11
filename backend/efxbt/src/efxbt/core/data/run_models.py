"""Run-related data models for orchestration and persistence."""

from typing import Annotated, Any

from pydantic import BaseModel, Field

from ..config.run_config import RunConfig, RunStatus


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
