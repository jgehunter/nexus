"""Dataset path resolution utilities.

Provides consistent path generation for accessing dataset files.
"""

from pathlib import Path
from typing import Literal

from ..config.defaults import Defaults


class DatasetPaths:
    """Helper for resolving paths within a dataset.

    Dataset structure:
        {base_path}/datasets/{dataset_name}/
            meta.json
            trades/{pair}/{YYYYMMDD}.parquet
            market/{pair}/{YYYYMMDD}.parquet
    """

    def __init__(self, base_path: Path, dataset_name: str) -> None:
        """Initialize dataset path resolver.

        Args:
            base_path: Root data directory (e.g., /path/to/data)
            dataset_name: Name of the dataset
        """
        self.base_path = Path(base_path)
        self.dataset_name = dataset_name
        self._root = self.base_path / "datasets" / dataset_name

    @property
    def root(self) -> Path:
        """Root directory of the dataset."""
        return self._root

    @property
    def meta_path(self) -> Path:
        """Path to the meta.json file."""
        return self._root / Defaults.META_FILENAME

    def trades_dir(self, pair: str | None = None) -> Path:
        """Path to trades directory, optionally for a specific pair.

        Args:
            pair: Currency pair (e.g., EURUSD). If None, returns base trades dir.

        Returns:
            Path to trades directory
        """
        path = self._root / Defaults.TRADES_SUBDIR
        if pair:
            path = path / pair.upper()
        return path

    def market_dir(self, pair: str | None = None) -> Path:
        """Path to market data directory, optionally for a specific pair.

        Args:
            pair: Currency pair (e.g., EURUSD). If None, returns base market dir.

        Returns:
            Path to market directory
        """
        path = self._root / Defaults.MARKET_SUBDIR
        if pair:
            path = path / pair.upper()
        return path

    def parquet_path(
        self,
        data_type: Literal["trades", "market"],
        pair: str,
        date: str,
    ) -> Path:
        """Get path to a specific parquet file.

        Args:
            data_type: Type of data ("trades" or "market")
            pair: Currency pair (e.g., EURUSD)
            date: Date string in YYYYMMDD format

        Returns:
            Full path to the parquet file
        """
        subdir = Defaults.TRADES_SUBDIR if data_type == "trades" else Defaults.MARKET_SUBDIR
        return self._root / subdir / pair.upper() / f"{date}.parquet"

    def exists(self) -> bool:
        """Check if dataset root directory exists."""
        return self._root.exists() and self._root.is_dir()

    def has_meta(self) -> bool:
        """Check if meta.json exists."""
        return self.meta_path.exists() and self.meta_path.is_file()

    def list_pairs(self, data_type: Literal["trades", "market"]) -> list[str]:
        """List all pairs available for a data type.

        Args:
            data_type: Type of data ("trades" or "market")

        Returns:
            List of pair names (directory names under trades/ or market/)
        """
        base_dir = self.trades_dir() if data_type == "trades" else self.market_dir()
        if not base_dir.exists():
            return []
        return sorted(
            d.name for d in base_dir.iterdir() if d.is_dir() and len(d.name) == 6
        )

    def list_dates(
        self,
        data_type: Literal["trades", "market"],
        pair: str,
    ) -> list[str]:
        """List all dates available for a pair.

        Args:
            data_type: Type of data ("trades" or "market")
            pair: Currency pair

        Returns:
            List of date strings (YYYYMMDD) sorted ascending
        """
        pair_dir = (
            self.trades_dir(pair) if data_type == "trades" else self.market_dir(pair)
        )
        if not pair_dir.exists():
            return []
        return sorted(
            f.stem for f in pair_dir.glob("*.parquet") if f.is_file()
        )


def get_datasets_dir(base_path: Path) -> Path:
    """Get the datasets directory.

    Args:
        base_path: Root data directory

    Returns:
        Path to datasets directory
    """
    return base_path / "datasets"


def list_datasets(base_path: Path) -> list[str]:
    """List all available datasets.

    Args:
        base_path: Root data directory

    Returns:
        List of dataset names (directory names under datasets/)
    """
    datasets_dir = get_datasets_dir(base_path)
    if not datasets_dir.exists():
        return []
    return sorted(
        d.name
        for d in datasets_dir.iterdir()
        if d.is_dir() and (d / Defaults.META_FILENAME).exists()
    )
