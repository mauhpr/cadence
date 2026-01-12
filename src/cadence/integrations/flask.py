"""Flask integration for Cadence.

Provides decorators and utilities for using cadences in Flask applications.

Example:
    from flask import Flask
    from cadence import Cadence, Context, beat
    from cadence.integrations.flask import cadence_route, CadenceBlueprint

    app = Flask(__name__)

    @app.route("/orders", methods=["POST"])
    @cadence_route(order_cadence, context_factory=OrderContext.from_request)
    def create_order():
        pass  # Cadence handles everything

    # Or using blueprints
    orders_bp = CadenceBlueprint("orders", __name__, url_prefix="/orders")
    orders_bp.register_cadence("/", order_cadence, methods=["POST"])
    app.register_blueprint(orders_bp)
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
)

ContextT = TypeVar("ContextT")


def _get_flask():
    """Lazy import Flask to avoid requiring it as a dependency."""
    try:
        import flask
        return flask
    except ImportError:
        raise ImportError(
            "Flask is required for Flask integration. "
            "Install it with: pip install cadence[flask] or pip install flask"
        )


def cadence_route(
    cadence: Cadence[ContextT],
    *,
    context_factory: Callable[..., ContextT] | None = None,
    response_factory: Callable[[ContextT], Any] | None = None,
    error_handler: Callable[[Exception], Any] | None = None,
) -> Callable:
    """
    Decorator to wrap a Flask route with a cadence.

    The decorated function can optionally return initial context data,
    or you can provide a context_factory to build context from the request.

    Args:
        cadence: The Cadence instance to execute
        context_factory: Function to create context from Flask request.
            Receives (request,) and returns ContextT.
            If None, decorated function's return value is used as context.
        response_factory: Function to convert final context to response.
            Receives (context,) and returns response.
            If None, context is returned directly (Flask will try to jsonify).
        error_handler: Function to handle cadence errors.
            Receives (exception,) and returns response.
            If None, exceptions are re-raised.

    Example:
        @app.route("/orders", methods=["POST"])
        @cadence_route(order_cadence, context_factory=lambda req: OrderContext(**req.json))
        def create_order():
            pass

        # Or let the decorated function provide context:
        @app.route("/orders/<order_id>")
        @cadence_route(order_cadence)
        def get_order(order_id: str):
            return OrderContext(order_id=order_id)
    """
    flask = _get_flask()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                # Get context either from factory or decorated function
                if context_factory is not None:
                    context = context_factory(flask.request)
                else:
                    result = fn(*args, **kwargs)
                    if result is None:
                        raise ValueError(
                            "cadence_route decorated function must return context "
                            "or provide context_factory"
                        )
                    context = result

                # Initialize context if needed
                if hasattr(context, "__post_init__") and callable(context.__post_init__):
                    # Check if already initialized
                    if not hasattr(context, "_original_values"):
                        context.__post_init__()

                # Clone cadence with new context
                from cadence.flow import Cadence
                cadence_instance = Cadence(cadence._name, context)
                cadence_instance._nodes = cadence._nodes
                cadence_instance._time_reporter = cadence._time_reporter
                cadence_instance._error_handler = cadence._error_handler
                cadence_instance._stop_on_error = cadence._stop_on_error

                # Run cadence (handle async in sync context)
                final_context = asyncio.run(cadence_instance.run())

                # Convert to response
                if response_factory is not None:
                    return response_factory(final_context)
                return final_context

            except Exception as e:
                if error_handler is not None:
                    return error_handler(e)
                raise

        return wrapper

    return decorator


def with_cadence(
    context_class: type[ContextT],
    *,
    from_request: Callable[..., dict[str, Any]] | None = None,
) -> Callable:
    """
    Decorator that injects a cadence-ready context into the view function.

    The context is created from request data and passed to the function.
    The function should build and run the cadence.

    Args:
        context_class: The Context class to instantiate
        from_request: Function to extract context kwargs from request.
            If None, uses request.json for POST/PUT, request.args for GET.

    Example:
        @app.route("/orders", methods=["POST"])
        @with_cadence(OrderContext)
        def create_order(ctx: OrderContext):
            cadence = (
                Cadence("create_order", ctx)
                .then("validate", validate)
                .then("process", process)
            )
            return asyncio.run(cadence.run())
    """
    flask = _get_flask()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract data from request
            if from_request is not None:
                data = from_request(flask.request)
            elif flask.request.method in ("POST", "PUT", "PATCH"):
                data = flask.request.get_json(silent=True) or {}
            else:
                data = dict(flask.request.args)

            # Merge with URL parameters
            data.update(kwargs)

            # Create context
            context = context_class(**data)
            if hasattr(context, "__post_init__"):
                context.__post_init__()

            # Call function with context
            return fn(context, *args)

        return wrapper

    return decorator


class CadenceBlueprint:
    """
    A Flask Blueprint with built-in cadence registration.

    Provides a convenient way to organize cadence-based routes.

    Example:
        from cadence.integrations.flask import CadenceBlueprint

        orders = CadenceBlueprint("orders", __name__, url_prefix="/orders")

        orders.register_cadence(
            "/",
            create_order_cadence,
            methods=["POST"],
            context_factory=lambda req: OrderContext(**req.json),
        )

        orders.register_cadence(
            "/<order_id>",
            get_order_cadence,
            methods=["GET"],
            context_factory=lambda req, order_id: OrderContext(order_id=order_id),
        )

        app.register_blueprint(orders)
    """

    def __init__(
        self,
        name: str,
        import_name: str,
        **blueprint_kwargs: Any,
    ) -> None:
        """
        Create a CadenceBlueprint.

        Args:
            name: Blueprint name
            import_name: Usually __name__
            **blueprint_kwargs: Additional kwargs for Flask Blueprint
        """
        flask = _get_flask()
        self._blueprint = flask.Blueprint(name, import_name, **blueprint_kwargs)
        self._cadences: list[dict[str, Any]] = []

    @property
    def blueprint(self):
        """Get the underlying Flask Blueprint."""
        return self._blueprint

    def register_cadence(
        self,
        rule: str,
        cadence: Cadence[ContextT],
        *,
        methods: list[str] | None = None,
        context_factory: Callable[..., ContextT] | None = None,
        response_factory: Callable[[ContextT], Any] | None = None,
        error_handler: Callable[[Exception], Any] | None = None,
        endpoint: str | None = None,
    ) -> None:
        """
        Register a cadence at a URL rule.

        Args:
            rule: URL rule (e.g., "/" or "/<order_id>")
            cadence: Cadence to execute
            methods: HTTP methods (default: ["GET"])
            context_factory: Function to create context.
                Receives (request, **url_params) and returns ContextT.
            response_factory: Function to convert context to response
            error_handler: Function to handle errors
            endpoint: Endpoint name (default: cadence name)
        """
        flask = _get_flask()
        methods = methods or ["GET"]
        endpoint = endpoint or cadence._name

        def view_func(**url_kwargs: Any) -> Any:
            try:
                # Build context
                if context_factory is not None:
                    context = context_factory(flask.request, **url_kwargs)
                else:
                    # Default: use request JSON + URL params
                    data = {}
                    if flask.request.method in ("POST", "PUT", "PATCH"):
                        data = flask.request.get_json(silent=True) or {}
                    data.update(url_kwargs)

                    # Try to instantiate context class from cadence's initial context
                    context_class = type(cadence._context)
                    context = context_class(**data)

                # Initialize context
                if hasattr(context, "__post_init__"):
                    context.__post_init__()

                # Clone and run cadence
                from cadence.flow import Cadence
                cadence_instance = Cadence(cadence._name, context)
                cadence_instance._nodes = cadence._nodes
                cadence_instance._time_reporter = cadence._time_reporter
                cadence_instance._error_handler = cadence._error_handler
                cadence_instance._stop_on_error = cadence._stop_on_error

                final_context = asyncio.run(cadence_instance.run())

                if response_factory is not None:
                    return response_factory(final_context)
                return final_context

            except Exception as e:
                if error_handler is not None:
                    return error_handler(e)
                raise

        # Set function name for Flask
        view_func.__name__ = endpoint

        self._blueprint.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=methods,
        )

    def route(self, rule: str, **options: Any) -> Callable:
        """Standard Flask route decorator (passthrough)."""
        return self._blueprint.route(rule, **options)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to underlying blueprint."""
        return getattr(self._blueprint, name)


class CadenceExtension:
    """
    Flask extension for Cadence.

    Provides app-level configuration and utilities.

    Example:
        from flask import Flask
        from cadence.integrations.flask import CadenceExtension

        app = Flask(__name__)
        cadences = CadenceExtension(app)

        # Or with factory pattern
        cadences = CadenceExtension()
        cadences.init_app(app)

        # Configure default reporter
        cadences.set_reporter(json_reporter)
    """

    def __init__(self, app: Any | None = None) -> None:
        self._reporter: Callable | None = None
        self._error_handler: Callable | None = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        """Initialize the extension with a Flask app."""
        app.extensions = getattr(app, "extensions", {})
        app.extensions["cadence"] = self

        # Register error handler if configured
        if self._error_handler:
            from cadence.exceptions import CadenceError
            app.register_error_handler(CadenceError, self._error_handler)

    def set_reporter(self, reporter: Callable) -> None:
        """Set the default time reporter for all cadences."""
        self._reporter = reporter

    def set_error_handler(self, handler: Callable) -> None:
        """Set the default error handler for all cadences."""
        self._error_handler = handler

    @property
    def reporter(self) -> Callable | None:
        return self._reporter

    @property
    def error_handler(self) -> Callable | None:
        return self._error_handler
