"""Canonical data schemas for trades and market data.

These schemas define the contract for all data flowing through the backtester.
Both Pydantic models (for validation) and PyArrow schemas (for Parquet I/O)
are provided.
"""

from typing import Annotated, Literal

import pyarrow as pa
from pydantic import BaseModel, Field, field_validator

from ..config.defaults import Defaults
from ..config.universe import validate_pair


# =============================================================================
# Pydantic Models (for validation and API contracts)
# =============================================================================


class TradeRecord(BaseModel):
    """Canonical representation of a single trade.

    Trades can be either client trades (incoming flow) or hedge trades
    (executed by the desk to manage risk).

    Side Convention (HOUSE's perspective throughout the system):
        +1 = House BUYS base currency (going long)
        -1 = House SELLS base currency (going short)

        For client flow: When a client buys from us, WE are selling (side=-1).
        For hedges: When we hedge by buying in the market, side=+1.
    """

    timestamp_ms: Annotated[
        int,
        Field(description="Trade execution time in milliseconds since Unix epoch"),
    ]
    pair: Annotated[
        str,
        Field(description="Currency pair in canonical form (e.g., EURUSD)"),
    ]
    side: Annotated[
        Literal[1, -1],
        Field(description="+1 = house buys base, -1 = house sells base"),
    ]
    qty: Annotated[
        float,
        Field(gt=0, description="Quantity in base currency units"),
    ]
    price: Annotated[
        float,
        Field(gt=0, description="Execution price"),
    ]
    trade_id: Annotated[
        str,
        Field(min_length=1, description="Unique trade identifier"),
    ]
    order_id: Annotated[
        str | None,
        Field(default=None, description="Parent order identifier if applicable"),
    ]

    @field_validator("pair")
    @classmethod
    def validate_pair_format(cls, v: str) -> str:
        """Ensure pair is uppercase and valid."""
        v = v.upper()
        if not validate_pair(v):
            raise ValueError(f"Invalid pair format: {v}")
        return v


class DecrossedTradeRecord(BaseModel):
    """Trade record with decrossing metadata.

    Represents a single leg resulting from decrossing a cross-pair trade.
    For direct-pair trades, this is a passthrough with is_direct=True.
    """

    # Original TradeRecord fields
    timestamp_ms: Annotated[
        int,
        Field(description="Trade execution time in milliseconds since Unix epoch"),
    ]
    pair: Annotated[
        str,
        Field(description="Direct pair for this leg (e.g., EURUSD)"),
    ]
    side: Annotated[
        Literal[1, -1],
        Field(description="+1 = buy base currency, -1 = sell base currency"),
    ]
    qty: Annotated[
        float,
        Field(gt=0, description="Quantity in base currency units"),
    ]
    price: Annotated[
        float,
        Field(gt=0, description="Backsolved price to match original cross rate"),
    ]
    trade_id: Annotated[
        str,
        Field(min_length=1, description="Unique leg identifier"),
    ]
    order_id: Annotated[
        str | None,
        Field(default=None, description="Parent order identifier if applicable"),
    ]

    # Decrossing metadata
    source_trade_id: Annotated[
        str,
        Field(min_length=1, description="Original cross-trade ID"),
    ]
    source_pair: Annotated[
        str,
        Field(description="Original pair (e.g., EURGBP for cross, EURUSD for direct)"),
    ]
    source_price: Annotated[
        float,
        Field(gt=0, description="Original trade price"),
    ]
    leg_index: Annotated[
        int,
        Field(ge=0, description="Leg number in decomposition (0-indexed)"),
    ]
    leg_count: Annotated[
        int,
        Field(gt=0, description="Total legs in decomposition"),
    ]
    path: Annotated[
        list[str],
        Field(min_length=2, description="Currency path (e.g., ['EUR', 'USD', 'GBP'])"),
    ]
    is_direct: Annotated[
        bool,
        Field(description="True if original trade was already a direct pair"),
    ]

    @field_validator("pair", "source_pair")
    @classmethod
    def validate_pair_format(cls, v: str) -> str:
        """Ensure pair is uppercase and valid."""
        v = v.upper()
        if not validate_pair(v):
            raise ValueError(f"Invalid pair format: {v}")
        return v

    @field_validator("path")
    @classmethod
    def validate_path_currencies(cls, v: list[str]) -> list[str]:
        """Ensure all currencies in path are 3-letter uppercase codes."""
        if not v or len(v) < 2:
            raise ValueError("Path must contain at least 2 currencies")
        result = []
        for curr in v:
            curr = curr.upper()
            if len(curr) != 3 or not curr.isalpha():
                raise ValueError(f"Invalid currency code in path: {curr}")
            result.append(curr)
        return result

    @classmethod
    def batch_from_table(cls, table: pa.Table) -> list["DecrossedTradeRecord"]:
        """Efficiently batch-construct from Arrow table without per-row validation.

        This method skips Pydantic validation since data from parquet was already
        validated when written. Uses model_construct() for ~10x faster loading.

        Args:
            table: PyArrow table with DECROSSED_TRADE_ARROW_SCHEMA

        Returns:
            List of DecrossedTradeRecord instances
        """
        # Direct column access - much faster than to_pylist()
        n = len(table)
        if n == 0:
            return []

        # Extract columns (avoid repeated dict lookups)
        timestamp_ms = table["timestamp_ms"].to_pylist()
        pair = table["pair"].to_pylist()
        side = table["side"].to_pylist()
        qty = table["qty"].to_pylist()
        price = table["price"].to_pylist()
        trade_id = table["trade_id"].to_pylist()
        order_id = table["order_id"].to_pylist()
        source_trade_id = table["source_trade_id"].to_pylist()
        source_pair = table["source_pair"].to_pylist()
        source_price = table["source_price"].to_pylist()
        leg_index = table["leg_index"].to_pylist()
        leg_count = table["leg_count"].to_pylist()
        path = table["path"].to_pylist()
        is_direct = table["is_direct"].to_pylist()

        # Batch construct using model_construct (skips validation)
        return [
            cls.model_construct(
                timestamp_ms=timestamp_ms[i],
                pair=pair[i],
                side=side[i],
                qty=qty[i],
                price=price[i],
                trade_id=trade_id[i],
                order_id=order_id[i],
                source_trade_id=source_trade_id[i],
                source_pair=source_pair[i],
                source_price=source_price[i],
                leg_index=leg_index[i],
                leg_count=leg_count[i],
                path=path[i],
                is_direct=is_direct[i],
            )
            for i in range(n)
        ]


class MarketTickRecord(BaseModel):
    """Canonical representation of a market data tick.

    Contains top-of-book prices and optional depth (rung) data.
    """

    timestamp_ms: Annotated[
        int,
        Field(description="Tick time in milliseconds since Unix epoch"),
    ]
    pair: Annotated[
        str,
        Field(description="Currency pair in canonical form"),
    ]
    bid_tob: Annotated[
        float,
        Field(gt=0, description="Best bid price (top of book)"),
    ]
    ask_tob: Annotated[
        float,
        Field(gt=0, description="Best ask price (top of book)"),
    ]
    bid_qty_tob: Annotated[
        float,
        Field(gt=0, description="Quantity available at best bid"),
    ]
    ask_qty_tob: Annotated[
        float,
        Field(gt=0, description="Quantity available at best ask"),
    ]
    # Optional depth data (rungs)
    bid_rungs_qty: Annotated[
        list[float] | None,
        Field(default=None, description="Ordered array of bid quantities at each rung"),
    ]
    bid_rungs_price: Annotated[
        list[float] | None,
        Field(default=None, description="Ordered array of bid prices at each rung"),
    ]
    ask_rungs_qty: Annotated[
        list[float] | None,
        Field(default=None, description="Ordered array of ask quantities at each rung"),
    ]
    ask_rungs_price: Annotated[
        list[float] | None,
        Field(default=None, description="Ordered array of ask prices at each rung"),
    ]

    @field_validator("pair")
    @classmethod
    def validate_pair_format(cls, v: str) -> str:
        """Ensure pair is uppercase and valid."""
        v = v.upper()
        if not validate_pair(v):
            raise ValueError(f"Invalid pair format: {v}")
        return v

    @property
    def mid(self) -> float:
        """Reference mid price: (bid_tob + ask_tob) / 2."""
        return (self.bid_tob + self.ask_tob) / 2.0

    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.ask_tob - self.bid_tob


class DatasetMeta(BaseModel):
    """Metadata for a dataset stored in meta.json."""

    name: Annotated[
        str,
        Field(min_length=1, description="Dataset unique identifier"),
    ]
    description: Annotated[
        str | None,
        Field(default=None, description="Human-readable description"),
    ]
    pairs: Annotated[
        list[str],
        Field(min_length=1, description="List of currency pairs in this dataset"),
    ]
    start_date: Annotated[
        str,
        Field(
            pattern=r"^\d{4}-\d{2}-\d{2}$",
            description="First date with data (YYYY-MM-DD)",
        ),
    ]
    end_date: Annotated[
        str,
        Field(
            pattern=r"^\d{4}-\d{2}-\d{2}$",
            description="Last date with data (YYYY-MM-DD)",
        ),
    ]
    source: Annotated[
        str | None,
        Field(default=None, description="Data source identifier"),
    ]
    created_at_ms: Annotated[
        int,
        Field(description="Creation timestamp in milliseconds since epoch"),
    ]

    @field_validator("pairs")
    @classmethod
    def validate_pairs(cls, v: list[str]) -> list[str]:
        """Ensure all pairs are valid and uppercase."""
        result = []
        for pair in v:
            pair = pair.upper()
            if not validate_pair(pair):
                raise ValueError(f"Invalid pair format: {pair}")
            result.append(pair)
        return result


# =============================================================================
# PyArrow Schemas (for Parquet I/O)
# =============================================================================


TRADE_ARROW_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("timestamp_ms", pa.int64(), nullable=False),
        pa.field("pair", pa.string(), nullable=False),
        pa.field("side", pa.int8(), nullable=False),
        pa.field("qty", pa.float64(), nullable=False),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("trade_id", pa.string(), nullable=False),
        pa.field("order_id", pa.string(), nullable=True),
    ],
    metadata={
        b"description": b"Canonical trade schema for eFX backtester",
        b"version": b"1.0",
    },
)


DECROSSED_TRADE_ARROW_SCHEMA: pa.Schema = pa.schema(
    [
        # Original TradeRecord fields
        pa.field("timestamp_ms", pa.int64(), nullable=False),
        pa.field("pair", pa.string(), nullable=False),
        pa.field("side", pa.int8(), nullable=False),
        pa.field("qty", pa.float64(), nullable=False),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("trade_id", pa.string(), nullable=False),
        pa.field("order_id", pa.string(), nullable=True),
        # Decrossing metadata
        pa.field("source_trade_id", pa.string(), nullable=False),
        pa.field("source_pair", pa.string(), nullable=False),
        pa.field("source_price", pa.float64(), nullable=False),
        pa.field("leg_index", pa.int32(), nullable=False),
        pa.field("leg_count", pa.int32(), nullable=False),
        pa.field("path", pa.list_(pa.string()), nullable=False),
        pa.field("is_direct", pa.bool_(), nullable=False),
    ],
    metadata={
        b"description": b"Decrossed trade schema for eFX backtester",
        b"version": b"1.0",
    },
)


MARKET_ARROW_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("timestamp_ms", pa.int64(), nullable=False),
        pa.field("pair", pa.string(), nullable=False),
        pa.field("bid_tob", pa.float64(), nullable=False),
        pa.field("ask_tob", pa.float64(), nullable=False),
        pa.field("bid_qty_tob", pa.float64(), nullable=False),
        pa.field("ask_qty_tob", pa.float64(), nullable=False),
        pa.field("bid_rungs_qty", pa.list_(pa.float64()), nullable=True),
        pa.field("bid_rungs_price", pa.list_(pa.float64()), nullable=True),
        pa.field("ask_rungs_qty", pa.list_(pa.float64()), nullable=True),
        pa.field("ask_rungs_price", pa.list_(pa.float64()), nullable=True),
    ],
    metadata={
        b"description": b"Canonical market data schema for eFX backtester",
        b"version": b"1.0",
    },
)


# =============================================================================
# Utility Functions
# =============================================================================


def compute_ref_mid(bid_tob: float, ask_tob: float) -> float:
    """Compute reference mid price.

    Args:
        bid_tob: Best bid price
        ask_tob: Best ask price

    Returns:
        Reference mid: (bid_tob + ask_tob) / 2
    """
    return (bid_tob + ask_tob) / 2.0
