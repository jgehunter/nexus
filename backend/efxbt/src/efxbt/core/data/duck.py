"""DuckDB connection and query utilities.

Provides connection management and common query patterns for DuckDB.
All heavy data operations should go through DuckDB for performance.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb


@contextmanager
def get_connection(
    database: str | Path = ":memory:",
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager for DuckDB connections.

    Args:
        database: Path to database file or ":memory:" for in-memory
        read_only: If True, open in read-only mode

    Yields:
        DuckDB connection

    Example:
        with get_connection() as conn:
            result = conn.execute("SELECT 1").fetchone()
    """
    conn = duckdb.connect(str(database), read_only=read_only)
    try:
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
