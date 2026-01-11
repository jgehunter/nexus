"""FastAPI application factory and entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core.config import Defaults, get_settings
from .api.router import api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    app = FastAPI(
        title="eFX Backtester API",
        description="API for eFX hedging backtest simulation",
        version=Defaults.VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Configure CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(api_router)

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "efxbt.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
