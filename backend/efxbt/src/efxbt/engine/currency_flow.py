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

    Side Convention:
        Uses HOUSE's perspective throughout:
        - side = +1: House BUYS base currency
        - side = -1: House SELLS base currency
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
        and quantity. Uses mid price for all legs (backsolving will adjust
        the last leg to match original rate).

        Args:
            pair: Direct pair for this leg
            is_inverted: Whether the pair is inverted relative to path
            tick: Market tick for the pair

        Returns:
            Tuple of (pair, side, qty, market_price)
        """
        pair_base = get_base_currency(pair)
        pair_quote = get_quote_currency(pair)

        if self.original_side == 1:  # BUY base currency of original trade
            # We're buying the base currency, selling the quote
            if not is_inverted:  # EURUSD: EUR is base
                # BUY EUR (base of EURUSD)
                leg_side = 1
                leg_qty = self.original_qty
                market_price = tick.mid  # Use mid price
            else:  # Path is inverted relative to pair
                # To buy the original base (which is pair's quote), we SELL pair's base
                leg_side = -1
                # Need to calculate pair base quantity needed
                leg_qty = self.original_qty / tick.mid
                market_price = tick.mid  # Use mid price
        else:  # SELL base currency of original trade (original_side == -1)
            if not is_inverted:  # EURUSD: EUR is base
                # SELL EUR (base of EURUSD)
                leg_side = -1
                leg_qty = self.original_qty
                market_price = tick.mid  # Use mid price
            else:  # Path is inverted relative to pair
                # To sell the original base (which is pair's quote), we BUY pair's base
                leg_side = 1
                leg_qty = self.original_qty / tick.mid
                market_price = tick.mid  # Use mid price

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

        Currency flow analysis:
        - intermediate_qty is in path.currencies[leg_index] (the "from" currency)
        - leg_qty must be in the BASE currency of the pair

        For non-inverted edge (from_curr→to_curr via pair):
            - pair = from_curr + to_curr (base=from_curr, quote=to_curr)
            - intermediate_qty is in from_curr = base of pair
            - leg_qty = intermediate_qty (already in base currency)

        For inverted edge (from_curr→to_curr via pair):
            - pair = to_curr + from_curr (base=to_curr, quote=from_curr)
            - intermediate_qty is in from_curr = quote of pair
            - leg_qty = intermediate_qty / mid (convert quote to base)
        """
        pair_base = get_base_currency(pair)
        pair_quote = get_quote_currency(pair)

        # Calculate quantity in intermediate currency from previous legs
        # This gives us quantity in path.currencies[leg_index]
        intermediate_qty = self._calculate_intermediate_qty(
            leg_index, path, market_ticks
        )

        # Determine the currencies we're converting between
        from_curr = path.currencies[leg_index]
        to_curr = path.currencies[leg_index + 1]

        # Determine side and quantity based on original intent and pair structure
        if self.original_side == 1:  # Original intent: BUY base of cross pair
            # Money flows backwards through path: we acquire base, pay with quote
            if not is_inverted:
                # Non-inverted: pair base = from_curr
                # We BUY base (from_curr) with quote (to_curr)
                # But for intermediate legs, we're providing from_curr to acquire earlier currencies
                # Actually we need to SELL from_curr to get what we need
                leg_side = 1  # BUY base (acquiring the from_curr we need)
                # intermediate_qty is in from_curr = base of pair
                leg_qty = intermediate_qty  # Already in base currency
                market_price = tick.mid  # Use mid for quantity calc
            else:
                # Inverted: pair base = to_curr, pair quote = from_curr
                # We SELL base (to_curr) to provide quote (from_curr)
                leg_side = -1  # SELL base
                # intermediate_qty is in from_curr = quote of pair
                # Convert from quote to base: base_qty = quote_qty / rate
                leg_qty = intermediate_qty / tick.mid
                market_price = tick.mid  # Use mid for quantity calc
        else:  # Original intent: SELL base of cross pair (original_side == -1)
            # Money flows forward through path: we sell base, receive quote
            if not is_inverted:
                # Non-inverted: pair base = from_curr
                # We SELL base (from_curr) to get quote (to_curr)
                leg_side = -1  # SELL base
                # intermediate_qty is in from_curr = base of pair
                leg_qty = intermediate_qty  # Already in base currency
                market_price = tick.mid  # Use mid for quantity calc
            else:
                # Inverted: pair base = to_curr, pair quote = from_curr
                # We BUY base (to_curr) with quote (from_curr)
                leg_side = 1  # BUY base
                # intermediate_qty is in from_curr = quote of pair
                # Convert from quote to base: base_qty = quote_qty / rate
                leg_qty = intermediate_qty / tick.mid
                market_price = tick.mid  # Use mid for quantity calc

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

        Checks that each leg's quantity matches the expected quantity based on
        the currency flow through the path.

        Args:
            legs: List of leg dicts with qty, side, pair
            path: Currency path
            market_ticks: Market ticks
            tolerance: Relative tolerance for conservation check (1% default)

        Returns:
            True if quantities conserve, False otherwise

        Example:
            BUY 1000 EURGBP via EUR→USD→GBP (EURUSD @ 1.10, GBPUSD @ 1.25)
            Leg 0: BUY 1000 EUR via EURUSD
            Leg 1: SELL 880 GBP via GBPUSD (1000 * 1.10 / 1.25 = 880)
            Check: Leg quantities match expected flow
        """
        if len(legs) < 2:
            return True  # Single leg always conserves

        # Validate each leg's quantity matches expected from currency flow
        for i, leg in enumerate(legs):
            is_inverted = path.inversions[i]
            tick = market_ticks[leg["pair"]]

            if i == 0:
                # First leg: quantity should be original_qty or original_qty / mid for inverted
                if not is_inverted:
                    expected_qty = self.original_qty
                else:
                    expected_qty = self.original_qty / tick.mid
            else:
                # Intermediate/final legs: calculate from intermediate quantity
                # intermediate_qty is in path.currencies[i]
                intermediate_qty = self._calculate_intermediate_qty(i, path, market_ticks)

                if not is_inverted:
                    # Non-inverted: intermediate_qty is in base of pair
                    expected_qty = intermediate_qty
                else:
                    # Inverted: intermediate_qty is in quote of pair, need to convert to base
                    expected_qty = intermediate_qty / tick.mid

            # Check if actual matches expected
            actual_qty = leg["qty"]
            if expected_qty == 0:
                return False
            if abs(actual_qty - expected_qty) / expected_qty > tolerance:
                return False

        return True
