"""Lightweight internal state structures for hot path performance.

Uses dataclasses instead of Pydantic to avoid validation overhead in the simulation loop.
These are converted to Pydantic models only at API boundaries.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class TradePnLAttributionInternal:
    """Lightweight version of TradePnLAttribution for hot path.

    Uses __slots__ for reduced memory footprint and faster attribute access.
    No Pydantic validation overhead.

    Performance notes:
    - metadata: tuple(order_id, is_direct, path) - avoids dict creation overhead
    - matched_slices: list of tuples (slice_id, qty, pnl) - avoids dict creation
    """
    timestamp_ms: int
    event_type: str
    source_trade_id: str
    pair: str
    native_currency: str
    reporting_currency: str
    fx_rate: float

    side: int = 0
    qty: float = 0.0
    price: float = 0.0

    # Tuple format: (order_id, is_direct, path) - more efficient than dict
    metadata: tuple | None = None

    execution_pnl_native: float = 0.0
    execution_pnl_reporting: float = 0.0
    inventory_pnl_native: float = 0.0
    inventory_pnl_reporting: float = 0.0
    hedge_pnl_native: float = 0.0
    hedge_pnl_reporting: float = 0.0
    unrealized_pnl_native: float = 0.0
    unrealized_pnl_reporting: float = 0.0

    # List of tuples: (slice_source_trade_id, matched_qty, pnl)
    matched_slices: list | None = None
    triggered_hedge: bool = False
    hedge_allocation_pct: float = 0.0
    net_position: float = 0.0  # Position after this event


@dataclass(slots=True)
class PnLAttributionRecordInternal:
    """Lightweight version of PnLAttributionRecord for hot path."""
    timestamp_ms: int
    event_type: str
    trade_attributions: list  # list[TradePnLAttributionInternal]
    total_execution_pnl_reporting: float
    total_inventory_pnl_reporting: float
    total_hedge_pnl_reporting: float
    total_unrealized_pnl_reporting: float


def to_pydantic_attribution(attr: TradePnLAttributionInternal):
    """Convert internal attribution to Pydantic model for API serialization.

    Converts tuple formats back to dicts for API compatibility.
    """
    from .state import TradePnLAttribution

    # Convert metadata tuple to dict (order_id, is_direct, path)
    if attr.metadata is not None:
        metadata_dict = {
            "order_id": attr.metadata[0],
            "is_direct": attr.metadata[1],
            "path": attr.metadata[2],
        }
    else:
        metadata_dict = {}

    # Convert matched_slices tuples to dicts
    if attr.matched_slices:
        matched_slices_dicts = [
            {
                "slice_source_trade_id": s[0],
                "matched_qty": s[1],
                "pnl": s[2],
            }
            for s in attr.matched_slices
        ]
    else:
        matched_slices_dicts = []

    return TradePnLAttribution(
        timestamp_ms=attr.timestamp_ms,
        event_type=attr.event_type,
        source_trade_id=attr.source_trade_id,
        pair=attr.pair,
        side=attr.side,
        qty=attr.qty,
        price=attr.price,
        native_currency=attr.native_currency,
        reporting_currency=attr.reporting_currency,
        fx_rate=attr.fx_rate,
        metadata=metadata_dict,
        execution_pnl_native=attr.execution_pnl_native,
        execution_pnl_reporting=attr.execution_pnl_reporting,
        inventory_pnl_native=attr.inventory_pnl_native,
        inventory_pnl_reporting=attr.inventory_pnl_reporting,
        hedge_pnl_native=attr.hedge_pnl_native,
        hedge_pnl_reporting=attr.hedge_pnl_reporting,
        unrealized_pnl_native=attr.unrealized_pnl_native,
        unrealized_pnl_reporting=attr.unrealized_pnl_reporting,
        matched_slices=matched_slices_dicts,
        triggered_hedge=attr.triggered_hedge,
        hedge_allocation_pct=attr.hedge_allocation_pct,
        net_position=attr.net_position,
    )


def to_pydantic_record(record: PnLAttributionRecordInternal):
    """Convert internal record to Pydantic model for API serialization."""
    from .state import PnLAttributionRecord
    return PnLAttributionRecord(
        timestamp_ms=record.timestamp_ms,
        event_type=record.event_type,
        trade_attributions=[to_pydantic_attribution(a) for a in record.trade_attributions],
        total_execution_pnl_reporting=record.total_execution_pnl_reporting,
        total_inventory_pnl_reporting=record.total_inventory_pnl_reporting,
        total_hedge_pnl_reporting=record.total_hedge_pnl_reporting,
        total_unrealized_pnl_reporting=record.total_unrealized_pnl_reporting,
    )


def convert_records_to_pydantic(records: list[PnLAttributionRecordInternal]):
    """Batch convert internal records to Pydantic for API output."""
    return [to_pydantic_record(r) for r in records]
