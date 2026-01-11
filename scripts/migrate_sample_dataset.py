"""Migrate sample dataset to new architecture.

Separates market data (datasets/) from trade books (tradebooks/).
"""

import shutil
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend" / "efxbt" / "src"
sys.path.insert(0, str(backend_path))


def migrate_sample_dataset(data_root: Path) -> None:
    """Migrate sample_efx_2024 to new architecture.

    Args:
        data_root: Root data directory
    """
    old_dataset = data_root / "datasets" / "sample_efx_2024"

    if not old_dataset.exists():
        print("Sample dataset not found. Nothing to migrate.")
        return

    print("Migrating sample_efx_2024 to new architecture...")
    print(f"Source: {old_dataset}")

    # Step 1: Create new directory structure
    new_dataset = data_root / "datasets" / "sample_efx_2024_market"
    tradebooks_dir = data_root / "tradebooks"

    new_dataset.mkdir(parents=True, exist_ok=True)
    tradebooks_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Move market data (keep in datasets)
    old_market = old_dataset / "market"
    new_market = new_dataset / "market"

    if old_market.exists():
        print(f"\n1. Moving market data to {new_market}")
        if new_market.exists():
            shutil.rmtree(new_market)
        shutil.copytree(old_market, new_market)
        print(f"   ✓ Market data copied to {new_market}")

    # Step 3: Split trade books (move to tradebooks/)
    old_trades = old_dataset / "trades"

    if old_trades.exists():
        print(f"\n2. Splitting trade books to {tradebooks_dir}")

        for book_dir in old_trades.iterdir():
            if not book_dir.is_dir() or book_dir.name.startswith("."):
                continue

            book_name = book_dir.name
            new_book_dir = tradebooks_dir / book_name

            print(f"   - Creating trade book: {book_name}")
            new_book_dir.mkdir(parents=True, exist_ok=True)

            # Copy parquet files directly to book root (flatten structure)
            for pq_file in book_dir.glob("*.parquet"):
                dest = new_book_dir / pq_file.name
                shutil.copy2(pq_file, dest)
                print(f"     ✓ {pq_file.name}")

    # Step 4: Keep old dataset for compatibility
    print(f"\n3. Keeping old dataset at {old_dataset} for backward compatibility")

    print(f"\n✓ Migration complete!")
    print(f"\nNew structure:")
    print(f"  - Market data: {new_dataset}")
    print(f"  - Trade books: {tradebooks_dir}")
    print(f"  - Legacy (unchanged): {old_dataset}")


if __name__ == "__main__":
    data_root = Path(__file__).parent.parent / "data"
    migrate_sample_dataset(data_root)
