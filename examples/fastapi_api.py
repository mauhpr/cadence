"""
FastAPI Integration Example - User Registration API

This example demonstrates using Cadence with FastAPI to build
a user registration API with validation, enrichment, and notifications.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, EmailStr

from cadence import Cadence, Context, beat, retry, timeout, fallback, LoggingHooks
from cadence.integrations.fastapi import with_cadence, CadenceDependency

# Conditional import for FastAPI
try:
    from fastapi import FastAPI, HTTPException, Depends
    from fastapi.responses import JSONResponse
except ImportError:
    print("FastAPI not installed. Run: pip install cadence[fastapi]")
    raise


# --- Pydantic Models (Request/Response) ---


class UserRegistrationRequest(BaseModel):
    """Request model for user registration."""
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    """Response model for user data."""
    id: str
    email: str
    username: str
    full_name: str | None
    verified: bool
    profile_complete: bool


class RegistrationResponse(BaseModel):
    """Response model for registration endpoint."""
    user: UserResponse
    message: str
    verification_sent: bool


# --- Context Definition ---


@dataclass
class RegistrationContext(Context):
    """Context container for the registration cadence."""
    email: str
    username: str
    password: str
    full_name: str | None = None

    # Populated by beats
    user_id: str | None = None
    password_hash: str | None = None
    email_valid: bool = False
    username_available: bool = False
    user_created: bool = False
    verification_sent: bool = False
    welcome_sent: bool = False
    analytics_tracked: bool = False
    errors: list[str] = field(default_factory=list)


# --- Mock Services ---


class ValidationService:
    """Mock validation service."""

    BLOCKED_DOMAINS = ["spam.com", "fake.org"]
    TAKEN_USERNAMES = ["admin", "root", "system"]

    async def validate_email(self, email: str) -> bool:
        await asyncio.sleep(0.01)
        domain = email.split("@")[1] if "@" in email else ""
        return domain not in self.BLOCKED_DOMAINS

    async def check_username(self, username: str) -> bool:
        await asyncio.sleep(0.01)
        return username.lower() not in self.TAKEN_USERNAMES


class UserDatabase:
    """Mock user database."""

    _users: dict[str, dict] = {}
    _next_id = 1

    async def create_user(
        self,
        email: str,
        username: str,
        password_hash: str,
        full_name: str | None,
    ) -> str:
        await asyncio.sleep(0.02)
        user_id = f"user_{self._next_id}"
        UserDatabase._next_id += 1
        UserDatabase._users[user_id] = {
            "id": user_id,
            "email": email,
            "username": username,
            "password_hash": password_hash,
            "full_name": full_name,
            "verified": False,
        }
        return user_id

    async def get_user(self, user_id: str) -> dict | None:
        await asyncio.sleep(0.005)
        return UserDatabase._users.get(user_id)


class NotificationService:
    """Mock notification service."""

    async def send_verification_email(self, email: str, user_id: str) -> bool:
        await asyncio.sleep(0.03)
        print(f"  [Email] Verification sent to {email}")
        return True

    async def send_welcome_email(self, email: str, username: str) -> bool:
        await asyncio.sleep(0.02)
        print(f"  [Email] Welcome sent to {email}")
        return True


class AnalyticsService:
    """Mock analytics service."""

    async def track_registration(self, user_id: str, source: str = "api") -> None:
        await asyncio.sleep(0.01)
        print(f"  [Analytics] Tracked registration for {user_id}")


# Initialize services
validation_svc = ValidationService()
user_db = UserDatabase()
notification_svc = NotificationService()
analytics_svc = AnalyticsService()


# --- Beat Definitions ---


@beat
@timeout(1.0)
async def validate_email(ctx: RegistrationContext) -> None:
    """Validate email format and domain."""
    ctx.email_valid = await validation_svc.validate_email(ctx.email)
    if not ctx.email_valid:
        ctx.errors.append("Email domain is not allowed")


@beat
@timeout(1.0)
async def check_username_availability(ctx: RegistrationContext) -> None:
    """Check if username is available."""
    ctx.username_available = await validation_svc.check_username(ctx.username)
    if not ctx.username_available:
        ctx.errors.append(f"Username '{ctx.username}' is not available")


@beat
def hash_password(ctx: RegistrationContext) -> None:
    """Hash the user's password."""
    # In production, use bcrypt or argon2
    ctx.password_hash = f"hashed_{ctx.password[::-1]}"


@beat
async def check_validation_results(ctx: RegistrationContext) -> bool | None:
    """Check if validation passed. Returns True to stop cadence if failed."""
    if ctx.errors:
        return True  # Interrupt cadence
    return None  # Continue


@beat
@retry(max_attempts=3, backoff="exponential", delay=0.1)
@timeout(2.0)
async def create_user(ctx: RegistrationContext) -> None:
    """Create user in database."""
    ctx.user_id = await user_db.create_user(
        email=ctx.email,
        username=ctx.username,
        password_hash=ctx.password_hash or "",
        full_name=ctx.full_name,
    )
    ctx.user_created = True


@beat
@retry(max_attempts=2)
@timeout(3.0)
async def send_verification_email(ctx: RegistrationContext) -> None:
    """Send email verification link."""
    if ctx.user_id:
        ctx.verification_sent = await notification_svc.send_verification_email(
            ctx.email, ctx.user_id
        )


@beat
@timeout(2.0)
@fallback(False)
async def send_welcome_email(ctx: RegistrationContext) -> None:
    """Send welcome email (non-critical)."""
    ctx.welcome_sent = await notification_svc.send_welcome_email(
        ctx.email, ctx.username
    )


@beat
@fallback(None)
async def track_analytics(ctx: RegistrationContext) -> None:
    """Track registration in analytics (non-critical)."""
    if ctx.user_id:
        await analytics_svc.track_registration(ctx.user_id)
        ctx.analytics_tracked = True


# --- Cadence Factory ---


def create_registration_cadence(ctx: RegistrationContext) -> Cadence[RegistrationContext]:
    """Create the user registration cadence."""
    return (
        Cadence("user_registration", ctx)
        .with_hooks(LoggingHooks())
        # Validation phase (parallel)
        .sync("validate", [
            validate_email,
            check_username_availability,
            hash_password,
        ])
        # Check validation results
        .then("check_validation", check_validation_results)
        # Create user
        .then("create_user", create_user)
        # Notifications (parallel, non-blocking)
        .sync("notify", [
            send_verification_email,
            send_welcome_email,
            track_analytics,
        ])
    )


# --- FastAPI Application ---


app = FastAPI(
    title="Cadence FastAPI Example",
    description="User Registration API demonstrating Cadence integration",
    version="1.0.0",
)


# Method 1: Using @with_cadence decorator
@app.post("/register", response_model=RegistrationResponse)
@with_cadence(
    create_registration_cadence,
    response_mapper=lambda ctx: RegistrationResponse(
        user=UserResponse(
            id=ctx.user_id or "",
            email=ctx.email,
            username=ctx.username,
            full_name=ctx.full_name,
            verified=False,
            profile_complete=bool(ctx.full_name),
        ),
        message="Registration successful" if ctx.user_created else "Registration failed",
        verification_sent=ctx.verification_sent,
    ),
)
def register_user(request: UserRegistrationRequest) -> RegistrationContext:
    """
    Register a new user.

    This endpoint uses the @with_cadence decorator which:
    1. Takes the returned context and passes it to the cadence
    2. Runs the cadence
    3. Maps the result using response_mapper
    """
    return RegistrationContext(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
    )


# Method 2: Using CadenceDependency for more control
registration_cadence_dep = CadenceDependency(
    Cadence("registration_template", RegistrationContext(email="", username="", password=""))
)


@app.post("/register/v2", response_model=RegistrationResponse)
async def register_user_v2(
    request: UserRegistrationRequest,
    execute_cadence=Depends(registration_cadence_dep),
):
    """
    Register a new user (alternative method using dependency injection).

    This method gives you more control over the cadence execution.
    """
    # Create context
    ctx = RegistrationContext(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
    )

    # Create and run cadence manually
    cadence = create_registration_cadence(ctx)
    result = await cadence.run()

    # Check for validation errors
    if result.errors:
        raise HTTPException(status_code=400, detail={"errors": result.errors})

    # Build response
    return RegistrationResponse(
        user=UserResponse(
            id=result.user_id or "",
            email=result.email,
            username=result.username,
            full_name=result.full_name,
            verified=False,
            profile_complete=bool(result.full_name),
        ),
        message="Registration successful",
        verification_sent=result.verification_sent,
    )


# Method 3: Manual cadence execution (most flexible)
@app.post("/register/v3")
async def register_user_v3(request: UserRegistrationRequest) -> dict[str, Any]:
    """
    Register a new user (manual cadence execution).

    This method shows direct cadence execution without helpers.
    """
    ctx = RegistrationContext(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
    )

    cadence = create_registration_cadence(ctx)

    try:
        result = await cadence.run()

        if result.errors:
            return JSONResponse(
                status_code=400,
                content={"success": False, "errors": result.errors},
            )

        return {
            "success": True,
            "user_id": result.user_id,
            "verification_sent": result.verification_sent,
            "welcome_sent": result.welcome_sent,
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "registration-api"}


# --- Main ---


if __name__ == "__main__":
    import uvicorn

    print("Starting FastAPI User Registration API...")
    print()
    print("Endpoints:")
    print("  POST /register      - Using @with_cadence decorator")
    print("  POST /register/v2   - Using CadenceDependency")
    print("  POST /register/v3   - Manual cadence execution")
    print("  GET  /health        - Health check")
    print()
    print("Try:")
    print('  curl -X POST http://localhost:8000/register \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"email": "user@example.com", "username": "newuser", "password": "secret123"}\'')
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)
