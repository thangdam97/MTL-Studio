"""
Scene Planning package (v1.6 Stage 1).

Provides a lightweight planning agent that extracts narrative beats and
chapter-local character rhythm profiles before translation.
"""

from .scene_planner import (
    CharacterProfile,
    SceneBeat,
    ScenePlan,
    ScenePlanningAgent,
    ScenePlanningError,
)

__all__ = [
    "CharacterProfile",
    "SceneBeat",
    "ScenePlan",
    "ScenePlanningAgent",
    "ScenePlanningError",
]

