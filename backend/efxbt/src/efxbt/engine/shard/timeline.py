"""Decision timeline construction for simulation events.

Builds ordered timeline combining client fills, hedge executions, and sampling points
with proper priority handling for simultaneous events.
"""

from pydantic import BaseModel

from ...core.config.run_config import SimulationConfig
from ...core.data.schemas import DecrossedTradeRecord


class TimelinePoint(BaseModel):
    """Single point on the decision timeline.

    Represents a moment in time when the simulation engine needs to make a decision
    or update state. Events include client fills, hedge executions, and sampling points.

    Attributes:
        timestamp_ms: Event timestamp (milliseconds)
        event_type: Type of event ("client_fill", "hedge_fill", "sample")
        client_trade: Client trade if event_type is "client_fill"
        hedge_trade: Hedge trade dict if event_type is "hedge_fill"
    """

    timestamp_ms: int
    event_type: str  # "client_fill", "hedge_fill", "sample"

    # Event-specific data
    client_trade: DecrossedTradeRecord | None = None
    hedge_trade: dict | None = None


def build_timeline(
    client_trades: list[DecrossedTradeRecord],
    config: SimulationConfig,
) -> list[TimelinePoint]:
    """Build decision timeline combining all event types.

    Creates a sorted, deduplicated timeline that merges:
    1. Client trade timestamps (highest priority at same timestamp)
    2. Periodic sampling grid for unrealized PnL snapshots

    Hedge fills are added dynamically during simulation, not at timeline construction.

    Args:
        client_trades: List of client trades to process
        config: Simulation configuration (includes sample_interval_seconds)

    Returns:
        Sorted list of TimelinePoint objects

    Example:
        >>> config = SimulationConfig(sample_interval_seconds=60)
        >>> trades = [
        ...     DecrossedTradeRecord(timestamp_ms=1000, ...),
        ...     DecrossedTradeRecord(timestamp_ms=5000, ...),
        ... ]
        >>> timeline = build_timeline(trades, config)
        >>> # Timeline contains client fills at 1000, 5000
        >>> # Plus samples at 1000, 2000, 3000, 4000, 5000
    """
    timeline_points: list[TimelinePoint] = []

    # Step 1: Add client fill events
    for trade in client_trades:
        timeline_points.append(
            TimelinePoint(
                timestamp_ms=trade.timestamp_ms,
                event_type="client_fill",
                client_trade=trade,
            )
        )

    # Step 2: Add sampling grid (if we have trades)
    if client_trades:
        start_ms = min(t.timestamp_ms for t in client_trades)
        end_ms = max(t.timestamp_ms for t in client_trades)

        sample_interval_ms = config.sample_interval_seconds * 1000
        current_ms = start_ms

        while current_ms <= end_ms:
            timeline_points.append(
                TimelinePoint(
                    timestamp_ms=current_ms,
                    event_type="sample",
                )
            )
            current_ms += sample_interval_ms

    # Step 3: Sort by timestamp, then by event priority
    # Priority order ensures correct processing when events share a timestamp:
    # 1. client_fill (highest - must process trade first)
    # 2. hedge_fill (second - process hedges after client fills)
    # 3. sample (lowest - snapshot after all trades processed)
    event_priority = {
        "client_fill": 0,
        "hedge_fill": 1,
        "sample": 2,
    }

    timeline_points.sort(key=lambda p: (p.timestamp_ms, event_priority[p.event_type]))

    # Step 4: Deduplicate sampling points that coincide with fills
    # Keep fills, remove samples at same timestamp
    deduplicated: list[TimelinePoint] = []
    seen_timestamps: set[int] = set()

    for point in timeline_points:
        if point.event_type == "sample":
            # Only add sample if no fill event at this timestamp
            if point.timestamp_ms not in seen_timestamps:
                deduplicated.append(point)
                seen_timestamps.add(point.timestamp_ms)
        else:
            # Always add fill events
            deduplicated.append(point)
            seen_timestamps.add(point.timestamp_ms)

    return deduplicated
