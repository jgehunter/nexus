"""Service layer for parameter sweep operations.

Provides business logic for creating, starting, and analyzing parameter sweeps.

Sweep execution creates individual runs for each parameter combination,
with full idempotence support via config hash.
"""

import itertools
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.config.run_config import (
    DecrossConfig,
    GeneralConfig,
    RunConfig,
    RunStatus,
    SimulationConfig,
)
from ...core.config.sweep_config import SweepConfig, SweepStatus
from ...core.data.run_registry import RunRegistry, compute_config_hash
from ...core.data.sweep_models import (
    BestConfigsResponse,
    FrontierConfig,
    FrontierConstraint,
    FrontierTableResponse,
    SweepCreateResponse,
    SweepDetailResponse,
    SweepListItem,
    SweepListResponse,
    SweepStatusResponse,
)
from ...core.data.sweep_registry import (
    InvalidSweepStateError,
    SweepNotFoundError,
    SweepRegistry,
)
from ...util.time import now_ms

if TYPE_CHECKING:
    from .runs import RunService

logger = logging.getLogger(__name__)


class SweepService:
    """Service for parameter sweep operations.

    Follows the service pattern established by RunService.
    """

    def __init__(
        self,
        data_root: Path,
        results_root: Path,
        run_service: "RunService",
        max_parallel_runs: int = 2,
    ) -> None:
        """Initialize service.

        Args:
            data_root: Root directory for market/trade data
            results_root: Root directory for results storage
            run_service: Run service instance for creating/executing runs
            max_parallel_runs: Max concurrent run executions in a sweep
        """
        self.data_root = Path(data_root)
        self.results_root = Path(results_root)
        self.sweep_registry = SweepRegistry(results_root)
        self.run_registry = RunRegistry(results_root)
        self.run_service = run_service
        self.max_parallel_runs = max_parallel_runs

        # ThreadPoolExecutor for background sweep execution
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="sweep_exec"
        )

    def create_sweep(self, config: SweepConfig) -> SweepCreateResponse:
        """Validate config and create sweep record.

        Does NOT start execution. Call start_sweep() to begin.

        Args:
            config: Sweep configuration

        Returns:
            SweepCreateResponse with sweep_id and config count

        Raises:
            ValidationError: If config validation fails
        """
        # Validate dataset and tradebook exist
        from .runs import ValidationError

        try:
            from .datasets import DatasetsService
            from .tradebooks import TradeBooksService

            datasets = DatasetsService(self.data_root)
            tradebooks = TradeBooksService(self.data_root)

            datasets.get_dataset(config.dataset)
            tradebooks.get_tradebook(config.tradebook)
        except FileNotFoundError as e:
            raise ValidationError(str(e))

        # Create sweep record
        sweep = self.sweep_registry.create_sweep(config)

        return SweepCreateResponse(
            sweep_id=sweep.sweep_id,
            status=sweep.status,
            config_hash=sweep.config_hash,
            total_configs=sweep.total_configs,
            message=f"Created sweep with {sweep.total_configs} configurations",
        )

    def start_sweep(self, sweep_id: str) -> SweepStatusResponse:
        """Start sweep execution in background thread.

        Returns immediately after submitting to executor.

        Args:
            sweep_id: Sweep identifier

        Returns:
            SweepStatusResponse with initial RUNNING status

        Raises:
            SweepNotFoundError: If sweep doesn't exist
            InvalidSweepStateError: If sweep not in PENDING status
        """
        sweep = self.sweep_registry.get_sweep(sweep_id)

        if sweep.status != SweepStatus.PENDING:
            raise InvalidSweepStateError(
                sweep_id, sweep.status, "Can only start sweeps in PENDING status"
            )

        # Update status to RUNNING
        self.sweep_registry.update_status(
            sweep_id, SweepStatus.RUNNING, started_at_ms=now_ms()
        )

        # Submit execution to background thread
        logger.info(f"Submitting sweep {sweep_id} to background executor")
        self._executor.submit(self._execute_sweep, sweep_id)

        return self.get_status(sweep_id)

    def _execute_sweep(self, sweep_id: str) -> None:
        """Execute all configs in sweep (background thread).

        Args:
            sweep_id: Sweep identifier
        """
        try:
            sweep = self.sweep_registry.get_sweep(sweep_id)
            expanded_configs = self._expand_parameter_grid(sweep.config)

            completed = 0
            failed = 0
            skipped = 0

            for i, (run_config, params) in enumerate(expanded_configs):
                try:
                    # Check idempotence - does this config already exist?
                    config_hash = compute_config_hash(run_config)
                    existing = self.run_registry.find_existing_run(config_hash)

                    if existing and existing.status == RunStatus.COMPLETED:
                        # Reuse existing completed run
                        self.sweep_registry.add_member_run(sweep_id, existing.run_id)
                        skipped += 1
                        logger.info(
                            f"Sweep {sweep_id}: Reusing existing run {existing.run_id} "
                            f"(config {i+1}/{len(expanded_configs)})"
                        )
                    else:
                        # Create and execute new run
                        logger.info(
                            f"Sweep {sweep_id}: Creating run {i+1}/{len(expanded_configs)} "
                            f"with params {params}"
                        )

                        # Update current run info
                        self.sweep_registry.update_progress(
                            sweep_id, current_run_id=f"creating_{i+1}"
                        )

                        result = self.run_service.create_run(
                            run_config, idempotence="new"
                        )
                        self.sweep_registry.add_member_run(sweep_id, result.run_id)
                        self.sweep_registry.update_progress(
                            sweep_id, current_run_id=result.run_id
                        )

                        # Start and wait for completion
                        self.run_service.start_run(result.run_id)
                        self._wait_for_run(result.run_id)

                        # Check if run completed successfully
                        final_run = self.run_registry.get_run(result.run_id)
                        if final_run.status == RunStatus.COMPLETED:
                            completed += 1
                        else:
                            failed += 1
                            logger.warning(
                                f"Run {result.run_id} finished with status {final_run.status}"
                            )

                    # Update progress
                    self.sweep_registry.update_progress(
                        sweep_id,
                        completed_configs=completed,
                        failed_configs=failed,
                        skipped_configs=skipped,
                    )

                except Exception as e:
                    logger.exception(
                        f"Config execution failed in sweep {sweep_id}: {e}"
                    )
                    failed += 1
                    self.sweep_registry.update_progress(
                        sweep_id,
                        completed_configs=completed,
                        failed_configs=failed,
                        skipped_configs=skipped,
                    )

            # Determine final status
            if failed == 0:
                final_status = SweepStatus.COMPLETED
            elif completed > 0 or skipped > 0:
                final_status = SweepStatus.PARTIAL
            else:
                final_status = SweepStatus.PARTIAL

            self.sweep_registry.update_status(
                sweep_id,
                final_status,
                completed_at_ms=now_ms(),
                current_run_id=None,
            )

            logger.info(
                f"Sweep {sweep_id} finished: {completed} completed, "
                f"{skipped} skipped, {failed} failed"
            )

        except Exception as e:
            logger.exception(f"Sweep {sweep_id} failed with unexpected error: {e}")
            try:
                self.sweep_registry.update_status(
                    sweep_id,
                    SweepStatus.PARTIAL,
                    completed_at_ms=now_ms(),
                    error_message=str(e),
                )
            except Exception:
                logger.exception(f"Failed to update status for sweep {sweep_id}")

    def _wait_for_run(self, run_id: str, poll_interval: float = 2.0) -> None:
        """Wait for a run to complete.

        Args:
            run_id: Run identifier
            poll_interval: Seconds between status checks
        """
        import time

        while True:
            run = self.run_registry.get_run(run_id)
            if run.status in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            ):
                break
            time.sleep(poll_interval)

    def _expand_parameter_grid(
        self, config: SweepConfig
    ) -> list[tuple[RunConfig, dict[str, Any]]]:
        """Expand sweep config to list of individual RunConfigs.

        Returns:
            List of (RunConfig, parameters) tuples
        """
        grid = config.parameter_grid.expand_all()

        if not grid:
            # No parameters to sweep - return single config
            return [(self._build_run_config(config, {}), {})]

        # Cartesian product of all parameter values
        param_names = list(grid.keys())
        param_values = [grid[name] for name in param_names]

        run_configs = []
        for combo in itertools.product(*param_values):
            param_dict = dict(zip(param_names, combo))
            run_config = self._build_run_config(config, param_dict)
            run_configs.append((run_config, param_dict))

        return run_configs

    def _build_run_config(
        self, sweep_config: SweepConfig, params: dict[str, Any]
    ) -> RunConfig:
        """Build a RunConfig from sweep config and parameter values.

        Args:
            sweep_config: Base sweep configuration
            params: Parameter values for this specific config

        Returns:
            RunConfig for this parameter combination
        """
        # Start with deep copies of base configs
        import copy

        sim_config_dict = copy.deepcopy(sweep_config.base_simulation_config)
        decross_config_dict = copy.deepcopy(sweep_config.base_decross_config)
        general_config_dict = copy.deepcopy(sweep_config.base_general_config)

        # Ensure hedge_policy_config exists
        if "hedge_policy_config" not in sim_config_dict:
            sim_config_dict["hedge_policy_config"] = {}

        # Apply parameter overrides
        for key, value in params.items():
            if key in ["risk_band_qty", "hedge_mode"]:
                # Goes into hedge_policy_config
                sim_config_dict["hedge_policy_config"][key] = value
            elif key in ["reporting_currency", "hedge_policy", "sample_interval_seconds"]:
                # Top-level simulation config
                sim_config_dict[key] = value
            elif key in ["max_path_length", "min_leg_qty", "priority_currencies", "use_banker_rounding"]:
                # Decross config
                decross_config_dict[key] = value

        # Ensure dataset is set in simulation config
        if "dataset" not in sim_config_dict:
            sim_config_dict["dataset"] = sweep_config.dataset

        # Build SimulationConfig
        simulation_config = SimulationConfig(**sim_config_dict)

        # Build DecrossConfig
        decross_config = DecrossConfig(**decross_config_dict)

        # Build GeneralConfig (sweeps don't modify direct_pairs, use defaults)
        general_config = GeneralConfig()  # type: ignore[call-arg]

        # Build final RunConfig
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        name = f"{sweep_config.name or 'Sweep'}: {param_str}" if params else sweep_config.name

        return RunConfig(
            dataset=sweep_config.dataset,
            tradebook=sweep_config.tradebook,
            start_date=sweep_config.start_date,
            end_date=sweep_config.end_date,
            simulation_config=simulation_config,
            decross_config=decross_config,
            general_config=general_config,
            name=name,
            description=sweep_config.description,
        )

    def get_status(self, sweep_id: str) -> SweepStatusResponse:
        """Get current sweep status and progress.

        Args:
            sweep_id: Sweep identifier

        Returns:
            SweepStatusResponse with status and progress

        Raises:
            SweepNotFoundError: If sweep doesn't exist
        """
        sweep = self.sweep_registry.get_sweep(sweep_id)

        return SweepStatusResponse(
            sweep_id=sweep.sweep_id,
            status=sweep.status,
            total_configs=sweep.total_configs,
            completed_configs=sweep.completed_configs,
            failed_configs=sweep.failed_configs,
            skipped_configs=sweep.skipped_configs,
            progress_pct=sweep.progress_pct,
            current_run_id=sweep.current_run_id,
            error_message=sweep.error_message,
        )

    def get_sweep_detail(self, sweep_id: str) -> SweepDetailResponse:
        """Get full details of a sweep.

        Args:
            sweep_id: Sweep identifier

        Returns:
            SweepDetailResponse with full sweep details

        Raises:
            SweepNotFoundError: If sweep doesn't exist
        """
        sweep = self.sweep_registry.get_sweep(sweep_id)

        return SweepDetailResponse(
            sweep_id=sweep.sweep_id,
            status=sweep.status,
            config_hash=sweep.config_hash,
            config=sweep.config,
            created_at_ms=sweep.created_at_ms,
            started_at_ms=sweep.started_at_ms,
            completed_at_ms=sweep.completed_at_ms,
            total_configs=sweep.total_configs,
            completed_configs=sweep.completed_configs,
            failed_configs=sweep.failed_configs,
            skipped_configs=sweep.skipped_configs,
            progress_pct=sweep.progress_pct,
            member_run_ids=sweep.member_run_ids,
            error_message=sweep.error_message,
        )

    def list_sweeps(
        self,
        status: SweepStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SweepListResponse:
        """List sweeps with optional filters.

        Args:
            status: Filter by status (None = all)
            limit: Maximum sweeps to return
            offset: Number of sweeps to skip

        Returns:
            SweepListResponse with paginated sweeps
        """
        sweeps = self.sweep_registry.list_sweeps(status=status, limit=limit, offset=offset)
        total = self.sweep_registry.count_sweeps(status=status)

        sweep_items = [
            SweepListItem(
                sweep_id=sweep.sweep_id,
                status=sweep.status,
                config_hash=sweep.config_hash,
                name=sweep.config.name,
                dataset=sweep.config.dataset,
                tradebook=sweep.config.tradebook,
                total_configs=sweep.total_configs,
                completed_configs=sweep.completed_configs,
                failed_configs=sweep.failed_configs,
                skipped_configs=sweep.skipped_configs,
                progress_pct=sweep.progress_pct,
                created_at_ms=sweep.created_at_ms,
                completed_at_ms=sweep.completed_at_ms,
            )
            for sweep in sweeps
        ]

        return SweepListResponse(
            sweeps=sweep_items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def delete_sweep(self, sweep_id: str, delete_runs: bool = False) -> None:
        """Delete sweep and optionally its member runs.

        Args:
            sweep_id: Sweep identifier
            delete_runs: If True, also delete all member runs

        Raises:
            SweepNotFoundError: If sweep doesn't exist
            InvalidSweepStateError: If sweep is currently running
        """
        sweep = self.sweep_registry.get_sweep(sweep_id)

        if delete_runs:
            for run_id in sweep.member_run_ids:
                try:
                    self.run_service.delete_run(run_id)
                except Exception as e:
                    logger.warning(f"Failed to delete run {run_id}: {e}")

        self.sweep_registry.delete_sweep(sweep_id)

    def get_frontier(
        self,
        sweep_id: str,
        constraints: list[FrontierConstraint] | None = None,
    ) -> FrontierTableResponse:
        """Generate frontier table with optional constraints.

        Args:
            sweep_id: Sweep identifier
            constraints: Optional list of constraints to filter configs

        Returns:
            FrontierTableResponse with configs and Pareto status

        Raises:
            SweepNotFoundError: If sweep doesn't exist
        """
        sweep = self.sweep_registry.get_sweep(sweep_id)

        # Load all member run summaries
        configs: list[FrontierConfig] = []

        for run_id in sweep.member_run_ids:
            try:
                summary = self.run_service.get_summary(run_id)
                run = self.run_registry.get_run(run_id)

                # Extract swept parameters by comparing to base config
                swept_params = self._extract_swept_params(run.config, sweep.config)

                frontier_config = FrontierConfig(
                    run_id=run_id,
                    config_hash=run.config_hash[:8],  # Short hash for display
                    parameters=swept_params,
                    total_pnl=(
                        summary.frontier_scores.total_pnl
                        if summary.frontier_scores
                        else summary.total_pnl
                    ),
                    pnl_per_volume_bps=(
                        summary.frontier_scores.pnl_per_volume_bps
                        if summary.frontier_scores
                        else 0.0
                    ),
                    max_drawdown_pct=(
                        summary.frontier_scores.max_drawdown_pct
                        if summary.frontier_scores
                        else 0.0
                    ),
                    inventory_risk_score=(
                        summary.frontier_scores.inventory_risk_score
                        if summary.frontier_scores
                        else 0.0
                    ),
                    risk_adjusted_return=(
                        summary.frontier_scores.risk_adjusted_return
                        if summary.frontier_scores
                        else 0.0
                    ),
                    internalization_ratio=summary.internalization_ratio,
                    total_client_volume=summary.total_client_volume,
                    hedge_count=(
                        summary.ops_metrics.hedge_count if summary.ops_metrics else 0
                    ),
                )
                configs.append(frontier_config)

            except Exception as e:
                logger.warning(f"Failed to load summary for run {run_id}: {e}")
                continue

        total_configs = len(configs)

        # Apply constraints
        filtered = self._apply_constraints(configs, constraints or [])

        # Mark Pareto-optimal configs
        self._mark_pareto_optimal(filtered)

        pareto_count = sum(1 for c in filtered if c.is_pareto_optimal)

        return FrontierTableResponse(
            sweep_id=sweep_id,
            configs=filtered,
            total_configs=total_configs,
            filtered_count=len(filtered),
            pareto_count=pareto_count,
        )

    def _extract_swept_params(
        self, run_config: RunConfig, sweep_config: SweepConfig
    ) -> dict[str, Any]:
        """Extract the swept parameter values from a run config.

        Args:
            run_config: Individual run configuration
            sweep_config: Parent sweep configuration

        Returns:
            Dict of swept parameter names to values
        """
        result: dict[str, Any] = {}

        # Get the parameters that were swept
        swept_param_names = sweep_config.parameter_grid.expand_all().keys()

        for param_name in swept_param_names:
            if param_name in ["risk_band_qty", "hedge_mode"]:
                # From hedge_policy_config
                if run_config.simulation_config:
                    value = run_config.simulation_config.hedge_policy_config.get(
                        param_name
                    )
                    if value is not None:
                        result[param_name] = value
            elif param_name in ["hedge_policy", "reporting_currency", "sample_interval_seconds"]:
                # Top-level simulation config
                if run_config.simulation_config:
                    value = getattr(run_config.simulation_config, param_name, None)
                    if value is not None:
                        result[param_name] = value
            elif param_name in ["max_path_length", "min_leg_qty", "priority_currencies"]:
                # Decross config
                if run_config.decross_config:
                    value = getattr(run_config.decross_config, param_name, None)
                    if value is not None:
                        result[param_name] = value

        return result

    def _apply_constraints(
        self,
        configs: list[FrontierConfig],
        constraints: list[FrontierConstraint],
    ) -> list[FrontierConfig]:
        """Filter configs by constraints (AND logic).

        Args:
            configs: List of frontier configs
            constraints: List of constraints to apply

        Returns:
            Filtered list of configs satisfying all constraints
        """
        result = configs

        for constraint in constraints:
            result = [c for c in result if self._check_constraint(c, constraint)]

        return result

    def _check_constraint(
        self, config: FrontierConfig, constraint: FrontierConstraint
    ) -> bool:
        """Check if a config satisfies a constraint.

        Args:
            config: Frontier config to check
            constraint: Constraint to evaluate

        Returns:
            True if config satisfies constraint
        """
        raw_value = getattr(config, constraint.metric, None)
        if raw_value is None:
            return False

        # Cast to float for proper typing
        value: float = float(raw_value)
        threshold: float = constraint.value

        if constraint.operator == "lt":
            return value < threshold
        elif constraint.operator == "le":
            return value <= threshold
        elif constraint.operator == "gt":
            return value > threshold
        elif constraint.operator == "ge":
            return value >= threshold
        elif constraint.operator == "eq":
            return abs(value - threshold) < 1e-9
        else:
            return False

    def _mark_pareto_optimal(self, configs: list[FrontierConfig]) -> None:
        """Mark configs that are Pareto-optimal on (return, risk) frontier.

        Pareto optimal = no other config dominates on both dimensions.
        - Higher pnl_per_volume_bps = better (maximize)
        - Lower inventory_risk_score = better (minimize)

        Args:
            configs: List of configs to evaluate (modified in place)
        """
        for config in configs:
            config.is_pareto_optimal = True

            for other in configs:
                if other is config:
                    continue

                # Check if 'other' dominates 'config'
                better_or_equal_return = (
                    other.pnl_per_volume_bps >= config.pnl_per_volume_bps
                )
                better_or_equal_risk = (
                    other.inventory_risk_score <= config.inventory_risk_score
                )
                strictly_better = (
                    other.pnl_per_volume_bps > config.pnl_per_volume_bps
                    or other.inventory_risk_score < config.inventory_risk_score
                )

                if better_or_equal_return and better_or_equal_risk and strictly_better:
                    config.is_pareto_optimal = False
                    break

    def get_best_configs(
        self,
        sweep_id: str,
        constraints: list[FrontierConstraint],
        sort_by: str = "risk_adjusted_return",
        limit: int = 5,
    ) -> BestConfigsResponse:
        """Get best configs satisfying constraints.

        Args:
            sweep_id: Sweep identifier
            constraints: Constraints to filter by (AND logic)
            sort_by: Metric to sort by
            limit: Maximum configs to return

        Returns:
            BestConfigsResponse with top configs

        Raises:
            SweepNotFoundError: If sweep doesn't exist
        """
        frontier = self.get_frontier(sweep_id, constraints)

        # Sort by specified metric
        # Higher is better for return metrics, lower for risk metrics
        reverse = sort_by in [
            "pnl_per_volume_bps",
            "risk_adjusted_return",
            "total_pnl",
            "internalization_ratio",
        ]

        sorted_configs = sorted(
            frontier.configs,
            key=lambda c: getattr(c, sort_by, 0),
            reverse=reverse,
        )

        return BestConfigsResponse(
            sweep_id=sweep_id,
            constraints=constraints,
            sort_by=sort_by,
            configs=sorted_configs[:limit],
            count=len(sorted_configs),
        )
