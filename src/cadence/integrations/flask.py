"""Flask integration for Cadence.

Provides decorators and utilities for using cadences in Flask applications.

Example:
    from flask import Flask
    from cadence import Cadence, Score, note
    from cadence.integrations.flask import cadence_route, CadenceBlueprint

    app = Flask(__name__)

    @app.route("/orders", methods=["POST"])
    @cadence_route(order_cadence, score_factory=OrderScore.from_request)
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
    TYPE_CHECKING,
    Any,
    TypeVar,
)

if TYPE_CHECKING:
    from cadence.cadence import Cadence

ScoreT = TypeVar("ScoreT")


def _get_flask() -> Any:
    """Lazy import Flask to avoid requiring it as a dependency."""
    try:
        import flask

        return flask
    except ImportError as exc:
        raise ImportError(
            "Flask is required for Flask integration. "
            "Install it with: pip install cadence[flask] or pip install flask"
        ) from exc


def cadence_route(
    cadence: Cadence[ScoreT],
    *,
    score_factory: Callable[..., ScoreT] | None = None,
    response_factory: Callable[[ScoreT], Any] | None = None,
    error_handler: Callable[[Exception], Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to wrap a Flask route with a cadence.

    The decorated function can optionally return initial score data,
    or you can provide a score_factory to build score from the request.

    Args:
        cadence: The Cadence instance to execute
        score_factory: Function to create score from Flask request.
            Receives (request,) and returns ScoreT.
            If None, decorated function's return value is used as score.
        response_factory: Function to convert final score to response.
            Receives (score,) and returns response.
            If None, score is returned directly (Flask will try to jsonify).
        error_handler: Function to handle cadence errors.
            Receives (exception,) and returns response.
            If None, exceptions are re-raised.

    Example:
        @app.route("/orders", methods=["POST"])
        @cadence_route(order_cadence, score_factory=lambda req: OrderScore(**req.json))
        def create_order():
            pass

        # Or let the decorated function provide score:
        @app.route("/orders/<order_id>")
        @cadence_route(order_cadence)
        def get_order(order_id: str):
            return OrderScore(order_id=order_id)
    """
    flask = _get_flask()

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                # Get score either from factory or decorated function
                if score_factory is not None:
                    score = score_factory(flask.request)
                else:
                    result = fn(*args, **kwargs)
                    if result is None:
                        raise ValueError(
                            "cadence_route decorated function must return score "
                            "or provide score_factory"
                        )
                    score = result

                # Initialize score if needed
                if (
                    hasattr(score, "__post_init__")
                    and callable(score.__post_init__)
                    and not hasattr(score, "_original_values")
                ):
                    score.__post_init__()

                # Clone cadence with new score
                from cadence.cadence import Cadence

                cadence_instance = Cadence(cadence._name, score)
                cadence_instance._measures = cadence._measures
                cadence_instance._time_reporter = cadence._time_reporter
                cadence_instance._error_handler = cadence._error_handler
                cadence_instance._stop_on_error = cadence._stop_on_error

                # Run cadence (handle async in sync context)
                final_score = asyncio.run(cadence_instance.run())

                # Convert to response
                if response_factory is not None:
                    return response_factory(final_score)
                return final_score

            except Exception as e:
                if error_handler is not None:
                    return error_handler(e)
                raise

        return wrapper

    return decorator


def with_cadence(
    score_class: type[ScoreT],
    *,
    from_request: Callable[..., dict[str, Any]] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator that injects a cadence-ready score into the view function.

    The score is created from request data and passed to the function.
    The function should build and run the cadence.

    Args:
        score_class: The Score class to instantiate
        from_request: Function to extract score kwargs from request.
            If None, uses request.json for POST/PUT, request.args for GET.

    Example:
        @app.route("/orders", methods=["POST"])
        @with_cadence(OrderScore)
        def create_order(score: OrderScore):
            cadence = (
                Cadence("create_order", score)
                .then("validate", validate)
                .then("process", process)
            )
            return asyncio.run(cadence.run())
    """
    flask = _get_flask()

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract data from request
            if from_request is not None:
                data: dict[str, Any] = from_request(flask.request)
            elif flask.request.method in ("POST", "PUT", "PATCH"):
                data = flask.request.get_json(silent=True) or {}
            else:
                data = dict(flask.request.args)

            # Merge with URL parameters
            data.update(kwargs)

            # Create score
            score = score_class(**data)
            if hasattr(score, "__post_init__"):
                score.__post_init__()

            # Call function with score
            return fn(score, *args)

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
            score_factory=lambda req: OrderScore(**req.json),
        )

        orders.register_cadence(
            "/<order_id>",
            get_order_cadence,
            methods=["GET"],
            score_factory=lambda req, order_id: OrderScore(order_id=order_id),
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
    def blueprint(self) -> Any:
        """Get the underlying Flask Blueprint."""
        return self._blueprint

    def register_cadence(
        self,
        rule: str,
        cadence: Cadence[ScoreT],
        *,
        methods: list[str] | None = None,
        score_factory: Callable[..., ScoreT] | None = None,
        response_factory: Callable[[ScoreT], Any] | None = None,
        error_handler: Callable[[Exception], Any] | None = None,
        endpoint: str | None = None,
    ) -> None:
        """
        Register a cadence at a URL rule.

        Args:
            rule: URL rule (e.g., "/" or "/<order_id>")
            cadence: Cadence to execute
            methods: HTTP methods (default: ["GET"])
            score_factory: Function to create score.
                Receives (request, **url_params) and returns ScoreT.
            response_factory: Function to convert score to response
            error_handler: Function to handle errors
            endpoint: Endpoint name (default: cadence name)
        """
        flask = _get_flask()
        methods = methods or ["GET"]
        endpoint = endpoint or cadence._name

        def view_func(**url_kwargs: Any) -> Any:
            try:
                # Build score
                if score_factory is not None:
                    score = score_factory(flask.request, **url_kwargs)
                else:
                    # Default: use request JSON + URL params
                    data: dict[str, Any] = {}
                    if flask.request.method in ("POST", "PUT", "PATCH"):
                        data = flask.request.get_json(silent=True) or {}
                    data.update(url_kwargs)

                    # Try to instantiate score class from cadence's initial score
                    score_class = type(cadence._score)
                    score = score_class(**data)

                # Initialize score
                if hasattr(score, "__post_init__"):
                    score.__post_init__()

                # Clone and run cadence
                from cadence.cadence import Cadence

                cadence_instance = Cadence(cadence._name, score)
                cadence_instance._measures = cadence._measures
                cadence_instance._time_reporter = cadence._time_reporter
                cadence_instance._error_handler = cadence._error_handler
                cadence_instance._stop_on_error = cadence._stop_on_error

                final_score = asyncio.run(cadence_instance.run())

                if response_factory is not None:
                    return response_factory(final_score)
                return final_score

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

    def route(self, rule: str, **options: Any) -> Callable[..., Any]:
        """Standard Flask route decorator (passthrough)."""
        result: Callable[..., Any] = self._blueprint.route(rule, **options)
        return result

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
        self._reporter: Callable[..., Any] | None = None
        self._error_handler: Callable[..., Any] | None = None

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

    def set_reporter(self, reporter: Callable[..., Any]) -> None:
        """Set the default time reporter for all cadences."""
        self._reporter = reporter

    def set_error_handler(self, handler: Callable[..., Any]) -> None:
        """Set the default error handler for all cadences."""
        self._error_handler = handler

    @property
    def reporter(self) -> Callable[..., Any] | None:
        return self._reporter

    @property
    def error_handler(self) -> Callable[..., Any] | None:
        return self._error_handler
