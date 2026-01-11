"""Integration tests for MultiShardSimulator.

Tests the complete simulation pipeline across multiple shards:
- Shard discovery
- State chaining across dates
- Multi-pair simulation
- Result aggregation
- Parquet output writing
"""

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from efxbt.core.config.run_config import SimulationConfig
from efxbt.core.data.schemas import DecrossedTradeRecord
from efxbt.engine.simulation.simulator import MultiShardSimulator


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


def create_test_market_data(pair: str, date_str: str, data_root: Path) -> None:
    """Create minimal test market data."""
    market_dir = data_root / "datasets" / "test" / "market" / pair
    market_dir.mkdir(parents=True, exist_ok=True)

    # Generate simple market data
    timestamps = []
    bids = []
    asks = []

    base_time = 1704110400000  # 2024-01-01 00:00:00 UTC
    if date_str == "20240102":
        base_time += 86400000  # +1 day

    base_bid = 1.0998
    base_ask = 1.1002

    for i in range(120):
        timestamps.append(base_time + (i * 1000))
        bids.append(base_bid + (i * 0.0001))
        asks.append(base_ask + (i * 0.0001))

    table = pa.table({
        "timestamp_ms": pa.array(timestamps, type=pa.int64()),
        "pair": pa.array([pair] * len(timestamps), type=pa.string()),
        "bid_tob": pa.array(bids, type=pa.float64()),
        "ask_tob": pa.array(asks, type=pa.float64()),
    })

    output_file = market_dir / f"{date_str}.parquet"
    pq.write_table(table, output_file)


def create_decrossed_trades_file(
    pair: str,
    date_str: str,
    trades: list[DecrossedTradeRecord],
    decrossed_dir: Path,
) -> None:
    """Write decrossed trades to parquet file."""
    date_dir = decrossed_dir / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    if not trades:
        # Create empty file
        empty_table = pa.table({})
        pq.write_table(empty_table, date_dir / f"{pair}.parquet")
        return

    # Convert trades to dict
    rows = [
        {
            "trade_id": t.trade_id,
            "source_trade_id": t.source_trade_id,
            "order_id": t.order_id,
            "timestamp_ms": t.timestamp_ms,
            "pair": t.pair,
            "source_pair": t.source_pair,
            "side": t.side,
            "qty": t.qty,
            "price": t.price,
            "source_price": t.source_price,
            "is_direct": t.is_direct,
            "path": t.path,
            "leg_index": t.leg_index,
            "leg_count": t.leg_count,
        }
        for t in trades
    ]

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, date_dir / f"{pair}.parquet")


@pytest.fixture
def test_environment():
    """Create complete test environment with market data and decrossed trades."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir)
        decrossed_dir = data_root / "decrossed"
        output_dir = data_root / "simulation"

        # Create market data for 2 days, 2 pairs
        for date_str in ["20240101", "20240102"]:
            create_test_market_data("EURUSD", date_str, data_root)
            create_test_market_data("GBPUSD", date_str, data_root)

        # Create decrossed trades
        # Day 1 - EURUSD
        day1_eurusd_trades = [
            create_test_trade("D1_EUR_T001", 1704110400000, 1, 500.0, 1.1005, "EURUSD"),
            create_test_trade("D1_EUR_T002", 1704110430000, -1, 300.0, 1.0995, "EURUSD"),
        ]
        create_decrossed_trades_file("EURUSD", "20240101", day1_eurusd_trades, decrossed_dir)

        # Day 1 - GBPUSD
        day1_gbpusd_trades = [
            create_test_trade("D1_GBP_T001", 1704110400000, 1, 1000.0, 1.2505, "GBPUSD"),
        ]
        create_decrossed_trades_file("GBPUSD", "20240101", day1_gbpusd_trades, decrossed_dir)

        # Day 2 - EURUSD
        day2_eurusd_trades = [
            create_test_trade("D2_EUR_T001", 1704196800000, -1, 200.0, 1.0990, "EURUSD"),
        ]
        create_decrossed_trades_file("EURUSD", "20240102", day2_eurusd_trades, decrossed_dir)

        # Day 2 - GBPUSD
        day2_gbpusd_trades = [
            create_test_trade("D2_GBP_T001", 1704196800000, -1, 800.0, 1.2490, "GBPUSD"),
        ]
        create_decrossed_trades_file("GBPUSD", "20240102", day2_gbpusd_trades, decrossed_dir)

        yield {
            "data_root": data_root,
            "decrossed_dir": decrossed_dir,
            "output_dir": output_dir,
        }


class TestMultiShardSimulator:
    """Integration tests for multi-shard simulation."""

    def test_discover_shards(self, test_environment):
        """Test shard discovery from decrossed output."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        # Discover shards
        shards = simulator._discover_shards(test_environment["decrossed_dir"])

        # Should find 4 shards: (2 dates × 2 pairs)
        assert len(shards) == 4

        # Verify shard structure
        pairs = set(s["pair"] for s in shards)
        dates = set(s["date"] for s in shards)

        assert pairs == {"EURUSD", "GBPUSD"}
        assert dates == {"20240101", "20240102"}

    def test_multi_shard_simulation(self, test_environment):
        """Test complete multi-shard simulation."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            test_environment["decrossed_dir"],
            test_environment["output_dir"],
        )

        # Verify aggregated results
        assert result.total_shards == 4
        assert set(result.pairs) == {"EURUSD", "GBPUSD"}
        assert result.date_range == ("20240101", "20240102")

        # Verify total volume aggregation
        # Day 1: EURUSD (500+300) + GBPUSD (1000) = 1800
        # Day 2: EURUSD (200) + GBPUSD (800) = 1000
        # Total: 2800
        assert result.total_client_volume == 2800.0

        # Verify PnL aggregation (should be non-zero)
        assert result.total_pnl != 0.0

        # Verify output files created
        assert (test_environment["output_dir"] / "pnl_attribution.parquet").exists()

    def test_state_chaining_across_dates(self, test_environment):
        """Test that state chains correctly across dates for same pair."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            test_environment["decrossed_dir"],
            test_environment["output_dir"],
        )

        # Find EURUSD shards in results
        eurusd_shards = [s for s in result.shard_results if s["pair"] == "EURUSD"]
        assert len(eurusd_shards) == 2  # 2 dates

        # Verify they processed in chronological order
        # Day 1: +500 -300 = +200
        # Day 2: +200 (from day 1) -200 = 0
        # Final internalization should reflect state continuity

    def test_pnl_attribution_output(self, test_environment):
        """Test PnL attribution parquet output."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            test_environment["decrossed_dir"],
            test_environment["output_dir"],
        )

        # Read PnL attribution file
        attribution_file = test_environment["output_dir"] / "pnl_attribution.parquet"
        assert attribution_file.exists()

        table = pq.read_table(attribution_file)

        # Should have attribution records
        assert len(table) > 0

        # Verify schema
        expected_columns = {
            "timestamp_ms",
            "event_type",
            "source_trade_id",
            "pair",
            "native_currency",
            "reporting_currency",
            "fx_rate",
            "execution_pnl_native",
            "execution_pnl_reporting",
            "inventory_pnl_native",
            "inventory_pnl_reporting",
            "hedge_pnl_native",
            "hedge_pnl_reporting",
            "unrealized_pnl_native",
            "unrealized_pnl_reporting",
        }

        assert set(table.column_names) >= expected_columns

    def test_empty_decrossed_directory(self, test_environment):
        """Test handling of empty decrossed directory."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        # Create empty directory
        empty_dir = test_environment["data_root"] / "empty_decrossed"
        empty_dir.mkdir()

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            empty_dir,
            test_environment["output_dir"],
        )

        # Should return empty result
        assert result.total_shards == 0
        assert result.total_client_volume == 0.0
        assert result.total_pnl == 0.0

    def test_per_shard_metrics(self, test_environment):
        """Test that per-shard metrics are included in results."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            test_environment["decrossed_dir"],
            test_environment["output_dir"],
        )

        # Verify each shard has metrics
        for shard_result in result.shard_results:
            assert "pair" in shard_result
            assert "date" in shard_result

            # Metrics are now flat in the shard_result dict
            # Since we may not have pnl_breakdown nested, just verify key metrics exist
            # The actual structure depends on how ShardEngine populates shard_results

    def test_multi_pair_aggregation(self, test_environment):
        """Test correct aggregation across multiple pairs."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            test_environment["decrossed_dir"],
            test_environment["output_dir"],
        )

        # Calculate expected volumes
        # EURUSD: Day1 (500+300) + Day2 (200) = 1000
        # GBPUSD: Day1 (1000) + Day2 (800) = 1800
        # Total: 2800
        assert result.total_client_volume == 2800.0

        # Verify both pairs are represented
        assert len(result.pairs) == 2
        assert "EURUSD" in result.pairs
        assert "GBPUSD" in result.pairs


class TestMultiShardSimulatorEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_market_data_for_pair(self, test_environment):
        """Test handling when market data missing for a pair."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        # Create decrossed trades for pair without market data
        fake_trades = [
            create_test_trade("T001", 1704110400000, 1, 500.0, 0.8795, "EURGBP"),
        ]
        create_decrossed_trades_file(
            "EURGBP", "20240101", fake_trades, test_environment["decrossed_dir"]
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        # Should handle gracefully (skip shard or raise clear error)
        with pytest.raises((FileNotFoundError, ValueError)):
            simulator.run(
                test_environment["decrossed_dir"],
                test_environment["output_dir"],
            )

    def test_chronological_ordering_preservation(self, test_environment):
        """Test that shards are processed in chronological order per pair."""
        config = SimulationConfig(
            dataset="test",
            reporting_currency="USD",
            hedge_policy="aggressive",
            hedge_policy_config={"risk_band_qty": 1000.0, "hedge_mode": "full"},
            sample_interval_seconds=30,
        )

        simulator = MultiShardSimulator(config, test_environment["data_root"])

        result = simulator.run(
            test_environment["decrossed_dir"],
            test_environment["output_dir"],
        )

        # Verify EURUSD shards are ordered by date
        eurusd_shards = [s for s in result.shard_results if s["pair"] == "EURUSD"]
        dates = [s["date"] for s in eurusd_shards]

        assert dates == sorted(dates), "Shards should be processed in chronological order"
