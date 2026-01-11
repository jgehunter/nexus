"""Currency flow tracking for multi-hop trade decomposition.

This module provides accurate currency flow calculations for decrossing
cross-pair trades through multi-hop paths.
"""

from ..core.config.universe import get_base_currency, get_quote_currency
from ..core.data.schemas import MarketTickRecord, TradeRecord
from ..core.graph.schemas import CurrencyPath


class CurrencyFlowTracker:
    """Tracks currency positions through multi-hop decomposition.

    Handles the complex logic of determining quantities, sides, and prices
    for each leg in a multi-hop currency path, ensuring proper currency
    flow and conservation.
    """

    def __init__(self, original_trade: TradeRecord, path: CurrencyPath):
        """Initialize currency flow tracker.

        Args:
            original_trade: Original cross-pair trade to decompose
            path: Currency path for decomposition
        """
        self.base_curr = path.currencies[0]
        self.quote_curr = path.currencies[-1]
        self.original_side = original_trade.side
        self.original_qty = original_trade.qty
        self.original_price = original_trade.price

    def calculate_leg_parameters(
        self,
        leg_index: int,
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
    ) -> tuple[str, int, float, float]:
        """Calculate parameters for a single leg in the decomposition.

        Args:
            leg_index: Index of the leg (0-based)
            path: Currency path
            market_ticks: Market ticks for all pairs in path

        Returns:
            Tuple of (pair, side, qty, market_price)
            - pair: Direct pair for this leg
            - side: +1 (buy base) or -1 (sell base)
            - qty: Quantity in base currency of the pair
            - market_price: Market price from ticks (bid/ask based on side)

        Example:
            For BUY 1000 EURGBP via EUR->USD->GBP:
            Leg 0: ('EURUSD', 1, 1000.0, 1.1001)  # BUY 1000 EUR at ask
            Leg 1: ('GBPUSD', 1, 880.0, 1.2501)   # BUY 880 GBP at ask (inverted)
        """
        pair = path.pairs[leg_index]
        is_inverted = path.inversions[leg_index]
        tick = market_ticks[pair]

        pair_base = get_base_currency(pair)
        pair_quote = get_quote_currency(pair)

        if leg_index == 0:
            # First leg: matches original trade's base currency
            return self._calculate_first_leg(pair, is_inverted, tick)
        else:
            # Subsequent legs: bridge through intermediate currencies
            return self._calculate_intermediate_leg(
                leg_index, pair, is_inverted, tick, path, market_ticks
            )

    def _calculate_first_leg(
        self,
        pair: str,
        is_inverted: bool,
        tick: MarketTickRecord,
    ) -> tuple[str, int, float, float]:
        """Calculate parameters for the first leg.

        The first leg always involves the original trade's base currency
        and quantity.

        Args:
            pair: Direct pair for this leg
            is_inverted: Whether the pair is inverted relative to path
            tick: Market tick for the pair

        Returns:
            Tuple of (pair, side, qty, market_price)
        """
        pair_base = get_base_currency(pair)
        pair_quote = get_quote_currency(pair)

        if self.original_side == 1:  # BUY base currency
            # We're buying the base currency, selling the quote
            if not is_inverted:  # EURUSD: EUR is base
                # BUY EUR (base of EURUSD)
                leg_side = 1
                leg_qty = self.original_qty
                market_price = tick.ask_tob  # Buying at ask
            else:  # USDEUR: EUR is quote
                # To buy EUR (quote), we SELL USD (base)
                leg_side = -1
                # Need to calculate USD quantity needed
                # EUR qty / EUR_per_USD = USD qty
                leg_qty = self.original_qty / tick.mid
                market_price = tick.bid_tob  # Selling at bid
        else:  # SELL base currency (original_side == -1)
            if not is_inverted:  # EURUSD: EUR is base
                # SELL EUR (base of EURUSD)
                leg_side = -1
                leg_qty = self.original_qty
                market_price = tick.bid_tob  # Selling at bid
            else:  # USDEUR: EUR is quote
                # To sell EUR (quote), we BUY USD (base)
                leg_side = 1
                leg_qty = self.original_qty / tick.mid
                market_price = tick.ask_tob  # Buying at ask

        return (pair, leg_side, leg_qty, market_price)

    def _calculate_intermediate_leg(
        self,
        leg_index: int,
        pair: str,
        is_inverted: bool,
        tick: MarketTickRecord,
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
    ) -> tuple[str, int, float, float]:
        """Calculate parameters for intermediate/final legs.

        These legs bridge from the output of the previous leg to the
        next currency in the path.

        Args:
            leg_index: Index of this leg
            pair: Direct pair for this leg
            is_inverted: Whether pair is inverted
            tick: Market tick for this pair
            path: Full currency path
            market_ticks: All market ticks

        Returns:
            Tuple of (pair, side, qty, market_price)
        """
        pair_base = get_base_currency(pair)
        pair_quote = get_quote_currency(pair)

        # Calculate quantity in intermediate currency from previous legs
        intermediate_qty = self._calculate_intermediate_qty(
            leg_index, path, market_ticks
        )

        # Determine the currencies we're converting between
        from_curr = path.currencies[leg_index]
        to_curr = path.currencies[leg_index + 1]

        # Determine side and quantity based on original intent and pair structure
        if self.original_side == 1:  # Original intent: BUY final currency
            # We need to convert intermediate → final (buy final, sell intermediate)
            if not is_inverted:
                # Pair is from_curr → to_curr (e.g., USD → GBP via USDGBP)
                # We're buying to_curr (the pair's base)
                leg_side = 1  # BUY base
                # We have intermediate_qty of from_curr to spend
                # Need to calculate how much base we can buy
                leg_qty = intermediate_qty / tick.mid
                market_price = tick.ask_tob  # Buying at ask
            else:
                # Pair is to_curr → from_curr (e.g., GBP → USD via GBPUSD, inverted)
                # We're selling from_curr (the pair's quote when inverted)
                # Which means selling the pair's base in normal terms
                leg_side = -1  # SELL base (to get quote)
                leg_qty = intermediate_qty
                market_price = tick.bid_tob  # Selling at bid
        else:  # Original intent: SELL final currency (original_side == -1)
            # We need to convert intermediate → final (sell final, buy intermediate)
            if not is_inverted:
                # Pair is from_curr → to_curr
                # We're selling to_curr (the pair's base)
                leg_side = -1  # SELL base
                leg_qty = intermediate_qty / tick.mid
                market_price = tick.bid_tob  # Selling at bid
            else:
                # Pair is to_curr → from_curr (inverted)
                # We're buying from_curr
                leg_side = 1  # BUY base
                leg_qty = intermediate_qty
                market_price = tick.ask_tob  # Buying at ask

        return (pair, leg_side, leg_qty, market_price)

    def _calculate_intermediate_qty(
        self,
        leg_index: int,
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
    ) -> float:
        """Calculate quantity in intermediate currency after previous legs.

        Walks through all previous legs and calculates the cumulative
        conversion using mid prices.

        Args:
            leg_index: Current leg index
            path: Currency path
            market_ticks: Market ticks for all pairs

        Returns:
            Quantity in the intermediate currency (path.currencies[leg_index])

        Example:
            Original: 1000 EUR
            After leg 0 (EURUSD @ 1.10 mid): 1000 * 1.10 = 1100 USD
            After leg 1 (USDJPY @ 150 mid): 1100 * 150 = 165000 JPY
        """
        qty = self.original_qty

        for i in range(leg_index):
            pair = path.pairs[i]
            is_inverted = path.inversions[i]
            tick = market_ticks[pair]

            # Use mid price for quantity calculations
            # (Actual execution uses bid/ask, but quantity flow uses mid)
            if not is_inverted:
                # Convert qty through this pair (multiply by rate)
                qty = qty * tick.mid
            else:
                # Inverted pair: divide by rate
                qty = qty / tick.mid

        return qty

    def validate_quantity_conservation(
        self,
        legs: list[dict],
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
        tolerance: float = 0.01,
    ) -> bool:
        """Validate that quantities conserve across legs.

        Checks that the intermediate currency quantities balance
        at each hop in the path.

        Args:
            legs: List of leg dicts with qty, side, pair
            path: Currency path
            market_ticks: Market ticks
            tolerance: Relative tolerance for conservation check (1% default)

        Returns:
            True if quantities conserve, False otherwise

        Example:
            Leg 0: BUY 1000 EUR, sell 1100 USD (EURUSD @ 1.10)
            Leg 1: BUY 880 GBP, sell 1100 USD (GBPUSD @ 1.25)
            Check: Both legs involve same USD quantity (1100)
        """
        if len(legs) < 2:
            return True  # Single leg always conserves

        # For each intermediate currency, check that input = output
        for i in range(1, len(legs)):
            prev_leg = legs[i - 1]
            curr_leg = legs[i]

            # Calculate output quantity from previous leg
            prev_pair = prev_leg["pair"]
            prev_tick = market_ticks[prev_pair]
            prev_output_qty = prev_leg["qty"] * prev_tick.mid

            # Calculate input quantity to current leg
            curr_input_qty = curr_leg["qty"]

            # Check if they match (within tolerance)
            if abs(prev_output_qty - curr_input_qty) / prev_output_qty > tolerance:
                return False

        return True
