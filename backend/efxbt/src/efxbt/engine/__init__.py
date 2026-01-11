"""Simulation engine components for FX backtesting.

This package contains the core simulation engines:
- Decrossing engine: Decomposes cross-pair trades into direct legs
- Shard engine: Per-(date, pair) simulation with FIFO matching and PnL attribution
- Multi-shard simulator: Coordinates simulation across multiple shards with state chaining
"""

from .decrosser import DecrossingEngine
from .shard.shard_engine import ShardEngine
from .simulation.simulator import MultiShardSimulator

__all__ = [
    "DecrossingEngine",
    "ShardEngine",
    "MultiShardSimulator",
]
