"""Integration tests for ShardEngine end-to-end simulation.

Tests the complete simulation flow:
- Timeline construction
- Market snapshot fetching
- FIFO matching
- Hedge policy evaluation
- PnL calculation with multi-currency support
- Trade-level attribution
"""

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from efxbt.core.config.run_config import SimulationConfig
from efxbt.core.config.hedging_config import (
    HedgingRuleSet, HedgingRule, NoHedgeParams, HedgePercentageParams
)
from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.shard.shard_engine import ShardEngine
from efxbt.engine.shard.state import ShardState


def make_hedging_rules(risk_band_qty: float = 1000.0, hedge_pct: float = 1.0) -> HedgingRuleSet:
    """Create hedging rules similar to the old aggressive policy.

    Args:
        risk_band_qty: Position threshold before hedging (default 1000)
        hedge_pct: Percentage of position to hedge when threshold exceeded (default 1.0 = 100%)

    Returns:
        HedgingRuleSet with no-hedge rule below threshold, hedge rule above
    """
    return HedgingRuleSet(
        groups=[],
        rules=[
            HedgingRule(
                pair_or_group="ALL",
                amount_type="absolute",
                from_amount=0,
                to_amount=risk_band_qty,
                action=NoHedgeParams(),
            ),
            HedgingRule(
                pair_or_group="ALL",
                amount_type="absolute",
                from_amount=risk_band_qty,
                to_amount=float("inf"),
                action=HedgePercentageParams(hedge_percentage=hedge_pct),
            ),
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
        path=["EUR", "USD"] if pair == "EURUSD" else ["GBP", "USD"],
        leg_index=0,
        leg_count=1,
    )


def create_test_market_data(pair: str, data_root: Path) -> None:
    """Create minimal test market data for integration testing."""
    # Create market data directory structure
    market_dir = data_root / "datasets" / "test" / "market" / pair
    market_dir.mkdir(parents=True, exist_ok=True)

    # Create simple market data (one day)
    date_str = "20240101"

    # Generate ticks every second for 1 minute
    timestamps = []
    bids = []
    asks = []

    base_time = 1704110400000  # 2024-01-01 00:00:00 UTC
    base_bid = 1.0998
    base_ask = 1.1002

    for i in range(120):  # 2 minutes of data
        timestamps.append(base_time + (i * 1000))
        # Add some variance
        bids.append(base_bid + (i * 0.0001))
        asks.append(base_ask + (i * 0.0001))

    # Create PyArrow table
    table = pa.table({
        "timestamp_ms": pa.array(timestamps, type=pa.int64()),
        "pair": pa.array([pair] * len(timestamps), type=pa.string()),
        "bid_tob": pa.array(bids, type=pa.float64()),
        "ask_tob": pa.array(asks, type=pa.float64()),
    })

    # Write to parquet
    output_file = market_dir / f"{date_str}.parquet"
    pq.write_table(table, output_file)


@pytest.fixture
def test_data_root():
    """Create temporary directory with test market data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir)

        # Create market data for EURUSD
        create_test_market_data("EURUSD", data_root)

        # Create market data for GBPUSD (for FX conversion tests)
        create_test_market_data("GBPUSD", data_root)

        yield data_root


class TestShardEngineIntegration:
    """Integration tests for ShardEngine with real data flow."""

    def test_single_shard_simple_flow(self, test_data_root):
        """Test simple flow with BUY and SELL trades."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        # Create client trades (all sides from HOUSE's perspective)
        # side=-1: House SELLS (client buys from us)
        # side=+1: House BUYS (client sells to us)
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 500.0, 1.1005),  # House SELLS 500
            create_test_trade("T002", 1704110430000, 1, 300.0, 1.0995),  # House BUYS 300
        ]

        # Run simulation
        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(client_trades, prior_state=None)

        # Verify results
        assert result.pair == "EURUSD"
        assert result.date == "20240101"
        assert result.final_state is not None

        # Net position: House SELLS 500 (side=-1) → -500, House BUYS 300 (side=+1) → +300
        # Net = -500 + 300 = -200
        assert abs(result.final_state.net_position - (-200.0)) < 1e-8

        # Should have PnL records
        assert len(result.pnl_records) > 0

        # Verify metrics exist
        assert "total_client_volume" in result.metrics
        assert "internalization_ratio" in result.metrics

        # Verify internalization (no hedge triggered)
        assert result.metrics["total_client_volume"] == 800.0  # 500 + 300
        assert result.metrics["internalized_volume"] == 800.0  # All internalized
        assert result.metrics["internalization_ratio"] == 1.0  # 100% internalized

    def test_hedge_triggered_flow(self, test_data_root):
        """Test flow where hedge is triggered."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=500.0),
            sample_interval_seconds=30,
        )

        # Create trades that exceed risk band
        # House SELLS 1000 → position = -1000 (exceeds band of 500)
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 1000.0, 1.1005),  # House SELLS 1000
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(client_trades, prior_state=None)

        # Position exceeds 500, should trigger hedge
        # Hedge should flatten to 0
        assert abs(result.final_state.net_position) < 1e-8

        # Verify externalization (hedge executed)
        assert result.metrics["externalized_volume"] > 0  # Hedge executed
        assert result.metrics["internalization_ratio"] < 1.0  # Not fully internalized

    def test_state_chaining_across_days(self, test_data_root):
        """Test state chaining from day N to day N+1."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        # Day 1: Build up position
        # House SELLS 500 → position = -500
        day1_trades = [
            create_test_trade("T001", 1704110400000, -1, 500.0, 1.1005),  # House SELLS 500
        ]

        engine_day1 = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result_day1 = engine_day1.run(day1_trades, prior_state=None)

        # Day 1 final position: -500 (House SELLS 500 → house is SHORT 500)
        assert abs(result_day1.final_state.net_position - (-500.0)) < 1e-8

        # Day 2: Use day 1 final state as prior state
        # House BUYS 300 → position goes from -500 to -200
        day2_trades = [
            create_test_trade("T002", 1704110400000, 1, 300.0, 1.0995),  # House BUYS 300
        ]

        engine_day2 = ShardEngine(
            pair="EURUSD",
            date="20240102",
            config=config,
            data_root=test_data_root,
        )

        result_day2 = engine_day2.run(day2_trades, prior_state=result_day1.final_state)

        # Day 2 final position: -500 + 300 = -200 (House BUYS 300 → house +300)
        assert abs(result_day2.final_state.net_position - (-200.0)) < 1e-8

        # Cumulative PnL should accumulate
        # Day 2 cumulative PnL = Day 1 cumulative + Day 2 incremental
        assert result_day2.final_state.cumulative_execution_pnl >= 0

    def test_pnl_attribution_completeness(self, test_data_root):
        """Test that all PnL is attributed to source trades."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=500.0),
            sample_interval_seconds=30,
        )

        # House SELLS 800 → position = -800 (exceeds band of 500, triggers hedge)
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 800.0, 1.1005),  # House SELLS 800
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(client_trades, prior_state=None)

        # Collect all attributed PnL
        total_attributed_execution = 0.0
        total_attributed_inventory = 0.0
        total_attributed_hedge = 0.0

        for record in result.pnl_records:
            for trade_attr in record.trade_attributions:
                total_attributed_execution += trade_attr.execution_pnl_reporting
                total_attributed_inventory += trade_attr.inventory_pnl_reporting
                total_attributed_hedge += trade_attr.hedge_pnl_reporting

        # Verify attribution totals match metrics
        assert abs(total_attributed_execution - result.metrics["execution_pnl_reporting"]) < 1e-6
        assert abs(total_attributed_inventory - result.metrics["inventory_pnl_reporting"]) < 1e-6
        assert abs(total_attributed_hedge - result.metrics["hedge_pnl_reporting"]) < 1e-6

    def test_multi_currency_pnl_tracking(self, test_data_root):
        """Test that both native and reporting currency PnL are tracked."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        # House SELLS 500 EURUSD
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 500.0, 1.1005, "EURUSD"),
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(client_trades, prior_state=None)

        # Verify all attribution records have both currencies
        for record in result.pnl_records:
            for trade_attr in record.trade_attributions:
                assert trade_attr.native_currency == "USD"  # EURUSD native = USD
                assert trade_attr.reporting_currency == "USD"
                assert trade_attr.fx_rate == 1.0  # Same currency

                # Native and reporting should match for EURUSD -> USD
                assert abs(trade_attr.execution_pnl_native - trade_attr.execution_pnl_reporting) < 1e-8

    def test_partial_hedge_mode(self, test_data_root):
        """Test partial hedge mode (hedge to band edge)."""
        # Use HedgeToTargetParams with target_percentage=1.0 to hedge down to from_amount
        from efxbt.core.config.hedging_config import HedgeToTargetParams
        partial_rules = HedgingRuleSet(
            groups=[],
            rules=[
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type="absolute",
                    from_amount=0,
                    to_amount=500.0,
                    action=NoHedgeParams(),
                ),
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type="absolute",
                    from_amount=500.0,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=1.0),  # Hedge to from_amount (500)
                ),
            ],
        )
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=partial_rules,
            sample_interval_seconds=30,
        )

        # House SELLS 1000 → position = -1000 (exceeds band of 500)
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 1000.0, 1.1005),  # House SELLS 1000
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(client_trades, prior_state=None)

        # Position should be hedged back to band edge (-500)
        # House SELLS 1000 → position = -1000, hedge BUY 500 → position = -500
        assert abs(result.final_state.net_position - (-500.0)) < 1e-8

        # Verify partial externalization
        assert result.metrics["externalized_volume"] == 500.0  # Partial hedge
        assert result.metrics["internalization_ratio"] == 0.5  # 50% internalized

    def test_hedge_to_zero_2m_threshold(self, test_data_root):
        """Test HedgeToTarget 0% with 2M threshold - user's exact config.

        User configuration:
        - Only one rule: positions > 2M should hedge to target 0%
        - No rule for positions below 2M (so no hedging for small positions)

        Expected behavior:
        - Position < 2M: No hedge
        - Position >= 2M: Hedge entire position to 0
        """
        from efxbt.core.config.hedging_config import HedgeToTargetParams

        # User's exact configuration
        user_rules = HedgingRuleSet(
            groups=[],
            rules=[
                # Only one rule: hedge to 0 when >= 2M
                HedgingRule(
                    pair_or_group="ALL",
                    amount_type="absolute",
                    from_amount=2_000_000.0,
                    to_amount=float("inf"),
                    action=HedgeToTargetParams(target_percentage=0.0),
                ),
            ],
        )

        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=user_rules,
            sample_interval_seconds=30,
        )

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        # Test 1: Single trade exceeds 2M
        # House SELLS 3M → position = -3M → should hedge to 0
        trades_3m = [
            create_test_trade("T001", 1704110400000, -1, 3_000_000.0, 1.1005),
        ]
        result_3m = engine.run(trades_3m, prior_state=None)

        # Position should be 0 after hedge
        assert abs(result_3m.final_state.net_position) < 1e-8, (
            f"Expected position 0, got {result_3m.final_state.net_position}"
        )
        # Should have externalized 3M
        assert result_3m.metrics["externalized_volume"] == 3_000_000.0

        # Test 2: Trade below threshold - no hedge
        engine2 = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )
        trades_1m = [
            create_test_trade("T002", 1704110400000, -1, 1_500_000.0, 1.1005),
        ]
        result_1m = engine2.run(trades_1m, prior_state=None)

        # Position should remain -1.5M (no hedge, below threshold)
        assert abs(result_1m.final_state.net_position - (-1_500_000.0)) < 1e-8, (
            f"Expected position -1.5M, got {result_1m.final_state.net_position}"
        )
        # Should have no externalization
        assert result_1m.metrics["externalized_volume"] == 0.0

        # Test 3: Multiple trades accumulating to exceed threshold
        engine3 = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )
        trades_accumulate = [
            create_test_trade("T003", 1704110400000, -1, 1_000_000.0, 1.1005),  # pos = -1M
            create_test_trade("T004", 1704110401000, -1, 800_000.0, 1.1005),    # pos = -1.8M
            create_test_trade("T005", 1704110402000, -1, 500_000.0, 1.1005),    # pos = -2.3M → HEDGE to 0
        ]
        result_accum = engine3.run(trades_accumulate, prior_state=None)

        # Final position should be 0 (hedge triggered when position hit -2.3M)
        assert abs(result_accum.final_state.net_position) < 1e-8, (
            f"Expected position 0, got {result_accum.final_state.net_position}"
        )

    def test_empty_trades(self, test_data_root):
        """Test shard with no client trades."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run([], prior_state=None)

        # Should return clean state
        assert result.final_state.net_position == 0.0
        assert len(result.pnl_records) == 0
        assert result.metrics["total_client_volume"] == 0.0

    def test_time_to_close_tracking(self, test_data_root):
        """Test that time-to-close metrics are calculated."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        # Create trade that leaves open position
        # House SELLS 500 → position = -500 (stays open, within band)
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 500.0, 1.1005),  # House SELLS 500
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(client_trades, prior_state=None)

        # Verify time-to-close metrics exist
        assert "open_slice_count" in result.metrics
        assert "max_time_open_seconds" in result.metrics

        # Should have open slices
        assert result.metrics["open_slice_count"] > 0
        assert result.metrics["max_time_open_seconds"] >= 0.0

    def test_hedge_delay_across_days(self, test_data_root):
        """Test that pending hedges are chained across day boundaries.

        Scenario:
        - Day 1: Trade triggers hedge with delay extending beyond Day 1's last trade
        - Day 2: Engine should receive pending hedges from Day 1 and execute them

        This tests the fix for pending hedges being lost at day boundaries.
        Note: With heap-based timeline, hedges execute at their scheduled time within the
        same day if possible. This test uses a hedge scheduled AFTER day 1's timeline ends.
        """
        from efxbt.core.config.hedging_config import HedgeToTargetParams

        # Day 1: Trade at 12:00:00, last sample at 12:00:00
        # Hedge delay 100 seconds -> scheduled for 12:01:40
        # But no more trades in Day 1, so timeline ends at 12:00:00
        # With heap-based execution, hedge executes at 12:01:40 (dynamic timeline point)
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=HedgingRuleSet(
                groups=[],
                rules=[
                    # No hedge for small positions
                    HedgingRule(
                        pair_or_group="ALL",
                        amount_type="absolute",
                        from_amount=0,
                        to_amount=500.0,
                        action=NoHedgeParams(),
                    ),
                    # Hedge to zero for positions > 500
                    HedgingRule(
                        pair_or_group="ALL",
                        amount_type="absolute",
                        from_amount=500.0,
                        to_amount=float("inf"),
                        action=HedgeToTargetParams(target_percentage=0.0),
                    ),
                ],
            ),
            sample_interval_seconds=30,
            hedge_delay_ms=100000,  # 100 second delay
        )

        # Day 1: Single trade triggers hedge
        day1_trades = [
            create_test_trade("T001", 1704110400000, -1, 1000.0, 1.1005),  # House SELLS 1000
        ]

        engine_day1 = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result_day1 = engine_day1.run(day1_trades, prior_state=None)

        # With heap-based timeline, hedge executes at scheduled time (100s after trade)
        # Position should be 0 (hedge executed, flattened)
        assert result_day1.final_state.net_position == 0.0, (
            f"Expected position 0 (hedge executed at scheduled time), got {result_day1.final_state.net_position}"
        )

        # Verify hedge executed (should be in metrics)
        assert result_day1.metrics["hedge_trade_count"] == 1, (
            "Expected 1 hedge trade to have executed"
        )

    def test_hedge_delay_exact_timing(self, test_data_root):
        """Test that hedge executes at exactly the scheduled time (delay_ms after trigger).

        This is the key test for the heap-based timeline fix that ensures hedges don't
        wait for the next sample/trade point but execute at their exact scheduled time.
        """
        from efxbt.core.config.hedging_config import HedgeToTargetParams

        # Use a small delay (50ms) - this should execute at t+50ms, not t+60s
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=HedgingRuleSet(
                groups=[],
                rules=[
                    HedgingRule(
                        pair_or_group="ALL",
                        amount_type="absolute",
                        from_amount=0,
                        to_amount=500.0,
                        action=NoHedgeParams(),
                    ),
                    HedgingRule(
                        pair_or_group="ALL",
                        amount_type="absolute",
                        from_amount=500.0,
                        to_amount=float("inf"),
                        action=HedgeToTargetParams(target_percentage=0.0),
                    ),
                ],
            ),
            sample_interval_seconds=60,  # 60 second sample interval
            hedge_delay_ms=50,  # 50ms delay - hedge should NOT wait 60s
        )

        # Trade at t=1704110400000
        # With old code: hedge waits for next sample at t+60s
        # With fix: hedge executes at t+50ms
        trades = [
            create_test_trade("T001", 1704110400000, -1, 1000.0, 1.1005),
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        result = engine.run(trades, prior_state=None)

        # Find the hedge fill record
        hedge_records = [
            attr
            for rec in result.pnl_records
            for attr in rec.trade_attributions
            if attr.event_type == "hedge_fill"
        ]

        assert len(hedge_records) > 0, "Expected at least one hedge fill"

        # Hedge should execute at t+50ms, not t+60s
        hedge_timestamp = hedge_records[0].timestamp_ms
        expected_timestamp = 1704110400000 + 50  # trigger time + delay

        assert hedge_timestamp == expected_timestamp, (
            f"Expected hedge at {expected_timestamp} (trigger + 50ms), "
            f"got {hedge_timestamp}. Diff: {hedge_timestamp - 1704110400000}ms"
        )


class TestShardEngineErrorHandling:
    """Test error handling in ShardEngine."""

    def test_missing_market_data(self, test_data_root):
        """Test handling when market data is missing."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        # Create trade for pair without market data
        client_trades = [
            create_test_trade("T001", 1704110400000, 1, 500.0, 1.1005, "EURGBP"),
        ]

        engine = ShardEngine(
            pair="EURGBP",  # No market data for EURGBP
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        # Should raise error about missing market data
        with pytest.raises((FileNotFoundError, ValueError)):
            engine.run(client_trades, prior_state=None)

    def test_invalid_prior_state(self, test_data_root):
        """Test handling invalid prior state."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedging_rules=make_hedging_rules(risk_band_qty=1000.0),
            sample_interval_seconds=30,
        )

        # Create prior state for wrong pair
        invalid_prior_state = ShardState(
            pair="GBPUSD",  # Wrong pair
            date="20231231",
            net_position=500.0,
        )

        # House SELLS 500
        client_trades = [
            create_test_trade("T001", 1704110400000, -1, 500.0, 1.1005),
        ]

        engine = ShardEngine(
            pair="EURUSD",
            date="20240101",
            config=config,
            data_root=test_data_root,
        )

        # Should handle gracefully (use provided state anyway or warn)
        # For now, just verify it doesn't crash
        result = engine.run(client_trades, prior_state=invalid_prior_state)
        assert result is not None
