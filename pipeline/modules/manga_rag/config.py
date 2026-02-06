"""
Manga RAG Configuration.

Defines defaults for manga_rag config.yaml section.
Feature-gated: all operations check is_enabled() before executing.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MangaRAGConfig:
    """Configuration for Manga RAG pipeline."""
    
    # Master switch
    enabled: bool = False
    
    # Models
    vision_model: str = "gemini-3-pro-preview"
    
    # Analysis
    analysis_mode: str = "full_page"        # 'full_page' or 'panel_segmented'
    max_panels_per_page: int = 8
    ocr_enabled: bool = True
    ocr_engine: str = "gemini"              # 'gemini' or 'mokuro'
    
    # Retrieval
    max_panels_per_segment: int = 4
    min_similarity: float = 0.75
    inject_threshold: float = 0.80
    log_threshold: float = 0.65
    
    # Ambiguity detection
    ambiguity_enabled: bool = True
    ambiguity_threshold: float = 0.6
    
    # Speaker diarization
    speaker_diarization_enabled: bool = True
    speaker_confidence_threshold: float = 0.85
    
    # Alignment
    alignment_method: str = "manual"        # 'manual', 'dialogue_match', 'embedding'
    alignment_file: str = "manga_alignment.yaml"
    
    # Cache
    cache_path: str = "manga_cache.json"
    max_age_days: int = 180
    
    # Thinking
    thinking_enabled: bool = True
    thinking_path: str = "cache/manga_thoughts"
    
    # Vector store
    persist_directory: str = "chroma_manga"
    collection_prefix: str = "manga_panels"
    
    @classmethod
    def from_yaml(cls, config: dict) -> "MangaRAGConfig":
        """Load from config.yaml manga_rag section."""
        manga_cfg = config.get("manga_rag", {})
        if not manga_cfg:
            return cls()
        
        return cls(
            enabled=manga_cfg.get("enabled", False),
            vision_model=manga_cfg.get("models", {}).get("vision", "gemini-3-pro-preview"),
            analysis_mode=manga_cfg.get("analysis", {}).get("mode", "full_page"),
            max_panels_per_page=manga_cfg.get("analysis", {}).get("max_panels_per_page", 8),
            ocr_enabled=manga_cfg.get("analysis", {}).get("ocr_enabled", True),
            max_panels_per_segment=manga_cfg.get("retrieval", {}).get("max_panels_per_segment", 4),
            min_similarity=manga_cfg.get("retrieval", {}).get("min_similarity", 0.75),
            inject_threshold=manga_cfg.get("retrieval", {}).get("inject_threshold", 0.80),
            ambiguity_enabled=manga_cfg.get("ambiguity", {}).get("enabled", True),
            ambiguity_threshold=manga_cfg.get("ambiguity", {}).get("threshold", 0.6),
            speaker_diarization_enabled=manga_cfg.get("speaker_diarization", {}).get("enabled", True),
            speaker_confidence_threshold=manga_cfg.get("speaker_diarization", {}).get("confidence_threshold", 0.85),
            alignment_method=manga_cfg.get("alignment", {}).get("method", "manual"),
            alignment_file=manga_cfg.get("alignment", {}).get("file", "manga_alignment.yaml"),
            cache_path=manga_cfg.get("cache", {}).get("path", "manga_cache.json"),
            max_age_days=manga_cfg.get("cache", {}).get("max_age_days", 180),
            thinking_enabled=manga_cfg.get("thinking", {}).get("enabled", True),
            thinking_path=manga_cfg.get("thinking", {}).get("path", "cache/manga_thoughts"),
            persist_directory=manga_cfg.get("vector_store", {}).get("persist_directory", "chroma_manga"),
            collection_prefix=manga_cfg.get("vector_store", {}).get("collection_prefix", "manga_panels"),
        )
