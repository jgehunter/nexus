"""Run configuration schema for backtesting runs."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


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
            default=3,
            ge=2,
            description="Maximum number of currencies in decomposition path",
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
    the shard-based simulation engine (Phase 3).
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

    # Hedge policy
    hedge_policy: Annotated[
        str,
        Field(
            default="aggressive",
            description="Hedge policy name: 'aggressive', 'passive', etc.",
        ),
    ]
    hedge_policy_config: Annotated[
        dict,
        Field(
            default_factory=lambda: {
                "risk_band_qty": 1000.0,
                "hedge_mode": "full",
            },
            description="Policy-specific configuration dict",
        ),
    ]

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


class RunConfig(BaseModel):
    """Configuration for a single backtest run.

    Extended in Phase 3 to include simulation engine settings for
    hedge policies, risk parameters, and PnL attribution.
    """

    # Dataset selection
    dataset: str = Field(
        ...,
        description="Name of the dataset to use",
        min_length=1,
    )
    pairs: list[str] = Field(
        default_factory=list,
        description="Currency pairs to include (empty = all pairs in dataset)",
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

    # Decrossing configuration
    enable_decrossing: bool = Field(
        default=True,
        description="Enable automatic trade decrossing in pipeline",
    )
    decross_config: DecrossConfig = Field(
        default_factory=DecrossConfig,
        description="Configuration for decrossing pipeline",
    )
    tradebook: str | None = Field(
        default=None,
        description="Name of the tradebook to decross (if enable_decrossing=True)",
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
