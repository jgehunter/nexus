"""Tests for datasets service layer."""

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from efxbt.app.services.datasets import (
    DatasetDetail,
    DatasetSummary,
    DatasetsService,
    HealthReportResponse,
)
from efxbt.core.data.schemas import MARKET_ARROW_SCHEMA, TRADE_ARROW_SCHEMA


@pytest.fixture
def sample_data_root():
    """Create sample data root with datasets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        datasets_dir = base_path / "datasets"

        # Create dataset 1
        ds1_dir = datasets_dir / "ds1"
        ds1_dir.mkdir(parents=True)

        trades_dir = ds1_dir / "trades" / "MAD_GLD"
        trades_dir.mkdir(parents=True)

        trade_data = {
            "timestamp_ms": [1000, 2000],
            "pair": ["EURUSD", "EURUSD"],
            "side": [1, -1],
            "qty": [100.0, 200.0],
            "price": [1.1000, 1.1005],
            "trade_id": ["T1", "T2"],
            "order_id": [None, None],
        }
        trade_table = pa.table(trade_data, schema=TRADE_ARROW_SCHEMA)
        pq.write_table(trade_table, trades_dir / "20240101.parquet")

        market_dir = ds1_dir / "market" / "EURUSD"
        market_dir.mkdir(parents=True)

        market_data = {
            "timestamp_ms": [1000, 2000],
            "pair": ["EURUSD", "EURUSD"],
            "bid_tob": [1.0999, 1.1000],
            "ask_tob": [1.1001, 1.1002],
            "bid_qty_tob": [1000.0, 1000.0],
            "ask_qty_tob": [1000.0, 1000.0],
            "bid_rungs_qty": [None, None],
            "bid_rungs_price": [None, None],
            "ask_rungs_qty": [None, None],
            "ask_rungs_price": [None, None],
        }
        market_table = pa.table(market_data, schema=MARKET_ARROW_SCHEMA)
        pq.write_table(market_table, market_dir / "20240101.parquet")

        # Create dataset 2
        ds2_dir = datasets_dir / "ds2"
        ds2_dir.mkdir(parents=True)

        trades_dir2 = ds2_dir / "trades" / "MXN_GLD"
        trades_dir2.mkdir(parents=True)
        pq.write_table(trade_table, trades_dir2 / "20240101.parquet")

        yield base_path


def test_list_datasets(sample_data_root):
    """Test listing market datasets."""
    service = DatasetsService(sample_data_root)
    datasets = service.list_datasets()

    # Only ds1 has market data (ds2 only has trades)
    assert len(datasets) == 1
    assert all(isinstance(ds, DatasetSummary) for ds in datasets)

    names = [ds.name for ds in datasets]
    assert "ds1" in names


def test_list_datasets_empty():
    """Test listing datasets when directory is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = DatasetsService(Path(tmpdir))
        datasets = service.list_datasets()
        assert datasets == []


def test_get_dataset(sample_data_root):
    """Test getting dataset details."""
    service = DatasetsService(sample_data_root)
    detail = service.get_dataset("ds1")

    assert isinstance(detail, DatasetDetail)
    assert detail.name == "ds1"
    assert len(detail.pairs) > 0
    assert len(detail.dates) > 0
    assert len(detail.pair_dates) > 0


def test_get_dataset_not_found(sample_data_root):
    """Test getting non-existent dataset."""
    service = DatasetsService(sample_data_root)

    with pytest.raises(FileNotFoundError):
        service.get_dataset("nonexistent")


def test_get_dataset_pairs(sample_data_root):
    """Test getting dataset pairs."""
    service = DatasetsService(sample_data_root)
    pairs = service.get_dataset_pairs("ds1")

    assert isinstance(pairs, list)
    assert len(pairs) > 0
    assert all(isinstance(p, str) for p in pairs)


def test_get_dataset_dates(sample_data_root):
    """Test getting dataset dates."""
    service = DatasetsService(sample_data_root)
    dates = service.get_dataset_dates("ds1")

    assert isinstance(dates, list)
    assert len(dates) > 0
    assert "20240101" in dates


def test_compute_health(sample_data_root):
    """Test computing health report for market data."""
    service = DatasetsService(sample_data_root)
    report = service.compute_health("ds1", validate_schemas=True)

    assert isinstance(report, HealthReportResponse)
    assert report.dataset_name == "ds1"
    assert len(report.version_id) == 16
    assert isinstance(report.has_issues, bool)
    assert "total_ticks" in report.summary
    assert "pairs_covered" in report.summary
    # Market datasets don't have trade data
    assert "total_trades" not in report.summary


def test_compute_health_no_schema_validation(sample_data_root):
    """Test computing health without schema validation."""
    service = DatasetsService(sample_data_root)
    report = service.compute_health("ds1", validate_schemas=False)

    assert isinstance(report, HealthReportResponse)
    assert report.dataset_name == "ds1"


def test_dataset_summary_structure(sample_data_root):
    """Test market dataset summary structure."""
    service = DatasetsService(sample_data_root)
    datasets = service.list_datasets()

    summary = datasets[0]
    assert hasattr(summary, "name")
    assert hasattr(summary, "version_id")
    assert hasattr(summary, "pairs")
    assert hasattr(summary, "dates")
    assert hasattr(summary, "total_files")
    assert hasattr(summary, "total_ticks")
    assert hasattr(summary, "root_path")
    # Market datasets don't have trade-specific fields
    assert not hasattr(summary, "trades_pairs")
    assert not hasattr(summary, "market_pairs")
    assert not hasattr(summary, "total_trades_files")


def test_dataset_detail_structure(sample_data_root):
    """Test market dataset detail structure."""
    service = DatasetsService(sample_data_root)
    detail = service.get_dataset("ds1")

    assert hasattr(detail, "pair_dates")
    assert isinstance(detail.pair_dates, list)
    assert len(detail.pair_dates) > 0

    pair_date = detail.pair_dates[0]
    assert "pair" in pair_date
    assert "date" in pair_date
    assert "row_count" in pair_date
    # Market datasets don't have trade-specific fields
    assert "has_trades" not in pair_date
    assert "has_market" not in pair_date
    assert "trades_row_count" not in pair_date


def test_health_report_structure(sample_data_root):
    """Test health report response structure for market data."""
    service = DatasetsService(sample_data_root)
    report = service.compute_health("ds1")

    assert isinstance(report.tick_coverage, list)
    # Market datasets don't have trade_coverage
    assert not hasattr(report, "trade_coverage")

    if len(report.tick_coverage) > 0:
        tick = report.tick_coverage[0]
        assert "pair" in tick
        assert "date" in tick
        assert "has_data" in tick
        assert "tick_count" in tick
        assert "gaps_over_1min" in tick
        assert "gaps_over_5min" in tick
        assert "gaps_over_15min" in tick
