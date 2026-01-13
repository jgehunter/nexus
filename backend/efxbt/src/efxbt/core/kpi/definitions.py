"""KPI definitions registry for manager-grade reporting.

Each KPI is documented with:
- id: Unique identifier matching field names
- name: Human-readable display name
- category: Grouping (pnl, risk, ops, internalization)
- description: Plain-English explanation for non-technical users
- formula: Mathematical formula (optional)
- unit: Unit of measurement
- interpretation: Whether higher/lower is better, or neutral
"""

from ..data.run_models import KPIDefinition


# -----------------------------------------------------------------------------
# PnL Metrics
# -----------------------------------------------------------------------------

_PNL_KPIS = [
    KPIDefinition(
        id="total_pnl",
        name="Total PnL",
        category="pnl",
        description="The overall profit or loss from all trading activity, including execution spread capture, inventory carrying costs, and hedging expenses.",
        formula="total_pnl = execution_pnl + inventory_pnl + hedge_pnl",
        unit="USD",
        interpretation="higher_better",
    ),
    KPIDefinition(
        id="total_execution_pnl",
        name="Execution PnL",
        category="pnl",
        description="Profit from the spread between client fill prices and market mid-price at execution time. Positive when filling clients at favorable prices.",
        formula="sum((fill_price - mid_price) * quantity * side)",
        unit="USD",
        interpretation="higher_better",
    ),
    KPIDefinition(
        id="total_inventory_pnl",
        name="Inventory PnL",
        category="pnl",
        description="Profit or loss from holding inventory as the market moves. Positive when prices move favorably before positions are closed.",
        formula="sum((close_mid - open_mid) * quantity * side)",
        unit="USD",
        interpretation="higher_better",
    ),
    KPIDefinition(
        id="total_hedge_pnl",
        name="Hedge Cost",
        category="pnl",
        description="Cost of hedging excess inventory by crossing the spread in the market. Always negative - represents the cost of risk reduction.",
        formula="sum(-spread/2 * hedge_quantity)",
        unit="USD",
        interpretation="higher_better",
    ),
]


# -----------------------------------------------------------------------------
# Risk Metrics
# -----------------------------------------------------------------------------

_RISK_KPIS = [
    KPIDefinition(
        id="max_abs_inventory",
        name="Peak Position",
        category="risk",
        description="The largest aggregate absolute position (in USD) held at any point during the simulation, computed as the sum of absolute USD-converted positions across all direct pairs.",
        formula="max(sum(|position_pair * fx_rate_pair|)) across all timestamps",
        unit="USD",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="inventory_p95",
        name="Position P95",
        category="risk",
        description="The 95th percentile of aggregate absolute position (in USD). The total USD exposure was below this level 95% of the time.",
        formula="percentile(sum(|position * rate|), 95)",
        unit="USD",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="inventory_p99",
        name="Position P99",
        category="risk",
        description="The 99th percentile of aggregate absolute position (in USD). Captures tail risk from extreme total exposure.",
        formula="percentile(sum(|position * rate|), 99)",
        unit="USD",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="max_drawdown",
        name="Max Drawdown",
        category="risk",
        description="The largest peak-to-trough decline in cumulative PnL. Measures the worst loss from a high point.",
        formula="max(peak_pnl - trough_pnl) where trough follows peak",
        unit="USD",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="max_drawdown_pct",
        name="Max Drawdown %",
        category="risk",
        description="Maximum drawdown expressed as a percentage of the peak PnL. Useful for comparing runs with different PnL scales.",
        formula="max_drawdown / peak_pnl * 100",
        unit="%",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="worst_interval_pnl",
        name="Worst 5-Min PnL",
        category="risk",
        description="The worst PnL change over any 5-minute interval. Captures short-term loss potential.",
        formula="min(pnl_change) over rolling 5-minute windows",
        unit="USD",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="cvar_95",
        name="CVaR 95%",
        category="risk",
        description="Conditional Value at Risk - the average loss in the worst 5% of 5-minute intervals. A tail risk measure.",
        formula="mean(worst 5% of interval_pnl)",
        unit="USD",
        interpretation="lower_better",
    ),
]


# -----------------------------------------------------------------------------
# Operations Metrics
# -----------------------------------------------------------------------------

_OPS_KPIS = [
    KPIDefinition(
        id="hedge_count",
        name="Hedge Count",
        category="ops",
        description="Total number of hedge trades executed to manage inventory risk.",
        formula="count(hedge_trades)",
        unit="trades",
        interpretation="neutral",
    ),
    KPIDefinition(
        id="total_hedge_volume",
        name="Hedge Volume",
        category="ops",
        description="Total volume of all hedge trades executed.",
        formula="sum(hedge_quantities)",
        unit="Base CCY",
        interpretation="neutral",
    ),
    KPIDefinition(
        id="hedge_volume_ratio",
        name="Hedge Ratio",
        category="ops",
        description="Ratio of hedge volume to client volume. Lower values indicate more internalization and less external hedging.",
        formula="hedge_volume / client_volume",
        unit="ratio",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="avg_hedge_size",
        name="Avg Hedge Size",
        category="ops",
        description="Average size of hedge trades. Larger hedges may have higher market impact.",
        formula="total_hedge_volume / hedge_count",
        unit="Base CCY",
        interpretation="neutral",
    ),
]


# -----------------------------------------------------------------------------
# Internalization Metrics
# -----------------------------------------------------------------------------

_INTERNALIZATION_KPIS = [
    KPIDefinition(
        id="total_client_volume",
        name="Client Volume",
        category="internalization",
        description="Total volume of all client trades processed.",
        formula="sum(client_trade_quantities)",
        unit="Base CCY",
        interpretation="neutral",
    ),
    KPIDefinition(
        id="total_internalized_volume",
        name="Internalized Volume",
        category="internalization",
        description="Volume matched between opposing client trades without external hedging.",
        formula="volume matched client-to-client",
        unit="Base CCY",
        interpretation="higher_better",
    ),
    KPIDefinition(
        id="total_externalized_volume",
        name="Externalized Volume",
        category="internalization",
        description="Volume covered by hedging to the external market.",
        formula="total_client_volume - internalized_volume",
        unit="Base CCY",
        interpretation="neutral",
    ),
    KPIDefinition(
        id="internalization_ratio",
        name="Internalization %",
        category="internalization",
        description="Percentage of client volume internalized. Higher internalization typically means lower hedging costs.",
        formula="internalized_volume / client_volume * 100",
        unit="%",
        interpretation="neutral",
    ),
]


# -----------------------------------------------------------------------------
# Efficient Frontier Scores
# -----------------------------------------------------------------------------

_FRONTIER_KPIS = [
    KPIDefinition(
        id="pnl_per_volume_bps",
        name="PnL per Volume",
        category="frontier",
        description="PnL earned per unit of client volume, expressed in basis points. Key metric for comparing run efficiency.",
        formula="total_pnl / client_volume * 10000",
        unit="bps",
        interpretation="higher_better",
    ),
    KPIDefinition(
        id="inventory_risk_score",
        name="Risk Score",
        category="frontier",
        description="Normalized risk score from P99 inventory. Used for efficient frontier analysis.",
        formula="normalized(p99)",
        unit="score",
        interpretation="lower_better",
    ),
    KPIDefinition(
        id="risk_adjusted_return",
        name="Risk-Adjusted Return",
        category="frontier",
        description="PnL per volume divided by risk score. Higher values indicate better risk-adjusted performance.",
        formula="pnl_per_volume_bps / inventory_risk_score",
        unit="ratio",
        interpretation="higher_better",
    ),
]


# -----------------------------------------------------------------------------
# Combined Registry
# -----------------------------------------------------------------------------

KPI_REGISTRY: list[KPIDefinition] = (
    _PNL_KPIS + _RISK_KPIS + _OPS_KPIS + _INTERNALIZATION_KPIS + _FRONTIER_KPIS
)


def get_kpi_definition(kpi_id: str) -> KPIDefinition | None:
    """Get a KPI definition by ID.

    Args:
        kpi_id: The unique KPI identifier

    Returns:
        KPIDefinition if found, None otherwise
    """
    for kpi in KPI_REGISTRY:
        if kpi.id == kpi_id:
            return kpi
    return None


def get_kpis_by_category(category: str) -> list[KPIDefinition]:
    """Get all KPIs in a category.

    Args:
        category: Category name (pnl, risk, ops, internalization, frontier)

    Returns:
        List of KPIDefinitions in that category
    """
    return [kpi for kpi in KPI_REGISTRY if kpi.category == category]
