"""Run registry for discovering and managing run records.

Provides persistent storage of run metadata using JSON files,
with support for idempotence detection via config hashing.
"""

import hashlib
import json
import logging
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

from ..config.run_config import RunConfig, RunStatus
from .run_models import DecrossProgress, FailedShardDetail, RunRecord
from ...util.time import now_ms


class RunNotFoundError(Exception):
    """Raised when a run is not found."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class DuplicateRunError(Exception):
    """Raised when a duplicate run config is detected."""

    def __init__(self, existing_run_id: str, config_hash: str) -> None:
        self.existing_run_id = existing_run_id
        self.config_hash = config_hash
        super().__init__(
            f"Duplicate config detected. Existing run: {existing_run_id}"
        )


class InvalidRunStateError(Exception):
    """Raised when an operation is invalid for the current run state."""

    def __init__(self, run_id: str, current_status: RunStatus, message: str) -> None:
        self.run_id = run_id
        self.current_status = current_status
        super().__init__(f"Run {run_id} ({current_status}): {message}")


def compute_config_hash(config: RunConfig) -> str:
    """Compute deterministic SHA-256 hash of run config.

    Args:
        config: Run configuration to hash

    Returns:
        16-character hex string (first 64 bits of SHA-256)
    """
    # Use model_dump with sorted keys for deterministic serialization
    config_dict = config.model_dump(mode="json")
    config_json = json.dumps(config_dict, sort_keys=True, default=str)
    full_hash = hashlib.sha256(config_json.encode()).hexdigest()
    return full_hash[:16]


class RunRegistry:
    """Registry for discovering and managing run records.

    Storage structure:
        results/runs/{run_id}/
            ├── run_config.json      # Immutable config snapshot
            ├── run_status.json      # Mutable status/progress
            ├── pnl_attribution.parquet
            ├── summary_metrics.json
            └── timeseries.parquet
    """

    CONFIG_FILENAME = "run_config.json"
    STATUS_FILENAME = "run_status.json"
    SUMMARY_FILENAME = "summary_metrics.json"

    def __init__(self, results_root: Path) -> None:
        """Initialize run registry.

        Args:
            results_root: Root directory for results storage
        """
        self.results_root = Path(results_root)
        self.runs_dir = self.results_root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def generate_run_id(self) -> str:
        """Generate unique run ID.

        Format: run_{timestamp}_{random_suffix}
        Example: run_20240115_143022_a1b2c3d4

        Returns:
            Unique run identifier
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = secrets.token_hex(4)
        return f"run_{timestamp}_{suffix}"

    def get_run_dir(self, run_id: str) -> Path:
        """Get the directory path for a run.

        Args:
            run_id: Run identifier

        Returns:
            Path to run directory
        """
        return self.runs_dir / run_id

    def find_existing_run(self, config_hash: str) -> RunRecord | None:
        """Find existing run with same config hash.

        Args:
            config_hash: Hash of config to search for

        Returns:
            RunRecord if found, None otherwise
        """
        for run_dir in self.runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            status_file = run_dir / self.STATUS_FILENAME
            if not status_file.exists():
                continue

            try:
                status_data = json.loads(status_file.read_text())
                if status_data.get("config_hash") == config_hash:
                    return self.get_run(run_dir.name)
            except (json.JSONDecodeError, KeyError):
                continue

        return None

    def create_run(self, config: RunConfig, run_id: str | None = None) -> RunRecord:
        """Create new run record with config snapshot.

        Args:
            config: Run configuration
            run_id: Optional custom run ID (auto-generated if None)

        Returns:
            Created RunRecord

        Raises:
            ValueError: If run_id already exists
        """
        if run_id is None:
            run_id = self.generate_run_id()

        run_dir = self.get_run_dir(run_id)
        if run_dir.exists():
            raise ValueError(f"Run already exists: {run_id}")

        run_dir.mkdir(parents=True)

        config_hash = compute_config_hash(config)
        current_time_ms = now_ms()

        record = RunRecord(
            run_id=run_id,
            config_hash=config_hash,
            status=RunStatus.CREATED,
            created_at_ms=current_time_ms,
            config=config,
        )

        # Write immutable config
        config_file = run_dir / self.CONFIG_FILENAME
        config_file.write_text(config.model_dump_json(indent=2))

        # Write mutable status
        self._write_status(run_id, record)

        return record

    def create_run_with_idempotence(
        self,
        config: RunConfig,
        behavior: str = "error",
    ) -> tuple[RunRecord, bool]:
        """Create run with idempotence check.

        Args:
            config: Run configuration
            behavior: What to do if duplicate found:
                - "error": Raise DuplicateRunError
                - "reuse": Return existing run
                - "new": Create new run anyway

        Returns:
            Tuple of (run_record, is_new)

        Raises:
            DuplicateRunError: If behavior="error" and duplicate found
            ValueError: If behavior is invalid
        """
        if behavior not in ("error", "reuse", "new"):
            raise ValueError(f"Invalid idempotence behavior: {behavior}")

        config_hash = compute_config_hash(config)
        existing = self.find_existing_run(config_hash)

        if existing:
            if behavior == "error":
                raise DuplicateRunError(existing.run_id, config_hash)
            elif behavior == "reuse":
                return existing, False

        # Create new run
        return self.create_run(config), True

    def get_run(self, run_id: str) -> RunRecord:
        """Load run record by ID.

        Args:
            run_id: Run identifier

        Returns:
            RunRecord

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        run_dir = self.get_run_dir(run_id)
        status_file = run_dir / self.STATUS_FILENAME
        config_file = run_dir / self.CONFIG_FILENAME

        if not run_dir.exists() or not status_file.exists():
            raise RunNotFoundError(run_id)

        status_data = json.loads(status_file.read_text())
        config_data = json.loads(config_file.read_text())

        # Parse failed_shard_details
        failed_details = [
            FailedShardDetail(**d) for d in status_data.get("failed_shard_details", [])
        ]

        # Parse decross_progress (with backward compatibility)
        decross_data = status_data.get("decross_progress", {})
        decross_progress = DecrossProgress(
            status=decross_data.get("status", "pending"),
            total_dates=decross_data.get("total_dates", 0),
            completed_dates=decross_data.get("completed_dates", 0),
            current_date=decross_data.get("current_date"),
            started_at_ms=decross_data.get("started_at_ms"),
            completed_at_ms=decross_data.get("completed_at_ms"),
            error=decross_data.get("error"),
        )

        return RunRecord(
            run_id=run_id,
            config_hash=status_data["config_hash"],
            status=RunStatus(status_data["status"]),
            created_at_ms=status_data["created_at_ms"],
            started_at_ms=status_data.get("started_at_ms"),
            completed_at_ms=status_data.get("completed_at_ms"),
            decross_progress=decross_progress,
            total_shards=status_data.get("total_shards", 0),
            completed_shards=status_data.get("completed_shards", 0),
            failed_shards=status_data.get("failed_shards", 0),
            current_stage=status_data.get("current_stage"),
            error_message=status_data.get("error_message"),
            failed_shard_details=failed_details,
            config=RunConfig(**config_data),
        )

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        **kwargs: Any,
    ) -> RunRecord:
        """Update run status and optional fields.

        Args:
            run_id: Run identifier
            status: New status
            **kwargs: Additional fields to update (started_at, completed_at,
                     error_message, failed_shard_details)

        Returns:
            Updated RunRecord

        Raises:
            RunNotFoundError: If run doesn't exist
        """
        logger.info(f"[REGISTRY] update_status called: run_id={run_id}, status={status.value}")
        print(f"[REGISTRY] update_status called: run_id={run_id}, status={status.value}", flush=True)

        record = self.get_run(run_id)
        record.status = status

        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)

        self._write_status(run_id, record)
        logger.info(f"[REGISTRY] Status written successfully for run {run_id}")
        print(f"[REGISTRY] Status written successfully for run {run_id}", flush=True)
        return record

    def update_progress(
        self,
        run_id: str,
        completed_shards: int | None = None,
        failed_shards: int | None = None,
        total_shards: int | None = None,
    ) -> RunRecord:
        """Update shard progress counters.

        Args:
            run_id: Run identifier
            completed_shards: Number of completed shards
            failed_shards: Number of failed shards
            total_shards: Total number of shards

        Returns:
            Updated RunRecord
        """
        record = self.get_run(run_id)

        if completed_shards is not None:
            record.completed_shards = completed_shards
        if failed_shards is not None:
            record.failed_shards = failed_shards
        if total_shards is not None:
            record.total_shards = total_shards

        self._write_status(run_id, record)
        return record

    def update_stage(self, run_id: str, stage: str) -> RunRecord:
        """Update the current stage of the run.

        Args:
            run_id: Run identifier
            stage: Current stage (decrossing, simulating, computing_metrics, writing_results)

        Returns:
            Updated RunRecord
        """
        record = self.get_run(run_id)
        record.current_stage = stage
        self._write_status(run_id, record)
        return record

    def add_failed_shard(
        self,
        run_id: str,
        pair: str,
        date: str,
        error: str,
        traceback: str | None = None,
    ) -> RunRecord:
        """Add a failed shard detail.

        Args:
            run_id: Run identifier
            pair: Currency pair
            date: Date string
            error: Error message
            traceback: Optional traceback

        Returns:
            Updated RunRecord
        """
        record = self.get_run(run_id)
        record.failed_shard_details.append(
            FailedShardDetail(pair=pair, date=date, error=error, traceback=traceback)
        )
        record.failed_shards = len(record.failed_shard_details)

        self._write_status(run_id, record)
        return record

    def list_runs(
        self,
        status: RunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunRecord]:
        """List runs with optional status filter.

        Args:
            status: Filter by status (None = all)
            limit: Maximum runs to return
            offset: Number of runs to skip

        Returns:
            List of RunRecords, sorted by created_at descending
        """
        runs: list[RunRecord] = []

        for run_dir in self.runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            try:
                record = self.get_run(run_dir.name)
                if status is None or record.status == status:
                    runs.append(record)
            except (RunNotFoundError, json.JSONDecodeError):
                continue

        # Sort by created_at_ms descending (newest first)
        runs.sort(key=lambda r: r.created_at_ms, reverse=True)

        # Apply pagination
        return runs[offset : offset + limit]

    def delete_run(self, run_id: str) -> None:
        """Delete run directory and all results.

        Args:
            run_id: Run identifier

        Raises:
            RunNotFoundError: If run doesn't exist
            InvalidRunStateError: If run is currently running
        """
        record = self.get_run(run_id)

        if record.status == RunStatus.RUNNING:
            raise InvalidRunStateError(
                run_id, record.status, "Cannot delete running run"
            )

        run_dir = self.get_run_dir(run_id)
        shutil.rmtree(run_dir)

    def write_summary(self, run_id: str, summary: BaseModel) -> None:
        """Write summary metrics to JSON.

        Args:
            run_id: Run identifier
            summary: Summary model to persist
        """
        run_dir = self.get_run_dir(run_id)
        summary_file = run_dir / self.SUMMARY_FILENAME
        summary_file.write_text(summary.model_dump_json(indent=2))

    def read_summary(self, run_id: str) -> dict[str, Any]:
        """Read summary metrics from JSON.

        Args:
            run_id: Run identifier

        Returns:
            Summary dict

        Raises:
            FileNotFoundError: If summary file doesn't exist
        """
        run_dir = self.get_run_dir(run_id)
        summary_file = run_dir / self.SUMMARY_FILENAME

        if not summary_file.exists():
            raise FileNotFoundError(f"Summary not found for run: {run_id}")

        return json.loads(summary_file.read_text())

    def _write_status(self, run_id: str, record: RunRecord) -> None:
        """Write status file atomically.

        Args:
            run_id: Run identifier
            record: Record to persist
        """
        run_dir = self.get_run_dir(run_id)
        status_file = run_dir / self.STATUS_FILENAME

        status_data = {
            "run_id": record.run_id,
            "config_hash": record.config_hash,
            "status": record.status.value,
            "created_at_ms": record.created_at_ms,
            "started_at_ms": record.started_at_ms,
            "completed_at_ms": record.completed_at_ms,
            "decross_progress": {
                "status": record.decross_progress.status,
                "total_dates": record.decross_progress.total_dates,
                "completed_dates": record.decross_progress.completed_dates,
                "current_date": record.decross_progress.current_date,
                "started_at_ms": record.decross_progress.started_at_ms,
                "completed_at_ms": record.decross_progress.completed_at_ms,
                "error": record.decross_progress.error,
            },
            "total_shards": record.total_shards,
            "completed_shards": record.completed_shards,
            "failed_shards": record.failed_shards,
            "current_stage": record.current_stage,
            "error_message": record.error_message,
            "failed_shard_details": [
                d.model_dump() for d in record.failed_shard_details
            ],
        }

        # Write atomically via temp file
        temp_file = status_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(status_data, indent=2))
        temp_file.replace(status_file)

    def update_decross_progress(
        self,
        run_id: str,
        completed_dates: int,
        total_dates: int,
        current_date: str | None = None,
    ) -> RunRecord:
        """Update decrossing progress.

        Args:
            run_id: Run identifier
            completed_dates: Number of dates completed
            total_dates: Total number of dates to process
            current_date: Currently processing date

        Returns:
            Updated RunRecord
        """
        record = self.get_run(run_id)

        record.decross_progress.completed_dates = completed_dates
        record.decross_progress.total_dates = total_dates
        record.decross_progress.current_date = current_date

        # Set status to running if not already
        if record.decross_progress.status == "pending":
            record.decross_progress.status = "running"
            record.decross_progress.started_at_ms = now_ms()

        self._write_status(run_id, record)
        return record

    def complete_decrossing(
        self,
        run_id: str,
        success: bool = True,
        error: str | None = None,
    ) -> RunRecord:
        """Mark decrossing as complete.

        Args:
            run_id: Run identifier
            success: Whether decrossing succeeded
            error: Optional error message if failed

        Returns:
            Updated RunRecord
        """
        record = self.get_run(run_id)

        record.decross_progress.status = "completed" if success else "failed"
        record.decross_progress.completed_at_ms = now_ms()
        record.decross_progress.current_date = None

        if error:
            record.decross_progress.error = error

        self._write_status(run_id, record)
        return record
