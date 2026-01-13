"""Numba-optimized FIFO matching engine.

High-performance FIFO queue matching with inventory PnL calculation and
trade-level attribution tracking. Uses Numba JIT compilation for 10-100x speedup.
"""

from collections import namedtuple

import numpy as np
from numba import njit

from ...core.data.schemas import DecrossedTradeRecord
from .market_fetcher import MarketSnapshot

# Numpy structured array dtype for Numba compatibility
FIFO_SLICE_DTYPE = np.dtype([
    ('slice_id', 'U32'),
    ('open_timestamp_ms', np.int64),
    ('side', np.int8),
    ('qty', np.float64),
    ('open_mid', np.float64),
    ('source_type', 'U8'),  # "client" or "hedge"
    ('source_trade_id', 'U32'),
])


# Named tuple for match results
MatchResult = namedtuple('MatchResult', [
    'updated_queue',
    'inventory_pnl',
    'matched_slices'
])


@njit
def fifo_match_and_pnl_attributed(
    queue: np.ndarray,
    new_side: np.int8,
    new_qty: np.float64,
    new_mid: np.float64,
    new_timestamp_ms: np.int64,
    new_source_type: str,
    new_trade_id: str,
) -> tuple:
    """FIFO matching with detailed attribution (Numba-optimized hot loop).

    This is the performance-critical function that processes every fill.
    JIT compilation delivers 10-100x speedup over pure Python.

    Args:
        queue: Current FIFO queue (numpy structured array)
        new_side: Trade side (+1 buy, -1 sell)
        new_qty: Trade quantity
        new_mid: Current mid price (for inventory PnL calculation)
        new_timestamp_ms: Trade timestamp
        new_source_type: "client" or "hedge"
        new_trade_id: Unique trade identifier

    Returns:
        Tuple of (updated_queue, total_inventory_pnl, matched_slices)

        matched_slices is a list of tuples:
            [(slice_source_trade_id, matched_qty, inventory_pnl_contribution), ...]

    Algorithm:
        1. Iterate through queue in FIFO order
        2. Match new fill against opposing slices
        3. Calculate inventory PnL for each match: (close_mid - open_mid) * qty * side
        4. Update slice quantities or remove fully matched slices
        5. Add unmatched quantity as new slice

    Example:
        Queue: BUY 1000 @ 1.10 (from trade T001)
        New fill: SELL 500 @ 1.12

        → Match 500 of the 1000 BUY
        → Inventory PnL = (1.12 - 1.10) * 500 * 1 = +10.0
        → Matched slices = [("T001", 500, 10.0)]
        → Updated queue: BUY 500 @ 1.10 (remaining)
    """
    inventory_pnl = 0.0
    remaining_qty = new_qty

    # Pre-allocate arrays for output (max size = queue + 1 for new slice)
    max_size = len(queue) + 1
    temp_queue = np.empty(max_size, dtype=FIFO_SLICE_DTYPE)
    queue_idx = 0

    # Pre-allocate for matched slices tracking
    matched_trade_ids = np.empty(max_size, dtype='U32')
    matched_qtys = np.zeros(max_size, dtype=np.float64)
    matched_pnls = np.zeros(max_size, dtype=np.float64)
    matched_count = 0

    # FIFO matching loop
    for i in range(len(queue)):
        if remaining_qty <= 1e-8:
            # Consumed all new quantity, add rest of queue
            for j in range(i, len(queue)):
                temp_queue[queue_idx] = queue[j]
                queue_idx += 1
            break

        # Get current slice
        current_slice = queue[i]

        # Check if this slice opposes the new fill
        if current_slice['side'] == -new_side:
            # Match occurs
            match_qty = min(current_slice['qty'], remaining_qty)

            # Inventory PnL for this specific match
            # Formula: (close_mid - open_mid) * qty * side
            slice_pnl = (new_mid - current_slice['open_mid']) * match_qty * current_slice['side']
            inventory_pnl += slice_pnl

            # Record attribution
            matched_trade_ids[matched_count] = current_slice['source_trade_id']
            matched_qtys[matched_count] = match_qty
            matched_pnls[matched_count] = slice_pnl
            matched_count += 1

            # Update quantity
            updated_qty = current_slice['qty'] - match_qty
            remaining_qty -= match_qty

            # Keep slice if still has quantity
            if updated_qty > 1e-8:
                # Add to temp queue with updated quantity
                temp_queue[queue_idx]['slice_id'] = current_slice['slice_id']
                temp_queue[queue_idx]['open_timestamp_ms'] = current_slice['open_timestamp_ms']
                temp_queue[queue_idx]['side'] = current_slice['side']
                temp_queue[queue_idx]['qty'] = updated_qty
                temp_queue[queue_idx]['open_mid'] = current_slice['open_mid']
                temp_queue[queue_idx]['source_type'] = current_slice['source_type']
                temp_queue[queue_idx]['source_trade_id'] = current_slice['source_trade_id']
                queue_idx += 1
        else:
            # Same side, no match - keep slice
            temp_queue[queue_idx] = current_slice
            queue_idx += 1

    # Add unmatched quantity as new slice
    if remaining_qty > 1e-8:
        temp_queue[queue_idx]['slice_id'] = new_trade_id
        temp_queue[queue_idx]['open_timestamp_ms'] = new_timestamp_ms
        temp_queue[queue_idx]['side'] = new_side
        temp_queue[queue_idx]['qty'] = remaining_qty
        temp_queue[queue_idx]['open_mid'] = new_mid
        temp_queue[queue_idx]['source_type'] = new_source_type
        temp_queue[queue_idx]['source_trade_id'] = new_trade_id
        queue_idx += 1

    # Trim to actual size
    updated_queue = temp_queue[:queue_idx]

    # Build matched slices list
    matched_slices = []
    for i in range(matched_count):
        matched_slices.append((
            matched_trade_ids[i],
            matched_qtys[i],
            matched_pnls[i]
        ))

    return (updated_queue, inventory_pnl, matched_slices)


@njit
def calculate_unrealized_pnl_by_slice(
    queue: np.ndarray,
    current_mid: float,
) -> list:
    """Calculate unrealized PnL with per-slice attribution (Numba-optimized).

    Marks each open slice to current market mid price.

    Args:
        queue: Current FIFO queue
        current_mid: Current mid price

    Returns:
        List of (source_trade_id, unrealized_pnl) tuples

    Example:
        Queue: BUY 500 @ 1.10 (from T001), SELL 300 @ 1.15 (from T002)
        Current mid: 1.12

        → T001: (1.12 - 1.10) * 500 * 1 = +10.0
        → T002: (1.12 - 1.15) * 300 * -1 = +9.0
        → Returns: [("T001", 10.0), ("T002", 9.0)]
    """
    slice_pnls = []

    for i in range(len(queue)):
        slice_ = queue[i]
        slice_pnl = (current_mid - slice_['open_mid']) * slice_['qty'] * slice_['side']
        slice_pnls.append((slice_['source_trade_id'], slice_pnl))

    return slice_pnls


class FIFOMatcher:
    """Python wrapper for Numba FIFO matching engine.

    Provides a clean interface for the simulation engine while leveraging
    Numba-optimized hot loops for performance.
    """

    def __init__(self):
        """Initialize FIFO matcher with empty queue."""
        self.queue = np.array([], dtype=FIFO_SLICE_DTYPE)

    def process_fill(
        self,
        trade: DecrossedTradeRecord | dict,
        market_snapshot: MarketSnapshot,
        is_hedge: bool = False,
    ) -> MatchResult:
        """Process a fill (client or hedge) through FIFO queue.

        Args:
            trade: Trade to process (DecrossedTradeRecord or dict with same fields)
            market_snapshot: Current market conditions
            is_hedge: True if this is a hedge fill

        Returns:
            MatchResult with updated_queue, inventory_pnl, and matched_slices

        Example:
            >>> matcher = FIFOMatcher()
            >>> trade = DecrossedTradeRecord(
            ...     side=1, qty=1000.0, source_trade_id="T001", ...
            ... )
            >>> snapshot = MarketSnapshot(mid=1.10, ...)
            >>> result = matcher.process_fill(trade, snapshot)
            >>> result.inventory_pnl
            0.0  # First fill, nothing to match
            >>> len(matcher.queue)
            1  # New slice added
        """
        # Extract trade fields (handle both DecrossedTradeRecord and dict)
        if isinstance(trade, dict):
            trade_id = trade.get("trade_id", trade.get("source_trade_id", "unknown"))
            side = trade["side"]
            qty = trade["qty"]
            timestamp_ms = trade["timestamp_ms"]
        else:
            trade_id = trade.source_trade_id
            side = trade.side
            qty = trade.qty
            timestamp_ms = trade.timestamp_ms

        # Side is always from house's perspective:
        # +1 = house BUYS base currency (going long)
        # -1 = house SELLS base currency (going short)
        # Both client trades and hedge trades now use this convention.

        # Call Numba hot loop
        updated_queue, inv_pnl, matched_slices = fifo_match_and_pnl_attributed(
            self.queue,
            np.int8(side),
            np.float64(qty),
            np.float64(market_snapshot.mid),
            np.int64(timestamp_ms),
            "hedge" if is_hedge else "client",
            trade_id,
        )

        # Update queue
        self.queue = updated_queue

        return MatchResult(
            updated_queue=updated_queue,
            inventory_pnl=inv_pnl,
            matched_slices=matched_slices,
        )

    def calculate_unrealized_pnl(self, current_mid: float) -> list:
        """Calculate unrealized PnL for all open slices.

        Args:
            current_mid: Current mid price

        Returns:
            List of (source_trade_id, unrealized_pnl) tuples

        Example:
            >>> matcher = FIFOMatcher()
            >>> # ... process some fills ...
            >>> unrealized = matcher.calculate_unrealized_pnl(1.12)
            >>> unrealized
            [("T001", 10.0), ("T002", -5.0)]
        """
        return calculate_unrealized_pnl_by_slice(self.queue, current_mid)

    def get_net_position(self) -> float:
        """Calculate current net position from queue.

        Returns:
            Net position (sum of qty * side for all slices)

        Example:
            >>> matcher = FIFOMatcher()
            >>> # Queue: BUY 500, SELL 300
            >>> matcher.get_net_position()
            200.0  # +500 - 300
        """
        if len(self.queue) == 0:
            return 0.0

        net_pos = 0.0
        for i in range(len(self.queue)):
            slice_ = self.queue[i]
            net_pos += slice_['qty'] * slice_['side']

        return net_pos

    def get_queue_summary(self) -> dict:
        """Get summary statistics of current FIFO queue.

        Returns:
            Dict with queue statistics

        Example:
            >>> matcher.get_queue_summary()
            {
                "slice_count": 3,
                "total_buy_qty": 1500.0,
                "total_sell_qty": 800.0,
                "net_position": 700.0,
                "oldest_timestamp_ms": 1704110400000,
            }
        """
        if len(self.queue) == 0:
            return {
                "slice_count": 0,
                "total_buy_qty": 0.0,
                "total_sell_qty": 0.0,
                "net_position": 0.0,
                "oldest_timestamp_ms": None,
            }

        buy_qty = 0.0
        sell_qty = 0.0
        oldest_ts = None

        for i in range(len(self.queue)):
            slice_ = self.queue[i]
            if slice_['side'] == 1:
                buy_qty += slice_['qty']
            else:
                sell_qty += slice_['qty']

            if oldest_ts is None or slice_['open_timestamp_ms'] < oldest_ts:
                oldest_ts = slice_['open_timestamp_ms']

        return {
            "slice_count": len(self.queue),
            "total_buy_qty": buy_qty,
            "total_sell_qty": sell_qty,
            "net_position": buy_qty - sell_qty,
            "oldest_timestamp_ms": int(oldest_ts) if oldest_ts is not None else None,
        }
