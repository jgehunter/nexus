# Hedging Policies

This document explains the hedging system and how to implement new hedging modes.

## Overview

The hedging system manages risk by executing trades when positions exceed configured thresholds. Each policy defines:

- **When** to hedge (trigger conditions)
- **How much** to hedge (quantity calculation)
- **At what price** to execute (price selection)

## Available Policies

### AggressiveHedgePolicy

Flattens position immediately when outside risk band. Designed for risk-averse desks.

**Configuration:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `risk_band_qty` | float | 1000.0 | Maximum position before hedging |
| `hedge_mode` | string | "full" | "full" (flatten) or "partial" (to band edge) |
| `pair_bands` | dict | {} | Per-pair band overrides |

**Behavior:**

```
Position: +1500 (long)
Risk Band: 1000

Mode "full":   Hedge -1500 (flatten to zero)
Mode "partial": Hedge -500  (reduce to +1000)
```

**Example Configuration:**

```python
config = {
    "risk_band_qty": 1000.0,      # Global default
    "hedge_mode": "full",          # Flatten completely
    "pair_bands": {
        "EURUSD": 2000.0,          # Higher tolerance for EURUSD
        "GBPUSD": 500.0,           # Lower tolerance for GBPUSD
    }
}
```

### PassiveHedgePolicy

Waits for favorable market conditions before hedging. More patient approach.

**Status:** Not yet implemented (placeholder)

## Adding a New Hedging Policy

### Step 1: Create the Policy Class

```python
# backend/efxbt/src/efxbt/engine/shard/hedge_policy.py

class MyNewPolicy(HedgePolicy):
    """Description of your policy behavior.

    Configuration:
        my_param: float (default: 100.0)
            Description of what this parameter controls

    Behavior:
        - Describe when hedging triggers
        - Describe how quantity is calculated
    """

    def evaluate(
        self,
        state: ShardState,
        market_snapshot: MarketSnapshot,
        config: dict,
    ) -> list[dict]:
        """Evaluate the policy and generate hedge trades.

        Args:
            state: Current shard state (net_position, pair, etc.)
            market_snapshot: Current market (bid, ask, mid, timestamp_ms)
            config: Policy configuration dict

        Returns:
            List of hedge trade dicts, empty if no hedge needed
        """
        # Get config parameters with defaults
        my_param = config.get("my_param", 100.0)

        # Check trigger condition
        if not self._should_hedge(state, my_param):
            return []

        # Calculate hedge quantity
        hedge_qty = self._calculate_quantity(state, config)

        # Determine side (opposite of position)
        hedge_side = -1 if state.net_position > 0 else 1

        # Select price (cross spread: buy at ask, sell at bid)
        hedge_price = (
            market_snapshot.ask if hedge_side == 1
            else market_snapshot.bid
        )

        # Return hedge trade(s)
        return [{
            "side": hedge_side,
            "qty": hedge_qty,
            "price": hedge_price,
            "trade_id": f"hedge_{state.pair}_{market_snapshot.timestamp_ms}",
            "timestamp_ms": market_snapshot.timestamp_ms,
        }]

    def _should_hedge(self, state: ShardState, threshold: float) -> bool:
        """Check if hedging should trigger."""
        return abs(state.net_position) > threshold

    def _calculate_quantity(self, state: ShardState, config: dict) -> float:
        """Calculate hedge quantity."""
        return abs(state.net_position)
```

### Step 2: Register the Policy

Add to the policy registry at the bottom of `hedge_policy.py`:

```python
POLICY_REGISTRY = {
    "aggressive": AggressiveHedgePolicy,
    "passive": PassiveHedgePolicy,
    "my_new_policy": MyNewPolicy,  # Add your policy
}
```

### Step 3: Add Tests

```python
# backend/efxbt/tests/engine/test_hedge_policy.py

import pytest
from efxbt.engine.shard.hedge_policy import MyNewPolicy
from efxbt.engine.shard.state import ShardState
from efxbt.engine.shard.market_fetcher import MarketSnapshot


class TestMyNewPolicy:
    @pytest.fixture
    def policy(self):
        return MyNewPolicy()

    @pytest.fixture
    def state(self):
        return ShardState(
            pair="EURUSD",
            net_position=1500.0,
            # ... other required fields
        )

    @pytest.fixture
    def market(self):
        return MarketSnapshot(
            timestamp_ms=1704067200000,
            bid=1.0998,
            ask=1.1002,
            mid=1.1000,
        )

    def test_hedge_triggers_above_threshold(self, policy, state, market):
        """Test that hedge triggers when position exceeds threshold."""
        config = {"my_param": 1000.0}
        hedges = policy.evaluate(state, market, config)

        assert len(hedges) == 1
        assert hedges[0]["side"] == -1  # Sell to reduce long
        assert hedges[0]["qty"] == 1500.0

    def test_no_hedge_below_threshold(self, policy, state, market):
        """Test no hedge when position within threshold."""
        state.net_position = 500.0
        config = {"my_param": 1000.0}
        hedges = policy.evaluate(state, market, config)

        assert len(hedges) == 0

    def test_uses_correct_price(self, policy, state, market):
        """Test that sells use bid price."""
        config = {"my_param": 1000.0}
        hedges = policy.evaluate(state, market, config)

        # Long position hedges with sell, uses bid
        assert hedges[0]["price"] == market.bid
```

### Step 4: Run Tests

```bash
cd backend/efxbt
uv run pytest tests/engine/test_hedge_policy.py -v
```

## Configuration Reference

### Global Configuration (SimulationConfig)

```python
from efxbt.core.config.run_config import SimulationConfig

config = SimulationConfig(
    hedge_policy="aggressive",        # Policy name
    hedge_policy_config={             # Policy-specific config
        "risk_band_qty": 1000.0,
        "hedge_mode": "full",
        "pair_bands": {"EURUSD": 2000.0},
    },
)
```

### Per-Run Override

When creating a backtest run, you can override hedging config:

```python
run_config = {
    "tradebook": "MAD_GLD",
    "dataset": "efx_2024_q1",
    "simulation": {
        "hedge_policy": "aggressive",
        "hedge_policy_config": {
            "risk_band_qty": 500.0,  # More aggressive for this run
        },
    },
}
```

## Policy Design Considerations

### 1. Position Tracking

The `ShardState.net_position` tracks the current position in base currency units:
- Positive = long (house bought base)
- Negative = short (house sold base)

### 2. Price Selection

For realistic execution:
- **Buy hedge**: Use `market_snapshot.ask` (pay the spread)
- **Sell hedge**: Use `market_snapshot.bid` (pay the spread)

### 3. Trade IDs

Generate unique trade IDs for hedge trades:
```python
trade_id = f"hedge_{state.pair}_{market_snapshot.timestamp_ms}"
```

### 4. Multiple Hedges

Policies can return multiple hedge trades if needed:
```python
return [
    {"side": -1, "qty": 500.0, ...},  # First tranche
    {"side": -1, "qty": 500.0, ...},  # Second tranche
]
```

### 5. No Hedge

Return empty list when no hedge is needed:
```python
if abs(state.net_position) <= threshold:
    return []
```

## Common Patterns

### Time-Based Hedging

Hedge only at certain times:

```python
def evaluate(self, state, market, config):
    # Only hedge during active hours
    hour = self._get_hour(market.timestamp_ms)
    if hour < 8 or hour > 17:
        return []  # No hedging outside hours

    # Normal hedge logic...
```

### Spread-Aware Hedging

Wait for favorable spreads:

```python
def evaluate(self, state, market, config):
    max_spread = config.get("max_spread_bps", 5.0)
    current_spread = (market.ask - market.bid) / market.mid * 10000

    if current_spread > max_spread:
        return []  # Spread too wide, wait

    # Normal hedge logic...
```

### Tiered Hedging

Hedge in tranches based on position size:

```python
def evaluate(self, state, market, config):
    bands = [(1000, 0.25), (2000, 0.50), (3000, 1.0)]

    for threshold, hedge_pct in bands:
        if abs(state.net_position) > threshold:
            hedge_qty = abs(state.net_position) * hedge_pct
            return [self._create_hedge(state, market, hedge_qty)]

    return []
```
