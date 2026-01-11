"""Test new health analyzers with separated data."""

from pathlib import Path

from efxbt.core.data.registry import MarketDatasetRegistry, TradeBookRegistry
from efxbt.core.data.health_new import (
    MarketDataHealthAnalyzer,
    TradeBookHealthAnalyzer,
)


def test_market_health():
    """Test market data health analyzer."""
    print("\n" + "=" * 60)
    print("Testing Market Data Health Analyzer")
    print("=" * 60)

    data_dir = Path("c:/Users/jgehu/QUANT/Projects/nexus/data")
    registry = MarketDatasetRegistry(data_dir)

    dataset_names = registry.list_datasets()
    print(f"\nFound {len(dataset_names)} market datasets")

    for name in dataset_names:
        inv = registry.discover_dataset(name)
        print(f"\n📊 Dataset: {inv.name}")
        print(f"   Version ID: {inv.version_id}")
        print(f"   Pairs: {sorted(inv.pairs)}")
        print(f"   Files: {inv.total_files}")
        print(f"   Ticks: {inv.total_ticks}")

        # Analyze health
        analyzer = MarketDataHealthAnalyzer(inv)
        report = analyzer.compute_health_report(validate_schemas=True)

        print(f"\n   Health Report:")
        print(f"   - Has Issues: {report.has_issues}")
        print(f"   - Total Ticks: {report.summary['total_ticks']}")
        print(f"   - Pairs Covered: {report.summary['pairs_covered']}")
        print(f"   - Gaps > 1min: {report.summary['gaps_over_1min']}")
        print(f"   - Gaps > 5min: {report.summary['gaps_over_5min']}")
        print(f"   - Gaps > 15min: {report.summary['gaps_over_15min']}")
        print(f"   - Schema Issues: {report.summary['total_schema_issues']}")

        if report.has_issues:
            print("\n   ⚠️ ISSUES DETECTED:")
            if report.summary["gaps_over_5min"] > 0:
                print(f"      - {report.summary['gaps_over_5min']} gaps over 5 minutes")
            if report.summary["total_schema_issues"] > 0:
                print(f"      - {report.summary['total_schema_issues']} schema issues")

        # Show per-pair details
        print("\n   Per-Pair Coverage:")
        for tc in report.tick_coverage:
            if tc.has_data:
                print(
                    f"      {tc.pair} ({tc.date}): {tc.tick_count} ticks, "
                    f"{tc.gaps_over_5min} gaps > 5min"
                )


def test_tradebook_health():
    """Test trade book health analyzer."""
    print("\n" + "=" * 60)
    print("Testing Trade Book Health Analyzer")
    print("=" * 60)

    data_dir = Path("c:/Users/jgehu/QUANT/Projects/nexus/data")
    registry = TradeBookRegistry(data_dir)

    book_names = registry.list_tradebooks()
    print(f"\nFound {len(book_names)} trade books")

    for name in book_names:
        inv = registry.discover_tradebook(name)
        print(f"\n📕 Trade Book: {inv.name}")
        print(f"   Version ID: {inv.version_id}")
        print(f"   Pairs: {sorted(inv.pairs)}")
        print(f"   Files: {inv.total_files}")
        print(f"   Trades: {inv.total_trades}")
        print(f"   Volume: {inv.total_volume:.2f}")

        # Analyze health
        analyzer = TradeBookHealthAnalyzer(inv)
        report = analyzer.compute_health_report(validate_schemas=True)

        print(f"\n   Health Report:")
        print(f"   - Has Issues: {report.has_issues}")
        print(f"   - Total Trades: {report.summary['total_trades']}")
        print(f"   - Total Volume: {report.summary['total_volume']:.2f}")
        print(f"   - Pairs Traded: {report.summary['pairs_traded']}")
        print(f"   - Schema Issues: {report.summary['total_schema_issues']}")

        if report.has_issues:
            print("\n   ⚠️ ISSUES DETECTED:")
            if report.summary["total_schema_issues"] > 0:
                print(f"      - {report.summary['total_schema_issues']} schema issues")

        # Show per-pair details
        print("\n   Per-Pair Stats:")
        for ts in report.trade_stats:
            if ts.has_data:
                print(
                    f"      {ts.pair} ({ts.date}): {ts.trade_count} trades, "
                    f"vol={ts.total_volume:.2f}, avg={ts.avg_trade_size:.2f}"
                )


if __name__ == "__main__":
    test_market_health()
    test_tradebook_health()
    print("\n✅ All health analyzers working correctly!\n")
