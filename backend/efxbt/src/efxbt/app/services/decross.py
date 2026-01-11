"""Service layer for trade decrossing operations.

Provides high-level API for building currency graphs, previewing decompositions,
and batch processing trade books through the decrossing pipeline.
"""

from pathlib import Path

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
    ) -> None:
        """Batch process trade book through decrossing pipeline.

        This is the main production function that:
        1. Builds currency graph from market dataset
        2. Loads trades and market data via DuckDB
        3. Performs ASOF join for market ticks at trade times
        4. Decrosses each trade
        5. Writes partitioned output

        Args:
            tradebook_name: Name of trade book to decross
            market_dataset_name: Market dataset for graph and ticks
            output_dir: Output directory for decrossed trades
            date_range: Optional (start_date, end_date) tuple (YYYYMMDD format)

        Raises:
            ValueError: If tradebook or dataset not found, or data issues
        """
        # Step 1: Build graph and initialize engine
        graph = self.build_graph_for_dataset(market_dataset_name)
        path_finder = PathFinder(graph, self.config.priority_currencies)
        engine = DecrossingEngine(graph, path_finder, self.config)

        # Step 2: Load data via DuckDB
        tradebook_inv = self.tradebook_registry.discover_tradebook(tradebook_name)
        market_inv = self.market_registry.discover_dataset(market_dataset_name)

        # Get file paths
        trade_files = [Path(df.file_path) for df in tradebook_inv.date_files]
        market_files = [Path(pd.file_path) for pd in market_inv.pair_dates]

        # Filter by date range if specified
        if date_range:
            start_date, end_date = date_range
            trade_files = [
                f for f in trade_files
                if start_date <= f.stem <= end_date
            ]

        if not trade_files:
            raise ValueError(f"No trade files found for {tradebook_name} in date range")

        # Step 3: Process with DuckDB ASOF join
        decrossed_legs: list[DecrossedTradeRecord] = []

        with get_connection(":memory:") as conn:
            # Register parquet files as views
            register_parquet_files(conn, "trades", trade_files)
            register_parquet_files(conn, "market", market_files)

            # ASOF join query to match trades with market ticks
            query = """
            SELECT
                t.timestamp_ms,
                t.pair,
                t.side,
                t.qty,
                t.price,
                t.trade_id,
                t.order_id,
                m.pair as market_pair,
                m.bid_tob,
                m.ask_tob
            FROM trades t
            ASOF LEFT JOIN market m
                ON t.timestamp_ms >= m.timestamp_ms
                AND t.pair = m.pair
            ORDER BY t.timestamp_ms
            """

            result = conn.execute(query).fetch_arrow_table()

            # Step 4: Process trades in batches (within connection context)
            # Process trades from arrow table
            for batch in result.to_batches(max_chunksize=10000):
                # Convert batch to list of dicts for iteration
                batch_dict = batch.to_pylist()

                for row in batch_dict:
                    # Build TradeRecord
                    trade = TradeRecord(
                        timestamp_ms=int(row["timestamp_ms"]),
                        pair=str(row["pair"]),
                        side=int(row["side"]),
                        qty=float(row["qty"]),
                        price=float(row["price"]),
                        trade_id=str(row["trade_id"]),
                        order_id=str(row["order_id"]) if row.get("order_id") else None,
                    )

                    # Fetch market ticks for all pairs in decomposition path
                    # Uses ASOF join to get most recent ticks before trade time
                    try:
                        market_ticks = self._fetch_path_ticks(trade, graph, conn)
                    except ValueError as e:
                        # Log error but continue processing (e.g., missing market data)
                        print(f"Warning: Failed to fetch ticks for trade {trade.trade_id}: {e}")
                        continue

                    # Decross the trade using fetched ticks
                    try:
                        legs = engine.decross_trade(trade, market_ticks)
                        decrossed_legs.extend(legs)
                    except ValueError as e:
                        # Log error but continue processing
                        print(f"Warning: Failed to decross trade {trade.trade_id}: {e}")
                        continue

        # Step 5: Write partitioned output
        self._write_decrossed_output(decrossed_legs, output_dir)

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
        from datetime import datetime

        partitions: dict[tuple[str, str], list[DecrossedTradeRecord]] = defaultdict(list)

        for leg in legs:
            # Extract date from timestamp_ms
            dt = datetime.fromtimestamp(leg.timestamp_ms / 1000.0)
            date_str = dt.strftime("%Y%m%d")

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
