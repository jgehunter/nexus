"""Data health analysis for separated architecture.

This module provides health analyzers for the new separated architecture:
- MarketDataHealthAnalyzer: Analyzes market data quality (gaps, coverage)
- TradeBookHealthAnalyzer: Analyzes trade book quality (counts, volume)

The old DataHealthAnalyzer is preserved in health.py for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from .registry import (
    MarketDatasetInventory,
    MarketPairDateInventory,
    TradeBookInventory,
    TradeDateInventory,
)
from .schemas import MARKET_ARROW_SCHEMA, TRADE_ARROW_SCHEMA


@dataclass
class TickCoverageStats:
    """Tick coverage statistics for a pair-date."""

    pair: str
    date: str
    has_data: bool
    tick_count: int = 0
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    duration_ms: int | None = None
    avg_gap_ms: float | None = None
    max_gap_ms: int | None = None
    gaps_over_1min: int = 0
    gaps_over_5min: int = 0
    gaps_over_15min: int = 0


@dataclass
class TradeStats:
    """Trade statistics for a date in a trade book."""

    date: str
    has_data: bool
    trade_count: int = 0
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    duration_ms: int | None = None


@dataclass
class SchemaValidation:
    """Schema validation result for a parquet file."""

    file_path: Path
    is_valid: bool
    expected_schema: str
    actual_schema: str
    missing_fields: list[str] | None = None
    extra_fields: list[str] | None = None
    type_mismatches: dict[str, tuple[str, str]] | None = None


@dataclass
class MarketDataHealthReport:
    """Health report for a market dataset.

    Focuses on tick quality: coverage, gaps, and temporal consistency.
    """

    dataset_name: str
    version_id: str
    tick_coverage: list[TickCoverageStats]
    schema_validations: list[SchemaValidation]
    has_issues: bool
    summary: dict[str, Any]


@dataclass
class TradeBookHealthReport:
    """Health report for a trade book.

    Focuses on trade statistics: counts and temporal distribution.
    """

    book_name: str
    version_id: str
    trade_stats: list[TradeStats]
    schema_validations: list[SchemaValidation]
    has_issues: bool
    summary: dict[str, Any]


class MarketDataHealthAnalyzer:
    """Analyzes health of market datasets (tick data).

    Performs gap analysis, coverage checks, and schema validation
    for market tick data.
    """

    # Batch size for DuckDB queries (to avoid overly large UNION ALL)
    BATCH_SIZE = 50

    def __init__(self, inventory: MarketDatasetInventory):
        """Initialize analyzer.

        Args:
            inventory: Market dataset inventory to analyze
        """
        self.inventory = inventory

    def compute_health_report(
        self, validate_schemas: bool = True
    ) -> MarketDataHealthReport:
        """Compute comprehensive health report for market data.

        Uses batched DuckDB queries for efficient processing of many files.

        Args:
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Market data health report with coverage and validation results
        """
        # Use batched queries for tick coverage (major performance improvement)
        tick_coverage = self._compute_all_tick_coverage_batched()

        schema_validations = []
        if validate_schemas:
            schema_validations = self._validate_schemas()

        # Compute summary
        summary = self._compute_summary(tick_coverage, schema_validations)

        has_issues = summary["total_schema_issues"] > 0 or summary["gaps_over_5min"] > 0

        return MarketDataHealthReport(
            dataset_name=self.inventory.name,
            version_id=self.inventory.version_id,
            tick_coverage=tick_coverage,
            schema_validations=schema_validations,
            has_issues=has_issues,
            summary=summary,
        )

    def _compute_all_tick_coverage_batched(self) -> list[TickCoverageStats]:
        """Compute tick coverage for all files using batched DuckDB queries.

        Uses a single DuckDB connection and batches files to avoid
        memory issues with large UNION ALL queries.

        Returns:
            List of tick coverage statistics for all pair-dates
        """
        # Filter to only files that exist
        valid_pair_dates = [pd for pd in self.inventory.pair_dates if pd.file_path]

        if not valid_pair_dates:
            return []

        results = []

        # Process in batches to avoid memory issues
        for i in range(0, len(valid_pair_dates), self.BATCH_SIZE):
            batch = valid_pair_dates[i : i + self.BATCH_SIZE]
            batch_results = self._compute_batch_tick_coverage(batch)
            results.extend(batch_results)

        return results

    def _compute_batch_tick_coverage(
        self, batch: list[MarketPairDateInventory]
    ) -> list[TickCoverageStats]:
        """Compute tick coverage for a batch of files in a single query.

        Args:
            batch: List of pair-date items to process

        Returns:
            List of tick coverage statistics
        """
        if not batch:
            return []

        try:
            conn = duckdb.connect(":memory:")

            # Build UNION ALL query for all files in batch
            file_queries = []
            for pd in batch:
                # Escape single quotes in file path
                file_path = str(pd.file_path).replace("'", "''")
                file_queries.append(f"""
                    SELECT
                        '{pd.pair}' AS pair,
                        '{pd.date}' AS date,
                        timestamp_ms
                    FROM read_parquet('{file_path}')
                """)

            # Combine all files and compute stats
            combined_query = f"""
            WITH all_ticks AS (
                {' UNION ALL '.join(file_queries)}
            ),
            tick_data AS (
                SELECT
                    pair,
                    date,
                    timestamp_ms,
                    LAG(timestamp_ms) OVER (PARTITION BY pair, date ORDER BY timestamp_ms) AS prev_ts
                FROM all_ticks
            ),
            gaps AS (
                SELECT
                    pair,
                    date,
                    timestamp_ms - prev_ts AS gap_ms
                FROM tick_data
                WHERE prev_ts IS NOT NULL
            ),
            gap_stats AS (
                SELECT
                    pair,
                    date,
                    AVG(gap_ms) AS avg_gap,
                    MAX(gap_ms) AS max_gap,
                    SUM(CASE WHEN gap_ms > 60000 THEN 1 ELSE 0 END) AS gaps_1min,
                    SUM(CASE WHEN gap_ms > 300000 THEN 1 ELSE 0 END) AS gaps_5min,
                    SUM(CASE WHEN gap_ms > 900000 THEN 1 ELSE 0 END) AS gaps_15min
                FROM gaps
                GROUP BY pair, date
            )
            SELECT
                t.pair,
                t.date,
                COUNT(*) AS tick_count,
                MIN(t.timestamp_ms) AS first_ts,
                MAX(t.timestamp_ms) AS last_ts,
                g.avg_gap,
                g.max_gap,
                COALESCE(g.gaps_1min, 0) AS gaps_1min,
                COALESCE(g.gaps_5min, 0) AS gaps_5min,
                COALESCE(g.gaps_15min, 0) AS gaps_15min
            FROM tick_data t
            LEFT JOIN gap_stats g ON t.pair = g.pair AND t.date = g.date
            GROUP BY t.pair, t.date, g.avg_gap, g.max_gap, g.gaps_1min, g.gaps_5min, g.gaps_15min
            ORDER BY t.pair, t.date
            """

            rows = conn.execute(combined_query).fetchall()
            conn.close()

            # Convert results to TickCoverageStats
            results = []
            for row in rows:
                pair, date, tick_count, first_ts, last_ts, avg_gap, max_gap, gaps_1min, gaps_5min, gaps_15min = row
                duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

                results.append(
                    TickCoverageStats(
                        pair=pair,
                        date=date,
                        has_data=True,
                        tick_count=tick_count or 0,
                        first_timestamp_ms=first_ts,
                        last_timestamp_ms=last_ts,
                        duration_ms=duration_ms,
                        avg_gap_ms=avg_gap,
                        max_gap_ms=max_gap,
                        gaps_over_1min=gaps_1min or 0,
                        gaps_over_5min=gaps_5min or 0,
                        gaps_over_15min=gaps_15min or 0,
                    )
                )

            return results

        except Exception:
            # Fall back to individual queries on batch failure
            return [self._compute_tick_coverage_single(pd) for pd in batch]

    def _compute_tick_coverage_single(
        self, pd: MarketPairDateInventory
    ) -> TickCoverageStats:
        """Compute tick coverage for a single file (fallback method).

        Args:
            pd: Market pair-date inventory item

        Returns:
            Tick coverage statistics
        """
        if not pd.file_path:
            return TickCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

        try:
            conn = duckdb.connect(":memory:")
            file_path = str(pd.file_path).replace("'", "''")

            query = f"""
            WITH tick_data AS (
                SELECT
                    timestamp_ms,
                    LAG(timestamp_ms) OVER (ORDER BY timestamp_ms) AS prev_ts
                FROM read_parquet('{file_path}')
            ),
            gaps AS (
                SELECT timestamp_ms - prev_ts AS gap_ms
                FROM tick_data
                WHERE prev_ts IS NOT NULL
            )
            SELECT
                COUNT(*) AS tick_count,
                MIN(timestamp_ms) AS first_ts,
                MAX(timestamp_ms) AS last_ts,
                AVG(gap_ms) AS avg_gap,
                MAX(gap_ms) AS max_gap,
                SUM(CASE WHEN gap_ms > 60000 THEN 1 ELSE 0 END) AS gaps_1min,
                SUM(CASE WHEN gap_ms > 300000 THEN 1 ELSE 0 END) AS gaps_5min,
                SUM(CASE WHEN gap_ms > 900000 THEN 1 ELSE 0 END) AS gaps_15min
            FROM tick_data
            LEFT JOIN gaps ON 1=1
            """

            result = conn.execute(query).fetchone()
            conn.close()

            if result is None:
                return TickCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

            tick_count, first_ts, last_ts, avg_gap, max_gap, gaps_1min, gaps_5min, gaps_15min = result
            duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

            return TickCoverageStats(
                pair=pd.pair,
                date=pd.date,
                has_data=True,
                tick_count=tick_count or 0,
                first_timestamp_ms=first_ts,
                last_timestamp_ms=last_ts,
                duration_ms=duration_ms,
                avg_gap_ms=avg_gap,
                max_gap_ms=max_gap,
                gaps_over_1min=gaps_1min or 0,
                gaps_over_5min=gaps_5min or 0,
                gaps_over_15min=gaps_15min or 0,
            )

        except Exception:
            return TickCoverageStats(
                pair=pd.pair, date=pd.date, has_data=False, tick_count=0
            )

    def _validate_schemas(self) -> list[SchemaValidation]:
        """Validate parquet file schemas against expected market schema.

        Returns:
            List of schema validation results
        """
        validations = []

        for pd in self.inventory.pair_dates:
            if pd.file_path:
                validation = self._validate_file_schema(
                    pd.file_path, MARKET_ARROW_SCHEMA, "market"
                )
                validations.append(validation)

        return validations

    def _validate_file_schema(
        self, file_path: Path, expected_schema: Any, schema_type: str
    ) -> SchemaValidation:
        """Validate a single parquet file's schema.

        Args:
            file_path: Path to parquet file
            expected_schema: Expected PyArrow schema
            schema_type: Type label for reporting

        Returns:
            Schema validation result
        """
        try:
            pq_file = pq.ParquetFile(file_path)
            actual_schema = pq_file.schema_arrow

            # Check field names
            expected_names = set(expected_schema.names)
            actual_names = set(actual_schema.names)

            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)

            # Check types for common fields
            type_mismatches = {}
            for name in expected_names & actual_names:
                expected_type = str(expected_schema.field(name).type)
                actual_type = str(actual_schema.field(name).type)
                if expected_type != actual_type:
                    type_mismatches[name] = (expected_type, actual_type)

            is_valid = not (missing or extra or type_mismatches)

            return SchemaValidation(
                file_path=file_path,
                is_valid=is_valid,
                expected_schema=schema_type,
                actual_schema=str(actual_schema),
                missing_fields=missing if missing else None,
                extra_fields=extra if extra else None,
                type_mismatches=type_mismatches if type_mismatches else None,
            )

        except Exception as e:
            return SchemaValidation(
                file_path=file_path,
                is_valid=False,
                expected_schema=schema_type,
                actual_schema=f"Error reading schema: {str(e)}",
            )

    def _compute_summary(
        self,
        tick_coverage: list[TickCoverageStats],
        schema_validations: list[SchemaValidation],
    ) -> dict[str, Any]:
        """Compute summary statistics for market data.

        Args:
            tick_coverage: List of tick coverage stats
            schema_validations: List of schema validations

        Returns:
            Summary dictionary
        """
        tick_with_data = [t for t in tick_coverage if t.has_data]

        total_ticks = sum(t.tick_count for t in tick_with_data)
        total_gaps_1min = sum(t.gaps_over_1min for t in tick_with_data)
        total_gaps_5min = sum(t.gaps_over_5min for t in tick_with_data)
        total_gaps_15min = sum(t.gaps_over_15min for t in tick_with_data)

        schema_issues = len([v for v in schema_validations if not v.is_valid])

        return {
            "total_tick_files": len(tick_coverage),
            "total_ticks": total_ticks,
            "gaps_over_1min": total_gaps_1min,
            "gaps_over_5min": total_gaps_5min,
            "gaps_over_15min": total_gaps_15min,
            "total_schema_issues": schema_issues,
            "pairs_covered": len(set(t.pair for t in tick_with_data)),
        }


class TradeBookHealthAnalyzer:
    """Analyzes health of trade books.

    Performs trade count analysis, volume statistics, and schema validation
    for trade data.
    """

    # Batch size for DuckDB queries
    BATCH_SIZE = 50

    def __init__(self, inventory: TradeBookInventory):
        """Initialize analyzer.

        Args:
            inventory: Trade book inventory to analyze
        """
        self.inventory = inventory

    def compute_health_report(
        self, validate_schemas: bool = True
    ) -> TradeBookHealthReport:
        """Compute comprehensive health report for trade book.

        Uses batched DuckDB queries for efficient processing of many files.

        Args:
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Trade book health report with statistics and validation results
        """
        # Use batched queries for trade stats (major performance improvement)
        trade_stats = self._compute_all_trade_stats_batched()

        schema_validations = []
        if validate_schemas:
            schema_validations = self._validate_schemas()

        # Compute summary
        summary = self._compute_summary(trade_stats, schema_validations)

        has_issues = summary["total_schema_issues"] > 0

        return TradeBookHealthReport(
            book_name=self.inventory.name,
            version_id=self.inventory.version_id,
            trade_stats=trade_stats,
            schema_validations=schema_validations,
            has_issues=has_issues,
            summary=summary,
        )

    def _compute_all_trade_stats_batched(self) -> list[TradeStats]:
        """Compute trade stats for all files using batched DuckDB queries.

        Uses a single DuckDB connection and batches files to avoid
        memory issues with large UNION ALL queries.

        Returns:
            List of trade statistics for all dates
        """
        # Filter to only files that exist
        valid_date_files = [df for df in self.inventory.date_files if df.file_path]

        if not valid_date_files:
            return []

        results = []

        # Process in batches to avoid memory issues
        for i in range(0, len(valid_date_files), self.BATCH_SIZE):
            batch = valid_date_files[i : i + self.BATCH_SIZE]
            batch_results = self._compute_batch_trade_stats(batch)
            results.extend(batch_results)

        return results

    def _compute_batch_trade_stats(
        self, batch: list[TradeDateInventory]
    ) -> list[TradeStats]:
        """Compute trade stats for a batch of files in a single query.

        Args:
            batch: List of date inventory items to process

        Returns:
            List of trade statistics
        """
        if not batch:
            return []

        try:
            conn = duckdb.connect(":memory:")

            # Build UNION ALL query for all files in batch
            file_queries = []
            for df in batch:
                # Escape single quotes in file path
                file_path = str(df.file_path).replace("'", "''")
                file_queries.append(f"""
                    SELECT '{df.date}' AS date, timestamp_ms
                    FROM read_parquet('{file_path}')
                """)

            # Combine all files and compute stats
            combined_query = f"""
            WITH all_trades AS (
                {' UNION ALL '.join(file_queries)}
            )
            SELECT
                date,
                COUNT(*) AS trade_count,
                MIN(timestamp_ms) AS first_ts,
                MAX(timestamp_ms) AS last_ts
            FROM all_trades
            GROUP BY date
            ORDER BY date
            """

            rows = conn.execute(combined_query).fetchall()
            conn.close()

            # Convert results to TradeStats
            results = []
            for row in rows:
                date, trade_count, first_ts, last_ts = row
                duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

                results.append(
                    TradeStats(
                        date=date,
                        has_data=True,
                        trade_count=trade_count or 0,
                        first_timestamp_ms=first_ts,
                        last_timestamp_ms=last_ts,
                        duration_ms=duration_ms,
                    )
                )

            return results

        except Exception:
            # Fall back to individual queries on batch failure
            return [self._compute_trade_stats_single(df) for df in batch]

    def _compute_trade_stats_single(self, df: TradeDateInventory) -> TradeStats:
        """Compute trade statistics for a single file (fallback method).

        Args:
            df: Trade date inventory item

        Returns:
            Trade statistics
        """
        if not df.file_path:
            return TradeStats(date=df.date, has_data=False)

        try:
            conn = duckdb.connect(":memory:")
            file_path = str(df.file_path).replace("'", "''")

            query = f"""
            SELECT
                COUNT(*) AS trade_count,
                MIN(timestamp_ms) AS first_ts,
                MAX(timestamp_ms) AS last_ts
            FROM read_parquet('{file_path}')
            """

            result = conn.execute(query).fetchone()
            conn.close()

            if result is None:
                return TradeStats(date=df.date, has_data=False)

            trade_count, first_ts, last_ts = result
            duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

            return TradeStats(
                date=df.date,
                has_data=True,
                trade_count=trade_count or 0,
                first_timestamp_ms=first_ts,
                last_timestamp_ms=last_ts,
                duration_ms=duration_ms,
            )

        except Exception:
            return TradeStats(date=df.date, has_data=False)

    def _validate_schemas(self) -> list[SchemaValidation]:
        """Validate parquet file schemas against expected trade schema.

        Returns:
            List of schema validation results
        """
        validations = []

        for df in self.inventory.date_files:
            if df.file_path:
                validation = self._validate_file_schema(
                    df.file_path, TRADE_ARROW_SCHEMA, "trades"
                )
                validations.append(validation)

        return validations

    def _validate_file_schema(
        self, file_path: Path, expected_schema: Any, schema_type: str
    ) -> SchemaValidation:
        """Validate a single parquet file's schema.

        Args:
            file_path: Path to parquet file
            expected_schema: Expected PyArrow schema
            schema_type: Type label for reporting

        Returns:
            Schema validation result
        """
        try:
            pq_file = pq.ParquetFile(file_path)
            actual_schema = pq_file.schema_arrow

            # Check field names
            expected_names = set(expected_schema.names)
            actual_names = set(actual_schema.names)

            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)

            # Check types for common fields
            type_mismatches = {}
            for name in expected_names & actual_names:
                expected_type = str(expected_schema.field(name).type)
                actual_type = str(actual_schema.field(name).type)
                if expected_type != actual_type:
                    type_mismatches[name] = (expected_type, actual_type)

            is_valid = not (missing or extra or type_mismatches)

            return SchemaValidation(
                file_path=file_path,
                is_valid=is_valid,
                expected_schema=schema_type,
                actual_schema=str(actual_schema),
                missing_fields=missing if missing else None,
                extra_fields=extra if extra else None,
                type_mismatches=type_mismatches if type_mismatches else None,
            )

        except Exception as e:
            return SchemaValidation(
                file_path=file_path,
                is_valid=False,
                expected_schema=schema_type,
                actual_schema=f"Error reading schema: {str(e)}",
            )

    def _compute_summary(
        self,
        trade_stats: list[TradeStats],
        schema_validations: list[SchemaValidation],
    ) -> dict[str, Any]:
        """Compute summary statistics for trade book.

        Args:
            trade_stats: List of trade statistics
            schema_validations: List of schema validations

        Returns:
            Summary dictionary
        """
        trades_with_data = [t for t in trade_stats if t.has_data]

        total_trades = sum(t.trade_count for t in trades_with_data)

        schema_issues = len([v for v in schema_validations if not v.is_valid])

        return {
            "total_trade_files": len(trade_stats),
            "total_trades": total_trades,
            "total_schema_issues": schema_issues,
            "dates_covered": len(trades_with_data),
        }
