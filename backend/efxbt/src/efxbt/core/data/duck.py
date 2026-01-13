"""DuckDB connection and query utilities.

Provides connection management and common query patterns for DuckDB.
All heavy data operations should go through DuckDB for performance.
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

# Default memory limit for DuckDB queries (4GB for better performance, configurable via env var)
DEFAULT_MEMORY_LIMIT = os.environ.get("EFXBT_DUCKDB_MEMORY_LIMIT", "4GB")


@contextmanager
def get_connection(
    database: str | Path = ":memory:",
    read_only: bool = False,
    memory_limit: str | None = None,
    temp_directory: Path | None = None,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager for DuckDB connections with memory configuration.

    Args:
        database: Path to database file or ":memory:" for in-memory
        read_only: If True, open in read-only mode
        memory_limit: Optional memory limit (e.g., "256MB", "1GB").
                     If None, uses system default (no limit).
        temp_directory: Optional temp directory for spill-to-disk.
                       If None, uses system temp directory.

    Yields:
        DuckDB connection

    Example:
        with get_connection(memory_limit="512MB") as conn:
            result = conn.execute("SELECT 1").fetchone()

    Note:
        When memory_limit is set, DuckDB will spill to disk when the limit
        is exceeded, preventing out-of-memory crashes for large queries.
    """
    conn = duckdb.connect(str(database), read_only=read_only)
    try:
        # Configure memory limit if specified
        if memory_limit:
            conn.execute(f"SET memory_limit = '{memory_limit}'")

        # Configure temp directory for spill-to-disk
        # Use per-process directories to avoid race conditions between workers
        if temp_directory:
            temp_dir = Path(temp_directory) / str(os.getpid())
            temp_dir.mkdir(parents=True, exist_ok=True)
            conn.execute(f"SET temp_directory = '{temp_dir}'")
        elif memory_limit:
            # If memory limit is set but no temp dir specified,
            # use system temp to enable spilling (per-process to avoid conflicts)
            temp_dir = Path(tempfile.gettempdir()) / "duckdb_spill" / str(os.getpid())
            temp_dir.mkdir(parents=True, exist_ok=True)
            conn.execute(f"SET temp_directory = '{temp_dir}'")

        yield conn
    finally:
        conn.close()


def check_duckdb_health() -> bool:
    """Verify DuckDB is operational.

    Returns:
        True if DuckDB can execute a simple query, False otherwise
    """
    try:
        with get_connection() as conn:
            result = conn.execute("SELECT 1 AS health_check").fetchone()
            return result is not None and result[0] == 1
    except Exception:
        return False


def get_duckdb_version() -> str:
    """Get DuckDB version string.

    Returns:
        DuckDB version or "unknown" on error
    """
    try:
        with get_connection() as conn:
            result = conn.execute("SELECT version()").fetchone()
            return result[0] if result else "unknown"
    except Exception:
        return "unknown"


def register_parquet_files(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    parquet_paths: list[Path],
) -> None:
    """Register parquet files as a virtual table.

    Args:
        conn: DuckDB connection
        table_name: Name for the virtual table
        parquet_paths: List of parquet file paths to include
    """
    if not parquet_paths:
        raise ValueError("No parquet files provided")

    paths_str = ", ".join(f"'{p}'" for p in parquet_paths)
    conn.execute(f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_parquet([{paths_str}])")
