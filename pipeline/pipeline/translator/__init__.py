"""
Translator Module - Phase 2 of MT Publishing Pipeline.

Translates Japanese light novel chapters to English using Gemini API.

Responsible for:
1. Loading master prompts and RAG modules
2. Translating JP chapters to target language
3. Maintaining context across chapters
4. Self-auditing translation quality
"""

__version__ = "1.0.0"

# Lazy imports to avoid circular import warnings when running with -m flag
def __getattr__(name):
    """Lazy loading to prevent RuntimeWarning with -m flag."""
    if name == 'TranslatorAgent':
        from .agent import TranslatorAgent
        return TranslatorAgent
    elif name == 'run_translator':
        from .agent import run_translator
        return run_translator
    elif name == 'TranslationReport':
        from .agent import TranslationReport
        return TranslationReport
    elif name == 'GeminiClient':
        from .gemini_client import GeminiClient
        return GeminiClient
    elif name == 'GeminiResponse':
        from .gemini_client import GeminiResponse
        return GeminiResponse
    elif name == 'PromptLoader':
        from .prompt_loader import PromptLoader
        return PromptLoader
    elif name == 'ContextManager':
        from .context_manager import ContextManager
        return ContextManager
    elif name == 'ChapterProcessor':
        from .chapter_processor import ChapterProcessor
        return ChapterProcessor
    elif name == 'TranslationResult':
        from .chapter_processor import TranslationResult
        return TranslationResult
    elif name == 'QualityMetrics':
        from .quality_metrics import QualityMetrics
        return QualityMetrics
    elif name == 'AuditResult':
        from .quality_metrics import AuditResult
        return AuditResult
    elif name == 'GlossaryLock':
        from .glossary_lock import GlossaryLock
        return GlossaryLock
    elif name == 'ChunkMerger':
        from .chunk_merger import ChunkMerger
        return ChunkMerger
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Main entry points
    'TranslatorAgent',
    'run_translator',

    # Result types
    'TranslationReport',
    'TranslationResult',
    'GeminiResponse',
    'AuditResult',

    # Components (for advanced usage)
    'GeminiClient',
    'PromptLoader',
    'ContextManager',
    'ChapterProcessor',
    'QualityMetrics',
    'GlossaryLock',
    'ChunkMerger',
]
