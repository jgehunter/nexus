"""Dataset registry for discovering and inventorying data files.

The registry provides a unified view of available datasets, handling:
- Multi-book trades (e.g., MAD_GLD, MAD_SLV, MXN_GLD)
- Separate tick files per pair and metal type (gold/silver)
- Version ID computation for reproducibility
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pyarrow.parquet as pq

from ...util.hashing import hash_dict
from .paths import DatasetPaths


@dataclass(frozen=True)
class PairDateInventory:
    """Inventory of available data for a specific pair and date."""

    pair: str
    date: str  # YYYYMMDD format
    has_trades: bool
    has_market: bool
    trades_file: Path | None
    market_file: Path | None
    trades_row_count: int = 0
    market_row_count: int = 0


@dataclass(frozen=True)
class DatasetInventory:
    """Complete inventory of a dataset."""

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


class DatasetRegistry:
    """Registry for discovering and inventorying datasets.

    Handles the data directory structure:
        data/
        ├── datasets/
        │   └── {dataset_name}/
        │       ├── meta.json (optional)
        │       ├── trades/
        │       │   ├── MAD_GLD/
        │       │   │   └── 20240101.parquet
        │       │   ├── MAD_SLV/
        │       │   ├── MXN_GLD/
        │       │   └── ...
        │       └── market/
        │           ├── gold/
        │           │   ├── EURUSD/
        │           │   │   └── 20240101.parquet
        │           │   └── ...
        │           └── silver/
        │               └── ...
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize registry.

        Args:
            base_path: Root data directory
        """
        self.base_path = Path(base_path)
        self.datasets_dir = self.base_path / "datasets"

    def list_datasets(self) -> list[str]:
        """List all available dataset names.

        Returns:
            Sorted list of dataset directory names
        """
        if not self.datasets_dir.exists():
            return []

        datasets = []
        for d in self.datasets_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                datasets.append(d.name)

        return sorted(datasets)

    def discover_dataset(self, dataset_name: str) -> DatasetInventory:
        """Discover and inventory a dataset.

        Args:
            dataset_name: Name of the dataset to discover

        Returns:
            Complete inventory of the dataset

        Raises:
            FileNotFoundError: If dataset directory does not exist
        """
        dataset_root = self.datasets_dir / dataset_name
        if not dataset_root.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_name}")

        # Discover trades
        trades_files = self._discover_files(dataset_root / "trades", "trades")
        trades_pairs = sorted({item["pair"] for item in trades_files})

        # Discover market data (handle both gold/silver subdirs and flat structure)
        market_files = self._discover_market_files(dataset_root / "market")
        market_pairs = sorted({item["pair"] for item in market_files})

        # Combine into pair-date inventory
        all_pairs = sorted(set(trades_pairs) | set(market_pairs))
        all_dates = sorted(
            set(item["date"] for item in trades_files)
            | set(item["date"] for item in market_files)
        )

        pair_dates = self._build_pair_date_inventory(
            trades_files, market_files, all_pairs, all_dates
        )

        # Compute version ID
        version_id = self._compute_version_id(dataset_name, pair_dates)

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

    def _discover_files(
        self, base_dir: Path, data_type: Literal["trades", "market"]
    ) -> list[dict[str, str | Path]]:
        """Discover all parquet files under a base directory.

        Args:
            base_dir: Base directory to search
            data_type: Type of data being discovered

        Returns:
            List of dicts with keys: pair, date, file_path, row_count
        """
        if not base_dir.exists():
            return []

        files = []
        for pair_dir in base_dir.iterdir():
            if not pair_dir.is_dir() or pair_dir.name.startswith("."):
                continue

            pair = pair_dir.name.upper()

            for pq_file in pair_dir.glob("*.parquet"):
                date = pq_file.stem  # YYYYMMDD
                row_count = self._get_row_count(pq_file)

                files.append(
                    {
                        "pair": pair,
                        "date": date,
                        "file_path": pq_file,
                        "row_count": row_count,
                        "data_type": data_type,
                    }
                )

        return files

    def _discover_market_files(self, market_dir: Path) -> list[dict[str, str | Path]]:
        """Discover market data files, handling gold/silver subdirectories.

        Args:
            market_dir: Base market directory

        Returns:
            List of dicts with keys: pair, date, file_path, row_count
        """
        if not market_dir.exists():
            return []

        files = []

        # Check if we have gold/silver subdirectories
        gold_dir = market_dir / "gold"
        silver_dir = market_dir / "silver"

        if gold_dir.exists() or silver_dir.exists():
            # Nested structure: market/{gold,silver}/{pair}/YYYYMMDD.parquet
            for metal_dir in [gold_dir, silver_dir]:
                if metal_dir.exists():
                    files.extend(self._discover_files(metal_dir, "market"))
        else:
            # Flat structure: market/{pair}/YYYYMMDD.parquet
            files.extend(self._discover_files(market_dir, "market"))

        return files

    def _get_row_count(self, parquet_file: Path) -> int:
        """Get row count from a parquet file without reading data.

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

    def _build_pair_date_inventory(
        self,
        trades_files: list[dict[str, str | Path]],
        market_files: list[dict[str, str | Path]],
        all_pairs: list[str],
        all_dates: list[str],
    ) -> list[PairDateInventory]:
        """Build pair-date inventory from discovered files.

        Args:
            trades_files: List of trade file metadata
            market_files: List of market file metadata
            all_pairs: All pairs found
            all_dates: All dates found

        Returns:
            List of PairDateInventory objects
        """
        # Build lookup tables
        trades_lookup: dict[tuple[str, str], dict[str, str | Path]] = {}
        for item in trades_files:
            key = (str(item["pair"]), str(item["date"]))
            trades_lookup[key] = item

        market_lookup: dict[tuple[str, str], dict[str, str | Path]] = {}
        for item in market_files:
            key = (str(item["pair"]), str(item["date"]))
            market_lookup[key] = item

        # Build inventory for all pair-date combinations that exist
        inventory = []
        for pair in all_pairs:
            for date in all_dates:
                key = (pair, date)
                trades_item = trades_lookup.get(key)
                market_item = market_lookup.get(key)

                # Only include if at least one data type exists
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
                        trades_row_count=int(trades_item.get("row_count", 0))
                        if trades_item
                        else 0,
                        market_row_count=int(market_item.get("row_count", 0))
                        if market_item
                        else 0,
                    )
                )

        return inventory

    def _compute_version_id(
        self, dataset_name: str, pair_dates: list[PairDateInventory]
    ) -> str:
        """Compute deterministic version ID for a dataset.

        Version ID is based on:
        - Dataset name
        - File manifest (pair, date, has_trades, has_market, row_counts)

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
        return full_hash[:16]  # Short version ID


def get_dataset_version_id(base_path: Path, dataset_name: str) -> str:
    """Compute version ID for a dataset.

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
