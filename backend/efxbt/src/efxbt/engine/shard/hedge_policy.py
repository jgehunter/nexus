"""Rule-based hedge policy implementation.

This module implements the rule-based hedging policy that evaluates
hedging rules with priority-based matching to determine when and
how to hedge positions.

Priority Resolution:
1. Specific pair rules (exact match on pair name)
2. Group rules (pair belongs to a custom group)
3. "ALL" rules (catch-all)

Within each priority level, first matching rule wins (order matters).

EXTENSIBILITY:
To add a new action type:
1. Create a new ActionParams subclass in hedging_config.py
2. Add it to the ActionParams union type
3. Implement the action handler in _execute_action() below
"""

from efxbt.core.config.hedging_config import (
    AmountType,
    HedgePercentageParams,
    HedgeToTargetParams,
    HedgingRule,
    HedgingRuleSet,
    NoHedgeParams,
)

from .market_fetcher import MarketSnapshot
from .state import ShardState


class RuleBasedHedgePolicy:
    """Rule-based hedge policy with priority matching.

    This policy evaluates hedging rules in priority order to determine
    whether to hedge and how much.

    Priority Resolution:
    1. Specific pair rules (exact match on pair name)
    2. Group rules (pair belongs to a custom group)
    3. "ALL" rules (catch-all)

    Within each priority level, first matching rule wins (order matters).

    Example:
        >>> rule_set = HedgingRuleSet(
        ...     groups=[PairGroup(name="G3", pairs=["EURUSD", "USDJPY"])],
        ...     rules=[
        ...         HedgingRule(pair_or_group="ALL", from_amount=0, to_amount=1000,
        ...                     action=NoHedgeParams()),
        ...         HedgingRule(pair_or_group="ALL", from_amount=1000, to_amount=float('inf'),
        ...                     action=HedgePercentageParams(hedge_percentage=1.0)),
        ...     ]
        ... )
        >>> policy = RuleBasedHedgePolicy(rule_set)
        >>> hedges = policy.evaluate(state, market_snapshot, pending_hedges=[])
    """

    def __init__(self, rule_set: HedgingRuleSet) -> None:
        """Initialize the policy with a rule set.

        Args:
            rule_set: Complete hedging configuration with groups and rules
        """
        self.rule_set = rule_set
        # Pre-compute pair -> group mapping for O(1) lookup
        self._pair_to_group: dict[str, str] = {}
        for group in rule_set.groups:
            for pair in group.pairs:
                self._pair_to_group[pair] = group.name

    def evaluate(
        self,
        state: ShardState,
        market_snapshot: MarketSnapshot,
        pending_hedges: list,
    ) -> list[dict]:
        """Evaluate rules and generate hedge trades.

        Args:
            state: Current shard state (position, pair, etc.)
            market_snapshot: Current market conditions (bid, ask, mid)
            pending_hedges: List of pending hedge tuples (execute_at, hedge_dict, snapshot).
                           Used to calculate effective position including in-flight hedges.
                           Pass empty list [] if no pending hedges.

        Returns:
            List of hedge trade dicts. Each dict contains:
            - side: int (+1 buy, -1 sell)
            - qty: float (hedge quantity in base currency)
            - price: float (execution price, bid for sells, ask for buys)
            - trade_id: str (unique identifier)
            - timestamp_ms: int (execution timestamp)

        Example:
            >>> hedges = policy.evaluate(state, snapshot, pending_hedges=[])
            >>> hedges
            [{"side": -1, "qty": 1500.0, "price": 1.0998, ...}]
        """
        pair = state.pair
        position = state.net_position

        # Calculate effective position accounting for pending hedges
        # This prevents duplicate hedges when policy is evaluated multiple times
        for _, hedge, _ in pending_hedges:
            # Hedge side: +1 = buy (adds to position), -1 = sell (reduces position)
            hedge_effect = hedge["side"] * hedge["qty"]
            position += hedge_effect

        # Find first matching rule by priority
        rule = self._find_matching_rule(pair, position)
        if rule is None:
            return []

        # Execute the action
        hedge_qty = self._execute_action(rule, position)
        if abs(hedge_qty) < 1e-8:
            return []

        # Build hedge trade
        # Hedge side is opposite of position: long position -> sell, short -> buy
        hedge_side = -1 if position > 0 else 1
        # Cross the spread: buy at ask, sell at bid
        hedge_price = market_snapshot.ask if hedge_side == 1 else market_snapshot.bid

        return [
            {
                "side": hedge_side,
                "qty": abs(hedge_qty),
                "price": hedge_price,
                "trade_id": f"hedge_{pair}_{market_snapshot.timestamp_ms}",
                "timestamp_ms": market_snapshot.timestamp_ms,
            }
        ]

    def _find_matching_rule(self, pair: str, position: float) -> HedgingRule | None:
        """Find first matching rule using priority resolution.

        Args:
            pair: Currency pair (e.g., "EURUSD")
            position: Current net position (positive = long, negative = short)

        Returns:
            First matching HedgingRule, or None if no rule matches
        """
        # Priority 1: Specific pair rules (exact match)
        for rule in self.rule_set.rules:
            if rule.pair_or_group == pair and self._position_in_range(position, rule):
                return rule

        # Priority 2: Group rules (pair belongs to a custom group)
        group_name = self._pair_to_group.get(pair)
        if group_name:
            for rule in self.rule_set.rules:
                if rule.pair_or_group == group_name and self._position_in_range(
                    position, rule
                ):
                    return rule

        # Priority 3: "ALL" rules (catch-all)
        for rule in self.rule_set.rules:
            if rule.pair_or_group.upper() == "ALL" and self._position_in_range(
                position, rule
            ):
                return rule

        return None

    def _position_in_range(self, position: float, rule: HedgingRule) -> bool:
        """Check if position falls within rule's range.

        Args:
            position: Current net position
            rule: Hedging rule to check

        Returns:
            True if position is within [from_amount, to_amount]
        """
        if rule.amount_type == AmountType.ABSOLUTE:
            value = abs(position)
        else:  # SIGNED
            value = position
        return rule.from_amount <= value <= rule.to_amount

    def _execute_action(self, rule: HedgingRule, position: float) -> float:
        """Execute action and return hedge quantity.

        Args:
            rule: Matched hedging rule
            position: Current net position

        Returns:
            Hedge quantity (0 for no-hedge actions, positive for hedge actions)

        Raises:
            ValueError: If action type is unknown
        """
        action = rule.action
        abs_pos = abs(position)

        # === EXTENSIBILITY POINT ===
        # Add new action handlers here

        if isinstance(action, NoHedgeParams):
            return 0.0

        elif isinstance(action, HedgeToTargetParams):
            # Target = from_amount * target_percentage
            # Hedge down to target level
            target = rule.from_amount * action.target_percentage
            return max(0.0, abs_pos - target)

        elif isinstance(action, HedgePercentageParams):
            # Hedge this percentage of current position
            return abs_pos * action.hedge_percentage

        # Unknown action type - should not happen with proper type checking
        raise ValueError(f"Unknown action type: {type(action)}")
