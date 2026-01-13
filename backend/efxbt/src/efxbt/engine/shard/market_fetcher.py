"""Market snapshot fetching with batch ASOF joins.

Fetches market data and FX conversion rates for all timeline points in a single
DuckDB query using native ASOF JOIN for maximum performance.

Supports both direct FX conversion (single pair) and triangulated multi-hop
conversion when the direct pair isn't available in the market dataset.

Performance optimizations:
1. Connection reuse via MarketDataCache (single connection per process)
2. Native DuckDB ASOF JOIN instead of window functions (10-100x faster)
3. Market data tables cached and reused across shards
"""

import logging
from pathlib import Path

import pyarrow as pa
from pydantic import BaseModel

from ...core.config.run_config import SimulationConfig
from ...core.data.registry import MarketDatasetRegistry
from ...core.graph.schemas import CurrencyPath
from .fx_converter import FXConverter
from .market_cache import MarketDataCache
from .timeline import TimelinePoint

logger = logging.getLogger(__name__)


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
        Supports multi-hop FX conversion when direct pairs aren't available.

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
        conversion_path: CurrencyPath | None = None
        conversion_files_map: dict[str, list[Path]] = {}

        if needs_conversion:
            # First try direct conversion pair
            conversion_info = self.fx_converter.get_conversion_pair(self.pair)
            if conversion_info:
                direct_pair, is_inverted = conversion_info

                # Check if direct pair exists in dataset
                direct_files = [
                    Path(pd.file_path)
                    for pd in inventory.pair_dates
                    if pd.pair == direct_pair
                ]

                if direct_files:
                    # Direct pair available - create simple path
                    native = self.fx_converter.get_native_currency(self.pair)
                    conversion_path = CurrencyPath(
                        currencies=[native, self.fx_converter.reporting_currency],
                        pairs=[direct_pair],
                        inversions=[is_inverted],
                    )
                    conversion_files_map[direct_pair] = direct_files
                    logger.debug(
                        f"Using direct FX conversion: {direct_pair} "
                        f"(inverted={is_inverted})"
                    )

            # If no direct pair, try pathfinding for multi-hop conversion
            if conversion_path is None:
                available_pairs = list({pd.pair for pd in inventory.pair_dates})
                logger.info(
                    f"Direct conversion pair not found for {self.pair}, "
                    f"attempting triangulation with available pairs: {available_pairs}"
                )

                conversion_path = self.fx_converter.get_conversion_path(
                    self.pair, available_pairs
                )

                if conversion_path:
                    logger.info(
                        f"Found conversion path: {' -> '.join(conversion_path.currencies)} "
                        f"via pairs {conversion_path.pairs}"
                    )

                    # Collect files for each pair in the path
                    for conv_pair in conversion_path.pairs:
                        pair_data_files = [
                            Path(pd.file_path)
                            for pd in inventory.pair_dates
                            if pd.pair == conv_pair
                        ]
                        if not pair_data_files:
                            raise ValueError(
                                f"No market data found for conversion pair {conv_pair} "
                                f"in dataset {self.config.dataset}"
                            )
                        conversion_files_map[conv_pair] = pair_data_files

        # Use process-local cache for connection reuse
        cache = MarketDataCache.get_instance()
        conn = cache.get_connection()

        # Register market data tables (cached - only registered once per pair)
        market_table = cache.ensure_pair_registered(
            self.pair, pair_files, self.config.dataset
        )

        # Register FX conversion pair tables
        fx_tables: dict[str, str] = {}
        for i, (conv_pair, files) in enumerate(conversion_files_map.items()):
            fx_tables[conv_pair] = cache.ensure_fx_pair_registered(
                conv_pair, files, self.config.dataset, i
            )

        # Create timeline temp table (this is small, OK to recreate)
        timeline_table = pa.table({
            "timestamp_ms": pa.array(timestamps_ms, type=pa.int64())
        })
        conn.register("timeline", timeline_table)

        # Build query using native ASOF JOIN
        query = self._build_query_asof(
            market_table, conversion_path, fx_tables
        )
        result = conn.execute(query).fetchall()

        # Unregister timeline table to avoid memory leak
        try:
            conn.unregister("timeline")
        except Exception:
            pass

        # Build snapshot dict
        snapshots = {}

        # Determine number of FX rate columns based on conversion path
        num_fx_rates = len(conversion_path.pairs) if conversion_path else 0

        for row in result:
            # First 5 columns are always: timestamp, bid, ask, mid, spread
            ts_ms, bid, ask, mid, spread = row[:5]

            if bid is None:
                raise ValueError(
                    f"No market tick found for {self.pair} at or before "
                    f"timestamp {ts_ms}. Market data gap detected."
                )

            # Calculate combined FX rate from conversion path
            if conversion_path and num_fx_rates > 0:
                fx_rates = list(row[5:5 + num_fx_rates])
                # Replace None with 1.0
                fx_rates = [r if r is not None else 1.0 for r in fx_rates]
                fx_rate = FXConverter.calculate_chained_fx_rate(
                    fx_rates, conversion_path.inversions
                )
            else:
                fx_rate = 1.0

            snapshots[ts_ms] = MarketSnapshot(
                timestamp_ms=ts_ms,
                pair=self.pair,
                mid=mid,
                bid=bid,
                ask=ask,
                spread=spread,
                fx_rate=fx_rate,
            )

        return snapshots

    def _build_query_asof(
        self,
        market_table: str,
        conversion_path: CurrencyPath | None,
        fx_tables: dict[str, str],
    ) -> str:
        """Build DuckDB query using native ASOF JOIN for maximum performance.

        Uses DuckDB's native ASOF JOIN operator which is 10-100x faster than
        the window function approach.

        Args:
            market_table: Name of the cached market data table
            conversion_path: Path for FX conversion (or None if not needed)
            fx_tables: Map of conversion pair -> table name

        Returns:
            SQL query string
        """
        if not conversion_path or not fx_tables:
            # No FX conversion needed - simple ASOF join
            return f"""
            SELECT
                t.timestamp_ms,
                m.bid_tob,
                m.ask_tob,
                (m.bid_tob + m.ask_tob) / 2.0 AS mid,
                m.ask_tob - m.bid_tob AS spread
            FROM timeline t
            ASOF JOIN {market_table} m
                ON t.timestamp_ms >= m.timestamp_ms
            WHERE m.pair = '{self.pair}'
            ORDER BY t.timestamp_ms
            """

        # With FX conversion - chain ASOF JOINs
        # Build FX rate columns and joins
        fx_selects = []
        fx_joins = []

        for i, conv_pair in enumerate(conversion_path.pairs):
            table_name = fx_tables[conv_pair]
            alias = f"fx{i}"

            fx_selects.append(
                f"COALESCE(({alias}.bid_tob + {alias}.ask_tob) / 2.0, 1.0) AS fx_rate_{i}"
            )

            # Chain ASOF JOIN for each FX pair
            fx_joins.append(f"""
            ASOF JOIN {table_name} {alias}
                ON t.timestamp_ms >= {alias}.timestamp_ms
                AND {alias}.pair = '{conv_pair}'""")

        select_cols = [
            "t.timestamp_ms",
            "m.bid_tob",
            "m.ask_tob",
            "(m.bid_tob + m.ask_tob) / 2.0 AS mid",
            "m.ask_tob - m.bid_tob AS spread",
        ] + fx_selects

        query = f"""
        SELECT
            {', '.join(select_cols)}
        FROM timeline t
        ASOF JOIN {market_table} m
            ON t.timestamp_ms >= m.timestamp_ms
            AND m.pair = '{self.pair}'
        {''.join(fx_joins)}
        ORDER BY t.timestamp_ms
        """

        return query

    def _build_query(
        self,
        conversion_path: CurrencyPath | None,
        conversion_files_map: dict[str, list[Path]],
    ) -> str:
        """Build DuckDB query for market data and FX rates (legacy - window function approach).

        DEPRECATED: Use _build_query_asof instead for better performance.

        Args:
            conversion_path: Path for FX conversion (or None if not needed)
            conversion_files_map: Map of pair -> files for conversion pairs

        Returns:
            SQL query string
        """
        # Base CTE for traded pair market data
        base_cte = f"""
        ranked_ticks AS (
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
        )"""

        if not conversion_path or not conversion_files_map:
            # No conversion needed - simple query
            return f"""
            WITH {base_cte}
            SELECT
                timestamp_ms,
                bid_tob,
                ask_tob,
                mid,
                spread
            FROM ranked_ticks
            WHERE rn = 1
            ORDER BY timestamp_ms
            """

        # Build CTEs for each FX conversion pair
        fx_ctes = []
        fx_selects = []
        fx_joins = []

        pair_to_table = {}
        for i, conv_pair in enumerate(conversion_path.pairs):
            table_name = f"fx_market_{i}"
            cte_name = f"ranked_fx_{i}"
            pair_to_table[conv_pair] = (table_name, cte_name, i)

            fx_ctes.append(f"""
        {cte_name} AS (
            SELECT
                t.timestamp_ms,
                (fx.bid_tob + fx.ask_tob) / 2.0 AS fx_mid,
                ROW_NUMBER() OVER (
                    PARTITION BY t.timestamp_ms
                    ORDER BY fx.timestamp_ms DESC
                ) AS rn
            FROM timeline t
            LEFT JOIN {table_name} fx
                ON fx.timestamp_ms <= t.timestamp_ms
                AND fx.pair = '{conv_pair}'
        )""")

            fx_selects.append(f"COALESCE(fx{i}.fx_mid, 1.0) AS fx_rate_{i}")
            fx_joins.append(f"""
            LEFT JOIN {cte_name} fx{i}
                ON rt.timestamp_ms = fx{i}.timestamp_ms
                AND fx{i}.rn = 1""")

        # Combine all CTEs
        all_ctes = base_cte + "," + ",".join(fx_ctes)

        # Build final SELECT
        select_cols = [
            "rt.timestamp_ms",
            "rt.bid_tob",
            "rt.ask_tob",
            "rt.mid",
            "rt.spread",
        ] + fx_selects

        query = f"""
        WITH {all_ctes}
        SELECT
            {', '.join(select_cols)}
        FROM ranked_ticks rt
        {''.join(fx_joins)}
        WHERE rt.rn = 1
        ORDER BY rt.timestamp_ms
        """

        return query
