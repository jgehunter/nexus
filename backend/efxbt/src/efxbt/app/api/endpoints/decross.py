"""Decrossing configuration and preview endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ....core.config.run_config import DecrossConfig
from ....core.data.schemas import TradeRecord
from ...services.decross import DecrossService
from ..deps import get_decross_service


router = APIRouter(tags=["decross"])


# =============================================================================
# Request/Response Models
# =============================================================================


class CurrencyGraphResponse(BaseModel):
    """Currency graph representation for API."""

    nodes: list[str] = Field(description="List of currency codes")
    edges: list[dict[str, str]] = Field(
        description="List of edges with keys: from, to, pair"
    )
    version_id: str = Field(description="Graph version ID (hash)")


class LegPreview(BaseModel):
    """Preview of a single decrossed leg."""

    pair: str
    side: int
    qty: float
    price: float
    leg_index: int


class TradePreview(BaseModel):
    """Preview of decrossing for one trade."""

    source_trade_id: str
    source_pair: str
    path: list[str]
    legs: list[LegPreview]
    is_direct: bool
    error: str | None = None


class DecrossPreviewRequest(BaseModel):
    """Request to preview decrossing."""

    trades: list[TradeRecord]
    market_dataset: str


class DecrossPreviewResponse(BaseModel):
    """Response with decrossing previews."""

    previews: list[TradePreview]
    graph_version: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/graph", response_model=CurrencyGraphResponse)
async def get_currency_graph(
    dataset_name: Annotated[
        str,
        Query(description="Market dataset name to build graph from"),
    ],
    service: Annotated[DecrossService, Depends(get_decross_service)],
) -> CurrencyGraphResponse:
    """Get the currency graph for a market dataset.

    Returns nodes (currencies) and edges (direct pairs) that can be traded.
    The graph is used for pathfinding when decrossing cross-pair trades.

    Args:
        dataset_name: Market dataset to build graph from
        service: Injected DecrossService

    Returns:
        CurrencyGraphResponse with nodes, edges, and version ID

    Example:
        GET /api/v1/decross/graph?dataset_name=fx_2024
        {
            "nodes": ["EUR", "USD", "GBP"],
            "edges": [
                {"from": "EUR", "to": "USD", "pair": "EURUSD"},
                {"from": "USD", "to": "EUR", "pair": "EURUSD"},
                ...
            ],
            "version_id": "a1b2c3d4e5f6g7h8"
        }
    """
    graph = service.build_graph_for_dataset(dataset_name)

    return CurrencyGraphResponse(
        nodes=[node.currency for node in graph.nodes],
        edges=[
            {
                "from": edge.from_currency,
                "to": edge.to_currency,
                "pair": edge.pair,
            }
            for edge in graph.edges
        ],
        version_id=graph.version_id,
    )


@router.post("/preview", response_model=DecrossPreviewResponse)
async def preview_decross(
    request: DecrossPreviewRequest,
    service: Annotated[DecrossService, Depends(get_decross_service)],
) -> DecrossPreviewResponse:
    """Preview decrossing for a set of trades.

    Shows how cross trades would be decomposed into direct risk pairs
    without actually running the full pipeline. Useful for debugging
    and understanding the decrossing logic.

    Args:
        request: Preview request with trades and dataset name
        service: Injected DecrossService

    Returns:
        DecrossPreviewResponse with preview for each trade

    Example:
        POST /api/v1/decross/preview
        {
            "trades": [
                {
                    "timestamp_ms": 1609459200000,
                    "pair": "EURGBP",
                    "side": 1,
                    "qty": 1000.0,
                    "price": 0.85,
                    "trade_id": "T1"
                }
            ],
            "market_dataset": "fx_2024"
        }

        Response:
        {
            "previews": [{
                "source_trade_id": "T1",
                "source_pair": "EURGBP",
                "path": ["EUR", "USD", "GBP"],
                "legs": [
                    {"pair": "EURUSD", "side": 1, "qty": 1000.0, "price": 1.10, "leg_index": 0},
                    {"pair": "GBPUSD", "side": -1, "qty": 880.0, "price": 1.25, "leg_index": 1}
                ],
                "is_direct": false
            }],
            "graph_version": "a1b2c3d4e5f6g7h8"
        }
    """
    # Get graph for version ID
    graph = service.build_graph_for_dataset(request.market_dataset)

    # Get previews
    preview_dicts = service.preview_decross(
        trades=request.trades,
        market_dataset_name=request.market_dataset,
    )

    # Convert to response model
    previews = []
    for p in preview_dicts:
        if "error" in p:
            previews.append(
                TradePreview(
                    source_trade_id=p["source_trade_id"],
                    source_pair=p["source_pair"],
                    path=[],
                    legs=[],
                    is_direct=False,
                    error=p["error"],
                )
            )
        else:
            previews.append(
                TradePreview(
                    source_trade_id=p["source_trade_id"],
                    source_pair=p["source_pair"],
                    path=p["path"],
                    legs=[LegPreview(**leg) for leg in p["legs"]],
                    is_direct=p["is_direct"],
                )
            )

    return DecrossPreviewResponse(
        previews=previews,
        graph_version=graph.version_id,
    )


@router.get("/config", response_model=DecrossConfig)
async def get_decross_config(
    service: Annotated[DecrossService, Depends(get_decross_service)],
) -> DecrossConfig:
    """Get current decrossing configuration.

    Returns settings for currency priorities, path length limits,
    rounding behavior, and minimum quantities.

    Args:
        service: Injected DecrossService

    Returns:
        DecrossConfig with current settings

    Example:
        GET /api/v1/decross/config
        {
            "priority_currencies": ["USD", "EUR", "GBP", "JPY"],
            "max_path_length": 3,
            "use_banker_rounding": true,
            "min_leg_qty": 0.01
        }
    """
    return service.get_config()
