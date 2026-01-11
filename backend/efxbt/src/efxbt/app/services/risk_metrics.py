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
    EfficientFrontierScores,
    InternalizationMetrics,
    OpsMetrics,
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
    ) -> tuple[RiskMetrics, OpsMetrics, InternalizationMetrics]:
        """Calculate all metrics from parquet file.

        Args:
            pnl_path: Path to pnl_attribution.parquet
            config: Simulation config (for risk band threshold)
            client_volume: Total client volume (for ratios)
            total_pnl: Total PnL (for drawdown percentage)

        Returns:
            Tuple of (RiskMetrics, OpsMetrics, InternalizationMetrics)
        """
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

        # Calculate metrics
        risk = self._compute_risk_metrics(data, risk_band, total_pnl)
        ops = self._compute_ops_metrics(data, client_volume)
        internalization = self._compute_internalization_metrics(data)

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

        # Composite risk score: normalize P99 and time above band
        # Scale P99 to 0-1 range (assume max of 10000 base units)
        p99_normalized = min(risk.inventory_p99 / 10000.0, 1.0)
        time_above_normalized = risk.time_above_risk_band_pct / 100.0

        inventory_risk_score = (p99_normalized + time_above_normalized) / 2
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
    ) -> RiskMetrics:
        """Compute risk metrics from PnL data.

        Args:
            data: Dict of column arrays from parquet
            risk_band: Risk band threshold for time_above calculation
            total_pnl: Total PnL for drawdown percentage

        Returns:
            RiskMetrics
        """
        timestamps = np.array(data.get("timestamp_ms", []))
        if len(timestamps) == 0:
            return self._empty_risk_metrics()

        # Build position timeseries from trade data
        # We need to reconstruct position from fills
        # event_type indicates "client_fill" or "hedge_fill"
        event_types = data.get("event_type", [])
        sides = np.array(data.get("side", []))
        qtys = np.array(data.get("qty", []))

        # Build cumulative position
        positions = []
        cum_position = 0.0
        for i in range(len(timestamps)):
            # Position change = side * qty for all fills
            if event_types[i] in ("client_fill", "hedge_fill"):
                cum_position += sides[i] * qtys[i]
            positions.append(cum_position)

        positions = np.array(positions)
        abs_positions = np.abs(positions)

        # Inventory metrics
        max_abs_inventory = float(np.max(abs_positions)) if len(abs_positions) > 0 else 0.0
        inventory_p95 = float(np.percentile(abs_positions, 95)) if len(abs_positions) > 0 else 0.0
        inventory_p99 = float(np.percentile(abs_positions, 99)) if len(abs_positions) > 0 else 0.0

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

        # Time above risk band
        time_above_pct = self._compute_time_above_band(timestamps, abs_positions, risk_band)

        return RiskMetrics(
            max_abs_inventory=max_abs_inventory,
            inventory_p95=inventory_p95,
            inventory_p99=inventory_p99,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            worst_interval_pnl=worst_interval_pnl,
            worst_interval_start_ms=worst_interval_start_ms,
            time_above_risk_band_pct=time_above_pct,
            cvar_95=cvar_95,
            pair_risk=[],
        )

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
        """Compute worst 5-minute interval PnL.

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

        # For each point, find the PnL change to points within INTERVAL_MS
        for i in range(len(timestamps) - 1):
            start_ts = timestamps[i]
            end_ts = start_ts + INTERVAL_MS

            # Find all points within the interval
            mask = (timestamps > start_ts) & (timestamps <= end_ts)
            if np.any(mask):
                interval_end_idx = np.where(mask)[0][-1]
                interval_pnl = cumulative_pnl[interval_end_idx] - cumulative_pnl[i]

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

    def _compute_time_above_band(
        self, timestamps: np.ndarray, abs_positions: np.ndarray, risk_band: float
    ) -> float:
        """Compute percentage of time position exceeded risk band.

        Args:
            timestamps: Timestamp array (ms)
            abs_positions: Absolute position array
            risk_band: Risk band threshold

        Returns:
            Percentage of time above band (0-100)
        """
        if len(timestamps) < 2:
            return 0.0

        above_band = abs_positions > risk_band

        # Weight by time duration
        time_diffs = np.diff(timestamps)
        total_time = float(np.sum(time_diffs))

        if total_time == 0:
            return 0.0

        # Time above band (using position at start of each interval)
        time_above = float(np.sum(time_diffs[above_band[:-1]]))

        return (time_above / total_time) * 100

    def _compute_ops_metrics(
        self, data: dict[str, list], client_volume: float
    ) -> OpsMetrics:
        """Compute operational metrics.

        Args:
            data: Dict of column arrays from parquet
            client_volume: Total client volume

        Returns:
            OpsMetrics
        """
        event_types = data.get("event_type", [])
        qtys = np.array(data.get("qty", []))

        # Count and sum hedge trades
        hedge_mask = np.array([et == "hedge_fill" for et in event_types])
        hedge_count = int(np.sum(hedge_mask))
        total_hedge_volume = float(np.sum(qtys[hedge_mask])) if hedge_count > 0 else 0.0

        # Hedge volume ratio
        hedge_volume_ratio = 0.0
        if client_volume > 0:
            hedge_volume_ratio = total_hedge_volume / client_volume

        # Average hedge size
        avg_hedge_size = 0.0
        if hedge_count > 0:
            avg_hedge_size = total_hedge_volume / hedge_count

        return OpsMetrics(
            hedge_count=hedge_count,
            total_hedge_volume=total_hedge_volume,
            hedge_volume_ratio=hedge_volume_ratio,
            avg_hedge_size=avg_hedge_size,
            pair_ops=[],
        )

    def _compute_internalization_metrics(
        self, data: dict[str, list]
    ) -> InternalizationMetrics:
        """Compute internalization metrics.

        Args:
            data: Dict of column arrays from parquet

        Returns:
            InternalizationMetrics
        """
        event_types = data.get("event_type", [])
        qtys = np.array(data.get("qty", []))
        pairs = data.get("pair", [])

        # Client and hedge volumes
        client_mask = np.array([et == "client_fill" for et in event_types])
        hedge_mask = np.array([et == "hedge_fill" for et in event_types])

        total_client_volume = float(np.sum(qtys[client_mask]))
        total_hedge_volume = float(np.sum(qtys[hedge_mask]))

        # Externalized = hedged, Internalized = client - hedged
        total_externalized = total_hedge_volume
        total_internalized = max(0.0, total_client_volume - total_hedge_volume)

        internalization_ratio = 0.0
        if total_client_volume > 0:
            internalization_ratio = total_internalized / total_client_volume

        # Per-pair breakdown
        pair_breakdown = self._compute_pair_internalization(
            pairs, event_types, qtys, client_mask, hedge_mask
        )

        return InternalizationMetrics(
            total_client_volume=total_client_volume,
            total_internalized_volume=total_internalized,
            total_externalized_volume=total_externalized,
            internalization_ratio=internalization_ratio,
            pair_breakdown=pair_breakdown,
        )

    def _compute_pair_internalization(
        self,
        pairs: list,
        event_types: list,
        qtys: np.ndarray,
        client_mask: np.ndarray,
        hedge_mask: np.ndarray,
    ) -> list[dict[str, Any]]:
        """Compute per-pair internalization breakdown.

        Args:
            pairs: List of pair strings
            event_types: List of event types
            qtys: Quantity array
            client_mask: Boolean mask for client fills
            hedge_mask: Boolean mask for hedge fills

        Returns:
            List of dicts with per-pair internalization
        """
        unique_pairs = list(set(pairs))
        breakdown = []

        for pair in unique_pairs:
            pair_mask = np.array([p == pair for p in pairs])

            client_vol = float(np.sum(qtys[pair_mask & client_mask]))
            hedge_vol = float(np.sum(qtys[pair_mask & hedge_mask]))

            externalized = hedge_vol
            internalized = max(0.0, client_vol - hedge_vol)
            ratio = internalized / client_vol if client_vol > 0 else 0.0

            breakdown.append({
                "pair": pair,
                "client_volume": client_vol,
                "internalized_volume": internalized,
                "externalized_volume": externalized,
                "internalization_ratio": ratio,
            })

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
            ),
            InternalizationMetrics(
                total_client_volume=0.0,
                total_internalized_volume=0.0,
                total_externalized_volume=0.0,
                internalization_ratio=0.0,
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
            time_above_risk_band_pct=0.0,
            cvar_95=0.0,
        )
