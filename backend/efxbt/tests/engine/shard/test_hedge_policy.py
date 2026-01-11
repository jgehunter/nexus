"""Unit tests for hedge policies.

Tests hedge policy evaluation logic for different risk management strategies.
"""

import pytest

from efxbt.engine.shard.hedge_policy import (
    AggressiveHedgePolicy,
    PassiveHedgePolicy,
    create_hedge_policy,
)
from efxbt.engine.shard.market_fetcher import MarketSnapshot
from efxbt.engine.shard.state import ShardState


class TestAggressiveHedgePolicy:
    """Test aggressive hedge policy (flatten immediately when outside band)."""

    def test_no_hedge_within_band(self):
        """Test no hedge triggered when position within risk band."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=500.0,  # Within 1000 band
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        config = {"risk_band_qty": 1000.0, "hedge_mode": "full"}

        hedges = policy.evaluate(state, snapshot, config)

        assert len(hedges) == 0  # No hedge

    def test_full_hedge_outside_band_long(self):
        """Test full hedge when long position exceeds band."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=1500.0,  # Exceeds 1000 band
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        config = {"risk_band_qty": 1000.0, "hedge_mode": "full"}

        hedges = policy.evaluate(state, snapshot, config)

        # Expect SELL 1500 @ bid (full flatten)
        assert len(hedges) == 1
        assert hedges[0]["side"] == -1  # SELL
        assert abs(hedges[0]["qty"] - 1500.0) < 1e-8
        assert abs(hedges[0]["price"] - 1.0998) < 1e-8  # Bid
        assert "hedge_" in hedges[0]["trade_id"]

    def test_full_hedge_outside_band_short(self):
        """Test full hedge when short position exceeds band."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=-1500.0,  # Exceeds 1000 band (short)
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        config = {"risk_band_qty": 1000.0, "hedge_mode": "full"}

        hedges = policy.evaluate(state, snapshot, config)

        # Expect BUY 1500 @ ask (full flatten)
        assert len(hedges) == 1
        assert hedges[0]["side"] == 1  # BUY
        assert abs(hedges[0]["qty"] - 1500.0) < 1e-8
        assert abs(hedges[0]["price"] - 1.1002) < 1e-8  # Ask

    def test_partial_hedge_mode(self):
        """Test partial hedge mode (hedge to band edge)."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=1500.0,
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        config = {"risk_band_qty": 1000.0, "hedge_mode": "partial"}

        hedges = policy.evaluate(state, snapshot, config)

        # Expect SELL 500 @ bid (partial to band edge)
        # 1500 - 1000 = 500
        assert len(hedges) == 1
        assert hedges[0]["side"] == -1
        assert abs(hedges[0]["qty"] - 500.0) < 1e-8

    def test_default_config_values(self):
        """Test policy with default configuration values."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=1500.0,
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        # Empty config uses defaults: risk_band_qty=1000, hedge_mode="full"
        hedges = policy.evaluate(state, snapshot, {})

        assert len(hedges) == 1
        assert hedges[0]["side"] == -1
        assert abs(hedges[0]["qty"] - 1500.0) < 1e-8  # Full flatten

    def test_exact_band_edge_no_hedge(self):
        """Test no hedge when position exactly at band edge."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=1000.0,  # Exactly at band
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        config = {"risk_band_qty": 1000.0, "hedge_mode": "full"}

        hedges = policy.evaluate(state, snapshot, config)

        assert len(hedges) == 0  # No hedge

    def test_custom_risk_band(self):
        """Test with custom risk band quantity."""
        policy = AggressiveHedgePolicy()

        state = ShardState(
            pair="EURUSD",
            date="20240101",
            net_position=1800.0,
        )

        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )

        config = {"risk_band_qty": 2000.0, "hedge_mode": "full"}

        hedges = policy.evaluate(state, snapshot, config)

        # Position 1800 < band 2000, no hedge
        assert len(hedges) == 0


class TestPassiveHedgePolicy:
    """Test passive hedge policy (not yet implemented)."""

    def test_not_implemented(self):
        """Test that passive policy raises NotImplementedError."""
        policy = PassiveHedgePolicy()

        state = ShardState(pair="EURUSD", date="20240101", net_position=1500.0)
        snapshot = MarketSnapshot(
            timestamp_ms=1704110400000,
            pair="EURUSD",
            mid=1.1000,
            bid=1.0998,
            ask=1.1002,
            spread=0.0004,
            fx_rate=1.0,
        )
        config = {}

        with pytest.raises(NotImplementedError):
            policy.evaluate(state, snapshot, config)


class TestCreateHedgePolicy:
    """Test hedge policy factory function."""

    def test_create_aggressive_policy(self):
        """Test creating aggressive policy by name."""
        policy = create_hedge_policy("aggressive")
        assert isinstance(policy, AggressiveHedgePolicy)

    def test_create_passive_policy(self):
        """Test creating passive policy by name."""
        policy = create_hedge_policy("passive")
        assert isinstance(policy, PassiveHedgePolicy)

    def test_invalid_policy_name(self):
        """Test error handling for invalid policy name."""
        with pytest.raises(ValueError, match="Unknown hedge policy"):
            create_hedge_policy("invalid_policy")
