"""
Pipeline Base Configuration - Language-Agnostic Core Settings.

This module provides core configuration that is shared across all pipeline agents.
Language-specific settings should be loaded from config.yaml or manifest.json.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import yaml

# Load environment variables from .env file at module import time
from dotenv import load_dotenv

# ============================================================================
# BASE PATHS
# ============================================================================

PIPELINE_ROOT = Path(__file__).parent.parent.resolve()

# Load .env file from pipeline root (if it exists)
_env_path = PIPELINE_ROOT / ".env"
load_dotenv(_env_path)
PIPELINE_DIR = Path(__file__).parent.resolve()

# Standard directories
INPUT_DIR = PIPELINE_ROOT / "INPUT"
WORK_DIR = PIPELINE_ROOT / "WORK"
OUTPUT_DIR = PIPELINE_ROOT / "OUTPUT"
PROMPTS_DIR = PIPELINE_ROOT / "prompts"
MODULES_DIR = PIPELINE_ROOT / "modules"
TEMPLATES_DIR = PIPELINE_ROOT / "templates"

# Ensure directories exist
for dir_path in [INPUT_DIR, WORK_DIR, OUTPUT_DIR]:
    dir_path.mkdir(exist_ok=True)


# ============================================================================
# CONFIGURATION LOADER
# ============================================================================

_config_cache: Optional[Dict[str, Any]] = None


def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.yaml.

    Returns:
        Dictionary containing all configuration settings.
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    config_path = PIPELINE_ROOT / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        _config_cache = yaml.safe_load(f)

    return _config_cache


def get_config_section(section: str) -> Dict[str, Any]:
    """
    Get a specific section from the configuration.

    Args:
        section: Configuration section name (e.g., 'gemini', 'translation', 'builder')

    Returns:
        Dictionary containing section configuration.
    """
    config = load_config()
    return config.get(section, {})


# ============================================================================
# EPUB FORMAT CONSTANTS (Language-Agnostic)
# ============================================================================

# EPUB structure constants
EPUB_MIMETYPE = "application/epub+zip"
EPUB_CONTAINER_PATH = "META-INF/container.xml"

# Common content directories in EPUBs
EPUB_CONTENT_DIRS = ["OEBPS", "OPS", "EPUB", "item", "content"]

# Image file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}

# XHTML file extension
XHTML_EXTENSION = '.xhtml'


# ============================================================================
# CONTENT PROCESSING CONSTANTS
# ============================================================================

# Scene break marker (universal)
SCENE_BREAK_MARKER = "* * *"

# Illustration placeholder patterns
# Legacy format: [ILLUSTRATION: filename]
ILLUSTRATION_PLACEHOLDER_PATTERN = r'\[ILLUSTRATION:?\s*"?([^"\]]+)"?\]'
# Standard markdown format: ![alt](filename) where alt can be 'illustration', 'gaiji', or empty
MARKDOWN_IMAGE_PATTERN = r'!\[(illustration|gaiji|)\]\(([^)]+)\)'

# Ruby tag removal (for CJK languages)
REMOVE_RUBY_TAGS = True


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

def get_log_level() -> str:
    """Get logging level from configuration."""
    config = load_config()
    return config.get('logging', {}).get('level', 'INFO')


def get_log_format() -> str:
    """Get logging format from configuration."""
    config = load_config()
    return config.get('logging', {}).get(
        'format',
        '[%(levelname)s] %(asctime)s - %(name)s - %(message)s'
    )


# ============================================================================
# DEBUG FLAGS
# ============================================================================

def is_debug_mode() -> bool:
    """Check if debug mode is enabled."""
    config = load_config()
    return config.get('debug', {}).get('verbose_api', False)


def is_dry_run() -> bool:
    """Check if dry run mode is enabled."""
    config = load_config()
    return config.get('debug', {}).get('dry_run', False)


# ============================================================================
# PROJECT / LANGUAGE CONFIGURATION
# ============================================================================

def get_project_config() -> Dict[str, Any]:
    """
    Get project-level configuration including language settings.

    Returns:
        Dictionary containing project configuration with target_language and languages.
    """
    config = load_config()
    return config.get('project', {
        'target_language': 'en',
        'languages': {
            'en': {
                'master_prompt': 'prompts/master_prompt_en_compressed.xml',
                'modules_dir': 'modules/',
                'output_suffix': '_EN',
                'language_code': 'en',
                'language_name': 'English'
            }
        }
    })


def get_target_language() -> str:
    """
    Get the current target language from configuration.

    Returns:
        Language code (e.g., 'en', 'vn')
    """
    project = get_project_config()
    return project.get('target_language', 'en')


def get_language_config(target_language: str = None) -> Dict[str, Any]:
    """
    Get language-specific configuration.

    Args:
        target_language: Language code (e.g., 'en', 'vn').
                        If None, uses current target language from config.

    Returns:
        Dictionary containing language-specific settings.

    Raises:
        ValueError: If the specified language is not configured.
    """
    if target_language is None:
        target_language = get_target_language()

    project = get_project_config()
    languages = project.get('languages', {})

    if target_language not in languages:
        available = list(languages.keys())
        raise ValueError(
            f"Language '{target_language}' not configured. "
            f"Available languages: {available}"
        )

    return languages[target_language]


def get_available_languages() -> list:
    """
    Get list of available target languages.

    Returns:
        List of language codes (e.g., ['en', 'vn'])
    """
    project = get_project_config()
    return list(project.get('languages', {}).keys())


def set_target_language(language: str) -> None:
    """
    Set the target language in config.yaml.

    Args:
        language: Language code to set (e.g., 'en', 'vn')

    Raises:
        ValueError: If the language is not available.
    """
    available = get_available_languages()
    if language not in available:
        raise ValueError(
            f"Language '{language}' not available. "
            f"Available languages: {available}"
        )

    config_path = PIPELINE_ROOT / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    config['project']['target_language'] = language

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Clear cache so next load picks up new value
    global _config_cache
    _config_cache = None


def validate_language_setup(target_language: str = None) -> tuple:
    """
    Validate that language resources exist.

    Args:
        target_language: Language to validate. If None, uses current target.

    Returns:
        Tuple of (is_valid: bool, issues: list[str])
    """
    if target_language is None:
        target_language = get_target_language()

    try:
        lang_config = get_language_config(target_language)
    except ValueError as e:
        return False, [str(e)]

    issues = []

    # Check master prompt
    master_prompt_path = PIPELINE_ROOT / lang_config.get('master_prompt', '')
    if not master_prompt_path.exists():
        issues.append(f"Master prompt not found: {master_prompt_path}")

    # Check modules directory
    modules_dir = PIPELINE_ROOT / lang_config.get('modules_dir', '')
    if not modules_dir.exists():
        issues.append(f"Modules directory not found: {modules_dir}")
    elif not any(modules_dir.glob('*.md')):
        issues.append(f"No .md modules found in: {modules_dir}")

    # Check genre-specific prompts
    prompts = lang_config.get('prompts', {})
    for genre, prompt_path in prompts.items():
        full_path = PIPELINE_ROOT / prompt_path
        if not full_path.exists():
            issues.append(f"Genre prompt '{genre}' not found: {full_path}")

    return len(issues) == 0, issues
