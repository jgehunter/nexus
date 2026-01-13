"""Service layer for trade decrossing operations.

Provides high-level API for building currency graphs, previewing decompositions,
and batch processing trade books through the decrossing pipeline.
"""

import gc
from collections import defaultdict
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.parquet as pq

from ...core.config.run_config import DecrossConfig
from ...core.config.universe import get_base_currency, get_quote_currency
from ...core.data.duck import get_connection, register_parquet_files
from ...core.data.registry import MarketDatasetRegistry, TradeBookRegistry
from ...core.data.schemas import (
    DECROSSED_TRADE_ARROW_SCHEMA,
    DecrossedTradeRecord,
    MarketTickRecord,
    TradeRecord,
)
from ...core.graph.currency_graph import CurrencyGraphBuilder
from ...core.graph.pathfinding import PathFinder
from ...core.graph.schemas import CurrencyGraph
from ...engine.decrosser import DecrossingEngine
from ...util.time import ms_to_file_date

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], None]


class DecrossService:
    """Service for decrossing operations.

    Handles graph construction, trade decomposition preview, and batch
    processing of trade books with market data.
    """

    def __init__(self, data_root: Path, config: DecrossConfig | None = None):
        """Initialize decross service.

        Args:
            data_root: Root directory for data (contains tradebooks/ and datasets/)
            config: Decrossing configuration (uses defaults if None)
        """
        self.data_root = Path(data_root)
        self.config = config or DecrossConfig()

        # Initialize registries
        self.market_registry = MarketDatasetRegistry(self.data_root)
        self.tradebook_registry = TradeBookRegistry(self.data_root)

        # Cache for built graphs (dataset_name -> graph)
        self._graph_cache: dict[str, CurrencyGraph] = {}

        # Cache for computed paths (from_curr, to_curr) -> CurrencyPath | None
        self._path_cache: dict[tuple[str, str], tuple] = {}

    def build_graph_for_dataset(self, dataset_name: str) -> CurrencyGraph:
        """Build currency graph from market dataset's direct pairs.

        Args:
            dataset_name: Name of market dataset

        Returns:
            CurrencyGraph with nodes and edges

        Raises:
            ValueError: If dataset not found
        """
        # Check cache first
        if dataset_name in self._graph_cache:
            return self._graph_cache[dataset_name]

        # Discover dataset inventory
        inventory = self.market_registry.discover_dataset(dataset_name)

        # Build graph from pairs
        builder = CurrencyGraphBuilder(inventory.pairs)
        graph = builder.build_graph()

        # Cache for future use
        self._graph_cache[dataset_name] = graph

        return graph

    def _get_or_compute_path(
        self,
        from_curr: str,
        to_curr: str,
        graph: CurrencyGraph,
    ) -> tuple[list[str] | None, bool]:
        """Get decomposition path from cache or compute and cache.

        Args:
            from_curr: Source currency
            to_curr: Target currency
            graph: Currency graph

        Returns:
            Tuple of (path_pairs, is_direct) where:
            - path_pairs: List of pair names in path, or None if no path
            - is_direct: True if trade pair is a direct pair
        """
        cache_key = (from_curr, to_curr)

        if cache_key not in self._path_cache:
            # Check if it's a direct pair
            direct_pairs = {edge.pair for edge in graph.edges if not edge.is_inverted}
            trade_pair = from_curr + to_curr

            if trade_pair in direct_pairs:
                # Direct pair: cache as direct
                self._path_cache[cache_key] = ([trade_pair], True)
            else:
                # Cross pair: find path
                path_finder = PathFinder(
                    graph,
                    priority_currencies=self.config.priority_currencies,
                )
                path = path_finder.find_path(
                    from_curr,
                    to_curr,
                    max_path_length=self.config.max_path_length,
                )

                if path is None:
                    # No path found: cache None
                    self._path_cache[cache_key] = (None, False)
                else:
                    # Path found: cache pairs
                    self._path_cache[cache_key] = (path.pairs, False)

        return self._path_cache[cache_key]

    def preview_decross(
        self,
        trades: list[TradeRecord],
        market_dataset_name: str,
    ) -> list[dict]:
        """Preview decrossing for sample trades without writing output.

        Args:
            trades: List of trades to preview
            market_dataset_name: Market dataset to use for graph/ticks

        Returns:
            List of preview dicts with keys:
            - source_trade_id
            - source_pair
            - path
            - legs (list of leg dicts)
            - is_direct

        Example:
            [{
                "source_trade_id": "T1",
                "source_pair": "EURGBP",
                "path": ["EUR", "USD", "GBP"],
                "legs": [
                    {"pair": "EURUSD", "side": 1, "qty": 1000.0, "price": 1.10},
                    {"pair": "GBPUSD", "side": -1, "qty": 880.0, "price": 1.25}
                ],
                "is_direct": False
            }]
        """
        # Build graph
        graph = self.build_graph_for_dataset(market_dataset_name)
        path_finder = PathFinder(graph, self.config.priority_currencies)
        engine = DecrossingEngine(graph, path_finder, self.config)

        # For preview, we need market ticks
        # Since we don't have actual ticks, we'll create mock ticks at mid=1.0
        # This is just for preview purposes
        mock_ticks = self._create_mock_ticks(graph)

        previews = []
        for trade in trades:
            try:
                legs = engine.decross_trade(trade, mock_ticks)

                preview = {
                    "source_trade_id": legs[0].source_trade_id,
                    "source_pair": legs[0].source_pair,
                    "path": legs[0].path,
                    "legs": [
                        {
                            "pair": leg.pair,
                            "side": leg.side,
                            "qty": leg.qty,
                            "price": leg.price,
                            "leg_index": leg.leg_index,
                        }
                        for leg in legs
                    ],
                    "is_direct": legs[0].is_direct,
                }
                previews.append(preview)

            except ValueError as e:
                # If no path exists, include error in preview
                previews.append({
                    "source_trade_id": trade.trade_id,
                    "source_pair": trade.pair,
                    "error": str(e),
                })

        return previews

    def decross_tradebook(
        self,
        tradebook_name: str,
        market_dataset_name: str,
        output_dir: Path,
        date_range: tuple[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Stream-process trade book through decrossing pipeline.

        This is the main production function that:
        1. Builds currency graph from market dataset
        2. Processes trades DATE BY DATE to minimize memory usage
        3. Writes output incrementally per date
        4. Reports progress via callback

        Memory optimizations:
        - Process one date at a time (bounded memory)
        - Per-trade tick fetching (no bulk cache)
        - Incremental output writing
        - Explicit garbage collection between dates

        Args:
            tradebook_name: Name of trade book to decross
            market_dataset_name: Market dataset for graph and ticks
            output_dir: Output directory for decrossed trades
            date_range: Optional (start_date, end_date) tuple (YYYY-MM-DD format)
            progress_callback: Optional callback(stage, current, total, message)

        Raises:
            ValueError: If tradebook or dataset not found, or data issues
        """
        # Step 1: Build graph and initialize engine
        graph = self.build_graph_for_dataset(market_dataset_name)
        path_finder = PathFinder(graph, self.config.priority_currencies)
        engine = DecrossingEngine(graph, path_finder, self.config)

        # Step 2: Get list of trade dates (small metadata query)
        trade_dates = self._get_trade_dates(tradebook_name, date_range)
        total_dates = len(trade_dates)

        if not trade_dates:
            raise ValueError(f"No trade files found for {tradebook_name} in date range")

        # Create output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 3: Process one date at a time
        for i, (date_str, trade_file) in enumerate(trade_dates):
            # Report progress
            if progress_callback:
                progress_callback(
                    "decrossing", i, total_dates,
                    f"Decrossing {date_str}"
                )

            # Process single date (bounded memory)
            self._decross_single_date(
                trade_file=trade_file,
                date_str=date_str,
                market_dataset_name=market_dataset_name,
                output_dir=output_dir,
                graph=graph,
                engine=engine,
            )

            # Explicit cleanup after each date
            gc.collect()

        # Final progress update
        if progress_callback:
            progress_callback(
                "decrossing", total_dates, total_dates,
                "Decrossing complete"
            )

    def _get_trade_dates(
        self,
        tradebook_name: str,
        date_range: tuple[str, str] | None = None,
    ) -> list[tuple[str, Path]]:
        """Get list of trade dates and their file paths.

        Args:
            tradebook_name: Name of trade book
            date_range: Optional (start_date, end_date) in YYYY-MM-DD format

        Returns:
            List of (date_str, file_path) tuples, sorted by date
        """
        tradebook_inv = self.tradebook_registry.discover_tradebook(tradebook_name)

        trade_dates = []
        for df in tradebook_inv.date_files:
            date_str = df.date  # YYYYMMDD format
            file_path = Path(df.file_path)

            # Filter by date range if specified
            if date_range:
                start_date, end_date = date_range
                # Convert YYYY-MM-DD to YYYYMMDD format for comparison
                start_date_file = start_date.replace("-", "")
                end_date_file = end_date.replace("-", "")
                if not (start_date_file <= date_str <= end_date_file):
                    continue

            trade_dates.append((date_str, file_path))

        # Sort by date
        return sorted(trade_dates, key=lambda x: x[0])

    def _get_market_files_for_date(
        self,
        market_dataset_name: str,
        date_str: str,
    ) -> list[Path]:
        """Get market data files for a specific date.

        Args:
            market_dataset_name: Name of market dataset
            date_str: Date in YYYYMMDD format

        Returns:
            List of market file paths for the date
        """
        market_inv = self.market_registry.discover_dataset(market_dataset_name)

        market_files = []
        for pd in market_inv.pair_dates:
            if pd.date == date_str:
                market_files.append(Path(pd.file_path))

        return market_files

    def _decross_single_date(
        self,
        trade_file: Path,
        date_str: str,
        market_dataset_name: str,
        output_dir: Path,
        graph: CurrencyGraph,
        engine: DecrossingEngine,
    ) -> None:
        """Process a single date's trades with bounded memory.

        Args:
            trade_file: Path to trade file for this date
            date_str: Date in YYYYMMDD format
            market_dataset_name: Market dataset name
            output_dir: Output directory
            graph: Currency graph
            engine: Decrossing engine
        """
        # Get market files for this date
        market_files = self._get_market_files_for_date(market_dataset_name, date_str)

        if not market_files:
            # Try to get market files from surrounding dates for ASOF join
            market_inv = self.market_registry.discover_dataset(market_dataset_name)
            # Get all market files up to this date (for ASOF join lookback)
            market_files = [
                Path(pd.file_path) for pd in market_inv.pair_dates
                if pd.date <= date_str
            ]

        if not market_files:
            print(f"Warning: No market data available for date {date_str}")
            return

        decrossed_legs: list[DecrossedTradeRecord] = []
        batch_size = 1000
        write_threshold = 10000

        with get_connection(":memory:") as conn:
            # Register ONLY this date's trade data
            register_parquet_files(conn, "trades", [trade_file])
            # Register market data (need data up to this date for ASOF join)
            register_parquet_files(conn, "market", market_files)

            # Check if order_id column exists in trades table (it's optional)
            schema = conn.execute("DESCRIBE trades").fetchall()
            has_order_id = any(col[0] == "order_id" for col in schema)
            order_id_select = "order_id" if has_order_id else "NULL as order_id"

            # Stream trades with cursor (no fetchall)
            trades_query = f"""
            SELECT
                timestamp_ms,
                pair,
                side,
                qty,
                price,
                trade_id,
                {order_id_select}
            FROM trades
            ORDER BY timestamp_ms
            """
            cursor = conn.execute(trades_query)

            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    break

                for row in batch:
                    timestamp_ms, pair, side, qty, price, trade_id, order_id = row

                    # Build TradeRecord
                    trade = TradeRecord(
                        timestamp_ms=int(timestamp_ms),
                        pair=str(pair),
                        side=int(side),
                        qty=float(qty),
                        price=float(price),
                        trade_id=str(trade_id),
                        order_id=str(order_id) if order_id else None,
                    )

                    # Fetch ticks for this trade (bounded query)
                    try:
                        ticks = self._fetch_ticks_for_trade(trade, graph, conn)
                    except ValueError as e:
                        print(f"Warning: Failed to get ticks for trade {trade.trade_id}: {e}")
                        continue

                    # Decross the trade
                    try:
                        legs = engine.decross_trade(trade, ticks)
                        decrossed_legs.extend(legs)
                    except ValueError as e:
                        print(f"Warning: Failed to decross trade {trade.trade_id}: {e}")
                        continue

                # Write batch if accumulated enough
                if len(decrossed_legs) >= write_threshold:
                    self._append_to_output(decrossed_legs, output_dir)
                    decrossed_legs = []

            # Write remaining legs
            if decrossed_legs:
                self._append_to_output(decrossed_legs, output_dir)

    def _fetch_ticks_for_trade(
        self,
        trade: TradeRecord,
        graph: CurrencyGraph,
        conn,
    ) -> dict[str, MarketTickRecord]:
        """Fetch ticks for a single trade (bounded, simple query).

        Args:
            trade: Trade record
            graph: Currency graph
            conn: DuckDB connection

        Returns:
            Dict of {pair: MarketTickRecord}

        Raises:
            ValueError: If required tick is missing
        """
        base_curr = get_base_currency(trade.pair)
        quote_curr = get_quote_currency(trade.pair)

        path_pairs, _ = self._get_or_compute_path(base_curr, quote_curr, graph)

        if path_pairs is None:
            raise ValueError(f"No path for {trade.pair}")

        ticks = {}
        for pair in path_pairs:
            # Simple ASOF query - DuckDB optimizes this well
            result = conn.execute(f"""
                SELECT timestamp_ms, bid_tob, ask_tob, bid_qty_tob, ask_qty_tob
                FROM market
                WHERE pair = '{pair}' AND timestamp_ms <= {trade.timestamp_ms}
                ORDER BY timestamp_ms DESC
                LIMIT 1
            """).fetchone()

            if result is None:
                raise ValueError(
                    f"No tick for {pair} at {trade.timestamp_ms}. "
                    f"Market data gap detected."
                )

            tick_ts, bid, ask, bid_qty, ask_qty = result
            ticks[pair] = MarketTickRecord(
                timestamp_ms=tick_ts,
                pair=pair,
                bid_tob=bid,
                ask_tob=ask,
                bid_qty_tob=bid_qty,
                ask_qty_tob=ask_qty,
            )

        return ticks

    def _append_to_output(
        self,
        legs: list[DecrossedTradeRecord],
        output_dir: Path,
    ) -> None:
        """Append decrossed legs to output files.

        Groups by (date, pair) and appends to existing files or creates new ones.

        Args:
            legs: List of decrossed trade legs
            output_dir: Root output directory
        """
        if not legs:
            return

        # Group legs by (date, pair)
        partitions: dict[tuple[str, str], list[DecrossedTradeRecord]] = defaultdict(list)

        for leg in legs:
            date_str = ms_to_file_date(leg.timestamp_ms)
            partitions[(date_str, leg.pair)].append(leg)

        # Write each partition
        for (date_str, pair), partition_legs in partitions.items():
            # Create date directory
            date_dir = output_dir / date_str
            date_dir.mkdir(exist_ok=True)

            # Convert to Arrow table
            records = [leg.model_dump() for leg in partition_legs]
            new_table = pa.Table.from_pylist(records, schema=DECROSSED_TRADE_ARROW_SCHEMA)

            # Sort by timestamp
            new_table = new_table.sort_by([("timestamp_ms", "ascending")])

            # Write or append to parquet
            output_file = date_dir / f"{pair}.parquet"

            if output_file.exists():
                # Append to existing file
                existing_table = pq.read_table(output_file)
                combined_table = pa.concat_tables([existing_table, new_table])
                combined_table = combined_table.sort_by([("timestamp_ms", "ascending")])
                pq.write_table(combined_table, output_file, compression="snappy")
            else:
                # Create new file
                pq.write_table(new_table, output_file, compression="snappy")

    def _get_ticks_from_cache(
        self,
        trade: TradeRecord,
        graph: CurrencyGraph,
        tick_cache: dict[tuple[str, int], MarketTickRecord],
    ) -> dict[str, MarketTickRecord]:
        """Get market ticks for a trade from the pre-built cache.

        Args:
            trade: Trade record
            graph: Currency graph
            tick_cache: Pre-built cache of (pair, timestamp) -> tick

        Returns:
            Dict of {pair: MarketTickRecord} for all path pairs

        Raises:
            ValueError: If required tick is missing from cache
        """
        base_curr = get_base_currency(trade.pair)
        quote_curr = get_quote_currency(trade.pair)

        path_pairs, _ = self._get_or_compute_path(base_curr, quote_curr, graph)

        if path_pairs is None:
            raise ValueError(f"No path for {trade.pair}")

        ticks = {}
        for pair in path_pairs:
            cache_key = (pair, trade.timestamp_ms)
            if cache_key not in tick_cache:
                raise ValueError(
                    f"No tick for {pair} at {trade.timestamp_ms} in cache. "
                    f"Market data gap detected."
                )
            ticks[pair] = tick_cache[cache_key]

        return ticks

    def _create_mock_ticks(self, graph: CurrencyGraph) -> dict[str, MarketTickRecord]:
        """Create mock market ticks for preview (all at mid=1.0).

        Args:
            graph: Currency graph

        Returns:
            Dict of {pair: mock_tick}
        """
        ticks = {}
        direct_pairs = {edge.pair for edge in graph.edges if not edge.is_inverted}

        for pair in direct_pairs:
            ticks[pair] = MarketTickRecord(
                timestamp_ms=0,
                pair=pair,
                bid_tob=0.9999,
                ask_tob=1.0001,
                bid_qty_tob=1000000.0,
                ask_qty_tob=1000000.0,
            )

        return ticks

    def _fetch_path_ticks(
        self,
        trade: TradeRecord,
        graph: CurrencyGraph,
        conn,
    ) -> dict[str, MarketTickRecord]:
        """Fetch market ticks for all pairs needed in decomposition path.

        Uses ASOF join to get the most recent tick before the trade timestamp
        for each pair in the decomposition path.

        Args:
            trade: Original trade
            graph: Currency graph
            conn: Active DuckDB connection with market data registered

        Returns:
            Dict of {pair: MarketTickRecord} for all path pairs

        Raises:
            ValueError: If any required tick is missing (data gap)
        """
        # Determine decomposition path using cache
        base_curr = get_base_currency(trade.pair)
        quote_curr = get_quote_currency(trade.pair)

        # Get path from cache or compute
        path_pairs, is_direct = self._get_or_compute_path(base_curr, quote_curr, graph)

        if path_pairs is None:
            raise ValueError(
                f"No decomposition path found for {trade.pair} "
                f"({base_curr} -> {quote_curr})"
            )

        # Build query to fetch ticks for all path pairs using ASOF join
        if not path_pairs:
            return {}

        # Create a comma-separated list of pair strings for SQL
        pairs_list = ", ".join(f"'{pair}'" for pair in path_pairs)

        # Query to fetch most recent tick before trade time for each pair
        # Use subquery with ROW_NUMBER to get most recent tick per pair
        query = f"""
        WITH path_pairs AS (
            SELECT unnest([{pairs_list}]) AS pair
        ),
        ranked_ticks AS (
            SELECT
                m.pair,
                m.timestamp_ms,
                m.bid_tob,
                m.ask_tob,
                m.bid_qty_tob,
                m.ask_qty_tob,
                ROW_NUMBER() OVER (PARTITION BY m.pair ORDER BY m.timestamp_ms DESC) as rn
            FROM market m
            WHERE m.pair IN ({pairs_list})
                AND m.timestamp_ms <= {trade.timestamp_ms}
        )
        SELECT
            pp.pair,
            rt.timestamp_ms,
            rt.bid_tob,
            rt.ask_tob,
            rt.bid_qty_tob,
            rt.ask_qty_tob
        FROM path_pairs pp
        LEFT JOIN ranked_ticks rt
            ON pp.pair = rt.pair
            AND rt.rn = 1
        """

        result = conn.execute(query).fetchall()

        # Build tick dict
        ticks = {}
        for row in result:
            pair, ts, bid, ask, bid_qty, ask_qty = row

            if bid is None:  # No tick found
                raise ValueError(
                    f"No market tick found for {pair} at or before "
                    f"trade timestamp {trade.timestamp_ms}. "
                    f"Market data gap detected."
                )

            ticks[pair] = MarketTickRecord(
                timestamp_ms=ts,
                pair=pair,
                bid_tob=bid,
                ask_tob=ask,
                bid_qty_tob=bid_qty,
                ask_qty_tob=ask_qty,
            )

        # Verify we got all pairs
        missing_pairs = set(path_pairs) - set(ticks.keys())
        if missing_pairs:
            raise ValueError(
                f"Missing market ticks for pairs: {missing_pairs}. "
                f"Check market dataset completeness."
            )

        return ticks

    def _write_decrossed_output(
        self,
        legs: list[DecrossedTradeRecord],
        output_dir: Path,
    ) -> None:
        """Write decrossed legs to partitioned parquet files.

        Partition structure: output_dir/{YYYYMMDD}/{pair}.parquet

        Args:
            legs: List of decrossed trade legs
            output_dir: Root output directory
        """
        if not legs:
            return

        # Group legs by (date, pair)
        from collections import defaultdict

        from ...util.time import ms_to_file_date

        partitions: dict[tuple[str, str], list[DecrossedTradeRecord]] = defaultdict(list)

        for leg in legs:
            # Extract date from timestamp (handles both ms and us formats)
            date_str = ms_to_file_date(leg.timestamp_ms)

            partitions[(date_str, leg.pair)].append(leg)

        # Write each partition
        output_dir.mkdir(parents=True, exist_ok=True)

        for (date_str, pair), partition_legs in partitions.items():
            # Create date directory
            date_dir = output_dir / date_str
            date_dir.mkdir(exist_ok=True)

            # Convert to Arrow table
            records = [leg.model_dump() for leg in partition_legs]
            table = pa.Table.from_pylist(records, schema=DECROSSED_TRADE_ARROW_SCHEMA)

            # Sort by timestamp within partition
            table = table.sort_by([("timestamp_ms", "ascending")])

            # Write parquet
            output_file = date_dir / f"{pair}.parquet"
            pq.write_table(table, output_file, compression="snappy")

    def get_config(self) -> DecrossConfig:
        """Get current decrossing configuration.

        Returns:
            DecrossConfig instance
        """
        return self.config
