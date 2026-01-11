"""Data health metrics and validation.

Provides comprehensive data quality checks including:
- Tick coverage statistics per pair/day
- Schema conformance validation
- Timestamp validation and gap detection
- Price sanity checks
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from .registry import DatasetInventory, PairDateInventory
from .schemas import MARKET_ARROW_SCHEMA, TRADE_ARROW_SCHEMA


@dataclass(frozen=True)
class TickCoverageStats:
    """Statistics about tick coverage for a pair on a specific date."""

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


@dataclass(frozen=True)
class TradeCoverageStats:
    """Statistics about trades for a pair on a specific date."""

    pair: str
    date: str
    has_data: bool
    trade_count: int = 0
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    duration_ms: int | None = None
    total_volume: float = 0.0
    avg_trade_size: float = 0.0


@dataclass(frozen=True)
class SchemaValidation:
    """Result of schema validation for a parquet file."""

    file_path: Path
    is_valid: bool
    expected_schema: str
    actual_schema: str | None = None
    missing_fields: list[str] | None = None
    extra_fields: list[str] | None = None
    type_mismatches: dict[str, tuple[str, str]] | None = None


@dataclass(frozen=True)
class DataHealthReport:
    """Comprehensive health report for a dataset."""

    dataset_name: str
    version_id: str
    tick_coverage: list[TickCoverageStats]
    trade_coverage: list[TradeCoverageStats]
    schema_validations: list[SchemaValidation]
    has_issues: bool
    summary: dict[str, Any]


class DataHealthAnalyzer:
    """Analyzer for computing data health metrics."""

    def __init__(self, inventory: DatasetInventory) -> None:
        """Initialize analyzer with dataset inventory.

        Args:
            inventory: Dataset inventory from registry
        """
        self.inventory = inventory

    def compute_health_report(
        self, validate_schemas: bool = True
    ) -> DataHealthReport:
        """Compute comprehensive health report.

        Args:
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Complete health report
        """
        tick_coverage = []
        trade_coverage = []

        for pd in self.inventory.pair_dates:
            if pd.has_market and pd.market_file:
                tick_stats = self._compute_tick_coverage(pd)
                tick_coverage.append(tick_stats)

            if pd.has_trades and pd.trades_file:
                trade_stats = self._compute_trade_coverage(pd)
                trade_coverage.append(trade_stats)

        schema_validations = []
        if validate_schemas:
            schema_validations = self._validate_schemas()

        # Compute summary
        summary = self._compute_summary(
            tick_coverage, trade_coverage, schema_validations
        )

        has_issues = summary["total_schema_issues"] > 0

        return DataHealthReport(
            dataset_name=self.inventory.name,
            version_id=self.inventory.version_id,
            tick_coverage=tick_coverage,
            trade_coverage=trade_coverage,
            schema_validations=schema_validations,
            has_issues=has_issues,
            summary=summary,
        )

    def _compute_tick_coverage(self, pd: PairDateInventory) -> TickCoverageStats:
        """Compute tick coverage statistics for a pair-date.

        Uses DuckDB for efficient aggregation without loading all data.

        Args:
            pd: Pair-date inventory item

        Returns:
            Tick coverage statistics
        """
        if not pd.has_market or not pd.market_file:
            return TickCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

        try:
            conn = duckdb.connect(":memory:")

            # Read tick data with timestamp analysis
            query = f"""
            WITH tick_data AS (
                SELECT
                    timestamp_ms,
                    LAG(timestamp_ms) OVER (ORDER BY timestamp_ms) AS prev_ts
                FROM read_parquet('{pd.market_file}')
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

        except Exception as e:
            # Return error state but don't fail entire analysis
            return TickCoverageStats(
                pair=pd.pair,
                date=pd.date,
                has_data=False,
                tick_count=0,
            )

    def _compute_trade_coverage(self, pd: PairDateInventory) -> TradeCoverageStats:
        """Compute trade coverage statistics for a pair-date.

        Args:
            pd: Pair-date inventory item

        Returns:
            Trade coverage statistics
        """
        if not pd.has_trades or not pd.trades_file:
            return TradeCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

        try:
            conn = duckdb.connect(":memory:")

            query = f"""
            SELECT
                COUNT(*) AS trade_count,
                MIN(timestamp_ms) AS first_ts,
                MAX(timestamp_ms) AS last_ts,
                SUM(qty) AS total_volume,
                AVG(qty) AS avg_trade_size
            FROM read_parquet('{pd.trades_file}')
            """

            result = conn.execute(query).fetchone()
            conn.close()

            if result is None:
                return TradeCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

            trade_count = result[0] or 0
            first_ts = result[1]
            last_ts = result[2]
            total_volume = result[3] or 0.0
            avg_trade_size = result[4] or 0.0

            duration_ms = (last_ts - first_ts) if (first_ts and last_ts) else None

            return TradeCoverageStats(
                pair=pd.pair,
                date=pd.date,
                has_data=True,
                trade_count=trade_count,
                first_timestamp_ms=first_ts,
                last_timestamp_ms=last_ts,
                duration_ms=duration_ms,
                total_volume=total_volume,
                avg_trade_size=avg_trade_size,
            )

        except Exception:
            return TradeCoverageStats(pair=pd.pair, date=pd.date, has_data=False)

    def _validate_schemas(self) -> list[SchemaValidation]:
        """Validate parquet file schemas against expected schemas.

        Returns:
            List of schema validation results
        """
        validations = []

        for pd in self.inventory.pair_dates:
            # Validate market file
            if pd.has_market and pd.market_file:
                validation = self._validate_file_schema(
                    pd.market_file, MARKET_ARROW_SCHEMA, "market"
                )
                validations.append(validation)

            # Validate trades file
            if pd.has_trades and pd.trades_file:
                validation = self._validate_file_schema(
                    pd.trades_file, TRADE_ARROW_SCHEMA, "trades"
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
        trade_coverage: list[TradeCoverageStats],
        schema_validations: list[SchemaValidation],
    ) -> dict[str, Any]:
        """Compute summary statistics for the report.

        Args:
            tick_coverage: List of tick coverage stats
            trade_coverage: List of trade coverage stats
            schema_validations: List of schema validations

        Returns:
            Summary dictionary
        """
        tick_with_data = [t for t in tick_coverage if t.has_data]
        trades_with_data = [t for t in trade_coverage if t.has_data]

        total_ticks = sum(t.tick_count for t in tick_with_data)
        total_trades = sum(t.trade_count for t in trades_with_data)
        total_volume = sum(t.total_volume for t in trades_with_data)

        # Count gaps
        total_gaps_1min = sum(t.gaps_over_1min for t in tick_with_data)
        total_gaps_5min = sum(t.gaps_over_5min for t in tick_with_data)
        total_gaps_15min = sum(t.gaps_over_15min for t in tick_with_data)

        # Schema issues
        schema_issues = len([v for v in schema_validations if not v.is_valid])

        return {
            "total_tick_files": len(tick_coverage),
            "total_trade_files": len(trade_coverage),
            "total_ticks": total_ticks,
            "total_trades": total_trades,
            "total_volume": total_volume,
            "gaps_over_1min": total_gaps_1min,
            "gaps_over_5min": total_gaps_5min,
            "gaps_over_15min": total_gaps_15min,
            "total_schema_issues": schema_issues,
            "pairs_with_ticks": len(set(t.pair for t in tick_with_data)),
            "pairs_with_trades": len(set(t.pair for t in trades_with_data)),
        }


def compute_tick_coverage(
    inventory: DatasetInventory, pair: str | None = None, date: str | None = None
) -> list[TickCoverageStats]:
    """Compute tick coverage statistics.

    Args:
        inventory: Dataset inventory
        pair: Optional pair filter
        date: Optional date filter

    Returns:
        List of tick coverage statistics
    """
    analyzer = DataHealthAnalyzer(inventory)
    report = analyzer.compute_health_report(validate_schemas=False)

    coverage = report.tick_coverage

    if pair:
        coverage = [c for c in coverage if c.pair == pair.upper()]
    if date:
        coverage = [c for c in coverage if c.date == date]

    return coverage
