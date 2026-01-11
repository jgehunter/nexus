"""Unit tests for PnL calculator with multi-currency support.

Tests PnL calculation methods including:
- Execution PnL (native and reporting currency)
- Hedge cost attribution
- Inventory PnL conversion
- Currency conversion logic
"""

import pytest

from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.shard.fx_converter import FXConverter
from efxbt.engine.shard.pnl_calculator import PnLCalculator, calculate_hedge_cost


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


class TestCalculateHedgeCost:
    """Test hedge cost calculation (Numba function)."""

    def test_hedge_cost_buy(self):
        """Test hedge cost when buying (crossing spread upward)."""
        # Buy 1000 with spread 0.0010
        cost = calculate_hedge_cost(1, 1000.0, 0.0010)

        # Expected: -(0.0010 / 2) * 1000 = -0.5
        assert abs(cost - (-0.5)) < 1e-8

    def test_hedge_cost_sell(self):
        """Test hedge cost when selling (crossing spread downward)."""
        # Sell 1000 with spread 0.0010
        cost = calculate_hedge_cost(-1, 1000.0, 0.0010)

        # Expected: -(0.0010 / 2) * 1000 = -0.5
        assert abs(cost - (-0.5)) < 1e-8

    def test_hedge_cost_large_spread(self):
        """Test hedge cost with larger spread."""
        # Buy 500 with spread 0.0040
        cost = calculate_hedge_cost(1, 500.0, 0.0040)

        # Expected: -(0.0040 / 2) * 500 = -1.0
        assert abs(cost - (-1.0)) < 1e-8

    def test_hedge_cost_zero_spread(self):
        """Test hedge cost with zero spread (unrealistic but edge case)."""
        cost = calculate_hedge_cost(1, 1000.0, 0.0)
        assert abs(cost) < 1e-8


class TestPnLCalculator:
    """Test PnL calculator with multi-currency support."""

    def test_calculate_execution_pnl_eurusd(self):
        """Test execution PnL for EURUSD (native=reporting)."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # EURUSD: buy at 1.1005, mid was 1.1000
        pnl_native, pnl_reporting = calc.calculate_execution_pnl(
            exec_price=1.1005,
            exec_mid=1.1000,
            qty=1000.0,
            side=1,
            pair="EURUSD",
            fx_rate=1.0,
        )

        # Expected: (1.1005 - 1.1000) * 1000 * 1 = +0.5 USD
        assert abs(pnl_native - 0.5) < 1e-8
        assert abs(pnl_reporting - 0.5) < 1e-8  # Same currency

    def test_calculate_execution_pnl_eurgbp(self):
        """Test execution PnL for EURGBP with GBP->USD conversion."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # EURGBP: sell at 0.8795, mid was 0.8800
        # GBPUSD rate = 1.25 for conversion
        pnl_native, pnl_reporting = calc.calculate_execution_pnl(
            exec_price=0.8795,
            exec_mid=0.8800,
            qty=1000.0,
            side=-1,
            pair="EURGBP",
            fx_rate=1.25,
        )

        # Expected native (GBP): (0.8795 - 0.8800) * 1000 * -1 = +0.5 GBP
        assert abs(pnl_native - 0.5) < 1e-8

        # Expected reporting (USD): 0.5 GBP * 1.25 = 0.625 USD
        assert abs(pnl_reporting - 0.625) < 1e-8

    def test_calculate_execution_pnl_usdjpy(self):
        """Test execution PnL for USDJPY with JPY->USD conversion."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # USDJPY: buy at 150.05, mid was 150.00
        # Need to invert for JPY->USD conversion: 1/150.00 = 0.00666667
        pnl_native, pnl_reporting = calc.calculate_execution_pnl(
            exec_price=150.05,
            exec_mid=150.00,
            qty=1000.0,
            side=1,
            pair="USDJPY",
            fx_rate=150.00,  # USDJPY mid (need to invert)
        )

        # Expected native (JPY): (150.05 - 150.00) * 1000 * 1 = +50.0 JPY
        assert abs(pnl_native - 50.0) < 1e-8

        # Expected reporting (USD): 50.0 JPY / 150.00 = 0.333... USD
        assert abs(pnl_reporting - (50.0 / 150.00)) < 1e-6

    def test_attribute_hedge_cost_to_trades(self):
        """Test hedge cost attribution to triggering trades."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # Create triggering trades
        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),
            create_test_trade("T002", 1704110430000, 1, 500.0, 1.1010),
        ]

        # Hedge cost: -1.0 (both native and reporting, since EURUSD)
        current_position = 1500.0  # +1000 + 500

        allocation = calc.attribute_hedge_cost_to_trades(
            hedge_cost_native=-1.0,
            hedge_cost_reporting=-1.0,
            triggering_trades=trades,
            current_position=current_position,
        )

        # Expected allocation (proportional to contribution):
        # T001: 1000/1500 * -1.0 = -0.6667
        # T002: 500/1500 * -1.0 = -0.3333
        assert "T001" in allocation
        assert "T002" in allocation
        assert abs(allocation["T001"][0] - (-0.666667)) < 1e-4  # Native
        assert abs(allocation["T001"][1] - (-0.666667)) < 1e-4  # Reporting
        assert abs(allocation["T002"][0] - (-0.333333)) < 1e-4
        assert abs(allocation["T002"][1] - (-0.333333)) < 1e-4

    def test_attribute_hedge_cost_empty_trades(self):
        """Test hedge cost attribution with no triggering trades."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        allocation = calc.attribute_hedge_cost_to_trades(
            hedge_cost_native=-1.0,
            hedge_cost_reporting=-1.0,
            triggering_trades=[],
            current_position=0.0,
        )

        assert len(allocation) == 0

    def test_attribute_hedge_cost_zero_cost(self):
        """Test hedge cost attribution with zero cost."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),
        ]

        allocation = calc.attribute_hedge_cost_to_trades(
            hedge_cost_native=0.0,
            hedge_cost_reporting=0.0,
            triggering_trades=trades,
            current_position=1000.0,
        )

        assert len(allocation) == 0

    def test_convert_inventory_pnl_eurusd(self):
        """Test inventory PnL conversion for EURUSD."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # EURUSD: native = reporting
        pnl_reporting = calc.convert_inventory_pnl(
            inventory_pnl_native=10.0, pair="EURUSD", fx_rate=1.0
        )

        assert abs(pnl_reporting - 10.0) < 1e-8

    def test_convert_inventory_pnl_eurgbp(self):
        """Test inventory PnL conversion for EURGBP."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # EURGBP: native GBP, reporting USD
        # 10 GBP * 1.25 = 12.5 USD
        pnl_reporting = calc.convert_inventory_pnl(
            inventory_pnl_native=10.0, pair="EURGBP", fx_rate=1.25
        )

        assert abs(pnl_reporting - 12.5) < 1e-8

    def test_convert_inventory_pnl_usdjpy(self):
        """Test inventory PnL conversion for USDJPY."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # USDJPY: native JPY, reporting USD
        # 150 JPY / 150.00 = 1.0 USD
        pnl_reporting = calc.convert_inventory_pnl(
            inventory_pnl_native=150.0, pair="USDJPY", fx_rate=150.00
        )

        assert abs(pnl_reporting - 1.0) < 1e-8

    def test_get_native_currency(self):
        """Test getting native currency for pairs."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        assert calc.get_native_currency("EURUSD") == "USD"
        assert calc.get_native_currency("GBPUSD") == "USD"
        assert calc.get_native_currency("USDJPY") == "JPY"
        assert calc.get_native_currency("EURGBP") == "GBP"

    def test_get_reporting_currency(self):
        """Test getting reporting currency."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        assert calc.get_reporting_currency() == "USD"

        fx_converter_eur = FXConverter("EUR")
        calc_eur = PnLCalculator(fx_converter_eur)
        assert calc_eur.get_reporting_currency() == "EUR"


class TestPnLCalculatorEdgeCases:
    """Test edge cases and error handling."""

    def test_negative_execution_pnl(self):
        """Test negative execution PnL (unfavorable fill)."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # Buy at 1.1020, mid was 1.1000 (paid above mid)
        pnl_native, pnl_reporting = calc.calculate_execution_pnl(
            exec_price=1.1020,
            exec_mid=1.1000,
            qty=1000.0,
            side=1,
            pair="EURUSD",
            fx_rate=1.0,
        )

        # Expected: (1.1020 - 1.1000) * 1000 * 1 = +2.0 (still positive!)
        # This is correct - buyer paid 2 more than mid
        assert abs(pnl_native - 2.0) < 1e-8

        # Sell at 1.0980, mid was 1.1000 (received below mid)
        pnl_native2, pnl_reporting2 = calc.calculate_execution_pnl(
            exec_price=1.0980,
            exec_mid=1.1000,
            qty=1000.0,
            side=-1,
            pair="EURUSD",
            fx_rate=1.0,
        )

        # Expected: (1.0980 - 1.1000) * 1000 * -1 = +2.0 (still positive!)
        # This is correct - seller received 2 less than mid
        assert abs(pnl_native2 - 2.0) < 1e-8

    def test_large_fx_rate(self):
        """Test with large FX rate (e.g., USDJPY)."""
        fx_converter = FXConverter("USD")
        calc = PnLCalculator(fx_converter)

        # USDJPY at 150.00, profit 1000 JPY
        pnl_reporting = calc.convert_inventory_pnl(
            inventory_pnl_native=1000.0, pair="USDJPY", fx_rate=150.00
        )

        # Expected: 1000 / 150 = 6.6667 USD
        assert abs(pnl_reporting - (1000.0 / 150.0)) < 1e-4
