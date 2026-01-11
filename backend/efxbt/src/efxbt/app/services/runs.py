"""Service layer for run orchestration operations.

Provides business logic for creating, starting, and monitoring backtest runs.
"""

import logging
from pathlib import Path

from ...core.config.run_config import RunConfig, RunStatus
from ...core.data.run_models import (
    CancelResponse,
    PnLBreakdownResponse,
    RunCreateResponse,
    RunDetailResponse,
    RunListResponse,
    RunStatusResponse,
    RunSummary,
    TimeseriesPoint,
    TimeseriesResponse,
)
from ...core.data.run_registry import (
    DuplicateRunError,
    InvalidRunStateError,
    RunNotFoundError,
    RunRecord,
    RunRegistry,
)
from ...engine.orchestration.orchestrator import RunOrchestrator
from ...util.downsample import lttb_downsample
from .datasets import DatasetsService
from .tradebooks import TradeBooksService

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when run configuration validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class RunService:
    """Service for run orchestration operations.

    Follows the service pattern established by DatasetsService and TradeBooksService.
    """

    def __init__(
        self,
        data_root: Path,
        results_root: Path,
        orchestrator: RunOrchestrator | None = None,
    ) -> None:
        """Initialize service.

        Args:
            data_root: Root directory for market/trade data
            results_root: Root directory for results storage
            orchestrator: Optional pre-configured orchestrator (for singleton pattern)
        """
        self.data_root = Path(data_root)
        self.results_root = Path(results_root)
        self.registry = RunRegistry(results_root)

        if orchestrator is not None:
            self.orchestrator = orchestrator
        else:
            self.orchestrator = RunOrchestrator(
                registry=self.registry,
                data_root=self.data_root,
            )

        # Initialize validation services
        self.datasets_service = DatasetsService(data_root)
        self.tradebooks_service = TradeBooksService(data_root)

    def create_run(
        self,
        config: RunConfig,
        idempotence: str = "error",
    ) -> RunCreateResponse:
        """Validate config and create run record.

        Returns run_id without starting execution.

        Args:
            config: Run configuration
            idempotence: Behavior if duplicate config found:
                - "error": Return 409 Conflict
                - "reuse": Return existing run
                - "new": Create new run anyway

        Returns:
            RunCreateResponse with run_id and status

        Raises:
            ValidationError: If config validation fails
            DuplicateRunError: If idempotence="error" and duplicate found
        """
        # Validate dataset exists
        try:
            self.datasets_service.get_dataset(config.dataset)
        except FileNotFoundError:
            raise ValidationError(f"Dataset '{config.dataset}' not found")

        # Validate tradebook exists if specified
        if config.tradebook:
            try:
                self.tradebooks_service.get_tradebook(config.tradebook)
            except FileNotFoundError:
                raise ValidationError(f"Tradebook '{config.tradebook}' not found")

        # Validate simulation config dataset
        if config.simulation_config and config.simulation_config.dataset:
            try:
                self.datasets_service.get_dataset(config.simulation_config.dataset)
            except FileNotFoundError:
                raise ValidationError(
                    f"Simulation dataset '{config.simulation_config.dataset}' not found"
                )

        # Create run with idempotence check
        try:
            run, is_new = self.registry.create_run_with_idempotence(
                config, behavior=idempotence
            )
        except DuplicateRunError:
            raise

        return RunCreateResponse(
            run_id=run.run_id,
            status=run.status,
            is_new=is_new,
            config_hash=run.config_hash,
        )

    def start_run(self, run_id: str) -> RunStatusResponse:
        """Start run execution.

        Args:
            run_id: Run identifier

        Returns:
            RunStatusResponse with updated status

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run not in CREATED status
        """
        run = self.registry.get_run(run_id)

        if run.status != RunStatus.CREATED:
            raise InvalidRunStateError(
                run_id, run.status, "Can only start runs in CREATED status"
            )

        # Determine decrossed data directory
        # This should be in the run's output directory or a staging area
        decrossed_data_dir = self._get_decrossed_data_dir(run)

        # Start orchestration
        self.orchestrator.start_run(run_id, decrossed_data_dir)

        # Return updated status
        return self.get_status(run_id)

    def get_status(self, run_id: str) -> RunStatusResponse:
        """Get current run status and progress.

        Args:
            run_id: Run identifier

        Returns:
            RunStatusResponse with status and progress

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.registry.get_run(run_id)

        return RunStatusResponse(
            run_id=run.run_id,
            status=run.status,
            total_shards=run.total_shards,
            completed_shards=run.completed_shards,
            failed_shards=run.failed_shards,
            progress_pct=run.progress_pct,
            started_at_ms=run.started_at_ms,
            error_message=run.error_message,
        )

    def get_run_detail(self, run_id: str) -> RunDetailResponse:
        """Get full details of a run including config.

        Args:
            run_id: Run identifier

        Returns:
            RunDetailResponse with full run details

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.registry.get_run(run_id)

        return RunDetailResponse(
            run_id=run.run_id,
            status=run.status,
            config_hash=run.config_hash,
            config=run.config,
            created_at_ms=run.created_at_ms,
            started_at_ms=run.started_at_ms,
            completed_at_ms=run.completed_at_ms,
            total_shards=run.total_shards,
            completed_shards=run.completed_shards,
            failed_shards=run.failed_shards,
            progress_pct=run.progress_pct,
            error_message=run.error_message,
            failed_shard_details=run.failed_shard_details,
        )

    def cancel_run(self, run_id: str) -> CancelResponse:
        """Request cancellation of a running run.

        Args:
            run_id: Run identifier

        Returns:
            CancelResponse indicating success

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run = self.registry.get_run(run_id)

        if run.status not in (RunStatus.CREATED, RunStatus.RUNNING):
            return CancelResponse(
                run_id=run_id,
                cancelled=False,
                message=f"Cannot cancel run in {run.status} status",
            )

        cancelled = self.orchestrator.cancel_run(run_id)

        if not cancelled and run.status == RunStatus.CREATED:
            # Directly update status for runs that haven't started
            self.registry.update_status(run_id, RunStatus.CANCELLED)
            cancelled = True

        return CancelResponse(
            run_id=run_id,
            cancelled=cancelled,
            message="Cancellation requested" if cancelled else "Run not active",
        )

    def delete_run(self, run_id: str) -> None:
        """Delete run and all results.

        Args:
            run_id: Run identifier

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run is currently running
        """
        self.registry.delete_run(run_id)

    def list_runs(
        self,
        status: RunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> RunListResponse:
        """List runs with optional filters.

        Args:
            status: Filter by status (None = all)
            limit: Maximum runs to return
            offset: Number of runs to skip

        Returns:
            RunListResponse with paginated runs
        """
        runs = self.registry.list_runs(status=status, limit=limit, offset=offset)

        run_details = [
            RunDetailResponse(
                run_id=run.run_id,
                status=run.status,
                config_hash=run.config_hash,
                config=run.config,
                created_at_ms=run.created_at_ms,
                started_at_ms=run.started_at_ms,
                completed_at_ms=run.completed_at_ms,
                total_shards=run.total_shards,
                completed_shards=run.completed_shards,
                failed_shards=run.failed_shards,
                progress_pct=run.progress_pct,
                error_message=run.error_message,
                failed_shard_details=run.failed_shard_details,
            )
            for run in runs
        ]

        return RunListResponse(
            runs=run_details,
            total=len(run_details),
            limit=limit,
            offset=offset,
        )

    def get_summary(self, run_id: str) -> RunSummary:
        """Get summary results for a completed run.

        Args:
            run_id: Run identifier

        Returns:
            RunSummary with aggregated metrics

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run not completed
        """
        run = self.registry.get_run(run_id)

        if run.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
            raise InvalidRunStateError(
                run_id,
                run.status,
                "Summary only available for completed or failed runs",
            )

        try:
            summary_data = self.registry.read_summary(run_id)
            return RunSummary(**summary_data)
        except FileNotFoundError:
            # Return empty summary if file missing
            return RunSummary(
                run_id=run_id,
                status=run.status,
                pairs=[],
                date_range=None,
                total_shards=run.total_shards,
                total_execution_pnl=0.0,
                total_inventory_pnl=0.0,
                total_hedge_pnl=0.0,
                total_pnl=0.0,
                total_client_volume=0.0,
                total_internalized_volume=0.0,
                total_externalized_volume=0.0,
                internalization_ratio=0.0,
                pair_summaries=[],
            )

    def get_timeseries(
        self,
        run_id: str,
        sample_points: int = 500,
    ) -> TimeseriesResponse:
        """Get downsampled time series for visualization.

        Uses LTTB algorithm for intelligent downsampling.

        Args:
            run_id: Run identifier
            sample_points: Target number of points (10-5000)

        Returns:
            TimeseriesResponse with downsampled points

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run not completed
        """
        import pyarrow.parquet as pq

        run = self.registry.get_run(run_id)

        if run.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
            raise InvalidRunStateError(
                run_id,
                run.status,
                "Time series only available for completed or failed runs",
            )

        # Load PnL attribution file
        pnl_path = self.registry.get_run_dir(run_id) / "pnl_attribution.parquet"

        if not pnl_path.exists():
            return TimeseriesResponse(
                run_id=run_id,
                sample_points=0,
                points=[],
            )

        try:
            table = pq.read_table(pnl_path)
            if table.num_rows == 0:
                return TimeseriesResponse(
                    run_id=run_id,
                    sample_points=0,
                    points=[],
                )

            # Extract timestamps and PnL columns
            df = table.to_pandas()

            # Group by timestamp and compute cumulative PnL
            if "timestamp_ms" not in df.columns:
                return TimeseriesResponse(run_id=run_id, sample_points=0, points=[])

            # Get PnL columns
            exec_col = "execution_pnl_reporting"
            inv_col = "inventory_pnl_reporting"
            hedge_col = "hedge_pnl_reporting"

            # Aggregate by timestamp
            agg_cols = {}
            for col in [exec_col, inv_col, hedge_col]:
                if col in df.columns:
                    agg_cols[col] = "sum"

            if not agg_cols:
                return TimeseriesResponse(run_id=run_id, sample_points=0, points=[])

            grouped = df.groupby("timestamp_ms").agg(agg_cols).reset_index()
            grouped = grouped.sort_values("timestamp_ms")

            # Compute cumulative PnL
            cumulative_pnl = 0.0
            raw_series = []

            for _, row in grouped.iterrows():
                pnl = sum(row.get(col, 0.0) for col in agg_cols.keys())
                cumulative_pnl += pnl
                raw_series.append((row["timestamp_ms"], cumulative_pnl))

            # Apply LTTB downsampling
            if len(raw_series) > sample_points:
                downsampled = lttb_downsample(raw_series, sample_points)
            else:
                downsampled = raw_series

            points = [
                TimeseriesPoint(
                    timestamp_ms=int(ts),
                    cumulative_pnl=pnl,
                    net_position=0.0,  # Would need position tracking
                    unrealized_pnl=0.0,
                )
                for ts, pnl in downsampled
            ]

            return TimeseriesResponse(
                run_id=run_id,
                sample_points=len(points),
                points=points,
            )

        except Exception as e:
            logger.exception(f"Error loading time series for {run_id}")
            return TimeseriesResponse(run_id=run_id, sample_points=0, points=[])

    def get_pnl_breakdown(
        self,
        run_id: str,
        group_by: str = "total",
    ) -> PnLBreakdownResponse:
        """Get PnL breakdown by grouping level.

        Args:
            run_id: Run identifier
            group_by: Grouping level: "total", "pair", or "date"

        Returns:
            PnLBreakdownResponse with breakdown data

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run not completed
        """
        import pyarrow.parquet as pq

        run = self.registry.get_run(run_id)

        if run.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
            raise InvalidRunStateError(
                run_id,
                run.status,
                "PnL breakdown only available for completed or failed runs",
            )

        pnl_path = self.registry.get_run_dir(run_id) / "pnl_attribution.parquet"

        if not pnl_path.exists():
            return PnLBreakdownResponse(
                run_id=run_id,
                group_by=group_by,
                breakdown=[],
            )

        try:
            table = pq.read_table(pnl_path)
            if table.num_rows == 0:
                return PnLBreakdownResponse(
                    run_id=run_id,
                    group_by=group_by,
                    breakdown=[],
                )

            df = table.to_pandas()

            # PnL columns
            pnl_cols = [
                "execution_pnl_reporting",
                "inventory_pnl_reporting",
                "hedge_pnl_reporting",
            ]
            available_cols = [c for c in pnl_cols if c in df.columns]

            if not available_cols:
                return PnLBreakdownResponse(
                    run_id=run_id,
                    group_by=group_by,
                    breakdown=[],
                )

            if group_by == "total":
                breakdown = [{
                    "group": "total",
                    "execution_pnl": df[available_cols[0]].sum() if len(available_cols) > 0 else 0.0,
                    "inventory_pnl": df[available_cols[1]].sum() if len(available_cols) > 1 else 0.0,
                    "hedge_pnl": df[available_cols[2]].sum() if len(available_cols) > 2 else 0.0,
                }]
                breakdown[0]["total_pnl"] = sum(
                    breakdown[0].get(k, 0.0)
                    for k in ["execution_pnl", "inventory_pnl", "hedge_pnl"]
                )

            elif group_by == "pair" and "pair" in df.columns:
                grouped = df.groupby("pair")[available_cols].sum().reset_index()
                breakdown = []
                for _, row in grouped.iterrows():
                    entry = {
                        "group": row["pair"],
                        "execution_pnl": row.get(available_cols[0], 0.0) if len(available_cols) > 0 else 0.0,
                        "inventory_pnl": row.get(available_cols[1], 0.0) if len(available_cols) > 1 else 0.0,
                        "hedge_pnl": row.get(available_cols[2], 0.0) if len(available_cols) > 2 else 0.0,
                    }
                    entry["total_pnl"] = sum(
                        entry.get(k, 0.0)
                        for k in ["execution_pnl", "inventory_pnl", "hedge_pnl"]
                    )
                    breakdown.append(entry)

            elif group_by == "date" and "timestamp_ms" in df.columns:
                # Extract date from timestamp (convert ms to YYYYMMDD)
                from datetime import datetime, timezone
                df["date"] = df["timestamp_ms"].apply(
                    lambda x: datetime.fromtimestamp(x / 1000, tz=timezone.utc).strftime("%Y%m%d") if x else "unknown"
                )
                grouped = df.groupby("date")[available_cols].sum().reset_index()
                breakdown = []
                for _, row in grouped.iterrows():
                    entry = {
                        "group": row["date"],
                        "execution_pnl": row.get(available_cols[0], 0.0) if len(available_cols) > 0 else 0.0,
                        "inventory_pnl": row.get(available_cols[1], 0.0) if len(available_cols) > 1 else 0.0,
                        "hedge_pnl": row.get(available_cols[2], 0.0) if len(available_cols) > 2 else 0.0,
                    }
                    entry["total_pnl"] = sum(
                        entry.get(k, 0.0)
                        for k in ["execution_pnl", "inventory_pnl", "hedge_pnl"]
                    )
                    breakdown.append(entry)
            else:
                breakdown = []

            return PnLBreakdownResponse(
                run_id=run_id,
                group_by=group_by,
                breakdown=breakdown,
            )

        except Exception as e:
            logger.exception(f"Error computing PnL breakdown for {run_id}")
            return PnLBreakdownResponse(
                run_id=run_id,
                group_by=group_by,
                breakdown=[],
            )

    def _get_decrossed_data_dir(self, run: RunRecord) -> Path:
        """Get the decrossed data directory for a run.

        For now, this assumes decrossed data is in a standard location.
        In a full implementation, this would be set during run creation
        or after the decrossing phase completes.

        Args:
            run: Run record

        Returns:
            Path to decrossed data directory
        """
        # Default: look in run directory for decrossed data
        run_dir = self.registry.get_run_dir(run.run_id)
        decrossed_dir = run_dir / "decrossed"

        # If not there, try results root
        if not decrossed_dir.exists():
            decrossed_dir = self.results_root / "decrossed" / run.config.tradebook

        return decrossed_dir
