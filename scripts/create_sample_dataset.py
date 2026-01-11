"""Create sample dataset for testing Phase 1 functionality.

This script creates a sample dataset with:
- Multiple trade books (MAD_GLD, MAD_SLV)
- Market data for gold pairs
- Multiple dates and pairs
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend" / "efxbt" / "src"
sys.path.insert(0, str(backend_path))

import pyarrow as pa
import pyarrow.parquet as pq

from efxbt.core.data.schemas import MARKET_ARROW_SCHEMA, TRADE_ARROW_SCHEMA


def create_sample_dataset(data_root: Path) -> None:
    """Create a sample dataset for demonstration.

    Args:
        data_root: Root data directory
    """
    dataset_name = "sample_efx_2024"
    dataset_dir = data_root / "datasets" / dataset_name
    dataset_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating sample dataset: {dataset_name}")
    print(f"Location: {dataset_dir}")

    # Create trades for MAD_GLD book
    print("\n1. Creating MAD_GLD trades...")
    create_trades_book(dataset_dir, "MAD_GLD", "EURUSD", ["20240101", "20240102"])
    create_trades_book(dataset_dir, "MAD_GLD", "GBPUSD", ["20240101", "20240102"])

    # Create trades for MAD_SLV book
    print("2. Creating MAD_SLV trades...")
    create_trades_book(dataset_dir, "MAD_SLV", "EURUSD", ["20240101"])
    create_trades_book(dataset_dir, "MAD_SLV", "USDJPY", ["20240101"])

    # Create market data in gold subdirectory
    print("3. Creating gold market data...")
    create_market_data(
        dataset_dir, "gold", "EURUSD", ["20240101", "20240102", "20240103"]
    )
    create_market_data(dataset_dir, "gold", "GBPUSD", ["20240101", "20240102"])
    create_market_data(dataset_dir, "gold", "USDJPY", ["20240101"])

    print(f"\n✓ Sample dataset created successfully!")
    print(f"  - Location: {dataset_dir}")
    print(f"  - Trade books: MAD_GLD, MAD_SLV")
    print(f"  - Pairs: EURUSD, GBPUSD, USDJPY")
    print(f"  - Date range: 20240101-20240103")


def create_trades_book(
    dataset_dir: Path, book: str, pair: str, dates: list[str]
) -> None:
    """Create trade files for a specific book and pair.

    Args:
        dataset_dir: Dataset root directory
        book: Book name (e.g., MAD_GLD)
        pair: Currency pair
        dates: List of dates in YYYYMMDD format
    """
    trades_dir = dataset_dir / "trades" / book
    trades_dir.mkdir(parents=True, exist_ok=True)

    for date in dates:
        # Generate sample trade data
        base_ts = int(date) * 86400000  # Convert YYYYMMDD to approximate ms

        trade_data = {
            "timestamp_ms": [
                base_ts + 3600000,  # 1 hour into day
                base_ts + 7200000,  # 2 hours
                base_ts + 10800000,  # 3 hours
                base_ts + 14400000,  # 4 hours
                base_ts + 18000000,  # 5 hours
            ],
            "pair": [pair] * 5,
            "side": [1, -1, 1, -1, 1],
            "qty": [100000.0, 150000.0, 200000.0, 175000.0, 125000.0],
            "price": [1.1000 + i * 0.0001 for i in range(5)],
            "trade_id": [f"{book}_{pair}_{date}_T{i+1}" for i in range(5)],
            "order_id": [None] * 5,
        }

        trade_table = pa.table(trade_data, schema=TRADE_ARROW_SCHEMA)
        output_path = trades_dir / f"{date}.parquet"
        pq.write_table(trade_table, output_path)
        print(f"   Created: {output_path.relative_to(dataset_dir)}")


def create_market_data(
    dataset_dir: Path, metal: str, pair: str, dates: list[str]
) -> None:
    """Create market data files for a pair.

    Args:
        dataset_dir: Dataset root directory
        metal: Metal subdirectory (gold/silver)
        pair: Currency pair
        dates: List of dates in YYYYMMDD format
    """
    market_dir = dataset_dir / "market" / metal / pair
    market_dir.mkdir(parents=True, exist_ok=True)

    for date in dates:
        # Generate sample tick data
        base_ts = int(date) * 86400000

        # Create ticks every minute for 6 hours
        num_ticks = 360
        timestamps = [base_ts + i * 60000 for i in range(num_ticks)]

        market_data = {
            "timestamp_ms": timestamps,
            "pair": [pair] * num_ticks,
            "bid_tob": [1.0999 + (i % 100) * 0.00001 for i in range(num_ticks)],
            "ask_tob": [1.1001 + (i % 100) * 0.00001 for i in range(num_ticks)],
            "bid_qty_tob": [1000000.0] * num_ticks,
            "ask_qty_tob": [1000000.0] * num_ticks,
            "bid_rungs_qty": [None] * num_ticks,
            "bid_rungs_price": [None] * num_ticks,
            "ask_rungs_qty": [None] * num_ticks,
            "ask_rungs_price": [None] * num_ticks,
        }

        market_table = pa.table(market_data, schema=MARKET_ARROW_SCHEMA)
        output_path = market_dir / f"{date}.parquet"
        pq.write_table(market_table, output_path)
        print(f"   Created: {output_path.relative_to(dataset_dir)}")


if __name__ == "__main__":
    # Determine data root
    script_dir = Path(__file__).parent
    data_root = script_dir.parent / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    create_sample_dataset(data_root)
