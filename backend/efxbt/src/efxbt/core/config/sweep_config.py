"""Sweep configuration schemas for parameter grid sweeps."""

from enum import Enum
from typing import Annotated, Any, Union

from pydantic import BaseModel, Field, model_validator

from .hedging_config import HedgingRule, HedgingRuleSet, NoHedgeParams


class SweepStatus(str, Enum):
    """Sweep lifecycle states."""

    PENDING = "pending"  # Created, not yet started
    RUNNING = "running"  # Actively executing configs
    COMPLETED = "completed"  # All configs finished successfully
    PARTIAL = "partial"  # Some configs failed
    CANCELLED = "cancelled"  # User cancelled


class ParameterRange(BaseModel):
    """Range-based parameter definition for numeric parameters.

    Expands to a list of values from min to max (inclusive) with given step.
    """

    min: Annotated[float, Field(description="Minimum value (inclusive)")]
    max: Annotated[float, Field(description="Maximum value (inclusive)")]
    step: Annotated[float, Field(gt=0, description="Step size between values")]

    @model_validator(mode="after")
    def validate_range(self) -> "ParameterRange":
        """Ensure min <= max."""
        if self.min > self.max:
            msg = f"min ({self.min}) must be <= max ({self.max})"
            raise ValueError(msg)
        return self

    def expand(self) -> list[float]:
        """Expand range to list of values."""
        values = []
        current = self.min
        # Use tolerance for float comparison
        while current <= self.max + 1e-9:
            # Round to avoid float precision issues
            values.append(round(current, 10))
            current += self.step
        return values


# Union type for parameter specification
# Can be explicit list, range notation, or single value
ParameterSpec = Union[list[Any], ParameterRange]


class SweepParameterGrid(BaseModel):
    """Parameter grid specification for sweep.

    Supports both explicit value lists and range notation.
    All parameters are optional - only specified parameters are swept.

    Example:
        ```python
        SweepParameterGrid(
            hedging_rules_index=[0, 1, 2],  # Sweep over 3 different hedging rule sets
            sample_interval_seconds=ParameterRange(min=30, max=120, step=30),
        )
        ```
    """

    # Hedging rules - index into hedging_rules_presets list
    hedging_rules_index: Annotated[
        list[int] | None,
        Field(
            default=None,
            description="Indices into hedging_rules_presets to sweep (e.g., [0, 1, 2])",
        ),
    ]

    # Hedge delay
    hedge_delay_ms: Annotated[
        ParameterSpec | None,
        Field(
            default=None,
            description="Hedge delay values in milliseconds to sweep",
        ),
    ]

    # Simulation config top-level
    reporting_currency: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Reporting currencies to sweep (e.g., ['USD', 'EUR'])",
        ),
    ]
    sample_interval_seconds: Annotated[
        ParameterSpec | None,
        Field(
            default=None,
            description="Sample interval values to sweep",
        ),
    ]

    # Decross parameters
    max_path_length: Annotated[
        ParameterSpec | None,
        Field(
            default=None,
            description="Max path length values to sweep",
        ),
    ]
    min_leg_qty: Annotated[
        ParameterSpec | None,
        Field(
            default=None,
            description="Min leg quantity values to sweep",
        ),
    ]
    priority_currencies: Annotated[
        list[list[str]] | None,
        Field(
            default=None,
            description="Priority currency orderings to sweep",
        ),
    ]

    def expand_all(self) -> dict[str, list[Any]]:
        """Expand all parameters to lists of values.

        Returns:
            Dict mapping parameter names to lists of values to sweep.
            Only includes parameters that were specified (non-None).
        """
        result: dict[str, list[Any]] = {}

        # Define fields and their types
        param_fields = [
            "hedging_rules_index",
            "hedge_delay_ms",
            "reporting_currency",
            "sample_interval_seconds",
            "max_path_length",
            "min_leg_qty",
            "priority_currencies",
        ]

        for field_name in param_fields:
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = self._expand_spec(value)

        return result

    def _expand_spec(self, spec: ParameterSpec | list[Any]) -> list[Any]:
        """Expand a single parameter spec to a list."""
        if isinstance(spec, ParameterRange):
            return spec.expand()
        elif isinstance(spec, list):
            return spec
        return [spec]

    def get_param_count(self) -> int:
        """Calculate total number of parameter combinations.

        Returns:
            Product of all parameter value counts.
        """
        expanded = self.expand_all()
        if not expanded:
            return 1

        count = 1
        for values in expanded.values():
            count *= len(values)
        return count


class SweepConfig(BaseModel):
    """Configuration for a parameter sweep.

    Combines a base configuration with parameter variations.
    The base configs define fixed parameters, while the parameter_grid
    defines which parameters to sweep and their values.
    """

    # Dataset and tradebook (required)
    dataset: str = Field(
        ...,
        description="Name of the market dataset to use",
        min_length=1,
    )
    tradebook: str = Field(
        ...,
        description="Name of the tradebook to simulate",
        min_length=1,
    )

    # Date range (optional - defaults to full dataset range)
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

    # Hedging rule presets to sweep over
    # Each preset is a complete HedgingRuleSet configuration
    hedging_rules_presets: Annotated[
        list[HedgingRuleSet],
        Field(
            default_factory=lambda: [
                HedgingRuleSet(
                    name="No Hedge",
                    groups=[],
                    rules=[
                        HedgingRule(
                            pair_or_group="ALL",
                            from_amount=0,
                            to_amount=float("inf"),
                            action=NoHedgeParams(),
                        )
                    ],
                )
            ],
            description="List of hedging rule configurations to sweep over",
        ),
    ]

    # Base simulation config (fixed parameters not being swept)
    # hedging_rules will be filled from hedging_rules_presets based on index
    base_simulation_config: Annotated[
        dict[str, Any],
        Field(
            default_factory=lambda: {
                "reporting_currency": "USD",
                "sample_interval_seconds": 60,
                "hedge_delay_ms": 0,
            },
            description="Base simulation configuration (hedging_rules comes from presets)",
        ),
    ]

    # Base decross config (fixed parameters not being swept)
    base_decross_config: Annotated[
        dict[str, Any],
        Field(
            default_factory=lambda: {
                "priority_currencies": ["USD", "EUR", "GBP", "JPY"],
                "max_path_length": 4,
                "min_leg_qty": 0.01,
                "use_banker_rounding": True,
            },
            description="Base decross configuration (overridden by sweep parameters)",
        ),
    ]

    # Base general config
    base_general_config: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            description="Base general configuration",
        ),
    ]

    # Parameter grid (what varies)
    parameter_grid: SweepParameterGrid = Field(
        default_factory=lambda: SweepParameterGrid(),  # type: ignore[call-arg]
        description="Parameters to sweep over",
    )

    # Sweep metadata
    name: str | None = Field(
        default=None,
        description="Optional human-readable sweep name",
    )
    description: str | None = Field(
        default=None,
        description="Optional sweep description",
    )

    @model_validator(mode="after")
    def validate_hedging_rules_indices(self) -> "SweepConfig":
        """Validate that hedging_rules_index values are valid."""
        if self.parameter_grid.hedging_rules_index:
            max_idx = len(self.hedging_rules_presets) - 1
            for idx in self.parameter_grid.hedging_rules_index:
                if idx < 0 or idx > max_idx:
                    raise ValueError(
                        f"hedging_rules_index {idx} is out of range "
                        f"(0-{max_idx} for {len(self.hedging_rules_presets)} presets)"
                    )
        return self

    def get_total_configs(self) -> int:
        """Get total number of configurations in the sweep."""
        return self.parameter_grid.get_param_count()
