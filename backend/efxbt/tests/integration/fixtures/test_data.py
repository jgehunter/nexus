"""Test data generation utilities for integration testing.

Provides functions to create realistic test market datasets and tradebooks
for end-to-end decrossing pipeline testing.
"""

import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from efxbt.core.data.schemas import (
    MARKET_ARROW_SCHEMA,
    TRADE_ARROW_SCHEMA,
    MarketTickRecord,
    TradeRecord,
)


def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """Generate list of dates in YYYYMMDD format.

    Args:
        start_date: Start date in YYYYMMDD format
        end_date: End date in YYYYMMDD format

    Returns:
        List of date strings in YYYYMMDD format
    """
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")

    dates = []
    current_dt = start_dt
    while current_dt <= end_dt:
        dates.append(current_dt.strftime("%Y%m%d"))
        current_dt += timedelta(days=1)

    return dates


def generate_realistic_ticks(
    pair: str,
    date: str,
    tick_count: int = 1000,
    base_price: float | None = None,
) -> list[MarketTickRecord]:
    """Generate realistic FX ticks with realistic prices and spreads.

    Args:
        pair: Currency pair (e.g., "EURUSD")
        date: Date in YYYYMMDD format
        tick_count: Number of ticks to generate
        base_price: Base price level (uses defaults if None)

    Returns:
        List of MarketTickRecord objects with realistic prices
    """
    # Default base prices for common pairs
    default_base_prices = {
        "EURUSD": 1.10,
        "GBPUSD": 1.25,
        "USDJPY": 150.0,
        "EURGBP": 0.88,
        "EURJPY": 165.0,
        "GBPJPY": 187.5,
        "AUDUSD": 0.65,
        "USDCAD": 1.35,
        "NZDUSD": 0.60,
    }

    # Use provided base price or default
    if base_price is None:
        base_price = default_base_prices.get(pair, 1.0)

    # Spread in basis points (0.2 bps = 0.00002)
    spread_bps = 2  # 2 basis points spread
    spread = base_price * (spread_bps / 10000)

    # Generate ticks with random walk
    ticks = []
    start_ts = datetime.strptime(date, "%Y%m%d").timestamp() * 1000

    current_price = base_price
    for i in range(tick_count):
        # Random walk with mean reversion
        price_change = random.gauss(0, base_price * 0.0001)  # 0.01% std dev
        mean_reversion = (base_price - current_price) * 0.01  # 1% reversion
        current_price += price_change + mean_reversion

        # Calculate bid/ask from mid
        mid = current_price
        bid = mid - spread / 2
        ask = mid + spread / 2

        # Timestamp: evenly spaced throughout the day
        timestamp_ms = int(start_ts + (i * 86400000 / tick_count))

        tick = MarketTickRecord(
            timestamp_ms=timestamp_ms,
            pair=pair,
            bid_tob=bid,
            ask_tob=ask,
            bid_qty_tob=1000000.0,  # Standard 1M liquidity
            ask_qty_tob=1000000.0,
        )
        ticks.append(tick)

    return ticks


def create_test_market_dataset(
    data_root: Path,
    dataset_name: str,
    pairs: list[str],
    date_range: tuple[str, str],
    ticks_per_day: int = 1000,
) -> None:
    """Create test market dataset with realistic tick data.

    Creates a complete market dataset directory structure with parquet files
    for each pair and date.

    Args:
        data_root: Root data directory
        dataset_name: Dataset name
        pairs: List of pairs to generate (e.g., ["EURUSD", "GBPUSD"])
        date_range: (start_date, end_date) in YYYYMMDD format
        ticks_per_day: Number of ticks to generate per day per pair

    Example:
        create_test_market_dataset(
            Path("data"),
            "test_fx",
            ["EURUSD", "GBPUSD"],
            ("20240101", "20240103"),
        )
        # Creates: data/datasets/test_fx/market/EURUSD/20240101.parquet, etc.
    """
    dataset_dir = data_root / "datasets" / dataset_name / "market"

    for pair in pairs:
        pair_dir = dataset_dir / pair
        pair_dir.mkdir(parents=True, exist_ok=True)

        # Generate ticks for each date
        for date_str in generate_date_range(*date_range):
            ticks = generate_realistic_ticks(
                pair=pair,
                date=date_str,
                tick_count=ticks_per_day,
            )

            # Convert to Arrow table
            table = pa.Table.from_pylist(
                [tick.model_dump() for tick in ticks],
                schema=MARKET_ARROW_SCHEMA,
            )

            # Write to parquet
            output_file = pair_dir / f"{date_str}.parquet"
            pq.write_table(table, output_file, compression="snappy")


def create_test_tradebook(
    data_root: Path,
    book_name: str,
    trades: list[TradeRecord],
) -> None:
    """Create test trade book with specified trades.

    Creates a tradebook directory structure with parquet files partitioned by date.

    Args:
        data_root: Root data directory
        book_name: Tradebook name
        trades: List of TradeRecord objects to write

    Example:
        trades = [
            TradeRecord(
                timestamp_ms=1704110400000,  # 2024-01-01 10:00
                pair="EURGBP",
                side=1,
                qty=1000.0,
                price=0.88,
                trade_id="T001",
            ),
        ]
        create_test_tradebook(Path("data"), "test_book", trades)
        # Creates: data/tradebooks/test_book/20240101.parquet
    """
    tradebook_dir = data_root / "tradebooks" / book_name
    tradebook_dir.mkdir(parents=True, exist_ok=True)

    # Group trades by date
    trades_by_date = defaultdict(list)
    for trade in trades:
        date_str = datetime.fromtimestamp(trade.timestamp_ms / 1000).strftime("%Y%m%d")
        trades_by_date[date_str].append(trade)

    # Write each date's trades
    for date_str, date_trades in trades_by_date.items():
        table = pa.Table.from_pylist(
            [t.model_dump() for t in date_trades],
            schema=TRADE_ARROW_SCHEMA,
        )

        output_file = tradebook_dir / f"{date_str}.parquet"
        pq.write_table(table, output_file, compression="snappy")


def create_sample_trades(
    pairs: list[str],
    start_timestamp: int,
    count_per_pair: int = 10,
) -> list[TradeRecord]:
    """Generate sample trades for testing.

    Args:
        pairs: List of currency pairs
        start_timestamp: Starting timestamp in milliseconds
        count_per_pair: Number of trades to generate per pair

    Returns:
        List of TradeRecord objects
    """
    trades = []
    trade_id_counter = 1

    for pair in pairs:
        for i in range(count_per_pair):
            # Alternate between buy and sell
            side = 1 if i % 2 == 0 else -1

            # Random quantity between 100 and 10000
            qty = random.uniform(100, 10000)

            # Timestamp: spread trades throughout the day
            timestamp_ms = start_timestamp + (i * 3600000)  # 1 hour apart

            # Price: random realistic price
            price = random.uniform(0.8, 1.5)

            trade = TradeRecord(
                timestamp_ms=timestamp_ms,
                pair=pair,
                side=side,
                qty=qty,
                price=price,
                trade_id=f"T{trade_id_counter:04d}",
            )
            trades.append(trade)
            trade_id_counter += 1

    return trades
