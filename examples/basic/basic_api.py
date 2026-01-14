"""
Basic API Example - User Dashboard

This example demonstrates building a user dashboard endpoint
that fetches data from multiple sources in parallel.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from cadence import Cadence, Score, note, retry, timeout
from cadence.reporters import console_reporter


# --- Score Definition ---

@dataclass
class DashboardScore(Score):
    """Score container for the dashboard cadence."""
    user_id: str

    # Populated by notes
    profile: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    notifications: Optional[List[Dict[str, Any]]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None


# --- Mock Services (replace with real implementations) ---

class UserService:
    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.05)  # Simulate network
        return {"id": user_id, "name": "John Doe", "tier": "premium"}

    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.03)
        return {"theme": "dark", "notifications": True}


class NotificationService:
    async def get_unread(self, user_id: str) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.04)
        return [
            {"id": 1, "message": "Welcome!"},
            {"id": 2, "message": "New feature available"},
        ]


class RecommendationService:
    async def get_recommendations(
        self, profile: Dict, preferences: Dict
    ) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.08)
        return [
            {"id": "item1", "name": "Recommended Product 1"},
            {"id": "item2", "name": "Recommended Product 2"},
        ]


# Initialize services
user_svc = UserService()
notification_svc = NotificationService()
recommendation_svc = RecommendationService()


# --- Note Definitions ---

@note
@retry(max_attempts=3, backoff="exponential")
@timeout(2.0)
async def fetch_profile(score: DashboardScore) -> None:
    """Fetch user profile from user service."""
    score.profile = await user_svc.get_profile(score.user_id)


@note
@timeout(2.0)
async def fetch_preferences(score: DashboardScore) -> None:
    """Fetch user preferences."""
    score.preferences = await user_svc.get_preferences(score.user_id)


@note
@timeout(2.0)
async def fetch_notifications(score: DashboardScore) -> None:
    """Fetch unread notifications."""
    score.notifications = await notification_svc.get_unread(score.user_id)


@note
async def generate_recommendations(score: DashboardScore) -> None:
    """Generate personalized recommendations based on profile and preferences."""
    score.recommendations = await recommendation_svc.get_recommendations(
        score.profile, score.preferences
    )


@note
def log_completion(score: DashboardScore) -> None:
    """Log that the dashboard was successfully built."""
    print(f"\nDashboard ready for user {score.user_id}")
    print(f"  Profile: {score.profile['name']} ({score.profile['tier']})")
    print(f"  Notifications: {len(score.notifications)} unread")
    print(f"  Recommendations: {len(score.recommendations)} items")


# --- Cadence Definition ---

def create_dashboard_cadence(user_id: str) -> Cadence[DashboardScore]:
    """Create the dashboard cadence for a given user."""
    return (
        Cadence("dashboard", DashboardScore(user_id=user_id))
        .with_reporter(console_reporter)
        .sync("fetch_user_data", [
            fetch_profile,
            fetch_preferences,
            fetch_notifications,
        ])
        .then("recommendations", generate_recommendations)
        .then("complete", log_completion)
        .on_error(lambda score, err: print(f"Error: {err}"))
    )


# --- Main ---

async def main():
    print("Building user dashboard...\n")

    cadence = create_dashboard_cadence(user_id="user_123")
    result = await cadence.run()

    print(f"\nFinal context:")
    print(f"  recommendations = {result.recommendations}")


if __name__ == "__main__":
    asyncio.run(main())
