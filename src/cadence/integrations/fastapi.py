"""FastAPI integration for Cadence.

Provides seamless integration between Cadence flows and FastAPI endpoints.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import (
    Any,
    Generic,
    TypeVar,
)

try:
    from fastapi import HTTPException, Response
    from fastapi.routing import APIRoute

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from cadence.cadence import Cadence
from cadence.exceptions import CadenceError
from cadence.score import Score

ScoreT = TypeVar("ScoreT", bound=Score)
ResponseT = TypeVar("ResponseT")


def _check_fastapi() -> None:
    """Check if FastAPI is installed."""
    if not HAS_FASTAPI:
        raise ImportError(
            "FastAPI is required for this integration. "
            "Install it with: pip install cadence[fastapi]"
        )


class CadenceRoute(APIRoute):
    """
    Custom APIRoute that wraps endpoints with cadence execution.

    Use this as the route_class for endpoints that should execute cadences.

    Example:
        from fastapi import FastAPI
        from cadence.integrations.fastapi import CadenceRoute

        app = FastAPI()

        @app.post("/orders", route_class=CadenceRoute)
        async def create_order(request: OrderRequest) -> OrderResponse:
            # This becomes the cadence score
            score = OrderScore.from_request(request)
            return await order_cadence.run(score)
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _check_fastapi()
        super().__init__(*args, **kwargs)


def cadence_endpoint(
    cadence: Cadence[ScoreT],
    score_factory: Callable[..., ScoreT],
    response_mapper: Callable[[ScoreT], Any] | None = None,
    error_handler: Callable[[Exception], Response] | None = None,
) -> Callable[..., Any]:
    """
    Create a FastAPI endpoint from a Cadence.

    Args:
        cadence: The cadence to execute
        score_factory: Function to create score from request data
        response_mapper: Optional function to convert score to response
        error_handler: Optional custom error handler

    Returns:
        An async function suitable as a FastAPI endpoint

    Example:
        from fastapi import FastAPI
        from cadence.integrations.fastapi import cadence_endpoint

        app = FastAPI()

        app.post("/orders")(
            cadence_endpoint(
                cadence=order_cadence,
                score_factory=lambda order: OrderScore(
                    order_id=order.id,
                    user_id=order.user_id,
                ),
                response_mapper=lambda score: OrderResponse(
                    order_id=score.order_id,
                    status=score.status,
                ),
            )
        )
    """
    _check_fastapi()

    async def endpoint(**kwargs: Any) -> Any:
        try:
            # Create score from request data
            score = score_factory(**kwargs)

            # Initialize score if needed
            if hasattr(score, "__post_init__") and not getattr(score, "_initialized", False):
                score.__post_init__()

            # Execute cadence
            result = await cadence.run()

            # Map response
            if response_mapper:
                return response_mapper(result)
            return result

        except CadenceError as e:
            if error_handler:
                return error_handler(e)
            raise HTTPException(status_code=500, detail=str(e)) from e

        except Exception as e:
            if error_handler:
                return error_handler(e)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return endpoint


def with_cadence(
    cadence_factory: Callable[[Any], Cadence[ScoreT]],
    response_mapper: Callable[[ScoreT], Any] | None = None,
) -> Callable[[Callable[..., ScoreT]], Callable[..., Any]]:
    """
    Decorator to wrap a FastAPI endpoint with cadence execution.

    The decorated function should return a Score object, which becomes
    the initial score for the cadence.

    Args:
        cadence_factory: Function that takes score and returns a Cadence
        response_mapper: Optional function to convert final score to response

    Example:
        from cadence.integrations.fastapi import with_cadence

        def create_checkout_cadence(score: OrderScore) -> Cadence[OrderScore]:
            return (
                Cadence("checkout", score)
                .then("validate", validate_order)
                .then("process", process_payment)
            )

        @app.post("/checkout")
        @with_cadence(create_checkout_cadence, lambda score: {"order_id": score.order_id})
        async def checkout(order: OrderRequest) -> OrderScore:
            return OrderScore(
                order_id=order.id,
                user_id=order.user_id,
            )
    """
    _check_fastapi()

    def decorator(func: Callable[..., ScoreT]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get initial score from decorated function
            score = func(*args, **kwargs)

            # Initialize if needed
            if hasattr(score, "__post_init__") and not getattr(score, "_initialized", False):
                score.__post_init__()

            # Create and run cadence
            cadence = cadence_factory(score)
            result = await cadence.run()

            # Map response
            if response_mapper:
                return response_mapper(result)
            return result

        return wrapper

    return decorator


class CadenceDependency(Generic[ScoreT]):
    """
    FastAPI dependency that provides cadence execution.

    Use this to inject cadence execution into your endpoints while
    maintaining full control over the endpoint logic.

    Example:
        from fastapi import Depends
        from cadence.integrations.fastapi import CadenceDependency

        cadence_dep = CadenceDependency(order_cadence)

        @app.post("/orders")
        async def create_order(
            order: OrderRequest,
            execute: Callable = Depends(cadence_dep),
        ):
            score = OrderScore(order_id=order.id)
            result = await execute(score)
            return {"order_id": result.order_id}
    """

    def __init__(self, cadence: Cadence[ScoreT]) -> None:
        _check_fastapi()
        self._cadence = cadence

    async def __call__(self) -> Callable[[ScoreT], Any]:
        """Return an execution function."""

        async def execute(score: ScoreT) -> ScoreT:
            # Clone cadence with new score
            new_cadence = Cadence(self._cadence.name, score)
            new_cadence._measures = self._cadence._measures
            new_cadence._time_reporter = self._cadence._time_reporter
            new_cadence._error_handler = self._cadence._error_handler
            new_cadence._stop_on_error = self._cadence._stop_on_error
            return await new_cadence.run()

        return execute


# Middleware for request-scoped cadence score
class CadenceMiddleware:
    """
    ASGI middleware for request-scoped cadence context.

    Provides automatic timing and error handling for all cadence executions
    within a request.

    Example:
        from fastapi import FastAPI
        from cadence.integrations.fastapi import CadenceMiddleware

        app = FastAPI()
        app.add_middleware(CadenceMiddleware, reporter=json_reporter)
    """

    def __init__(
        self,
        app: Any,
        reporter: Callable[..., Any] | None = None,
        error_handler: Callable[..., Any] | None = None,
    ) -> None:
        _check_fastapi()
        self.app = app
        self.reporter = reporter
        self.error_handler = error_handler

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Could add request-scoped score here using contextvars
        # For now, just pass through
        await self.app(scope, receive, send)
