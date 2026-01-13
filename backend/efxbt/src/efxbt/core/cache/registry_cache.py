"""In-memory cache for registry discovery with TTL and mtime invalidation.

Caches:
- Dataset/tradebook name lists
- Individual inventory objects

Cache invalidation:
- TTL-based expiry (default 60 seconds)
- Directory mtime-based invalidation (detects file changes)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from ..data.registry import MarketDatasetInventory, TradeBookInventory

T = TypeVar("T")


@dataclass
class CacheEntry:
    """Generic cache entry with TTL and mtime tracking."""

    value: object
    cached_at: float
    dir_mtime: float | None = None


class RegistryCache:
    """In-memory cache for registry discovery operations.

    Thread-safe cache with TTL-based expiry and optional mtime invalidation.
    """

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.ttl = ttl_seconds
        self._lock = threading.RLock()

        # Dataset caches
        self._dataset_list: CacheEntry | None = None
        self._dataset_inventories: dict[str, CacheEntry] = {}

        # Tradebook caches
        self._tradebook_list: CacheEntry | None = None
        self._tradebook_inventories: dict[str, CacheEntry] = {}

    def _is_expired(self, entry: CacheEntry | None) -> bool:
        """Check if a cache entry is expired."""
        if entry is None:
            return True
        return (time.time() - entry.cached_at) > self.ttl

    def _get_dir_mtime(self, directory: Path) -> float | None:
        """Get directory modification time for invalidation."""
        try:
            return directory.stat().st_mtime
        except (OSError, FileNotFoundError):
            return None

    def _is_mtime_valid(self, entry: CacheEntry, directory: Path) -> bool:
        """Check if cached mtime matches current directory mtime."""
        if entry.dir_mtime is None:
            return True  # No mtime tracking for this entry
        current_mtime = self._get_dir_mtime(directory)
        return current_mtime == entry.dir_mtime

    # --- Dataset List Cache ---

    def get_dataset_list(self, datasets_dir: Path) -> list[str] | None:
        """Get cached dataset list if valid.

        Args:
            datasets_dir: Directory containing datasets

        Returns:
            Cached list of dataset names, or None if cache miss/invalid
        """
        with self._lock:
            if self._is_expired(self._dataset_list):
                return None
            if not self._is_mtime_valid(self._dataset_list, datasets_dir):
                self._dataset_list = None
                return None
            return self._dataset_list.value  # type: ignore

    def set_dataset_list(self, datasets_dir: Path, names: list[str]) -> None:
        """Cache the dataset list.

        Args:
            datasets_dir: Directory containing datasets
            names: List of dataset names to cache
        """
        with self._lock:
            self._dataset_list = CacheEntry(
                value=names,
                cached_at=time.time(),
                dir_mtime=self._get_dir_mtime(datasets_dir),
            )

    # --- Dataset Inventory Cache ---

    def get_dataset_inventory(self, name: str) -> MarketDatasetInventory | None:
        """Get cached dataset inventory if valid.

        Args:
            name: Dataset name

        Returns:
            Cached inventory, or None if cache miss/invalid
        """
        with self._lock:
            entry = self._dataset_inventories.get(name)
            if self._is_expired(entry):
                self._dataset_inventories.pop(name, None)
                return None
            return entry.value  # type: ignore

    def set_dataset_inventory(
        self, name: str, inventory: MarketDatasetInventory
    ) -> None:
        """Cache a dataset inventory.

        Args:
            name: Dataset name
            inventory: Inventory to cache
        """
        with self._lock:
            self._dataset_inventories[name] = CacheEntry(
                value=inventory,
                cached_at=time.time(),
                dir_mtime=self._get_dir_mtime(inventory.root_path),
            )

    # --- Tradebook List Cache ---

    def get_tradebook_list(self, tradebooks_dir: Path) -> list[str] | None:
        """Get cached tradebook list if valid.

        Args:
            tradebooks_dir: Directory containing tradebooks

        Returns:
            Cached list of tradebook names, or None if cache miss/invalid
        """
        with self._lock:
            if self._is_expired(self._tradebook_list):
                return None
            if not self._is_mtime_valid(self._tradebook_list, tradebooks_dir):
                self._tradebook_list = None
                return None
            return self._tradebook_list.value  # type: ignore

    def set_tradebook_list(self, tradebooks_dir: Path, names: list[str]) -> None:
        """Cache the tradebook list.

        Args:
            tradebooks_dir: Directory containing tradebooks
            names: List of tradebook names to cache
        """
        with self._lock:
            self._tradebook_list = CacheEntry(
                value=names,
                cached_at=time.time(),
                dir_mtime=self._get_dir_mtime(tradebooks_dir),
            )

    # --- Tradebook Inventory Cache ---

    def get_tradebook_inventory(self, name: str) -> TradeBookInventory | None:
        """Get cached tradebook inventory if valid.

        Args:
            name: Tradebook name

        Returns:
            Cached inventory, or None if cache miss/invalid
        """
        with self._lock:
            entry = self._tradebook_inventories.get(name)
            if self._is_expired(entry):
                self._tradebook_inventories.pop(name, None)
                return None
            return entry.value  # type: ignore

    def set_tradebook_inventory(
        self, name: str, inventory: TradeBookInventory
    ) -> None:
        """Cache a tradebook inventory.

        Args:
            name: Tradebook name
            inventory: Inventory to cache
        """
        with self._lock:
            self._tradebook_inventories[name] = CacheEntry(
                value=inventory,
                cached_at=time.time(),
                dir_mtime=self._get_dir_mtime(inventory.root_path),
            )

    # --- Cache Management ---

    def clear(self) -> None:
        """Clear all caches."""
        with self._lock:
            self._dataset_list = None
            self._dataset_inventories.clear()
            self._tradebook_list = None
            self._tradebook_inventories.clear()

    def clear_dataset(self, name: str) -> None:
        """Clear cache for a specific dataset.

        Args:
            name: Dataset name to clear
        """
        with self._lock:
            self._dataset_inventories.pop(name, None)
            # Also invalidate the list since it may have changed
            self._dataset_list = None

    def clear_tradebook(self, name: str) -> None:
        """Clear cache for a specific tradebook.

        Args:
            name: Tradebook name to clear
        """
        with self._lock:
            self._tradebook_inventories.pop(name, None)
            # Also invalidate the list since it may have changed
            self._tradebook_list = None

    def stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache entry counts
        """
        with self._lock:
            return {
                "dataset_list_cached": 1 if self._dataset_list else 0,
                "dataset_inventories_cached": len(self._dataset_inventories),
                "tradebook_list_cached": 1 if self._tradebook_list else 0,
                "tradebook_inventories_cached": len(self._tradebook_inventories),
            }


# Global singleton instance
_registry_cache: RegistryCache | None = None
_cache_lock = threading.Lock()


def get_registry_cache(ttl_seconds: float = 60.0) -> RegistryCache:
    """Get or create the global registry cache singleton.

    Args:
        ttl_seconds: TTL for cache entries (only used on first call)

    Returns:
        Global RegistryCache instance
    """
    global _registry_cache
    with _cache_lock:
        if _registry_cache is None:
            _registry_cache = RegistryCache(ttl_seconds=ttl_seconds)
        return _registry_cache
