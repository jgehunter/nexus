"""Core decrossing engine for FX trade decomposition.

Decomposes cross-pair trades into direct-pair legs using currency graph pathfinding,
with price backsolving to match original cross rates exactly.
"""

from decimal import ROUND_HALF_EVEN, Decimal

from ..core.config.run_config import DecrossConfig
from ..core.config.universe import get_base_currency, get_quote_currency
from ..core.data.schemas import DecrossedTradeRecord, MarketTickRecord, TradeRecord
from ..core.graph.currency_graph import CurrencyGraphBuilder
from ..core.graph.pathfinding import PathFinder
from ..core.graph.schemas import CurrencyGraph, CurrencyPath
from .currency_flow import CurrencyFlowTracker


class DecrossingEngine:
    """Core engine for decomposing cross-pair trades into direct legs.

    Takes trade records and market tick data, finds optimal currency paths,
    and decomposes cross-pair trades while preserving original execution prices.
    """

    def __init__(
        self,
        graph: CurrencyGraph,
        path_finder: PathFinder,
        config: DecrossConfig,
    ):
        """Initialize decrossing engine.

        Args:
            graph: Currency graph defining tradeable pairs
            path_finder: Pathfinder for finding decomposition routes
            config: Decrossing configuration (rounding, min qty, etc.)
        """
        self.graph = graph
        self.path_finder = path_finder
        self.config = config

        # Build set of direct pairs for quick lookup
        self._direct_pairs: set[str] = {
            edge.pair for edge in graph.edges if not edge.is_inverted
        }

    def decross_trade(
        self,
        trade: TradeRecord,
        market_ticks: dict[str, MarketTickRecord],
    ) -> list[DecrossedTradeRecord]:
        """Decompose a single trade into direct-pair legs.

        Args:
            trade: Original trade to decross
            market_ticks: Dict of {pair: tick} at trade timestamp (from ASOF join)

        Returns:
            List of DecrossedTradeRecord:
            - Length 1 if already direct pair (passthrough)
            - Length N if cross pair (decomposed along path)

        Raises:
            ValueError: If no path exists for cross pair or market data missing
        """
        pair = trade.pair.upper()

        # Check if already a direct pair
        if self._is_direct_pair(pair):
            return [self._create_passthrough_leg(trade)]

        # Find decomposition path for cross pair
        base_curr = get_base_currency(pair)
        quote_curr = get_quote_currency(pair)

        path = self.path_finder.find_path(
            base_curr, quote_curr, self.config.max_path_length
        )

        if path is None:
            raise ValueError(
                f"No decrossing path found for {pair} "
                f"(from {base_curr} to {quote_curr}). "
                f"Available pairs: {sorted(self._direct_pairs)}"
            )

        # Decompose into legs
        legs = self._decompose_to_legs(trade, path, market_ticks)

        return legs

    def _is_direct_pair(self, pair: str) -> bool:
        """Check if pair is directly tradeable (exists in market dataset).

        Args:
            pair: Currency pair to check

        Returns:
            True if pair is in graph's direct pairs
        """
        return pair in self._direct_pairs

    def _create_passthrough_leg(self, trade: TradeRecord) -> DecrossedTradeRecord:
        """Create single leg for direct-pair trade (no decomposition needed).

        Args:
            trade: Original direct-pair trade

        Returns:
            DecrossedTradeRecord with is_direct=True
        """
        base = get_base_currency(trade.pair)
        quote = get_quote_currency(trade.pair)

        return DecrossedTradeRecord(
            # Original fields
            timestamp_ms=trade.timestamp_ms,
            pair=trade.pair,
            side=trade.side,
            qty=trade.qty,
            price=trade.price,
            trade_id=trade.trade_id,
            order_id=trade.order_id,
            # Decrossing metadata
            source_trade_id=trade.trade_id,
            source_pair=trade.pair,
            source_price=trade.price,
            leg_index=0,
            leg_count=1,
            path=[base, quote],
            is_direct=True,
        )

    def _decompose_to_legs(
        self,
        trade: TradeRecord,
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
    ) -> list[DecrossedTradeRecord]:
        """Decompose cross trade along a currency path.

        This implements the critical logic:
        1. Calculate quantities for each leg (currency flow)
        2. Get market-based prices from ticks
        3. Backsolve prices to match original cross rate
        4. Apply deterministic rounding
        5. Filter zero-quantity legs

        Args:
            trade: Original cross-pair trade
            path: Currency path to decompose along
            market_ticks: Market ticks for direct pairs

        Returns:
            List of DecrossedTradeRecord legs

        Example:
            Trade: BUY 1000 EURGBP @ 0.8500
            Path: EUR -> USD -> GBP (via EURUSD, GBPUSD)

            Leg 0: BUY 1000 EUR vs USD (EURUSD)
            Leg 1: SELL (1000 * EURUSD_price) USD vs GBP (GBPUSD, inverted)

            Prices backsolved so effective rate = 0.8500
        """
        # Verify we have market ticks for all pairs in path
        for pair in path.pairs:
            if pair not in market_ticks:
                raise ValueError(
                    f"Missing market tick for {pair} at timestamp {trade.timestamp_ms}. "
                    f"ASOF join may have failed or market data gap exists."
                )

        # Step 1: Calculate quantities for each leg based on currency flow
        leg_data = self._calculate_leg_quantities(trade, path, market_ticks)

        # Step 2: Backsolve prices to match original cross rate
        leg_data = self._backsolve_prices(leg_data, trade.price, path, market_ticks)

        # Step 3: Build DecrossedTradeRecord objects with rounding and filtering
        legs: list[DecrossedTradeRecord] = []

        for i, leg_info in enumerate(leg_data):
            # Apply deterministic rounding
            rounded_qty = self._round_quantity(leg_info["qty"])

            # Filter out zero-quantity legs
            if rounded_qty < self.config.min_leg_qty:
                continue

            leg = DecrossedTradeRecord(
                # Original fields
                timestamp_ms=trade.timestamp_ms,
                pair=leg_info["pair"],
                side=leg_info["side"],
                qty=rounded_qty,
                price=leg_info["price"],
                trade_id=f"{trade.trade_id}_leg{i}",
                order_id=trade.order_id,
                # Decrossing metadata
                source_trade_id=trade.trade_id,
                source_pair=trade.pair,
                source_price=trade.price,
                leg_index=i,
                leg_count=len(leg_data),
                path=path.currencies,
                is_direct=False,
            )
            legs.append(leg)

        return legs

    def _calculate_leg_quantities(
        self,
        trade: TradeRecord,
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
    ) -> list[dict]:
        """Calculate quantity and side for each leg based on currency flow.

        Uses CurrencyFlowTracker to properly handle multi-hop currency conversions,
        ensuring correct sides, quantities, and prices for each leg.

        Args:
            trade: Original trade
            path: Decomposition path
            market_ticks: Market ticks for pricing

        Returns:
            List of dicts with keys: pair, side, qty, market_price

        Example:
            BUY 1000 EURGBP @ 0.8500
            Path: EUR->USD->GBP via [EURUSD, GBPUSD]

            Leg 0: EURUSD
                - BUY 1000 EUR (= sell USD)
                - qty=1000, side=+1
                - market_price=1.1000 (ask for buying EUR)

            Leg 1: GBPUSD (inverted to get USD->GBP)
                - SELL 1100 USD (= buy GBP)
                - Need to BUY GBP (to complete EURGBP purchase)
                - qty=880 GBP, side=+1
                - market_price=1.2500 (ask for buying GBP)
        """
        # Initialize currency flow tracker with original trade
        tracker = CurrencyFlowTracker(trade, path)

        # Calculate parameters for each leg using the tracker
        legs = []
        for i in range(len(path.pairs)):
            pair, side, qty, market_price = tracker.calculate_leg_parameters(
                i, path, market_ticks
            )

            legs.append({
                "pair": pair,
                "side": side,
                "qty": qty,
                "market_price": market_price,
                "price": market_price,  # Will be backsolved
            })

        # Validate quantity conservation
        is_valid = tracker.validate_quantity_conservation(legs, path, market_ticks)
        if not is_valid:
            raise ValueError(
                f"Quantity conservation check failed for trade {trade.trade_id}. "
                f"Intermediate currency quantities do not balance across legs."
            )

        return legs

    def _backsolve_prices(
        self,
        legs: list[dict],
        original_price: float,
        path: CurrencyPath,
        market_ticks: dict[str, MarketTickRecord],
    ) -> list[dict]:
        """Adjust leg prices proportionally to match original cross rate.

        The market-based leg prices may not exactly reconstruct the original
        cross price. We need to adjust them proportionally.

        Args:
            legs: List of leg dicts with market_price
            original_price: Original cross trade price
            path: Currency path
            market_ticks: Market ticks

        Returns:
            Updated legs with backsolved prices

        Example:
            Original: EURGBP @ 0.8500
            Market: EURUSD @ 1.1000, GBPUSD @ 1.2500
            Implied: 1.1000 / 1.2500 = 0.8800 (≠ 0.8500!)

            Adjustment factor = 0.8500 / 0.8800 = 0.9659
            Apply to each leg price proportionally
        """
        if len(legs) == 0:
            return legs

        # Calculate implied cross rate from market-based leg prices
        # For EUR->USD->GBP: implied = EURUSD / GBPUSD
        # This is path-dependent and needs careful handling

        # Simplified approach: calculate effective cross rate from leg prices
        # then adjust all prices by ratio

        # For now, calculate implied rate by walking through path
        implied_rate = 1.0
        for leg, is_inverted in zip(legs, path.inversions):
            if is_inverted:
                implied_rate /= leg["market_price"]
            else:
                implied_rate *= leg["market_price"]

        # Adjustment factor
        if abs(implied_rate) < 1e-10:
            raise ValueError("Implied rate is zero, cannot backsolve prices")

        adjustment_factor = original_price / implied_rate

        # Apply adjustment to all leg prices
        for leg in legs:
            leg["price"] = leg["market_price"] * adjustment_factor

        return legs

    def _round_quantity(self, qty: float) -> float:
        """Apply deterministic rounding to quantity.

        Uses banker's rounding (round-half-to-even) for reproducibility.

        Args:
            qty: Quantity to round

        Returns:
            Rounded quantity (2 decimal places)
        """
        if self.config.use_banker_rounding:
            # Banker's rounding to 2 decimal places
            return float(Decimal(str(qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))
        else:
            # Standard rounding
            return round(qty, 2)
