"""Hedge policy interface and implementations.

Provides pluggable hedge policies for different risk management strategies.
Each policy evaluates current state and market conditions to decide when
and how to hedge.
"""

from abc import ABC, abstractmethod

from .market_fetcher import MarketSnapshot
from .state import ShardState


class HedgePolicy(ABC):
    """Abstract base class for hedge policies.

    A hedge policy examines the current position and market conditions,
    then decides whether to execute hedges and at what quantities.
    """

    @abstractmethod
    def evaluate(
        self,
        state: ShardState,
        market_snapshot: MarketSnapshot,
        config: dict,
    ) -> list[dict]:
        """Evaluate policy and generate hedge trades.

        Args:
            state: Current shard state (position, queue)
            market_snapshot: Current market conditions
            config: Policy-specific configuration dict

        Returns:
            List of hedge trade dicts. Each dict contains:
            - side: int (+1 buy, -1 sell)
            - qty: float (hedge quantity)
            - price: float (execution price, typically bid/ask)
            - trade_id: str (unique identifier)
            - timestamp_ms: int (execution timestamp)

        Example:
            >>> policy = AggressiveHedgePolicy()
            >>> state = ShardState(pair="EURUSD", net_position=1500.0, ...)
            >>> snapshot = MarketSnapshot(mid=1.10, bid=1.0998, ask=1.1002, ...)
            >>> config = {"risk_band_qty": 1000.0, "hedge_mode": "full"}
            >>> hedges = policy.evaluate(state, snapshot, config)
            >>> hedges
            [{"side": -1, "qty": 1500.0, "price": 1.0998, ...}]
        """
        pass


class AggressiveHedgePolicy(HedgePolicy):
    """Flatten position immediately when outside risk band.

    This policy monitors the net position and hedges aggressively when
    it exceeds the configured risk band. Designed for risk-averse desks.

    Configuration:
        risk_band_qty: float (default: 1000.0)
            Maximum absolute position before hedging

        hedge_mode: str (default: "full")
            - "full": Flatten position completely (hedge entire position)
            - "partial": Hedge back to risk band edge (hedge excess only)

    Behavior:
        - If |position| <= risk_band_qty: No hedge
        - If |position| > risk_band_qty:
            - full mode: Hedge entire position (flatten to zero)
            - partial mode: Hedge (|position| - risk_band_qty) to reach band edge

    Example:
        >>> policy = AggressiveHedgePolicy()
        >>> config = {"risk_band_qty": 1000.0, "hedge_mode": "full"}
        >>> state = ShardState(net_position=1500.0, ...)

        >>> # Outside band (1500 > 1000), hedge triggered
        >>> hedges = policy.evaluate(state, snapshot, config)
        >>> hedges[0]["qty"]
        1500.0  # Full flatten

        >>> config = {"risk_band_qty": 1000.0, "hedge_mode": "partial"}
        >>> hedges = policy.evaluate(state, snapshot, config)
        >>> hedges[0]["qty"]
        500.0  # Partial (1500 - 1000)
    """

    def evaluate(
        self,
        state: ShardState,
        market_snapshot: MarketSnapshot,
        config: dict,
    ) -> list[dict]:
        """Evaluate aggressive hedge policy.

        Args:
            state: Current shard state
            market_snapshot: Current market snapshot
            config: Policy config with risk_band_qty and hedge_mode

        Returns:
            List of hedge trades (empty if no hedge needed)
        """
        risk_band_qty = config.get("risk_band_qty", 1000.0)
        hedge_mode = config.get("hedge_mode", "full")

        abs_pos = abs(state.net_position)

        # Check if outside band
        if abs_pos <= risk_band_qty:
            return []  # No hedge needed

        # Determine hedge side (opposite of position)
        hedge_side = -1 if state.net_position > 0 else 1

        # Determine hedge quantity
        if hedge_mode == "full":
            hedge_qty = abs_pos  # Flatten completely
        else:  # "partial"
            hedge_qty = abs_pos - risk_band_qty  # To band edge

        # Select execution price (cross spread)
        # Buy at ask, sell at bid (realistic execution)
        hedge_price = market_snapshot.ask if hedge_side == 1 else market_snapshot.bid

        # Generate hedge trade
        hedge_trade = {
            "side": hedge_side,
            "qty": hedge_qty,
            "price": hedge_price,
            "trade_id": f"hedge_{state.pair}_{market_snapshot.timestamp_ms}",
            "timestamp_ms": market_snapshot.timestamp_ms,
        }

        return [hedge_trade]


class PassiveHedgePolicy(HedgePolicy):
    """Wait and hedge only at advantageous prices.

    This policy is more patient, waiting for favorable market conditions
    before hedging. Suitable for desks with higher risk tolerance.

    Configuration:
        risk_band_qty: float (default: 2000.0)
            Maximum absolute position (higher than aggressive)

        wait_threshold_pct: float (default: 0.5)
            Wait for this percentage of spread improvement before hedging

    Behavior:
        - If |position| <= risk_band_qty: No hedge
        - If |position| > risk_band_qty:
            - Check if current spread is favorable (< threshold)
            - If favorable: Hedge back to band edge
            - If not favorable: Wait (no hedge this cycle)

    Note: This is a future implementation placeholder.
    """

    def evaluate(
        self,
        state: ShardState,
        market_snapshot: MarketSnapshot,
        config: dict,
    ) -> list[dict]:
        """Evaluate passive hedge policy.

        Args:
            state: Current shard state
            market_snapshot: Current market snapshot
            config: Policy configuration

        Returns:
            List of hedge trades (empty if waiting)

        Note:
            This is a stub for future implementation.
            Currently raises NotImplementedError.
        """
        raise NotImplementedError(
            "PassiveHedgePolicy is not yet implemented. Use AggressiveHedgePolicy."
        )


# Policy registry for easy lookup
POLICY_REGISTRY = {
    "aggressive": AggressiveHedgePolicy,
    "passive": PassiveHedgePolicy,
}


def create_hedge_policy(policy_name: str) -> HedgePolicy:
    """Factory function to create hedge policy by name.

    Args:
        policy_name: Name of the policy ("aggressive", "passive", etc.)

    Returns:
        HedgePolicy instance

    Raises:
        ValueError: If policy_name not found in registry

    Example:
        >>> policy = create_hedge_policy("aggressive")
        >>> isinstance(policy, AggressiveHedgePolicy)
        True
    """
    if policy_name not in POLICY_REGISTRY:
        raise ValueError(
            f"Unknown hedge policy: {policy_name}. "
            f"Available policies: {list(POLICY_REGISTRY.keys())}"
        )

    policy_class = POLICY_REGISTRY[policy_name]
    return policy_class()
