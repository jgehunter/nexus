"""Generate validation test data for easy manual verification.

Creates:
- Market data: EURUSD, GBPUSD for 5 weekdays (Mon-Fri)
- Soft flow tradebook: Zero-alpha trades
- Aggressive flow tradebook: Alpha-informed trades (clients predict next-minute move)

Usage:
    python scripts/generate_validation_data.py
"""

import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

# Constants
DATA_ROOT = Path(__file__).parent.parent / "data"
DATASET_NAME = "validation_week"
SOFT_FLOW_NAME = "soft_flow"
AGGRESSIVE_FLOW_NAME = "aggressive_flow"

# Date range: Monday 2024-01-08 to Friday 2024-01-12 (5 weekdays)
START_DATE = datetime(2024, 1, 8)
END_DATE = datetime(2024, 1, 12)

# Starting FX rates
BASE_RATES = {
    "EURUSD": 1.1655,
    "GBPUSD": 1.3471,
}

# Spreads (full bid-ask spread in price terms)
BASE_SPREADS = {
    "EURUSD": 0.00001,  # 0.1 pip
    "GBPUSD": 0.00003,  # 0.3 pip
}

# Market hours (7am-5pm London/GMT)
MARKET_OPEN_HOUR = 7
MARKET_CLOSE_HOUR = 17

# Tick intervals (milliseconds)
IN_MARKET_INTERVAL_MS = 100    # Every 100ms during market hours
OUT_MARKET_INTERVAL_MS = 500   # Every 500ms outside market hours

# Spread multiplier for out-of-market hours
OUT_OF_MARKET_SPREAD_MULT = 2.5

# Volatility parameters (Ornstein-Uhlenbeck)
DAILY_VOLATILITY = 0.005  # 0.5% daily volatility (~50 pips)
MEAN_REVERSION_SPEED = 0.1  # How fast price reverts to mean

# Depth rungs (additional spread from TOB for larger sizes)
DEPTH_RUNGS = [
    {"qty": 1_000_000, "spread_add": 0.0},      # 1M at TOB
    {"qty": 5_000_000, "spread_add": 0.00001},  # 5M: +0.1 pip
    {"qty": 10_000_000, "spread_add": 0.00003}, # 10M: +0.3 pip
    {"qty": 25_000_000, "spread_add": 0.00005}, # 25M: +0.5 pip
]

# Trade parameters
TRADE_SIZES = [1_000_000, 5_000_000]  # 1M and 5M only
TRADES_PER_DAY = 15  # ~15 trades per day per tradebook
PAIRS_WITH_CROSSES = ["EURUSD", "GBPUSD", "EURGBP"]

# Random seed for reproducibility
RANDOM_SEED = 42


def is_market_hours(dt: datetime) -> bool:
    """Check if timestamp is during London market hours (7am-5pm GMT)."""
    return MARKET_OPEN_HOUR <= dt.hour < MARKET_CLOSE_HOUR


def generate_market_data_for_day(
    pair: str,
    date: datetime,
    prev_close_mid: float,
    rng: np.random.Generator,
) -> tuple[list[dict], float]:
    """Generate tick data for a single day.

    Uses Ornstein-Uhlenbeck process for realistic mean-reverting price evolution.

    Returns:
        tuple of (list of tick dicts, final mid price)
    """
    base_rate = BASE_RATES[pair]
    base_spread = BASE_SPREADS[pair]

    # Start from previous close or base rate
    mid_price = prev_close_mid if prev_close_mid else base_rate

    ticks = []
    current_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = current_time + timedelta(days=1)

    # Calculate per-tick volatility (annualized to per-tick)
    # Assuming ~250 trading days, ~86400 seconds per day
    # Daily vol = 0.5%, so per-second vol = 0.5% / sqrt(86400) = 0.000017
    per_tick_vol = DAILY_VOLATILITY / np.sqrt(86400 / 0.1)  # Adjust for 100ms ticks

    while current_time < end_time:
        is_market = is_market_hours(current_time)

        # Determine tick interval
        interval_ms = IN_MARKET_INTERVAL_MS if is_market else OUT_MARKET_INTERVAL_MS

        # Ornstein-Uhlenbeck step: mean reversion + random walk
        dt = interval_ms / 1000.0 / 86400.0  # Fraction of day
        mean_reversion = MEAN_REVERSION_SPEED * (base_rate - mid_price) * dt * 86400
        random_shock = rng.normal(0, per_tick_vol * np.sqrt(interval_ms / 100))
        mid_price += mean_reversion + random_shock

        # Calculate spread with time-of-day variation
        spread_mult = 1.0 if is_market else OUT_OF_MARKET_SPREAD_MULT
        # Add small random variation (80%-120% of base)
        spread_variation = rng.uniform(0.8, 1.2)
        spread = base_spread * spread_mult * spread_variation

        half_spread = spread / 2
        bid = mid_price - half_spread
        ask = mid_price + half_spread

        timestamp_ms = int(current_time.timestamp() * 1000)

        # Build depth rungs
        bid_rungs_qty = []
        bid_rungs_price = []
        ask_rungs_qty = []
        ask_rungs_price = []

        for rung in DEPTH_RUNGS:
            rung_qty = rung["qty"]
            rung_spread_add = rung["spread_add"] * spread_mult * spread_variation

            bid_rungs_qty.append(float(rung_qty))
            bid_rungs_price.append(bid - rung_spread_add)
            ask_rungs_qty.append(float(rung_qty))
            ask_rungs_price.append(ask + rung_spread_add)

        tick = {
            "timestamp_ms": timestamp_ms,
            "pair": pair,
            "bid_tob": bid,
            "ask_tob": ask,
            "bid_qty_tob": float(DEPTH_RUNGS[0]["qty"]),
            "ask_qty_tob": float(DEPTH_RUNGS[0]["qty"]),
            "bid_rungs_qty": bid_rungs_qty,
            "bid_rungs_price": bid_rungs_price,
            "ask_rungs_qty": ask_rungs_qty,
            "ask_rungs_price": ask_rungs_price,
        }
        ticks.append(tick)

        current_time += timedelta(milliseconds=interval_ms)

    return ticks, mid_price


def generate_market_data() -> dict[str, dict[str, list[dict]]]:
    """Generate market data for all pairs and days.

    Returns:
        dict[pair][date_str] = list of ticks
    """
    rng = np.random.default_rng(RANDOM_SEED)

    all_data = {}

    for pair in BASE_RATES:
        all_data[pair] = {}
        prev_close = None

        current_date = START_DATE
        while current_date <= END_DATE:
            date_str = current_date.strftime("%Y%m%d")
            print(f"  Generating {pair} {date_str}...")

            ticks, prev_close = generate_market_data_for_day(
                pair, current_date, prev_close, rng
            )
            all_data[pair][date_str] = ticks

            current_date += timedelta(days=1)

    return all_data


def get_mid_price_at_time(
    market_data: dict[str, dict[str, list[dict]]],
    pair: str,
    timestamp_ms: int,
) -> float | None:
    """Get mid price for a pair at a specific timestamp."""
    date_str = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y%m%d")

    if pair not in market_data or date_str not in market_data[pair]:
        return None

    ticks = market_data[pair][date_str]

    # Binary search for closest tick <= timestamp
    left, right = 0, len(ticks) - 1
    best_tick = None

    while left <= right:
        mid = (left + right) // 2
        if ticks[mid]["timestamp_ms"] <= timestamp_ms:
            best_tick = ticks[mid]
            left = mid + 1
        else:
            right = mid - 1

    if best_tick is None:
        return None

    return (best_tick["bid_tob"] + best_tick["ask_tob"]) / 2


def get_price_change_next_minute(
    market_data: dict[str, dict[str, list[dict]]],
    pair: str,
    timestamp_ms: int,
) -> float:
    """Get price change over the next minute.

    Returns:
        Price change (positive = price went up, negative = price went down)
    """
    current_mid = get_mid_price_at_time(market_data, pair, timestamp_ms)
    future_mid = get_mid_price_at_time(market_data, pair, timestamp_ms + 60000)  # +1 min

    if current_mid is None or future_mid is None:
        return 0.0

    return future_mid - current_mid


def generate_trade_timestamps(
    date: datetime,
    count: int,
    rng: np.random.Generator,
) -> list[int]:
    """Generate random trade timestamps during market hours."""
    timestamps = []

    # Market hours: 7am-5pm (10 hours)
    market_open = date.replace(hour=MARKET_OPEN_HOUR, minute=30, second=0)
    market_close = date.replace(hour=MARKET_CLOSE_HOUR - 1, minute=30, second=0)

    open_ms = int(market_open.timestamp() * 1000)
    close_ms = int(market_close.timestamp() * 1000)

    for _ in range(count):
        ts = rng.integers(open_ms, close_ms)
        timestamps.append(ts)

    return sorted(timestamps)


def generate_soft_flow(
    market_data: dict[str, dict[str, list[dict]]],
) -> list[dict]:
    """Generate soft flow tradebook (zero alpha).

    Trades have:
    - Random 50/50 direction
    - Execution at mid with 0-1 pip house edge
    - No correlation with future price moves

    Side Convention (HOUSE's perspective):
    - side = +1: House BUYS base currency (client sells to us)
    - side = -1: House SELLS base currency (client buys from us)
    """
    rng = np.random.default_rng(RANDOM_SEED + 1)

    trades = []
    trade_id = 1

    current_date = START_DATE
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y%m%d")
        print(f"  Generating soft_flow trades for {date_str}...")

        # Generate timestamps for this day
        timestamps = generate_trade_timestamps(current_date, TRADES_PER_DAY, rng)

        for ts in timestamps:
            # Random pair (including cross)
            pair = rng.choice(PAIRS_WITH_CROSSES)

            # Random direction (50/50) - HOUSE's perspective
            # +1 = house buys, -1 = house sells
            side = rng.choice([1, -1])

            # Random size
            qty = float(rng.choice(TRADE_SIZES))

            # Get market price
            if pair == "EURGBP":
                # Cross pair - derive from EURUSD/GBPUSD
                eur_mid = get_mid_price_at_time(market_data, "EURUSD", ts)
                gbp_mid = get_mid_price_at_time(market_data, "GBPUSD", ts)
                if eur_mid and gbp_mid:
                    mid = eur_mid / gbp_mid
                else:
                    mid = 0.8652  # Fallback
            else:
                mid = get_mid_price_at_time(market_data, pair, ts)
                if mid is None:
                    mid = BASE_RATES[pair]

            # Execution price with house edge based on spread
            # House earns 0 to half-spread on each trade (realistic)
            # Get the spread for this pair (for cross pairs, use average of components)
            if pair == "EURGBP":
                pair_spread = (BASE_SPREADS["EURUSD"] + BASE_SPREADS["GBPUSD"]) / 2
            else:
                pair_spread = BASE_SPREADS.get(pair, 0.00002)

            half_spread = pair_spread / 2
            house_edge = rng.uniform(0, 1) * half_spread  # 0 to half-spread

            if side == -1:  # House sells - we receive higher price
                price = mid + house_edge
            else:  # House buys - we pay lower price
                price = mid - house_edge

            trade = {
                "timestamp_ms": ts,
                "pair": pair,
                "side": side,
                "qty": qty,
                "price": price,
                "trade_id": f"SOFT_{trade_id:06d}",
            }
            trades.append(trade)
            trade_id += 1

        current_date += timedelta(days=1)

    return trades


def generate_aggressive_flow(
    market_data: dict[str, dict[str, list[dict]]],
) -> list[dict]:
    """Generate aggressive flow tradebook (client alpha).

    Trades have:
    - Direction predicts next-minute price move
    - Clients have alpha: they buy before price goes up, sell before price goes down
    - House always ends up on the wrong side (loses on inventory)

    Side Convention (HOUSE's perspective):
    - side = +1: House BUYS base currency (client sells to us, before price drops)
    - side = -1: House SELLS base currency (client buys from us, before price rises)
    """
    rng = np.random.default_rng(RANDOM_SEED + 2)

    trades = []
    trade_id = 1

    current_date = START_DATE
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y%m%d")
        print(f"  Generating aggressive_flow trades for {date_str}...")

        # Generate timestamps for this day
        timestamps = generate_trade_timestamps(current_date, TRADES_PER_DAY, rng)

        for ts in timestamps:
            # Random pair (prefer direct pairs for clearer alpha signal)
            # 60% direct pairs, 40% cross
            if rng.random() < 0.6:
                pair = rng.choice(["EURUSD", "GBPUSD"])
            else:
                pair = "EURGBP"

            # Get price change in next minute
            if pair == "EURGBP":
                # For cross, use EURUSD as reference
                price_change = get_price_change_next_minute(market_data, "EURUSD", ts)
                eur_mid = get_mid_price_at_time(market_data, "EURUSD", ts)
                gbp_mid = get_mid_price_at_time(market_data, "GBPUSD", ts)
                mid = (eur_mid / gbp_mid) if (eur_mid and gbp_mid) else 0.8652
            else:
                price_change = get_price_change_next_minute(market_data, pair, ts)
                mid = get_mid_price_at_time(market_data, pair, ts)
                if mid is None:
                    mid = BASE_RATES[pair]

            # Alpha: clients trade in direction of future move (HOUSE's perspective)
            # Price goes up → client buys → house SELLS (side=-1, loses on inventory)
            # Price goes down → client sells → house BUYS (side=+1, loses on inventory)
            if price_change > 0:
                side = -1  # House sells (client buys before price rise)
            elif price_change < 0:
                side = 1  # House buys (client sells before price drop)
            else:
                side = rng.choice([1, -1])  # Random if no change

            # Random size
            qty = float(rng.choice(TRADE_SIZES))

            # Execution price with house edge based on spread
            # House earns 0 to half-spread on each trade (realistic)
            if pair == "EURGBP":
                pair_spread = (BASE_SPREADS["EURUSD"] + BASE_SPREADS["GBPUSD"]) / 2
            else:
                pair_spread = BASE_SPREADS.get(pair, 0.00002)

            half_spread = pair_spread / 2
            house_edge = rng.uniform(0, 1) * half_spread  # 0 to half-spread

            if side == -1:  # House sells - we receive higher price
                price = mid + house_edge
            else:  # House buys - we pay lower price
                price = mid - house_edge

            trade = {
                "timestamp_ms": ts,
                "pair": pair,
                "side": side,
                "qty": qty,
                "price": price,
                "trade_id": f"AGGR_{trade_id:06d}",
            }
            trades.append(trade)
            trade_id += 1

        current_date += timedelta(days=1)

    return trades


def write_market_data(market_data: dict[str, dict[str, list[dict]]]) -> None:
    """Write market data to parquet files."""
    dataset_dir = DATA_ROOT / "datasets" / DATASET_NAME / "market"

    for pair, dates in market_data.items():
        pair_dir = dataset_dir / pair
        pair_dir.mkdir(parents=True, exist_ok=True)

        for date_str, ticks in dates.items():
            # Convert to arrow table
            table = pa.Table.from_pylist(ticks)

            output_file = pair_dir / f"{date_str}.parquet"
            pq.write_table(table, output_file, compression="snappy")
            print(f"  Written {output_file} ({len(ticks):,} ticks)")


def write_tradebook(trades: list[dict], book_name: str) -> None:
    """Write tradebook to parquet files, partitioned by date."""
    tradebook_dir = DATA_ROOT / "tradebooks" / book_name
    tradebook_dir.mkdir(parents=True, exist_ok=True)

    # Group trades by date
    trades_by_date = defaultdict(list)
    for trade in trades:
        date_str = datetime.fromtimestamp(trade["timestamp_ms"] / 1000).strftime("%Y%m%d")
        trades_by_date[date_str].append(trade)

    for date_str, date_trades in trades_by_date.items():
        table = pa.Table.from_pylist(date_trades)

        output_file = tradebook_dir / f"{date_str}.parquet"
        pq.write_table(table, output_file, compression="snappy")
        print(f"  Written {output_file} ({len(date_trades)} trades)")


def main():
    """Main entry point."""
    print("=" * 60)
    print("Generating Validation Test Data")
    print("=" * 60)

    # Set random seed
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    # Generate market data
    print("\n1. Generating market data...")
    market_data = generate_market_data()

    print("\n2. Writing market data...")
    write_market_data(market_data)

    # Generate soft flow
    print("\n3. Generating soft_flow tradebook...")
    soft_trades = generate_soft_flow(market_data)
    write_tradebook(soft_trades, SOFT_FLOW_NAME)

    # Generate aggressive flow
    print("\n4. Generating aggressive_flow tradebook...")
    aggressive_trades = generate_aggressive_flow(market_data)
    write_tradebook(aggressive_trades, AGGRESSIVE_FLOW_NAME)

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Dataset: {DATASET_NAME}")
    print(f"  Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"  Pairs: {list(BASE_RATES.keys())}")

    total_ticks = sum(
        len(ticks)
        for dates in market_data.values()
        for ticks in dates.values()
    )
    print(f"  Total ticks: {total_ticks:,}")

    print(f"\nTradebook: {SOFT_FLOW_NAME}")
    print(f"  Trades: {len(soft_trades)}")
    print(f"  Characteristics: Zero alpha, random direction")

    print(f"\nTradebook: {AGGRESSIVE_FLOW_NAME}")
    print(f"  Trades: {len(aggressive_trades)}")
    print(f"  Characteristics: Client alpha (predicts 1-min move)")

    print("\nDone!")


if __name__ == "__main__":
    main()
