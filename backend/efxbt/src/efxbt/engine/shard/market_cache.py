"""Process-local market data cache with DuckDB connection reuse.

Eliminates per-shard connection overhead by maintaining a persistent DuckDB
connection within each worker process and caching registered market data tables.
"""

import logging
import os
from pathlib import Path
from typing import ClassVar

import duckdb

logger = logging.getLogger(__name__)


class MarketDataCache:
    """Process-local singleton for DuckDB connection and market data caching.

    Key optimizations:
    1. Single DuckDB connection per process (reused across shards)
    2. Market data tables registered once per pair (not per shard)
    3. FX conversion tables cached similarly

    This eliminates the main DuckDB bottleneck: creating 300+ connections
    for a typical multi-day, multi-pair simulation.

    Usage:
        cache = MarketDataCache.get_instance()
        conn = cache.get_connection()
        table_name = cache.ensure_pair_registered(pair, files, dataset)
    """

    _instance: ClassVar["MarketDataCache | None"] = None
    _pid: ClassVar[int] = -1  # Track process ID to detect forks

    def __init__(self) -> None:
        """Initialize cache (private - use get_instance())."""
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._registered_pairs: dict[str, str] = {}  # (pair, dataset) -> table_name
        self._memory_limit = os.environ.get("EFXBT_DUCKDB_MEMORY_LIMIT", "4GB")

    @classmethod
    def get_instance(cls) -> "MarketDataCache":
        """Get process-local singleton instance.

        Handles process forking by detecting PID changes.

        Returns:
            MarketDataCache instance for current process
        """
        current_pid = os.getpid()

        # Detect fork - create new instance for child process
        if cls._pid != current_pid:
            cls._instance = None
            cls._pid = current_pid

        if cls._instance is None:
            cls._instance = cls()
            logger.debug(f"Created MarketDataCache for process {current_pid}")

        return cls._instance

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create DuckDB connection.

        Returns:
            DuckDB connection configured with memory limits
        """
        if self._conn is None:
            self._conn = duckdb.connect(":memory:")
            self._conn.execute(f"SET memory_limit = '{self._memory_limit}'")

            # Enable spill to disk for large queries
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "duckdb_cache" / str(os.getpid())
            temp_dir.mkdir(parents=True, exist_ok=True)
            self._conn.execute(f"SET temp_directory = '{temp_dir}'")

            logger.debug(
                f"Created DuckDB connection for process {os.getpid()} "
                f"with memory_limit={self._memory_limit}"
            )

        return self._conn

    def ensure_pair_registered(
        self,
        pair: str,
        files: list[Path],
        dataset: str,
    ) -> str:
        """Ensure pair's market data is registered as a table.

        Registers the parquet files as a DuckDB table ONCE, then reuses
        across all shards for this pair.

        Args:
            pair: Currency pair (e.g., "EURUSD")
            files: List of parquet file paths
            dataset: Dataset name (for cache key uniqueness)

        Returns:
            Table name to use in queries
        """
        cache_key = f"{dataset}:{pair}"

        if cache_key not in self._registered_pairs:
            conn = self.get_connection()
            table_name = f"market_{pair}_{dataset}".replace("-", "_")

            # Register as TABLE (not VIEW) for better query performance
            paths_str = ", ".join(f"'{p}'" for p in files)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} AS
                SELECT * FROM read_parquet([{paths_str}])
            """)

            # Create index on timestamp for faster ASOF lookups
            try:
                conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table_name}_ts
                    ON {table_name} (timestamp_ms)
                """)
            except Exception:
                # Index creation may fail if already exists or not supported
                pass

            self._registered_pairs[cache_key] = table_name
            logger.debug(f"Registered market data table {table_name} with {len(files)} files")

        return self._registered_pairs[cache_key]

    def ensure_fx_pair_registered(
        self,
        pair: str,
        files: list[Path],
        dataset: str,
        index: int,
    ) -> str:
        """Ensure FX conversion pair data is registered.

        Args:
            pair: FX pair (e.g., "GBPUSD")
            files: List of parquet file paths
            dataset: Dataset name
            index: Index for table naming (supports multiple FX pairs)

        Returns:
            Table name to use in queries
        """
        cache_key = f"{dataset}:fx:{pair}"

        if cache_key not in self._registered_pairs:
            conn = self.get_connection()
            table_name = f"fx_{pair}_{dataset}_{index}".replace("-", "_")

            paths_str = ", ".join(f"'{p}'" for p in files)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} AS
                SELECT * FROM read_parquet([{paths_str}])
            """)

            self._registered_pairs[cache_key] = table_name
            logger.debug(f"Registered FX table {table_name}")

        return self._registered_pairs[cache_key]

    def clear_cache(self) -> None:
        """Clear all cached data and close connection.

        Useful for testing or when switching datasets.
        """
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

        self._registered_pairs.clear()
        logger.debug(f"Cleared MarketDataCache for process {os.getpid()}")

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        if cls._instance is not None:
            cls._instance.clear_cache()
        cls._instance = None
        cls._pid = -1
