"""Internalization and time-to-close metrics calculator.

Provides methods for calculating key risk and performance metrics across
simulation results.
"""

from ...core.data.schemas import DecrossedTradeRecord
from ..shard.state import FIFOSlice


class MetricsCalculator:
    """Calculate internalization and time-to-close metrics."""

    @staticmethod
    def calculate_internalization(
        client_trades: list[DecrossedTradeRecord],
        hedge_trades: list[dict],
    ) -> dict:
        """Calculate internalization metrics.

        Internalized volume: Volume matched between opposing client trades
        Externalized volume: Volume matched between client and hedge

        Args:
            client_trades: All client trades for the shard
            hedge_trades: All hedge trades executed during simulation

        Returns:
            Dict with internalization metrics:
            {
                "total_client_volume": float,
                "internalized_volume": float,
                "externalized_volume": float,
                "internalization_ratio": float,  # % internalized (0.0 - 1.0)
            }

        Example:
            >>> client_trades = [
            ...     DecrossedTradeRecord(qty=1000.0, ...),
            ...     DecrossedTradeRecord(qty=500.0, ...),
            ...     DecrossedTradeRecord(qty=800.0, ...),
            ... ]
            >>> hedge_trades = [{"qty": 300.0}, {"qty": 200.0}]
            >>> metrics = MetricsCalculator.calculate_internalization(
            ...     client_trades, hedge_trades
            ... )
            >>> metrics
            {
                "total_client_volume": 2300.0,
                "externalized_volume": 500.0,
                "internalized_volume": 1800.0,
                "internalization_ratio": 0.7826,  # 78.26% internalized
            }
        """
        total_volume = sum(t.qty for t in client_trades)
        externalized_volume = sum(h["qty"] for h in hedge_trades)
        internalized_volume = total_volume - externalized_volume

        return {
            "total_client_volume": total_volume,
            "internalized_volume": max(0.0, internalized_volume),
            "externalized_volume": externalized_volume,
            "internalization_ratio": (
                internalized_volume / total_volume if total_volume > 0 else 0.0
            ),
        }

    @staticmethod
    def calculate_time_to_close(
        fifo_queue: list[FIFOSlice],
        current_timestamp_ms: int,
    ) -> dict:
        """Calculate time-to-close risk metrics.

        Measures how long positions have been open (risk exposure duration).

        Args:
            fifo_queue: Current FIFO queue with open slices
            current_timestamp_ms: Current simulation timestamp

        Returns:
            Dict with time-to-close metrics:
            {
                "avg_time_to_close_seconds": float,
                "max_time_to_close_seconds": float,
                "open_slice_count": int,
            }

        Example:
            >>> fifo_queue = [
            ...     FIFOSlice(open_timestamp_ms=1704110400000, ...),  # Opened 60s ago
            ...     FIFOSlice(open_timestamp_ms=1704110430000, ...),  # Opened 30s ago
            ... ]
            >>> current_timestamp_ms = 1704110460000
            >>> metrics = MetricsCalculator.calculate_time_to_close(
            ...     fifo_queue, current_timestamp_ms
            ... )
            >>> metrics
            {
                "avg_time_to_close_seconds": 45.0,
                "max_time_to_close_seconds": 60.0,
                "open_slice_count": 2,
            }
        """
        if not fifo_queue:
            return {
                "avg_time_to_close_seconds": 0.0,
                "max_time_to_close_seconds": 0.0,
                "open_slice_count": 0,
            }

        times_to_close = []
        for slice_ in fifo_queue:
            time_open_ms = current_timestamp_ms - slice_.open_timestamp_ms
            times_to_close.append(time_open_ms / 1000.0)

        return {
            "avg_time_to_close_seconds": sum(times_to_close) / len(times_to_close),
            "max_time_to_close_seconds": max(times_to_close),
            "open_slice_count": len(fifo_queue),
        }

    @staticmethod
    def calculate_pnl_breakdown(pnl_records: list) -> dict:
        """Calculate aggregate PnL breakdown from attribution records.

        Args:
            pnl_records: List of PnLAttributionRecord objects

        Returns:
            Dict with PnL component totals in both native and reporting currency:
            {
                "total_execution_pnl_native": float,
                "total_inventory_pnl_native": float,
                "total_hedge_pnl_native": float,
                "total_execution_pnl_reporting": float,
                "total_inventory_pnl_reporting": float,
                "total_hedge_pnl_reporting": float,
                "total_pnl_reporting": float,
            }
        """
        if not pnl_records:
            return {
                "total_execution_pnl_reporting": 0.0,
                "total_inventory_pnl_reporting": 0.0,
                "total_hedge_pnl_reporting": 0.0,
                "total_pnl_reporting": 0.0,
            }

        # PnLAttributionRecord only has reporting currency totals, not native
        total_exec_reporting = sum(
            r.total_execution_pnl_reporting for r in pnl_records
        )
        total_inv_reporting = sum(r.total_inventory_pnl_reporting for r in pnl_records)
        total_hedge_reporting = sum(r.total_hedge_pnl_reporting for r in pnl_records)

        return {
            "total_execution_pnl_reporting": total_exec_reporting,
            "total_inventory_pnl_reporting": total_inv_reporting,
            "total_hedge_pnl_reporting": total_hedge_reporting,
            "total_pnl_reporting": (
                total_exec_reporting + total_inv_reporting + total_hedge_reporting
            ),
        }
