"""Risk metrics calculation service.

Computes comprehensive risk, ops, and internalization metrics from
completed run data stored in pnl_attribution.parquet.
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from ...core.config.run_config import SimulationConfig
from ...core.data.run_models import (
    AggregatePositionTimeseries,
    AggregatePositionTimeseriesPoint,
    DirectPairInternalization,
    EfficientFrontierScores,
    InternalizationMetrics,
    OpsMetrics,
    PairPositionTimeseries,
    PositionTimeseriesPoint,
    RiskMetrics,
    RunSummary,
)

logger = logging.getLogger(__name__)

# Constants
INTERVAL_MS = 5 * 60 * 1000  # 5 minutes in milliseconds
CVAR_PERCENTILE = 0.05  # Bottom 5% for CVaR


class RiskMetricsCalculator:
    """Calculate risk metrics from completed run data.

    This service reads the pnl_attribution.parquet file and computes:
    - Risk metrics (inventory peaks, drawdown, CVaR)
    - Ops metrics (hedge counts, volume ratios)
    - Internalization metrics (detailed breakdown)
    - Efficient frontier scores (scalar comparison metrics)
    """

    def calculate_all(
        self,
        pnl_path: Path,
        config: SimulationConfig | None = None,
        client_volume: float = 0.0,
        total_pnl: float = 0.0,
        direct_pairs: list[str] | None = None,
    ) -> tuple[RiskMetrics, OpsMetrics, InternalizationMetrics]:
        """Calculate all metrics from parquet file.

        Args:
            pnl_path: Path to pnl_attribution.parquet
            config: Simulation config (for risk band threshold)
            client_volume: Total client volume (for ratios)
            total_pnl: Total PnL (for drawdown percentage)
            direct_pairs: List of direct pairs (e.g., ["EURUSD", "GBPUSD"])

        Returns:
            Tuple of (RiskMetrics, OpsMetrics, InternalizationMetrics)
        """
        if direct_pairs is None:
            direct_pairs = ["EURUSD", "GBPUSD"]

        # Load data
        if not pnl_path.exists():
            logger.warning(f"PnL file not found: {pnl_path}")
            return self._empty_metrics()

        try:
            table = pq.read_table(pnl_path)
            if table.num_rows == 0:
                logger.info("Empty PnL table, returning default metrics")
                return self._empty_metrics()

            data = table.to_pydict()
        except Exception as e:
            logger.exception(f"Error reading PnL file: {e}")
            return self._empty_metrics()

        # Get risk band threshold from config
        risk_band = 1000.0  # Default
        if config and config.hedge_policy_config:
            risk_band = config.hedge_policy_config.get("risk_band_qty", 1000.0)

        # Calculate metrics with progress logging
        print(f"[RISK] Computing risk metrics ({len(data.get('timestamp_ms', []))} events)...", flush=True)
        risk = self._compute_risk_metrics(data, risk_band, total_pnl, direct_pairs)
        print(f"[RISK] Risk metrics done", flush=True)

        print(f"[RISK] Computing ops metrics...", flush=True)
        ops = self._compute_ops_metrics(data, client_volume)
        print(f"[RISK] Ops metrics done", flush=True)

        print(f"[RISK] Computing internalization metrics...", flush=True)
        internalization = self._compute_internalization_metrics(data, direct_pairs)
        print(f"[RISK] Internalization metrics done", flush=True)

        return risk, ops, internalization

    def compute_frontier_scores(
        self,
        summary: RunSummary,
        risk: RiskMetrics,
    ) -> EfficientFrontierScores:
        """Compute scalar scores for efficient frontier analysis.

        Args:
            summary: Run summary with PnL totals
            risk: Computed risk metrics

        Returns:
            EfficientFrontierScores for run comparison
        """
        # PnL per volume in basis points
        client_volume = summary.total_client_volume
        pnl_per_volume_bps = 0.0
        if client_volume > 0:
            pnl_per_volume_bps = (summary.total_pnl / client_volume) * 10000

        # Composite risk score: normalize P99
        # Scale P99 to 0-1 range (assume max of 10000 base units)
        p99_normalized = min(risk.inventory_p99 / 10000.0, 1.0)

        inventory_risk_score = p99_normalized
        # Ensure non-zero for division
        inventory_risk_score = max(inventory_risk_score, 0.001)

        # Risk-adjusted return
        risk_adjusted_return = pnl_per_volume_bps / inventory_risk_score

        return EfficientFrontierScores(
            total_pnl=summary.total_pnl,
            pnl_per_volume_bps=pnl_per_volume_bps,
            max_drawdown_pct=risk.max_drawdown_pct,
            inventory_risk_score=inventory_risk_score,
            risk_adjusted_return=risk_adjusted_return,
        )

    def _compute_risk_metrics(
        self,
        data: dict[str, list],
        risk_band: float,
        total_pnl: float,
        direct_pairs: list[str] | None = None,
    ) -> RiskMetrics:
        """Compute risk metrics from PnL data.

        Args:
            data: Dict of column arrays from parquet
            risk_band: Risk band threshold (unused, kept for API compatibility)
            total_pnl: Total PnL for drawdown percentage
            direct_pairs: List of direct pairs to track (e.g., ["EURUSD", "GBPUSD"])

        Returns:
            RiskMetrics
        """
        if direct_pairs is None:
            direct_pairs = ["EURUSD", "GBPUSD"]

        timestamps = np.array(data.get("timestamp_ms", []))
        if len(timestamps) == 0:
            return self._empty_risk_metrics()

        # Build position timeseries from trade data
        # We need to reconstruct position from fills
        # event_type indicates "client_fill" or "hedge_fill"
        event_types = data.get("event_type", [])
        sides = np.array(data.get("side", []))
        qtys = np.array(data.get("qty", []))
        pairs = data.get("pair", [])
        prices = np.array(data.get("price", [1.0] * len(timestamps)))

        # Track positions per pair (not aggregate raw base currency)
        # This allows proper USD conversion for cross-pair metrics
        pair_positions: dict[str, float] = {pair: 0.0 for pair in direct_pairs}
        pair_rates: dict[str, float] = {pair: 1.0 for pair in direct_pairs}

        # Track seen hedge fills to avoid double-counting
        seen_hedge_fills: set[tuple[int, str]] = set()

        # Build aggregate USD exposure at each event
        # aggregate_usd = sum(|position_pair * fx_rate_pair|) for all pairs
        aggregate_usd_exposures: list[float] = []
        aggregate_timestamps: list[int] = []

        for i in range(len(timestamps)):
            event_type = event_types[i]
            pair = pairs[i] if i < len(pairs) else ""

            # Skip pairs not in direct_pairs
            if pair not in direct_pairs:
                continue

            # Update position for this pair
            if event_type == "client_fill":
                pair_positions[pair] += sides[i] * qtys[i]
            elif event_type == "hedge_fill":
                # Deduplicate hedge fills - only count once per (timestamp, pair)
                hedge_key = (int(timestamps[i]), pair)
                if hedge_key not in seen_hedge_fills:
                    seen_hedge_fills.add(hedge_key)
                    pair_positions[pair] += sides[i] * qtys[i]
            else:
                continue

            # Update last-known rate for this pair (price = mid price for XXX/USD)
            pair_rates[pair] = prices[i] if i < len(prices) else 1.0

            # Compute aggregate USD exposure: sum of |position_pair * fx_rate|
            aggregate_usd = sum(
                abs(pos) * pair_rates[p] for p, pos in pair_positions.items()
            )
            aggregate_usd_exposures.append(aggregate_usd)
            aggregate_timestamps.append(int(timestamps[i]))

        # Build position timeseries per direct pair
        position_timeseries = self._compute_position_timeseries_by_pair(
            timestamps, event_types, sides, qtys, pairs, prices, direct_pairs
        )

        # Inventory metrics on aggregate USD exposures
        abs_positions_usd = np.array(aggregate_usd_exposures) if aggregate_usd_exposures else np.array([0.0])
        max_abs_inventory = float(np.max(abs_positions_usd)) if len(abs_positions_usd) > 0 else 0.0
        inventory_p95 = float(np.percentile(abs_positions_usd, 95)) if len(abs_positions_usd) > 0 else 0.0
        inventory_p99 = float(np.percentile(abs_positions_usd, 99)) if len(abs_positions_usd) > 0 else 0.0

        # Build cumulative PnL timeseries for drawdown
        exec_pnl = np.array(data.get("execution_pnl_reporting", data.get("execution_pnl", [])))
        inv_pnl = np.array(data.get("inventory_pnl_reporting", data.get("inventory_pnl", [])))
        hedge_pnl = np.array(data.get("hedge_pnl_reporting", data.get("hedge_pnl", [])))

        # Handle missing columns gracefully
        if len(exec_pnl) == 0:
            exec_pnl = np.zeros(len(timestamps))
        if len(inv_pnl) == 0:
            inv_pnl = np.zeros(len(timestamps))
        if len(hedge_pnl) == 0:
            hedge_pnl = np.zeros(len(timestamps))

        event_pnl = exec_pnl + inv_pnl + hedge_pnl
        cumulative_pnl = np.cumsum(event_pnl)

        # Drawdown calculation
        max_drawdown, max_drawdown_pct = self._compute_drawdown(cumulative_pnl, total_pnl)

        # Interval risk (5-minute windows)
        worst_interval_pnl, worst_interval_start_ms = self._compute_worst_interval(
            timestamps, cumulative_pnl
        )

        # CVaR 95%
        cvar_95 = self._compute_cvar(timestamps, cumulative_pnl)

        # Build aggregate position timeseries
        aggregate_points = [
            AggregatePositionTimeseriesPoint(
                timestamp_ms=ts,
                total_abs_position_usd=exposure,
            )
            for ts, exposure in zip(aggregate_timestamps, aggregate_usd_exposures)
        ]
        aggregate_position_timeseries = AggregatePositionTimeseries(
            points=aggregate_points,
            max_total_abs_position_usd=max_abs_inventory,
        )

        return RiskMetrics(
            max_abs_inventory=max_abs_inventory,
            inventory_p95=inventory_p95,
            inventory_p99=inventory_p99,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            worst_interval_pnl=worst_interval_pnl,
            worst_interval_start_ms=worst_interval_start_ms,
            cvar_95=cvar_95,
            pair_risk=[],
            position_timeseries=position_timeseries,
            aggregate_position_timeseries=aggregate_position_timeseries,
        )

    def _compute_position_timeseries_by_pair(
        self,
        timestamps: np.ndarray,
        event_types: list,
        sides: np.ndarray,
        qtys: np.ndarray,
        pairs: list,
        prices: np.ndarray,
        direct_pairs: list[str] | None = None,
    ) -> list[PairPositionTimeseries]:
        """Build position timeseries for each direct pair.

        Args:
            timestamps: Array of timestamps
            event_types: List of event types
            sides: Array of sides
            qtys: Array of quantities
            pairs: List of pairs
            prices: Array of mid prices (for position USD valuation)
            direct_pairs: List of direct pairs to track

        Returns:
            List of PairPositionTimeseries
        """
        if direct_pairs is None:
            direct_pairs = ["EURUSD", "GBPUSD"]

        # Track positions per pair
        pair_positions: dict[str, list[PositionTimeseriesPoint]] = {
            pair: [] for pair in direct_pairs
        }
        pair_cum_positions: dict[str, float] = {pair: 0.0 for pair in direct_pairs}

        # Track seen hedge fills to avoid double-counting
        # Key: (timestamp_ms, pair) -> already counted
        seen_hedge_fills: set[tuple[int, str]] = set()

        for i in range(len(timestamps)):
            pair = pairs[i] if i < len(pairs) else ""

            if pair not in direct_pairs:
                continue

            event_type = event_types[i]

            # Only update on fills
            if event_type == "client_fill":
                pair_cum_positions[pair] += sides[i] * qtys[i]
            elif event_type == "hedge_fill":
                # Deduplicate hedge fills - only count once per (timestamp, pair)
                hedge_key = (int(timestamps[i]), pair)
                if hedge_key in seen_hedge_fills:
                    continue
                seen_hedge_fills.add(hedge_key)
                pair_cum_positions[pair] += sides[i] * qtys[i]
            else:
                continue

            # Get mid price for USD conversion (position * mid = USD value)
            price = prices[i] if i < len(prices) else 1.0

            pair_positions[pair].append(
                PositionTimeseriesPoint(
                    timestamp_ms=int(timestamps[i]),
                    position=pair_cum_positions[pair],
                    position_usd=pair_cum_positions[pair] * price,
                )
            )

        # Build result
        result = []
        for pair in direct_pairs:
            points = pair_positions.get(pair, [])
            max_pos = 0.0
            max_pos_usd = 0.0
            if points:
                max_pos = max(abs(p.position) for p in points)
                max_pos_usd = max(abs(p.position_usd) for p in points)

            result.append(
                PairPositionTimeseries(
                    pair=pair,
                    points=points,
                    max_position=max_pos,
                    max_position_usd=max_pos_usd,
                )
            )

        return result

    def _compute_drawdown(
        self, cumulative_pnl: np.ndarray, total_pnl: float
    ) -> tuple[float, float]:
        """Compute maximum drawdown and percentage.

        Args:
            cumulative_pnl: Cumulative PnL array
            total_pnl: Final total PnL

        Returns:
            Tuple of (max_drawdown, max_drawdown_pct)
        """
        if len(cumulative_pnl) == 0:
            return 0.0, 0.0

        # Running maximum
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdowns = running_max - cumulative_pnl
        max_drawdown = float(np.max(drawdowns))

        # Drawdown percentage (relative to peak)
        peak = float(np.max(cumulative_pnl))
        max_drawdown_pct = 0.0
        if peak > 0:
            max_drawdown_pct = (max_drawdown / peak) * 100

        return max_drawdown, max_drawdown_pct

    def _compute_worst_interval(
        self, timestamps: np.ndarray, cumulative_pnl: np.ndarray
    ) -> tuple[float, int]:
        """Compute worst 5-minute interval PnL using O(n) sliding window.

        Args:
            timestamps: Timestamp array (ms)
            cumulative_pnl: Cumulative PnL array

        Returns:
            Tuple of (worst_interval_pnl, start_timestamp_ms)
        """
        if len(timestamps) < 2:
            return 0.0, 0

        worst_pnl = 0.0
        worst_start = int(timestamps[0])

        # Use two-pointer sliding window for O(n) complexity
        end_ptr = 0
        n = len(timestamps)

        for start_ptr in range(n - 1):
            start_ts = timestamps[start_ptr]
            end_ts = start_ts + INTERVAL_MS

            # Move end pointer forward while within interval
            while end_ptr < n and timestamps[end_ptr] <= end_ts:
                end_ptr += 1

            # Calculate interval PnL (end_ptr - 1 is the last point in interval)
            if end_ptr > start_ptr + 1:
                interval_end_idx = end_ptr - 1
                interval_pnl = cumulative_pnl[interval_end_idx] - cumulative_pnl[start_ptr]

                if interval_pnl < worst_pnl:
                    worst_pnl = interval_pnl
                    worst_start = int(start_ts)

        return float(worst_pnl), worst_start

    def _compute_cvar(
        self, timestamps: np.ndarray, cumulative_pnl: np.ndarray
    ) -> float:
        """Compute CVaR 95% from 5-minute interval returns.

        Args:
            timestamps: Timestamp array (ms)
            cumulative_pnl: Cumulative PnL array

        Returns:
            CVaR 95% (average of worst 5% intervals)
        """
        if len(timestamps) < 2:
            return 0.0

        # Compute non-overlapping 5-minute interval returns
        interval_returns = []
        current_interval_start = timestamps[0]
        start_pnl = cumulative_pnl[0]

        for i in range(1, len(timestamps)):
            if timestamps[i] >= current_interval_start + INTERVAL_MS:
                interval_return = cumulative_pnl[i - 1] - start_pnl
                interval_returns.append(interval_return)

                current_interval_start = timestamps[i]
                start_pnl = cumulative_pnl[i]

        if len(interval_returns) == 0:
            # Single interval - use total return
            return float(cumulative_pnl[-1] - cumulative_pnl[0])

        # Sort returns and take average of worst 5%
        sorted_returns = np.sort(interval_returns)
        n_worst = max(1, int(len(sorted_returns) * CVAR_PERCENTILE))
        cvar = float(np.mean(sorted_returns[:n_worst]))

        return cvar

    def _compute_ops_metrics(
        self, data: dict[str, list], client_volume: float
    ) -> OpsMetrics:
        """Compute operational metrics.

        Args:
            data: Dict of column arrays from parquet
            client_volume: Total client volume (fallback, we compute from data)

        Returns:
            OpsMetrics
        """
        event_types = data.get("event_type", [])
        timestamps = data.get("timestamp_ms", [])
        pairs = data.get("pair", [])
        qtys = np.array(data.get("qty", []))

        # Count and sum hedge trades (deduplicated)
        # Each hedge can appear multiple times in the file (attributed to multiple source trades)
        seen_hedges: set[tuple[int, str]] = set()
        hedge_count = 0
        total_hedge_volume = 0.0

        # Also compute client volume directly from data
        computed_client_volume = 0.0

        for i, event_type in enumerate(event_types):
            if event_type == "hedge_fill":
                ts = timestamps[i] if i < len(timestamps) else 0
                pair = pairs[i] if i < len(pairs) else ""
                hedge_key = (int(ts), pair)
                if hedge_key not in seen_hedges:
                    seen_hedges.add(hedge_key)
                    hedge_count += 1
                    total_hedge_volume += qtys[i]
            elif event_type == "client_fill":
                computed_client_volume += qtys[i]

        # Use computed client volume if available, otherwise fall back to parameter
        effective_client_volume = computed_client_volume if computed_client_volume > 0 else client_volume

        # Hedge volume ratio
        hedge_volume_ratio = 0.0
        if effective_client_volume > 0:
            hedge_volume_ratio = total_hedge_volume / effective_client_volume

        # Average hedge size
        avg_hedge_size = 0.0
        if hedge_count > 0:
            avg_hedge_size = total_hedge_volume / hedge_count

        return OpsMetrics(
            hedge_count=hedge_count,
            total_hedge_volume=total_hedge_volume,
            hedge_volume_ratio=hedge_volume_ratio,
            avg_hedge_size=avg_hedge_size,
            total_client_volume=effective_client_volume,
            pair_ops=[],
        )

    def _compute_internalization_metrics(
        self,
        data: dict[str, list],
        direct_pairs: list[str] | None = None,
    ) -> InternalizationMetrics:
        """Compute internalization metrics for direct pairs.

        Args:
            data: Dict of column arrays from parquet
            direct_pairs: List of direct pairs to include

        Returns:
            InternalizationMetrics with values normalized to reporting currency
        """
        if direct_pairs is None:
            direct_pairs = ["EURUSD", "GBPUSD"]

        event_types = data.get("event_type", [])
        timestamps = data.get("timestamp_ms", [])
        qtys = np.array(data.get("qty", []))
        pairs = data.get("pair", [])
        prices = np.array(data.get("price", [1.0] * len(qtys)))

        # Track seen hedge fills to deduplicate
        seen_hedge_fills: set[tuple[int, str]] = set()

        # Aggregate volumes (deduplicated)
        total_client_volume = 0.0
        total_hedge_volume = 0.0
        total_client_volume_usd = 0.0
        total_hedge_volume_usd = 0.0

        for i, event_type in enumerate(event_types):
            pair = pairs[i] if i < len(pairs) else ""
            if pair not in direct_pairs:
                continue

            qty = qtys[i]
            price = prices[i] if i < len(prices) else 1.0
            qty_usd = qty * price

            if event_type == "client_fill":
                total_client_volume += qty
                total_client_volume_usd += qty_usd
            elif event_type == "hedge_fill":
                ts = timestamps[i] if i < len(timestamps) else 0
                hedge_key = (int(ts), pair)
                if hedge_key not in seen_hedge_fills:
                    seen_hedge_fills.add(hedge_key)
                    total_hedge_volume += qty
                    total_hedge_volume_usd += qty_usd

        total_externalized = total_hedge_volume
        total_internalized = max(0.0, total_client_volume - total_hedge_volume)
        total_externalized_usd = total_hedge_volume_usd
        total_internalized_usd = max(0.0, total_client_volume_usd - total_hedge_volume_usd)

        internalization_ratio = 0.0
        if total_client_volume_usd > 0:
            internalization_ratio = total_internalized_usd / total_client_volume_usd

        # Per direct pair breakdown (in reporting currency)
        direct_pair_breakdown = self._compute_direct_pair_internalization(
            pairs, timestamps, event_types, qtys, prices, direct_pairs
        )

        # Legacy per-pair breakdown (in base currency) - skip for simplicity
        pair_breakdown: list[dict[str, Any]] = []

        return InternalizationMetrics(
            total_client_volume_usd=total_client_volume_usd,
            total_internalized_volume_usd=total_internalized_usd,
            total_externalized_volume_usd=total_externalized_usd,
            internalization_ratio=internalization_ratio,
            total_client_volume=total_client_volume,
            total_internalized_volume=total_internalized,
            total_externalized_volume=total_externalized,
            direct_pair_breakdown=direct_pair_breakdown,
            pair_breakdown=pair_breakdown,
        )

    def _compute_direct_pair_internalization(
        self,
        pairs: list,
        timestamps: list,
        event_types: list,
        qtys: np.ndarray,
        prices: np.ndarray,
        direct_pairs: list[str],
    ) -> list[DirectPairInternalization]:
        """Compute internalization for direct pairs in reporting currency.

        Args:
            pairs: List of pair strings
            timestamps: List of timestamps
            event_types: List of event types
            qtys: Quantity array
            prices: Mid prices for USD valuation
            direct_pairs: List of direct pairs to include

        Returns:
            List of DirectPairInternalization for each direct pair
        """
        breakdown = []

        for target_pair in direct_pairs:
            # Track seen hedge fills to deduplicate
            seen_hedge_fills: set[int] = set()
            client_vol_usd = 0.0
            hedge_vol_usd = 0.0

            for i, event_type in enumerate(event_types):
                pair = pairs[i] if i < len(pairs) else ""
                if pair != target_pair:
                    continue

                qty = qtys[i]
                price = prices[i] if i < len(prices) else 1.0
                qty_usd = qty * price

                if event_type == "client_fill":
                    client_vol_usd += qty_usd
                elif event_type == "hedge_fill":
                    ts = timestamps[i] if i < len(timestamps) else 0
                    if int(ts) not in seen_hedge_fills:
                        seen_hedge_fills.add(int(ts))
                        hedge_vol_usd += qty_usd

            externalized_usd = hedge_vol_usd
            internalized_usd = max(0.0, client_vol_usd - hedge_vol_usd)
            ratio = internalized_usd / client_vol_usd if client_vol_usd > 0 else 0.0

            breakdown.append(
                DirectPairInternalization(
                    pair=target_pair,
                    client_volume_usd=client_vol_usd,
                    internalized_volume_usd=internalized_usd,
                    externalized_volume_usd=externalized_usd,
                    internalization_ratio=ratio,
                )
            )

        return breakdown

    def _empty_metrics(
        self,
    ) -> tuple[RiskMetrics, OpsMetrics, InternalizationMetrics]:
        """Return empty metrics for runs with no data."""
        return (
            self._empty_risk_metrics(),
            OpsMetrics(
                hedge_count=0,
                total_hedge_volume=0.0,
                hedge_volume_ratio=0.0,
                avg_hedge_size=0.0,
                total_client_volume=0.0,
            ),
            InternalizationMetrics(
                total_client_volume_usd=0.0,
                total_internalized_volume_usd=0.0,
                total_externalized_volume_usd=0.0,
                internalization_ratio=0.0,
                total_client_volume=0.0,
                total_internalized_volume=0.0,
                total_externalized_volume=0.0,
                direct_pair_breakdown=[],
                pair_breakdown=[],
            ),
        )

    def _empty_risk_metrics(self) -> RiskMetrics:
        """Return empty risk metrics."""
        return RiskMetrics(
            max_abs_inventory=0.0,
            inventory_p95=0.0,
            inventory_p99=0.0,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            worst_interval_pnl=0.0,
            worst_interval_start_ms=0,
            cvar_95=0.0,
            position_timeseries=[],
            aggregate_position_timeseries=AggregatePositionTimeseries(
                points=[],
                max_total_abs_position_usd=0.0,
            ),
        )
