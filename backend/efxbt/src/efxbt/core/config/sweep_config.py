"""Sweep configuration schemas for parameter grid sweeps."""

from enum import Enum
from typing import Annotated, Any, Union

from pydantic import BaseModel, Field, model_validator


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
            risk_band_qty=ParameterRange(min=1e6, max=10e6, step=3e6),
            hedge_mode=["full", "partial"],
        )
        ```
    """

    # Simulation parameters (hedge_policy_config)
    risk_band_qty: Annotated[
        ParameterSpec | None,
        Field(
            default=None,
            description="Risk band quantity values to sweep (hedge_policy_config.risk_band_qty)",
        ),
    ]
    hedge_mode: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Hedge mode values to sweep (hedge_policy_config.hedge_mode)",
        ),
    ]

    # Simulation config top-level
    hedge_policy: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Hedge policy names to sweep (e.g., ['aggressive', 'passive'])",
        ),
    ]
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
            "risk_band_qty",
            "hedge_mode",
            "hedge_policy",
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

    # Base simulation config (fixed parameters not being swept)
    base_simulation_config: Annotated[
        dict[str, Any],
        Field(
            default_factory=lambda: {
                "hedge_policy": "aggressive",
                "hedge_policy_config": {"risk_band_qty": 1000.0, "hedge_mode": "full"},
                "reporting_currency": "USD",
                "sample_interval_seconds": 60,
            },
            description="Base simulation configuration (overridden by sweep parameters)",
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

    def get_total_configs(self) -> int:
        """Get total number of configurations in the sweep."""
        return self.parameter_grid.get_param_count()
