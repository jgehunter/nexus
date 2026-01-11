"""Run cleanup utilities for storage hygiene.

Provides functions for cleaning up old runs based on retention policies.
"""

import logging
from datetime import datetime, timedelta

from ..core.config.run_config import RunStatus
from ..core.data.run_registry import RunNotFoundError, RunRegistry

logger = logging.getLogger(__name__)


def cleanup_old_runs(
    registry: RunRegistry,
    retention_days: int = 30,
    max_runs: int = 100,
    dry_run: bool = False,
) -> dict[str, int]:
    """Clean up old runs based on retention policy.

    Deletes runs that are:
    1. Older than retention_days (if > 0)
    2. Beyond the max_runs limit (oldest first)

    Only deletes runs in terminal states (COMPLETED, FAILED, CANCELLED).
    Never deletes RUNNING or CREATED runs.

    Args:
        registry: Run registry instance
        retention_days: Days to retain completed runs (0 = forever)
        max_runs: Maximum runs to keep (0 = unlimited)
        dry_run: If True, don't actually delete, just report

    Returns:
        Dict with cleanup statistics:
        - deleted_by_age: Runs deleted due to age
        - deleted_by_count: Runs deleted due to count limit
        - skipped_active: Runs skipped (not in terminal state)
        - errors: Runs that failed to delete
    """
    stats = {
        "deleted_by_age": 0,
        "deleted_by_count": 0,
        "skipped_active": 0,
        "errors": 0,
    }

    terminal_states = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    # Get all runs
    all_runs = registry.list_runs(limit=10000)  # High limit to get all

    # Separate terminal and active runs
    terminal_runs = [r for r in all_runs if r.status in terminal_states]
    stats["skipped_active"] = len(all_runs) - len(terminal_runs)

    # Sort by creation date (oldest first)
    terminal_runs.sort(key=lambda r: r.created_at_ms)

    # Calculate age cutoff in milliseconds
    cutoff_ms = (
        int((datetime.utcnow() - timedelta(days=retention_days)).timestamp() * 1000)
        if retention_days > 0
        else None
    )

    to_delete = set()

    # Mark runs for deletion by age
    if cutoff_ms:
        for run in terminal_runs:
            if run.created_at_ms < cutoff_ms:
                to_delete.add(run.run_id)
                stats["deleted_by_age"] += 1

    # Mark runs for deletion by count (after age-based deletion)
    if max_runs > 0:
        remaining = [r for r in terminal_runs if r.run_id not in to_delete]
        if len(remaining) > max_runs:
            # Delete oldest runs beyond limit
            excess = remaining[:-max_runs]  # Keep newest max_runs
            for run in excess:
                to_delete.add(run.run_id)
                stats["deleted_by_count"] += 1

    # Perform deletion
    for run_id in to_delete:
        if dry_run:
            logger.info(f"[DRY RUN] Would delete run: {run_id}")
        else:
            try:
                registry.delete_run(run_id)
                logger.info(f"Deleted run: {run_id}")
            except RunNotFoundError:
                # Already deleted
                pass
            except Exception as e:
                logger.error(f"Failed to delete run {run_id}: {e}")
                stats["errors"] += 1

    if dry_run:
        logger.info(
            f"[DRY RUN] Would delete {stats['deleted_by_age']} by age, "
            f"{stats['deleted_by_count']} by count"
        )
    else:
        logger.info(
            f"Cleanup complete: {stats['deleted_by_age']} deleted by age, "
            f"{stats['deleted_by_count']} deleted by count, "
            f"{stats['skipped_active']} active skipped, "
            f"{stats['errors']} errors"
        )

    return stats


def get_storage_stats(registry: RunRegistry) -> dict:
    """Get storage statistics for runs.

    Args:
        registry: Run registry instance

    Returns:
        Dict with storage statistics
    """
    import os

    all_runs = registry.list_runs(limit=10000)

    total_size = 0
    runs_by_status = {}

    for run in all_runs:
        status = run.status.value
        runs_by_status[status] = runs_by_status.get(status, 0) + 1

        # Calculate run directory size
        run_dir = registry.get_run_dir(run.run_id)
        if run_dir.exists():
            for path in run_dir.rglob("*"):
                if path.is_file():
                    try:
                        total_size += path.stat().st_size
                    except OSError:
                        pass

    return {
        "total_runs": len(all_runs),
        "runs_by_status": runs_by_status,
        "total_size_bytes": total_size,
        "total_size_mb": total_size / (1024 * 1024),
    }
