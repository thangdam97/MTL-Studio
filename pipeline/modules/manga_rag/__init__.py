"""
Manga RAG — Visual Storyboard Intelligence (Phase 1.8)

🧪 EXPERIMENTAL

Treats manga adaptations as dense visual storyboards to augment
light novel translation with panel-level visual context.

Architecture:
  - ingest.py            → CBZ/PDF/directory → page images
  - analyzer.py          → Gemini 3 Pro Vision (manga panel analysis)
  - cache_manager.py     → manga_cache.json persistence
  - vector_store.py      → ChromaDB semantic index ("manga_panels_{id}")
  - alignment.py         → LN ↔ Manga chapter alignment (manual YAML)
  - retriever.py         → Scene-level panel retrieval (chapter-scoped)
  - ambiguity_detector.py→ Selective retrieval trigger (saves API calls)
  - speaker_resolver.py  → Visual Speaker Diarization (speech bubble tails)
  - prompt_injector.py   → Storyboard Notes + Binocular Vision merger
  - config.py            → MangaRAGConfig dataclass

See docs/PHASE_1_8_MANGA_RAG.md for full implementation plan.
"""

import logging

logger = logging.getLogger(__name__)

# ─── Feature Gate ────────────────────────────────────────────────────────
# Disabled by default. Enable in config.yaml: manga_rag.enabled: true

MANGA_RAG_ENABLED = False


def is_enabled() -> bool:
    """Check if Manga RAG feature is enabled."""
    return MANGA_RAG_ENABLED


# ─── Lazy Imports (only when feature is enabled) ─────────────────────────
# These are deferred to avoid import errors when dependencies are missing.

__all__ = [
    "MANGA_RAG_ENABLED",
    "is_enabled",
    # Ingest
    "ingest_manga",
    # Analysis
    "MangaPanelAnalyzer",
    # Cache
    "MangaCacheManager",
    # Vector Store
    "MangaVectorStore",
    "PanelSearchResult",
    "build_embedding_text",
    # Alignment
    "ChapterAlignment",
    "generate_alignment_template",
    # Retrieval
    "MangaRetriever",
    "MangaQueryType",
    "SpeakerAttribution",
    # Ambiguity
    "AmbiguityDetector",
    "AmbiguityScore",
    # Speaker
    "SpeakerResolver",
    "SpeakerResolution",
    # Prompt Injection
    "build_binocular_context",
    "build_storyboard_context",
    "build_segment_visual_context",
    "format_storyboard_note",
    "MANGA_CANON_DIVERGENCE_DIRECTIVE",
    # Config
    "MangaRAGConfig",
]


def __getattr__(name):
    """Lazy import to avoid loading heavy dependencies when feature is disabled."""
    _import_map = {
        # ingest
        "ingest_manga": "modules.manga_rag.ingest",
        # analyzer
        "MangaPanelAnalyzer": "modules.manga_rag.analyzer",
        # cache_manager
        "MangaCacheManager": "modules.manga_rag.cache_manager",
        # vector_store
        "MangaVectorStore": "modules.manga_rag.vector_store",
        "PanelSearchResult": "modules.manga_rag.vector_store",
        "build_embedding_text": "modules.manga_rag.vector_store",
        # alignment
        "ChapterAlignment": "modules.manga_rag.alignment",
        "generate_alignment_template": "modules.manga_rag.alignment",
        # retriever
        "MangaRetriever": "modules.manga_rag.retriever",
        "MangaQueryType": "modules.manga_rag.retriever",
        "SpeakerAttribution": "modules.manga_rag.retriever",
        # ambiguity_detector
        "AmbiguityDetector": "modules.manga_rag.ambiguity_detector",
        "AmbiguityScore": "modules.manga_rag.ambiguity_detector",
        # speaker_resolver
        "SpeakerResolver": "modules.manga_rag.speaker_resolver",
        "SpeakerResolution": "modules.manga_rag.speaker_resolver",
        # prompt_injector
        "build_binocular_context": "modules.manga_rag.prompt_injector",
        "build_storyboard_context": "modules.manga_rag.prompt_injector",
        "build_segment_visual_context": "modules.manga_rag.prompt_injector",
        "format_storyboard_note": "modules.manga_rag.prompt_injector",
        "MANGA_CANON_DIVERGENCE_DIRECTIVE": "modules.manga_rag.prompt_injector",
        # config
        "MangaRAGConfig": "modules.manga_rag.config",
    }

    if name in _import_map:
        import importlib
        module = importlib.import_module(_import_map[name])
        return getattr(module, name)

    raise AttributeError(f"module 'modules.manga_rag' has no attribute {name!r}")
