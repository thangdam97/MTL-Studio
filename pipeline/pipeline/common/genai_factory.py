"""
Unified Google GenAI client factory.

Supports dual-mode initialization:
- Gemini Developer API (API key)
- Vertex AI (API key or ADC)
"""

from __future__ import annotations

import os
from typing import Optional

from google import genai


_TRUTHY = {"1", "true", "yes", "on"}
_BACKEND_ALIASES = {
    "auto": "auto",
    "genai": "developer",
    "developer": "developer",
    "vertex": "vertex",
}
_VALID_BACKENDS = set(_BACKEND_ALIASES.keys())


def _is_truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _normalize_backend(value: Optional[str]) -> Optional[str]:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return None
    return _BACKEND_ALIASES.get(candidate)


def _safe_gemini_config() -> dict:
    """Best-effort config read to avoid import-time circular failures."""
    try:
        from pipeline.config import get_config_section

        return get_config_section("gemini") or {}
    except Exception:
        return {}


def resolve_genai_backend(backend: Optional[str] = None) -> str:
    """
    Resolve backend mode: developer (aka genai), vertex, or auto.

    Priority:
      1) explicit arg
      2) env: GENAI_BACKEND / GEMINI_BACKEND
      3) config.yaml: gemini.backend
      4) auto-detection by environment
    """
    candidate = _normalize_backend(backend)
    if candidate and candidate != "auto":
        return candidate

    env_backend = _normalize_backend(os.getenv("GENAI_BACKEND") or os.getenv("GEMINI_BACKEND"))
    if env_backend and env_backend != "auto":
        return env_backend

    gemini_cfg = _safe_gemini_config()
    cfg_backend = _normalize_backend(gemini_cfg.get("backend", "auto"))
    if cfg_backend and cfg_backend != "auto":
        return cfg_backend

    # Auto detection:
    # If explicitly marked for Vertex or Vertex project/location is present, use vertex.
    if _is_truthy(os.getenv("GOOGLE_GENAI_USE_VERTEXAI")):
        return "vertex"
    if os.getenv("GOOGLE_CLOUD_PROJECT") and os.getenv("GOOGLE_CLOUD_LOCATION"):
        return "vertex"

    return "developer"


def resolve_api_key(api_key: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Resolve API key with compatibility fallback.

    Priority:
      1) explicit arg
      2) GOOGLE_API_KEY
      3) GEMINI_API_KEY (legacy compatibility)
    """
    key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if required and not key:
        raise ValueError(
            "API key not found. Set GOOGLE_API_KEY (preferred) or GEMINI_API_KEY."
        )
    return key


def _resolve_vertex_project(project: Optional[str] = None) -> Optional[str]:
    gemini_cfg = _safe_gemini_config()
    vertex_cfg = gemini_cfg.get("vertex", {}) if isinstance(gemini_cfg, dict) else {}
    return project or os.getenv("GOOGLE_CLOUD_PROJECT") or vertex_cfg.get("project")


def _resolve_vertex_location(location: Optional[str] = None) -> Optional[str]:
    gemini_cfg = _safe_gemini_config()
    vertex_cfg = gemini_cfg.get("vertex", {}) if isinstance(gemini_cfg, dict) else {}
    return (
        location
        or os.getenv("GOOGLE_CLOUD_LOCATION")
        or vertex_cfg.get("location")
        or "us-central1"
    )


def create_genai_client(
    *,
    api_key: Optional[str] = None,
    backend: Optional[str] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
) -> genai.Client:
    """
    Create a google.genai.Client in developer or vertex mode.
    """
    resolved_backend = resolve_genai_backend(backend)

    if resolved_backend == "developer":
        key = resolve_api_key(api_key=api_key, required=True)
        return genai.Client(api_key=key)

    # Vertex mode (supports API key and/or ADC)
    vertex_project = _resolve_vertex_project(project)
    vertex_location = _resolve_vertex_location(location)
    key = resolve_api_key(api_key=api_key, required=False)

    if not vertex_project:
        # Graceful fallback for CLI hot-switch use: if Vertex is unavailable,
        # fall back to Developer API when API key is present.
        if key:
            return genai.Client(api_key=key)
        raise ValueError(
            "Vertex backend requires GOOGLE_CLOUD_PROJECT (or gemini.vertex.project in config.yaml), "
            "or GOOGLE_API_KEY/GEMINI_API_KEY for fallback."
        )

    kwargs = {
        "vertexai": True,
        "project": vertex_project,
        "location": vertex_location,
    }
    if key:
        kwargs["api_key"] = key

    try:
        return genai.Client(**kwargs)
    except Exception:
        if key:
            return genai.Client(api_key=key)
        raise
