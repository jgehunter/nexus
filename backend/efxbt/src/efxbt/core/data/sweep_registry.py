"""Sweep registry for discovering and managing sweep records.

Provides persistent storage of sweep metadata using JSON files,
with support for tracking member runs and progress.
"""

import hashlib
import json
import logging
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from ..config.sweep_config import SweepConfig, SweepStatus
from .sweep_models import SweepRecord
from ...util.time import now_ms


class SweepNotFoundError(Exception):
    """Raised when a sweep is not found."""

    def __init__(self, sweep_id: str) -> None:
        self.sweep_id = sweep_id
        super().__init__(f"Sweep not found: {sweep_id}")


class InvalidSweepStateError(Exception):
    """Raised when an operation is invalid for the current sweep state."""

    def __init__(self, sweep_id: str, current_status: SweepStatus, message: str) -> None:
        self.sweep_id = sweep_id
        self.current_status = current_status
        super().__init__(f"Sweep {sweep_id} ({current_status.value}): {message}")


def compute_sweep_config_hash(config: SweepConfig) -> str:
    """Compute deterministic SHA-256 hash of sweep config.

    Args:
        config: Sweep configuration to hash

    Returns:
        16-character hex string (first 64 bits of SHA-256)
    """
    config_dict = config.model_dump(mode="json")
    config_json = json.dumps(config_dict, sort_keys=True, default=str)
    full_hash = hashlib.sha256(config_json.encode()).hexdigest()
    return full_hash[:16]


class SweepRegistry:
    """Registry for discovering and managing sweep records.

    Storage structure:
        results/sweeps/{sweep_id}/
            ├── sweep_config.json   # Immutable config snapshot
            └── sweep_status.json   # Mutable status/progress
    """

    CONFIG_FILENAME = "sweep_config.json"
    STATUS_FILENAME = "sweep_status.json"

    def __init__(self, results_root: Path) -> None:
        """Initialize sweep registry.

        Args:
            results_root: Root directory for results storage
        """
        self.results_root = Path(results_root)
        self.sweeps_dir = self.results_root / "sweeps"
        self.sweeps_dir.mkdir(parents=True, exist_ok=True)

    def generate_sweep_id(self) -> str:
        """Generate unique sweep ID.

        Format: sweep_{timestamp}_{random_suffix}
        Example: sweep_20240115_143022_a1b2c3d4

        Returns:
            Unique sweep identifier
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = secrets.token_hex(4)
        return f"sweep_{timestamp}_{suffix}"

    def get_sweep_dir(self, sweep_id: str) -> Path:
        """Get the directory path for a sweep.

        Args:
            sweep_id: Sweep identifier

        Returns:
            Path to sweep directory
        """
        return self.sweeps_dir / sweep_id

    def create_sweep(
        self,
        config: SweepConfig,
        sweep_id: str | None = None,
    ) -> SweepRecord:
        """Create new sweep record with config snapshot.

        Args:
            config: Sweep configuration
            sweep_id: Optional custom sweep ID (auto-generated if None)

        Returns:
            Created SweepRecord

        Raises:
            ValueError: If sweep_id already exists
        """
        if sweep_id is None:
            sweep_id = self.generate_sweep_id()

        sweep_dir = self.get_sweep_dir(sweep_id)
        if sweep_dir.exists():
            raise ValueError(f"Sweep already exists: {sweep_id}")

        sweep_dir.mkdir(parents=True)

        config_hash = compute_sweep_config_hash(config)
        current_time_ms = now_ms()
        total_configs = config.get_total_configs()

        record = SweepRecord(
            sweep_id=sweep_id,
            config_hash=config_hash,
            status=SweepStatus.PENDING,
            created_at_ms=current_time_ms,
            config=config,
            total_configs=total_configs,
            completed_configs=0,
            failed_configs=0,
            skipped_configs=0,
            current_run_id=None,
        )

        # Write immutable config
        config_file = sweep_dir / self.CONFIG_FILENAME
        config_file.write_text(config.model_dump_json(indent=2))

        # Write mutable status
        self._write_status(sweep_id, record)

        logger.info(f"Created sweep {sweep_id} with {total_configs} configurations")
        return record

    def get_sweep(self, sweep_id: str) -> SweepRecord:
        """Load sweep record by ID.

        Args:
            sweep_id: Sweep identifier

        Returns:
            SweepRecord

        Raises:
            SweepNotFoundError: If sweep doesn't exist
        """
        sweep_dir = self.get_sweep_dir(sweep_id)
        status_file = sweep_dir / self.STATUS_FILENAME
        config_file = sweep_dir / self.CONFIG_FILENAME

        if not sweep_dir.exists() or not status_file.exists():
            raise SweepNotFoundError(sweep_id)

        status_data = json.loads(status_file.read_text())
        config_data = json.loads(config_file.read_text())

        return SweepRecord(
            sweep_id=sweep_id,
            config_hash=status_data["config_hash"],
            status=SweepStatus(status_data["status"]),
            created_at_ms=status_data["created_at_ms"],
            started_at_ms=status_data.get("started_at_ms"),
            completed_at_ms=status_data.get("completed_at_ms"),
            config=SweepConfig(**config_data),
            member_run_ids=status_data.get("member_run_ids", []),
            total_configs=status_data.get("total_configs", 0),
            completed_configs=status_data.get("completed_configs", 0),
            failed_configs=status_data.get("failed_configs", 0),
            skipped_configs=status_data.get("skipped_configs", 0),
            current_run_id=status_data.get("current_run_id"),
            error_message=status_data.get("error_message"),
        )

    def update_status(
        self,
        sweep_id: str,
        status: SweepStatus,
        **kwargs: Any,
    ) -> SweepRecord:
        """Update sweep status and optional fields.

        Args:
            sweep_id: Sweep identifier
            status: New status
            **kwargs: Additional fields to update

        Returns:
            Updated SweepRecord

        Raises:
            SweepNotFoundError: If sweep doesn't exist
        """
        logger.info(f"[SWEEP_REGISTRY] update_status: sweep_id={sweep_id}, status={status.value}")

        record = self.get_sweep(sweep_id)
        record.status = status

        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)

        self._write_status(sweep_id, record)
        return record

    def update_progress(
        self,
        sweep_id: str,
        completed_configs: int | None = None,
        failed_configs: int | None = None,
        skipped_configs: int | None = None,
        current_run_id: str | None = None,
    ) -> SweepRecord:
        """Update sweep progress counters.

        Args:
            sweep_id: Sweep identifier
            completed_configs: Number of completed configs
            failed_configs: Number of failed configs
            skipped_configs: Number of skipped configs (idempotence)
            current_run_id: Currently executing run_id

        Returns:
            Updated SweepRecord
        """
        record = self.get_sweep(sweep_id)

        if completed_configs is not None:
            record.completed_configs = completed_configs
        if failed_configs is not None:
            record.failed_configs = failed_configs
        if skipped_configs is not None:
            record.skipped_configs = skipped_configs
        if current_run_id is not None:
            record.current_run_id = current_run_id

        self._write_status(sweep_id, record)
        return record

    def add_member_run(self, sweep_id: str, run_id: str) -> SweepRecord:
        """Add a run_id to the sweep's member runs.

        Args:
            sweep_id: Sweep identifier
            run_id: Run identifier to add

        Returns:
            Updated SweepRecord
        """
        record = self.get_sweep(sweep_id)

        if run_id not in record.member_run_ids:
            record.member_run_ids.append(run_id)
            self._write_status(sweep_id, record)
            logger.info(f"Added run {run_id} to sweep {sweep_id}")

        return record

    def list_sweeps(
        self,
        status: SweepStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SweepRecord]:
        """List sweeps with optional status filter.

        Args:
            status: Filter by status (None = all)
            limit: Maximum sweeps to return
            offset: Number of sweeps to skip

        Returns:
            List of SweepRecords, sorted by created_at descending
        """
        sweeps: list[SweepRecord] = []

        for sweep_dir in self.sweeps_dir.iterdir():
            if not sweep_dir.is_dir():
                continue

            try:
                record = self.get_sweep(sweep_dir.name)
                if status is None or record.status == status:
                    sweeps.append(record)
            except (SweepNotFoundError, json.JSONDecodeError):
                continue

        # Sort by created_at_ms descending (newest first)
        sweeps.sort(key=lambda s: s.created_at_ms, reverse=True)

        # Apply pagination
        return sweeps[offset : offset + limit]

    def count_sweeps(self, status: SweepStatus | None = None) -> int:
        """Count total sweeps with optional status filter.

        Args:
            status: Filter by status (None = all)

        Returns:
            Total count of sweeps
        """
        count = 0
        for sweep_dir in self.sweeps_dir.iterdir():
            if not sweep_dir.is_dir():
                continue

            try:
                record = self.get_sweep(sweep_dir.name)
                if status is None or record.status == status:
                    count += 1
            except (SweepNotFoundError, json.JSONDecodeError):
                continue

        return count

    def delete_sweep(self, sweep_id: str) -> None:
        """Delete sweep directory.

        Args:
            sweep_id: Sweep identifier

        Raises:
            SweepNotFoundError: If sweep doesn't exist
            InvalidSweepStateError: If sweep is currently running
        """
        record = self.get_sweep(sweep_id)

        if record.status == SweepStatus.RUNNING:
            raise InvalidSweepStateError(
                sweep_id, record.status, "Cannot delete running sweep"
            )

        sweep_dir = self.get_sweep_dir(sweep_id)
        shutil.rmtree(sweep_dir)
        logger.info(f"Deleted sweep {sweep_id}")

    def _write_status(self, sweep_id: str, record: SweepRecord) -> None:
        """Write status file atomically.

        Args:
            sweep_id: Sweep identifier
            record: Record to persist
        """
        sweep_dir = self.get_sweep_dir(sweep_id)
        status_file = sweep_dir / self.STATUS_FILENAME

        status_data = {
            "sweep_id": record.sweep_id,
            "config_hash": record.config_hash,
            "status": record.status.value,
            "created_at_ms": record.created_at_ms,
            "started_at_ms": record.started_at_ms,
            "completed_at_ms": record.completed_at_ms,
            "member_run_ids": record.member_run_ids,
            "total_configs": record.total_configs,
            "completed_configs": record.completed_configs,
            "failed_configs": record.failed_configs,
            "skipped_configs": record.skipped_configs,
            "current_run_id": record.current_run_id,
            "error_message": record.error_message,
        }

        # Write atomically via temp file
        temp_file = status_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(status_data, indent=2))
        temp_file.replace(status_file)
