"""In-memory cache for health reports with TTL and version-based invalidation.

Caches computed health reports which are expensive to calculate.
Cache invalidation:
- TTL-based expiry (default 5 minutes)
- Version ID-based invalidation (detects data changes via version hash)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from ..data.market_health import MarketDataHealthReport, TradeBookHealthReport


@dataclass
class HealthCacheEntry:
    """Cache entry for health reports."""

    report: MarketDataHealthReport | TradeBookHealthReport
    cached_at: float
    version_id: str


class HealthCache:
    """In-memory cache for computed health reports.

    Thread-safe cache with TTL-based expiry and version ID invalidation.
    Health reports are keyed by (name, version_id) to ensure stale data
    is never served when the underlying data changes.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default 5 min)
        """
        self.ttl = ttl_seconds
        self._lock = threading.RLock()

        # Health report caches
        self._market_health: dict[str, HealthCacheEntry] = {}
        self._tradebook_health: dict[str, HealthCacheEntry] = {}

    def _is_expired(self, entry: HealthCacheEntry | None) -> bool:
        """Check if a cache entry is expired."""
        if entry is None:
            return True
        return (time.time() - entry.cached_at) > self.ttl

    # --- Market Data Health Cache ---

    def get_market_health(
        self, name: str, version_id: str
    ) -> MarketDataHealthReport | None:
        """Get cached market health report if valid.

        Args:
            name: Dataset name
            version_id: Current version ID of the dataset

        Returns:
            Cached health report, or None if cache miss/invalid/stale
        """
        with self._lock:
            entry = self._market_health.get(name)

            # Check expiry
            if self._is_expired(entry):
                self._market_health.pop(name, None)
                return None

            # Check version match (data hasn't changed)
            if entry.version_id != version_id:
                self._market_health.pop(name, None)
                return None

            return entry.report  # type: ignore

    def set_market_health(
        self, name: str, version_id: str, report: MarketDataHealthReport
    ) -> None:
        """Cache a market health report.

        Args:
            name: Dataset name
            version_id: Version ID of the dataset
            report: Health report to cache
        """
        with self._lock:
            self._market_health[name] = HealthCacheEntry(
                report=report,
                cached_at=time.time(),
                version_id=version_id,
            )

    # --- Tradebook Health Cache ---

    def get_tradebook_health(
        self, name: str, version_id: str
    ) -> TradeBookHealthReport | None:
        """Get cached tradebook health report if valid.

        Args:
            name: Tradebook name
            version_id: Current version ID of the tradebook

        Returns:
            Cached health report, or None if cache miss/invalid/stale
        """
        with self._lock:
            entry = self._tradebook_health.get(name)

            # Check expiry
            if self._is_expired(entry):
                self._tradebook_health.pop(name, None)
                return None

            # Check version match (data hasn't changed)
            if entry.version_id != version_id:
                self._tradebook_health.pop(name, None)
                return None

            return entry.report  # type: ignore

    def set_tradebook_health(
        self, name: str, version_id: str, report: TradeBookHealthReport
    ) -> None:
        """Cache a tradebook health report.

        Args:
            name: Tradebook name
            version_id: Version ID of the tradebook
            report: Health report to cache
        """
        with self._lock:
            self._tradebook_health[name] = HealthCacheEntry(
                report=report,
                cached_at=time.time(),
                version_id=version_id,
            )

    # --- Cache Management ---

    def clear(self) -> None:
        """Clear all caches."""
        with self._lock:
            self._market_health.clear()
            self._tradebook_health.clear()

    def clear_market_health(self, name: str) -> None:
        """Clear cache for a specific dataset's health.

        Args:
            name: Dataset name to clear
        """
        with self._lock:
            self._market_health.pop(name, None)

    def clear_tradebook_health(self, name: str) -> None:
        """Clear cache for a specific tradebook's health.

        Args:
            name: Tradebook name to clear
        """
        with self._lock:
            self._tradebook_health.pop(name, None)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache entry counts and ages
        """
        with self._lock:
            now = time.time()

            market_ages = []
            for entry in self._market_health.values():
                market_ages.append(now - entry.cached_at)

            tradebook_ages = []
            for entry in self._tradebook_health.values():
                tradebook_ages.append(now - entry.cached_at)

            return {
                "market_health_cached": len(self._market_health),
                "tradebook_health_cached": len(self._tradebook_health),
                "market_health_avg_age_s": (
                    sum(market_ages) / len(market_ages) if market_ages else 0
                ),
                "tradebook_health_avg_age_s": (
                    sum(tradebook_ages) / len(tradebook_ages) if tradebook_ages else 0
                ),
            }


# Global singleton instance
_health_cache: HealthCache | None = None
_cache_lock = threading.Lock()


def get_health_cache(ttl_seconds: float = 300.0) -> HealthCache:
    """Get or create the global health cache singleton.

    Args:
        ttl_seconds: TTL for cache entries (only used on first call)

    Returns:
        Global HealthCache instance
    """
    global _health_cache
    with _cache_lock:
        if _health_cache is None:
            _health_cache = HealthCache(ttl_seconds=ttl_seconds)
        return _health_cache
