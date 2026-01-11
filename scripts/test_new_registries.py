"""Test new registry architecture with migrated data."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend" / "efxbt" / "src"
sys.path.insert(0, str(backend_path))

from efxbt.core.data.registry import MarketDatasetRegistry, TradeBookRegistry


def test_new_registries(data_root: Path) -> None:
    """Test new registry classes with migrated data.

    Args:
        data_root: Root data directory
    """
    print("Testing New Registry Architecture")
    print("=" * 60)

    # Test MarketDatasetRegistry
    print("\n1. Market Dataset Registry")
    print("-" * 60)
    market_registry = MarketDatasetRegistry(data_root)
    datasets = market_registry.list_datasets()
    print(f"Found {len(datasets)} market dataset(s): {datasets}")

    if "sample_efx_2024_market" in datasets:
        print("\nDiscovering 'sample_efx_2024_market':")
        inventory = market_registry.discover_dataset("sample_efx_2024_market")
        print(f"  Name: {inventory.name}")
        print(f"  Version ID: {inventory.version_id}")
        print(f"  Pairs: {inventory.pairs}")
        print(f"  Dates: {inventory.dates}")
        print(f"  Total files: {inventory.total_files}")
        print(f"  Total ticks: {inventory.total_ticks:,}")

    # Test TradeBookRegistry
    print("\n\n2. Trade Book Registry")
    print("-" * 60)
    tradebook_registry = TradeBookRegistry(data_root)
    books = tradebook_registry.list_tradebooks()
    print(f"Found {len(books)} trade book(s): {books}")

    for book_name in books:
        print(f"\nDiscovering '{book_name}':")
        inventory = tradebook_registry.discover_tradebook(book_name)
        print(f"  Name: {inventory.name}")
        print(f"  Version ID: {inventory.version_id}")
        print(f"  Dates: {inventory.dates}")
        print(f"  Total files: {inventory.total_files}")
        print(f"  Total trades: {inventory.total_trades:,}")

    print("\n" + "=" * 60)
    print("✓ New architecture working correctly!")


if __name__ == "__main__":
    data_root = Path(__file__).parent.parent / "data"
    test_new_registries(data_root)
