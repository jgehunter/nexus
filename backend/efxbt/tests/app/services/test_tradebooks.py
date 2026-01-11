"""Tests for tradebooks service layer."""

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from efxbt.app.services.tradebooks import (
    TradeBookDetail,
    TradeBookHealthResponse,
    TradeBookSummary,
    TradeBooksService,
)
from efxbt.core.data.schemas import TRADE_ARROW_SCHEMA


@pytest.fixture
def sample_data_root():
    """Create sample data root with trade books."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        tradebooks_dir = base_path / "tradebooks"

        # Create trade book 1 (MAD_GLD)
        book1_dir = tradebooks_dir / "MAD_GLD"
        book1_dir.mkdir(parents=True)

        trade_data = {
            "timestamp_ms": [1000, 2000, 3000],
            "pair": ["MAD_GLD", "MAD_GLD", "MAD_GLD"],
            "side": [1, -1, 1],
            "qty": [100.0, 200.0, 150.0],
            "price": [1.1000, 1.1005, 1.1002],
            "trade_id": ["T1", "T2", "T3"],
            "order_id": [None, None, None],
        }
        trade_table = pa.table(trade_data, schema=TRADE_ARROW_SCHEMA)
        pq.write_table(trade_table, book1_dir / "20240101.parquet")

        trade_data2 = {
            "timestamp_ms": [4000, 5000],
            "pair": ["MAD_GLD", "MAD_GLD"],
            "side": [1, -1],
            "qty": [100.0, 100.0],
            "price": [1.1010, 1.1015],
            "trade_id": ["T4", "T5"],
            "order_id": [None, None],
        }
        trade_table2 = pa.table(trade_data2, schema=TRADE_ARROW_SCHEMA)
        pq.write_table(trade_table2, book1_dir / "20240102.parquet")

        # Create trade book 2 (MAD_SLV)
        book2_dir = tradebooks_dir / "MAD_SLV"
        book2_dir.mkdir(parents=True)

        trade_data3 = {
            "timestamp_ms": [1000, 2000],
            "pair": ["MAD_SLV", "MAD_SLV"],
            "side": [1, -1],
            "qty": [50.0, 50.0],
            "price": [0.9500, 0.9505],
            "trade_id": ["T6", "T7"],
            "order_id": [None, None],
        }
        trade_table3 = pa.table(trade_data3, schema=TRADE_ARROW_SCHEMA)
        pq.write_table(trade_table3, book2_dir / "20240101.parquet")

        yield base_path


def test_list_tradebooks(sample_data_root):
    """Test listing trade books."""
    service = TradeBooksService(sample_data_root)
    books = service.list_tradebooks()

    assert len(books) == 2
    assert all(isinstance(book, TradeBookSummary) for book in books)

    names = [book.name for book in books]
    assert "MAD_GLD" in names
    assert "MAD_SLV" in names


def test_list_tradebooks_empty():
    """Test listing trade books when directory is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = TradeBooksService(Path(tmpdir))
        books = service.list_tradebooks()
        assert books == []


def test_get_tradebook(sample_data_root):
    """Test getting trade book details."""
    service = TradeBooksService(sample_data_root)
    detail = service.get_tradebook("MAD_GLD")

    assert isinstance(detail, TradeBookDetail)
    assert detail.name == "MAD_GLD"
    assert len(detail.dates) == 2
    assert len(detail.date_files) == 2
    assert detail.total_trades == 5
    assert detail.total_files == 2


def test_get_tradebook_not_found(sample_data_root):
    """Test getting non-existent trade book."""
    service = TradeBooksService(sample_data_root)

    with pytest.raises(FileNotFoundError):
        service.get_tradebook("nonexistent")


def test_get_tradebook_dates(sample_data_root):
    """Test getting trade book dates."""
    service = TradeBooksService(sample_data_root)
    dates = service.get_tradebook_dates("MAD_GLD")

    assert isinstance(dates, list)
    assert len(dates) == 2
    assert "20240101" in dates
    assert "20240102" in dates


def test_compute_health(sample_data_root):
    """Test computing health report for trade book."""
    service = TradeBooksService(sample_data_root)
    report = service.compute_health("MAD_GLD", validate_schemas=True)

    assert isinstance(report, TradeBookHealthResponse)
    assert report.book_name == "MAD_GLD"
    assert len(report.version_id) == 16
    assert isinstance(report.has_issues, bool)
    assert "total_trades" in report.summary
    assert "dates_covered" in report.summary
    assert "total_trade_files" in report.summary


def test_compute_health_no_schema_validation(sample_data_root):
    """Test computing health without schema validation."""
    service = TradeBooksService(sample_data_root)
    report = service.compute_health("MAD_GLD", validate_schemas=False)

    assert isinstance(report, TradeBookHealthResponse)
    assert report.book_name == "MAD_GLD"
    assert report.summary["total_trades"] == 5


def test_tradebook_summary_structure(sample_data_root):
    """Test trade book summary structure."""
    service = TradeBooksService(sample_data_root)
    books = service.list_tradebooks()

    summary = books[0]
    assert hasattr(summary, "name")
    assert hasattr(summary, "version_id")
    assert hasattr(summary, "dates")
    assert hasattr(summary, "total_files")
    assert hasattr(summary, "total_trades")
    assert hasattr(summary, "root_path")


def test_tradebook_detail_structure(sample_data_root):
    """Test trade book detail structure."""
    service = TradeBooksService(sample_data_root)
    detail = service.get_tradebook("MAD_GLD")

    assert hasattr(detail, "date_files")
    assert isinstance(detail.date_files, list)
    assert len(detail.date_files) > 0

    date_file = detail.date_files[0]
    assert "date" in date_file
    assert "trade_count" in date_file


def test_health_report_structure(sample_data_root):
    """Test health report response structure for trade book."""
    service = TradeBooksService(sample_data_root)
    report = service.compute_health("MAD_GLD")

    assert isinstance(report.trade_stats, list)
    assert len(report.trade_stats) > 0

    stats = report.trade_stats[0]
    assert "date" in stats
    assert "has_data" in stats
    assert "trade_count" in stats
    assert "first_timestamp_ms" in stats
    assert "last_timestamp_ms" in stats


def test_multiple_tradebooks(sample_data_root):
    """Test handling multiple trade books."""
    service = TradeBooksService(sample_data_root)

    mad_gld = service.get_tradebook("MAD_GLD")
    mad_slv = service.get_tradebook("MAD_SLV")

    assert mad_gld.name == "MAD_GLD"
    assert mad_slv.name == "MAD_SLV"
    assert mad_gld.total_trades == 5
    assert mad_slv.total_trades == 2
    assert mad_gld.version_id != mad_slv.version_id
