"""Data registry for discovering and inventorying market data and trade books.

NEW ARCHITECTURE:
- MarketDataset = Market tick data only (observable universe)
- TradeBook = Trades for a specific book (independent entity)
- Backtest Run = Combines TradeBook + MarketDataset + Config
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from ...util.hashing import hash_dict
from .paths import DatasetPaths


@dataclass(frozen=True)
class MarketPairDateInventory:
    """Inventory of market data for a specific pair and date."""

    pair: str
    date: str  # YYYYMMDD format
    file_path: Path
    row_count: int


@dataclass(frozen=True)
class TradeDateInventory:
    """Inventory of trades for a specific date in a trade book."""

    date: str  # YYYYMMDD format
    file_path: Path
    trade_count: int


# Legacy alias
TradePairDateInventory = TradeDateInventory


@dataclass(frozen=True)
class MarketDatasetInventory:
    """Inventory of a market dataset (tick data only)."""

    name: str
    root_path: Path
    pairs: list[str]  # e.g., ["EURUSD", "GBPUSD"]
    dates: list[str]  # e.g., ["20240101", "20240102"]
    pair_dates: list[MarketPairDateInventory]
    version_id: str
    total_files: int
    total_ticks: int


@dataclass(frozen=True)
class TradeBookInventory:
    """Inventory of a trade book.

    A trade book is an independent entity representing a collection of
    trades organized by date. The book name IS the entity identifier.
    """

    name: str  # e.g., "MAD_GLD" - this IS the entity
    root_path: Path
    dates: list[str]  # Dates with trades, sorted
    date_files: list[TradeDateInventory]  # Trade data per date
    version_id: str
    total_files: int
    total_trades: int


# Legacy compatibility alias
@dataclass(frozen=True)
class PairDateInventory:
    """Legacy inventory format for backward compatibility.

    DEPRECATED: Use MarketPairDateInventory or TradePairDateInventory instead.
    """

    pair: str
    date: str
    has_trades: bool
    has_market: bool
    trades_file: Path | None
    market_file: Path | None
    trades_row_count: int = 0
    market_row_count: int = 0


@dataclass(frozen=True)
class DatasetInventory:
    """Legacy dataset inventory format for backward compatibility.

    DEPRECATED: Use MarketDatasetInventory for market data or
    TradeBookInventory for trade books.
    """

    name: str
    root_path: Path
    pairs: list[str]
    dates: list[str]
    trades_pairs: list[str]
    market_pairs: list[str]
    pair_dates: list[PairDateInventory]
    version_id: str
    total_trades_files: int
    total_market_files: int


class MarketDatasetRegistry:
    """Registry for discovering market datasets (tick data).

    Directory structure:
        data/
        └── datasets/
            └── {dataset_name}/
                └── market/
                    ├── EURUSD/
                    │   ├── 20240101.parquet
                    │   └── 20240102.parquet
                    └── GBPUSD/
                        └── 20240101.parquet
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize registry.

        Args:
            base_path: Root data directory
        """
        self.base_path = Path(base_path)
        self.datasets_dir = self.base_path / "datasets"

    def list_datasets(self) -> list[str]:
        """List all available market dataset names.

        Returns:
            Sorted list of dataset directory names
        """
        if not self.datasets_dir.exists():
            return []

        datasets = []
        for d in self.datasets_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                # Check if it has a market directory
                if (d / "market").exists():
                    datasets.append(d.name)

        return sorted(datasets)

    def discover_dataset(self, dataset_name: str) -> MarketDatasetInventory:
        """Discover and inventory a market dataset.

        Args:
            dataset_name: Name of the dataset to discover

        Returns:
            Complete inventory of the market dataset

        Raises:
            FileNotFoundError: If dataset directory does not exist
        """
        dataset_root = self.datasets_dir / dataset_name
        if not dataset_root.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_name}")

        market_dir = dataset_root / "market"
        if not market_dir.exists():
            raise FileNotFoundError(f"No market data found in dataset: {dataset_name}")

        # Discover market files (handle both nested and flat structure)
        market_files = self._discover_market_files(market_dir)

        pairs = sorted({item.pair for item in market_files})
        dates = sorted({item.date for item in market_files})
        total_ticks = sum(item.row_count for item in market_files)

        # Compute version ID
        version_id = self._compute_version_id(dataset_name, market_files)

        return MarketDatasetInventory(
            name=dataset_name,
            root_path=dataset_root,
            pairs=pairs,
            dates=dates,
            pair_dates=market_files,
            version_id=version_id,
            total_files=len(market_files),
            total_ticks=total_ticks,
        )

    def _discover_market_files(self, market_dir: Path) -> list[MarketPairDateInventory]:
        """Discover market data files, handling gold/silver subdirectories.

        Args:
            market_dir: Base market directory

        Returns:
            List of MarketPairDateInventory objects
        """
        files = []

        # Check for nested structure (gold/silver subdirs)
        gold_dir = market_dir / "gold"
        silver_dir = market_dir / "silver"

        if gold_dir.exists() or silver_dir.exists():
            # Nested: market/{gold,silver}/{pair}/YYYYMMDD.parquet
            for metal_dir in [gold_dir, silver_dir]:
                if metal_dir.exists():
                    files.extend(self._discover_files_in_dir(metal_dir))
        else:
            # Flat: market/{pair}/YYYYMMDD.parquet
            files.extend(self._discover_files_in_dir(market_dir))

        return files

    def _discover_files_in_dir(self, base_dir: Path) -> list[MarketPairDateInventory]:
        """Discover parquet files in a directory structure.

        Args:
            base_dir: Base directory to search

        Returns:
            List of MarketPairDateInventory objects
        """
        files = []

        for pair_dir in base_dir.iterdir():
            if not pair_dir.is_dir() or pair_dir.name.startswith("."):
                continue

            pair = pair_dir.name.upper()

            for pq_file in pair_dir.glob("*.parquet"):
                date = pq_file.stem  # YYYYMMDD
                row_count = self._get_row_count(pq_file)

                files.append(
                    MarketPairDateInventory(
                        pair=pair,
                        date=date,
                        file_path=pq_file,
                        row_count=row_count,
                    )
                )

        return files

    def _get_row_count(self, parquet_file: Path) -> int:
        """Get row count from a parquet file.

        Args:
            parquet_file: Path to parquet file

        Returns:
            Number of rows, or 0 if file cannot be read
        """
        try:
            pq_file = pq.ParquetFile(parquet_file)
            return pq_file.metadata.num_rows
        except Exception:
            return 0

    def _compute_version_id(
        self, dataset_name: str, pair_dates: list[MarketPairDateInventory]
    ) -> str:
        """Compute deterministic version ID for a dataset.

        Args:
            dataset_name: Name of the dataset
            pair_dates: Pair-date inventory

        Returns:
            SHA-256 hex digest (first 16 chars)
        """
        manifest = {
            "dataset_name": dataset_name,
            "files": [
                {
                    "pair": pd.pair,
                    "date": pd.date,
                    "rows": pd.row_count,
                }
                for pd in sorted(pair_dates, key=lambda x: (x.pair, x.date))
            ],
        }

        full_hash = hash_dict(manifest)
        return full_hash[:16]


class TradeBookRegistry:
    """Registry for discovering trade books.

    Directory structure:
        data/
        └── tradebooks/
            └── {book_name}/
                ├── 20240101.parquet
                ├── 20240102.parquet
                └── metadata.json (optional)
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize registry.

        Args:
            base_path: Root data directory
        """
        self.base_path = Path(base_path)
        self.tradebooks_dir = self.base_path / "tradebooks"

    def list_tradebooks(self) -> list[str]:
        """List all available trade book names.

        Returns:
            Sorted list of trade book directory names
        """
        if not self.tradebooks_dir.exists():
            return []

        books = []
        for d in self.tradebooks_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                books.append(d.name)

        return sorted(books)

    def discover_tradebook(self, book_name: str) -> TradeBookInventory:
        """Discover and inventory a trade book.

        Args:
            book_name: Name of the trade book to discover

        Returns:
            Complete inventory of the trade book

        Raises:
            FileNotFoundError: If trade book directory does not exist
        """
        book_root = self.tradebooks_dir / book_name
        if not book_root.exists():
            raise FileNotFoundError(f"Trade book not found: {book_name}")

        # Discover trade files
        date_files = self._discover_trade_files(book_root)

        if not date_files:
            raise FileNotFoundError(f"No trade files found in book: {book_name}")

        dates = sorted({item.date for item in date_files})
        total_trades = sum(item.trade_count for item in date_files)

        # Compute version ID
        version_id = self._compute_version_id(book_name, date_files)

        return TradeBookInventory(
            name=book_name,
            root_path=book_root,
            dates=dates,
            date_files=date_files,
            version_id=version_id,
            total_files=len(date_files),
            total_trades=total_trades,
        )

    def _discover_trade_files(self, book_dir: Path) -> list[TradeDateInventory]:
        """Discover trade files in a book directory.

        Args:
            book_dir: Trade book directory

        Returns:
            List of TradeDateInventory objects
        """
        files = []

        for pq_file in book_dir.glob("*.parquet"):
            date = pq_file.stem  # YYYYMMDD
            trade_count = self._get_row_count(pq_file)

            files.append(
                TradeDateInventory(
                    date=date,
                    file_path=pq_file,
                    trade_count=trade_count,
                )
            )

        return files

    def _get_row_count(self, parquet_file: Path) -> int:
        """Get row count from a parquet file.

        Args:
            parquet_file: Path to parquet file

        Returns:
            Number of rows, or 0 if file cannot be read
        """
        try:
            pq_file = pq.ParquetFile(parquet_file)
            return pq_file.metadata.num_rows
        except Exception:
            return 0

    def _compute_version_id(
        self, book_name: str, date_files: list[TradeDateInventory]
    ) -> str:
        """Compute deterministic version ID for a trade book.

        Args:
            book_name: Name of the trade book
            date_files: Date-file inventory

        Returns:
            SHA-256 hex digest (first 16 chars)
        """
        manifest = {
            "book_name": book_name,
            "files": [
                {
                    "date": df.date,
                    "trades": df.trade_count,
                }
                for df in sorted(date_files, key=lambda x: x.date)
            ],
        }

        full_hash = hash_dict(manifest)
        return full_hash[:16]


# Legacy compatibility class
class DatasetRegistry(MarketDatasetRegistry):
    """Legacy DatasetRegistry for backward compatibility.

    DEPRECATED: Use MarketDatasetRegistry or TradeBookRegistry instead.

    This class attempts to maintain the old API while using the new architecture.
    It discovers both market data and trade books from the old structure where
    they were combined.
    """

    def discover_dataset(self, dataset_name: str) -> DatasetInventory:
        """Discover dataset in legacy format (trades + market combined).

        Args:
            dataset_name: Name of the dataset to discover

        Returns:
            Legacy DatasetInventory

        Raises:
            FileNotFoundError: If dataset directory does not exist
        """
        dataset_root = self.datasets_dir / dataset_name
        if not dataset_root.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_name}")

        # Discover trades (legacy location: dataset/trades/)
        trades_files = self._discover_legacy_trades(dataset_root / "trades")
        trades_pairs = sorted({item["pair"] for item in trades_files})

        # Discover market data (legacy location: dataset/market/)
        market_dir = dataset_root / "market"
        market_files_inv = []
        if market_dir.exists():
            market_files_inv = self._discover_market_files(market_dir)

        market_files = [
            {
                "pair": mf.pair,
                "date": mf.date,
                "file_path": mf.file_path,
                "row_count": mf.row_count,
            }
            for mf in market_files_inv
        ]
        market_pairs = sorted({item["pair"] for item in market_files})

        # Combine
        all_pairs = sorted(set(trades_pairs) | set(market_pairs))
        all_dates = sorted(
            set(item["date"] for item in trades_files)
            | set(item["date"] for item in market_files)
        )

        pair_dates = self._build_legacy_pair_date_inventory(
            trades_files, market_files, all_pairs, all_dates
        )

        # Compute version ID
        version_id = self._compute_legacy_version_id(dataset_name, pair_dates)

        return DatasetInventory(
            name=dataset_name,
            root_path=dataset_root,
            pairs=all_pairs,
            dates=all_dates,
            trades_pairs=trades_pairs,
            market_pairs=market_pairs,
            pair_dates=pair_dates,
            version_id=version_id,
            total_trades_files=len(trades_files),
            total_market_files=len(market_files),
        )

    def _discover_legacy_trades(self, trades_dir: Path) -> list[dict]:
        """Discover trades in legacy format (trades/{book}/{pair}/YYYYMMDD.parquet).

        Args:
            trades_dir: Base trades directory

        Returns:
            List of dicts with trade file metadata
        """
        if not trades_dir.exists():
            return []

        files = []
        for book_dir in trades_dir.iterdir():
            if not book_dir.is_dir() or book_dir.name.startswith("."):
                continue

            # In legacy format, book name is the "pair"
            pair = book_dir.name.upper()

            for pq_file in book_dir.glob("*.parquet"):
                date = pq_file.stem
                row_count = self._get_row_count(pq_file)

                files.append(
                    {
                        "pair": pair,
                        "date": date,
                        "file_path": pq_file,
                        "row_count": row_count,
                    }
                )

        return files

    def _build_legacy_pair_date_inventory(
        self,
        trades_files: list[dict],
        market_files: list[dict],
        all_pairs: list[str],
        all_dates: list[str],
    ) -> list[PairDateInventory]:
        """Build legacy pair-date inventory.

        Args:
            trades_files: List of trade file metadata
            market_files: List of market file metadata
            all_pairs: All pairs found
            all_dates: All dates found

        Returns:
            List of PairDateInventory objects
        """
        # Build lookup tables
        trades_lookup: dict[tuple[str, str], dict] = {}
        for item in trades_files:
            key = (str(item["pair"]), str(item["date"]))
            trades_lookup[key] = item

        market_lookup: dict[tuple[str, str], dict] = {}
        for item in market_files:
            key = (str(item["pair"]), str(item["date"]))
            market_lookup[key] = item

        # Build inventory
        inventory = []
        for pair in all_pairs:
            for date in all_dates:
                key = (pair, date)
                trades_item = trades_lookup.get(key)
                market_item = market_lookup.get(key)

                # Only include if at least one exists
                if trades_item is None and market_item is None:
                    continue

                inventory.append(
                    PairDateInventory(
                        pair=pair,
                        date=date,
                        has_trades=trades_item is not None,
                        has_market=market_item is not None,
                        trades_file=trades_item["file_path"] if trades_item else None,
                        market_file=market_item["file_path"] if market_item else None,
                        trades_row_count=(
                            int(trades_item.get("row_count", 0)) if trades_item else 0
                        ),
                        market_row_count=(
                            int(market_item.get("row_count", 0)) if market_item else 0
                        ),
                    )
                )

        return inventory

    def _compute_legacy_version_id(
        self, dataset_name: str, pair_dates: list[PairDateInventory]
    ) -> str:
        """Compute version ID in legacy format.

        Args:
            dataset_name: Name of the dataset
            pair_dates: Pair-date inventory

        Returns:
            SHA-256 hex digest (first 16 chars)
        """
        manifest = {
            "dataset_name": dataset_name,
            "files": [
                {
                    "pair": pd.pair,
                    "date": pd.date,
                    "has_trades": pd.has_trades,
                    "has_market": pd.has_market,
                    "trades_rows": pd.trades_row_count,
                    "market_rows": pd.market_row_count,
                }
                for pd in sorted(pair_dates, key=lambda x: (x.pair, x.date))
            ],
        }

        full_hash = hash_dict(manifest)
        return full_hash[:16]


def get_dataset_version_id(base_path: Path, dataset_name: str) -> str:
    """Compute version ID for a dataset (legacy compatibility).

    Args:
        base_path: Root data directory
        dataset_name: Name of the dataset

    Returns:
        Version ID (16-char hex string)

    Raises:
        FileNotFoundError: If dataset does not exist
    """
    registry = DatasetRegistry(base_path)
    inventory = registry.discover_dataset(dataset_name)
    return inventory.version_id
