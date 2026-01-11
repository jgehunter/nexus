"""Test script for Phase 1: Dataset Registry and Health Diagnostics.

This script demonstrates:
1. Dataset discovery
2. Pair/date inventory
3. Version ID computation
4. Health metrics and tick coverage
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend" / "efxbt" / "src"
sys.path.insert(0, str(backend_path))

from rich.console import Console
from rich.table import Table

from efxbt.core.data.health import DataHealthAnalyzer
from efxbt.core.data.registry import DatasetRegistry


def main() -> None:
    """Run Phase 1 demonstration."""
    console = Console()

    # Get data root
    data_root = Path(__file__).parent.parent / "data"

    if not data_root.exists():
        console.print("[red]Error: Data directory does not exist.")
        console.print(f"[yellow]Please run create_sample_dataset.py first.")
        return

    console.print(
        "[bold cyan]Phase 1: Dataset Registry and Health Diagnostics[/bold cyan]\n"
    )

    # Initialize registry
    registry = DatasetRegistry(data_root)

    # 1. List datasets
    console.print("[bold]1. Discovering datasets...[/bold]")
    datasets = registry.list_datasets()

    if not datasets:
        console.print("[yellow]No datasets found.")
        console.print(
            "[yellow]Run scripts/create_sample_dataset.py to create a sample dataset."
        )
        return

    console.print(f"Found {len(datasets)} dataset(s): {', '.join(datasets)}\n")

    # 2. Get detailed inventory for first dataset
    dataset_name = datasets[0]
    console.print(f"[bold]2. Analyzing dataset: {dataset_name}[/bold]")

    inventory = registry.discover_dataset(dataset_name)

    # Display inventory summary
    table = Table(title=f"Dataset: {dataset_name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version ID", inventory.version_id)
    table.add_row("Root Path", str(inventory.root_path))
    table.add_row("Total Pairs", str(len(inventory.pairs)))
    table.add_row("Total Dates", str(len(inventory.dates)))
    table.add_row("Trade Files", str(inventory.total_trades_files))
    table.add_row("Market Files", str(inventory.total_market_files))

    console.print(table)
    console.print()

    # Display pairs
    console.print(f"[bold]Pairs:[/bold] {', '.join(inventory.pairs)}")
    console.print(
        f"[bold]Dates:[/bold] {', '.join(inventory.dates[:5])}"
        + (f"... (+{len(inventory.dates)-5} more)" if len(inventory.dates) > 5 else "")
    )
    console.print()

    # Display trade books
    if inventory.trades_pairs:
        console.print(
            f"[bold]Trade Books:[/bold] {', '.join(inventory.trades_pairs[:10])}"
        )
        console.print()

    # 3. Pair-date inventory
    console.print(f"[bold]3. Pair-Date Inventory (first 10 entries)[/bold]")

    inventory_table = Table()
    inventory_table.add_column("Pair", style="cyan")
    inventory_table.add_column("Date", style="yellow")
    inventory_table.add_column("Trades", style="green")
    inventory_table.add_column("Market", style="green")
    inventory_table.add_column("Trade Rows", justify="right")
    inventory_table.add_column("Market Rows", justify="right")

    for pd in inventory.pair_dates[:10]:
        inventory_table.add_row(
            pd.pair,
            pd.date,
            "✓" if pd.has_trades else "✗",
            "✓" if pd.has_market else "✗",
            str(pd.trades_row_count) if pd.has_trades else "-",
            str(pd.market_row_count) if pd.has_market else "-",
        )

    console.print(inventory_table)
    console.print()

    # 4. Health report
    console.print("[bold]4. Computing health report...[/bold]")

    analyzer = DataHealthAnalyzer(inventory)
    report = analyzer.compute_health_report(validate_schemas=True)

    # Summary
    summary_table = Table(title="Health Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right", style="green")

    summary_table.add_row("Total Tick Files", str(report.summary["total_tick_files"]))
    summary_table.add_row("Total Trade Files", str(report.summary["total_trade_files"]))
    summary_table.add_row("Total Ticks", f"{report.summary['total_ticks']:,}")
    summary_table.add_row("Total Trades", f"{report.summary['total_trades']:,}")
    summary_table.add_row("Total Volume", f"{report.summary['total_volume']:,.0f}")
    summary_table.add_row("Gaps > 1 min", str(report.summary["gaps_over_1min"]))
    summary_table.add_row("Gaps > 5 min", str(report.summary["gaps_over_5min"]))
    summary_table.add_row("Gaps > 15 min", str(report.summary["gaps_over_15min"]))
    summary_table.add_row("Schema Issues", str(report.summary["total_schema_issues"]))

    console.print(summary_table)
    console.print()

    # Tick coverage details (first 5)
    if report.tick_coverage:
        console.print("[bold]5. Tick Coverage (first 5 pair-dates)[/bold]")

        tick_table = Table()
        tick_table.add_column("Pair", style="cyan")
        tick_table.add_column("Date", style="yellow")
        tick_table.add_column("Tick Count", justify="right")
        tick_table.add_column("Duration", justify="right")
        tick_table.add_column("Avg Gap (ms)", justify="right")
        tick_table.add_column("Max Gap (ms)", justify="right")

        for tc in report.tick_coverage[:5]:
            if tc.has_data:
                duration_h = (tc.duration_ms / 3600000) if tc.duration_ms else 0
                tick_table.add_row(
                    tc.pair,
                    tc.date,
                    f"{tc.tick_count:,}",
                    f"{duration_h:.1f}h",
                    f"{tc.avg_gap_ms:.0f}" if tc.avg_gap_ms else "-",
                    f"{tc.max_gap_ms:,}" if tc.max_gap_ms else "-",
                )

        console.print(tick_table)
        console.print()

    # Trade coverage details (first 5)
    if report.trade_coverage:
        console.print("[bold]6. Trade Coverage (first 5 pair-dates)[/bold]")

        trade_table = Table()
        trade_table.add_column("Pair", style="cyan")
        trade_table.add_column("Date", style="yellow")
        trade_table.add_column("Trade Count", justify="right")
        trade_table.add_column("Total Volume", justify="right")
        trade_table.add_column("Avg Trade Size", justify="right")

        for tc in report.trade_coverage[:5]:
            if tc.has_data:
                trade_table.add_row(
                    tc.pair,
                    tc.date,
                    f"{tc.trade_count:,}",
                    f"{tc.total_volume:,.0f}",
                    f"{tc.avg_trade_size:,.0f}",
                )

        console.print(trade_table)
        console.print()

    # Schema validation results
    if report.schema_validations:
        invalid = [v for v in report.schema_validations if not v.is_valid]
        if invalid:
            console.print(f"[bold red]Schema Issues Found: {len(invalid)}[/bold red]")
            for v in invalid[:3]:
                console.print(f"  [red]✗[/red] {v.file_path.name}")
                if v.missing_fields:
                    console.print(f"    Missing fields: {', '.join(v.missing_fields)}")
                if v.extra_fields:
                    console.print(f"    Extra fields: {', '.join(v.extra_fields)}")
        else:
            console.print("[bold green]✓ All schemas valid[/bold green]")

    console.print("\n[bold cyan]Phase 1 Complete![/bold cyan]")


if __name__ == "__main__":
    main()
