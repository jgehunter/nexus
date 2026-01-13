"""Generate test market dataset and tradebook for backtesting.

Creates 2 days of market data for EURUSD, EURGBP, GBPUSD with trades
of 500K and 1M quantities.
"""

import random
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Configuration
DATA_ROOT = Path(__file__).parent.parent / "data"
DATASET_NAME = "test_market"
TRADEBOOK_NAME = "test_trades"

# Date range (2 days)
DATES = ["20250601", "20250602"]

# Pairs to generate
PAIRS = ["EURUSD", "GBPUSD", "EURGBP"]

# Base prices for each pair (realistic FX rates)
BASE_PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2650,
    "EURGBP": 0.8580,
}

# Typical spreads (in pips, 1 pip = 0.0001 for most pairs)
SPREADS = {
    "EURUSD": 0.00008,  # 0.8 pips
    "GBPUSD": 0.00010,  # 1.0 pips
    "EURGBP": 0.00012,  # 1.2 pips
}

# Market tick schema
MARKET_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("pair", pa.string()),
    ("bid_tob", pa.float64()),
    ("ask_tob", pa.float64()),
    ("bid_qty_tob", pa.float64()),
    ("ask_qty_tob", pa.float64()),
])

# Trade schema
TRADE_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("pair", pa.string()),
    ("side", pa.int8()),
    ("qty", pa.float64()),
    ("price", pa.float64()),
    ("trade_id", pa.string()),
    ("order_id", pa.string()),
])


def date_to_start_ms(date_str: str) -> int:
    """Convert YYYYMMDD to start-of-day milliseconds."""
    dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def generate_price_walk(base_price: float, num_ticks: int, volatility: float = 0.0001) -> list[float]:
    """Generate random walk prices around base price."""
    prices = [base_price]
    for _ in range(num_ticks - 1):
        change = random.gauss(0, volatility)
        new_price = prices[-1] * (1 + change)
        prices.append(new_price)
    return prices


def generate_market_ticks(date_str: str, pair: str) -> list[dict]:
    """Generate market ticks for a single day and pair.

    Generates ticks every 100ms during trading hours (8am-5pm UTC).
    """
    base_ms = date_to_start_ms(date_str)
    base_price = BASE_PRICES[pair]
    spread = SPREADS[pair]

    # Trading hours: 8am to 5pm UTC (9 hours = 32400 seconds)
    start_offset_ms = 8 * 3600 * 1000  # 8am
    end_offset_ms = 17 * 3600 * 1000   # 5pm

    # Tick every 100ms = 10 ticks per second
    tick_interval_ms = 100
    num_ticks = (end_offset_ms - start_offset_ms) // tick_interval_ms

    # Generate price walk
    mid_prices = generate_price_walk(base_price, num_ticks, volatility=0.00005)

    ticks = []
    for i, mid in enumerate(mid_prices):
        ts = base_ms + start_offset_ms + (i * tick_interval_ms)
        half_spread = spread / 2

        # Add some spread variation
        spread_mult = random.uniform(0.8, 1.5)
        actual_half_spread = half_spread * spread_mult

        ticks.append({
            "timestamp_ms": ts,
            "pair": pair,
            "bid_tob": mid - actual_half_spread,
            "ask_tob": mid + actual_half_spread,
            "bid_qty_tob": random.uniform(1_000_000, 10_000_000),
            "ask_qty_tob": random.uniform(1_000_000, 10_000_000),
        })

    return ticks


def generate_trades(date_str: str) -> list[dict]:
    """Generate trades for a single day across all pairs.

    Creates 15-25 trades per day with varying sizes.

    Side Convention (HOUSE's perspective):
        side = +1: House BUYS base currency (client sells to us)
        side = -1: House SELLS base currency (client buys from us)
    """
    base_ms = date_to_start_ms(date_str)
    start_offset_ms = 8 * 3600 * 1000 + 30 * 60 * 1000  # 8:30am
    end_offset_ms = 16 * 3600 * 1000 + 30 * 60 * 1000   # 4:30pm

    num_trades = random.randint(15, 25)
    trade_times = sorted([
        base_ms + random.randint(start_offset_ms, end_offset_ms)
        for _ in range(num_trades)
    ])

    trades = []
    trade_counter = 0

    for ts in trade_times:
        trade_counter += 1

        # Pick pair (weight toward cross pairs for interesting decrossing)
        pair_weights = [0.35, 0.35, 0.30]  # EURUSD, GBPUSD, EURGBP
        pair = random.choices(PAIRS, weights=pair_weights)[0]

        # Pick size
        qty = random.choice([500_000, 1_000_000])

        # Pick side from HOUSE's perspective (slightly biased to create positions)
        # +1 = house buys, -1 = house sells
        side = random.choice([1, 1, -1, -1, 1])  # Slight house buy bias

        # Get price near mid (with some slippage)
        base_price = BASE_PRICES[pair]
        spread = SPREADS[pair]

        # House trades with a slight edge (sell above mid, buy below mid)
        if side == -1:  # House sells - receive higher price
            price = base_price + spread/2 + random.uniform(0, spread * 0.2)
        else:  # House buys - pay lower price
            price = base_price - spread/2 - random.uniform(0, spread * 0.2)

        trades.append({
            "timestamp_ms": ts,
            "pair": pair,
            "side": side,
            "qty": float(qty),
            "price": price,
            "trade_id": f"T{date_str}_{trade_counter:04d}",
            "order_id": f"O{date_str}_{trade_counter:04d}",
        })

    return trades


def write_market_data():
    """Write market dataset to parquet files."""
    market_dir = DATA_ROOT / "datasets" / DATASET_NAME / "market"

    for pair in PAIRS:
        pair_dir = market_dir / pair
        pair_dir.mkdir(parents=True, exist_ok=True)

        for date_str in DATES:
            print(f"Generating market data: {pair} {date_str}")
            ticks = generate_market_ticks(date_str, pair)

            table = pa.Table.from_pylist(ticks, schema=MARKET_SCHEMA)
            output_path = pair_dir / f"{date_str}.parquet"
            pq.write_table(table, output_path, compression="snappy")

            print(f"  Written {len(ticks):,} ticks to {output_path}")


def write_tradebook():
    """Write tradebook to parquet files."""
    tradebook_dir = DATA_ROOT / "tradebooks" / TRADEBOOK_NAME
    tradebook_dir.mkdir(parents=True, exist_ok=True)

    all_trades = []

    for date_str in DATES:
        print(f"Generating trades: {date_str}")
        trades = generate_trades(date_str)
        all_trades.extend(trades)

        table = pa.Table.from_pylist(trades, schema=TRADE_SCHEMA)
        output_path = tradebook_dir / f"{date_str}.parquet"
        pq.write_table(table, output_path, compression="snappy")

        print(f"  Written {len(trades)} trades to {output_path}")

    # Print summary
    print("\n=== Trade Summary ===")
    pair_counts = {}
    pair_volumes = {}
    for t in all_trades:
        pair = t["pair"]
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        pair_volumes[pair] = pair_volumes.get(pair, 0) + t["qty"]

    for pair in PAIRS:
        count = pair_counts.get(pair, 0)
        volume = pair_volumes.get(pair, 0)
        print(f"  {pair}: {count} trades, {volume/1_000_000:.1f}M volume")


def main():
    """Generate all test data."""
    print(f"Generating test data in {DATA_ROOT}")
    print(f"Dataset: {DATASET_NAME}")
    print(f"Tradebook: {TRADEBOOK_NAME}")
    print(f"Dates: {DATES}")
    print(f"Pairs: {PAIRS}")
    print()

    # Set seed for reproducibility
    random.seed(42)

    write_market_data()
    print()
    write_tradebook()

    print("\n=== Done ===")
    print(f"Market dataset: data/datasets/{DATASET_NAME}/")
    print(f"Tradebook: data/tradebooks/{TRADEBOOK_NAME}/")


if __name__ == "__main__":
    main()
