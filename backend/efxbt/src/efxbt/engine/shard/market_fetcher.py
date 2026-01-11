"""Market snapshot fetching with batch ASOF joins.

Fetches market data and FX conversion rates for all timeline points in a single
DuckDB query, avoiding per-event database round-trips.
"""

from pathlib import Path

import pyarrow as pa
from pydantic import BaseModel

from ...core.config.run_config import SimulationConfig
from ...core.data.duck import get_connection, register_parquet_files
from ...core.data.registry import MarketDatasetRegistry
from .fx_converter import FXConverter
from .timeline import TimelinePoint


class MarketSnapshot(BaseModel):
    """Market snapshot at a single timeline point.

    Includes both market data for the traded pair and FX rates for PnL conversion.

    Attributes:
        timestamp_ms: Snapshot timestamp
        pair: Currency pair
        mid: Mid price (bid + ask) / 2
        bid: Best bid price
        ask: Best ask price
        spread: Ask - bid
        fx_rate: FX rate for converting PnL to reporting currency (1.0 if no conversion needed)
    """

    timestamp_ms: int
    pair: str
    mid: float
    bid: float
    ask: float
    spread: float
    fx_rate: float  # For PnL conversion to reporting currency


class MarketSnapshotFetcher:
    """Fetch market snapshots via batch ASOF joins.

    Fetches all market data in a SINGLE DuckDB query for maximum performance,
    including both market prices and FX conversion rates.
    """

    def __init__(
        self,
        pair: str,
        data_root: Path,
        config: SimulationConfig,
    ):
        """Initialize market fetcher.

        Args:
            pair: Currency pair to fetch market data for
            data_root: Root data directory
            config: Simulation configuration (includes dataset name and reporting currency)
        """
        self.pair = pair
        self.data_root = Path(data_root)
        self.config = config

        # Initialize registry
        self.market_registry = MarketDatasetRegistry(self.data_root)

        # Initialize FX converter
        self.fx_converter = FXConverter(config.reporting_currency)

    def fetch_snapshots(
        self,
        timeline: list[TimelinePoint],
    ) -> dict[int, MarketSnapshot]:
        """Fetch ALL market snapshots in a SINGLE DuckDB query.

        No per-event queries - everything batched upfront for performance.

        Args:
            timeline: List of timeline points

        Returns:
            Dict mapping timestamp_ms to MarketSnapshot

        Raises:
            ValueError: If market data not found for any timestamp
        """
        if not timeline:
            return {}

        # Get unique timestamps
        timestamps_ms = sorted(set(p.timestamp_ms for p in timeline))

        # Discover market dataset
        inventory = self.market_registry.discover_dataset(self.config.dataset)

        # Get market data files for this pair
        pair_files = [
            Path(pd.file_path)
            for pd in inventory.pair_dates
            if pd.pair == self.pair
        ]

        if not pair_files:
            raise ValueError(
                f"No market data found for pair {self.pair} in dataset {self.config.dataset}"
            )

        # Determine if we need FX conversion
        needs_conversion = self.fx_converter.needs_conversion(self.pair)
        conversion_pair = None
        conversion_files = []

        if needs_conversion:
            conversion_info = self.fx_converter.get_conversion_pair(self.pair)
            if conversion_info:
                conversion_pair, _ = conversion_info

                # Get conversion pair files
                conversion_files = [
                    Path(pd.file_path)
                    for pd in inventory.pair_dates
                    if pd.pair == conversion_pair
                ]

                if not conversion_files:
                    raise ValueError(
                        f"No market data found for conversion pair {conversion_pair} "
                        f"in dataset {self.config.dataset}"
                    )

        # Execute batch ASOF join
        with get_connection(":memory:") as conn:
            # Register market data
            register_parquet_files(conn, "market", pair_files)

            if needs_conversion and conversion_files:
                register_parquet_files(conn, "fx_market", conversion_files)

            # Create timeline temp table
            timeline_table = pa.table({
                "timestamp_ms": pa.array(timestamps_ms, type=pa.int64())
            })
            conn.register("timeline", timeline_table)

            # Build query based on whether conversion is needed
            if needs_conversion:
                query = f"""
                WITH ranked_ticks AS (
                    SELECT
                        t.timestamp_ms,
                        m.bid_tob,
                        m.ask_tob,
                        (m.bid_tob + m.ask_tob) / 2.0 AS mid,
                        m.ask_tob - m.bid_tob AS spread,
                        ROW_NUMBER() OVER (
                            PARTITION BY t.timestamp_ms
                            ORDER BY m.timestamp_ms DESC
                        ) AS rn
                    FROM timeline t
                    LEFT JOIN market m
                        ON m.timestamp_ms <= t.timestamp_ms
                        AND m.pair = '{self.pair}'
                ),
                ranked_fx AS (
                    SELECT
                        t.timestamp_ms,
                        (fx.bid_tob + fx.ask_tob) / 2.0 AS fx_mid,
                        ROW_NUMBER() OVER (
                            PARTITION BY t.timestamp_ms
                            ORDER BY fx.timestamp_ms DESC
                        ) AS rn
                    FROM timeline t
                    LEFT JOIN fx_market fx
                        ON fx.timestamp_ms <= t.timestamp_ms
                        AND fx.pair = '{conversion_pair}'
                )
                SELECT
                    rt.timestamp_ms,
                    rt.bid_tob,
                    rt.ask_tob,
                    rt.mid,
                    rt.spread,
                    COALESCE(fx.fx_mid, 1.0) AS fx_rate
                FROM ranked_ticks rt
                LEFT JOIN ranked_fx fx
                    ON rt.timestamp_ms = fx.timestamp_ms
                    AND fx.rn = 1
                WHERE rt.rn = 1
                ORDER BY rt.timestamp_ms
                """
            else:
                # No conversion needed
                query = f"""
                WITH ranked_ticks AS (
                    SELECT
                        t.timestamp_ms,
                        m.bid_tob,
                        m.ask_tob,
                        (m.bid_tob + m.ask_tob) / 2.0 AS mid,
                        m.ask_tob - m.bid_tob AS spread,
                        ROW_NUMBER() OVER (
                            PARTITION BY t.timestamp_ms
                            ORDER BY m.timestamp_ms DESC
                        ) AS rn
                    FROM timeline t
                    LEFT JOIN market m
                        ON m.timestamp_ms <= t.timestamp_ms
                        AND m.pair = '{self.pair}'
                )
                SELECT
                    timestamp_ms,
                    bid_tob,
                    ask_tob,
                    mid,
                    spread,
                    1.0 AS fx_rate
                FROM ranked_ticks
                WHERE rn = 1
                ORDER BY timestamp_ms
                """

            result = conn.execute(query).fetchall()

            # Build snapshot dict
            snapshots = {}
            for row in result:
                ts_ms, bid, ask, mid, spread, fx_rate = row

                if bid is None:
                    raise ValueError(
                        f"No market tick found for {self.pair} at or before "
                        f"timestamp {ts_ms}. Market data gap detected."
                    )

                snapshots[ts_ms] = MarketSnapshot(
                    timestamp_ms=ts_ms,
                    pair=self.pair,
                    mid=mid,
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    fx_rate=fx_rate if fx_rate is not None else 1.0,
                )

            return snapshots
