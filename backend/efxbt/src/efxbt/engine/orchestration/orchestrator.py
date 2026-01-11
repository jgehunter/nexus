"""Run orchestrator for parallel shard execution.

Manages parallel simulation across currency pairs with state chaining
across dates within each pair.
"""

import logging
import threading
import traceback
from concurrent.futures import Future, ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ...core.config.run_config import RunConfig, RunStatus, SimulationConfig
from ...core.data.run_models import RunSummary
from ...core.data.run_registry import (
    InvalidRunStateError,
    RunNotFoundError,
    RunRegistry,
)
from ..shard.shard_engine import ShardEngine
from ..shard.state import PnLAttributionRecord, ShardState

logger = logging.getLogger(__name__)


class PairResult:
    """Result from executing all shards for a single pair."""

    def __init__(
        self,
        pair: str,
        shard_count: int,
        pnl_records: list[PnLAttributionRecord],
        final_state: ShardState | None,
        metrics: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self.pair = pair
        self.shard_count = shard_count
        self.pnl_records = pnl_records
        self.final_state = final_state
        self.metrics = metrics
        self.error = error


def execute_pair_shards(
    pair: str,
    shards: list[dict],
    config: SimulationConfig,
    data_root: str,
) -> dict[str, Any]:
    """Execute all shards for a single pair sequentially.

    This function runs in a separate process. Dates are processed
    in chronological order with state chaining.

    Args:
        pair: Currency pair (e.g., "EURUSD")
        shards: List of {date, file_path} dicts, sorted by date
        config: Simulation configuration
        data_root: Data root directory path

    Returns:
        Dict with pair results (serializable for process pool)
    """
    from ...core.data.schemas import DecrossedTradeRecord

    all_pnl_records = []
    prior_state: ShardState | None = None
    aggregated_metrics: dict[str, float] = {
        "execution_pnl_reporting": 0.0,
        "inventory_pnl_reporting": 0.0,
        "hedge_pnl_reporting": 0.0,
        "total_client_volume": 0.0,
        "internalized_volume": 0.0,
        "externalized_volume": 0.0,
    }
    shard_results = []

    try:
        for shard_info in shards:
            # Load trades
            table = pq.read_table(shard_info["file_path"])
            client_trades = [
                DecrossedTradeRecord(**row) for row in table.to_pylist()
            ]

            # Create engine
            engine = ShardEngine(
                pair=pair,
                date=shard_info["date"],
                config=config,
                data_root=Path(data_root),
            )

            # Run with state chaining
            result = engine.run(client_trades, prior_state)

            # Collect PnL records
            all_pnl_records.extend(result.pnl_records)

            # Aggregate metrics
            for key in aggregated_metrics:
                aggregated_metrics[key] += result.metrics.get(key, 0.0)

            shard_results.append({
                "pair": pair,
                "date": shard_info["date"],
                **result.metrics,
            })

            # Chain state to next day
            prior_state = result.final_state

        return {
            "pair": pair,
            "shard_count": len(shards),
            "pnl_records": [_serialize_pnl_record(r) for r in all_pnl_records],
            "metrics": aggregated_metrics,
            "shard_results": shard_results,
            "error": None,
        }

    except Exception as e:
        logger.exception(f"Error executing shards for {pair}")
        return {
            "pair": pair,
            "shard_count": len(shards),
            "pnl_records": [],
            "metrics": aggregated_metrics,
            "shard_results": shard_results,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def _serialize_pnl_record(record: PnLAttributionRecord) -> dict:
    """Serialize PnL record for cross-process transfer."""
    return {
        "timestamp_ms": record.timestamp_ms,
        "trade_attributions": [
            attr.model_dump() for attr in record.trade_attributions
        ],
    }


class RunOrchestrator:
    """Orchestrates parallel simulation across pairs with state chaining.

    Key constraint: Within a pair, dates MUST be processed sequentially
    (day N final_state -> day N+1 prior_state). Different pairs can run
    in parallel.
    """

    def __init__(
        self,
        registry: RunRegistry,
        data_root: Path,
        max_workers: int = 4,
    ) -> None:
        """Initialize orchestrator.

        Args:
            registry: Run registry for persistence
            data_root: Root directory for market/trade data
            max_workers: Maximum parallel workers (one per pair)
        """
        self.registry = registry
        self.data_root = Path(data_root)
        self.max_workers = max_workers

        # Active runs tracking
        self._active_runs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start_run(self, run_id: str, decrossed_data_dir: Path) -> None:
        """Start run execution in background.

        Uses ProcessPoolExecutor for CPU-bound shard simulation.
        Each pair gets a worker that processes dates sequentially.

        Args:
            run_id: Run identifier
            decrossed_data_dir: Directory with decrossed trades

        Raises:
            InvalidRunStateError: If run not in CREATED status
            RunNotFoundError: If run doesn't exist
        """
        run = self.registry.get_run(run_id)

        if run.status != RunStatus.CREATED:
            raise InvalidRunStateError(
                run_id, run.status, "Can only start runs in CREATED status"
            )

        # Discover shards and group by pair
        shards = self._discover_shards(decrossed_data_dir)

        if not shards:
            # No shards to simulate - mark as completed immediately
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            self.registry.update_status(
                run_id,
                RunStatus.COMPLETED,
                started_at_ms=now_ms,
                completed_at_ms=now_ms,
            )
            self._write_empty_results(run_id)
            return

        shards_by_pair = self._group_by_pair(shards)

        # Update status to running with shard count
        self.registry.update_status(
            run_id,
            RunStatus.RUNNING,
            started_at_ms=int(datetime.utcnow().timestamp() * 1000),
        )
        self.registry.update_progress(run_id, total_shards=len(shards))

        # Create cancellation event
        cancel_event = threading.Event()

        # Build simulation config
        sim_config = run.config.simulation_config
        if sim_config is None:
            sim_config = SimulationConfig(dataset=run.config.dataset)

        # Submit pair workers to executor
        executor = ProcessPoolExecutor(max_workers=self.max_workers)
        futures: list[tuple[str, Future]] = []

        for pair, pair_shards in shards_by_pair.items():
            # Sort by date for chronological processing
            pair_shards.sort(key=lambda s: s["date"])

            future = executor.submit(
                execute_pair_shards,
                pair=pair,
                shards=pair_shards,
                config=sim_config,
                data_root=str(self.data_root),
            )
            futures.append((pair, future))

        # Track active run
        with self._lock:
            self._active_runs[run_id] = {
                "executor": executor,
                "futures": futures,
                "cancel_event": cancel_event,
                "shards_by_pair": shards_by_pair,
            }

        # Start completion monitor thread
        threading.Thread(
            target=self._monitor_completion,
            args=(run_id, futures, executor),
            daemon=True,
        ).start()

    def cancel_run(self, run_id: str) -> bool:
        """Request best-effort cancellation.

        Sets cancel flag; running shards will complete but no new
        shards will start.

        Args:
            run_id: Run identifier

        Returns:
            True if cancellation requested, False if run not active
        """
        with self._lock:
            if run_id not in self._active_runs:
                # Check if run exists and update status if in RUNNING state
                try:
                    run = self.registry.get_run(run_id)
                    if run.status == RunStatus.RUNNING:
                        self.registry.update_status(run_id, RunStatus.CANCELLED)
                        return True
                except RunNotFoundError:
                    pass
                return False

            self._active_runs[run_id]["cancel_event"].set()

        self.registry.update_status(run_id, RunStatus.CANCELLED)
        return True

    def is_active(self, run_id: str) -> bool:
        """Check if run is currently being executed.

        Args:
            run_id: Run identifier

        Returns:
            True if run is active in this orchestrator
        """
        with self._lock:
            return run_id in self._active_runs

    def _discover_shards(self, decrossed_data_dir: Path) -> list[dict]:
        """Discover all (date, pair) shards from decrossed output.

        Args:
            decrossed_data_dir: Directory with structure {YYYYMMDD}/{PAIR}.parquet

        Returns:
            List of shard info dicts
        """
        shards = []

        if not decrossed_data_dir.exists():
            return shards

        for date_dir in decrossed_data_dir.iterdir():
            if not date_dir.is_dir():
                continue

            date_str = date_dir.name

            for pair_file in date_dir.glob("*.parquet"):
                pair = pair_file.stem

                shards.append({
                    "pair": pair,
                    "date": date_str,
                    "file_path": str(pair_file),
                })

        return shards

    def _group_by_pair(self, shards: list[dict]) -> dict[str, list[dict]]:
        """Group shards by currency pair.

        Args:
            shards: List of shard info dicts

        Returns:
            Dict mapping pair to list of shards
        """
        by_pair: dict[str, list[dict]] = {}

        for shard in shards:
            pair = shard["pair"]
            if pair not in by_pair:
                by_pair[pair] = []
            by_pair[pair].append(shard)

        return by_pair

    def _monitor_completion(
        self,
        run_id: str,
        futures: list[tuple[str, Future]],
        executor: ProcessPoolExecutor,
    ) -> None:
        """Monitor futures and update status on completion.

        Args:
            run_id: Run identifier
            futures: List of (pair, future) tuples
            executor: ProcessPoolExecutor to shutdown
        """
        all_results: list[dict] = []
        failed_pairs: list[dict] = []
        completed_shards = 0

        for pair, future in futures:
            try:
                result = future.result()  # Blocks until complete
                all_results.append(result)

                # Update progress
                completed_shards += result.get("shard_count", 0)
                self.registry.update_progress(run_id, completed_shards=completed_shards)

                # Track failures
                if result.get("error"):
                    failed_pairs.append({
                        "pair": pair,
                        "error": result["error"],
                        "traceback": result.get("traceback"),
                    })
                    # Add failed shard details
                    for shard_result in result.get("shard_results", []):
                        self.registry.add_failed_shard(
                            run_id,
                            pair=pair,
                            date=shard_result.get("date", "unknown"),
                            error=result["error"],
                        )

            except Exception as e:
                logger.exception(f"Error getting result for {pair}")
                failed_pairs.append({
                    "pair": pair,
                    "error": str(e),
                })

        executor.shutdown(wait=True)

        # Determine final status
        try:
            run = self.registry.get_run(run_id)

            # Check if cancelled
            if run.status == RunStatus.CANCELLED:
                self._cleanup_active_run(run_id)
                return

            # Aggregate results and write
            self._write_final_results(run_id, all_results)

            if failed_pairs:
                self.registry.update_status(
                    run_id,
                    RunStatus.FAILED,
                    completed_at_ms=int(datetime.utcnow().timestamp() * 1000),
                    error_message=f"{len(failed_pairs)} pair(s) failed",
                )
            else:
                self.registry.update_status(
                    run_id,
                    RunStatus.COMPLETED,
                    completed_at_ms=int(datetime.utcnow().timestamp() * 1000),
                )

        except Exception as e:
            logger.exception(f"Error finalizing run {run_id}")
            try:
                self.registry.update_status(
                    run_id,
                    RunStatus.FAILED,
                    completed_at_ms=int(datetime.utcnow().timestamp() * 1000),
                    error_message=f"Finalization error: {e}",
                )
            except Exception:
                pass

        finally:
            self._cleanup_active_run(run_id)

    def _cleanup_active_run(self, run_id: str) -> None:
        """Remove run from active tracking.

        Args:
            run_id: Run identifier
        """
        with self._lock:
            if run_id in self._active_runs:
                del self._active_runs[run_id]

    def _write_final_results(self, run_id: str, all_results: list[dict]) -> None:
        """Aggregate and write final results.

        Args:
            run_id: Run identifier
            all_results: List of pair result dicts
        """
        run_dir = self.registry.get_run_dir(run_id)

        # Aggregate PnL records
        all_pnl_rows = []
        for result in all_results:
            for record in result.get("pnl_records", []):
                for attr in record.get("trade_attributions", []):
                    all_pnl_rows.append({
                        "timestamp_ms": record["timestamp_ms"],
                        **attr,
                    })

        # Write PnL attribution
        if all_pnl_rows:
            table = pa.Table.from_pylist(all_pnl_rows)
            pq.write_table(
                table,
                run_dir / "pnl_attribution.parquet",
                compression="snappy",
            )
        else:
            # Write empty table
            empty_table = pa.table({})
            pq.write_table(empty_table, run_dir / "pnl_attribution.parquet")

        # Aggregate metrics for summary
        pairs = []
        dates = set()
        total_exec_pnl = 0.0
        total_inv_pnl = 0.0
        total_hedge_pnl = 0.0
        total_client_volume = 0.0
        total_internalized = 0.0
        total_externalized = 0.0
        pair_summaries = []

        for result in all_results:
            if result.get("error"):
                continue

            pair = result["pair"]
            pairs.append(pair)
            metrics = result.get("metrics", {})

            total_exec_pnl += metrics.get("execution_pnl_reporting", 0.0)
            total_inv_pnl += metrics.get("inventory_pnl_reporting", 0.0)
            total_hedge_pnl += metrics.get("hedge_pnl_reporting", 0.0)
            total_client_volume += metrics.get("total_client_volume", 0.0)
            total_internalized += metrics.get("internalized_volume", 0.0)
            total_externalized += metrics.get("externalized_volume", 0.0)

            # Collect dates from shard results
            for shard_result in result.get("shard_results", []):
                dates.add(shard_result.get("date", ""))

            pair_summaries.append({
                "pair": pair,
                "shard_count": result.get("shard_count", 0),
                **metrics,
            })

        sorted_dates = sorted(dates)
        date_range = (sorted_dates[0], sorted_dates[-1]) if sorted_dates else None

        summary = RunSummary(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            pairs=sorted(pairs),
            date_range=date_range,
            total_shards=sum(r.get("shard_count", 0) for r in all_results),
            total_execution_pnl=total_exec_pnl,
            total_inventory_pnl=total_inv_pnl,
            total_hedge_pnl=total_hedge_pnl,
            total_pnl=total_exec_pnl + total_inv_pnl + total_hedge_pnl,
            total_client_volume=total_client_volume,
            total_internalized_volume=total_internalized,
            total_externalized_volume=total_externalized,
            internalization_ratio=(
                total_internalized / total_client_volume
                if total_client_volume > 0
                else 0.0
            ),
            pair_summaries=pair_summaries,
        )

        self.registry.write_summary(run_id, summary)

    def _write_empty_results(self, run_id: str) -> None:
        """Write empty results for runs with no shards.

        Args:
            run_id: Run identifier
        """
        run_dir = self.registry.get_run_dir(run_id)

        # Write empty PnL file
        empty_table = pa.table({})
        pq.write_table(empty_table, run_dir / "pnl_attribution.parquet")

        # Write empty summary
        summary = RunSummary(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            pairs=[],
            date_range=None,
            total_shards=0,
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
        self.registry.write_summary(run_id, summary)
