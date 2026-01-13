"""Service layer for run orchestration operations.

Provides business logic for creating, starting, and monitoring backtest runs.

Run execution (decrossing + orchestration) is performed in a background thread
to allow immediate HTTP response and progress polling from the frontend.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
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
    TradeRecord,
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
from .decross import DecrossService
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

        # Initialize decrossing service
        self.decross_service = DecrossService(data_root)

        # ThreadPoolExecutor for background run execution
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="run_exec")

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

        # Validate tradebook exists (required)
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
        """Start run execution in background thread.

        Returns immediately after submitting the run to the executor.
        The frontend can poll for progress using get_status().

        Args:
            run_id: Run identifier

        Returns:
            RunStatusResponse with initial RUNNING status

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run not in CREATED status
        """
        run = self.registry.get_run(run_id)

        if run.status != RunStatus.CREATED:
            raise InvalidRunStateError(
                run_id, run.status, "Can only start runs in CREATED status"
            )

        # Update status to RUNNING immediately so frontend knows execution started
        self.registry.update_status(run_id, RunStatus.RUNNING)

        # Submit execution to background thread
        logger.info(f"Submitting run {run_id} to background executor")
        self._executor.submit(self._execute_run, run_id)

        # Return immediately with RUNNING status
        return self.get_status(run_id)

    def _execute_run(self, run_id: str) -> None:
        """Execute run in background thread.

        Performs decrossing and orchestration. Updates progress via registry.

        Args:
            run_id: Run identifier
        """
        try:
            run = self.registry.get_run(run_id)

            # Get run output directory for decrossed data
            run_dir = self.registry.get_run_dir(run_id)
            decrossed_data_dir = run_dir / "decrossed"

            # Run decrossing (tradebook is always required now)
            logger.info(
                f"Running decrossing for run {run_id}: "
                f"tradebook={run.config.tradebook}, dataset={run.config.dataset}"
            )

            # Build date range if specified
            date_range = None
            if run.config.start_date and run.config.end_date:
                date_range = (run.config.start_date, run.config.end_date)

            # Define progress callback for decrossing
            def decross_progress_callback(
                stage: str, current: int, total: int, message: str
            ) -> None:
                """Update decrossing progress in registry."""
                # Extract current date from message if present
                current_date = None
                if message.startswith("Decrossing "):
                    current_date = message.split()[-1]

                self.registry.update_decross_progress(
                    run_id,
                    completed_dates=current,
                    total_dates=total,
                    current_date=current_date,
                )

            # Run decrossing pipeline with progress tracking
            try:
                self.decross_service.decross_tradebook(
                    tradebook_name=run.config.tradebook,
                    market_dataset_name=run.config.dataset,
                    output_dir=decrossed_data_dir,
                    date_range=date_range,
                    progress_callback=decross_progress_callback,
                )
                self.registry.complete_decrossing(run_id, success=True)
                logger.info(f"Decrossing complete for run {run_id}")

            except Exception as e:
                self.registry.complete_decrossing(run_id, success=False, error=str(e))
                logger.exception(f"Decrossing failed for run {run_id}: {e}")
                # Mark run as failed and return (don't proceed to orchestration)
                self.registry.update_status(run_id, RunStatus.FAILED, error_message=str(e))
                return

            # Start orchestration
            self.orchestrator.start_run(run_id, decrossed_data_dir)
            logger.info(f"Run {run_id} execution complete")

        except Exception as e:
            # Catch-all for unexpected errors
            logger.exception(f"Run {run_id} failed with unexpected error: {e}")
            try:
                self.registry.update_status(run_id, RunStatus.FAILED, error_message=str(e))
            except Exception:
                logger.exception(f"Failed to update status for run {run_id}")

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
            # Decrossing progress
            decross_status=run.decross_progress.status,
            decross_progress_pct=run.decross_progress.progress_pct,
            decross_total_dates=run.decross_progress.total_dates,
            decross_completed_dates=run.decross_progress.completed_dates,
            decross_current_date=run.decross_progress.current_date,
            # Shard progress
            total_shards=run.total_shards,
            completed_shards=run.completed_shards,
            failed_shards=run.failed_shards,
            progress_pct=run.progress_pct,
            started_at_ms=run.started_at_ms,
            current_stage=run.current_stage,
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
            import duckdb

            # Use DuckDB for aggregation with context manager for proper cleanup
            with duckdb.connect(":memory:") as conn:
                # Query to aggregate PnL by timestamp
                query = f"""
                SELECT
                    timestamp_ms,
                    COALESCE(SUM(execution_pnl_reporting), 0) as exec_pnl,
                    COALESCE(SUM(inventory_pnl_reporting), 0) as inv_pnl,
                    COALESCE(SUM(hedge_pnl_reporting), 0) as hedge_pnl
                FROM read_parquet('{pnl_path}')
                GROUP BY timestamp_ms
                ORDER BY timestamp_ms
                """

                result = conn.execute(query).fetchall()

            if not result:
                return TimeseriesResponse(run_id=run_id, sample_points=0, points=[])

            # Compute cumulative PnL
            cumulative_pnl = 0.0
            raw_series = []

            for row in result:
                ts, exec_pnl, inv_pnl, hedge_pnl = row
                pnl = exec_pnl + inv_pnl + hedge_pnl
                cumulative_pnl += pnl
                raw_series.append((ts, cumulative_pnl))

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
            import duckdb

            # Build query based on grouping
            if group_by == "total":
                query = f"""
                SELECT
                    'total' as group_name,
                    COALESCE(SUM(execution_pnl_reporting), 0) as execution_pnl,
                    COALESCE(SUM(inventory_pnl_reporting), 0) as inventory_pnl,
                    COALESCE(SUM(hedge_pnl_reporting), 0) as hedge_pnl
                FROM read_parquet('{pnl_path}')
                """
            elif group_by == "pair":
                query = f"""
                SELECT
                    pair as group_name,
                    COALESCE(SUM(execution_pnl_reporting), 0) as execution_pnl,
                    COALESCE(SUM(inventory_pnl_reporting), 0) as inventory_pnl,
                    COALESCE(SUM(hedge_pnl_reporting), 0) as hedge_pnl
                FROM read_parquet('{pnl_path}')
                GROUP BY pair
                ORDER BY pair
                """
            elif group_by == "date":
                # Handle both millisecond and microsecond timestamps
                query = f"""
                SELECT
                    strftime(
                        to_timestamp(
                            CASE WHEN timestamp_ms > 9999999999999
                                THEN timestamp_ms / 1000000.0
                                ELSE timestamp_ms / 1000.0
                            END
                        ),
                        '%Y%m%d'
                    ) as group_name,
                    COALESCE(SUM(execution_pnl_reporting), 0) as execution_pnl,
                    COALESCE(SUM(inventory_pnl_reporting), 0) as inventory_pnl,
                    COALESCE(SUM(hedge_pnl_reporting), 0) as hedge_pnl
                FROM read_parquet('{pnl_path}')
                GROUP BY group_name
                ORDER BY group_name
                """
            else:
                return PnLBreakdownResponse(
                    run_id=run_id,
                    group_by=group_by,
                    breakdown=[],
                )

            # Use context manager for proper connection cleanup
            with duckdb.connect(":memory:") as conn:
                result = conn.execute(query).fetchall()

            breakdown = []
            for row in result:
                group_name, exec_pnl, inv_pnl, hedge_pnl = row
                entry = {
                    "group": group_name,
                    "execution_pnl": float(exec_pnl),
                    "inventory_pnl": float(inv_pnl),
                    "hedge_pnl": float(hedge_pnl),
                    "total_pnl": float(exec_pnl + inv_pnl + hedge_pnl),
                }
                breakdown.append(entry)

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

    def get_trades(
        self,
        run_id: str,
        limit: int = 100,
        offset: int = 0,
        pair: str | None = None,
    ) -> tuple[list[TradeRecord], int]:
        """Get paginated trade-level data.

        Args:
            run_id: Run identifier
            limit: Maximum trades to return
            offset: Pagination offset
            pair: Optional filter by currency pair

        Returns:
            Tuple of (trade records, total count)

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run not completed
        """
        run = self.registry.get_run(run_id)

        if run.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
            raise InvalidRunStateError(
                run_id,
                run.status,
                "Trades only available for completed or failed runs",
            )

        pnl_path = self.registry.get_run_dir(run_id) / "pnl_attribution.parquet"

        if not pnl_path.exists():
            return [], 0

        try:
            import duckdb

            # Build WHERE clause for pair filter
            where_clause = f"WHERE pair = '{pair}'" if pair else ""

            # Use context manager for proper connection cleanup
            with duckdb.connect(":memory:") as conn:
                # Count total rows
                count_query = f"""
                SELECT COUNT(*) FROM read_parquet('{pnl_path}')
                {where_clause}
                """
                total = conn.execute(count_query).fetchone()[0]

                if total == 0:
                    return [], 0

                # Query for paginated trades
                query = f"""
                SELECT
                    timestamp_ms,
                    pair,
                    event_type,
                    side,
                    qty,
                    price,
                    COALESCE(execution_pnl_reporting, execution_pnl, 0) as execution_pnl,
                    COALESCE(inventory_pnl_reporting, inventory_pnl, 0) as inventory_pnl,
                    COALESCE(hedge_pnl_reporting, hedge_pnl, 0) as hedge_pnl,
                    source_trade_id
                FROM read_parquet('{pnl_path}')
                {where_clause}
                ORDER BY timestamp_ms
                LIMIT {limit} OFFSET {offset}
                """

                result = conn.execute(query).fetchall()

            # Convert to TradeRecord objects
            trades = []
            for row in result:
                ts, p, event, s, q, pr, exec_pnl, inv_pnl, h_pnl, src_id = row
                trade = TradeRecord(
                    timestamp_ms=int(ts) if ts else 0,
                    pair=str(p) if p else "",
                    event_type=str(event) if event else "unknown",
                    side=int(s) if s else 0,
                    qty=float(q) if q else 0.0,
                    price=float(pr) if pr else 0.0,
                    execution_pnl=float(exec_pnl) if exec_pnl else 0.0,
                    inventory_pnl=float(inv_pnl) if inv_pnl else 0.0,
                    hedge_pnl=float(h_pnl) if h_pnl else 0.0,
                    source_trade_id=str(src_id) if src_id else None,
                )
                trades.append(trade)

            return trades, total

        except Exception as e:
            logger.exception(f"Error getting trades for {run_id}")
            return [], 0

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
