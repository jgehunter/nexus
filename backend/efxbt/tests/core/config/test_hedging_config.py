"""Tests for hedging configuration models."""

import math

import pytest
from pydantic import ValidationError

from efxbt.core.config.hedging_config import (
    AmountType,
    HedgePercentageParams,
    HedgeToTargetParams,
    HedgingRule,
    HedgingRuleSet,
    NoHedgeParams,
    PairGroup,
)


class TestActionParams:
    """Tests for action parameter models."""

    def test_no_hedge_params_defaults(self):
        """NoHedgeParams should have action_type='no_hedge'."""
        params = NoHedgeParams()
        assert params.action_type == "no_hedge"

    def test_hedge_to_target_params_valid(self):
        """HedgeToTargetParams should accept valid percentage."""
        params = HedgeToTargetParams(target_percentage=0.5)
        assert params.action_type == "hedge_to_target"
        assert params.target_percentage == 0.5

    def test_hedge_to_target_params_boundaries(self):
        """HedgeToTargetParams should accept boundary values."""
        params_zero = HedgeToTargetParams(target_percentage=0.0)
        assert params_zero.target_percentage == 0.0

        params_one = HedgeToTargetParams(target_percentage=1.0)
        assert params_one.target_percentage == 1.0

    def test_hedge_to_target_params_invalid_below_zero(self):
        """HedgeToTargetParams should reject negative percentage."""
        with pytest.raises(ValidationError):
            HedgeToTargetParams(target_percentage=-0.1)

    def test_hedge_to_target_params_invalid_above_one(self):
        """HedgeToTargetParams should reject percentage above 1.0."""
        with pytest.raises(ValidationError):
            HedgeToTargetParams(target_percentage=1.5)

    def test_hedge_percentage_params_valid(self):
        """HedgePercentageParams should accept valid percentage."""
        params = HedgePercentageParams(hedge_percentage=0.75)
        assert params.action_type == "hedge_percentage"
        assert params.hedge_percentage == 0.75

    def test_hedge_percentage_params_invalid(self):
        """HedgePercentageParams should reject invalid percentage."""
        with pytest.raises(ValidationError):
            HedgePercentageParams(hedge_percentage=-0.5)

        with pytest.raises(ValidationError):
            HedgePercentageParams(hedge_percentage=2.0)


class TestPairGroup:
    """Tests for PairGroup model."""

    def test_pair_group_valid(self):
        """PairGroup should accept valid name and pairs."""
        group = PairGroup(name="G3", pairs=["EURUSD", "USDJPY", "EURJPY"])
        assert group.name == "G3"
        assert group.pairs == ["EURUSD", "USDJPY", "EURJPY"]

    def test_pair_group_reserved_name_all(self):
        """PairGroup should reject 'ALL' as name."""
        with pytest.raises(ValidationError) as exc_info:
            PairGroup(name="ALL", pairs=["EURUSD"])
        assert "reserved" in str(exc_info.value).lower()

    def test_pair_group_reserved_name_all_lowercase(self):
        """PairGroup should reject 'all' (case insensitive)."""
        with pytest.raises(ValidationError):
            PairGroup(name="all", pairs=["EURUSD"])

    def test_pair_group_empty_name(self):
        """PairGroup should reject empty name."""
        with pytest.raises(ValidationError):
            PairGroup(name="", pairs=["EURUSD"])

    def test_pair_group_empty_pairs(self):
        """PairGroup should reject empty pairs list."""
        with pytest.raises(ValidationError):
            PairGroup(name="G3", pairs=[])


class TestHedgingRule:
    """Tests for HedgingRule model."""

    def test_hedging_rule_absolute_valid(self):
        """HedgingRule should accept valid absolute range."""
        rule = HedgingRule(
            pair_or_group="ALL",
            amount_type=AmountType.ABSOLUTE,
            from_amount=0,
            to_amount=1000,
            action=NoHedgeParams(),
        )
        assert rule.pair_or_group == "ALL"
        assert rule.amount_type == AmountType.ABSOLUTE
        assert rule.from_amount == 0
        assert rule.to_amount == 1000

    def test_hedging_rule_signed_valid(self):
        """HedgingRule should accept valid signed range."""
        rule = HedgingRule(
            pair_or_group="EURUSD",
            amount_type=AmountType.SIGNED,
            from_amount=-1000,
            to_amount=0,
            action=NoHedgeParams(),
        )
        assert rule.amount_type == AmountType.SIGNED
        assert rule.from_amount == -1000
        assert rule.to_amount == 0

    def test_hedging_rule_absolute_negative_from(self):
        """HedgingRule should reject negative from_amount for absolute type."""
        with pytest.raises(ValidationError) as exc_info:
            HedgingRule(
                pair_or_group="ALL",
                amount_type=AmountType.ABSOLUTE,
                from_amount=-100,
                to_amount=1000,
                action=NoHedgeParams(),
            )
        assert "from_amount" in str(exc_info.value).lower()

    def test_hedging_rule_absolute_negative_to(self):
        """HedgingRule should reject negative to_amount for absolute type."""
        with pytest.raises(ValidationError):
            HedgingRule(
                pair_or_group="ALL",
                amount_type=AmountType.ABSOLUTE,
                from_amount=0,
                to_amount=-100,
                action=NoHedgeParams(),
            )

    def test_hedging_rule_from_greater_than_to(self):
        """HedgingRule should reject from_amount > to_amount."""
        with pytest.raises(ValidationError) as exc_info:
            HedgingRule(
                pair_or_group="ALL",
                amount_type=AmountType.ABSOLUTE,
                from_amount=1000,
                to_amount=500,
                action=NoHedgeParams(),
            )
        assert "from_amount" in str(exc_info.value).lower()

    def test_hedging_rule_unbounded_to(self):
        """HedgingRule should accept infinity for to_amount."""
        rule = HedgingRule(
            pair_or_group="ALL",
            amount_type=AmountType.ABSOLUTE,
            from_amount=1000,
            to_amount=float("inf"),
            action=HedgePercentageParams(hedge_percentage=1.0),
        )
        assert math.isinf(rule.to_amount)

    def test_hedging_rule_with_hedge_to_target(self):
        """HedgingRule should work with HedgeToTargetParams."""
        rule = HedgingRule(
            pair_or_group="G3",
            from_amount=1000,
            to_amount=5000,
            action=HedgeToTargetParams(target_percentage=0.5),
        )
        assert rule.action.action_type == "hedge_to_target"
        assert rule.action.target_percentage == 0.5

    def test_hedging_rule_with_hedge_percentage(self):
        """HedgingRule should work with HedgePercentageParams."""
        rule = HedgingRule(
            pair_or_group="EURUSD",
            from_amount=500,
            to_amount=float("inf"),
            action=HedgePercentageParams(hedge_percentage=1.0),
        )
        assert rule.action.action_type == "hedge_percentage"
        assert rule.action.hedge_percentage == 1.0


class TestHedgingRuleSet:
    """Tests for HedgingRuleSet model."""

    def test_hedging_rule_set_minimal(self):
        """HedgingRuleSet should accept minimal valid config."""
        rule_set = HedgingRuleSet(
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                )
            ]
        )
        assert len(rule_set.rules) == 1
        assert len(rule_set.groups) == 0

    def test_hedging_rule_set_with_groups(self):
        """HedgingRuleSet should accept groups and rules."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
                PairGroup(name="Scandies", pairs=["EURSEK", "EURNOK"]),
            ],
            rules=[
                HedgingRule(
                    pair_or_group="G3",
                    from_amount=0,
                    to_amount=1000,
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
        assert len(rule_set.groups) == 2
        assert len(rule_set.rules) == 2

    def test_hedging_rule_set_duplicate_pair_in_groups(self):
        """HedgingRuleSet should reject pair appearing in multiple groups."""
        with pytest.raises(ValidationError) as exc_info:
            HedgingRuleSet(
                groups=[
                    PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
                    PairGroup(name="Majors", pairs=["EURUSD", "GBPUSD"]),  # EURUSD duplicated
                ],
                rules=[
                    HedgingRule(
                        pair_or_group="ALL",
                        from_amount=0,
                        to_amount=float("inf"),
                        action=NoHedgeParams(),
                    )
                ],
            )
        assert "EURUSD" in str(exc_info.value)
        assert "multiple groups" in str(exc_info.value).lower()

    def test_hedging_rule_set_empty_rules(self):
        """HedgingRuleSet should reject empty rules list."""
        with pytest.raises(ValidationError):
            HedgingRuleSet(rules=[])

    def test_hedging_rule_set_get_group_for_pair_found(self):
        """get_group_for_pair should return group name when pair is in group."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
            ],
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                )
            ],
        )
        assert rule_set.get_group_for_pair("EURUSD") == "G3"
        assert rule_set.get_group_for_pair("USDJPY") == "G3"

    def test_hedging_rule_set_get_group_for_pair_not_found(self):
        """get_group_for_pair should return None when pair is not in any group."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
            ],
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                )
            ],
        )
        assert rule_set.get_group_for_pair("GBPUSD") is None

    def test_hedging_rule_set_get_pairs_in_group_found(self):
        """get_pairs_in_group should return pairs when group exists."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
            ],
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                )
            ],
        )
        assert rule_set.get_pairs_in_group("G3") == ["EURUSD", "USDJPY"]

    def test_hedging_rule_set_get_pairs_in_group_not_found(self):
        """get_pairs_in_group should return empty list when group not found."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD"]),
            ],
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    from_amount=0,
                    to_amount=float("inf"),
                    action=NoHedgeParams(),
                )
            ],
        )
        assert rule_set.get_pairs_in_group("Unknown") == []


class TestCompleteConfiguration:
    """Integration tests for complete hedging configurations."""

    def test_typical_configuration(self):
        """Test a typical production-like configuration."""
        rule_set = HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY", "EURJPY"]),
                PairGroup(name="Scandies", pairs=["EURSEK", "EURNOK", "EURDKK"]),
            ],
            rules=[
                # Specific pair rule - highest priority
                HedgingRule(
                    pair_or_group="EURUSD",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=0,
                    to_amount=2000,
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="EURUSD",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=2000,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=0.5),
                ),
                # Group rule - G3 default
                HedgingRule(
                    pair_or_group="G3",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=0,
                    to_amount=1000,
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="G3",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
                # Catch-all rule
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=0,
                    to_amount=500,
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.ABSOLUTE,
                    from_amount=500,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),
                ),
            ],
        )

        assert len(rule_set.groups) == 2
        assert len(rule_set.rules) == 6
        assert rule_set.get_group_for_pair("EURUSD") == "G3"
        assert rule_set.get_group_for_pair("EURSEK") == "Scandies"
        assert rule_set.get_group_for_pair("GBPUSD") is None

    def test_signed_amount_configuration(self):
        """Test configuration with signed (directional) rules."""
        rule_set = HedgingRuleSet(
            rules=[
                # Different rules for long and short positions
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.SIGNED,
                    from_amount=-float("inf"),
                    to_amount=-1000,
                    action=HedgePercentageParams(hedge_percentage=0.5),  # Partial hedge shorts
                ),
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.SIGNED,
                    from_amount=-1000,
                    to_amount=1000,
                    action=NoHedgeParams(),  # No hedge within band
                ),
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type=AmountType.SIGNED,
                    from_amount=1000,
                    to_amount=float("inf"),
                    action=HedgePercentageParams(hedge_percentage=1.0),  # Full hedge longs
                ),
            ]
        )

        assert len(rule_set.rules) == 3
        assert rule_set.rules[0].amount_type == AmountType.SIGNED
