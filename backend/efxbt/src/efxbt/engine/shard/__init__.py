"""Shard-level simulation components.

This package contains the core simulation engine for individual (date, pair) shards,
including FIFO matching, PnL calculation, hedge policies, and state management.
"""

from .fifo_matcher import FIFOMatcher, MatchResult
from .fx_converter import FXConverter
from .hedge_policy import AggressiveHedgePolicy, HedgePolicy, create_hedge_policy
from .market_fetcher import MarketSnapshot, MarketSnapshotFetcher
from .pnl_calculator import PnLCalculator, calculate_hedge_cost
from .state import (
    FIFOSlice,
    PnLAttributionRecord,
    ShardState,
    TradePnLAttribution,
)
from .timeline import TimelinePoint, build_timeline

__all__ = [
    # State schemas
    "FIFOSlice",
    "ShardState",
    "TradePnLAttribution",
    "PnLAttributionRecord",
    # Timeline
    "TimelinePoint",
    "build_timeline",
    # Market data
    "MarketSnapshot",
    "MarketSnapshotFetcher",
    # FIFO matching
    "FIFOMatcher",
    "MatchResult",
    # PnL calculation
    "PnLCalculator",
    "calculate_hedge_cost",
    # FX conversion
    "FXConverter",
    # Hedge policies
    "HedgePolicy",
    "AggressiveHedgePolicy",
    "create_hedge_policy",
]
