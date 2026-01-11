"""Multi-shard simulation coordination and metrics.

This package orchestrates simulation across multiple (date, pair) shards,
chains state across dates, and calculates cross-shard metrics.
"""

from .metrics import MetricsCalculator
from .simulator import MultiShardSimulator, SimulationResult

__all__ = [
    "MultiShardSimulator",
    "SimulationResult",
    "MetricsCalculator",
]
