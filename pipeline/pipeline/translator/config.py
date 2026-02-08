"""
Translator Configuration Loader.
Loads settings from the global config.yaml and provides typed accessors.
Supports multi-language configuration (EN, VN, etc.)
"""

from pathlib import Path
from typing import Dict, Any, Optional
from pipeline.config import (
    get_config_section, get_target_language, get_language_config,
    PIPELINE_ROOT
)

# Module constants
MODULE_NAME = "translator"


def get_gemini_config() -> Dict[str, Any]:
    """Get Gemini API configuration."""
    return get_config_section("gemini")


def get_translation_config() -> Dict[str, Any]:
    """Get translation-specific settings."""
    return get_config_section("translation")


def get_master_prompt_path(target_language: str = None) -> Path:
    """
    Get absolute path to master prompt file.

    Args:
        target_language: Language code (e.g., 'en', 'vn').
                        If None, uses current target language from config.

    Returns:
        Absolute path to the master prompt file.
    """
    if target_language is None:
        target_language = get_target_language()

    lang_config = get_language_config(target_language)
    relative_path = lang_config.get("master_prompt")

    if not relative_path:
        raise ValueError(f"Master prompt not configured for language: {target_language}")

    return PIPELINE_ROOT / relative_path


def get_modules_directory(target_language: str = None) -> Path:
    """
    Get absolute path to RAG modules directory.

    Args:
        target_language: Language code (e.g., 'en', 'vn').
                        If None, uses current target language from config.

    Returns:
        Absolute path to the modules directory.
    """
    if target_language is None:
        target_language = get_target_language()

    lang_config = get_language_config(target_language)
    relative_path = lang_config.get("modules_dir", "modules/")

    return PIPELINE_ROOT / relative_path


def get_genre_prompt_path(genre: str, target_language: str = None) -> Path:
    """
    Get path to genre-specific prompt.

    Args:
        genre: Genre key (e.g., 'romcom', 'fantasy')
        target_language: Language code. If None, uses current target language.

    Returns:
        Absolute path to the genre-specific prompt file.
    """
    if target_language is None:
        target_language = get_target_language()

    lang_config = get_language_config(target_language)
    prompts = lang_config.get("prompts", {})

    if genre not in prompts:
        # Fall back to master prompt
        return get_master_prompt_path(target_language)

    return PIPELINE_ROOT / prompts[genre]

def get_lookback_chapters() -> int:
    """Get number of chapters to include for context continuity."""
    config = get_translation_config()
    return config.get("context", {}).get("lookback_chapters", 2)

def get_quality_threshold() -> float:
    """Get minimum contraction rate threshold."""
    config = get_translation_config()
    return config.get("quality", {}).get("contraction_rate_min", 0.80)

def get_safety_settings() -> Dict[str, str]:
    """Get safety settings for Gemini."""
    gemini_conf = get_gemini_config()
    return gemini_conf.get("safety", {})

def get_model_name() -> str:
    """Get configured model name."""
    return get_gemini_config().get("model", "gemini-2.5-pro")

def get_fallback_model_name() -> str:
    """Get configured fallback model name."""
    return get_gemini_config().get("fallback_model", "gemini-2.5-flash")

def get_generation_params() -> Dict[str, Any]:
    """Get generation parameters (temperature, tokens, etc)."""
    return get_gemini_config().get("generation", {})


def get_rate_limit_config() -> Dict[str, Any]:
    """Get rate limiting configuration."""
    gemini_conf = get_gemini_config()
    rate_limit = gemini_conf.get("rate_limit", {})
    return {
        "requests_per_minute": rate_limit.get("requests_per_minute", 10),
        "retry_attempts": rate_limit.get("retry_attempts", 3),
        "retry_delay_seconds": rate_limit.get("retry_delay_seconds", 5),
    }


def get_caching_config() -> Dict[str, Any]:
    """Get caching configuration."""
    gemini_conf = get_gemini_config()
    caching = gemini_conf.get("caching", {})
    return {
        "enabled": caching.get("enabled", True),
        "ttl_minutes": caching.get("ttl_minutes", 120),
    }


def is_name_consistency_enabled() -> bool:
    """Check if character name consistency is enforced."""
    config = get_translation_config()
    return config.get("context", {}).get("enforce_name_consistency", True)


def get_quality_thresholds() -> Dict[str, Any]:
    """Get quality threshold settings."""
    config = get_translation_config()
    quality = config.get("quality", {})
    return {
        "contraction_rate_min": quality.get("contraction_rate_min", 0.80),
        "max_ai_isms_per_chapter": quality.get("max_ai_isms_per_chapter", 5),
    }


def get_ai_ism_patterns() -> list:
    """Get list of AI-ism patterns to detect."""
    critics_config = get_config_section("critics")
    return critics_config.get("ai_ism_patterns", [
        "indeed", "quite", "rather", "I shall",
        "most certainly", "if you will", "as it were",
        "one might say"
    ])
