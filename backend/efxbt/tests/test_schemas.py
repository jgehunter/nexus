"""Tests for data schemas."""

import pytest
from pydantic import ValidationError

from efxbt.core.data.schemas import (
    TradeRecord,
    MarketTickRecord,
    DatasetMeta,
    compute_ref_mid,
)


class TestTradeRecord:
    """Tests for TradeRecord schema."""

    def test_valid_trade(self) -> None:
        """Valid trade record is accepted."""
        trade = TradeRecord(
            timestamp_ms=1704067200000,
            pair="EURUSD",
            side=1,
            qty=1000000.0,
            price=1.10250,
            trade_id="T001",
        )
        assert trade.pair == "EURUSD"
        assert trade.side == 1
        assert trade.qty == 1000000.0

    def test_pair_normalized_to_uppercase(self) -> None:
        """Pair is normalized to uppercase."""
        trade = TradeRecord(
            timestamp_ms=1704067200000,
            pair="eurusd",
            side=1,
            qty=1000000.0,
            price=1.10250,
            trade_id="T001",
        )
        assert trade.pair == "EURUSD"

    def test_invalid_pair_format_rejected(self) -> None:
        """Invalid pair format raises ValidationError."""
        with pytest.raises(ValidationError):
            TradeRecord(
                timestamp_ms=1704067200000,
                pair="EUR/USD",
                side=1,
                qty=1000000.0,
                price=1.10250,
                trade_id="T001",
            )

    def test_invalid_side_rejected(self) -> None:
        """Invalid side value raises ValidationError."""
        with pytest.raises(ValidationError):
            TradeRecord(
                timestamp_ms=1704067200000,
                pair="EURUSD",
                side=0,  # Invalid: must be 1 or -1
                qty=1000000.0,
                price=1.10250,
                trade_id="T001",
            )

    def test_negative_qty_rejected(self) -> None:
        """Negative quantity raises ValidationError."""
        with pytest.raises(ValidationError):
            TradeRecord(
                timestamp_ms=1704067200000,
                pair="EURUSD",
                side=1,
                qty=-1000000.0,
                price=1.10250,
                trade_id="T001",
            )

    def test_zero_qty_rejected(self) -> None:
        """Zero quantity raises ValidationError."""
        with pytest.raises(ValidationError):
            TradeRecord(
                timestamp_ms=1704067200000,
                pair="EURUSD",
                side=1,
                qty=0,
                price=1.10250,
                trade_id="T001",
            )


class TestMarketTickRecord:
    """Tests for MarketTickRecord schema."""

    def test_valid_tick(self) -> None:
        """Valid market tick is accepted."""
        tick = MarketTickRecord(
            timestamp_ms=1704067200000,
            pair="EURUSD",
            bid_tob=1.10248,
            ask_tob=1.10252,
            bid_qty_tob=5000000.0,
            ask_qty_tob=3000000.0,
        )
        assert tick.pair == "EURUSD"
        assert tick.bid_tob == 1.10248

    def test_mid_property(self) -> None:
        """Mid property computes correctly."""
        tick = MarketTickRecord(
            timestamp_ms=1704067200000,
            pair="EURUSD",
            bid_tob=1.10248,
            ask_tob=1.10252,
            bid_qty_tob=5000000.0,
            ask_qty_tob=3000000.0,
        )
        assert tick.mid == pytest.approx(1.10250, rel=1e-6)

    def test_spread_property(self) -> None:
        """Spread property computes correctly."""
        tick = MarketTickRecord(
            timestamp_ms=1704067200000,
            pair="EURUSD",
            bid_tob=1.10248,
            ask_tob=1.10252,
            bid_qty_tob=5000000.0,
            ask_qty_tob=3000000.0,
        )
        assert tick.spread == pytest.approx(0.00004, rel=1e-6)

    def test_optional_rungs(self) -> None:
        """Optional rung data is accepted."""
        tick = MarketTickRecord(
            timestamp_ms=1704067200000,
            pair="EURUSD",
            bid_tob=1.10248,
            ask_tob=1.10252,
            bid_qty_tob=5000000.0,
            ask_qty_tob=3000000.0,
            bid_rungs_qty=[5000000.0, 10000000.0, 20000000.0],
            bid_rungs_price=[1.10248, 1.10246, 1.10244],
            ask_rungs_qty=[3000000.0, 8000000.0, 15000000.0],
            ask_rungs_price=[1.10252, 1.10254, 1.10256],
        )
        assert tick.bid_rungs_qty is not None
        assert len(tick.bid_rungs_qty) == 3


class TestDatasetMeta:
    """Tests for DatasetMeta schema."""

    def test_valid_meta(self) -> None:
        """Valid dataset metadata is accepted."""
        meta = DatasetMeta(
            name="test_dataset",
            pairs=["EURUSD", "USDJPY"],
            start_date="2024-01-01",
            end_date="2024-12-31",
            created_at_ms=1704067200000,
        )
        assert meta.name == "test_dataset"
        assert len(meta.pairs) == 2

    def test_pairs_normalized_to_uppercase(self) -> None:
        """Pairs are normalized to uppercase."""
        meta = DatasetMeta(
            name="test_dataset",
            pairs=["eurusd", "usdjpy"],
            start_date="2024-01-01",
            end_date="2024-12-31",
            created_at_ms=1704067200000,
        )
        assert meta.pairs == ["EURUSD", "USDJPY"]

    def test_invalid_date_format_rejected(self) -> None:
        """Invalid date format raises ValidationError."""
        with pytest.raises(ValidationError):
            DatasetMeta(
                name="test_dataset",
                pairs=["EURUSD"],
                start_date="01-01-2024",  # Wrong format
                end_date="2024-12-31",
                created_at_ms=1704067200000,
            )

    def test_empty_pairs_rejected(self) -> None:
        """Empty pairs list raises ValidationError."""
        with pytest.raises(ValidationError):
            DatasetMeta(
                name="test_dataset",
                pairs=[],
                start_date="2024-01-01",
                end_date="2024-12-31",
                created_at_ms=1704067200000,
            )


class TestComputeRefMid:
    """Tests for compute_ref_mid utility function."""

    def test_compute_ref_mid(self) -> None:
        """Reference mid computes correctly."""
        mid = compute_ref_mid(1.10248, 1.10252)
        assert mid == pytest.approx(1.10250, rel=1e-6)

    def test_compute_ref_mid_symmetric(self) -> None:
        """Reference mid is symmetric to argument order."""
        mid1 = compute_ref_mid(1.10248, 1.10252)
        mid2 = compute_ref_mid(1.10252, 1.10248)
        assert mid1 == mid2
