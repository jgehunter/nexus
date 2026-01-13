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
from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.shard.shard_engine import ShardEngine
from efxbt.engine.shard.state import ShardState


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
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 500.0, "hedge_mode": "full"},
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
        assert result.metrics["total_hedge_volume"] > 0  # Hedge executed
        assert result.metrics["internalization_ratio"] < 1.0  # Not fully internalized

    def test_state_chaining_across_days(self, test_data_root):
        """Test state chaining from day N to day N+1."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 500.0, "hedge_mode": "full"},
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
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 500.0, "hedge_mode": "partial"},
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
        assert result.metrics["total_hedge_volume"] == 500.0  # Partial hedge
        assert result.metrics["internalization_ratio"] == 0.5  # 50% internalized

    def test_empty_trades(self, test_data_root):
        """Test shard with no client trades."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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


class TestShardEngineErrorHandling:
    """Test error handling in ShardEngine."""

    def test_missing_market_data(self, test_data_root):
        """Test handling when market data is missing."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
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
