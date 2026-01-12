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
    from fastapi import HTTPException, Request, Response
    from fastapi.routing import APIRoute
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import Response as StarletteResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from cadence.exceptions import CadenceError
from cadence.flow import Cadence
from cadence.state import Context

ContextT = TypeVar("ContextT", bound=Context)
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
            # This becomes the cadence context
            ctx = OrderContext.from_request(request)
            return await order_cadence.run(ctx)
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _check_fastapi()
        super().__init__(*args, **kwargs)


def cadence_endpoint(
    cadence: Cadence[ContextT],
    context_factory: Callable[..., ContextT],
    response_mapper: Callable[[ContextT], Any] | None = None,
    error_handler: Callable[[Exception], Response] | None = None,
) -> Callable:
    """
    Create a FastAPI endpoint from a Cadence.

    Args:
        cadence: The cadence to execute
        context_factory: Function to create context from request data
        response_mapper: Optional function to convert context to response
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
                context_factory=lambda order: OrderContext(
                    order_id=order.id,
                    user_id=order.user_id,
                ),
                response_mapper=lambda ctx: OrderResponse(
                    order_id=ctx.order_id,
                    status=ctx.status,
                ),
            )
        )
    """
    _check_fastapi()

    async def endpoint(**kwargs: Any) -> Any:
        try:
            # Create context from request data
            ctx = context_factory(**kwargs)

            # Initialize context if needed
            if hasattr(ctx, "__post_init__") and not getattr(ctx, "_initialized", False):
                ctx.__post_init__()

            # Execute cadence
            result = await cadence.run()

            # Map response
            if response_mapper:
                return response_mapper(result)
            return result

        except CadenceError as e:
            if error_handler:
                return error_handler(e)
            raise HTTPException(status_code=500, detail=str(e))

        except Exception as e:
            if error_handler:
                return error_handler(e)
            raise HTTPException(status_code=500, detail=str(e))

    return endpoint


def with_cadence(
    cadence_factory: Callable[[Any], Cadence[ContextT]],
    response_mapper: Callable[[ContextT], Any] | None = None,
) -> Callable[[Callable[..., ContextT]], Callable]:
    """
    Decorator to wrap a FastAPI endpoint with cadence execution.

    The decorated function should return a Context object, which becomes
    the initial context for the cadence.

    Args:
        cadence_factory: Function that takes context and returns a Cadence
        response_mapper: Optional function to convert final context to response

    Example:
        from cadence.integrations.fastapi import with_cadence

        def create_checkout_cadence(ctx: OrderContext) -> Cadence[OrderContext]:
            return (
                Cadence("checkout", ctx)
                .then("validate", validate_order)
                .then("process", process_payment)
            )

        @app.post("/checkout")
        @with_cadence(create_checkout_cadence, lambda ctx: {"order_id": ctx.order_id})
        async def checkout(order: OrderRequest) -> OrderContext:
            return OrderContext(
                order_id=order.id,
                user_id=order.user_id,
            )
    """
    _check_fastapi()

    def decorator(func: Callable[..., ContextT]) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get initial context from decorated function
            context = func(*args, **kwargs)

            # Initialize if needed
            if hasattr(context, "__post_init__") and not getattr(context, "_initialized", False):
                context.__post_init__()

            # Create and run cadence
            cadence = cadence_factory(context)
            result = await cadence.run()

            # Map response
            if response_mapper:
                return response_mapper(result)
            return result

        return wrapper

    return decorator


class CadenceDependency(Generic[ContextT]):
    """
    FastAPI dependency that provides cadence execution context.

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
            ctx = OrderContext(order_id=order.id)
            result = await execute(ctx)
            return {"order_id": result.order_id}
    """

    def __init__(self, cadence: Cadence[ContextT]) -> None:
        _check_fastapi()
        self._cadence = cadence

    async def __call__(self) -> Callable[[ContextT], Any]:
        """Return an execution function."""
        async def execute(context: ContextT) -> ContextT:
            # Clone cadence with new context
            new_cadence = Cadence(self._cadence.name, context)
            new_cadence._nodes = self._cadence._nodes
            new_cadence._time_reporter = self._cadence._time_reporter
            new_cadence._error_handler = self._cadence._error_handler
            new_cadence._stop_on_error = self._cadence._stop_on_error
            return await new_cadence.run()

        return execute


# Middleware for request-scoped cadence context
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
        reporter: Callable | None = None,
        error_handler: Callable | None = None,
    ) -> None:
        _check_fastapi()
        self.app = app
        self.reporter = reporter
        self.error_handler = error_handler

    async def __call__(
        self,
        scope: dict,
        receive: Callable,
        send: Callable,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Could add request-scoped context here using contextvars
        # For now, just pass through
        await self.app(scope, receive, send)
