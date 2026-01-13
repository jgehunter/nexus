"""Generate comprehensive test market dataset and tradebook for backtesting.

Creates 5 days of market data for 26 direct pairs plus 3 cross pairs (for decrossing),
with realistic tick frequencies, trade volumes, and price distributions.

Direct pairs (26): EURUSD, EURCHF, EURCZK, EURDKK, EURHUF, EURNOK, EURPLN, EURRON, EURSEK,
                   USDJPY, GBPUSD, USDCAD, AUDUSD, NZDUSD, USDAED, USDCNH, USDHKD,
                   USDILS, USDMXN, USDQAR, USDSAR, USDSGD, USDTHB, USDTRY, USDZAR, USDCLP

Cross pairs (3): EURGBP, GBPCHF, GBPJPY (for multi-leg decomposition/decrossing tests)
"""

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

# =============================================================================
# Configuration
# =============================================================================

DATA_ROOT = Path(__file__).parent.parent / "data"
DATASET_NAME = "comprehensive_market"
TRADEBOOK_NAME = "comprehensive_trades"

# Date range (5 days)
DATES = ["20250601", "20250602", "20250603", "20250604", "20250605"]

# Direct pairs (26 total) - these have corresponding market data
DIRECT_PAIRS = [
    "EURUSD", "EURCHF", "EURCZK", "EURDKK", "EURHUF", "EURNOK", "EURPLN", "EURRON", "EURSEK",
    "USDJPY", "GBPUSD", "USDCAD", "AUDUSD", "NZDUSD", "USDAED", "USDCNH", "USDHKD",
    "USDILS", "USDMXN", "USDQAR", "USDSAR", "USDSGD", "USDTHB", "USDTRY", "USDZAR", "USDCLP",
]

# Cross pairs for decrossing tests (require multi-leg decomposition)
CROSS_PAIRS = ["EURGBP", "GBPCHF", "GBPJPY"]

# All pairs for tradebook
ALL_PAIRS = DIRECT_PAIRS + CROSS_PAIRS

# All pairs requiring market data (direct pairs only - crosses derive from these)
MARKET_PAIRS = DIRECT_PAIRS

# Realistic base prices (approximate current market levels)
BASE_PRICES: dict[str, float] = {
    # EUR crosses
    "EURUSD": 1.0850, "EURCHF": 0.9650, "EURCZK": 25.20, "EURDKK": 7.46,
    "EURHUF": 395.0, "EURNOK": 11.75, "EURPLN": 4.32, "EURRON": 4.98, "EURSEK": 11.50,
    # Cross pairs (for trade pricing)
    "EURGBP": 0.8580, "GBPCHF": 1.1250, "GBPJPY": 196.50,
    # USD pairs
    "USDJPY": 155.50, "GBPUSD": 1.2650, "USDCAD": 1.3650, "AUDUSD": 0.6550,
    "NZDUSD": 0.6050, "USDAED": 3.6725, "USDCNH": 7.2500, "USDHKD": 7.7850,
    "USDILS": 3.65, "USDMXN": 17.25, "USDQAR": 3.64, "USDSAR": 3.75,
    "USDSGD": 1.3450, "USDTHB": 35.50, "USDTRY": 32.50, "USDZAR": 18.25, "USDCLP": 950.0,
}

# Typical spreads (appropriate pip values for each pair)
SPREADS: dict[str, float] = {
    # Major pairs - tight spreads
    "EURUSD": 0.00008, "GBPUSD": 0.00010, "USDJPY": 0.010, "USDCAD": 0.00015,
    "AUDUSD": 0.00012, "NZDUSD": 0.00015, "EURCHF": 0.00015,
    # EUR crosses - moderate
    "EURGBP": 0.00012, "EURDKK": 0.0003, "EURSEK": 0.0005, "EURNOK": 0.0005, "EURPLN": 0.003,
    # GBP crosses
    "GBPCHF": 0.00020, "GBPJPY": 0.025,
    # EM pairs - wider spreads
    "EURCZK": 0.02, "EURHUF": 0.25, "EURRON": 0.003,
    "USDMXN": 0.005, "USDCNH": 0.002, "USDTRY": 0.015, "USDZAR": 0.01,
    # Pegged/stable pairs - very tight
    "USDAED": 0.0002, "USDHKD": 0.0002, "USDQAR": 0.0002, "USDSAR": 0.0002,
    # Other
    "USDILS": 0.002, "USDSGD": 0.0004, "USDTHB": 0.02, "USDCLP": 1.0,
}

# Volatility per tick (daily vol ~1% for most pairs, scaled to tick level)
VOLATILITIES: dict[str, float] = {
    # Major pairs - lower vol
    "EURUSD": 0.00003, "GBPUSD": 0.00004, "USDJPY": 0.00004, "USDCAD": 0.00003,
    "AUDUSD": 0.00004, "NZDUSD": 0.00005, "EURCHF": 0.00003,
    # EUR crosses
    "EURGBP": 0.00003, "EURDKK": 0.00001, "EURSEK": 0.00005, "EURNOK": 0.00005, "EURPLN": 0.00008,
    # GBP crosses
    "GBPCHF": 0.00005, "GBPJPY": 0.00006,
    # EM pairs - higher vol
    "EURCZK": 0.00006, "EURHUF": 0.00010, "EURRON": 0.00004,
    "USDMXN": 0.00010, "USDCNH": 0.00003, "USDTRY": 0.00015, "USDZAR": 0.00010,
    # Pegged pairs - minimal vol
    "USDAED": 0.000005, "USDHKD": 0.00001, "USDQAR": 0.000005, "USDSAR": 0.000005,
    # Other
    "USDILS": 0.00005, "USDSGD": 0.00003, "USDTHB": 0.00004, "USDCLP": 0.00008,
}

# Pair categories for tick frequency
HIGH_VOLUME_PAIRS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"}
MEDIUM_VOLUME_PAIRS = {"EURGBP", "EURCHF", "USDCNH", "USDMXN", "USDZAR", "USDTRY", "GBPCHF", "GBPJPY"}
# All other pairs are low volume

# Tick intervals by category (ms)
TICK_INTERVALS_MS = {
    "high_volume": 500,     # ~172K ticks/day
    "medium_volume": 2000,  # ~43K ticks/day
    "low_volume": 5000,     # ~17K ticks/day
}

# Trades per day by pair (total volume targets spread across 5 days)
TRADES_PER_DAY: dict[str, int] = {
    "EURUSD": 700,   # 3500 total / 5 days
    "GBPUSD": 240,   # 1200 total / 5 days
    "EURGBP": 120,   # 600 total / 5 days (cross)
    "GBPCHF": 40,    # 200 total (cross)
    "GBPJPY": 40,    # 200 total (cross)
    "EURPLN": 30,    # 150 total / 5 days
    "USDCNH": 20,    # 100 total / 5 days
    "USDMXN": 60,    # 300 total / 5 days
    # Default for other pairs: 5-20 trades per day (anecdotal)
}

# Volume targets (total in millions of base currency across all 5 days)
VOLUME_TARGETS_M: dict[str, float] = {
    "EURUSD": 10000,  # 10B total
    "GBPUSD": 160,
    "EURGBP": 30,     # cross
    "GBPCHF": 15,     # cross
    "GBPJPY": 15,     # cross
    "EURPLN": 15,
    "USDCNH": 30,
    "USDMXN": 20,
}

# PyArrow schemas
MARKET_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("pair", pa.string()),
    ("bid_tob", pa.float64()),
    ("ask_tob", pa.float64()),
    ("bid_qty_tob", pa.float64()),
    ("ask_qty_tob", pa.float64()),
])

TRADE_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("pair", pa.string()),
    ("side", pa.int8()),
    ("qty", pa.float64()),
    ("price", pa.float64()),
    ("trade_id", pa.string()),
    ("order_id", pa.string()),
])


# =============================================================================
# Helper Functions
# =============================================================================

def date_to_start_ms(date_str: str) -> int:
    """Convert YYYYMMDD to start-of-day milliseconds (UTC)."""
    dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def get_tick_interval(pair: str) -> int:
    """Get tick interval in ms based on pair category."""
    if pair in HIGH_VOLUME_PAIRS:
        return TICK_INTERVALS_MS["high_volume"]
    elif pair in MEDIUM_VOLUME_PAIRS:
        return TICK_INTERVALS_MS["medium_volume"]
    else:
        return TICK_INTERVALS_MS["low_volume"]


def get_trades_per_day(pair: str) -> int:
    """Get number of trades per day for a pair."""
    return TRADES_PER_DAY.get(pair, random.randint(5, 20))


def get_avg_trade_size(pair: str, trades_per_day: int) -> float:
    """Calculate average trade size to meet volume targets."""
    if pair in VOLUME_TARGETS_M:
        total_volume = VOLUME_TARGETS_M[pair] * 1_000_000
        total_trades = trades_per_day * len(DATES)
        return total_volume / total_trades
    else:
        # Anecdotal pairs: 100K-500K avg size
        return random.uniform(100_000, 500_000)


def generate_price_walk(
    base_price: float, num_ticks: int, volatility: float, mean_reversion: float = 0.001
) -> list[float]:
    """Generate mean-reverting random walk prices."""
    prices = [base_price]

    for _ in range(num_ticks - 1):
        # Random shock
        change = random.gauss(0, volatility)
        # Mean reversion component
        reversion = mean_reversion * (base_price - prices[-1])
        new_price = prices[-1] * (1 + change) + reversion
        prices.append(new_price)

    return prices


def get_trade_price(mid: float, spread: float, side: int) -> float:
    """Generate trade price with realistic spread distribution.

    Side Convention (HOUSE's perspective):
        side = +1: House BUYS base currency
        side = -1: House SELLS base currency

    Distribution:
    - 80%: Favorable to house (we earn spread)
    - 15%: At mid (neutral)
    - 5%: Unfavorable (we got worse price)
    """
    rand = random.random()

    if rand < 0.80:  # Favorable - we earn spread
        markup = random.uniform(0.3, 0.8) * spread / 2
        if side == -1:  # House sells - receives above mid
            return mid + markup
        else:  # House buys - pays below mid
            return mid - markup
    elif rand < 0.95:  # At mid
        return mid + random.uniform(-0.1, 0.1) * spread / 2
    else:  # Unfavorable - we got worse price
        markup = random.uniform(0.1, 0.5) * spread / 2
        if side == -1:  # House sells below mid (bad)
            return mid - markup
        else:  # House buys above mid (bad)
            return mid + markup


# =============================================================================
# Market Data Generation
# =============================================================================

def generate_market_ticks(date_str: str, pair: str) -> list[dict[str, Any]]:
    """Generate 24h of market ticks for a single day and pair."""
    base_ms = date_to_start_ms(date_str)
    base_price = BASE_PRICES.get(pair, 1.0)
    spread = SPREADS.get(pair, 0.0001)
    volatility = VOLATILITIES.get(pair, 0.00005)
    tick_interval = get_tick_interval(pair)

    # 24 hours = 86400 seconds
    day_ms = 24 * 3600 * 1000
    num_ticks = day_ms // tick_interval

    # Generate price walk
    mid_prices = generate_price_walk(base_price, num_ticks, volatility)

    ticks = []
    for i, mid in enumerate(mid_prices):
        ts = base_ms + (i * tick_interval)
        half_spread = spread / 2

        # Add some spread variation (80% to 150% of base spread)
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


# Global cache for market data mid prices (for trade pricing)
MARKET_CACHE: dict[str, dict[str, list[tuple[int, float]]]] = {}


def build_market_cache(date_str: str, pair: str, ticks: list[dict[str, Any]]) -> None:
    """Cache mid prices for quick lookup during trade generation."""
    if date_str not in MARKET_CACHE:
        MARKET_CACHE[date_str] = {}

    # Store (timestamp_ms, mid) tuples sorted by timestamp
    mids = [(t["timestamp_ms"], (t["bid_tob"] + t["ask_tob"]) / 2) for t in ticks]
    MARKET_CACHE[date_str][pair] = mids


def lookup_market_mid(date_str: str, pair: str, timestamp_ms: int) -> float:
    """Look up prevailing mid price at a given timestamp."""
    if date_str not in MARKET_CACHE or pair not in MARKET_CACHE[date_str]:
        # Fallback to base price if cache not available
        return BASE_PRICES.get(pair, 1.0)

    mids = MARKET_CACHE[date_str][pair]

    # Binary search for the latest tick <= timestamp
    lo, hi = 0, len(mids) - 1
    result_mid = mids[0][1]  # Default to first tick

    while lo <= hi:
        mid_idx = (lo + hi) // 2
        if mids[mid_idx][0] <= timestamp_ms:
            result_mid = mids[mid_idx][1]
            lo = mid_idx + 1
        else:
            hi = mid_idx - 1

    return result_mid


def lookup_cross_mid(date_str: str, pair: str, timestamp_ms: int) -> float:
    """Look up mid price for cross pairs by computing from constituent direct pairs."""
    # For cross pairs, compute from direct pairs
    if pair == "EURGBP":
        # EURGBP = EURUSD / GBPUSD
        eurusd = lookup_market_mid(date_str, "EURUSD", timestamp_ms)
        gbpusd = lookup_market_mid(date_str, "GBPUSD", timestamp_ms)
        return eurusd / gbpusd
    elif pair == "GBPCHF":
        # GBPCHF = GBPUSD * (EURCHF / EURUSD)  -- approximate via USDCHF
        # Actually, simpler: GBPCHF = GBPUSD / USDCHF, but we have EURCHF
        # Let's use: GBPCHF = GBPUSD * EURCHF / EURUSD
        gbpusd = lookup_market_mid(date_str, "GBPUSD", timestamp_ms)
        eurchf = lookup_market_mid(date_str, "EURCHF", timestamp_ms)
        eurusd = lookup_market_mid(date_str, "EURUSD", timestamp_ms)
        return gbpusd * eurchf / eurusd
    elif pair == "GBPJPY":
        # GBPJPY = GBPUSD * USDJPY
        gbpusd = lookup_market_mid(date_str, "GBPUSD", timestamp_ms)
        usdjpy = lookup_market_mid(date_str, "USDJPY", timestamp_ms)
        return gbpusd * usdjpy
    else:
        # Direct pair
        return lookup_market_mid(date_str, pair, timestamp_ms)


# =============================================================================
# Trade Generation
# =============================================================================

def generate_trades_for_date(date_str: str) -> list[dict[str, Any]]:
    """Generate trades for a single day across all pairs.

    Side Convention (HOUSE's perspective):
        side = +1: House BUYS base currency (client sells to us)
        side = -1: House SELLS base currency (client buys from us)
    """
    base_ms = date_to_start_ms(date_str)
    day_ms = 24 * 3600 * 1000

    trades = []
    trade_counter = 0

    for pair in ALL_PAIRS:
        trades_per_day = get_trades_per_day(pair)
        avg_size = get_avg_trade_size(pair, trades_per_day)
        spread = SPREADS.get(pair, 0.0001)

        # Generate trade times spread throughout the day
        trade_times = sorted([
            base_ms + random.randint(0, day_ms - 1)
            for _ in range(trades_per_day)
        ])

        for ts in trade_times:
            trade_counter += 1

            # Random side from HOUSE's perspective (55% house buys)
            # +1 = house buys, -1 = house sells
            side = 1 if random.random() < 0.55 else -1

            # Randomize size around average (50% to 200% of avg)
            qty = avg_size * random.uniform(0.5, 2.0)

            # Look up prevailing mid price
            if pair in CROSS_PAIRS:
                mid = lookup_cross_mid(date_str, pair, ts)
            else:
                mid = lookup_market_mid(date_str, pair, ts)

            # Get trade price with spread distribution
            price = get_trade_price(mid, spread, side)

            trades.append({
                "timestamp_ms": ts,
                "pair": pair,
                "side": side,
                "qty": qty,
                "price": price,
                "trade_id": f"T{date_str}_{trade_counter:05d}",
                "order_id": f"O{date_str}_{trade_counter:05d}",
            })

    # Sort all trades by timestamp
    trades.sort(key=lambda t: t["timestamp_ms"])
    return trades


# =============================================================================
# File Writers
# =============================================================================

def write_market_data() -> None:
    """Write market dataset to parquet files."""
    market_dir = DATA_ROOT / "datasets" / DATASET_NAME / "market"

    total_ticks = 0

    for pair in MARKET_PAIRS:
        pair_dir = market_dir / pair
        pair_dir.mkdir(parents=True, exist_ok=True)

        for date_str in DATES:
            print(f"  {pair}/{date_str}...", end=" ", flush=True)
            ticks = generate_market_ticks(date_str, pair)

            # Cache for trade pricing
            build_market_cache(date_str, pair, ticks)

            table = pa.Table.from_pylist(ticks, schema=MARKET_SCHEMA)
            output_path = pair_dir / f"{date_str}.parquet"
            pq.write_table(table, output_path, compression="snappy")

            print(f"{len(ticks):,} ticks")
            total_ticks += len(ticks)

    print(f"\nTotal market ticks: {total_ticks:,}")


def write_tradebook() -> None:
    """Write tradebook to parquet files."""
    tradebook_dir = DATA_ROOT / "tradebooks" / TRADEBOOK_NAME
    tradebook_dir.mkdir(parents=True, exist_ok=True)

    all_trades: list[dict[str, Any]] = []

    for date_str in DATES:
        print(f"  {date_str}...", end=" ", flush=True)
        trades = generate_trades_for_date(date_str)
        all_trades.extend(trades)

        table = pa.Table.from_pylist(trades, schema=TRADE_SCHEMA)
        output_path = tradebook_dir / f"{date_str}.parquet"
        pq.write_table(table, output_path, compression="snappy")

        print(f"{len(trades):,} trades")

    # Print summary
    print(f"\nTotal trades: {len(all_trades):,}")
    print("\n=== Trade Summary by Pair ===")

    pair_counts: dict[str, int] = {}
    pair_volumes: dict[str, float] = {}
    for t in all_trades:
        pair = t["pair"]
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        pair_volumes[pair] = pair_volumes.get(pair, 0) + t["qty"]

    # Sort by volume
    sorted_pairs = sorted(pair_volumes.keys(), key=lambda p: pair_volumes[p], reverse=True)

    for pair in sorted_pairs:
        count = pair_counts.get(pair, 0)
        volume = pair_volumes.get(pair, 0)
        volume_m = volume / 1_000_000
        is_cross = "(cross)" if pair in CROSS_PAIRS else ""
        print(f"  {pair}: {count:,} trades, {volume_m:,.1f}M volume {is_cross}")


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    """Generate comprehensive test data."""
    print("=" * 60)
    print("Comprehensive Test Data Generator")
    print("=" * 60)
    print(f"Output directory: {DATA_ROOT}")
    print(f"Market dataset: {DATASET_NAME}")
    print(f"Tradebook: {TRADEBOOK_NAME}")
    print(f"Dates: {DATES[0]} to {DATES[-1]} ({len(DATES)} days)")
    print(f"Direct pairs: {len(DIRECT_PAIRS)}")
    print(f"Cross pairs: {len(CROSS_PAIRS)} ({', '.join(CROSS_PAIRS)})")
    print()

    # Set seed for reproducibility
    random.seed(42)

    print("Generating market data...")
    write_market_data()
    print()

    print("Generating tradebook...")
    write_tradebook()

    print()
    print("=" * 60)
    print("Done!")
    print("=" * 60)
    print(f"Market dataset: data/datasets/{DATASET_NAME}/")
    print(f"Tradebook: data/tradebooks/{TRADEBOOK_NAME}/")


if __name__ == "__main__":
    main()
