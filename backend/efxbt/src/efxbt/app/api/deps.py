"""Dependency injection utilities for FastAPI endpoints."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends

from ...core.config import Settings, get_settings
from ...core.data.run_registry import RunRegistry
from ...engine.orchestration.orchestrator import RunOrchestrator
from ..services.datasets import DatasetsService
from ..services.decross import DecrossService
from ..services.runs import RunService
from ..services.sweeps import SweepService
from ..services.tradebooks import TradeBooksService


# Type alias for settings dependency
SettingsDep = Annotated[Settings, Depends(get_settings)]

# Singleton for run orchestrator (maintains active run state)
_orchestrator: RunOrchestrator | None = None


def get_data_path(settings: SettingsDep) -> Path:
    """Get the data root path from settings.

    Args:
        settings: Application settings

    Returns:
        Resolved data root path
    """
    return settings.data_path


def get_results_path(settings: SettingsDep) -> Path:
    """Get the results root path from settings.

    Args:
        settings: Application settings

    Returns:
        Resolved results root path
    """
    return settings.results_path


def get_datasets_service(settings: SettingsDep) -> DatasetsService:
    """Get datasets service instance.

    Args:
        settings: Application settings

    Returns:
        Datasets service initialized with data root
    """
    return DatasetsService(settings.data_path)


def get_tradebooks_service(settings: SettingsDep) -> TradeBooksService:
    """Get trade books service instance.

    Args:
        settings: Application settings

    Returns:
        Trade books service initialized with data root
    """
    return TradeBooksService(settings.data_path)


def get_decross_service(settings: SettingsDep) -> DecrossService:
    """Get decross service instance.

    Args:
        settings: Application settings

    Returns:
        Decross service initialized with data root and default config
    """
    return DecrossService(settings.data_path)


def get_runs_service(settings: SettingsDep) -> RunService:
    """Get runs service instance.

    Uses singleton orchestrator for consistent active run tracking.

    Args:
        settings: Application settings

    Returns:
        Runs service initialized with data root and results path
    """
    global _orchestrator

    if _orchestrator is None:
        registry = RunRegistry(settings.results_path)
        _orchestrator = RunOrchestrator(registry, settings.data_path)

    return RunService(
        data_root=settings.data_path,
        results_root=settings.results_path,
        orchestrator=_orchestrator,
    )


def get_sweeps_service(settings: SettingsDep) -> SweepService:
    """Get sweeps service instance.

    Args:
        settings: Application settings

    Returns:
        Sweeps service initialized with data root, results path, and run service
    """
    run_service = get_runs_service(settings)
    return SweepService(
        data_root=settings.data_path,
        results_root=settings.results_path,
        run_service=run_service,
    )
