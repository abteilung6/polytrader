"""FastAPI application factory.

Per Platform_Proposal.md: App factory pattern enables clean testing
by allowing dependency override and multiple app instances.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polytrader.api.control import router as control_router
from polytrader.api.market import router as market_router
from polytrader.api.middleware import ObservabilityMiddleware


def create_app() -> FastAPI:
    """Create FastAPI application with dependency injection.

    This factory pattern enables:
    - Clean testing (easy to override dependencies)
    - Multiple app instances (for testing)
    - Dependency injection configuration

    Returns:
        FastAPI application instance

    Example:
        >>> app = create_app()
        >>> # Use with uvicorn: uvicorn.run(app, host="0.0.0.0", port=8000)
    """
    app = FastAPI(
        title="Polytrader Control API",
        description="Control plane API for Polytrader platform",
        version="1.0.0",
        docs_url="/docs",  # Swagger UI
        redoc_url="/redoc",  # ReDoc
        openapi_url="/openapi.json",  # OpenAPI spec
    )

    # Observability middleware (logging, metrics, correlation IDs)
    # Must be added before CORS to capture all requests
    app.add_middleware(ObservabilityMiddleware)

    # CORS middleware (configure appropriately for production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(control_router)
    app.include_router(market_router)

    return app
