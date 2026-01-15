"""Run orchestrator for parallel shard execution.

Manages parallel simulation across currency pairs with state chaining
across dates within each pair.
"""

import gc
import logging
import os
import tempfile
import threading
import traceback
from concurrent.futures import Future, ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from ...app.services.risk_metrics import RiskMetricsCalculator
from ...core.config.run_config import RunConfig, RunStatus, SimulationConfig
from ...core.data.run_models import RunSummary
from ...core.data.run_registry import (
    InvalidRunStateError,
    RunNotFoundError,
    RunRegistry,
)
from ...util.time import now_ms
from ..io.pnl_writer import StreamingPnLWriter, merge_pnl_files
from ..shard.shard_engine import ShardEngine
from ..shard.state import PnLAttributionRecord, ShardState

logger = logging.getLogger(__name__)

# Timeout for individual shard futures (5 minutes per pair)
FUTURE_TIMEOUT_SECONDS = 300

# Flag to track if Numba JIT warmup has been done
_numba_warmed_up = False


def _warmup_numba_jit() -> None:
    """Pre-warm Numba JIT compiled functions before spawning workers.

    This triggers JIT compilation in the main process, which:
    1. Validates the Numba code compiles without errors
    2. Populates Numba's on-disk cache for workers to use
    3. Identifies compilation issues early rather than in workers

    Called once before the first ProcessPoolExecutor is created.
    """
    global _numba_warmed_up
    if _numba_warmed_up:
        return

    try:
        import numpy as np
        from ..shard.fifo_matcher import (
            FIFO_SLICE_DTYPE,
            fifo_match_and_pnl_attributed,
            calculate_unrealized_pnl_by_slice,
        )

        logger.info("Warming up Numba JIT compiled functions...")

        # Create minimal dummy data for warmup
        empty_queue = np.array([], dtype=FIFO_SLICE_DTYPE)

        # Warmup the main matching function
        fifo_match_and_pnl_attributed(
            empty_queue,
            np.int8(1),  # side
            np.float64(100.0),  # qty
            np.float64(1.1),  # mid
            np.int64(1704110400000),  # timestamp
            "client",  # source_type
            "warmup_trade",  # trade_id
        )

        # Warmup the unrealized PnL function
        calculate_unrealized_pnl_by_slice(empty_queue, 1.1)

        _numba_warmed_up = True
        logger.info("Numba JIT warmup complete")

    except Exception as e:
        logger.warning(f"Numba JIT warmup failed (non-fatal): {e}")
        _numba_warmed_up = True  # Don't retry on failure


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

    Memory optimization: Uses StreamingPnLWriter to write records to
    a temp file instead of accumulating in memory, reducing peak memory
    usage from O(total_records) to O(buffer_size).

    Args:
        pair: Currency pair (e.g., "EURUSD")
        shards: List of {date, file_path} dicts, sorted by date
        config: Simulation configuration
        data_root: Data root directory path

    Returns:
        Dict with pair results (serializable for process pool)
    """
    from ...core.data.schemas import DecrossedTradeRecord

    prior_state: ShardState | None = None
    prior_pending_hedges: list[tuple[int, dict, dict]] | None = None  # (execute_at, hedge, snapshot_dict)
    aggregated_metrics: dict[str, float] = {
        "execution_pnl_reporting": 0.0,
        "inventory_pnl_reporting": 0.0,
        "hedge_pnl_reporting": 0.0,
        "total_client_volume": 0.0,
        "internalized_volume": 0.0,
        "externalized_volume": 0.0,
    }
    shard_results = []

    # Create temp file path for streaming PnL writes
    temp_dir = Path(tempfile.gettempdir())
    pnl_temp_file = temp_dir / f"_pnl_{pair}_{uuid4().hex}.parquet"

    try:
        # Use streaming writer to avoid accumulating all records in memory
        with StreamingPnLWriter(pnl_temp_file, buffer_size=10000) as writer:
            for shard_info in shards:
                # Load trades (batch construct without per-row validation)
                table = pq.read_table(shard_info["file_path"])
                client_trades = DecrossedTradeRecord.batch_from_table(table)

                # Create engine
                engine = ShardEngine(
                    pair=pair,
                    date=shard_info["date"],
                    config=config,
                    data_root=Path(data_root),
                )

                # Run with state chaining (includes pending hedges from prior day)
                result = engine.run(
                    client_trades,
                    prior_state,
                    prior_pending_hedges=prior_pending_hedges,
                )

                # Stream PnL records to disk instead of accumulating
                writer.write_records(result.pnl_records)

                # Aggregate metrics
                for key in aggregated_metrics:
                    aggregated_metrics[key] += result.metrics.get(key, 0.0)

                shard_results.append({
                    "pair": pair,
                    "date": shard_info["date"],
                    **result.metrics,
                })

                # Chain state and pending hedges to next day
                prior_state = result.final_state
                prior_pending_hedges = result.pending_hedges

                # Explicit cleanup to release memory between shards
                del client_trades
                del result
                gc.collect()

        return {
            "pair": pair,
            "shard_count": len(shards),
            "pnl_temp_file": str(pnl_temp_file),  # Return path, not records
            "metrics": aggregated_metrics,
            "shard_results": shard_results,
            "error": None,
        }

    except Exception as e:
        logger.exception(f"Error executing shards for {pair}")
        # Cleanup temp file on error
        if pnl_temp_file.exists():
            pnl_temp_file.unlink(missing_ok=True)
        return {
            "pair": pair,
            "shard_count": len(shards),
            "pnl_temp_file": None,
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
        max_workers: int | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            registry: Run registry for persistence
            data_root: Root directory for market/trade data
            max_workers: Maximum parallel workers (one per pair).
                        If None, uses min(cpu_count, 16) for optimal parallelism.
        """
        self.registry = registry
        self.data_root = Path(data_root)
        # Dynamic worker count based on CPU cores (capped at 16 to avoid memory issues)
        self.max_workers = max_workers or min(os.cpu_count() or 4, 16)

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

        if run.status not in (RunStatus.CREATED, RunStatus.RUNNING):
            raise InvalidRunStateError(
                run_id, run.status, "Can only start runs in CREATED or RUNNING status"
            )

        # Discover shards and group by pair
        shards = self._discover_shards(decrossed_data_dir)

        if not shards:
            # No shards to simulate - mark as completed immediately
            current_time_ms = now_ms()
            self.registry.update_status(
                run_id,
                RunStatus.COMPLETED,
                started_at_ms=current_time_ms,
                completed_at_ms=current_time_ms,
            )
            self._write_empty_results(run_id)
            return

        shards_by_pair = self._group_by_pair(shards)

        # Update status to running with shard count
        self.registry.update_status(
            run_id,
            RunStatus.RUNNING,
            started_at_ms=now_ms(),
        )
        self.registry.update_progress(run_id, total_shards=len(shards))
        self.registry.update_stage(run_id, "simulating")

        # Create cancellation event
        cancel_event = threading.Event()

        # Build simulation config
        sim_config = run.config.simulation_config
        if sim_config is None:
            sim_config = SimulationConfig(dataset=run.config.dataset)

        # Pre-warm Numba JIT functions before spawning workers
        _warmup_numba_jit()

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
            daemon=False,  # Must complete before process exits to update status
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
        logger.info(f"[MONITOR] Starting _monitor_completion for run {run_id}")
        print(f"[MONITOR] Starting _monitor_completion for run {run_id}", flush=True)

        all_results: list[dict] = []
        failed_pairs: list[dict] = []
        completed_shards = 0

        logger.info(f"[MONITOR] Waiting for {len(futures)} futures to complete")
        print(f"[MONITOR] Waiting for {len(futures)} futures to complete", flush=True)

        for pair, future in futures:
            try:
                result = future.result(timeout=FUTURE_TIMEOUT_SECONDS)
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

            except FuturesTimeoutError:
                logger.error(f"Timeout waiting for {pair} after {FUTURE_TIMEOUT_SECONDS}s")
                failed_pairs.append({
                    "pair": pair,
                    "error": f"Timeout after {FUTURE_TIMEOUT_SECONDS} seconds",
                })

            except BrokenProcessPool as e:
                logger.error(
                    f"Worker process crashed for {pair}. This usually indicates "
                    "memory exhaustion or a segmentation fault in the worker. "
                    f"Error: {e}"
                )
                failed_pairs.append({
                    "pair": pair,
                    "error": f"Worker process crashed: {e}",
                })

            except Exception as e:
                logger.exception(f"Error getting result for {pair}")
                failed_pairs.append({
                    "pair": pair,
                    "error": str(e),
                })

        logger.info(f"[MONITOR] All futures completed. Results: {len(all_results)}, Failed: {len(failed_pairs)}")
        print(f"[MONITOR] All futures completed. Results: {len(all_results)}, Failed: {len(failed_pairs)}", flush=True)

        # Shutdown executor with cancel_futures to terminate any pending work
        # after failures or timeouts
        try:
            executor.shutdown(wait=True, cancel_futures=bool(failed_pairs))
        except TypeError:
            # Python < 3.9 doesn't support cancel_futures
            executor.shutdown(wait=True)

        logger.info(f"[MONITOR] Executor shutdown complete for run {run_id}")
        print(f"[MONITOR] Executor shutdown complete for run {run_id}", flush=True)

        # Determine final status
        try:
            run = self.registry.get_run(run_id)
            logger.info(f"[MONITOR] Current run status: {run.status}")
            print(f"[MONITOR] Current run status: {run.status}", flush=True)

            # Check if cancelled
            if run.status == RunStatus.CANCELLED:
                self._cleanup_active_run(run_id)
                return

            # Aggregate results and write - track success separately
            write_succeeded = False
            write_error_message = None
            try:
                logger.info(f"[MONITOR] Writing final results for run {run_id}")
                print(f"[MONITOR] Writing final results for run {run_id}", flush=True)
                self._write_final_results(run_id, all_results)
                write_succeeded = True
                logger.info(f"[MONITOR] Successfully wrote final results for run {run_id}")
                print(f"[MONITOR] Successfully wrote final results for run {run_id}", flush=True)
            except Exception as write_error:
                logger.exception(f"Failed to write results for run {run_id}")
                write_error_message = str(write_error)

            # Status update happens regardless of write success
            completed_at_ms = now_ms()
            logger.info(f"[MONITOR] About to update status. failed_pairs={len(failed_pairs)}, write_succeeded={write_succeeded}")
            print(f"[MONITOR] About to update status. failed_pairs={len(failed_pairs)}, write_succeeded={write_succeeded}", flush=True)

            if failed_pairs:
                logger.info(f"[MONITOR] Setting status to FAILED (pairs failed)")
                print(f"[MONITOR] Setting status to FAILED (pairs failed)", flush=True)
                self.registry.update_status(
                    run_id,
                    RunStatus.FAILED,
                    completed_at_ms=completed_at_ms,
                    error_message=f"{len(failed_pairs)} pair(s) failed",
                )
            elif not write_succeeded:
                logger.info(f"[MONITOR] Setting status to FAILED (write failed)")
                print(f"[MONITOR] Setting status to FAILED (write failed)", flush=True)
                self.registry.update_status(
                    run_id,
                    RunStatus.FAILED,
                    completed_at_ms=completed_at_ms,
                    error_message=f"Results write failed: {write_error_message}",
                )
            else:
                logger.info(f"[MONITOR] Setting status to COMPLETED")
                print(f"[MONITOR] Setting status to COMPLETED", flush=True)
                self.registry.update_status(
                    run_id,
                    RunStatus.COMPLETED,
                    completed_at_ms=completed_at_ms,
                )
            logger.info(f"[MONITOR] Status update complete for run {run_id}")
            print(f"[MONITOR] Status update complete for run {run_id}", flush=True)

        except Exception as e:
            logger.exception(f"[MONITOR] Error finalizing run {run_id}: {e}")
            print(f"[MONITOR] Error finalizing run {run_id}: {e}", flush=True)
            try:
                self.registry.update_status(
                    run_id,
                    RunStatus.FAILED,
                    completed_at_ms=now_ms(),
                    error_message=f"Finalization error: {e}",
                )
            except Exception as inner_e:
                logger.exception(f"[MONITOR] Failed to update status after error: {inner_e}")
                print(f"[MONITOR] Failed to update status after error: {inner_e}", flush=True)

        finally:
            logger.info(f"[MONITOR] Cleaning up run {run_id}")
            print(f"[MONITOR] Cleaning up run {run_id}", flush=True)
            self._cleanup_active_run(run_id)
            logger.info(f"[MONITOR] _monitor_completion finished for run {run_id}")
            print(f"[MONITOR] _monitor_completion finished for run {run_id}", flush=True)

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

        Memory optimization: Merges per-pair temp files using DuckDB
        instead of accumulating all records in memory.

        Args:
            run_id: Run identifier
            all_results: List of pair result dicts
        """
        print(f"[WRITE] _write_final_results started for {run_id}", flush=True)
        run_dir = self.registry.get_run_dir(run_id)

        # Collect temp file paths from pair results
        temp_files = [
            Path(r["pnl_temp_file"])
            for r in all_results
            if r.get("pnl_temp_file") and Path(r["pnl_temp_file"]).exists()
        ]
        print(f"[WRITE] Found {len(temp_files)} temp files to merge", flush=True)

        # Merge temp files using memory-efficient DuckDB merge
        final_pnl_path = run_dir / "pnl_attribution.parquet"
        print(f"[WRITE] Merging PnL files...", flush=True)
        merge_pnl_files(temp_files, final_pnl_path)
        print(f"[WRITE] PnL files merged", flush=True)

        # Cleanup temp files
        for temp_file in temp_files:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

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

        total_pnl = total_exec_pnl + total_inv_pnl + total_hedge_pnl

        summary = RunSummary(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            pairs=sorted(pairs),
            date_range=date_range,
            total_shards=sum(r.get("shard_count", 0) for r in all_results),
            total_execution_pnl=total_exec_pnl,
            total_inventory_pnl=total_inv_pnl,
            total_hedge_pnl=total_hedge_pnl,
            total_pnl=total_pnl,
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

        # Phase 5: Calculate and attach risk metrics
        print(f"[WRITE] Calculating risk metrics...", flush=True)
        self.registry.update_stage(run_id, "computing_metrics")
        try:
            pnl_path = run_dir / "pnl_attribution.parquet"
            calculator = RiskMetricsCalculator()

            # Get simulation config for risk band threshold
            run = self.registry.get_run(run_id)
            sim_config = run.config.simulation_config

            # Get direct pairs from general config (default to EURUSD, GBPUSD)
            direct_pairs = ["EURUSD", "GBPUSD"]
            if run.config.general_config:
                direct_pairs = run.config.general_config.direct_pairs

            risk, ops, internalization = calculator.calculate_all(
                pnl_path=pnl_path,
                config=sim_config,
                client_volume=total_client_volume,
                total_pnl=total_pnl,
                direct_pairs=direct_pairs,
            )
            frontier = calculator.compute_frontier_scores(summary, risk)

            summary.risk_metrics = risk
            summary.ops_metrics = ops
            summary.internalization_metrics = internalization
            summary.frontier_scores = frontier

            print(f"[WRITE] Risk metrics computed", flush=True)
        except Exception as e:
            print(f"[WRITE] Risk metrics failed (optional): {e}", flush=True)
            # Continue without risk metrics - they're optional

        print(f"[WRITE] Writing summary to registry...", flush=True)
        self.registry.update_stage(run_id, "writing_results")
        self.registry.write_summary(run_id, summary)
        print(f"[WRITE] Summary written successfully", flush=True)

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
