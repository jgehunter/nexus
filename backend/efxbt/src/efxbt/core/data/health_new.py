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

from efxbt.core.data.registry import (
    MarketDatasetInventory,
    MarketPairDateInventory,
    TradeBookInventory,
    TradeDateInventory,
)
from efxbt.core.data.schemas import MARKET_ARROW_SCHEMA, TRADE_ARROW_SCHEMA


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

        Args:
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Market data health report with coverage and validation results
        """
        tick_coverage = []

        for pd in self.inventory.pair_dates:
            if pd.file_path:
                tick_stats = self._compute_tick_coverage(pd)
                tick_coverage.append(tick_stats)

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

    def _compute_tick_coverage(self, pd: MarketPairDateInventory) -> TickCoverageStats:
        """Compute tick coverage statistics for a pair-date.

        Uses DuckDB for efficient aggregation without loading all data.

        Args:
            pd: Market pair-date inventory item

        Returns:
            Tick coverage statistics
        """
        if not pd.file_path:
            return TickCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

        try:
            conn = duckdb.connect(":memory:")

            # Read tick data with timestamp analysis
            query = f"""
            WITH tick_data AS (
                SELECT
                    timestamp_ms,
                    LAG(timestamp_ms) OVER (ORDER BY timestamp_ms) AS prev_ts
                FROM read_parquet('{pd.file_path}')
            ),
            gaps AS (
                SELECT
                    timestamp_ms - prev_ts AS gap_ms
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

            tick_count = result[0] or 0
            first_ts = result[1]
            last_ts = result[2]
            avg_gap = result[3]
            max_gap = result[4]
            gaps_1min = result[5] or 0
            gaps_5min = result[6] or 0
            gaps_15min = result[7] or 0

            duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

            return TickCoverageStats(
                pair=pd.pair,
                date=pd.date,
                has_data=True,
                tick_count=tick_count,
                first_timestamp_ms=first_ts,
                last_timestamp_ms=last_ts,
                duration_ms=duration_ms,
                avg_gap_ms=avg_gap,
                max_gap_ms=max_gap,
                gaps_over_1min=gaps_1min,
                gaps_over_5min=gaps_5min,
                gaps_over_15min=gaps_15min,
            )

        except Exception:
            return TickCoverageStats(
                pair=pd.pair,
                date=pd.date,
                has_data=False,
                tick_count=0,
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
            "total_market_files": len(tick_coverage),
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

        Args:
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Trade book health report with statistics and validation results
        """
        trade_stats = []

        for df in self.inventory.date_files:
            if df.file_path:
                stats = self._compute_trade_stats(df)
                trade_stats.append(stats)

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

    def _compute_trade_stats(self, df: TradeDateInventory) -> TradeStats:
        """Compute trade statistics for a date.

        Args:
            df: Trade date inventory item

        Returns:
            Trade statistics
        """
        if not df.file_path:
            return TradeStats(date=df.date, has_data=False)

        try:
            conn = duckdb.connect(":memory:")

            query = f"""
            SELECT
                COUNT(*) AS trade_count,
                MIN(timestamp_ms) AS first_ts,
                MAX(timestamp_ms) AS last_ts
            FROM read_parquet('{df.file_path}')
            """

            result = conn.execute(query).fetchone()
            conn.close()

            if result is None:
                return TradeStats(date=df.date, has_data=False)

            trade_count = result[0] or 0
            first_ts = result[1]
            last_ts = result[2]

            duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

            return TradeStats(
                date=df.date,
                has_data=True,
                trade_count=trade_count,
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
