"""PnL calculation with trade-level attribution and FX conversion.

Provides methods for calculating execution PnL, hedge costs, and attribution
logic with proper currency conversion to reporting currency.
"""

from numba import njit

from ...core.data.schemas import DecrossedTradeRecord
from .fx_converter import FXConverter
from .market_fetcher import MarketSnapshot


@njit
def calculate_hedge_cost(side: int, qty: float, spread: float) -> float:
    """Calculate hedge cost from crossing the spread (Numba-optimized).

    When hedging, we must cross the spread (buy at ask, sell at bid).
    This is a realized cost of hedging.

    Args:
        side: Hedge side (+1 buy, -1 sell)
        qty: Hedge quantity
        spread: Market spread (ask - bid)

    Returns:
        Hedge cost (always negative)

    Example:
        >>> # Hedge by buying: pay ask instead of mid
        >>> calculate_hedge_cost(1, 1000.0, 0.0010)
        -0.5  # -(0.0010 / 2) * 1000 = -0.5

        >>> # Hedge by selling: receive bid instead of mid
        >>> calculate_hedge_cost(-1, 1000.0, 0.0010)
        -0.5  # -(0.0010 / 2) * 1000 = -0.5
    """
    return -(spread / 2.0) * qty


class PnLCalculator:
    """Calculate PnL components with trade-level attribution and FX conversion.

    Handles:
    - Execution PnL (difference between fill price and mid)
    - Hedge cost attribution (proportional allocation)
    - Currency conversion (native → reporting currency)
    """

    def __init__(self, fx_converter: FXConverter):
        """Initialize PnL calculator.

        Args:
            fx_converter: FX converter for currency normalization
        """
        self.fx_converter = fx_converter

    def calculate_execution_pnl(
        self,
        exec_price: float,
        exec_mid: float,
        qty: float,
        side: int,
        pair: str,
        fx_rate: float,
    ) -> tuple[float, float]:
        """Calculate execution PnL in both native and reporting currency.

        Execution PnL is the difference between the actual fill price and
        the mid price at execution time.

        Args:
            exec_price: Actual execution price
            exec_mid: Mid price at execution
            qty: Trade quantity
            side: Trade side (+1 buy, -1 sell)
            pair: Currency pair (for determining native currency)
            fx_rate: FX rate for conversion

        Returns:
            Tuple of (pnl_native, pnl_reporting)

        Example:
            >>> calc = PnLCalculator(FXConverter("USD"))
            >>> # EURUSD: buy at 1.1005, mid was 1.1000
            >>> pnl_native, pnl_reporting = calc.calculate_execution_pnl(
            ...     1.1005, 1.1000, 1000.0, 1, "EURUSD", 1.0
            ... )
            >>> pnl_native
            5.0  # (1.1005 - 1.1000) * 1000 * 1 = +5 USD
            >>> pnl_reporting
            5.0  # Same since EURUSD PnL is already in USD

            >>> # EURGBP: sell at 0.8795, mid was 0.8800
            >>> # GBPUSD rate = 1.25 for conversion
            >>> pnl_native, pnl_reporting = calc.calculate_execution_pnl(
            ...     0.8795, 0.8800, 1000.0, -1, "EURGBP", 1.25
            ... )
            >>> pnl_native
            5.0  # (0.8795 - 0.8800) * 1000 * -1 = +5 GBP
            >>> pnl_reporting
            6.25  # 5 GBP * 1.25 = 6.25 USD
        """
        # Calculate PnL in native currency (quote currency)
        pnl_native = (exec_price - exec_mid) * qty * side

        # Convert to reporting currency
        pnl_reporting, _ = self.fx_converter.convert_pnl(pnl_native, fx_rate, pair)

        return pnl_native, pnl_reporting

    def attribute_hedge_cost_to_trades(
        self,
        hedge_cost_native: float,
        hedge_cost_reporting: float,
        triggering_trades: list[DecrossedTradeRecord],
        current_position: float,
    ) -> dict[str, tuple[float, float]]:
        """Attribute hedge cost to trades that triggered the hedge.

        Allocates hedge cost proportionally based on each trade's contribution
        to the absolute position that exceeded the risk band.

        Args:
            hedge_cost_native: Total hedge cost in native currency (negative)
            hedge_cost_reporting: Total hedge cost in reporting currency (negative)
            triggering_trades: Trades that contributed to exceeding risk band
            current_position: Net position before hedge

        Returns:
            Dict mapping source_trade_id to (allocated_cost_native, allocated_cost_reporting)

        Example:
            >>> calc = PnLCalculator(FXConverter("USD"))
            >>> trades = [
            ...     DecrossedTradeRecord(source_trade_id="T001", qty=1000.0, side=1, ...),
            ...     DecrossedTradeRecord(source_trade_id="T002", qty=500.0, side=1, ...),
            ... ]
            >>> # Total position: +1500, hedge cost: -1.0 USD
            >>> allocation = calc.attribute_hedge_cost_to_trades(
            ...     -1.0, -1.0, trades, 1500.0
            ... )
            >>> allocation
            {
                "T001": (-0.667, -0.667),  # 1000/1500 * -1.0
                "T002": (-0.333, -0.333),  # 500/1500 * -1.0
            }
        """
        if not triggering_trades or abs(hedge_cost_native) < 1e-8:
            return {}

        # Calculate each trade's contribution to absolute position
        contributions = {}
        total_contribution = 0.0

        for trade in triggering_trades:
            contribution = abs(trade.qty * trade.side)
            contributions[trade.source_trade_id] = contribution
            total_contribution += contribution

        # Allocate hedge cost proportionally
        allocation = {}
        for trade_id, contribution in contributions.items():
            pct = contribution / total_contribution if total_contribution > 0 else 0
            allocation[trade_id] = (
                hedge_cost_native * pct,
                hedge_cost_reporting * pct,
            )

        return allocation

    def convert_inventory_pnl(
        self,
        inventory_pnl_native: float,
        pair: str,
        fx_rate: float,
    ) -> float:
        """Convert inventory PnL from native to reporting currency.

        Args:
            inventory_pnl_native: Inventory PnL in native currency
            pair: Currency pair
            fx_rate: FX rate for conversion

        Returns:
            Inventory PnL in reporting currency
        """
        pnl_reporting, _ = self.fx_converter.convert_pnl(
            inventory_pnl_native, fx_rate, pair
        )
        return pnl_reporting

    def get_native_currency(self, pair: str) -> str:
        """Get native currency for a pair's PnL.

        Args:
            pair: Currency pair

        Returns:
            Quote currency (native PnL currency)

        Example:
            >>> calc = PnLCalculator(FXConverter("USD"))
            >>> calc.get_native_currency("EURUSD")
            "USD"
            >>> calc.get_native_currency("USDJPY")
            "JPY"
            >>> calc.get_native_currency("EURGBP")
            "GBP"
        """
        return self.fx_converter.get_native_currency(pair)

    def get_reporting_currency(self) -> str:
        """Get reporting currency for aggregation.

        Returns:
            Reporting currency code

        Example:
            >>> calc = PnLCalculator(FXConverter("USD"))
            >>> calc.get_reporting_currency()
            "USD"
        """
        return self.fx_converter.reporting_currency
