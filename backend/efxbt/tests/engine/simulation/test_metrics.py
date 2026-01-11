"""Unit tests for metrics calculator.

Tests internalization, time-to-close, and PnL breakdown calculations.
"""

import pytest

from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.shard.state import FIFOSlice, PnLAttributionRecord, TradePnLAttribution
from efxbt.engine.simulation.metrics import MetricsCalculator


def create_test_trade(
    source_trade_id: str,
    timestamp_ms: int,
    side: int,
    qty: float,
    price: float,
    pair: str = "EURUSD",
) -> DecrossedTradeRecord:
    """Helper to create DecrossedTradeRecord for testing."""
    return DecrossedTradeRecord(
        trade_id=f"trade_{source_trade_id}",
        source_trade_id=source_trade_id,
        order_id=f"order_{source_trade_id}",
        timestamp_ms=timestamp_ms,
        pair=pair,
        source_pair=pair,
        side=side,
        qty=qty,
        price=price,
        source_price=price,
        is_direct=True,
        path=["EUR", "USD"] if pair == "EURUSD" else [pair[:3], pair[3:]],
        leg_index=0,
        leg_count=1,
    )


class TestCalculateInternalization:
    """Test internalization metrics calculation."""

    def test_full_internalization(self):
        """Test case where all volume is internalized (no hedges)."""
        client_trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),
            create_test_trade("T002", 1704110460000, -1, 800.0, 1.0995),
        ]

        hedge_trades = []  # No hedges

        metrics = MetricsCalculator.calculate_internalization(
            client_trades, hedge_trades
        )

        assert abs(metrics["total_client_volume"] - 1800.0) < 1e-8
        assert abs(metrics["internalized_volume"] - 1800.0) < 1e-8
        assert abs(metrics["externalized_volume"]) < 1e-8
        assert abs(metrics["internalization_ratio"] - 1.0) < 1e-8  # 100%

    def test_partial_internalization(self):
        """Test case with partial internalization."""
        client_trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),
            create_test_trade("T002", 1704110460000, 1, 500.0, 1.1010),
        ]

        # Hedge to flatten +1500 position
        hedge_trades = [{"qty": 1500.0}]

        metrics = MetricsCalculator.calculate_internalization(
            client_trades, hedge_trades
        )

        assert abs(metrics["total_client_volume"] - 1500.0) < 1e-8
        assert abs(metrics["internalized_volume"]) < 1e-8  # All externalized
        assert abs(metrics["externalized_volume"] - 1500.0) < 1e-8
        assert abs(metrics["internalization_ratio"]) < 1e-8  # 0%

    def test_mixed_internalization(self):
        """Test realistic case with mixed internalization."""
        client_trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),
            create_test_trade("T002", 1704110460000, -1, 600.0, 1.0995),
            create_test_trade("T003", 1704110490000, 1, 800.0, 1.1008),
        ]

        # Total: +1000 - 600 + 800 = +1200
        # Hedge to flatten +1200
        hedge_trades = [{"qty": 1200.0}]

        metrics = MetricsCalculator.calculate_internalization(
            client_trades, hedge_trades
        )

        # Total volume: 1000 + 600 + 800 = 2400
        # Internalized: 600 (BUY 1000 vs SELL 600 = 600 internalized)
        # Externalized: 1200 (hedge)
        # Ratio: (2400 - 1200) / 2400 = 0.5
        assert abs(metrics["total_client_volume"] - 2400.0) < 1e-8
        assert abs(metrics["externalized_volume"] - 1200.0) < 1e-8
        assert abs(metrics["internalized_volume"] - 1200.0) < 1e-8
        assert abs(metrics["internalization_ratio"] - 0.5) < 1e-8

    def test_empty_trades(self):
        """Test with no trades."""
        metrics = MetricsCalculator.calculate_internalization([], [])

        assert metrics["total_client_volume"] == 0.0
        assert metrics["internalized_volume"] == 0.0
        assert metrics["externalized_volume"] == 0.0
        assert metrics["internalization_ratio"] == 0.0


class TestCalculateTimeToClose:
    """Test time-to-close metrics calculation."""

    def test_single_open_slice(self):
        """Test time-to-close for single open slice."""
        fifo_queue = [
            FIFOSlice(
                slice_id="S001",
                open_timestamp_ms=1704110400000,  # Opened 60s ago
                side=1,
                qty=1000.0,
                open_mid=1.1000,
                source_type="client",
                source_trade_id="T001",
            )
        ]

        current_timestamp_ms = 1704110460000  # +60s

        metrics = MetricsCalculator.calculate_time_to_close(
            fifo_queue, current_timestamp_ms
        )

        assert abs(metrics["avg_time_to_close_seconds"] - 60.0) < 1e-8
        assert abs(metrics["max_time_to_close_seconds"] - 60.0) < 1e-8
        assert metrics["open_slice_count"] == 1

    def test_multiple_open_slices(self):
        """Test time-to-close for multiple open slices."""
        fifo_queue = [
            FIFOSlice(
                slice_id="S001",
                open_timestamp_ms=1704110400000,  # Opened 120s ago
                side=1,
                qty=500.0,
                open_mid=1.1000,
                source_type="client",
                source_trade_id="T001",
            ),
            FIFOSlice(
                slice_id="S002",
                open_timestamp_ms=1704110460000,  # Opened 60s ago
                side=1,
                qty=300.0,
                open_mid=1.1005,
                source_type="client",
                source_trade_id="T002",
            ),
        ]

        current_timestamp_ms = 1704110520000  # +120s from first, +60s from second

        metrics = MetricsCalculator.calculate_time_to_close(
            fifo_queue, current_timestamp_ms
        )

        # Average: (120 + 60) / 2 = 90
        assert abs(metrics["avg_time_to_close_seconds"] - 90.0) < 1e-8
        assert abs(metrics["max_time_to_close_seconds"] - 120.0) < 1e-8
        assert metrics["open_slice_count"] == 2

    def test_empty_queue(self):
        """Test time-to-close with empty queue."""
        metrics = MetricsCalculator.calculate_time_to_close([], 1704110400000)

        assert metrics["avg_time_to_close_seconds"] == 0.0
        assert metrics["max_time_to_close_seconds"] == 0.0
        assert metrics["open_slice_count"] == 0


class TestCalculatePnLBreakdown:
    """Test PnL breakdown calculation."""

    def test_pnl_breakdown_single_record(self):
        """Test PnL breakdown for single record."""
        pnl_records = [
            PnLAttributionRecord(
                timestamp_ms=1704110400000,
                event_type="client_fill",
                trade_attributions=[
                    TradePnLAttribution(
                        timestamp_ms=1704110400000,
                        event_type="client_fill",
                        source_trade_id="T001",
                        pair="EURUSD",
                        native_currency="USD",
                        reporting_currency="USD",
                        fx_rate=1.0,
                        execution_pnl_native=5.0,
                        inventory_pnl_native=10.0,
                        hedge_pnl_native=-1.0,
                        execution_pnl_reporting=5.0,
                        inventory_pnl_reporting=10.0,
                        hedge_pnl_reporting=-1.0,
                    )
                ],
                total_execution_pnl_reporting=5.0,
                total_inventory_pnl_reporting=10.0,
                total_hedge_pnl_reporting=-1.0,
                total_unrealized_pnl_reporting=0.0,
            )
        ]

        breakdown = MetricsCalculator.calculate_pnl_breakdown(pnl_records)

        assert abs(breakdown["total_execution_pnl_reporting"] - 5.0) < 1e-8
        assert abs(breakdown["total_inventory_pnl_reporting"] - 10.0) < 1e-8
        assert abs(breakdown["total_hedge_pnl_reporting"] - (-1.0)) < 1e-8
        assert abs(breakdown["total_pnl_reporting"] - 14.0) < 1e-8  # 5 + 10 - 1

    def test_pnl_breakdown_multiple_records(self):
        """Test PnL breakdown for multiple records."""
        pnl_records = [
            PnLAttributionRecord(
                timestamp_ms=1704110400000,
                event_type="client_fill",
                trade_attributions=[],
                total_execution_pnl_reporting=5.0,
                total_inventory_pnl_reporting=10.0,
                total_hedge_pnl_reporting=0.0,
                total_unrealized_pnl_reporting=0.0,
            ),
            PnLAttributionRecord(
                timestamp_ms=1704110460000,
                event_type="client_fill",
                trade_attributions=[],
                total_execution_pnl_reporting=3.0,
                total_inventory_pnl_reporting=8.0,
                total_hedge_pnl_reporting=-1.5,
                total_unrealized_pnl_reporting=0.0,
            ),
        ]

        breakdown = MetricsCalculator.calculate_pnl_breakdown(pnl_records)

        assert abs(breakdown["total_execution_pnl_reporting"] - 8.0) < 1e-8
        assert abs(breakdown["total_inventory_pnl_reporting"] - 18.0) < 1e-8
        assert abs(breakdown["total_hedge_pnl_reporting"] - (-1.5)) < 1e-8
        assert abs(breakdown["total_pnl_reporting"] - 24.5) < 1e-8

    def test_pnl_breakdown_empty_records(self):
        """Test PnL breakdown with no records."""
        breakdown = MetricsCalculator.calculate_pnl_breakdown([])

        assert breakdown["total_execution_pnl_reporting"] == 0.0
        assert breakdown["total_inventory_pnl_reporting"] == 0.0
        assert breakdown["total_hedge_pnl_reporting"] == 0.0
        assert breakdown["total_pnl_reporting"] == 0.0
