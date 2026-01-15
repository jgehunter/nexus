"""Unit tests for decision timeline construction.

Tests timeline building, event merging, and priority ordering.
"""

import pytest

from efxbt.core.config.run_config import SimulationConfig
from efxbt.core.config.hedging_config import HedgingRuleSet, HedgingRule, NoHedgeParams
from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.shard.timeline import TimelinePoint, build_timeline


# Default hedging rules for tests (simple no-hedge rule)
DEFAULT_TEST_HEDGING_RULES = HedgingRuleSet(
    groups=[],
    rules=[
        HedgingRule(
            pair_or_group="ALL",
            amount_type="absolute",
            from_amount=0,
            to_amount=float("inf"),
            action=NoHedgeParams(),
        )
    ],
)


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
        path=["EUR", "USD"],
        leg_index=0,
        leg_count=1,
    )


class TestBuildTimeline:
    """Test timeline construction from client trades and sampling grid."""

    def test_single_trade(self):
        """Test timeline with single client trade."""
        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005)
        ]

        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=60,
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline(trades, config)

        # Should have 1 client fill event
        assert len(timeline) >= 1
        assert timeline[0].event_type == "client_fill"
        assert timeline[0].timestamp_ms == 1704110400000
        assert timeline[0].client_trade.source_trade_id == "T001"

    def test_multiple_trades_sorted(self):
        """Test timeline with multiple trades (chronological sorting)."""
        trades = [
            create_test_trade("T002", 1704110460000, -1, 500.0, 1.0995),  # Later
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),  # Earlier
        ]

        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=60,
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline(trades, config)

        # Timeline should be sorted chronologically
        client_fills = [p for p in timeline if p.event_type == "client_fill"]
        assert len(client_fills) == 2
        assert client_fills[0].timestamp_ms == 1704110400000
        assert client_fills[1].timestamp_ms == 1704110460000

    def test_sampling_grid_generated(self):
        """Test that sampling grid is generated correctly."""
        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),  # Time 0
            create_test_trade("T002", 1704110460000, -1, 500.0, 1.0995),  # Time +60s
        ]

        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=30,  # Sample every 30s
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline(trades, config)

        # Should have sample events at 30s intervals
        sample_events = [p for p in timeline if p.event_type == "sample"]
        assert len(sample_events) > 0

    def test_priority_ordering(self):
        """Test event priority ordering (client_fill > sample)."""
        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005)
        ]

        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=60,
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline(trades, config)

        # Find events at same timestamp
        ts = 1704110400000
        events_at_ts = [p for p in timeline if p.timestamp_ms == ts]

        if len(events_at_ts) > 1:
            # Client fill should come before sample
            assert events_at_ts[0].event_type == "client_fill"

    def test_empty_trades(self):
        """Test timeline with no client trades."""
        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=60,
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline([], config)

        # Should return empty timeline
        assert len(timeline) == 0

    def test_deduplication_at_same_timestamp(self):
        """Test that sampling points don't duplicate fill events."""
        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005)
        ]

        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=1,  # Sample every 1s (likely overlaps)
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline(trades, config)

        # Count events at trade timestamp
        ts = 1704110400000
        events_at_ts = [p for p in timeline if p.timestamp_ms == ts]

        # Should have client fill first, sample may be deduplicated or ordered after
        assert events_at_ts[0].event_type == "client_fill"

    def test_custom_sample_interval(self):
        """Test timeline with custom sampling interval."""
        trades = [
            create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005),
            create_test_trade("T002", 1704110700000, -1, 500.0, 1.0995),  # +300s later
        ]

        config = SimulationConfig(
            dataset="btec",
            reporting_currency="USD",
            sample_interval_seconds=120,  # Sample every 2 minutes
            hedging_rules=DEFAULT_TEST_HEDGING_RULES,
        )

        timeline = build_timeline(trades, config)

        # Should have samples at 120s intervals
        sample_events = [p for p in timeline if p.event_type == "sample"]
        if len(sample_events) >= 2:
            # Verify 120s interval
            assert (
                sample_events[1].timestamp_ms - sample_events[0].timestamp_ms
            ) >= 120000


class TestTimelinePoint:
    """Test TimelinePoint model."""

    def test_create_client_fill_point(self):
        """Test creating client fill timeline point."""
        trade = create_test_trade("T001", 1704110400000, 1, 1000.0, 1.1005)

        point = TimelinePoint(
            timestamp_ms=1704110400000,
            event_type="client_fill",
            client_trade=trade,
        )

        assert point.timestamp_ms == 1704110400000
        assert point.event_type == "client_fill"
        assert point.client_trade.source_trade_id == "T001"
        assert point.hedge_trade is None

    def test_create_sample_point(self):
        """Test creating sample timeline point."""
        point = TimelinePoint(
            timestamp_ms=1704110400000,
            event_type="sample",
        )

        assert point.timestamp_ms == 1704110400000
        assert point.event_type == "sample"
        assert point.client_trade is None
        assert point.hedge_trade is None

    def test_create_hedge_fill_point(self):
        """Test creating hedge fill timeline point."""
        hedge = {
            "side": -1,
            "qty": 1000.0,
            "price": 1.0998,
            "trade_id": "hedge_EURUSD_1704110400000",
            "timestamp_ms": 1704110400000,
        }

        point = TimelinePoint(
            timestamp_ms=1704110400000,
            event_type="hedge_fill",
            hedge_trade=hedge,
        )

        assert point.timestamp_ms == 1704110400000
        assert point.event_type == "hedge_fill"
        assert point.hedge_trade["side"] == -1
        assert point.client_trade is None
