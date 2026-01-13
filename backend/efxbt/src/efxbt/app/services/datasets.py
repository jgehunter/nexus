"""Service layer for market dataset operations.

Provides business logic for market dataset discovery, health checks, and management.
Market datasets contain only tick price data (the observable universe).
"""

from pathlib import Path

from pydantic import BaseModel

from ...core.cache.health_cache import get_health_cache
from ...core.cache.registry_cache import get_registry_cache
from ...core.data.market_health import (
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
        self._registry_cache = get_registry_cache()
        self._health_cache = get_health_cache()

    def list_datasets(self) -> list[DatasetSummary]:
        """List all available market datasets with summary info.

        Uses caching to avoid repeated filesystem scans.

        Returns:
            List of market dataset summaries
        """
        # Try cache first for the list
        cached_names = self._registry_cache.get_dataset_list(
            self.registry.datasets_dir
        )
        if cached_names is not None:
            dataset_names = cached_names
        else:
            dataset_names = self.registry.list_datasets()
            self._registry_cache.set_dataset_list(
                self.registry.datasets_dir, dataset_names
            )

        summaries = []
        for name in dataset_names:
            try:
                # Try cache for individual inventory
                inventory = self._registry_cache.get_dataset_inventory(name)
                if inventory is None:
                    inventory = self.registry.discover_dataset(name)
                    self._registry_cache.set_dataset_inventory(name, inventory)
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

        Uses caching to avoid recomputing expensive health analysis.

        Args:
            dataset_name: Name of the dataset
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Health report

        Raises:
            FileNotFoundError: If dataset does not exist
        """
        # Get inventory (with caching)
        inventory = self._registry_cache.get_dataset_inventory(dataset_name)
        if inventory is None:
            inventory = self.registry.discover_dataset(dataset_name)
            self._registry_cache.set_dataset_inventory(dataset_name, inventory)

        # Try health cache (only for non-schema-validation requests)
        # Schema validation is typically slower and less frequently needed
        if not validate_schemas:
            cached_report = self._health_cache.get_market_health(
                dataset_name, inventory.version_id
            )
            if cached_report is not None:
                return self._health_report_to_response(cached_report)

        # Compute health report
        analyzer = MarketDataHealthAnalyzer(inventory)
        report = analyzer.compute_health_report(validate_schemas=validate_schemas)

        # Cache the result (only if not validating schemas, as that's the common case)
        if not validate_schemas:
            self._health_cache.set_market_health(
                dataset_name, inventory.version_id, report
            )

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
