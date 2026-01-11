"""Shard state schemas for stateful simulation.

Defines core data structures for maintaining simulation state across events and dates,
including FIFO queue management and trade-level PnL attribution.
"""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field


class FIFOSlice(BaseModel):
    """Single FIFO slice representing an open position component.

    Each slice tracks an unmatched portion of a trade (client or hedge) that
    remains open in the position queue. Slices are matched FIFO when opposing
    trades arrive.

    Attributes:
        slice_id: Unique identifier for this slice
        open_timestamp_ms: Timestamp when slice was opened (milliseconds)
        side: Trade side (+1 = buy base, -1 = sell base)
        qty: Remaining quantity in base currency
        open_mid: Mid price at slice open time (for inventory PnL calculation)
        source_type: Origin of the slice ("client" or "hedge")
        source_trade_id: ID of the trade that opened this slice
    """

    slice_id: str
    open_timestamp_ms: int
    side: int  # +1 (buy) or -1 (sell)
    qty: float
    open_mid: float
    source_type: str  # "client" or "hedge"
    source_trade_id: str


class ShardState(BaseModel):
    """Persistent state for a single shard (pair + date).

    Maintains the current position, FIFO queue, and cumulative PnL for a specific
    currency pair on a specific date. State is serializable for multi-day continuity.

    Attributes:
        pair: Currency pair (e.g., "EURUSD")
        date: Date in YYYYMMDD format
        fifo_queue: Ordered list of open slices (oldest first)
        net_position: Current net position (sum of all slice qty * side)
        cumulative_execution_pnl: Total execution PnL (exec_px - exec_mid)
        cumulative_inventory_pnl: Total inventory PnL from FIFO matching
        cumulative_hedge_pnl: Total hedge cost incurred
        last_timestamp_ms: Timestamp of last processed event
        last_mid: Last observed mid price
        version: Schema version for evolution
    """

    pair: str
    date: str  # YYYYMMDD

    # FIFO queue (sorted by open_timestamp_ms)
    fifo_queue: list[FIFOSlice] = Field(default_factory=list)

    # Current net position
    net_position: float = 0.0

    # Cumulative PnL components
    cumulative_execution_pnl: float = 0.0
    cumulative_inventory_pnl: float = 0.0
    cumulative_hedge_pnl: float = 0.0

    # Last processed state
    last_timestamp_ms: int = 0
    last_mid: float = 1.0

    # Version for schema evolution
    version: str = "1.0"

    def to_parquet(self, path: Path) -> None:
        """Serialize state to Parquet file.

        Args:
            path: Output file path

        Note:
            Follows existing pattern from DecrossedTradeRecord serialization.
        """
        # Convert state to dict
        state_dict = self.model_dump()

        # Flatten FIFO queue for Parquet (one row per slice)
        if self.fifo_queue:
            queue_records = [slice_.model_dump() for slice_ in self.fifo_queue]
            queue_table = pa.table({
                "slice_id": [r["slice_id"] for r in queue_records],
                "open_timestamp_ms": [r["open_timestamp_ms"] for r in queue_records],
                "side": [r["side"] for r in queue_records],
                "qty": [r["qty"] for r in queue_records],
                "open_mid": [r["open_mid"] for r in queue_records],
                "source_type": [r["source_type"] for r in queue_records],
                "source_trade_id": [r["source_trade_id"] for r in queue_records],
            })
        else:
            # Empty queue - create empty table with schema
            queue_table = pa.table({
                "slice_id": pa.array([], type=pa.string()),
                "open_timestamp_ms": pa.array([], type=pa.int64()),
                "side": pa.array([], type=pa.int8()),
                "qty": pa.array([], type=pa.float64()),
                "open_mid": pa.array([], type=pa.float64()),
                "source_type": pa.array([], type=pa.string()),
                "source_trade_id": pa.array([], type=pa.string()),
            })

        # Write to Parquet
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Store metadata as Parquet table with single row for state
        state_table = pa.table({
            "pair": [self.pair],
            "date": [self.date],
            "net_position": [self.net_position],
            "cumulative_execution_pnl": [self.cumulative_execution_pnl],
            "cumulative_inventory_pnl": [self.cumulative_inventory_pnl],
            "cumulative_hedge_pnl": [self.cumulative_hedge_pnl],
            "last_timestamp_ms": [self.last_timestamp_ms],
            "last_mid": [self.last_mid],
            "version": [self.version],
        })

        # Write state table
        pq.write_table(state_table, output_path / "state.parquet")

        # Write queue table
        pq.write_table(queue_table, output_path / "queue.parquet")

    @classmethod
    def from_parquet(cls, path: Path) -> "ShardState":
        """Deserialize state from Parquet files.

        Args:
            path: Directory containing state.parquet and queue.parquet

        Returns:
            ShardState instance

        Raises:
            FileNotFoundError: If state files not found
        """
        path = Path(path)

        # Read state table
        state_table = pq.read_table(path / "state.parquet")
        state_row = state_table.to_pylist()[0]

        # Read queue table
        queue_table = pq.read_table(path / "queue.parquet")
        queue_records = queue_table.to_pylist()

        # Reconstruct FIFO queue
        fifo_queue = [FIFOSlice(**record) for record in queue_records]

        # Build state
        return cls(
            pair=state_row["pair"],
            date=state_row["date"],
            fifo_queue=fifo_queue,
            net_position=state_row["net_position"],
            cumulative_execution_pnl=state_row["cumulative_execution_pnl"],
            cumulative_inventory_pnl=state_row["cumulative_inventory_pnl"],
            cumulative_hedge_pnl=state_row["cumulative_hedge_pnl"],
            last_timestamp_ms=state_row["last_timestamp_ms"],
            last_mid=state_row["last_mid"],
            version=state_row["version"],
        )


class TradePnLAttribution(BaseModel):
    """PnL attribution record linking PnL components to a source trade.

    Enables analysis of PnL by trade attributes (client, platform, etc.) by
    maintaining the linkage from each PnL component back to the originating trade.

    PnL is tracked in both native currency (quote currency of the pair) and
    reporting currency for proper aggregation.

    Attributes:
        timestamp_ms: Event timestamp
        event_type: Type of event ("client_fill", "hedge_fill", "hedge_match", "sample")
        source_trade_id: Links to DecrossedTradeRecord.source_trade_id
        pair: Currency pair
        native_currency: Native currency of PnL (quote currency of pair)
        reporting_currency: Reporting currency for aggregation (e.g., "USD")
        fx_rate: FX rate used for native -> reporting conversion
        metadata: Extensible dict for trade attributes (client, platform, etc.)
        execution_pnl_native: Execution PnL in native currency
        inventory_pnl_native: Inventory PnL in native currency
        hedge_pnl_native: Hedge cost in native currency
        unrealized_pnl_native: Unrealized PnL in native currency
        execution_pnl_reporting: Execution PnL in reporting currency
        inventory_pnl_reporting: Inventory PnL in reporting currency
        hedge_pnl_reporting: Hedge cost in reporting currency
        unrealized_pnl_reporting: Unrealized PnL in reporting currency
        matched_slices: Details of slices matched by this trade
        triggered_hedge: Whether this trade triggered a hedge
        hedge_allocation_pct: Percentage of hedge cost attributed to this trade
    """

    timestamp_ms: int
    event_type: str  # "client_fill", "hedge_fill", "hedge_match", "sample"

    # Source trade identification
    source_trade_id: str  # Links back to DecrossedTradeRecord.source_trade_id
    pair: str

    # Currency tracking for PnL conversion
    native_currency: str  # Quote currency of the pair (e.g., "USD" for EURUSD)
    reporting_currency: str  # Reporting currency (e.g., "USD" or "EUR")
    fx_rate: float  # FX rate: native -> reporting (1.0 if same currency)

    # Trade metadata (extensible for future attributes)
    metadata: dict = Field(
        default_factory=dict,
        description="Extensible metadata dict for client, platform, etc.",
    )

    # PnL components in NATIVE currency (quote currency of pair)
    execution_pnl_native: float = 0.0
    inventory_pnl_native: float = 0.0
    hedge_pnl_native: float = 0.0
    unrealized_pnl_native: float = 0.0

    # PnL components in REPORTING currency (for aggregation)
    execution_pnl_reporting: float = 0.0
    inventory_pnl_reporting: float = 0.0
    hedge_pnl_reporting: float = 0.0
    unrealized_pnl_reporting: float = 0.0

    # Attribution details
    matched_slices: list[dict] = Field(
        default_factory=list,
        description="List of {slice_source_trade_id, matched_qty, pnl} dicts",
    )
    triggered_hedge: bool = False
    hedge_allocation_pct: float = 0.0  # % of hedge cost attributed to this trade


class PnLAttributionRecord(BaseModel):
    """Complete PnL record for a single event with full trade-level attribution.

    Aggregates PnL across all trades affected by an event, while preserving
    per-trade attribution details for downstream analysis.

    Attributes:
        timestamp_ms: Event timestamp
        event_type: Type of event
        trade_attributions: Per-trade attribution breakdown
        total_execution_pnl_reporting: Sum of execution PnL in reporting currency
        total_inventory_pnl_reporting: Sum of inventory PnL in reporting currency
        total_hedge_pnl_reporting: Sum of hedge PnL in reporting currency
        total_unrealized_pnl_reporting: Sum of unrealized PnL in reporting currency
    """

    timestamp_ms: int
    event_type: str

    # Per-trade attribution breakdown
    trade_attributions: list[TradePnLAttribution]

    # Aggregate totals in REPORTING currency (for aggregation across pairs)
    total_execution_pnl_reporting: float
    total_inventory_pnl_reporting: float
    total_hedge_pnl_reporting: float
    total_unrealized_pnl_reporting: float


# PyArrow schema for PnL attribution output
# (Will be used for writing attribution records to Parquet)
PNL_ATTRIBUTION_ARROW_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("event_type", pa.string()),
    ("source_trade_id", pa.string()),
    ("pair", pa.string()),
    ("native_currency", pa.string()),
    ("reporting_currency", pa.string()),
    ("fx_rate", pa.float64()),
    ("metadata", pa.string()),  # JSON-encoded dict
    ("execution_pnl_native", pa.float64()),
    ("inventory_pnl_native", pa.float64()),
    ("hedge_pnl_native", pa.float64()),
    ("unrealized_pnl_native", pa.float64()),
    ("execution_pnl_reporting", pa.float64()),
    ("inventory_pnl_reporting", pa.float64()),
    ("hedge_pnl_reporting", pa.float64()),
    ("unrealized_pnl_reporting", pa.float64()),
    ("matched_slices", pa.string()),  # JSON-encoded list
    ("triggered_hedge", pa.bool_()),
    ("hedge_allocation_pct", pa.float64()),
])
