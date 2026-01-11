"""Service layer for trade book operations.

Provides business logic for trade book discovery, health checks, and management.
"""

from pathlib import Path

from pydantic import BaseModel

from ...core.data.health_new import (
    TradeBookHealthAnalyzer,
    TradeBookHealthReport,
    TradeStats,
)
from ...core.data.registry import TradeBookInventory, TradeBookRegistry


class TradeBookSummary(BaseModel):
    """Summary information about a trade book for API responses."""

    name: str
    version_id: str
    dates: list[str]
    total_files: int
    total_trades: int
    root_path: str


class TradeBookDetail(BaseModel):
    """Detailed information about a trade book including per-date inventory."""

    name: str
    version_id: str
    dates: list[str]
    total_files: int
    total_trades: int
    root_path: str
    date_files: list[dict[str, str | int]]


class TradeBookHealthResponse(BaseModel):
    """Health report response for trade books."""

    book_name: str
    version_id: str
    has_issues: bool
    summary: dict[str, int]
    trade_stats: list[dict[str, str | bool | int | None]]


class TradeBooksService:
    """Service for trade book operations."""

    def __init__(self, data_root: Path) -> None:
        """Initialize service.

        Args:
            data_root: Root data directory
        """
        self.data_root = Path(data_root)
        self.registry = TradeBookRegistry(self.data_root)

    def list_tradebooks(self) -> list[TradeBookSummary]:
        """List all available trade books with summary info.

        Returns:
            List of trade book summaries
        """
        book_names = self.registry.list_tradebooks()
        summaries = []

        for name in book_names:
            try:
                inventory = self.registry.discover_tradebook(name)
                summaries.append(self._inventory_to_summary(inventory))
            except Exception:
                # Skip trade books that fail to load
                continue

        return summaries

    def get_tradebook(self, book_name: str) -> TradeBookDetail:
        """Get detailed information about a trade book.

        Args:
            book_name: Name of the trade book

        Returns:
            Detailed trade book information

        Raises:
            FileNotFoundError: If trade book does not exist
        """
        inventory = self.registry.discover_tradebook(book_name)
        return self._inventory_to_detail(inventory)

    def get_tradebook_dates(self, book_name: str) -> list[str]:
        """Get list of dates in a trade book.

        Args:
            book_name: Name of the trade book

        Returns:
            Sorted list of dates in YYYYMMDD format

        Raises:
            FileNotFoundError: If trade book does not exist
        """
        inventory = self.registry.discover_tradebook(book_name)
        return inventory.dates

    def compute_health(
        self, book_name: str, validate_schemas: bool = True
    ) -> TradeBookHealthResponse:
        """Compute health report for a trade book.

        Args:
            book_name: Name of the trade book
            validate_schemas: Whether to validate parquet schemas

        Returns:
            Health report

        Raises:
            FileNotFoundError: If trade book does not exist
        """
        inventory = self.registry.discover_tradebook(book_name)
        analyzer = TradeBookHealthAnalyzer(inventory)
        report = analyzer.compute_health_report(validate_schemas=validate_schemas)

        return self._health_report_to_response(report)

    def _inventory_to_summary(self, inventory: TradeBookInventory) -> TradeBookSummary:
        """Convert inventory to summary response.

        Args:
            inventory: Trade book inventory

        Returns:
            Trade book summary
        """
        return TradeBookSummary(
            name=inventory.name,
            version_id=inventory.version_id,
            dates=inventory.dates,
            total_files=inventory.total_files,
            total_trades=inventory.total_trades,
            root_path=str(inventory.root_path),
        )

    def _inventory_to_detail(self, inventory: TradeBookInventory) -> TradeBookDetail:
        """Convert inventory to detailed response.

        Args:
            inventory: Trade book inventory

        Returns:
            Trade book detail
        """
        date_files = [
            {
                "date": df.date,
                "trade_count": df.trade_count,
            }
            for df in inventory.date_files
        ]

        return TradeBookDetail(
            name=inventory.name,
            version_id=inventory.version_id,
            dates=inventory.dates,
            total_files=inventory.total_files,
            total_trades=inventory.total_trades,
            root_path=str(inventory.root_path),
            date_files=date_files,
        )

    def _health_report_to_response(
        self, report: TradeBookHealthReport
    ) -> TradeBookHealthResponse:
        """Convert health report to API response.

        Args:
            report: Trade book health report

        Returns:
            Health report response
        """
        trade_stats = [
            {
                "date": ts.date,
                "has_data": ts.has_data,
                "trade_count": ts.trade_count,
                "first_timestamp_ms": ts.first_timestamp_ms,
                "last_timestamp_ms": ts.last_timestamp_ms,
                "duration_ms": ts.duration_ms,
            }
            for ts in report.trade_stats
        ]

        return TradeBookHealthResponse(
            book_name=report.book_name,
            version_id=report.version_id,
            has_issues=report.has_issues,
            summary=report.summary,
            trade_stats=trade_stats,
        )
