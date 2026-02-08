"""
Configuration bridge between CLI and pipeline config.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml


class ConfigBridge:
    """Bridge between CLI settings and pipeline configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize config bridge."""
        if config_path is None:
            # Default to pipeline root config.yaml
            self.config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
        else:
            self.config_path = config_path

        self._config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

        return self._config

    def save(self) -> None:
        """Save configuration to file."""
        if self._config is None:
            raise ValueError("No configuration loaded")

        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key_path: Dot-separated path (e.g., 'gemini.model')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if self._config is None:
            self.load()

        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.

        Args:
            key_path: Dot-separated path (e.g., 'gemini.model')
            value: Value to set
        """
        if self._config is None:
            self.load()

        keys = key_path.split('.')
        target = self._config

        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value

    # Convenience properties
    @property
    def target_language(self) -> str:
        """Get current target language."""
        return self.get('project.target_language', 'en')

    @target_language.setter
    def target_language(self, value: str) -> None:
        """Set target language."""
        self.set('project.target_language', value)

    @property
    def model(self) -> str:
        """Get current Gemini model."""
        return self.get('gemini.model', 'gemini-2.5-flash')

    @model.setter
    def model(self, value: str) -> None:
        """Set Gemini model."""
        self.set('gemini.model', value)

    @property
    def caching_enabled(self) -> bool:
        """Check if context caching is enabled."""
        return self.get('gemini.caching.enabled', True)

    @caching_enabled.setter
    def caching_enabled(self, value: bool) -> None:
        """Set caching enabled status."""
        self.set('gemini.caching.enabled', value)

    @property
    def cache_ttl(self) -> int:
        """Get cache TTL in minutes."""
        return self.get('gemini.caching.ttl_minutes', 120)

    @cache_ttl.setter
    def cache_ttl(self, value: int) -> None:
        """Set cache TTL."""
        self.set('gemini.caching.ttl_minutes', value)

    @property
    def temperature(self) -> float:
        """Get generation temperature."""
        return self.get('gemini.generation.temperature', 0.6)

    @temperature.setter
    def temperature(self, value: float) -> None:
        """Set generation temperature."""
        self.set('gemini.generation.temperature', value)

    @property
    def top_p(self) -> float:
        """Get top-p value."""
        return self.get('gemini.generation.top_p', 0.95)

    @top_p.setter
    def top_p(self, value: float) -> None:
        """Set top-p value."""
        self.set('gemini.generation.top_p', value)

    @property
    def top_k(self) -> int:
        """Get top-k value."""
        return self.get('gemini.generation.top_k', 40)

    @top_k.setter
    def top_k(self, value: int) -> None:
        """Set top-k value."""
        self.set('gemini.generation.top_k', value)

    @property
    def pre_toc_enabled(self) -> bool:
        """Check if pre-TOC detection is enabled."""
        return self.get('pre_toc_detection.enabled', False)

    @pre_toc_enabled.setter
    def pre_toc_enabled(self, value: bool) -> None:
        """Set pre-TOC detection enabled status."""
        self.set('pre_toc_detection.enabled', value)

    @property
    def verbose_mode(self) -> bool:
        """Check if verbose mode is enabled by default."""
        return self.get('cli.verbose_mode', True)

    @verbose_mode.setter
    def verbose_mode(self, value: bool) -> None:
        """Set default verbose mode."""
        self.set('cli.verbose_mode', value)

    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled."""
        return self.get('debug.verbose_api', False)

    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        """Set debug mode."""
        self.set('debug.verbose_api', value)

    @property
    def multimodal_processor_enabled(self) -> bool:
        """
        Check if multimodal processing is enabled by default.

        Uses both the global multimodal gate and translation default.
        """
        translation_enabled = bool(self.get('translation.enable_multimodal', False))
        multimodal_enabled = bool(self.get('multimodal.enabled', True))
        return translation_enabled and multimodal_enabled

    @multimodal_processor_enabled.setter
    def multimodal_processor_enabled(self, value: bool) -> None:
        """Enable/disable multimodal processor defaults in config."""
        self.set('translation.enable_multimodal', bool(value))
        self.set('multimodal.enabled', bool(value))

    @property
    def smart_chunking_enabled(self) -> bool:
        """Check if smart chunking for massive chapters is enabled."""
        return bool(self.get('translation.massive_chapter.enable_smart_chunking', True))

    @smart_chunking_enabled.setter
    def smart_chunking_enabled(self, value: bool) -> None:
        """Enable/disable smart chunking for massive chapters."""
        self.set('translation.massive_chapter.enable_smart_chunking', bool(value))

    def get_available_languages(self) -> List[str]:
        """Get list of available target languages."""
        languages = self.get('project.languages', {})
        return list(languages.keys())

    def get_language_config(self, lang_code: str) -> Dict[str, Any]:
        """Get configuration for a specific language."""
        return self.get(f'project.languages.{lang_code}', {})

    def get_available_models(self) -> List[Dict[str, str]]:
        """Get list of available models with descriptions."""
        return [
            {'value': 'gemini-2.5-flash', 'label': 'gemini-2.5-flash', 'desc': 'Balanced, recommended'},
            {'value': 'gemini-2.5-pro', 'label': 'gemini-2.5-pro', 'desc': 'Best quality, slower'},
            {'value': 'gemini-2.0-flash', 'label': 'gemini-2.0-flash', 'desc': 'Legacy, no caching'},
        ]
