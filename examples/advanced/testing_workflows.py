"""Testing Workflows Example.

This example demonstrates best practices for testing Cadence workflows,
including unit testing notes, testing branching logic, mocking external
dependencies, and integration testing patterns.

Key Concepts:
- Unit testing individual @note functions
- Testing cadence flow logic
- Mocking external services
- Testing error handling
- Testing with custom hooks for observability
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cadence import Cadence, Score, note
from cadence.hooks import CadenceHooks


# =============================================================================
# Application Code (What We're Testing)
# =============================================================================


@dataclass
class UserRegistrationScore(Score):
    """Score for user registration workflow."""
    email: str = ""
    username: str = ""
    password: str = ""
    user_id: str | None = None
    email_verified: bool = False
    profile_created: bool = False
    welcome_email_sent: bool = False
    errors: list[str] = field(default_factory=list)


# Simulated external service clients
class DatabaseClient:
    """Simulated database client."""
    async def create_user(self, email: str, username: str, password_hash: str) -> str:
        # In real code, this would create a user in the database
        return f"user_{hash(email) % 10000:04d}"

    async def user_exists(self, email: str) -> bool:
        return False


class EmailService:
    """Simulated email service."""
    async def send_verification_email(self, email: str, user_id: str) -> bool:
        return True

    async def send_welcome_email(self, email: str, username: str) -> bool:
        return True


# Global service instances (in real code, use dependency injection)
db_client = DatabaseClient()
email_service = EmailService()


@note
async def validate_email(score: UserRegistrationScore) -> None:
    """Validate email format and uniqueness."""
    if not score.email or "@" not in score.email:
        score.errors.append("Invalid email format")
        return

    if await db_client.user_exists(score.email):
        score.errors.append("Email already registered")


@note
async def validate_username(score: UserRegistrationScore) -> None:
    """Validate username requirements."""
    if not score.username or len(score.username) < 3:
        score.errors.append("Username must be at least 3 characters")

    if score.username and not score.username.isalnum():
        score.errors.append("Username must be alphanumeric")


@note
async def check_validation_errors(score: UserRegistrationScore) -> bool:
    """Check if there are validation errors. Returns True to interrupt if errors exist."""
    return len(score.errors) > 0


@note
async def create_user_record(score: UserRegistrationScore) -> None:
    """Create the user in the database."""
    password_hash = f"hashed_{score.password}"  # In real code, use proper hashing
    score.user_id = await db_client.create_user(
        score.email, score.username, password_hash
    )


@note
async def send_verification(score: UserRegistrationScore) -> None:
    """Send email verification."""
    if score.user_id:
        result = await email_service.send_verification_email(score.email, score.user_id)
        score.email_verified = result


@note
async def create_user_profile(score: UserRegistrationScore) -> None:
    """Create user profile with defaults."""
    score.profile_created = True


@note
async def send_welcome(score: UserRegistrationScore) -> None:
    """Send welcome email to user."""
    if score.user_id:
        result = await email_service.send_welcome_email(score.email, score.username)
        score.welcome_email_sent = result


def create_registration_cadence(
    email: str, username: str, password: str
) -> Cadence[UserRegistrationScore]:
    """Create a user registration cadence."""
    score = UserRegistrationScore(email=email, username=username, password=password)
    score.__post_init__()

    return (
        Cadence("user_registration", score)
        # Validation phase
        .then("validate_email", validate_email)
        .then("validate_username", validate_username)
        .then("check_errors", check_validation_errors, can_interrupt=True)
        # Creation phase
        .then("create_user", create_user_record)
        .sync("setup_user", [send_verification, create_user_profile])
        .then("send_welcome", send_welcome)
    )


# =============================================================================
# Test Utilities
# =============================================================================


class TestHooks(CadenceHooks):
    """Hooks for capturing test execution data."""

    def __init__(self):
        self.cadence_started = False
        self.cadence_completed = False
        self.notes_executed: list[str] = []
        self.errors: list[Exception] = []
        self.timings: dict[str, float] = {}

    async def before_cadence(self, cadence_name: str, score: Score) -> None:
        self.cadence_started = True

    async def after_cadence(
        self,
        cadence_name: str,
        score: Score,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self.cadence_completed = True
        self.timings["total"] = duration
        if error:
            self.errors.append(error)

    async def before_note(self, note_name: str, score: Score) -> None:
        pass

    async def after_note(
        self,
        note_name: str,
        score: Score,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self.notes_executed.append(note_name)
        self.timings[note_name] = duration
        if error:
            self.errors.append(error)


# =============================================================================
# Unit Tests for Individual Notes
# =============================================================================


class TestValidateEmail:
    """Unit tests for email validation note."""

    async def test_valid_email_passes(self):
        """Valid email should not add errors."""
        score = UserRegistrationScore(email="test@example.com")
        score.__post_init__()

        # Mock database client to return user doesn't exist
        with patch.object(db_client, "user_exists", return_value=False):
            await validate_email(score)

        assert len(score.errors) == 0

    async def test_invalid_email_format(self):
        """Invalid email format should add error."""
        score = UserRegistrationScore(email="invalid-email")
        score.__post_init__()

        await validate_email(score)

        assert "Invalid email format" in score.errors

    async def test_empty_email(self):
        """Empty email should add error."""
        score = UserRegistrationScore(email="")
        score.__post_init__()

        await validate_email(score)

        assert "Invalid email format" in score.errors

    async def test_duplicate_email(self):
        """Existing email should add error."""
        score = UserRegistrationScore(email="existing@example.com")
        score.__post_init__()

        # Mock database to return user exists
        with patch.object(db_client, "user_exists", return_value=True):
            await validate_email(score)

        assert "Email already registered" in score.errors


class TestValidateUsername:
    """Unit tests for username validation note."""

    async def test_valid_username_passes(self):
        """Valid username should not add errors."""
        score = UserRegistrationScore(username="validuser123")
        score.__post_init__()

        await validate_username(score)

        assert len(score.errors) == 0

    async def test_short_username(self):
        """Username too short should add error."""
        score = UserRegistrationScore(username="ab")
        score.__post_init__()

        await validate_username(score)

        assert "Username must be at least 3 characters" in score.errors

    async def test_non_alphanumeric_username(self):
        """Non-alphanumeric username should add error."""
        score = UserRegistrationScore(username="user@name")
        score.__post_init__()

        await validate_username(score)

        assert "Username must be alphanumeric" in score.errors


# =============================================================================
# Integration Tests for Full Workflow
# =============================================================================


class TestRegistrationCadence:
    """Integration tests for the full registration cadence."""

    async def test_successful_registration(self):
        """Full registration flow should complete successfully."""
        with patch.object(db_client, "user_exists", return_value=False), \
             patch.object(db_client, "create_user", return_value="user_1234"), \
             patch.object(email_service, "send_verification_email", return_value=True), \
             patch.object(email_service, "send_welcome_email", return_value=True):

            cadence = create_registration_cadence(
                email="newuser@example.com",
                username="newuser",
                password="securepass123",
            )
            await cadence.run()
            score = cadence.get_score()

        assert score.user_id == "user_1234"
        assert score.profile_created is True
        assert score.welcome_email_sent is True
        assert len(score.errors) == 0

    async def test_registration_stops_on_validation_error(self):
        """Registration should stop if validation fails."""
        cadence = create_registration_cadence(
            email="invalid-email",  # Invalid format
            username="ab",  # Too short
            password="pass",
        )
        await cadence.run()
        score = cadence.get_score()

        # Should have validation errors
        assert len(score.errors) > 0
        # User should not be created (cadence was interrupted)
        assert score.user_id is None
        assert score.profile_created is False

    async def test_registration_with_hooks(self):
        """Registration should trigger all hooks correctly."""
        hooks = TestHooks()

        with patch.object(db_client, "user_exists", return_value=False), \
             patch.object(db_client, "create_user", return_value="user_1234"), \
             patch.object(email_service, "send_verification_email", return_value=True), \
             patch.object(email_service, "send_welcome_email", return_value=True):

            score = UserRegistrationScore(
                email="test@example.com",
                username="testuser",
                password="pass123",
            )
            score.__post_init__()

            cadence = (
                Cadence("user_registration", score)
                .with_hooks(hooks)
                .then("validate_email", validate_email)
                .then("validate_username", validate_username)
                .then("check_errors", check_validation_errors, can_interrupt=True)
                .then("create_user", create_user_record)
            )
            await cadence.run()

        assert hooks.cadence_started is True
        assert hooks.cadence_completed is True
        assert "validate_email" in hooks.notes_executed
        assert "validate_username" in hooks.notes_executed
        assert "create_user" in hooks.notes_executed
        assert len(hooks.errors) == 0


# =============================================================================
# Testing Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in workflows."""

    async def test_database_error_propagates(self):
        """Database errors should propagate and be catchable."""
        with patch.object(db_client, "user_exists", return_value=False), \
             patch.object(db_client, "create_user", side_effect=Exception("DB Error")):

            cadence = create_registration_cadence(
                email="test@example.com",
                username="testuser",
                password="pass123",
            )

            with pytest.raises(Exception) as exc_info:
                await cadence.run()

            assert "DB Error" in str(exc_info.value)

    async def test_error_handler_captures_errors(self):
        """Custom error handler should capture errors."""
        captured_errors: list[tuple[Any, Exception]] = []

        def error_handler(score: UserRegistrationScore, error: Exception) -> None:
            captured_errors.append((score, error))
            score.errors.append(str(error))

        with patch.object(db_client, "user_exists", return_value=False), \
             patch.object(db_client, "create_user", side_effect=ValueError("Create failed")):

            score = UserRegistrationScore(
                email="test@example.com",
                username="testuser",
                password="pass123",
            )
            score.__post_init__()

            cadence = (
                Cadence("registration", score)
                .on_error(error_handler, stop=True)
                .then("validate_email", validate_email)
                .then("create_user", create_user_record)
            )

            # With error handler, exception is caught but cadence stops
            try:
                await cadence.run()
            except Exception:
                pass

        # Error should be captured
        assert len(captured_errors) >= 1 or "Create failed" in score.errors


# =============================================================================
# Testing Branching Logic
# =============================================================================


@dataclass
class BranchingScore(Score):
    """Score for branching tests."""
    user_type: str = "standard"
    path_taken: str = ""
    features: list[str] = field(default_factory=list)


@note
async def standard_setup(score: BranchingScore) -> None:
    """Standard user setup."""
    score.path_taken = "standard"
    score.features.append("basic_features")


@note
async def premium_setup(score: BranchingScore) -> None:
    """Premium user setup."""
    score.path_taken = "premium"
    score.features.extend(["basic_features", "premium_features", "priority_support"])


def is_premium_user(score: BranchingScore) -> bool:
    """Check if user is premium."""
    return score.user_type == "premium"


class TestBranchingLogic:
    """Tests for workflow branching."""

    async def test_standard_user_path(self):
        """Standard users should take standard path."""
        score = BranchingScore(user_type="standard")
        score.__post_init__()

        cadence = (
            Cadence("setup", score)
            .split(
                "user_type_branch",
                condition=is_premium_user,
                if_true=[premium_setup],
                if_false=[standard_setup],
            )
        )
        await cadence.run()

        assert score.path_taken == "standard"
        assert "basic_features" in score.features
        assert "premium_features" not in score.features

    async def test_premium_user_path(self):
        """Premium users should take premium path."""
        score = BranchingScore(user_type="premium")
        score.__post_init__()

        cadence = (
            Cadence("setup", score)
            .split(
                "user_type_branch",
                condition=is_premium_user,
                if_true=[premium_setup],
                if_false=[standard_setup],
            )
        )
        await cadence.run()

        assert score.path_taken == "premium"
        assert "premium_features" in score.features


# =============================================================================
# Main: Run Examples
# =============================================================================


async def run_example_tests():
    """Run example tests to demonstrate testing patterns."""
    print("=" * 60)
    print("TESTING WORKFLOWS EXAMPLE")
    print("=" * 60)

    # Unit test examples
    print("\n1. Unit Tests for Individual Notes")
    print("-" * 40)

    # Test valid email
    score = UserRegistrationScore(email="test@example.com")
    score.__post_init__()
    with patch.object(db_client, "user_exists", return_value=False):
        await validate_email(score)
    assert len(score.errors) == 0
    print("  [PASS] Valid email passes validation")

    # Test invalid email
    score = UserRegistrationScore(email="invalid")
    score.__post_init__()
    await validate_email(score)
    assert "Invalid email format" in score.errors
    print("  [PASS] Invalid email caught")

    # Integration test example
    print("\n2. Integration Tests")
    print("-" * 40)

    with patch.object(db_client, "user_exists", return_value=False), \
         patch.object(db_client, "create_user", return_value="user_1234"), \
         patch.object(email_service, "send_verification_email", return_value=True), \
         patch.object(email_service, "send_welcome_email", return_value=True):

        cadence = create_registration_cadence(
            email="new@example.com",
            username="newuser",
            password="password123",
        )
        await cadence.run()
        final = cadence.get_score()

    assert final.user_id == "user_1234"
    assert final.profile_created
    print("  [PASS] Full registration flow completed")

    # Hooks test
    print("\n3. Testing with Hooks")
    print("-" * 40)

    hooks = TestHooks()
    with patch.object(db_client, "user_exists", return_value=False), \
         patch.object(db_client, "create_user", return_value="user_5678"):

        score = UserRegistrationScore(
            email="hooked@example.com",
            username="hookeduser",
            password="pass",
        )
        score.__post_init__()

        cadence = (
            Cadence("test", score)
            .with_hooks(hooks)
            .then("validate_email", validate_email)
            .then("create_user", create_user_record)
        )
        await cadence.run()

    assert hooks.cadence_started
    assert hooks.cadence_completed
    assert len(hooks.notes_executed) == 2
    print(f"  [PASS] Hooks captured {len(hooks.notes_executed)} note executions")
    print(f"  [INFO] Notes: {hooks.notes_executed}")

    # Branching test
    print("\n4. Testing Branch Conditions")
    print("-" * 40)

    for user_type in ["standard", "premium"]:
        score = BranchingScore(user_type=user_type)
        score.__post_init__()

        cadence = (
            Cadence("setup", score)
            .split(
                "branch",
                condition=is_premium_user,
                if_true=[premium_setup],
                if_false=[standard_setup],
            )
        )
        await cadence.run()

        print(f"  [PASS] {user_type} user took {score.path_taken} path")

    print("\n" + "=" * 60)
    print("ALL EXAMPLE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_example_tests())
