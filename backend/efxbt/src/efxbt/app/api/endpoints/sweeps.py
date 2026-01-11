"""Parameter sweep endpoints (stub)."""

from fastapi import APIRouter

from ..errors import NotImplementedError


router = APIRouter(tags=["sweeps"])


@router.get("")
async def list_sweeps() -> None:
    """List all parameter sweeps.

    Returns paginated list of sweeps with status and metadata.
    """
    raise NotImplementedError("/api/v1/sweeps")


@router.post("")
async def create_sweep() -> None:
    """Create and start a new parameter sweep.

    Accepts sweep configuration specifying parameter ranges.
    """
    raise NotImplementedError("/api/v1/sweeps")


@router.get("/{sweep_id}")
async def get_sweep(sweep_id: str) -> None:
    """Get details of a specific sweep.

    Args:
        sweep_id: Unique sweep identifier
    """
    raise NotImplementedError(f"/api/v1/sweeps/{sweep_id}")


@router.delete("/{sweep_id}")
async def delete_sweep(sweep_id: str) -> None:
    """Delete a sweep and its results.

    Args:
        sweep_id: Unique sweep identifier
    """
    raise NotImplementedError(f"/api/v1/sweeps/{sweep_id}")


@router.get("/{sweep_id}/results")
async def get_sweep_results(sweep_id: str) -> None:
    """Get aggregated results from a sweep.

    Args:
        sweep_id: Unique sweep identifier

    Returns comparison of metrics across parameter combinations.
    """
    raise NotImplementedError(f"/api/v1/sweeps/{sweep_id}/results")
