"""Caching module for performance optimization.

Provides in-memory caching with TTL and invalidation for:
- Registry discovery (dataset/tradebook lists and inventories)
- Health reports (computed health analysis results)
"""

from .health_cache import HealthCache, get_health_cache
from .registry_cache import RegistryCache, get_registry_cache

__all__ = ["RegistryCache", "HealthCache", "get_registry_cache", "get_health_cache", "clear_all_caches"]


def clear_all_caches() -> None:
    """Clear all global caches.

    Useful for testing to ensure test isolation.
    """
    get_registry_cache().clear()
    get_health_cache().clear()
