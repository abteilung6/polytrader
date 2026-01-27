"""FastAPI middleware for observability (logging, metrics, correlation IDs).

Per observability.mdc §2, §3, §4: Structured logging, correlation IDs, and metrics
are required for all API requests.
"""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from polytrader.common.ids import generate_correlation_id
from polytrader.logging_config import logger
from polytrader.obs.logging import bind_correlation_context
from polytrader.obs.metrics import get_metrics_collector


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for request observability (logging, metrics, correlation IDs).

    Per observability.mdc:
    - §2: Every log line must include correlation_id when applicable
    - §3: Structured logging with mandatory fields
    - §4: Metrics for API requests

    This middleware:
    - Generates correlation_id for each request
    - Logs request/response with structured fields
    - Records metrics (api_requests_total, api_request_duration_seconds)
    - Adds correlation_id to request state for use in endpoints
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with observability.

        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint handler

        Returns:
            FastAPI response
        """
        # Generate correlation ID for this request
        correlation_id = generate_correlation_id()

        # Add correlation_id to request state for use in endpoints
        request.state.correlation_id = correlation_id

        # Extract endpoint path (remove query params for cleaner metrics)
        endpoint = request.url.path

        # Start timer for latency measurement
        start_time = time.monotonic()

        # Bind correlation context for structured logging
        log_ctx = bind_correlation_context(
            logger,
            correlation_id=correlation_id,
            endpoint=endpoint,
            method=request.method,
            event_type="APIRequest",
        )

        # Log request start
        log_ctx.info(
            "API request started: {method} {endpoint}",
            method=request.method,
            endpoint=endpoint,
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate latency
            latency_seconds = time.monotonic() - start_time
            latency_ms = latency_seconds * 1000

            # Record metrics
            metrics = get_metrics_collector()
            metrics.increment_counter(
                "api_requests_total",
                labels={
                    "endpoint": endpoint,
                    "method": request.method,
                    "status": str(response.status_code),
                },
            )
            metrics.record_histogram(
                "api_request_duration_seconds",
                latency_seconds,
                labels={"endpoint": endpoint, "method": request.method},
            )

            # Log successful response
            log_ctx.bind(
                status_code=response.status_code,
                latency_ms=latency_ms,
            ).info(
                "API request completed: {method} {endpoint} -> {status_code} ({latency_ms:.2f}ms)",
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )

            return response

        except Exception as e:
            # Calculate latency even on error
            latency_seconds = time.monotonic() - start_time
            latency_ms = latency_seconds * 1000

            # Record error metrics
            metrics = get_metrics_collector()
            metrics.increment_counter(
                "api_requests_total",
                labels={
                    "endpoint": endpoint,
                    "method": request.method,
                    "status": "500",
                },
            )
            metrics.record_histogram(
                "api_request_duration_seconds",
                latency_seconds,
                labels={"endpoint": endpoint, "method": request.method},
            )

            # Log error
            log_ctx.bind(
                status_code=500,
                latency_ms=latency_ms,
                error_class="fatal",
            ).error(
                "API request failed: {method} {endpoint} -> 500 ({latency_ms:.2f}ms): {error}",
                method=request.method,
                endpoint=endpoint,
                latency_ms=latency_ms,
                error=str(e),
                exc_info=True,
            )

            # Re-raise to let FastAPI handle it
            raise
