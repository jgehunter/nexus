"""Hedging configuration models for rule-based hedge policy.

This module defines the data models for the row-based hedging configuration system.
The system supports:
- Custom pair groups (e.g., G3, Scandies)
- Multiple rules with amount ranges
- Extensible action types
- Priority-based rule matching (specific pair > group > ALL)

EXTENSIBILITY:
To add a new action type:
1. Create a new ActionParams subclass with action_type literal
2. Add it to the ActionParams union type
3. Implement the action in RuleBasedHedgePolicy._execute_action()
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ACTION PARAMETER MODELS
# =============================================================================


class NoHedgeParams(BaseModel):
    """No hedge action - do nothing.

    Use this action to explicitly specify "do nothing" for a position range.
    """

    action_type: Literal["no_hedge"] = "no_hedge"


class HedgeToTargetParams(BaseModel):
    """Hedge position down to a target percentage of the From Amount.

    The target position is calculated as: from_amount * target_percentage

    Example:
        Rule: From=1000, To=5000, target_percentage=0.5
        Position: 3000 (within range)
        Target: 1000 * 0.5 = 500
        Hedge qty: 3000 - 500 = 2500
    """

    action_type: Literal["hedge_to_target"] = "hedge_to_target"
    target_percentage: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Target as percentage of From Amount (0.5 = 50%)",
    )


class HedgePercentageParams(BaseModel):
    """Hedge a percentage of the current position.

    Example:
        Position: 3000
        hedge_percentage: 1.0 -> hedge 3000 (flatten)
        hedge_percentage: 0.5 -> hedge 1500 (half)
    """

    action_type: Literal["hedge_percentage"] = "hedge_percentage"
    hedge_percentage: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Percentage of position to hedge (1.0 = flatten)",
    )


# Union type for all action parameters (discriminated by action_type)
# To add new action types, add them here
ActionParams = Annotated[
    NoHedgeParams | HedgeToTargetParams | HedgePercentageParams,
    Field(discriminator="action_type"),
]


# =============================================================================
# AMOUNT TYPE
# =============================================================================


class AmountType(str, Enum):
    """How to interpret the From/To amount range.

    ABSOLUTE: Rule applies to |position| (absolute value)
        - From=0, To=1000 matches positions from -1000 to +1000
        - Most common for symmetric hedging rules

    SIGNED: Rule applies to position with sign
        - From=-1000, To=0 matches only short positions
        - From=0, To=1000 matches only long positions
        - Use for asymmetric hedging (different rules for long vs short)
    """

    ABSOLUTE = "absolute"
    SIGNED = "signed"


# =============================================================================
# PAIR GROUPS
# =============================================================================


class PairGroup(BaseModel):
    """Custom group of currency pairs.

    Groups allow applying the same rules to multiple pairs.
    Each pair can only belong to one group.

    Example:
        PairGroup(name="G3", pairs=["EURUSD", "USDJPY", "EURJPY"])
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Group name (e.g., 'G3', 'Scandies')",
    )
    pairs: list[str] = Field(
        ...,
        min_length=1,
        description="Currency pairs in this group",
    )

    @field_validator("name")
    @classmethod
    def validate_reserved_names(cls, v: str) -> str:
        """Ensure 'ALL' is not used as a group name (reserved)."""
        if v.upper() == "ALL":
            raise ValueError("'ALL' is reserved and cannot be used as a group name")
        return v


# =============================================================================
# HEDGING RULE
# =============================================================================


class HedgingRule(BaseModel):
    """Single hedging rule with amount range and action.

    A rule matches when:
    1. The pair matches pair_or_group (directly, via group, or "ALL")
    2. The position falls within [from_amount, to_amount]

    Example:
        HedgingRule(
            pair_or_group="G3",
            amount_type=AmountType.ABSOLUTE,
            from_amount=0,
            to_amount=1000,
            action=NoHedgeParams()
        )
    """

    pair_or_group: str = Field(
        ...,
        description="Currency pair (EURUSD), group name, or 'ALL'",
    )
    amount_type: AmountType = Field(
        default=AmountType.ABSOLUTE,
        description="Whether From/To are absolute values or signed",
    )
    from_amount: float = Field(
        ...,
        description="Lower bound of position range",
    )
    to_amount: float = Field(
        ...,
        description="Upper bound of position range (use float('inf') for unbounded)",
    )
    action: ActionParams = Field(
        ...,
        description="Action to execute when rule matches",
    )

    @model_validator(mode="after")
    def validate_range(self) -> "HedgingRule":
        """Validate that from_amount <= to_amount and amounts are valid for type."""
        if self.amount_type == AmountType.ABSOLUTE:
            if self.from_amount < 0:
                raise ValueError("from_amount must be >= 0 for absolute type")
            if self.to_amount < 0:
                raise ValueError("to_amount must be >= 0 for absolute type")
        if self.from_amount > self.to_amount:
            raise ValueError("from_amount must be <= to_amount")
        return self


# =============================================================================
# HEDGING RULE SET
# =============================================================================


class HedgingRuleSet(BaseModel):
    """Complete hedging configuration with groups and rules.

    Priority Resolution:
    1. Specific pair rules (exact match on pair name)
    2. Group rules (pair belongs to a custom group)
    3. "ALL" rules (catch-all)

    Within each priority level, first matching rule wins (order matters).

    Example:
        HedgingRuleSet(
            groups=[
                PairGroup(name="G3", pairs=["EURUSD", "USDJPY"]),
            ],
            rules=[
                # Specific pair rule - highest priority
                HedgingRule(pair_or_group="EURUSD", ...),
                # Group rule
                HedgingRule(pair_or_group="G3", ...),
                # Catch-all
                HedgingRule(pair_or_group="ALL", ...),
            ]
        )
    """

    groups: list[PairGroup] = Field(
        default_factory=list,
        description="Custom pair groups",
    )
    rules: list[HedgingRule] = Field(
        ...,
        min_length=1,
        description="Ordered list of hedging rules (priority = order)",
    )

    @model_validator(mode="after")
    def validate_no_duplicate_pairs_in_groups(self) -> "HedgingRuleSet":
        """Ensure no pair appears in multiple groups."""
        seen_pairs: set[str] = set()
        for group in self.groups:
            for pair in group.pairs:
                if pair in seen_pairs:
                    raise ValueError(f"Pair {pair} appears in multiple groups")
                seen_pairs.add(pair)
        return self

    def get_group_for_pair(self, pair: str) -> str | None:
        """Find which group a pair belongs to, if any.

        Args:
            pair: Currency pair (e.g., "EURUSD")

        Returns:
            Group name or None if pair is not in any group
        """
        for group in self.groups:
            if pair in group.pairs:
                return group.name
        return None

    def get_pairs_in_group(self, group_name: str) -> list[str]:
        """Get all pairs in a group.

        Args:
            group_name: Name of the group

        Returns:
            List of pairs in the group, or empty list if group not found
        """
        for group in self.groups:
            if group.name == group_name:
                return group.pairs
        return []
