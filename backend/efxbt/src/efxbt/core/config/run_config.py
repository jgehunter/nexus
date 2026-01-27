"""Run configuration schema for backtesting runs."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .hedging_config import HedgingRuleSet

# Canonical direct pairs - pairs that typically have market data and can be hedged externally
DEFAULT_DIRECT_PAIRS = [
    "EURUSD", "EURCHF", "EURCZK", "EURDKK", "EURHUF", "EURNOK", "EURPLN", "EURRON", "EURSEK",
    "USDJPY", "GBPUSD", "USDCAD", "AUDUSD", "NZDUSD", "USDAED", "USDCNH", "USDHKD",
    "USDILS", "USDMXN", "USDQAR", "USDSAR", "USDSGD", "USDTHB", "USDTRY", "USDZAR", "USDCLP",
]


class RunStatus(str, Enum):
    """Run lifecycle states."""

    CREATED = "created"  # Config validated, ready to start
    RUNNING = "running"  # Actively executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Error during execution
    CANCELLED = "cancelled"  # User requested cancellation


class DecrossConfig(BaseModel):
    """Configuration for trade decrossing pipeline.

    Controls pathfinding behavior and decomposition parameters for
    converting cross-pair trades into direct-pair legs.
    """

    priority_currencies: Annotated[
        list[str],
        Field(
            default=["USD", "EUR", "GBP", "JPY"],
            description="Currency priority for path selection (higher priority = earlier in list)",
        ),
    ]
    max_path_length: Annotated[
        int,
        Field(
            default=4,
            ge=2,
            description="Maximum number of currencies in decomposition path (4 allows 3-leg decomposition)",
        ),
    ]
    use_banker_rounding: Annotated[
        bool,
        Field(
            default=True,
            description="Use banker's rounding (round-half-to-even) for deterministic quantity rounding",
        ),
    ]
    min_leg_qty: Annotated[
        float,
        Field(
            default=0.01,
            gt=0,
            description="Minimum quantity for a leg; filter out legs with qty < this value",
        ),
    ]


class SimulationConfig(BaseModel):
    """Configuration for simulation engine.

    Controls hedge policies, sampling behavior, and execution models for
    the shard-based simulation engine.
    """

    # Market dataset (referenced from RunConfig.dataset)
    dataset: str = Field(
        ...,
        description="Name of market dataset to use for simulation",
        min_length=1,
    )

    # Reporting currency for PnL normalization
    reporting_currency: Annotated[
        str,
        Field(
            default="USD",
            description="Currency for PnL reporting and aggregation (e.g., 'USD', 'EUR')",
            min_length=3,
            max_length=3,
        ),
    ]

    # Rule-based hedging configuration
    hedging_rules: HedgingRuleSet = Field(
        ...,
        description="Rule-based hedging configuration with groups and rules",
    )

    # Sampling grid
    sample_interval_seconds: Annotated[
        int,
        Field(
            default=60,
            gt=0,
            description="Interval between sampling points for unrealized PnL (seconds)",
        ),
    ]

    # Execution model
    use_mid_for_unrealized: Annotated[
        bool,
        Field(
            default=True,
            description="Use mid price for unrealized PnL calculations",
        ),
    ]

    # Hedge execution delay
    hedge_delay_ms: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Delay in milliseconds before hedge execution (0 = immediate)",
        ),
    ]


class GeneralConfig(BaseModel):
    """General configuration that applies across all runs.

    Contains settings like which pairs are considered "direct" pairs
    (can be hedged externally) vs cross pairs (need decomposition).
    """

    direct_pairs: Annotated[
        list[str],
        Field(
            default_factory=lambda: DEFAULT_DIRECT_PAIRS.copy(),
            description="Currency pairs that can be hedged externally (direct pairs)",
        ),
    ]


class RunConfig(BaseModel):
    """Configuration for a single backtest run.

    Extended in Phase 3 to include simulation engine settings for
    hedge policies, risk parameters, and PnL attribution.
    """

    # Dataset selection (required - provides market data)
    dataset: str = Field(
        ...,
        description="Name of the market dataset to use",
        min_length=1,
    )

    # Tradebook selection (required - provides trades to simulate)
    tradebook: str = Field(
        ...,
        description="Name of the tradebook to simulate",
        min_length=1,
    )

    # Date range
    start_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Start date (YYYY-MM-DD), defaults to dataset start",
    )
    end_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="End date (YYYY-MM-DD), defaults to dataset end",
    )

    # Simulation mode (placeholder for future phases)
    mode: Literal["backtest", "replay"] = Field(
        default="backtest",
        description="Simulation mode",
    )

    # Decrossing configuration (always enabled when tradebook is specified)
    decross_config: DecrossConfig = Field(
        default_factory=DecrossConfig,
        description="Configuration for decrossing pipeline",
    )

    # General configuration
    general_config: GeneralConfig = Field(
        default_factory=GeneralConfig,
        description="General configuration (direct pairs, etc.)",
    )

    # Simulation configuration (Phase 3)
    simulation_config: SimulationConfig | None = Field(
        default=None,
        description="Configuration for simulation engine (Phase 3); defaults to dataset if None",
    )

    # Run metadata
    name: str | None = Field(
        default=None,
        description="Optional human-readable run name",
    )
    description: str | None = Field(
        default=None,
        description="Optional run description",
    )
