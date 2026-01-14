"""Tests for Flask integration.

Tests cover:
- Flask import check
- cadence_route decorator
- with_cadence decorator
- CadenceBlueprint
- CadenceExtension
- Error handling
"""

from dataclasses import dataclass

import pytest

from cadence import Cadence, Score, note

# Check if Flask is available
try:
    from flask import Flask
    from flask.testing import FlaskClient

    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    Flask = None  # type: ignore[misc, assignment]
    FlaskClient = None  # type: ignore[misc, assignment]

pytestmark = pytest.mark.skipif(not HAS_FLASK, reason="Flask not installed")


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class FlaskTestScore(Score):
    """Score for Flask integration tests."""
    value: str = ""
    processed: bool = False
    error: str | None = None


@pytest.fixture
def test_score() -> FlaskTestScore:
    """Provide a fresh score for each test."""
    score = FlaskTestScore()
    score.__post_init__()
    return score


@pytest.fixture
def app() -> Flask:
    """Create a test Flask app."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create a test client."""
    return app.test_client()


# Sample notes for testing
@note
async def process_request(score: FlaskTestScore) -> None:
    """Process the request."""
    score.processed = True
    score.value = "processed"


@note
async def failing_note(score: FlaskTestScore) -> None:
    """Raise an error."""
    raise ValueError("Processing failed")


# =============================================================================
# Test: Flask Import Check
# =============================================================================


class TestFlaskImportCheck:
    """Tests for Flask import validation."""

    def test_get_flask_success(self):
        """_get_flask should return flask module when available."""
        from cadence.integrations.flask import _get_flask

        flask = _get_flask()
        assert flask is not None
        assert hasattr(flask, "Flask")

    def test_get_flask_returns_module(self):
        """_get_flask should return the flask module."""
        from cadence.integrations.flask import _get_flask

        flask = _get_flask()
        # Verify it's the actual flask module
        from flask import Flask as RealFlask
        assert flask.Flask is RealFlask


# =============================================================================
# Test: cadence_route Decorator
# =============================================================================


class TestCadenceRouteDecorator:
    """Tests for cadence_route decorator."""

    def test_cadence_route_basic(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should execute cadence and return result."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("test", test_score).then("process", process_request)

        # Flask needs a response_factory to convert Score to dict
        def to_dict(score):
            return {"value": score.value, "processed": score.processed}

        @app.route("/test", methods=["POST"])
        @cadence_route(cadence, response_factory=to_dict)
        def test_endpoint():
            return FlaskTestScore()

        client = app.test_client()
        response = client.post("/test")

        assert response.status_code == 200

    def test_cadence_route_with_score_factory(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should use score_factory when provided."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("test", test_score).then("process", process_request)

        def make_score(request):
            score = FlaskTestScore(value="from_factory")
            score.__post_init__()
            return score

        def to_dict(score):
            return {"value": score.value, "processed": score.processed}

        @app.route("/factory", methods=["POST"])
        @cadence_route(cadence, score_factory=make_score, response_factory=to_dict)
        def factory_endpoint():
            pass  # score_factory handles score creation

        client = app.test_client()
        response = client.post("/factory")

        assert response.status_code == 200

    def test_cadence_route_with_response_factory(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should use response_factory when provided."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("test", test_score).then("process", process_request)

        def make_response(score):
            return {"custom": True, "value": score.value}

        @app.route("/response", methods=["POST"])
        @cadence_route(cadence, response_factory=make_response)
        def response_endpoint():
            return FlaskTestScore()

        client = app.test_client()
        response = client.post("/response")

        assert response.status_code == 200
        data = response.get_json()
        assert data["custom"] is True

    def test_cadence_route_error_without_score(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should raise when no score and no factory."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("test", test_score).then("process", process_request)

        @app.route("/no_score", methods=["POST"])
        @cadence_route(cadence)
        def no_score_endpoint():
            return None  # Returns None without score_factory

        # Flask propagates ValueError when endpoint returns None without score_factory
        with pytest.raises(ValueError, match="must return score or provide score_factory"):
            client = app.test_client()
            client.post("/no_score")

    def test_cadence_route_preserves_function_name(self, test_score: FlaskTestScore):
        """cadence_route should preserve the decorated function's name."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("test", test_score)

        @cadence_route(cadence)
        def my_endpoint():
            return FlaskTestScore()

        assert my_endpoint.__name__ == "my_endpoint"


# =============================================================================
# Test: with_cadence Decorator
# =============================================================================


class TestWithCadenceDecorator:
    """Tests for with_cadence decorator."""

    def test_with_cadence_injects_score(self, app: Flask):
        """with_cadence should inject score into view function."""
        from cadence.integrations.flask import with_cadence

        received_score = []

        @app.route("/inject", methods=["POST"])
        @with_cadence(FlaskTestScore)
        def inject_endpoint(score: FlaskTestScore):
            received_score.append(score)
            return {"received": True}

        client = app.test_client()
        response = client.post(
            "/inject",
            json={"value": "test_value"},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert len(received_score) == 1
        assert received_score[0].value == "test_value"

    def test_with_cadence_get_request(self, app: Flask):
        """with_cadence should use query params for GET requests."""
        from cadence.integrations.flask import with_cadence

        received_score = []

        @app.route("/get_inject", methods=["GET"])
        @with_cadence(FlaskTestScore)
        def get_inject_endpoint(score: FlaskTestScore):
            received_score.append(score)
            return {"received": True}

        client = app.test_client()
        response = client.get("/get_inject?value=from_query")

        assert response.status_code == 200
        assert len(received_score) == 1
        assert received_score[0].value == "from_query"

    def test_with_cadence_custom_from_request(self, app: Flask):
        """with_cadence should use custom from_request function."""
        from cadence.integrations.flask import with_cadence

        def custom_extractor(request):
            return {"value": "custom_extracted"}

        received_score = []

        @app.route("/custom", methods=["POST"])
        @with_cadence(FlaskTestScore, from_request=custom_extractor)
        def custom_endpoint(score: FlaskTestScore):
            received_score.append(score)
            return {"received": True}

        client = app.test_client()
        response = client.post("/custom")

        assert response.status_code == 200
        assert received_score[0].value == "custom_extracted"

    def test_with_cadence_no_url_params(self, app: Flask):
        """with_cadence should work without URL parameters."""
        from cadence.integrations.flask import with_cadence

        received_scores = []

        @app.route("/simple", methods=["POST"])
        @with_cadence(FlaskTestScore)
        def simple_endpoint(score: FlaskTestScore):
            received_scores.append(score)
            return {"received": True, "value": score.value}

        client = app.test_client()
        response = client.post(
            "/simple",
            json={"value": "test_value"},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert len(received_scores) == 1
        assert received_scores[0].value == "test_value"


# =============================================================================
# Test: CadenceBlueprint
# =============================================================================


class TestCadenceBlueprint:
    """Tests for CadenceBlueprint class."""

    def test_blueprint_creation(self):
        """CadenceBlueprint should create underlying Flask Blueprint."""
        from cadence.integrations.flask import CadenceBlueprint

        bp = CadenceBlueprint("test_bp", __name__)

        assert bp.blueprint is not None
        assert bp.blueprint.name == "test_bp"

    def test_blueprint_with_url_prefix(self):
        """CadenceBlueprint should pass url_prefix to Blueprint."""
        from cadence.integrations.flask import CadenceBlueprint

        bp = CadenceBlueprint("prefixed", __name__, url_prefix="/api")

        assert bp.blueprint.url_prefix == "/api"

    def test_register_cadence(self, app: Flask, test_score: FlaskTestScore):
        """register_cadence should add route for cadence."""
        from cadence.integrations.flask import CadenceBlueprint

        cadence = Cadence("bp_test", test_score).then("process", process_request)

        def to_dict(score):
            return {"value": score.value, "processed": score.processed}

        bp = CadenceBlueprint("orders", __name__, url_prefix="/orders")
        bp.register_cadence(
            "/",
            cadence,
            methods=["POST"],
            score_factory=lambda req: FlaskTestScore(),
            response_factory=to_dict,
        )

        app.register_blueprint(bp.blueprint)

        client = app.test_client()
        response = client.post("/orders/")

        assert response.status_code == 200

    def test_register_cadence_with_response_factory(
        self, app: Flask, test_score: FlaskTestScore
    ):
        """register_cadence should use response_factory."""
        from cadence.integrations.flask import CadenceBlueprint

        cadence = Cadence("bp_response", test_score).then("process", process_request)

        def make_response(score):
            return {"blueprint_response": True}

        bp = CadenceBlueprint("responses", __name__)
        bp.register_cadence(
            "/custom",
            cadence,
            methods=["POST"],
            score_factory=lambda req: FlaskTestScore(),
            response_factory=make_response,
        )

        app.register_blueprint(bp.blueprint)

        client = app.test_client()
        response = client.post("/custom")

        assert response.status_code == 200
        data = response.get_json()
        assert data["blueprint_response"] is True

    def test_blueprint_route_passthrough(self, app: Flask):
        """CadenceBlueprint.route should work as standard decorator."""
        from cadence.integrations.flask import CadenceBlueprint

        bp = CadenceBlueprint("standard", __name__)

        @bp.route("/standard")
        def standard_route():
            return {"standard": True}

        app.register_blueprint(bp.blueprint)

        client = app.test_client()
        response = client.get("/standard")

        assert response.status_code == 200
        assert response.get_json()["standard"] is True

    def test_blueprint_getattr_delegation(self):
        """CadenceBlueprint should delegate unknown attributes to Blueprint."""
        from cadence.integrations.flask import CadenceBlueprint

        bp = CadenceBlueprint("delegate", __name__)

        # name is a Blueprint attribute
        assert bp.name == "delegate"


# =============================================================================
# Test: CadenceExtension
# =============================================================================


class TestCadenceExtension:
    """Tests for CadenceExtension Flask extension."""

    def test_extension_init_with_app(self, app: Flask):
        """CadenceExtension should initialize with app."""
        from cadence.integrations.flask import CadenceExtension

        ext = CadenceExtension(app)

        assert "cadence" in app.extensions
        assert app.extensions["cadence"] is ext

    def test_extension_init_app_later(self, app: Flask):
        """CadenceExtension should support init_app pattern."""
        from cadence.integrations.flask import CadenceExtension

        ext = CadenceExtension()
        ext.init_app(app)

        assert "cadence" in app.extensions
        assert app.extensions["cadence"] is ext

    def test_extension_set_reporter(self):
        """CadenceExtension should store reporter."""
        from cadence.integrations.flask import CadenceExtension

        ext = CadenceExtension()

        def my_reporter(data):
            pass

        ext.set_reporter(my_reporter)

        assert ext.reporter is my_reporter

    def test_extension_set_error_handler(self):
        """CadenceExtension should store error handler."""
        from cadence.integrations.flask import CadenceExtension

        ext = CadenceExtension()

        def my_handler(e):
            pass

        ext.set_error_handler(my_handler)

        assert ext.error_handler is my_handler

    def test_extension_initial_state(self):
        """CadenceExtension should start with no reporter or handler."""
        from cadence.integrations.flask import CadenceExtension

        ext = CadenceExtension()

        assert ext.reporter is None
        assert ext.error_handler is None


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestFlaskErrorHandling:
    """Tests for error handling in Flask integration."""

    def test_cadence_route_error_handler(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should use custom error_handler."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("failing", test_score).then("fail", failing_note)

        errors_caught = []

        def handle_error(e):
            errors_caught.append(e)
            return {"error": "handled"}, 400

        @app.route("/error", methods=["POST"])
        @cadence_route(cadence, error_handler=handle_error)
        def error_endpoint():
            return FlaskTestScore()

        client = app.test_client()
        response = client.post("/error")

        assert response.status_code == 400
        assert len(errors_caught) == 1
        data = response.get_json()
        assert data["error"] == "handled"

    def test_cadence_route_error_propagates(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should propagate errors without handler."""
        from cadence.integrations.flask import cadence_route
        from cadence.exceptions import NoteError

        cadence = Cadence("failing", test_score).then("fail", failing_note)

        @app.route("/propagate", methods=["POST"])
        @cadence_route(cadence)
        def propagate_endpoint():
            return FlaskTestScore()

        # Flask propagates NoteError without error_handler
        with pytest.raises(NoteError):
            client = app.test_client()
            client.post("/propagate")

    def test_blueprint_error_handler(self, app: Flask, test_score: FlaskTestScore):
        """CadenceBlueprint register_cadence should use error_handler."""
        from cadence.integrations.flask import CadenceBlueprint

        cadence = Cadence("bp_failing", test_score).then("fail", failing_note)

        errors_caught = []

        def handle_error(e):
            errors_caught.append(e)
            return {"bp_error": "handled"}, 422

        bp = CadenceBlueprint("errors", __name__)
        bp.register_cadence(
            "/bp_error",
            cadence,
            methods=["POST"],
            score_factory=lambda req: FlaskTestScore(),
            error_handler=handle_error,
        )

        app.register_blueprint(bp.blueprint)

        client = app.test_client()
        response = client.post("/bp_error")

        assert response.status_code == 422
        assert len(errors_caught) == 1


# =============================================================================
# Test: Score Initialization
# =============================================================================


class TestScoreInitialization:
    """Tests for automatic score initialization."""

    def test_cadence_route_initializes_score(self, app: Flask, test_score: FlaskTestScore):
        """cadence_route should initialize score if needed."""
        from cadence.integrations.flask import cadence_route

        cadence = Cadence("init_test", test_score).then("process", process_request)

        def to_dict(score):
            return {"value": score.value, "processed": score.processed}

        @app.route("/init", methods=["POST"])
        @cadence_route(cadence, response_factory=to_dict)
        def init_endpoint():
            # Return uninitialized score
            return FlaskTestScore(value="initial")

        client = app.test_client()
        response = client.post("/init")

        assert response.status_code == 200

    def test_with_cadence_initializes_score(self, app: Flask):
        """with_cadence should initialize score."""
        from cadence.integrations.flask import with_cadence

        received_scores = []

        @app.route("/with_init", methods=["POST"])
        @with_cadence(FlaskTestScore)
        def with_init_endpoint(score: FlaskTestScore):
            received_scores.append(score)
            # Check that score has _original_values (set by __post_init__)
            has_init = hasattr(score, "_original_values")
            return {"initialized": has_init}

        client = app.test_client()
        response = client.post(
            "/with_init",
            json={"value": "test"},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["initialized"] is True


# =============================================================================
# Test: Integration Patterns
# =============================================================================


class TestIntegrationPatterns:
    """Tests for common integration patterns."""

    def test_simple_post_endpoint(self, app: Flask):
        """Simple POST endpoint pattern should work."""
        from cadence.integrations.flask import cadence_route

        @note
        async def validate(score: FlaskTestScore) -> None:
            if not score.value:
                score.value = "default"

        @note
        async def process(score: FlaskTestScore) -> None:
            score.processed = True

        # Create template score for cadence definition
        template_score = FlaskTestScore()
        template_score.__post_init__()

        cadence = (
            Cadence("simple", template_score)
            .then("validate", validate)
            .then("process", process)
        )

        def to_dict(score):
            return {"value": score.value, "processed": score.processed}

        # Let endpoint return the score directly (not using score_factory)
        # This way the cadence_route uses the returned score
        @app.route("/simple", methods=["POST"])
        @cadence_route(cadence, response_factory=to_dict)
        def simple_endpoint():
            score = FlaskTestScore()
            score.__post_init__()
            return score

        client = app.test_client()
        response = client.post("/simple")

        assert response.status_code == 200
        # Note: Due to measure binding, template_score is modified
        # The returned score is used but measures modify template_score
        assert template_score.processed is True

    def test_blueprint_with_url_params(self, app: Flask, test_score: FlaskTestScore):
        """Blueprint with URL parameters should work."""
        from cadence.integrations.flask import CadenceBlueprint

        received_ids = []

        def make_score(request, item_id):
            received_ids.append(item_id)
            score = FlaskTestScore(value=item_id)
            score.__post_init__()
            return score

        def to_dict(score):
            return {"value": score.value, "processed": score.processed}

        cadence = Cadence("item", test_score).then("process", process_request)

        bp = CadenceBlueprint("items", __name__, url_prefix="/items")
        bp.register_cadence(
            "/<item_id>",
            cadence,
            methods=["GET"],
            score_factory=make_score,
            response_factory=to_dict,
        )

        app.register_blueprint(bp.blueprint)

        client = app.test_client()
        response = client.get("/items/abc123")

        assert response.status_code == 200
        assert "abc123" in received_ids
