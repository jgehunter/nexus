"""Tests for rule-based hedge policy."""

import pytest

from efxbt.core.config.hedging_config import (
    AmountType,
    HedgePercentageParams,
    HedgeToTargetParams,
    HedgingRule,
    HedgingRuleSet,
    NoHedgeParams,
    PairGroup,
)
from efxbt.engine.shard.hedge_policy import RuleBasedHedgePolicy
from efxbt.engine.shard.market_fetcher import MarketSnapshot
from efxbt.engine.shard.state import ShardState


def make_state(pair: str = "EURUSD", net_position: float = 0.0) -> ShardState:
    """Create a test ShardState."""
    return ShardState(
        pair=pair,
        date="20240101",
        net_position=net_position,
    )


def make_snapshot(
    timestamp_ms: int = 1704067200000,
    mid: float = 1.10,
    bid: float = 1.0998,
    ask: float = 1.1002,
    pair: str = "EURUSD",
) -> MarketSnapshot:
    """Create a test MarketSnapshot."""
    return MarketSnapshot(
        timestamp_ms=timestamp_ms,
        pair=pair,
        mid=mid,
        bid=bid,
        ask=ask,
        spread=ask - bid,
        fx_rate=1.0,
    )


class TestRuleMatching:
    """Tests for rule priority and matching logic."""

    def test_no_matching_rule_returns_empty(self):
        """When no rule matches, return empty list."""
        rule_set = HedgingRuleSet(
            rules=[
                # Rule only covers 0-500 range
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=500,
                    action=NoHedgeParams(),
                )
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=1000)  # Outside rule range
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert result == []

    def test_specific_pair_takes_priority_over_group(self):
        """Specific pair rules should match before group rules."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
            ],
            rules=[
                # Specific pair rule: no hedge for EURUSD
                HedgingRule(
                    pair_or_group="EURUSD",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                ),
                # Group rule: full hedge for G3
                HedgingRule(
                    pair_or_group="G3",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ],
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(pair="EURUSD", net_position=1000)
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        # Specific pair rule wins: no hedge
        assert result == []

    def test_group_takes_priority_over_all(self):
        """Group rules should match before ALL rules."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD"]),
            ],
            rules=[
                # Group rule: no hedge for G3
                HedgingRule(
                    pair_or_group="G3",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                ),
                # ALL rule: full hedge
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ],
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(pair="EURUSD", net_position=1000)
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        # Group rule wins: no hedge
        assert result == []

    def test_all_rule_matches_unknown_pair(self):
        """ALL rule should match pairs not in any group."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD"]),
            ],
            rules=[
                HedgingRule(
                    pair_or_group="G3",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ],
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(pair="GBPUSD", net_position=1000)  # Not in any group
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        # ALL rule matches: full hedge
        assert len(result) == 1
        assert result[0]["qty"] == 1000

    def test_first_matching_rule_wins_within_priority(self):
        """Within same priority, first matching rule should win."""
        rule_set = HedgingRuleSet(
            rules=[
                # First ALL rule: no hedge for 0-1000
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=1000,
                    action=NoHedgeParams(),
                ),
                # Second ALL rule: full hedge for 0-2000 (overlaps)
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=2000,
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ],
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=500)  # Within both ranges
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        # First rule wins: no hedge
        assert result == []


class TestAmountTypeMatching:
    """Tests for absolute vs signed amount matching."""

    def test_absolute_matches_positive_position(self):
        """Absolute type should match positive position."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=500,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=1000)  # |1000| = 1000 >= 500
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1

    def test_absolute_matches_negative_position(self):
        """Absolute type should match negative position using absolute value."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=500,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=-1000)  # |-1000| = 1000 >= 500
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1

    def test_signed_matches_only_positive(self):
        """Signed type should only match positive positions when rule is positive."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.SIGNED,
                    from_amount=500,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)

        # Positive position matches
        state_long = make_state(net_position=1000)
        result_long = policy.evaluate(state_long, make_snapshot(), [])
        assert len(result_long) == 1

        # Negative position does NOT match (signed -1000 not in [500, inf])
        state_short = make_state(net_position=-1000)
        result_short = policy.evaluate(state_short, make_snapshot(), [])
        assert result_short == []

    def test_signed_matches_only_negative(self):
        """Signed type should only match negative positions when rule is negative."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.SIGNED,
                    from_amount=-float("inf"),
                    to_amount=-500,
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)

        # Negative position matches
        state_short = make_state(net_position=-1000)
        result_short = policy.evaluate(state_short, make_snapshot(), [])
        assert len(result_short) == 1

        # Positive position does NOT match
        state_long = make_state(net_position=1000)
        result_long = policy.evaluate(state_long, make_snapshot(), [])
        assert result_long == []


class TestNoHedgeAction:
    """Tests for NoHedge action."""

    def test_no_hedge_returns_empty(self):
        """NoHedge action should return empty list."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=1000)
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert result == []


class TestHedgeToTargetAction:
    """Tests for HedgeToTarget action."""

    def test_hedge_to_target_50_percent(self):
        """HedgeToTarget 50% should hedge down to 50% of from_amount."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=0.5),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=3000)  # Target = 1000 * 0.5 = 500
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1
        # Hedge qty = 3000 - 500 = 2500
        assert result[0]["qty"] == 2500
        assert result[0]["side"] == -1  # Selling to reduce long position

    def test_hedge_to_target_zero_percent(self):
        """HedgeToTarget 0% should hedge to zero (flatten)."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=0.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=2000)  # Target = 0
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1
        # Hedge qty = 2000 - 0 = 2000
        assert result[0]["qty"] == 2000

    def test_hedge_to_target_100_percent(self):
        """HedgeToTarget 100% should hedge down to from_amount."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=2500)  # Target = 1000 * 1.0 = 1000
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1
        # Hedge qty = 2500 - 1000 = 1500
        assert result[0]["qty"] == 1500

    def test_hedge_to_target_no_hedge_needed(self):
        """HedgeToTarget should not hedge if position already at target."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=1000)  # Already at target
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        # Hedge qty = 1000 - 1000 = 0 → no hedge
        assert result == []

    def test_hedge_to_target_zero_percent_2m_threshold(self):
        """HedgeToTarget 0% with 2M threshold should hedge entire position to 0.

        User configuration: position > 2M should hedge to target 0%.
        With target_percentage=0.0, target = 2M * 0 = 0, so hedge_qty = abs_pos - 0 = abs_pos.
        """
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=2_000_000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=0.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        snapshot = make_snapshot()

        # Position at 3M - should hedge entire 3M to 0
        state_3m = make_state(net_position=3_000_000)
        result = policy.evaluate(state_3m, snapshot, [])

        assert len(result) == 1
        assert result[0]["qty"] == 3_000_000  # Hedge entire position
        assert result[0]["side"] == -1  # Sell to flatten

        # Position at exactly 2M threshold - should hedge entire 2M to 0
        state_2m = make_state(net_position=2_000_000)
        result_2m = policy.evaluate(state_2m, snapshot, [])

        assert len(result_2m) == 1
        assert result_2m[0]["qty"] == 2_000_000  # Hedge entire position

        # Position at 1.5M - below threshold, no rule matches
        state_below = make_state(net_position=1_500_000)
        result_below = policy.evaluate(state_below, snapshot, [])

        assert result_below == []  # No matching rule

    def test_hedge_to_target_zero_percent_short_position(self):
        """HedgeToTarget 0% should also work for short positions."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=2_000_000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=0.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        snapshot = make_snapshot()

        # Short position at -3M - should hedge entire 3M to 0
        state_short = make_state(net_position=-3_000_000)
        result = policy.evaluate(state_short, snapshot, [])

        assert len(result) == 1
        assert result[0]["qty"] == 3_000_000  # Hedge entire position (abs value)
        assert result[0]["side"] == 1  # Buy to cover short


class TestHedgePercentageAction:
    """Tests for HedgePercentage action."""

    def test_hedge_percentage_100(self):
        """HedgePercentage 100% should flatten position."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=2000)
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1
        # Hedge 100% of 2000 = 2000
        assert result[0]["qty"] == 2000
        assert result[0]["side"] == -1  # Sell to reduce long

    def test_hedge_percentage_50(self):
        """HedgePercentage 50% should hedge half the position."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=0.5),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=2000)
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1
        # Hedge 50% of 2000 = 1000
        assert result[0]["qty"] == 1000

    def test_hedge_percentage_short_position(self):
        """HedgePercentage should work correctly for short positions."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=500,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=-1500)  # Short position
        snapshot = make_snapshot()

        result = policy.evaluate(state, snapshot, [])

        assert len(result) == 1
        # Hedge 100% of |-1500| = 1500
        assert result[0]["qty"] == 1500
        assert result[0]["side"] == 1  # Buy to cover short


class TestHedgeTradeDetails:
    """Tests for hedge trade output details."""

    def test_hedge_trade_uses_bid_for_sell(self):
        """Sell hedge should use bid price."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=1000)  # Long → sell
        snapshot = make_snapshot(bid=1.0998, ask=1.1002)

        result = policy.evaluate(state, snapshot, [])

        assert result[0]["price"] == 1.0998  # Bid for sell

    def test_hedge_trade_uses_ask_for_buy(self):
        """Buy hedge should use ask price."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=-1000)  # Short → buy
        snapshot = make_snapshot(bid=1.0998, ask=1.1002)

        result = policy.evaluate(state, snapshot, [])

        assert result[0]["price"] == 1.1002  # Ask for buy

    def test_hedge_trade_has_correct_trade_id(self):
        """Hedge trade should have formatted trade_id."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(pair="EURUSD", net_position=1000)
        snapshot = make_snapshot(timestamp_ms=1704067200000)

        result = policy.evaluate(state, snapshot, [])

        assert result[0]["trade_id"] == "hedge_EURUSD_1704067200000"

    def test_hedge_trade_has_timestamp(self):
        """Hedge trade should have timestamp_ms from snapshot."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        state = make_state(net_position=1000)
        snapshot = make_snapshot(timestamp_ms=1704067200000)

        result = policy.evaluate(state, snapshot, [])

        assert result[0]["timestamp_ms"] == 1704067200000


class TestComplexScenarios:
    """Integration tests for complex hedging scenarios."""

    def test_tiered_hedging_configuration(self):
        """Test a tiered hedging configuration with multiple ranges."""
        rule_set = HedgingRuleSet(
            rules=[
                # No hedge for small positions
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=1000,
                    action=NoHedgeParams(),
                ),
                # Partial hedge for medium positions
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=5000,
                    action=HedgeToTargetParams(target_percentage=0.5),
                ),
                # Full hedge for large positions
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=5000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ]
        )
        policy = RuleBasedHedgePolicy(rule_set)
        snapshot = make_snapshot()

        # Small position: no hedge
        result_small = policy.evaluate(make_state(net_position=500), snapshot, [])
        assert result_small == []

        # Medium position: hedge to target (1000 * 0.5 = 500)
        result_medium = policy.evaluate(make_state(net_position=3000), snapshot, [])
        assert result_medium[0]["qty"] == 2500  # 3000 - 500

        # Large position: full hedge
        result_large = policy.evaluate(make_state(net_position=10000), snapshot, [])
        assert result_large[0]["qty"] == 10000

    def test_pair_specific_override(self):
        """Test pair-specific rules overriding defaults."""
        rule_set = HedgingRuleSet(
            rules=[
                # EURUSD: higher tolerance
                HedgingRule(
                    pair_or_group="EURUSD",
                    from_amount=0,
                    to_amount=5000,
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="EURUSD",
                    from_amount=5000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=0.5),
                ),
                # Default: lower tolerance
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=1000,
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ],
        )
        policy = RuleBasedHedgePolicy(rule_set)
        snapshot = make_snapshot()

        # EURUSD at 3000: no hedge (within 5000 tolerance)
        result_eur = policy.evaluate(make_state(pair="EURUSD", net_position=3000), snapshot, [])
        assert result_eur == []

        # GBPUSD at 3000: full hedge (exceeds 1000 tolerance)
        result_gbp = policy.evaluate(make_state(pair="GBPUSD", net_position=3000), snapshot, [])
        assert result_gbp[0]["qty"] == 3000
