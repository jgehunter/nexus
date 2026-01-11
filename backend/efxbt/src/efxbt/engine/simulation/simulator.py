"""Multi-shard simulation coordinator with state chaining.

Orchestrates simulation across multiple (date, pair) shards, chains state
across dates for continuity, and aggregates results.
"""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from ...core.config.run_config import SimulationConfig
from ...core.data.schemas import DecrossedTradeRecord
from ..shard.shard_engine import ShardEngine, ShardResult
from ..shard.state import PnLAttributionRecord, ShardState
from .metrics import MetricsCalculator


class SimulationResult(BaseModel):
    """Aggregated results from multi-shard simulation."""

    # Summary statistics
    total_shards: int = 0
    pairs: list[str] = Field(default_factory=list)
    date_range: tuple[str, str] | None = None

    # Aggregate PnL (reporting currency)
    total_execution_pnl: float = 0.0
    total_inventory_pnl: float = 0.0
    total_hedge_pnl: float = 0.0
    total_pnl: float = 0.0

    # Aggregate metrics
    total_client_volume: float = 0.0
    total_internalized_volume: float = 0.0
    total_externalized_volume: float = 0.0
    overall_internalization_ratio: float = 0.0

    # Per-shard results
    shard_results: list[dict] = Field(
        default_factory=list,
        description="List of {pair, date, pnl_breakdown, metrics} dicts",
    )

    # Output paths
    output_dir: Path | None = None
    pnl_attribution_path: Path | None = None


class MultiShardSimulator:
    """Coordinates simulation across multiple shards (pairs × dates)."""

    def __init__(self, config: SimulationConfig, data_root: Path):
        """Initialize multi-shard simulator.

        Args:
            config: Simulation configuration
            data_root: Root directory for market data
        """
        self.config = config
        self.data_root = data_root
        self.metrics_calculator = MetricsCalculator()

    def run(
        self,
        decrossed_data_dir: Path,
        output_dir: Path,
    ) -> SimulationResult:
        """Run simulation across all shards.

        Discovers (date, pair) partitions from decrossed output, chains state
        by pair across dates, and aggregates results.

        Args:
            decrossed_data_dir: Directory with decrossed trades (partitioned by date/pair)
            output_dir: Directory to write simulation results

        Returns:
            SimulationResult with aggregated metrics and per-shard details

        Algorithm:
            1. Discover all (date, pair) shards from decrossed output
            2. Group shards by pair for state continuity
            3. Run shards sequentially per pair (day N final_state → day N+1 prior_state)
            4. Aggregate results across all shards
            5. Write PnL attribution records to parquet

        Example:
            >>> config = SimulationConfig(dataset="btec", hedge_policy="aggressive", ...)
            >>> simulator = MultiShardSimulator(config, data_root)
            >>> result = simulator.run(
            ...     decrossed_data_dir=Path("results/run123/decrossed"),
            ...     output_dir=Path("results/run123/simulation"),
            ... )
            >>> result.total_pnl
            12345.67  # Total PnL in reporting currency
            >>> result.overall_internalization_ratio
            0.7234  # 72.34% of volume internalized
        """
        # Step 1: Discover shards (date, pair partitions)
        shards = self._discover_shards(decrossed_data_dir)

        if not shards:
            # No shards to simulate
            return SimulationResult(output_dir=output_dir)

        # Step 2: Group by pair for state continuity
        shards_by_pair = {}
        for shard in shards:
            pair = shard["pair"]
            if pair not in shards_by_pair:
                shards_by_pair[pair] = []
            shards_by_pair[pair].append(shard)

        # Step 3: Run shards sequentially per pair (maintain state)
        all_results: list[ShardResult] = []
        all_pnl_records: list[PnLAttributionRecord] = []

        for pair, pair_shards in shards_by_pair.items():
            # Sort by date for chronological processing
            pair_shards.sort(key=lambda s: s["date"])

            prior_state: ShardState | None = None

            for shard_info in pair_shards:
                # Load client trades for this shard
                client_trades = self._load_shard_trades(shard_info["file_path"])

                # Create shard engine
                engine = ShardEngine(
                    pair=pair,
                    date=shard_info["date"],
                    config=self.config,
                    data_root=self.data_root,
                )

                # Run simulation with prior state
                result = engine.run(client_trades, prior_state)

                # Collect results
                all_results.append(result)
                all_pnl_records.extend(result.pnl_records)

                # Chain state to next day
                prior_state = result.final_state

        # Step 4: Aggregate results
        aggregated = self._aggregate_results(all_results)
        aggregated.output_dir = output_dir

        # Step 5: Write results
        self._write_results(all_pnl_records, output_dir)
        aggregated.pnl_attribution_path = output_dir / "pnl_attribution.parquet"

        return aggregated

    def _discover_shards(self, decrossed_data_dir: Path) -> list[dict]:
        """Discover all (date, pair) shards from decrossed output.

        Args:
            decrossed_data_dir: Directory with structure {YYYYMMDD}/{PAIR}.parquet

        Returns:
            List of shard info dicts:
            [{"pair": "EURUSD", "date": "20240101", "file_path": Path(...)}, ...]

        Example directory structure:
            decrossed_data_dir/
                20240101/
                    EURUSD.parquet
                    GBPUSD.parquet
                20240102/
                    EURUSD.parquet
                    GBPUSD.parquet
        """
        shards = []

        if not decrossed_data_dir.exists():
            return shards

        for date_dir in decrossed_data_dir.iterdir():
            if not date_dir.is_dir():
                continue

            date_str = date_dir.name

            for pair_file in date_dir.glob("*.parquet"):
                pair = pair_file.stem

                shards.append(
                    {
                        "pair": pair,
                        "date": date_str,
                        "file_path": pair_file,
                    }
                )

        return shards

    def _load_shard_trades(self, file_path: Path) -> list[DecrossedTradeRecord]:
        """Load decrossed trades for a single shard.

        Args:
            file_path: Path to decrossed trades parquet file

        Returns:
            List of DecrossedTradeRecord objects
        """
        table = pq.read_table(file_path)
        records = []

        for batch in table.to_batches():
            for row in batch.to_pylist():
                records.append(DecrossedTradeRecord(**row))

        return records

    def _aggregate_results(self, all_results: list[ShardResult]) -> SimulationResult:
        """Aggregate metrics and PnL across all shards.

        Args:
            all_results: List of ShardResult objects from all shards

        Returns:
            SimulationResult with aggregated metrics
        """
        if not all_results:
            return SimulationResult()

        # Extract unique pairs and date range
        pairs = sorted(set(r.pair for r in all_results))
        dates = sorted(r.date for r in all_results)
        date_range = (dates[0], dates[-1])

        # Aggregate PnL (reporting currency) - metrics are flat, not nested
        total_exec_pnl = sum(
            r.metrics.get("execution_pnl_reporting", 0.0) for r in all_results
        )
        total_inv_pnl = sum(
            r.metrics.get("inventory_pnl_reporting", 0.0) for r in all_results
        )
        total_hedge_pnl = sum(
            r.metrics.get("hedge_pnl_reporting", 0.0) for r in all_results
        )

        # Aggregate volume metrics - metrics are flat, not nested
        total_client_volume = sum(
            r.metrics.get("total_client_volume", 0.0) for r in all_results
        )
        total_internalized = sum(
            r.metrics.get("internalized_volume", 0.0) for r in all_results
        )
        total_externalized = sum(
            r.metrics.get("externalized_volume", 0.0) for r in all_results
        )

        # Build per-shard summary - include full metrics (flat structure)
        shard_results = [
            {
                "pair": r.pair,
                "date": r.date,
                **r.metrics,  # Spread all flat metrics into shard result
            }
            for r in all_results
        ]

        return SimulationResult(
            total_shards=len(all_results),
            pairs=pairs,
            date_range=date_range,
            total_execution_pnl=total_exec_pnl,
            total_inventory_pnl=total_inv_pnl,
            total_hedge_pnl=total_hedge_pnl,
            total_pnl=total_exec_pnl + total_inv_pnl + total_hedge_pnl,
            total_client_volume=total_client_volume,
            total_internalized_volume=total_internalized,
            total_externalized_volume=total_externalized,
            overall_internalization_ratio=(
                total_internalized / total_client_volume
                if total_client_volume > 0
                else 0.0
            ),
            shard_results=shard_results,
        )

    def _write_results(
        self, all_pnl_records: list[PnLAttributionRecord], output_dir: Path
    ) -> None:
        """Write PnL attribution records to parquet.

        Args:
            all_pnl_records: All PnL attribution records from all shards
            output_dir: Directory to write results

        Writes:
            output_dir/pnl_attribution.parquet - All trade-level PnL attributions
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if not all_pnl_records:
            # Write empty file
            empty_table = pa.table({})
            pq.write_table(empty_table, output_dir / "pnl_attribution.parquet")
            return

        # Flatten PnL attribution records to rows
        rows = []
        for record in all_pnl_records:
            for trade_attr in record.trade_attributions:
                rows.append(
                    {
                        "timestamp_ms": trade_attr.timestamp_ms,
                        "event_type": trade_attr.event_type,
                        "source_trade_id": trade_attr.source_trade_id,
                        "pair": trade_attr.pair,
                        "native_currency": trade_attr.native_currency,
                        "reporting_currency": trade_attr.reporting_currency,
                        "fx_rate": trade_attr.fx_rate,
                        "execution_pnl_native": trade_attr.execution_pnl_native,
                        "inventory_pnl_native": trade_attr.inventory_pnl_native,
                        "hedge_pnl_native": trade_attr.hedge_pnl_native,
                        "unrealized_pnl_native": trade_attr.unrealized_pnl_native,
                        "execution_pnl_reporting": trade_attr.execution_pnl_reporting,
                        "inventory_pnl_reporting": trade_attr.inventory_pnl_reporting,
                        "hedge_pnl_reporting": trade_attr.hedge_pnl_reporting,
                        "unrealized_pnl_reporting": trade_attr.unrealized_pnl_reporting,
                        "triggered_hedge": trade_attr.triggered_hedge,
                        "hedge_allocation_pct": trade_attr.hedge_allocation_pct,
                        # Metadata fields (extensible)
                        "order_id": trade_attr.metadata.get("order_id"),
                        "is_direct": trade_attr.metadata.get("is_direct"),
                        "path": trade_attr.metadata.get("path"),
                    }
                )

        # Create PyArrow table
        table = pa.Table.from_pylist(rows)

        # Write to parquet with compression
        pq.write_table(
            table,
            output_dir / "pnl_attribution.parquet",
            compression="snappy",
        )
