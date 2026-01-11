"""Service layer for market dataset operations.

Provides business logic for market dataset discovery, health checks, and management.
Market datasets contain only tick price data (the observable universe).
"""

from pathlib import Path

from pydantic import BaseModel

from ...core.data.health_new import (
    MarketDataHealthAnalyzer,
    MarketDataHealthReport,
    TickCoverageStats,
)
from ...core.data.registry import (
    MarketDatasetInventory,
    MarketDatasetRegistry,
)


class DatasetSummary(BaseModel):
    """Summary information about a market dataset for API responses."""

    name: str
    version_id: str
    pairs: list[str]
    dates: list[str]
    total_files: int
    total_ticks: int
    root_path: str


class DatasetDetail(BaseModel):
    """Detailed information about a market dataset including pair-date inventory."""

    name: str
    version_id: str
    pairs: list[str]
    dates: list[str]
    total_files: int
    total_ticks: int
    root_path: str
    pair_dates: list[dict[str, str | int]]


class HealthReportResponse(BaseModel):
    """Health report response for market datasets."""

    dataset_name: str
    version_id: str
    has_issues: bool
    summary: dict[str, int | float]
    tick_coverage: list[dict[str, str | bool | int | float | None]]


class DatasetsService:
    """Service for market dataset operations."""

    def __init__(self, data_root: Path) -> None:
        """Initialize service.

        Args:
            data_root: Root data directory
        """
        self.data_root = Path(data_root)
        self.registry = MarketDatasetRegistry(self.data_root)

    def list_datasets(self) -> list[DatasetSummary]:
        """List all available market datasets with summary info.

        Returns:
            List of market dataset summaries
        """
        dataset_names = self.registry.list_datasets()
        summaries = []

        for name in dataset_names:
            try:
                inventory = self.registry.discover_dataset(name)
                summaries.append(self._inventory_to_summary(inventory))
            except Exception:
                # Skip datasets that fail to load
                continue

        return summaries

    def get_dataset(self, dataset_name: str) -> DatasetDetail:
        """Get detailed information about a market dataset.

        Args:
            dataset_name: Name of the dataset

        Returns:
            Detailed dataset information

        Raises:
            FileNotFoundError: If dataset does not exist
        """
        inventory = self.registry.discover_dataset(dataset_name)
        return self._inventory_to_detail(inventory)

    def get_dataset_pairs(self, dataset_name: str) -> list[str]:
        """Get list of pairs in a market dataset.

        Args:
            dataset_name: Name of the dataset

        Returns:
            Sorted list of pairs

        Raises:
            FileNotFoundError: If dataset does not exist
        """
        inventory = self.registry.discover_dataset(dataset_name)
        return inventory.pairs

    def get_dataset_dates(self, dataset_name: str) -> list[str]:
        """Get list of dates in a market dataset.

        Args:
            dataset_name: Name of the dataset

        Returns:
            Sorted list of dates in YYYYMMDD format

        Raises:
            FileNotFoundError: If dataset does not exist
        """
        inventory = self.registry.discover_dataset(dataset_name)
        return inventory.dates

    def compute_health(
        self, dataset_name: str, validate_schemas: bool = True
    ) -> HealthReportResponse:
        """Compute health report for a market dataset.

        Args:
            dataset_name: Name of the dataset
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Health report

        Raises:
            FileNotFoundError: If dataset does not exist
        """
        inventory = self.registry.discover_dataset(dataset_name)
        analyzer = MarketDataHealthAnalyzer(inventory)
        report = analyzer.compute_health_report(validate_schemas=validate_schemas)

        return self._health_report_to_response(report)

    def _inventory_to_summary(
        self, inventory: MarketDatasetInventory
    ) -> DatasetSummary:
        """Convert inventory to summary response.

        Args:
            inventory: Market dataset inventory

        Returns:
            Dataset summary
        """
        return DatasetSummary(
            name=inventory.name,
            version_id=inventory.version_id,
            pairs=inventory.pairs,
            dates=inventory.dates,
            total_files=inventory.total_files,
            total_ticks=inventory.total_ticks,
            root_path=str(inventory.root_path),
        )

    def _inventory_to_detail(self, inventory: MarketDatasetInventory) -> DatasetDetail:
        """Convert inventory to detailed response.

        Args:
            inventory: Market dataset inventory

        Returns:
            Dataset detail
        """
        pair_dates = [
            {
                "pair": pd.pair,
                "date": pd.date,
                "row_count": pd.row_count,
            }
            for pd in inventory.pair_dates
        ]

        return DatasetDetail(
            name=inventory.name,
            version_id=inventory.version_id,
            pairs=inventory.pairs,
            dates=inventory.dates,
            total_files=inventory.total_files,
            total_ticks=inventory.total_ticks,
            root_path=str(inventory.root_path),
            pair_dates=pair_dates,
        )

    def _health_report_to_response(
        self, report: MarketDataHealthReport
    ) -> HealthReportResponse:
        """Convert health report to API response.

        Args:
            report: Market data health report

        Returns:
            Health report response
        """
        tick_coverage = [
            {
                "pair": tc.pair,
                "date": tc.date,
                "has_data": tc.has_data,
                "tick_count": tc.tick_count,
                "first_timestamp_ms": tc.first_timestamp_ms,
                "last_timestamp_ms": tc.last_timestamp_ms,
                "duration_ms": tc.duration_ms,
                "avg_gap_ms": tc.avg_gap_ms,
                "max_gap_ms": tc.max_gap_ms,
                "gaps_over_1min": tc.gaps_over_1min,
                "gaps_over_5min": tc.gaps_over_5min,
                "gaps_over_15min": tc.gaps_over_15min,
            }
            for tc in report.tick_coverage
        ]

        return HealthReportResponse(
            dataset_name=report.dataset_name,
            version_id=report.version_id,
            has_issues=report.has_issues,
            summary=report.summary,
            tick_coverage=tick_coverage,
        )
