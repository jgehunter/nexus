"""Tests for dataset registry."""

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from efxbt.core.data.registry import (
    DatasetInventory,
    DatasetRegistry,
    PairDateInventory,
    get_dataset_version_id,
)
from efxbt.core.data.schemas import MARKET_ARROW_SCHEMA, TRADE_ARROW_SCHEMA


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory with sample datasets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        datasets_dir = base_path / "datasets"
        datasets_dir.mkdir()

        # Create test dataset 1: simple flat structure
        ds1_dir = datasets_dir / "test_ds1"
        ds1_dir.mkdir()

        # Trades for MAD_GLD
        trades_dir = ds1_dir / "trades" / "MAD_GLD"
        trades_dir.mkdir(parents=True)

        trade_data = {
            "timestamp_ms": [1000, 2000, 3000],
            "pair": ["EURUSD", "EURUSD", "EURUSD"],
            "side": [1, -1, 1],
            "qty": [100.0, 200.0, 150.0],
            "price": [1.1000, 1.1005, 1.1002],
            "trade_id": ["T1", "T2", "T3"],
            "order_id": [None, None, None],
        }
        trade_table = pa.table(trade_data, schema=TRADE_ARROW_SCHEMA)
        pq.write_table(trade_table, trades_dir / "20240101.parquet")

        # Market data for EURUSD in gold subdirectory
        market_dir = ds1_dir / "market" / "gold" / "EURUSD"
        market_dir.mkdir(parents=True)

        market_data = {
            "timestamp_ms": [1000, 2000, 3000, 4000],
            "pair": ["EURUSD", "EURUSD", "EURUSD", "EURUSD"],
            "bid_tob": [1.0999, 1.1000, 1.1001, 1.1000],
            "ask_tob": [1.1001, 1.1002, 1.1003, 1.1002],
            "bid_qty_tob": [1000.0, 1000.0, 1000.0, 1000.0],
            "ask_qty_tob": [1000.0, 1000.0, 1000.0, 1000.0],
            "bid_rungs_qty": [None, None, None, None],
            "bid_rungs_price": [None, None, None, None],
            "ask_rungs_qty": [None, None, None, None],
            "ask_rungs_price": [None, None, None, None],
        }
        market_table = pa.table(market_data, schema=MARKET_ARROW_SCHEMA)
        pq.write_table(market_table, market_dir / "20240101.parquet")
        pq.write_table(market_table, market_dir / "20240102.parquet")

        # Create test dataset 2: multiple books and pairs
        ds2_dir = datasets_dir / "test_ds2"
        ds2_dir.mkdir()

        # Trades for multiple books
        for book in ["MAD_GLD", "MAD_SLV", "MXN_GLD"]:
            book_dir = ds2_dir / "trades" / book
            book_dir.mkdir(parents=True)
            pq.write_table(trade_table, book_dir / "20240101.parquet")

        # Market data flat structure
        for pair in ["EURUSD", "GBPUSD"]:
            market_pair_dir = ds2_dir / "market" / pair
            market_pair_dir.mkdir(parents=True)
            pq.write_table(market_table, market_pair_dir / "20240101.parquet")

        yield base_path


def test_list_datasets(temp_data_dir):
    """Test listing available datasets."""
    registry = DatasetRegistry(temp_data_dir)
    datasets = registry.list_datasets()

    assert len(datasets) == 2
    assert "test_ds1" in datasets
    assert "test_ds2" in datasets
    assert datasets == sorted(datasets)


def test_list_datasets_empty():
    """Test listing datasets when directory doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = DatasetRegistry(Path(tmpdir) / "nonexistent")
        datasets = registry.list_datasets()
        assert datasets == []


def test_discover_dataset_simple(temp_data_dir):
    """Test discovering a simple dataset."""
    registry = DatasetRegistry(temp_data_dir)
    inventory = registry.discover_dataset("test_ds1")

    assert inventory.name == "test_ds1"
    assert len(inventory.pairs) > 0
    assert "MAD_GLD" in inventory.trades_pairs
    assert "EURUSD" in inventory.market_pairs
    assert len(inventory.dates) == 2  # 20240101 and 20240102
    assert "20240101" in inventory.dates
    assert "20240102" in inventory.dates


def test_discover_dataset_multibook(temp_data_dir):
    """Test discovering dataset with multiple books."""
    registry = DatasetRegistry(temp_data_dir)
    inventory = registry.discover_dataset("test_ds2")

    assert inventory.name == "test_ds2"
    assert "MAD_GLD" in inventory.trades_pairs
    assert "MAD_SLV" in inventory.trades_pairs
    assert "MXN_GLD" in inventory.trades_pairs
    assert "EURUSD" in inventory.market_pairs
    assert "GBPUSD" in inventory.market_pairs


def test_discover_dataset_not_found(temp_data_dir):
    """Test discovering non-existent dataset."""
    registry = DatasetRegistry(temp_data_dir)

    with pytest.raises(FileNotFoundError):
        registry.discover_dataset("nonexistent")


def test_pair_date_inventory(temp_data_dir):
    """Test pair-date inventory structure."""
    registry = DatasetRegistry(temp_data_dir)
    inventory = registry.discover_dataset("test_ds1")

    # Check that we have pair-date entries
    assert len(inventory.pair_dates) > 0

    # Find EURUSD entry
    eurusd_entries = [pd for pd in inventory.pair_dates if pd.pair == "EURUSD"]
    assert len(eurusd_entries) == 2  # Two dates

    # Check structure
    entry = eurusd_entries[0]
    assert isinstance(entry, PairDateInventory)
    assert entry.pair == "EURUSD"
    assert entry.date in ["20240101", "20240102"]
    assert entry.has_market
    assert entry.market_file is not None
    assert entry.market_row_count > 0


def test_version_id_deterministic(temp_data_dir):
    """Test that version IDs are deterministic."""
    registry = DatasetRegistry(temp_data_dir)

    inventory1 = registry.discover_dataset("test_ds1")
    inventory2 = registry.discover_dataset("test_ds1")

    assert inventory1.version_id == inventory2.version_id
    assert len(inventory1.version_id) == 16  # Short hash


def test_version_id_different_datasets(temp_data_dir):
    """Test that different datasets have different version IDs."""
    registry = DatasetRegistry(temp_data_dir)

    inventory1 = registry.discover_dataset("test_ds1")
    inventory2 = registry.discover_dataset("test_ds2")

    assert inventory1.version_id != inventory2.version_id


def test_get_dataset_version_id(temp_data_dir):
    """Test convenience function for getting version ID."""
    version_id = get_dataset_version_id(temp_data_dir, "test_ds1")

    assert len(version_id) == 16
    assert isinstance(version_id, str)


def test_file_counts(temp_data_dir):
    """Test file count tracking."""
    registry = DatasetRegistry(temp_data_dir)
    inventory = registry.discover_dataset("test_ds1")

    assert inventory.total_trades_files == 1
    assert inventory.total_market_files == 2  # Two dates


def test_row_counts(temp_data_dir):
    """Test row count extraction from parquet metadata."""
    registry = DatasetRegistry(temp_data_dir)
    inventory = registry.discover_dataset("test_ds1")

    # Find an entry with market data
    market_entries = [pd for pd in inventory.pair_dates if pd.has_market]
    assert len(market_entries) > 0

    entry = market_entries[0]
    assert entry.market_row_count > 0  # Should have detected rows
