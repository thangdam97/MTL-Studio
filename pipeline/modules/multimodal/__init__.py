"""
Multimodal Translation Module.

Provides visual-textual synthesis for light novel translation:
- Phase 1.6: Pre-bake visual analysis using Gemini 3 Pro Vision
- Phase 2:   Inject cached visual context into translation prompts

Architecture: "CPU + GPU" Dual-Model Strategy
  - Gemini 3 Pro ("GPU"): Visual analysis, emotional calibration (5% workload, once)
  - Gemini 2.5 Pro ("CPU"): Fast prose, dialogue, bulk translation (95% workload)

Pipeline Flow:
  Phase 1.6  →  visual_cache.json + cache/thoughts/*.json
  Phase 2    →  Art Director's Notes injected into translation prompts

Key Modules:
  - integrity_checker:  Pre-flight validation of JP tags vs asset files vs manifest
  - asset_processor:    Phase 1.6 "Art Director" (Gemini 3 Pro Vision + ThinkingConfig)
  - cache_manager:      Load/save/query visual_cache.json
  - prompt_injector:    Build Art Director's Notes for translation prompts
  - segment_classifier: Detect illustration markers in chapter text
  - analysis_detector:  Post-translation QA for analysis leaks
  - thought_logger:     Store/retrieve Gemini 3 Pro thinking process
  - kuchie_visualizer:  Canon name enforcement from manifest.json
  - canon name enforcer: Consistent character naming across visual + text

CLI:
  mtl.py phase1.6 <volume_id>                    # Pre-bake visual analysis
  mtl.py phase2 <volume_id> --enable-multimodal   # Translate with visual context
  mtl.py cache-inspect <volume_id>                 # Inspect visual cache
  mtl.py visual-thinking <volume_id>               # Convert thought logs to markdown
"""

# Cache management
from modules.multimodal.cache_manager import VisualCacheManager

# Prompt injection & canon enforcement
from modules.multimodal.prompt_injector import (
    build_chapter_visual_guidance,
    build_visual_context_block,
    build_visual_thinking_log,
    CanonNameEnforcer,
)

# Segment classification (illustration detection)
from modules.multimodal.segment_classifier import (
    SegmentType,
    ClassifiedSegment,
    extract_all_illustration_ids,
)

# Post-translation QA
from modules.multimodal.analysis_detector import detect_analysis_leak

# Pre-flight integrity checking
from modules.multimodal.integrity_checker import check_illustration_integrity

# Thought logging
from modules.multimodal.thought_logger import ThoughtLogger, VisualAnalysisLog

# Kuchie visualizer (OCR + ruby validation)
from modules.multimodal.kuchie_visualizer import (
    KuchieVisualizer,
    KuchieCharacter,
    RubyCanonEntry,
)

__all__ = [
    # Cache management
    "VisualCacheManager",

    # Prompt injection
    "build_chapter_visual_guidance",
    "build_visual_context_block",
    "build_visual_thinking_log",

    # Canon name enforcement
    "CanonNameEnforcer",

    # Segment classification
    "SegmentType",
    "ClassifiedSegment",
    "extract_all_illustration_ids",

    # Post-translation QA
    "detect_analysis_leak",

    # Pre-flight integrity
    "check_illustration_integrity",

    # Thought logging
    "ThoughtLogger",
    "VisualAnalysisLog",

    # Kuchie visualizer
    "KuchieVisualizer",
    "KuchieCharacter",
    "RubyCanonEntry",
]
