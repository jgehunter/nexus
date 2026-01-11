"""Unit tests for FIFO matching engine.

Tests the Numba-optimized FIFO matching algorithm with various scenarios:
- Single matches
- Partial matches
- Multi-match sequences
- Same-side (no match)
- Empty queue edge cases
- PnL accuracy validation
- Trade-level attribution
"""

import numpy as np
import pytest

from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.shard.fifo_matcher import (
    FIFO_SLICE_DTYPE,
    FIFOMatcher,
    calculate_unrealized_pnl_by_slice,
    fifo_match_and_pnl_attributed,
)
from efxbt.engine.shard.market_fetcher import MarketSnapshot


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
        ref_mid=price,
        is_direct=True,
        path=["EUR", "USD"],
        leg_index=0,
        leg_count=1,
    )


class TestFIFOMatchAndPnLAttribued:
    """Test the core Numba-optimized FIFO matching function."""

    def test_single_match_complete(self):
        """Test matching single opposing slice completely."""
        # Queue: BUY 1000 @ open_mid=1.10
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # New fill: SELL 1000 @ close_mid=1.12
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(-1),  # SELL
            np.float64(1000.0),
            np.float64(1.12),
            np.int64(1704110460000),
            "client",
            "T002",
        )

        # Expected: inventory_pnl = (1.12 - 1.10) * 1000 * 1 = +20.0
        assert abs(inv_pnl - 20.0) < 1e-8
        assert len(updated_queue) == 0  # Queue should be empty
        assert len(matched_slices) == 1
        assert matched_slices[0][0] == "T001"  # Matched slice from T001
        assert abs(matched_slices[0][1] - 1000.0) < 1e-8  # Matched qty
        assert abs(matched_slices[0][2] - 20.0) < 1e-8  # Slice PnL contribution

    def test_partial_match_remaining_slice(self):
        """Test partial matching of large slice."""
        # Queue: BUY 1000 @ 1.10
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # New fill: SELL 300 @ 1.12
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(-1),
            np.float64(300.0),
            np.float64(1.12),
            np.int64(1704110460000),
            "client",
            "T002",
        )

        # Expected: inventory_pnl = (1.12 - 1.10) * 300 * 1 = +6.0
        assert abs(inv_pnl - 6.0) < 1e-8
        assert len(updated_queue) == 1  # Remaining slice
        assert updated_queue[0]["qty"] == 700.0  # 1000 - 300
        assert updated_queue[0]["source_trade_id"] == "T001"
        assert len(matched_slices) == 1
        assert abs(matched_slices[0][1] - 300.0) < 1e-8

    def test_multi_match_across_slices(self):
        """Test matching across multiple slices."""
        # Queue: BUY 500 @ 1.10, BUY 700 @ 1.12
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    500.0,
                    1.10,
                    "client",
                    "T001",
                ),
                (
                    "T002",
                    1704110430000,
                    1,
                    700.0,
                    1.12,
                    "client",
                    "T002",
                ),
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # New fill: SELL 1000 @ 1.15
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(-1),
            np.float64(1000.0),
            np.float64(1.15),
            np.int64(1704110460000),
            "client",
            "T003",
        )

        # Expected:
        # Match 500 from T001: (1.15 - 1.10) * 500 * 1 = +25.0
        # Match 500 from T002: (1.15 - 1.12) * 500 * 1 = +15.0
        # Total: +40.0
        # Remaining in queue: BUY 200 @ 1.12 (from T002)
        assert abs(inv_pnl - 40.0) < 1e-8
        assert len(updated_queue) == 1
        assert updated_queue[0]["qty"] == 200.0
        assert updated_queue[0]["source_trade_id"] == "T002"
        assert len(matched_slices) == 2
        assert matched_slices[0][0] == "T001"
        assert abs(matched_slices[0][1] - 500.0) < 1e-8
        assert matched_slices[1][0] == "T002"
        assert abs(matched_slices[1][1] - 500.0) < 1e-8

    def test_same_side_no_match(self):
        """Test no matching when same side."""
        # Queue: BUY 1000 @ 1.10
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # New fill: BUY 500 @ 1.12 (same side)
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(1),  # BUY
            np.float64(500.0),
            np.float64(1.12),
            np.int64(1704110460000),
            "client",
            "T002",
        )

        # Expected: no match, inventory_pnl = 0
        assert abs(inv_pnl) < 1e-8
        assert len(updated_queue) == 2
        assert updated_queue[0]["source_trade_id"] == "T001"
        assert updated_queue[1]["source_trade_id"] == "T002"
        assert updated_queue[1]["qty"] == 500.0
        assert len(matched_slices) == 0

    def test_empty_queue(self):
        """Test processing fill with empty queue."""
        queue = np.array([], dtype=FIFO_SLICE_DTYPE)

        # New fill: BUY 1000 @ 1.10
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(1),
            np.float64(1000.0),
            np.float64(1.10),
            np.int64(1704110400000),
            "client",
            "T001",
        )

        # Expected: no match, new slice added
        assert abs(inv_pnl) < 1e-8
        assert len(updated_queue) == 1
        assert updated_queue[0]["source_trade_id"] == "T001"
        assert updated_queue[0]["qty"] == 1000.0
        assert len(matched_slices) == 0

    def test_exact_opposite_match(self):
        """Test exact opposite match (both sides consumed)."""
        # Queue: BUY 1000 @ 1.10
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # New fill: SELL 1000 @ 1.12 (exact opposite)
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(-1),
            np.float64(1000.0),
            np.float64(1.12),
            np.int64(1704110460000),
            "client",
            "T002",
        )

        # Expected: complete match, empty queue
        assert abs(inv_pnl - 20.0) < 1e-8
        assert len(updated_queue) == 0
        assert len(matched_slices) == 1

    def test_overflow_match_new_opposite_slice(self):
        """Test new fill larger than queue, creates opposite slice."""
        # Queue: BUY 500 @ 1.10
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    500.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # New fill: SELL 1000 @ 1.12 (larger than queue)
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            queue,
            np.int8(-1),
            np.float64(1000.0),
            np.float64(1.12),
            np.int64(1704110460000),
            "client",
            "T002",
        )

        # Expected:
        # Match 500: (1.12 - 1.10) * 500 * 1 = +10.0
        # Add new SELL 500 @ 1.12
        assert abs(inv_pnl - 10.0) < 1e-8
        assert len(updated_queue) == 1
        assert updated_queue[0]["side"] == -1  # SELL
        assert updated_queue[0]["qty"] == 500.0
        assert updated_queue[0]["source_trade_id"] == "T002"
        assert len(matched_slices) == 1


class TestCalculateUnrealizedPnL:
    """Test unrealized PnL calculation by slice."""

    def test_unrealized_pnl_single_slice(self):
        """Test unrealized PnL for single open slice."""
        # Queue: BUY 500 @ 1.10
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    500.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # Current mid: 1.12
        slice_pnls = calculate_unrealized_pnl_by_slice(queue, 1.12)

        # Expected: (1.12 - 1.10) * 500 * 1 = +10.0
        assert len(slice_pnls) == 1
        assert slice_pnls[0][0] == "T001"
        assert abs(slice_pnls[0][1] - 10.0) < 1e-8

    def test_unrealized_pnl_multiple_slices(self):
        """Test unrealized PnL for multiple open slices."""
        # Queue: BUY 500 @ 1.10, SELL 300 @ 1.15
        queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    500.0,
                    1.10,
                    "client",
                    "T001",
                ),
                (
                    "T002",
                    1704110430000,
                    -1,
                    300.0,
                    1.15,
                    "client",
                    "T002",
                ),
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        # Current mid: 1.12
        slice_pnls = calculate_unrealized_pnl_by_slice(queue, 1.12)

        # Expected:
        # T001: (1.12 - 1.10) * 500 * 1 = +10.0
        # T002: (1.12 - 1.15) * 300 * -1 = +9.0
        assert len(slice_pnls) == 2
        assert slice_pnls[0][0] == "T001"
        assert abs(slice_pnls[0][1] - 10.0) < 1e-8
        assert slice_pnls[1][0] == "T002"
        assert abs(slice_pnls[1][1] - 9.0) < 1e-8

    def test_unrealized_pnl_empty_queue(self):
        """Test unrealized PnL with empty queue."""
        queue = np.array([], dtype=FIFO_SLICE_DTYPE)
        slice_pnls = calculate_unrealized_pnl_by_slice(queue, 1.12)

        assert len(slice_pnls) == 0


class TestFIFOMatcher:
    """Test the Python wrapper for FIFO matching."""

    def test_process_fill_from_trade_record(self):
        """Test processing fill from DecrossedTradeRecord."""
        matcher = FIFOMatcher()

        # First fill: BUY 1000
        trade1 = create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005)
        snapshot1 = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        result1 = matcher.process_fill(trade1, snapshot1, is_hedge=False)

        # First fill: no match, inventory_pnl = 0
        assert abs(result1.inventory_pnl) < 1e-8
        assert len(matcher.queue) == 1

        # Second fill: SELL 500
        trade2 = create_test_trade("T002", 1704110460000, -1, 500.0, 1.0995)
        snapshot2 = MarketSnapshot(
            timestamp_ms=1704110460000,
            pair="EURUSD",
            mid=1.1020,
            bid=1.1018,
            ask=1.1022,
            spread=0.0004,
            fx_rate=1.0,
        )

        result2 = matcher.process_fill(trade2, snapshot2, is_hedge=False)

        # Expected: match 500 from first fill
        # inventory_pnl = (1.1020 - 1.1000) * 500 * 1 = +1.0
        assert abs(result2.inventory_pnl - 1.0) < 1e-8
        assert len(matcher.queue) == 1  # 500 remaining from first fill
        assert len(result2.matched_slices) == 1

    def test_get_net_position(self):
        """Test net position calculation."""
        matcher = FIFOMatcher()

        # Add BUY 1000
        matcher.queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                )
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        assert abs(matcher.get_net_position() - 1000.0) < 1e-8

        # Add SELL 300
        matcher.queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                ),
                (
                    "T002",
                    1704110430000,
                    -1,
                    300.0,
                    1.12,
                    "client",
                    "T002",
                ),
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        assert abs(matcher.get_net_position() - 700.0) < 1e-8

    def test_get_queue_summary(self):
        """Test queue summary statistics."""
        matcher = FIFOMatcher()

        # Empty queue
        summary = matcher.get_queue_summary()
        assert summary["slice_count"] == 0
        assert summary["net_position"] == 0.0

        # Add slices
        matcher.queue = np.array(
            [
                (
                    "T001",
                    1704110400000,
                    1,
                    1000.0,
                    1.10,
                    "client",
                    "T001",
                ),
                (
                    "T002",
                    1704110430000,
                    1,
                    500.0,
                    1.12,
                    "client",
                    "T002",
                ),
                (
                    "T003",
                    1704110460000,
                    -1,
                    800.0,
                    1.15,
                    "client",
                    "T003",
                ),
            ],
            dtype=FIFO_SLICE_DTYPE,
        )

        summary = matcher.get_queue_summary()
        assert summary["slice_count"] == 3
        assert abs(summary["total_buy_qty"] - 1500.0) < 1e-8
        assert abs(summary["total_sell_qty"] - 800.0) < 1e-8
        assert abs(summary["net_position"] - 700.0) < 1e-8
        assert summary["oldest_timestamp_ms"] == 1704110400000
