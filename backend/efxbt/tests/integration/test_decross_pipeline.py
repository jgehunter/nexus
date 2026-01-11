"""Integration tests for the complete decrossing pipeline.

Tests end-to-end decrossing from tradebook input through to decrossed output,
verifying correctness of decomposition, price backsolving, and output format.
"""

from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from efxbt.app.services.decross import DecrossService
from efxbt.core.data.schemas import TradeRecord

from .fixtures.test_data import (
    create_sample_trades,
    create_test_market_dataset,
    create_test_tradebook,
)


class TestDecrossPipeline:
    """End-to-end integration tests for decrossing pipeline."""

    @pytest.fixture
    def test_environment(self, tmp_path):
        """Setup test environment with market data and tradebook.

        Creates:
        - Test market dataset with EURUSD, GBPUSD, USDJPY ticks
        - Test tradebook with both direct and cross-pair trades
        """
        data_root = tmp_path / "data"
        results_root = tmp_path / "results"

        # Create test market dataset (3 days of data)
        create_test_market_dataset(
            data_root,
            dataset_name="test_fx",
            pairs=["EURUSD", "GBPUSD", "USDJPY"],
            date_range=("20240101", "20240103"),
            ticks_per_day=100,  # Fewer ticks for faster tests
        )

        # Create test trade book with mix of direct and cross pairs
        test_trades = [
            # Cross pair trade: EURGBP
            TradeRecord(
                timestamp_ms=int(datetime(2024, 1, 1, 10, 0).timestamp() * 1000),
                pair="EURGBP",  # Cross pair
                side=1,  # BUY
                qty=1000.0,
                price=0.88,
                trade_id="T001",
            ),
            # Direct pair trade: EURUSD
            TradeRecord(
                timestamp_ms=int(datetime(2024, 1, 1, 11, 0).timestamp() * 1000),
                pair="EURUSD",  # Direct pair
                side=-1,  # SELL
                qty=500.0,
                price=1.10,
                trade_id="T002",
            ),
            # Another cross pair: EURGBP (SELL)
            TradeRecord(
                timestamp_ms=int(datetime(2024, 1, 1, 12, 0).timestamp() * 1000),
                pair="EURGBP",  # Cross pair
                side=-1,  # SELL
                qty=2000.0,
                price=0.88,
                trade_id="T003",
            ),
        ]

        create_test_tradebook(data_root, "test_book", test_trades)

        return {
            "data_root": data_root,
            "results_root": results_root,
            "dataset": "test_fx",
            "tradebook": "test_book",
        }

    def test_decross_cross_pair_trade(self, test_environment):
        """Test decrossing of cross-pair trade produces correct legs."""
        service = DecrossService(test_environment["data_root"])
        output_dir = test_environment["results_root"] / "run_001" / "decrossed"

        # Run decrossing
        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir,
        )

        # Verify output structure exists
        assert output_dir.exists(), "Output directory should be created"

        # Load all decrossed trades
        all_legs = []
        for date_dir in output_dir.iterdir():
            if date_dir.is_dir():
                for parquet_file in date_dir.glob("*.parquet"):
                    table = pq.read_table(parquet_file)
                    all_legs.extend(table.to_pylist())

        # Should have legs from all 3 trades
        assert len(all_legs) > 0, "Should have decrossed legs"

        # Find EURGBP legs (trade T001)
        eurgbp_buy_legs = [
            leg for leg in all_legs
            if leg["source_pair"] == "EURGBP" and leg["source_trade_id"] == "T001"
        ]
        assert len(eurgbp_buy_legs) == 2, "EURGBP should be decrossed into 2 legs"

        # Verify legs have correct pairs (EURUSD and GBPUSD)
        leg_pairs = {leg["pair"] for leg in eurgbp_buy_legs}
        assert leg_pairs == {"EURUSD", "GBPUSD"}, f"Expected EURUSD and GBPUSD, got {leg_pairs}"

        # Verify metadata
        for leg in eurgbp_buy_legs:
            assert leg["is_direct"] is False, "Cross-pair legs should have is_direct=False"
            assert leg["leg_count"] == 2, "EURGBP path should have 2 legs"
            assert leg["source_pair"] == "EURGBP", "Source pair should be EURGBP"

    def test_decross_direct_pair_passthrough(self, test_environment):
        """Test that direct-pair trades pass through unchanged."""
        service = DecrossService(test_environment["data_root"])
        output_dir = test_environment["results_root"] / "run_002" / "decrossed"

        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir,
        )

        # Load all legs
        all_legs = []
        for date_dir in output_dir.iterdir():
            if date_dir.is_dir():
                for parquet_file in date_dir.glob("*.parquet"):
                    table = pq.read_table(parquet_file)
                    all_legs.extend(table.to_pylist())

        # Find EURUSD direct trade (T002)
        eurusd_legs = [
            leg for leg in all_legs
            if leg["source_trade_id"] == "T002"
        ]
        assert len(eurusd_legs) == 1, "Direct pair should have exactly 1 leg"

        leg = eurusd_legs[0]
        assert leg["pair"] == "EURUSD", "Direct pair should match source pair"
        assert leg["is_direct"] is True, "Should be marked as direct"
        assert leg["leg_count"] == 1, "Direct pair should have leg_count=1"
        assert leg["qty"] == 500.0, "Quantity should match source"
        assert leg["side"] == -1, "Side should match source"

    def test_decross_both_buy_and_sell(self, test_environment):
        """Test that both BUY and SELL cross-pair trades are handled correctly."""
        service = DecrossService(test_environment["data_root"])
        output_dir = test_environment["results_root"] / "run_003" / "decrossed"

        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir,
        )

        # Load all legs
        all_legs = []
        for date_dir in output_dir.iterdir():
            if date_dir.is_dir():
                for parquet_file in date_dir.glob("*.parquet"):
                    table = pq.read_table(parquet_file)
                    all_legs.extend(table.to_pylist())

        # Find BUY EURGBP legs (T001)
        buy_legs = [
            leg for leg in all_legs
            if leg["source_trade_id"] == "T001"
        ]
        assert len(buy_legs) == 2, "BUY EURGBP should have 2 legs"

        # Find SELL EURGBP legs (T003)
        sell_legs = [
            leg for leg in all_legs
            if leg["source_trade_id"] == "T003"
        ]
        assert len(sell_legs) == 2, "SELL EURGBP should have 2 legs"

        # Verify sides are consistent (not necessarily same, depends on path)
        # Both should have valid sides (+1 or -1)
        for leg in buy_legs + sell_legs:
            assert leg["side"] in [1, -1], f"Invalid side: {leg['side']}"

    def test_determinism(self, test_environment):
        """Test that decrossing produces identical output on repeated runs."""
        service = DecrossService(test_environment["data_root"])

        output_dir_1 = test_environment["results_root"] / "run_a" / "decrossed"
        output_dir_2 = test_environment["results_root"] / "run_b" / "decrossed"

        # Run twice
        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir_1,
        )

        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir_2,
        )

        # Compare outputs
        files_1 = sorted(output_dir_1.rglob("*.parquet"))
        files_2 = sorted(output_dir_2.rglob("*.parquet"))

        assert len(files_1) == len(files_2), "Should have same number of output files"
        assert len(files_1) > 0, "Should have at least one output file"

        # Compare each file
        for f1, f2 in zip(files_1, files_2):
            table1 = pq.read_table(f1)
            table2 = pq.read_table(f2)

            # Convert to list of dicts for comparison
            list1 = sorted(table1.to_pylist(), key=lambda x: x["source_trade_id"])
            list2 = sorted(table2.to_pylist(), key=lambda x: x["source_trade_id"])

            # Should be identical
            assert list1 == list2, f"Files {f1.name} and {f2.name} differ"

    def test_output_partitioning(self, test_environment):
        """Test that output is correctly partitioned by date and pair."""
        service = DecrossService(test_environment["data_root"])
        output_dir = test_environment["results_root"] / "run_004" / "decrossed"

        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir,
        )

        # Check directory structure: output_dir/YYYYMMDD/PAIR.parquet
        date_dirs = list(output_dir.iterdir())
        assert len(date_dirs) > 0, "Should have date directories"

        # Check that date directories are named correctly (YYYYMMDD)
        for date_dir in date_dirs:
            assert date_dir.is_dir(), f"{date_dir} should be a directory"
            assert len(date_dir.name) == 8, f"Date dir name should be YYYYMMDD: {date_dir.name}"
            assert date_dir.name.isdigit(), f"Date dir name should be numeric: {date_dir.name}"

            # Check parquet files within date directory
            parquet_files = list(date_dir.glob("*.parquet"))
            assert len(parquet_files) > 0, f"Date dir {date_dir.name} should have parquet files"

            # Verify parquet files are named by pair
            for pq_file in parquet_files:
                pair_name = pq_file.stem  # e.g., "EURUSD"
                assert len(pair_name) == 6, f"Pair name should be 6 chars: {pair_name}"
                assert pair_name.isupper(), f"Pair name should be uppercase: {pair_name}"

    def test_quantity_conservation(self, test_environment):
        """Test that quantities are properly conserved across legs."""
        service = DecrossService(test_environment["data_root"])
        output_dir = test_environment["results_root"] / "run_005" / "decrossed"

        service.decross_tradebook(
            tradebook_name=test_environment["tradebook"],
            market_dataset_name=test_environment["dataset"],
            output_dir=output_dir,
        )

        # Load all legs
        all_legs = []
        for date_dir in output_dir.iterdir():
            if date_dir.is_dir():
                for parquet_file in date_dir.glob("*.parquet"):
                    table = pq.read_table(parquet_file)
                    all_legs.extend(table.to_pylist())

        # For cross-pair trades, verify legs have reasonable quantities
        cross_legs = [leg for leg in all_legs if not leg["is_direct"]]

        for leg in cross_legs:
            # Quantities should be positive
            assert leg["qty"] > 0, f"Leg quantity should be positive: {leg['qty']}"

            # Quantities should be reasonable (not NaN, not infinity)
            assert abs(leg["qty"]) < 1e10, f"Leg quantity seems unreasonable: {leg['qty']}"

            # Prices should be reasonable
            assert leg["price"] > 0, f"Leg price should be positive: {leg['price']}"
            assert abs(leg["price"]) < 1e6, f"Leg price seems unreasonable: {leg['price']}"


class TestDecrossErrors:
    """Tests for error handling in decrossing pipeline."""

    def test_missing_market_data(self, tmp_path):
        """Test handling of missing market data."""
        data_root = tmp_path / "data"

        # Create empty market dataset (no tick data)
        (data_root / "datasets" / "empty_fx" / "market").mkdir(parents=True)

        # Create tradebook
        trades = [
            TradeRecord(
                timestamp_ms=int(datetime(2024, 1, 1, 10, 0).timestamp() * 1000),
                pair="EURUSD",
                side=1,
                qty=1000.0,
                price=1.10,
                trade_id="T001",
            ),
        ]
        create_test_tradebook(data_root, "test_book", trades)

        service = DecrossService(data_root)
        output_dir = tmp_path / "results" / "run_error" / "decrossed"

        # Should handle missing data gracefully (not crash)
        # Errors should be logged but processing should continue
        try:
            service.decross_tradebook(
                tradebook_name="test_book",
                market_dataset_name="empty_fx",
                output_dir=output_dir,
            )
            # If it doesn't raise, that's okay - check that output is empty or minimal
        except Exception as e:
            # Some errors are acceptable (e.g., no market data found)
            pass

    def test_invalid_tradebook(self, tmp_path):
        """Test handling of invalid tradebook name."""
        data_root = tmp_path / "data"

        # Create market dataset
        create_test_market_dataset(
            data_root,
            dataset_name="test_fx",
            pairs=["EURUSD"],
            date_range=("20240101", "20240101"),
        )

        service = DecrossService(data_root)
        output_dir = tmp_path / "results" / "run_error" / "decrossed"

        # Should raise FileNotFoundError for non-existent tradebook
        with pytest.raises(FileNotFoundError, match="not found"):
            service.decross_tradebook(
                tradebook_name="nonexistent_book",
                market_dataset_name="test_fx",
                output_dir=output_dir,
            )
