"""Unit tests for currency flow tracking."""

import pytest

from efxbt.core.data.schemas import MarketTickRecord, TradeRecord
from efxbt.core.graph.schemas import CurrencyPath
from efxbt.engine.currency_flow import CurrencyFlowTracker


class TestCurrencyFlowTracker:
    """Tests for CurrencyFlowTracker class."""

    @pytest.fixture
    def simple_path_eur_usd_gbp(self):
        """Create a simple 2-hop path: EUR->USD->GBP."""
        return CurrencyPath(
            currencies=["EUR", "USD", "GBP"],
            pairs=["EURUSD", "GBPUSD"],
            inversions=[False, True],  # EURUSD normal, GBPUSD inverted
        )

    @pytest.fixture
    def market_ticks_eur_usd_gbp(self):
        """Create market ticks for EURUSD and GBPUSD."""
        return {
            "EURUSD": MarketTickRecord(
                timestamp_ms=1000,
                pair="EURUSD",
                bid_tob=1.0998,
                ask_tob=1.1002,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
            "GBPUSD": MarketTickRecord(
                timestamp_ms=1000,
                pair="GBPUSD",
                bid_tob=1.2498,
                ask_tob=1.2502,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
        }

    def test_two_hop_buy_trade_first_leg(
        self, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
    ):
        """Test first leg of BUY 1000 EURGBP trade."""
        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=1,  # BUY EUR
            qty=1000.0,
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, simple_path_eur_usd_gbp)

        # First leg: BUY 1000 EUR via EURUSD
        pair, side, qty, price = tracker.calculate_leg_parameters(
            0, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )

        assert pair == "EURUSD"
        assert side == 1  # BUY EUR (base of EURUSD)
        assert qty == 1000.0  # Original quantity
        assert price == 1.1002  # Ask price (buying)

    def test_two_hop_buy_trade_second_leg(
        self, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
    ):
        """Test second leg of BUY 1000 EURGBP trade."""
        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=1,  # BUY EUR (which means SELL GBP)
            qty=1000.0,
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, simple_path_eur_usd_gbp)

        # Second leg: Convert USD to GBP via GBPUSD (inverted)
        pair, side, qty, price = tracker.calculate_leg_parameters(
            1, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )

        assert pair == "GBPUSD"
        # After leg 0: have ~1100 USD (1000 EUR * 1.10)
        # Need to BUY GBP (final currency), which is SELL USD (since inverted)
        assert side == -1  # SELL base of GBPUSD to get GBP
        # Quantity should be ~1100 USD
        expected_usd_qty = 1000.0 * 1.10  # Mid price of EURUSD
        assert abs(qty - expected_usd_qty) < 1.0
        assert price == 1.2498  # Bid price (selling)

    def test_two_hop_sell_trade(
        self, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
    ):
        """Test SELL 1000 EURGBP trade decomposition."""
        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=-1,  # SELL EUR
            qty=1000.0,
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, simple_path_eur_usd_gbp)

        # First leg: SELL EUR via EURUSD
        pair1, side1, qty1, price1 = tracker.calculate_leg_parameters(
            0, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )

        assert pair1 == "EURUSD"
        assert side1 == -1  # SELL EUR
        assert qty1 == 1000.0
        assert price1 == 1.0998  # Bid price (selling)

        # Second leg: Convert USD to GBP
        pair2, side2, qty2, price2 = tracker.calculate_leg_parameters(
            1, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )

        assert pair2 == "GBPUSD"
        # Original intent is SELL final (GBP), which means BUY GBP here
        # With inverted pair (GBPUSD), we BUY base (GBP)
        assert side2 == 1  # BUY base
        expected_usd_qty = 1000.0 * 1.10
        assert abs(qty2 - expected_usd_qty) < 1.0

    def test_intermediate_quantity_calculation(
        self, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
    ):
        """Test calculation of intermediate currency quantities."""
        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=1,
            qty=1000.0,
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, simple_path_eur_usd_gbp)

        # After 0 legs: should be original quantity (1000 EUR)
        qty_0 = tracker._calculate_intermediate_qty(
            0, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )
        assert qty_0 == 1000.0

        # After 1 leg (EURUSD): should be in USD
        qty_1 = tracker._calculate_intermediate_qty(
            1, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )
        # 1000 EUR * 1.10 (mid) = 1100 USD
        assert abs(qty_1 - 1100.0) < 1.0

    def test_three_hop_path(self):
        """Test 3-hop path EUR->USD->JPY->GBP."""
        path = CurrencyPath(
            currencies=["EUR", "USD", "JPY", "GBP"],
            pairs=["EURUSD", "USDJPY", "GBPJPY"],
            inversions=[False, False, True],
        )

        ticks = {
            "EURUSD": MarketTickRecord(
                timestamp_ms=1000,
                pair="EURUSD",
                bid_tob=1.0998,
                ask_tob=1.1002,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
            "USDJPY": MarketTickRecord(
                timestamp_ms=1000,
                pair="USDJPY",
                bid_tob=149.98,
                ask_tob=150.02,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
            "GBPJPY": MarketTickRecord(
                timestamp_ms=1000,
                pair="GBPJPY",
                bid_tob=187.48,
                ask_tob=187.52,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
        }

        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=1,
            qty=1000.0,
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, path)

        # Test all three legs can be calculated
        for i in range(3):
            pair, side, qty, price = tracker.calculate_leg_parameters(i, path, ticks)
            assert pair in ["EURUSD", "USDJPY", "GBPJPY"]
            assert side in [1, -1]
            assert qty > 0
            assert price > 0

    def test_quantity_conservation_validation(
        self, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
    ):
        """Test quantity conservation validation."""
        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=1,
            qty=1000.0,
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, simple_path_eur_usd_gbp)

        # Build legs
        legs = []
        for i in range(2):
            pair, side, qty, price = tracker.calculate_leg_parameters(
                i, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
            )
            legs.append({
                "pair": pair,
                "side": side,
                "qty": qty,
                "price": price,
            })

        # Validate conservation
        is_valid = tracker.validate_quantity_conservation(
            legs, simple_path_eur_usd_gbp, market_ticks_eur_usd_gbp
        )

        # Should be approximately conserved (within tolerance)
        assert is_valid

    def test_inverted_first_leg(self):
        """Test case where first leg pair is inverted."""
        # Path EUR->USD but using USDEUR (inverted)
        path = CurrencyPath(
            currencies=["EUR", "USD"],
            pairs=["USDEUR"],  # Inverted
            inversions=[True],
        )

        ticks = {
            "USDEUR": MarketTickRecord(
                timestamp_ms=1000,
                pair="USDEUR",
                bid_tob=0.9090,  # 1/1.10
                ask_tob=0.9092,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
        }

        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURUSD",
            side=1,  # BUY EUR
            qty=1000.0,
            price=1.10,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, path)

        pair, side, qty, price = tracker.calculate_leg_parameters(0, path, ticks)

        assert pair == "USDEUR"
        # To buy EUR (quote of USDEUR), we sell USD (base)
        assert side == -1  # SELL base
        # Quantity should be calculated based on how much USD needed
        assert qty > 0

    def test_direct_pair_single_leg(self):
        """Test that a direct pair results in single leg."""
        path = CurrencyPath(
            currencies=["EUR", "USD"],
            pairs=["EURUSD"],
            inversions=[False],
        )

        ticks = {
            "EURUSD": MarketTickRecord(
                timestamp_ms=1000,
                pair="EURUSD",
                bid_tob=1.0998,
                ask_tob=1.1002,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
        }

        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURUSD",
            side=1,
            qty=1000.0,
            price=1.10,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, path)

        # Only one leg
        pair, side, qty, price = tracker.calculate_leg_parameters(0, path, ticks)

        assert pair == "EURUSD"
        assert side == 1
        assert qty == 1000.0
        assert price == 1.1002  # Ask


class TestCurrencyFlowEdgeCases:
    """Test edge cases in currency flow calculations."""

    def test_very_small_quantity(self):
        """Test handling of very small quantities."""
        path = CurrencyPath(
            currencies=["EUR", "USD", "GBP"],
            pairs=["EURUSD", "GBPUSD"],
            inversions=[False, True],
        )

        ticks = {
            "EURUSD": MarketTickRecord(
                timestamp_ms=1000,
                pair="EURUSD",
                bid_tob=1.0998,
                ask_tob=1.1002,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
            "GBPUSD": MarketTickRecord(
                timestamp_ms=1000,
                pair="GBPUSD",
                bid_tob=1.2498,
                ask_tob=1.2502,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            ),
        }

        trade = TradeRecord(
            timestamp_ms=1000,
            pair="EURGBP",
            side=1,
            qty=0.01,  # Very small
            price=0.88,
            trade_id="T1",
        )

        tracker = CurrencyFlowTracker(trade, path)

        # Should handle small quantities without errors
        for i in range(2):
            pair, side, qty, price = tracker.calculate_leg_parameters(i, path, ticks)
            assert qty >= 0
