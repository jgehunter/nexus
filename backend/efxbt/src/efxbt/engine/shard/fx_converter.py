"""FX conversion utilities for PnL normalization.

Handles conversion of PnL from native currency (quote currency of each pair)
to a single reporting currency for aggregation.
"""

from ...core.config.universe import get_quote_currency


class FXConverter:
    """Converter for normalizing PnL to reporting currency.

    Each currency pair's PnL is naturally in its quote currency:
    - EURUSD PnL → USD
    - GBPUSD PnL → USD
    - USDJPY PnL → JPY
    - EURGBP PnL → GBP

    For aggregation, all PnL must be converted to a single reporting currency.
    """

    def __init__(self, reporting_currency: str):
        """Initialize converter.

        Args:
            reporting_currency: Target currency for PnL reporting (e.g., "USD", "EUR")
        """
        self.reporting_currency = reporting_currency.upper()

    def get_native_currency(self, pair: str) -> str:
        """Get native currency for a pair's PnL (quote currency).

        Args:
            pair: Currency pair (e.g., "EURUSD")

        Returns:
            Quote currency (e.g., "USD" for EURUSD)

        Example:
            >>> converter = FXConverter("USD")
            >>> converter.get_native_currency("EURUSD")
            "USD"
            >>> converter.get_native_currency("USDJPY")
            "JPY"
        """
        return get_quote_currency(pair)

    def needs_conversion(self, pair: str) -> bool:
        """Check if PnL from this pair needs currency conversion.

        Args:
            pair: Currency pair

        Returns:
            True if native currency != reporting currency

        Example:
            >>> converter = FXConverter("USD")
            >>> converter.needs_conversion("EURUSD")  # Native is USD
            False
            >>> converter.needs_conversion("USDJPY")  # Native is JPY
            True
        """
        native = self.get_native_currency(pair)
        return native != self.reporting_currency

    def get_conversion_pair(self, pair: str) -> tuple[str, bool] | None:
        """Determine conversion pair needed for PnL conversion.

        Args:
            pair: Currency pair whose PnL needs conversion

        Returns:
            Tuple of (conversion_pair, is_inverted) or None if no conversion needed
            - conversion_pair: Pair to use for FX rate (e.g., "GBPUSD")
            - is_inverted: True if need to invert the rate

        Example:
            >>> converter = FXConverter("USD")
            >>> converter.get_conversion_pair("EURGBP")  # GBP -> USD
            ("GBPUSD", False)  # Use GBPUSD rate directly

            >>> converter.get_conversion_pair("USDJPY")  # JPY -> USD
            ("USDJPY", True)  # Use 1/USDJPY rate (invert)

            >>> converter.get_conversion_pair("EURUSD")  # Already in USD
            None
        """
        native = self.get_native_currency(pair)

        if native == self.reporting_currency:
            return None  # No conversion needed

        # Try direct pair: native + reporting (e.g., GBPUSD for GBP->USD)
        direct_pair = native + self.reporting_currency
        # Try inverted pair: reporting + native (e.g., USDJPY for JPY->USD)
        inverted_pair = self.reporting_currency + native

        # We prefer the direct pair if available, but will accept either
        # The caller (market fetcher) will determine which is available
        # For now, return the format that makes sense
        if native < self.reporting_currency:
            # Native alphabetically before reporting: use direct pair
            return (direct_pair, False)
        else:
            # Native alphabetically after reporting: use inverted pair
            return (inverted_pair, True)

    def convert_pnl(
        self,
        pnl_native: float,
        fx_rate: float,
        pair: str,
    ) -> tuple[float, float]:
        """Convert PnL from native currency to reporting currency.

        Args:
            pnl_native: PnL in native currency (quote currency of pair)
            fx_rate: FX rate for conversion (from the actual traded pair when possible)
            pair: Original currency pair (to determine conversion direction)

        Returns:
            Tuple of (pnl_reporting, actual_fx_rate_used)

        Example:
            >>> converter = FXConverter("USD")
            >>> # EURGBP PnL is in GBP, convert to USD
            >>> # GBPUSD rate = 1.25 (1 GBP = 1.25 USD)
            >>> pnl_reporting, rate = converter.convert_pnl(100.0, 1.25, "EURGBP")
            >>> pnl_reporting
            125.0  # 100 GBP * 1.25 = 125 USD

            >>> # USDJPY PnL is in JPY, convert to USD
            >>> # USDJPY rate = 150.0 (1 USD = 150 JPY)
            >>> # Need to invert: 1 JPY = 1/150 USD
            >>> pnl_reporting, rate = converter.convert_pnl(15000.0, 150.0, "USDJPY")
            >>> pnl_reporting
            100.0  # 15000 JPY / 150 = 100 USD
        """
        native = self.get_native_currency(pair)

        if native == self.reporting_currency:
            # No conversion needed
            return pnl_native, 1.0

        # Check if the original trading pair can be used for conversion
        # This handles cases like USDJPY where we need JPY->USD conversion
        from ...core.config.universe import get_base_currency

        base = get_base_currency(pair)
        quote = native  # We already know quote = native

        # If the pair contains both native and reporting currencies, use it
        if self.reporting_currency in [base, quote]:
            # The fx_rate is from the actual pair
            if self.reporting_currency == base:
                # Reporting currency is base (e.g., USDJPY for JPY->USD)
                # Rate tells us: 1 USD = X JPY
                # To convert JPY to USD: divide by rate
                actual_rate = 1.0 / fx_rate if fx_rate != 0 else 0.0
                pnl_reporting = pnl_native * actual_rate
            else:
                # Reporting currency is quote (e.g., EURGBP + GBPUSD for GBP->USD)
                # This shouldn't happen when using the original pair
                # Fall back to standard logic
                conversion_info = self.get_conversion_pair(pair)
                if conversion_info is None:
                    return pnl_native, 1.0
                _, is_inverted = conversion_info
                if is_inverted:
                    actual_rate = 1.0 / fx_rate if fx_rate != 0 else 0.0
                    pnl_reporting = pnl_native * actual_rate
                else:
                    actual_rate = fx_rate
                    pnl_reporting = pnl_native * fx_rate
        else:
            # Need to use a different pair for conversion
            conversion_info = self.get_conversion_pair(pair)
            if conversion_info is None:
                return pnl_native, 1.0

            _, is_inverted = conversion_info

            if is_inverted:
                # Need to invert the rate
                actual_rate = 1.0 / fx_rate if fx_rate != 0 else 0.0
                pnl_reporting = pnl_native * actual_rate
            else:
                # Use rate directly
                actual_rate = fx_rate
                pnl_reporting = pnl_native * fx_rate

        return pnl_reporting, actual_rate

    def get_required_conversion_pairs(self, pairs: list[str]) -> set[str]:
        """Get all conversion pairs needed for a list of trading pairs.

        Args:
            pairs: List of currency pairs being traded

        Returns:
            Set of conversion pairs needed (may be empty if all pairs already in reporting currency)

        Example:
            >>> converter = FXConverter("USD")
            >>> converter.get_required_conversion_pairs(["EURUSD", "EURGBP", "USDJPY"])
            {"GBPUSD", "USDJPY"}  # Need these for conversion
        """
        conversion_pairs = set()

        for pair in pairs:
            conversion_info = self.get_conversion_pair(pair)
            if conversion_info is not None:
                conversion_pair, _ = conversion_info
                conversion_pairs.add(conversion_pair)

        return conversion_pairs
