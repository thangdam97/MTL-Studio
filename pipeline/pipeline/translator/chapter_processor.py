"""
Chapter Processor.
Handles the translation of a single chapter using Gemini and RAG context.
"""

import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from pipeline.common.gemini_client import GeminiClient
from pipeline.translator.prompt_loader import PromptLoader
from pipeline.translator.context_manager import ContextManager
from pipeline.translator.quality_metrics import QualityMetrics, AuditResult
from pipeline.translator.config import (
    get_generation_params,
    get_model_name,
    get_safety_settings,
    get_translation_config,
)
from pipeline.translator.scene_break_formatter import SceneBreakFormatter
from pipeline.translator.chunk_merger import ChunkMerger
from pipeline.translator.glossary_lock import GlossaryLock
from pipeline.translator.volume_context_integration import VolumeContextIntegration
from pipeline.post_processor.vn_cjk_cleaner import VietnameseCJKCleaner
from pipeline.config import PIPELINE_ROOT
from modules.gap_integration import GapIntegrationEngine
# RTASCalculator disabled (2026-02-10): Direct manifest reading instead
# from modules.rtas_calculator import RTASCalculator, VoiceSettings

# Dialect detection (v1.0 - 2026-02-01)
try:
    from modules.dialect_detector import detect_chapter_dialects
    DIALECT_DETECTION_AVAILABLE = True
except ImportError:
    DIALECT_DETECTION_AVAILABLE = False
    detect_chapter_dialects = None

logger = logging.getLogger(__name__)

@dataclass
class TranslationResult:
    success: bool
    output_path: Path
    input_tokens: int = 0
    output_tokens: int = 0
    audit_result: Optional[AuditResult] = None
    warnings: List[str] = None
    error: Optional[str] = None
    context_update: Optional[Dict[str, Any]] = None

class ChapterProcessor:
    def __init__(
        self,
        gemini_client: GeminiClient,
        prompt_loader: PromptLoader,
        context_manager: ContextManager,
        target_language: str = "en",
        work_dir: Optional[Path] = None
    ):
        self.client = gemini_client
        self.prompt_loader = prompt_loader
        self.context_manager = context_manager
        self.target_language = target_language
        self.model_name = get_model_name()
        self.gen_params = get_generation_params()
        self.safety_settings = get_safety_settings()

        # Initialize Vietnamese CJK cleaner for post-processing (VN only)
        self._vn_cjk_cleaner = None
        if target_language.lower() in ['vi', 'vn']:
            self._vn_cjk_cleaner = VietnameseCJKCleaner(strict_mode=True, log_substitutions=True)
            logger.info("✓ Vietnamese CJK post-processor initialized (hard substitution enabled)")
        
        # Initialize Self-Healing Anti-AI-ism Agent for post-processing
        # DISABLED (2026-02-10): 1a60 audit proved Gemini's native output has near-zero AI-ism contamination.
        # Post-processing over-correction damages natural prose quality. Trust the model.
        self._anti_ai_ism_agent = None
        self.enable_anti_ai_ism = False  # PERMANENTLY DISABLED - model quality is excellent
        
        # Load character names from manifest.json for name consistency
        self.character_names = self._load_character_names()
        if self.character_names:
            logger.info(f"✓ Loaded {len(self.character_names)} character names from manifest")
        
        # Load book genre from manifest for Sino-VN disambiguation (v2)
        self.book_genre = self._load_genre()
        if self.book_genre != "general":
            logger.info(f"✓ Book genre detected: {self.book_genre}")
        
        # Initialize gap analyzer (Week 2-3 integration)
        self.gap_analyzer = None
        self.enable_gap_analysis = False  # Will be enabled from agent if needed

        # Initialize multimodal (visual context injection)
        self.enable_multimodal = False  # Will be enabled from agent if needed
        self.visual_cache = None  # VisualCacheManager, set by agent

        # Volume-level context integration (Phase 1.2 - Full Long Context)
        self.volume_context_integration = None
        if work_dir:
            self.volume_context_integration = VolumeContextIntegration(
                work_dir=work_dir,
                gemini_client=self.client
            )
            logger.info("✓ Volume-level context integration enabled")

        # Massive chapter handling
        translation_config = get_translation_config()
        massive_cfg = translation_config.get("massive_chapter", {})
        configured_chunking = bool(massive_cfg.get("enable_smart_chunking", False))
        # Stability mode: force-disable smart chunking in codebase and run full chapter in one pass.
        self.smart_chunking_enabled = False
        if configured_chunking:
            logger.info("[CHUNK] Smart chunking configured ON but force-disabled in codebase for this runtime.")
        self.chunk_threshold_chars = int(massive_cfg.get("chunk_threshold_chars", 60000))
        self.chunk_threshold_bytes = int(massive_cfg.get("chunk_threshold_bytes", 120000))
        self.target_chunk_chars = int(massive_cfg.get("target_chunk_chars", 45000))

        self.glossary_lock: Optional[GlossaryLock] = None

        # RTAS Calculator - DISABLED (2026-02-10)
        # Bypass RTAS calculation, read contraction rates directly from manifest
        self.rtas_calculator = None  # Disabled
        self.voice_settings: Dict[str, Any] = {}  # Unused - kept for compatibility
        self.enable_rtas = False  # DISABLED - direct manifest reading instead
        self.contraction_rates: Dict[str, int] = {}  # Direct manifest-to-rate mapping
        self._load_contraction_rates_from_manifest()
        self._stage2_registers = self._load_stage2_registers()
        self._stage2_rhythm_targets = self._load_stage2_rhythm_targets()
        self._phase155_context = self._load_phase155_context_offload()

    def set_glossary_lock(self, glossary_lock: Optional[GlossaryLock]) -> None:
        """Attach manifest glossary lock from TranslatorAgent."""
        self.glossary_lock = glossary_lock

    def _load_contraction_rates_from_manifest(self) -> None:
        """
        Load contraction rates directly from manifest.json character profiles.

        RTAS calculator bypassed (2026-02-10): The calculator correctly reads manifest
        but Gemini ignores the calculated rates during translation. This method reads
        manifest values directly for prompt injection without intermediate calculation.

        Default: 95% for contemporary casual speech (global baseline)
        """
        try:
            work_dir = self.context_manager.work_dir
            manifest_path = work_dir / "manifest.json"

            if not manifest_path.exists():
                logger.debug("No manifest.json found for contraction rate loading")
                return

            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            # Extract character_profiles from metadata_en
            metadata_en = manifest.get("metadata_en", {})
            if not isinstance(metadata_en, dict):
                metadata_en = {}
            profiles = metadata_en.get("character_profiles", {})
            if not isinstance(profiles, dict):
                profiles = {}

            # Read contraction_rate.baseline directly from each character profile
            for char_id, profile in profiles.items():
                if not isinstance(profile, dict):
                    continue

                contraction_rate_data = profile.get("contraction_rate")
                if contraction_rate_data and isinstance(contraction_rate_data, dict):
                    # New format: {"baseline": 0.75, "narration": 0.75, ...}
                    baseline = contraction_rate_data.get("baseline", 0.95)
                    # Convert from 0.0-1.0 to 0-100 percentage
                    self.contraction_rates[char_id] = int(baseline * 100)
                else:
                    # Default to 95% for contemporary speech
                    self.contraction_rates[char_id] = 95

            if self.contraction_rates:
                logger.info(f"✓ Loaded contraction rates for {len(self.contraction_rates)} characters from manifest")
                for char_id, rate in list(self.contraction_rates.items())[:3]:
                    logger.debug(f"  {char_id}: {rate}%")
            else:
                logger.debug("No character profiles found in manifest")
        except Exception as e:
            logger.warning(f"Failed to load contraction rates from manifest: {e}")
            self.contraction_rates = {}

    def _format_rtas_guidance(self) -> Optional[str]:
        """
        Format contraction rate guidance for prompt injection.

        ALIGNED WITH TENSE ENFORCEMENT: Applies contractions primarily to dialogue
        (present tense) and to contractable past-tense forms in narration (I'd, wouldn't).
        Accepts that "was/were" cannot be contracted (grammatically correct).
        """
        if not self.contraction_rates:
            return None

        if self.target_language.lower() not in ['en', 'english']:
            # Contraction rules are English-specific
            return None

        # Find the protagonist/narrator (usually the first character with high rate)
        protagonist_id = None
        protagonist_rate = 0
        for char_id, rate in self.contraction_rates.items():
            if rate >= 90:
                protagonist_id = char_id
                protagonist_rate = rate
                break

        lines = [
            "=== CHARACTER VOICE & CONTRACTION RATES ===",
            "",
            "**PRIMARY APPLICATION: Character dialogue (present tense)**",
            "**SECONDARY APPLICATION: Past-tense contractions in narration (I'd, wouldn't, couldn't)**",
            ""
        ]

        lines.append("**CHARACTER DIALOGUE CONTRACTION RATES:**")
        for char_id, rate in self.contraction_rates.items():
            lines.append(f"- **{char_id}**: {rate}%")
            if rate >= 95:
                lines.append(f"  → Casual speech: \"I'm sure,\" \"don't worry,\" \"can't wait,\" \"won't forget,\" \"it's fine\"")
            elif rate >= 75:
                lines.append(f"  → Moderately formal: Mix \"I'm\" / \"I am\" depending on sentence context")
            else:
                lines.append(f"  → Formal speech: \"I am,\" \"do not,\" \"cannot,\" \"will not\"")

        lines.append("")
        lines.append("**NARRATION CONTRACTION RULES:**")
        if protagonist_id and protagonist_rate >= 90:
            lines.append(f"Narrator ({protagonist_id}) uses {protagonist_rate}% contraction rate:")
            lines.append("")
            lines.append("✓ ALWAYS contract past-tense auxiliaries:")
            lines.append("  - \"I had\" → \"I'd\"")
            lines.append("  - \"I would\" → \"I'd\"")
            lines.append("  - \"we had\" → \"we'd\"")
            lines.append("  - \"they would\" → \"they'd\"")
            lines.append("  - \"could not\" → \"couldn't\"")
            lines.append("  - \"would not\" → \"wouldn't\"")
            lines.append("  - \"should not\" → \"shouldn't\"")
            lines.append("  - \"did not\" → \"didn't\"")
            lines.append("  - \"have not\" → \"haven't\"")
            lines.append("")
            lines.append("✓ ACCEPT uncontractable forms (grammatically correct):")
            lines.append("  - \"I was\" (no contraction exists)")
            lines.append("  - \"you were\" (no contraction exists)")
            lines.append("  - \"he was\" (no contraction exists)")
            lines.append("  - \"they were\" (no contraction exists)")
        else:
            lines.append("Narrator uses formal narration style with minimal contractions.")

        lines.append("")
        lines.append("---")
        lines.append("**EXAMPLES:**")
        lines.append("")
        lines.append("❌ WRONG narration (95% rate):")
        lines.append("  \"I looked at her. I would have said hello, but I did not know what to say.\"")
        lines.append("")
        lines.append("✅ CORRECT narration (95% rate):")
        lines.append("  \"I looked at her. I'd have said hello, but I didn't know what to say.\"")
        lines.append("")
        lines.append("✅ CORRECT dialogue (95% rate):")
        lines.append("  \"Hey, I'm heading home now. Don't wait up for me, okay? It's pretty late.\"")
        lines.append("")
        lines.append("✅ CORRECT dialogue (75% rate - Nagi):")
        lines.append("  \"I am going home now. Please do not wait for me. It is rather late.\"")

        return "\n".join(lines)
    
    def _load_character_names(self) -> Dict[str, str]:
        """Load character names from manifest.json metadata_en."""
        try:
            # Get work directory from context_manager
            work_dir = self.context_manager.work_dir
            
            # Try metadata_en.json first (preferred)
            metadata_en_path = work_dir / "metadata_en.json"
            if metadata_en_path.exists():
                with open(metadata_en_path, 'r', encoding='utf-8') as f:
                    metadata_en = json.load(f)
                    return metadata_en.get('character_names', {})
            
            # Fallback to manifest.json
            manifest_path = work_dir / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                    metadata_en = manifest.get('metadata_en', {})
                    return metadata_en.get('character_names', {})
            
            logger.warning("No character names found in manifest")
            return {}
            
        except Exception as e:
            logger.warning(f"Failed to load character names: {e}")
            return {}
    
    def _load_genre(self) -> str:
        """Load book genre from metadata_en.json or manifest.json.
        
        Handles multiple manifest versions:
          - v1.0: top-level "genre" (string, e.g. "romcom_school_life")
          - v3.5+: metadata_en.genre (string) or content_info.genre (array)
          - v3.6+: translation_guidance.genre (array) or content_info.genre (array)
        
        Returns first genre tag that matches the Sino-VN v2 genre_mapping.
        Falls back to "japanese_light_novel" (broadest LN category).
        """
        # Known genres in sino_vietnamese_rag_v2.json genre_mapping
        KNOWN_GENRES = {
            "academic", "contemporary", "fantasy_classical", "historical",
            "isekai_medieval", "legal_thriller", "medical_drama", "modern_urban",
            "period_drama", "political", "psychological", "romcom",
            "school_life", "slice_of_life", "wuxia", "yandere",
        }
        
        try:
            work_dir = self.context_manager.work_dir
            
            # ── Cascade 1: metadata_en.json (preferred) ──
            metadata_en_path = work_dir / "metadata_en.json"
            if metadata_en_path.exists():
                with open(metadata_en_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                # Try top-level "genre" (string in v3.5+: "romcom", "romcom_yandere")
                genre_val = meta.get('genre')
                result = self._resolve_genre(genre_val, KNOWN_GENRES)
                if result:
                    return result
                # Try content_info.genre (array)
                ci = meta.get('content_info', {})
                genre_val = ci.get('genre') or ci.get('genres')
                result = self._resolve_genre(genre_val, KNOWN_GENRES)
                if result:
                    return result
            
            # ── Cascade 2: manifest.json ──
            manifest_path = work_dir / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                # v1.0: top-level "genre" (string)
                genre_val = manifest.get('genre')
                result = self._resolve_genre(genre_val, KNOWN_GENRES)
                if result:
                    return result
                # v3.5+: translation_guidance.genre (array)
                tg = manifest.get('translation_guidance', {})
                genre_val = tg.get('genre') or tg.get('genres')
                result = self._resolve_genre(genre_val, KNOWN_GENRES)
                if result:
                    return result
                # v3.5+: content_info.genre (array) — can be nested under metadata_en
                meta_en = manifest.get('metadata_en', {})
                ci = meta_en.get('content_info', manifest.get('content_info', {}))
                genre_val = ci.get('genre') or ci.get('genres')
                result = self._resolve_genre(genre_val, KNOWN_GENRES)
                if result:
                    return result
            
            logger.debug("[GENRE] No matching genre found in manifest, using 'japanese_light_novel'")
            return "japanese_light_novel"
            
        except Exception as e:
            logger.warning(f"[GENRE] Failed to load genre: {e}")
            return "japanese_light_novel"
    
    @staticmethod
    def _resolve_genre(genre_val, known_genres: set) -> Optional[str]:
        """Resolve a genre value (string or array) to a known Sino-VN genre.
        
        For compound strings like "romcom_school_life", splits on '_' and
        checks each segment against known genres.
        For arrays, returns first matching element.
        """
        if not genre_val:
            return None
        
        # Normalize to list
        if isinstance(genre_val, str):
            candidates = [genre_val]
        elif isinstance(genre_val, list):
            candidates = genre_val
        else:
            return None
        
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            c = candidate.lower().strip()
            # Direct match
            if c in known_genres:
                return c
            # Compound split: "romcom_school_life" → ["romcom", "school_life"]
            parts = c.split('_')
            # Try longest sub-sequences first ("school_life" from "romcom_school_life")
            for length in range(len(parts), 0, -1):
                for start in range(len(parts) - length + 1):
                    sub = '_'.join(parts[start:start + length])
                    if sub in known_genres:
                        return sub
        
        return None
    
    def _save_thinking_process(
        self, 
        chapter_id: str, 
        thinking_content: str, 
        output_path: Path,
        visual_guidance: Optional[str] = None,
        illustration_ids: Optional[list] = None
    ) -> None:
        """Save Gemini's thinking process to a separate markdown file.
        
        Args:
            chapter_id: Chapter identifier (e.g., "chapter_01")
            thinking_content: The thinking/reasoning content from Gemini
            output_path: Path to the translated chapter file
            visual_guidance: Optional visual context injected (multimodal)
            illustration_ids: Optional list of illustration IDs processed
        """
        from pipeline.config import get_config_section
        
        gemini_config = get_config_section('gemini')
        thinking_config = gemini_config.get('thinking_mode', {})
        
        if not thinking_config.get('save_to_file', False):
            return
        
        # Create THINKING directory in the work folder
        thinking_dir = output_path.parent.parent / thinking_config.get('output_dir', 'THINKING')
        thinking_dir.mkdir(exist_ok=True)
        
        # Generate thinking file name based on chapter
        thinking_file = thinking_dir / f"{chapter_id}_THINKING.md"
        
        # Create markdown content with metadata
        from datetime import datetime
        
        # Build multimodal section if applicable
        multimodal_section = ""
        visual_thinking_section = ""
        if self.enable_multimodal and visual_guidance:
            illust_count = len(illustration_ids) if illustration_ids else 0
            multimodal_section = f"""
## 🎨 Multimodal Visual Context

**Mode**: Dual-Model "CPU + GPU" Architecture
**Illustrations Analyzed**: {illust_count}
**Visual Cache**: Active

### Art Director's Notes Injected

The following visual analysis was provided to guide translation:

```
{visual_guidance[:2000]}{"..." if len(visual_guidance) > 2000 else ""}
```

---
"""
            # Include Gemini 3 Pro visual thinking log if available
            if illustration_ids:
                try:
                    from modules.multimodal.prompt_injector import build_visual_thinking_log
                    volume_path = output_path.parent.parent  # EN/chapter.md -> volume_dir
                    visual_thinking_section = build_visual_thinking_log(illustration_ids, volume_path)
                    if visual_thinking_section:
                        visual_thinking_section = f"\n{visual_thinking_section}\n\n---\n"
                except Exception as e:
                    logger.debug(f"[THINKING] Could not include visual thinking log: {e}")
        
        markdown_content = f"""# Translation Reasoning Process

**Chapter**: {chapter_id}
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Model**: {self.client.model}
**Target Language**: {self.target_language}
**Multimodal Enabled**: {self.enable_multimodal}

---
{multimodal_section}{visual_thinking_section}
## Gemini's Translation Reasoning

This document contains the internal reasoning process that Gemini used while translating this chapter. This "thinking" output shows how the model analyzed the source text, made translation decisions, and considered context.

---

{thinking_content}

---

*This thinking process is automatically generated by Gemini 3/2.5 models and provides insight into the translation decision-making process.*
"""
        
        # Write to file
        with open(thinking_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        logger.info(f"💭 Thinking process saved to: {thinking_file.relative_to(output_path.parent.parent.parent)}")

    def translate_chapter(
        self,
        source_path: Path,
        output_path: Path,
        chapter_id: str,
        en_title: Optional[str] = None,
        model_name: Optional[str] = None,
        cached_content: Optional[str] = None,
        volume_cache: Optional[str] = None,
        scene_plan: Optional[Dict[str, Any]] = None,
        allow_chunking: bool = True,
    ) -> TranslationResult:
        """
        Translate a single chapter file.
        
        Args:
            source_path: Path to source Japanese chapter
            output_path: Path to save translated chapter
            chapter_id: Chapter identifier
            en_title: Translated chapter title
            model_name: Model override
            cached_content: Cached content name for continuity (from previous chapter schema)
            volume_cache: Optional alias for cached_content (volume-level cache)
            scene_plan: Optional Stage 1 scene scaffold from PLANS/{chapter}_scene_plan.json
            allow_chunking: If False, force direct translation without chunk splitting
        """
        try:
            effective_cache = volume_cache or cached_content
            logger.debug(f"[VERBOSE] Starting translation for {chapter_id}")
            logger.debug(f"[VERBOSE] Source: {source_path}")
            logger.debug(f"[VERBOSE] Output: {output_path}")
            
            # 1. Load Source
            if not source_path.exists():
                return TranslationResult(False, output_path, error=f"Source file not found: {source_path}")
            
            logger.debug(f"[VERBOSE] Reading source file...")
            with open(source_path, 'r', encoding='utf-8') as f:
                source_text = f.read()
            logger.debug(f"[VERBOSE] Source text length: {len(source_text)} characters")

            source_bytes = len(source_text.encode("utf-8"))
            is_massive = (
                len(source_text) >= self.chunk_threshold_chars
                or source_bytes >= self.chunk_threshold_bytes
            )
            if allow_chunking and self.smart_chunking_enabled and is_massive:
                logger.info(
                    f"[CHUNK] {chapter_id} is massive "
                    f"({len(source_text)} chars, {source_bytes} bytes); "
                    f"thresholds=({self.chunk_threshold_chars} chars, {self.chunk_threshold_bytes} bytes). "
                    f"Using chunked translation flow."
                )
                return self._translate_chapter_in_chunks(
                    source_path=source_path,
                    output_path=output_path,
                    chapter_id=chapter_id,
                    source_text=source_text,
                    en_title=en_title,
                    model_name=model_name,
                    cached_content=effective_cache,
                    scene_plan=scene_plan,
                )
            if allow_chunking and not self.smart_chunking_enabled and is_massive:
                logger.info(
                    f"[CHUNK] Smart chunking disabled; processing {chapter_id} as single chapter "
                    f"({len(source_text)} chars, {source_bytes} bytes)"
                )
            
            # === GAP ANALYSIS (Pre-Translation) ===
            gap_flags = None
            if self.enable_gap_analysis and self.gap_analyzer:
                try:
                    logger.info(f"[GAP] Running pre-translation gap analysis on {chapter_id}...")
                    gap_report = self.gap_analyzer.analyze_chapter_pre_translation(
                        chapter_id=chapter_id,
                        jp_lines=source_text.split('\n'),
                        en_lines=None  # Pre-translation, no EN output yet
                    )
                    
                    if gap_report:
                        gap_a_count = len(gap_report.gap_a_flags)
                        gap_b_count = len(gap_report.gap_b_flags)
                        gap_c_count = len(gap_report.gap_c_flags)
                        total_gaps = gap_a_count + gap_b_count + gap_c_count
                        
                        if total_gaps > 0:
                            logger.info(f"[GAP] Detected {total_gaps} gaps: A={gap_a_count}, B={gap_b_count}, C={gap_c_count}")
                            gap_flags = {
                                'gap_a': gap_report.gap_a_flags,
                                'gap_b': gap_report.gap_b_flags,
                                'gap_c': gap_report.gap_c_flags
                            }
                        else:
                            logger.debug(f"[GAP] No gaps detected in {chapter_id}")
                except Exception as e:
                    logger.warning(f"[GAP] Gap analysis failed: {e}")
                    logger.warning("[GAP] Continuing without gap guidance")
            # === END GAP ANALYSIS ===

            # === DIALECT DETECTION (v1.0 - 2026-02-01) ===
            dialect_guidance = None
            if DIALECT_DETECTION_AVAILABLE and detect_chapter_dialects:
                try:
                    logger.debug(f"[DIALECT] Scanning {chapter_id} for regional dialects...")
                    has_dialects, dialect_text = detect_chapter_dialects(source_text, chapter_id)
                    
                    if has_dialects:
                        logger.info(f"[DIALECT] Regional dialect(s) detected in {chapter_id}")
                        dialect_guidance = dialect_text
                    else:
                        logger.debug(f"[DIALECT] No regional dialects detected in {chapter_id}")
                except Exception as e:
                    logger.warning(f"[DIALECT] Detection failed: {e}")
                    logger.warning("[DIALECT] Continuing without dialect guidance")
            # === END DIALECT DETECTION ===

            # Strip JP title if present (usually the first H1)
            # We preserve the original title for audit but send the rest to LLM
            source_content_only = source_text
            jp_title_match = re.match(r'^#\s*(.*?)\n+', source_text)
            if jp_title_match:
                source_content_only = source_text[jp_title_match.end():].strip()
                logger.info(f"Stripped JP title for translation: {jp_title_match.group(1)}")

            # === Kanji Disambiguation (Sino-Vietnamese Vector Search) ===
            # Extract kanji compounds and query vector store for Vietnamese guidance
            # Now with Context-Aware Disambiguation using surrounding sentences
            sino_vn_guidance = None
            context_str = ""  # Initialize early for kanji disambiguation (populated later at line 204)
            if self.target_language in ['vi', 'vn']:  # Only for Vietnamese translations
                try:
                    from modules.kanji_extractor import extract_unique_compounds
                    from modules.sino_vietnamese_store import SinoVietnameseStore
                    
                    logger.debug(f"[KANJI] Extracting kanji compounds for Sino-Vietnamese lookup...")
                    
                    # Extract top 30 most frequent kanji compounds (2-4 characters)
                    kanji_terms = extract_unique_compounds(
                        source_content_only, 
                        min_length=2, 
                        max_length=4,
                        top_n=30
                    )
                    
                    if kanji_terms:
                        logger.debug(f"[KANJI] Found {len(kanji_terms)} kanji compounds: {kanji_terms[:5]}...")
                        
                        # Query vector store for disambiguation guidance
                        # Now with CONTEXT-AWARE DISAMBIGUATION
                        store = SinoVietnameseStore()
                        
                        # Extract first 3 sentences as context hint
                        sentences = re.split(r'[。！？\n]', source_content_only)
                        context_sentences = [s.strip() for s in sentences[:5] if s.strip()]
                        context_hint = '。'.join(context_sentences[:3])
                        
                        # Get previous chapter context if available
                        prev_context = ""
                        if context_str:
                            # Extract relevant context from continuity
                            prev_context = context_str[:500] if len(context_str) > 500 else context_str
                        
                        sino_vn_guidance = store.get_bulk_guidance(
                            terms=kanji_terms,
                            genre=self.book_genre,  # v2: extracted from manifest
                            max_per_term=2,
                            min_confidence=0.68,
                            context=context_hint,  # Current chapter context
                            prev_context=prev_context,  # Previous chapter context
                            use_external_dict=True  # Enable external dictionary fallback
                        )
                        
                        high_conf = len(sino_vn_guidance.get("high_confidence", []))
                        medium_conf = len(sino_vn_guidance.get("medium_confidence", []))
                        external_count = len(sino_vn_guidance.get("external_dict", []))
                        lookup_stats = sino_vn_guidance.get("lookup_stats", {})
                        
                        logger.info(f"[KANJI] Sino-Vietnamese guidance: {high_conf} high, {medium_conf} medium, {external_count} external")
                        logger.debug(f"[KANJI] Lookup stats: direct={lookup_stats.get('direct_hits', 0)}, vector={lookup_stats.get('vector_hits', 0)}, external={lookup_stats.get('external_hits', 0)}")
                    else:
                        logger.debug(f"[KANJI] No kanji compounds found in chapter")
                        
                except Exception as e:
                    logger.warning(f"[KANJI] Sino-Vietnamese lookup failed: {e}")
                    logger.warning("[KANJI] Continuing without kanji disambiguation")
                    sino_vn_guidance = None

            # === English Grammar Pattern Detection (Vector Search) ===
            # Detect Japanese grammar patterns and query vector store for natural English equivalents
            en_pattern_guidance = None
            if self.target_language == 'en':  # English translations only
                try:
                    from modules.grammar_pattern_detector import detect_grammar_patterns
                    from modules.english_pattern_store import EnglishPatternStore

                    logger.debug(f"[GRAMMAR] Detecting Japanese patterns for natural English phrasing...")

                    # Detect grammar patterns (けど, が, も, etc.)
                    detected_patterns = detect_grammar_patterns(
                        source_content_only,
                        top_n=15,  # Top 15 most relevant patterns
                        include_line_numbers=True
                    )

                    if detected_patterns:
                        logger.debug(f"[GRAMMAR] Found {len(detected_patterns)} patterns")

                        # Query vector store for natural English equivalents
                        store = EnglishPatternStore()

                        # Extract first 5 sentences as context hint
                        sentences = re.split(r'[。！？\n]', source_content_only)
                        context_sentences = [s.strip() for s in sentences[:5] if s.strip()]
                        context_hint = '。'.join(context_sentences[:3])

                        # Get previous chapter context if available
                        prev_context = ""
                        if context_str:
                            # Extract relevant context from continuity
                            prev_context = context_str[:500] if len(context_str) > 500 else context_str

                        en_pattern_guidance = store.get_bulk_guidance(
                            patterns=detected_patterns,
                            context=context_hint,
                            max_per_pattern=2,
                            min_confidence=0.75
                        )

                        high_conf = len(en_pattern_guidance.get("high_confidence", []))
                        medium_conf = len(en_pattern_guidance.get("medium_confidence", []))
                        lookup_stats = en_pattern_guidance.get("lookup_stats", {})

                        logger.info(f"[GRAMMAR] English pattern guidance: {high_conf} high, {medium_conf} medium")
                        logger.debug(f"[GRAMMAR] Lookup stats: patterns_queried={lookup_stats.get('patterns_queried', 0)}")
                    else:
                        logger.debug(f"[GRAMMAR] No grammar patterns detected in chapter")

                except Exception as e:
                    logger.warning(f"[GRAMMAR] Pattern detection failed: {e}")
                    logger.warning("[GRAMMAR] Continuing without grammar pattern guidance")
                    en_pattern_guidance = None

            # === Vietnamese Grammar Pattern Detection (Vector Search) ===
            # Detect Japanese grammar patterns and query vector store for natural Vietnamese equivalents
            vn_pattern_guidance = None
            if self.target_language == 'vn':  # Vietnamese translations only
                try:
                    from modules.grammar_pattern_detector import detect_grammar_patterns
                    from modules.vietnamese_pattern_store import VietnamesePatternStore

                    logger.debug(f"[VN-GRAMMAR] Detecting Japanese patterns for natural Vietnamese phrasing...")

                    # Detect grammar patterns (same JP detector, VN-specific store)
                    detected_patterns = detect_grammar_patterns(
                        source_content_only,
                        top_n=15,
                        include_line_numbers=True
                    )

                    if detected_patterns:
                        logger.debug(f"[VN-GRAMMAR] Found {len(detected_patterns)} patterns")

                        # Query VN vector store for natural Vietnamese equivalents
                        vn_store = VietnamesePatternStore()

                        # Extract first 5 sentences as context hint
                        sentences = re.split(r'[。！？\n]', source_content_only)
                        context_sentences = [s.strip() for s in sentences[:5] if s.strip()]
                        context_hint = '。'.join(context_sentences[:3])

                        vn_pattern_guidance = vn_store.get_bulk_guidance(
                            patterns=detected_patterns,
                            context=context_hint,
                            max_per_pattern=2,
                            min_confidence=0.70
                        )

                        high_conf = len(vn_pattern_guidance.get("high_confidence", []))
                        medium_conf = len(vn_pattern_guidance.get("medium_confidence", []))
                        lookup_stats = vn_pattern_guidance.get("lookup_stats", {})

                        logger.info(f"[VN-GRAMMAR] Vietnamese pattern guidance: {high_conf} high, {medium_conf} medium")
                        logger.debug(f"[VN-GRAMMAR] Lookup stats: patterns_queried={lookup_stats.get('patterns_queried', 0)}, neg_penalties={lookup_stats.get('neg_penalties_applied', 0)}")
                    else:
                        logger.debug(f"[VN-GRAMMAR] No grammar patterns detected in chapter")

                except Exception as e:
                    logger.warning(f"[VN-GRAMMAR] Pattern detection failed: {e}")
                    logger.warning("[VN-GRAMMAR] Continuing without Vietnamese grammar pattern guidance")
                    vn_pattern_guidance = None

            # === MULTIMODAL VISUAL CONTEXT ===
            visual_guidance = None
            illustration_ids = []  # Track for thought logging
            if self.enable_multimodal and self.visual_cache:
                try:
                    from modules.multimodal.segment_classifier import extract_all_illustration_ids
                    from modules.multimodal.prompt_injector import build_chapter_visual_guidance

                    illustration_ids = extract_all_illustration_ids(source_content_only)
                    if illustration_ids:
                        cache_manifest = self.visual_cache.get_manifest()
                        if not isinstance(cache_manifest, dict):
                            cache_manifest = {}
                        visual_guidance = build_chapter_visual_guidance(
                            illustration_ids, self.visual_cache,
                            manifest=cache_manifest
                        )
                        if visual_guidance:
                            logger.info(f"[MULTIMODAL] Injecting visual context for {len(illustration_ids)} illustration(s)")
                        else:
                            logger.debug(f"[MULTIMODAL] No cached context found for illustrations: {illustration_ids}")
                    else:
                        logger.debug(f"[MULTIMODAL] No illustration markers found in {chapter_id}")
                except Exception as e:
                    logger.warning(f"[MULTIMODAL] Visual context extraction failed: {e}")
                    logger.warning("[MULTIMODAL] Continuing without visual context")
            # === END MULTIMODAL ===

            # 2. Build Prompt
            # Skip rebuilding system instruction if cache is available
            # Check: external cached_content OR internal client cache
            if effective_cache or (self.client.enable_caching and self.client._is_cache_valid(model_name)):
                cache_type = "external" if effective_cache else "internal"
                cache_name = effective_cache or self.client._cached_content_name
                logger.debug(f"[VERBOSE] Using {cache_type} cached system instruction ({cache_name})")
                system_instruction = None  # Not needed when cache is active
            else:
                logger.debug(f"[VERBOSE] Building system instruction...")
                system_instruction = self.prompt_loader.build_system_instruction()
                logger.debug(f"[VERBOSE] System instruction length: {len(system_instruction)} characters")
            
            # Get Context (Continuity)
            logger.debug(f"[VERBOSE] Getting context prompt...")
            context_str = self.context_manager.get_context_prompt(chapter_id)
            logger.debug(f"[VERBOSE] Context length: {len(context_str)} characters")

            # === VOLUME-LEVEL CONTEXT (Phase 1.2) ===
            volume_context_text = None
            volume_cache_name = None
            if self.volume_context_integration:
                logger.debug(f"[VERBOSE] Getting volume-level context...")
                volume_context_text, volume_cache_name = self.volume_context_integration.get_volume_context(
                    chapter_id=chapter_id,
                    source_dir=source_path.parent,
                    en_dir=output_path.parent
                )

                # If volume cache exists, use it instead of effective_cache
                if volume_cache_name:
                    effective_cache = volume_cache_name
                    logger.info(f"[VOLUME-CACHE] Using volume-level cache: {volume_cache_name[:50]}...")
                    logger.debug(f"[VERBOSE] Volume context length: {len(volume_context_text) if volume_context_text else 0} characters")
            # === END VOLUME CONTEXT ===

            # Construct User Message
            logger.debug(f"[VERBOSE] Building user prompt...")
            user_prompt = self._build_user_prompt(
                chapter_id,
                source_content_only,
                context_str,
                en_title,
                sino_vn_guidance=sino_vn_guidance,
                gap_flags=gap_flags,
                dialect_guidance=dialect_guidance,  # v1.0 - Dialect detection
                en_pattern_guidance=en_pattern_guidance,  # English grammar patterns
                vn_pattern_guidance=vn_pattern_guidance,  # Vietnamese grammar patterns
                visual_guidance=visual_guidance,
                scene_plan=scene_plan,
                volume_context=volume_context_text,  # Phase 1.2 - Volume-level context
            )
            logger.debug(f"[VERBOSE] User prompt length: {len(user_prompt)} characters")
            
            # 3. Call Gemini
            logger.debug(f"[VERBOSE] Calling Gemini API...")
            # Note regarding model: gemini_client usually handles model in init or call
            # We pass system_instruction separately as per new API patterns
            # If we have cached_content from previous chapter, pass it for continuity
            response = self.client.generate(
                prompt=user_prompt,
                system_instruction=system_instruction,
                temperature=self.gen_params.get("temperature", 0.7),
                max_output_tokens=self.gen_params.get("max_output_tokens", 65536),
                model=model_name or self.model_name,
                cached_content=effective_cache  # Inject cached schema for continuity
            )
            logger.debug(
                f"[VERBOSE] Gemini response received. "
                f"finish_reason={response.finish_reason}, "
                f"tokens={response.input_tokens} in/{response.output_tokens} out, "
                f"cached_tokens={response.cached_tokens}"
            )
            
            # Save thinking process to separate markdown file if enabled
            if response.thinking_content:
                self._save_thinking_process(
                    chapter_id, 
                    response.thinking_content, 
                    output_path,
                    visual_guidance=visual_guidance,
                    illustration_ids=illustration_ids
                )
            
            if not response.content:
                finish_reason = response.finish_reason or "UNKNOWN"
                upper_reason = finish_reason.upper()
                blocked = any(marker in upper_reason for marker in ("SAFETY", "PROHIBITED", "BLOCK"))

                if blocked:
                    logger.error(
                        f"[GEMINI-BLOCK] Chapter {chapter_id} blocked by Gemini "
                        f"(finish_reason={finish_reason}, "
                        f"in={response.input_tokens}, out={response.output_tokens})"
                    )
                else:
                    logger.error(
                        f"[GEMINI-EMPTY] Chapter {chapter_id} returned empty content "
                        f"(finish_reason={finish_reason}, "
                        f"in={response.input_tokens}, out={response.output_tokens})"
                    )

                return TranslationResult(
                    False, output_path,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    error=(
                        f"Gemini returned empty response "
                        f"(finish_reason={finish_reason}; possible safety block)"
                    )
                )
            
            # 4. Parse Response
            # We expect Markdown output. Prompt 2.0 asks for pure markdown.
            # But prompt also says <CONTINUITY_UPDATE>...
            # Wait, I optimized the prompt to REMOVE XML tags in OUTPUT_FORMAT?
            # Let me check my previous step.
            # Step 113 modify TRANSLATION_OUTPUT to be pure Markdown...
            # BUT Step 99 added CONTINUITY_UPDATE xml block...
            # Ah, Step 113 removed the XML structure and said "run analysis silently".
            # So we might NOT get explicit new terms in XML format if the prompt strictly follows 113.
            # HOWEVER, if we want continuity, we need ample output. 
            # Reviewing Step 113: "Modify the TRANSLATION_OUTPUT block... SCENE_TONE silent... output only Chapter Title and Content"
            # This implies NO structured context update in output. 
            # This makes automatic context updating harder. 
            # I will assume purely prose output for now, and ContextManager relies on 
            # maybe a separate extraction step OR we infer from the text (hard).
            # OR I should have kept the XML for context updates.
            # Decision: Process text as is for now. If context update missing, we just log it.
            
            translated_body = response.content

            # === MULTIMODAL POST-CHECK: Analysis Leak Detection ===
            if self.enable_multimodal and visual_guidance:
                try:
                    from modules.multimodal.analysis_detector import detect_analysis_leak
                    leak_detected, leak_issues = detect_analysis_leak(translated_body)
                    if leak_detected:
                        logger.warning(f"[MULTIMODAL] Analysis leak detected in {chapter_id}:")
                        for issue in leak_issues:
                            logger.warning(f"  - {issue}")
                        logger.warning("[MULTIMODAL] Output may contain analysis instead of translation")
                except Exception as e:
                    logger.debug(f"[MULTIMODAL] Leak detection failed: {e}")
            # === END MULTIMODAL POST-CHECK ===

            # Post-process (cleanup markdown fences if any)
            cleaned_body = self._clean_output(translated_body)
            final_content = self._compose_chapter_markdown(cleaned_body, en_title)
            if en_title:
                logger.info(f"Injected title: {en_title}")

            bleed_headings = self._detect_cross_chapter_heading_bleed(
                final_content,
                chapter_id=chapter_id,
                en_title=en_title,
            )
            if bleed_headings and effective_cache:
                logger.warning(
                    f"[CACHE BLEED] Detected possible cross-chapter heading bleed in {chapter_id}: "
                    f"{', '.join(bleed_headings[:3])}"
                )
                logger.warning("[CACHE BLEED] Retrying chapter once without external cache...")
                fallback_system_instruction = system_instruction or self.prompt_loader.build_system_instruction()
                retry_response = self.client.generate(
                    prompt=user_prompt,
                    system_instruction=fallback_system_instruction,
                    temperature=self.gen_params.get("temperature", 0.7),
                    max_output_tokens=self.gen_params.get("max_output_tokens", 65536),
                    model=model_name or self.model_name,
                    cached_content=None,
                    force_new_session=True,
                )
                if retry_response.content:
                    response = retry_response
                    translated_body = retry_response.content
                    cleaned_body = self._clean_output(translated_body)
                    final_content = self._compose_chapter_markdown(cleaned_body, en_title)
                    bleed_headings = self._detect_cross_chapter_heading_bleed(
                        final_content,
                        chapter_id=chapter_id,
                        en_title=en_title,
                    )
                    if bleed_headings:
                        logger.warning(
                            f"[CACHE BLEED] Retry still has suspicious headings in {chapter_id}: "
                            f"{', '.join(bleed_headings[:3])}"
                        )
                    else:
                        logger.info(f"[CACHE BLEED] Retry without cache resolved heading bleed for {chapter_id}")
            
            # Format scene breaks (replace *, **, *** with centered ◆)
            final_content, scene_break_count = SceneBreakFormatter.format_scene_breaks(final_content)
            if scene_break_count > 0:
                logger.info(f"Formatted {scene_break_count} scene break(s) in {chapter_id}")
            
            # 5. Quality Audit (Audit against full source for accuracy check)
            audit = QualityMetrics.quick_audit(final_content, source_text)
            
            # 7. Save Translation Output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            # 8. Post-Processing: Vietnamese CJK Hard Substitution (VN only)
            # NOTE (2026-02-10): Only CJK validator remains active for Vietnamese translations.
            # All other post-processors (grammar validator, anti-AI-ism agent) have been
            # disabled after 1a60 audit proved they damage Gemini's native prose quality.
            # Gemini Flash 2.0 produces excellent translations with minimal errors:
            # - 0 subject-verb errors natively
            # - 5 possessive errors (50% better than baseline with old prompts)
            # - 1 AI-ism total (0.015 per 1k words)
            # - 95.8/100 prose score
            # Conclusion: Trust the model. Minimal post-processing = better quality.
            cjk_cleaned_count = 0
            if self._vn_cjk_cleaner:
                clean_result = self._vn_cjk_cleaner.clean_file(output_path)
                cjk_cleaned_count = clean_result.get('substitutions', 0)
                remaining_leaks = clean_result.get('remaining_leaks', 0)

                if cjk_cleaned_count > 0:
                    logger.info(f"✓ CJK post-processor: {cjk_cleaned_count} hard substitutions applied")
                if remaining_leaks > 0:
                    logger.warning(f"⚠ CJK post-processor: {remaining_leaks} unknown leaks remain (manual review needed)")

            # 9. Post-Processing: Self-Healing Anti-AI-ism Agent (DISABLED - damages prose quality)
            # DISABLED (2026-02-10): 1a60 audit found only 1 AI-ism in entire volume (0.015/1k).
            # Gemini's native output is excellent. Post-processing over-correction damages natural prose.
            # Evidence: Grammar validator introduced 35 errors trying to "fix" correct grammar.
            # Philosophy: Trust the model. Minimal intervention = better quality.
            # ai_ism_healed_count = 0  # Unused - agent permanently disabled
            # if self.enable_anti_ai_ism and self._anti_ai_ism_agent:
            #     try:
            #         logger.debug(f"[ANTI-AI-ISM] Running self-healing agent on {chapter_id}...")
            #         heal_report = self._anti_ai_ism_agent.heal_file(output_path)
            #
            #         if heal_report and heal_report.issues:
            #             ai_ism_healed_count = len([i for i in heal_report.issues if i.corrected])
            #             total_issues = len(heal_report.issues)
            #
            #             if ai_ism_healed_count > 0:
            #                 logger.info(f"✓ Anti-AI-ism agent: {ai_ism_healed_count}/{total_issues} issues auto-corrected")
            #
            #             # Log severity breakdown
            #             critical = len([i for i in heal_report.issues if i.severity == 'CRITICAL'])
            #             major = len([i for i in heal_report.issues if i.severity == 'MAJOR'])
            #             minor = len([i for i in heal_report.issues if i.severity == 'MINOR'])
            #
            #             if critical > 0:
            #                 logger.warning(f"  Critical: {critical}, Major: {major}, Minor: {minor}")
            #             elif major > 0:
            #                 logger.info(f"  Major: {major}, Minor: {minor}")
            #         else:
            #             logger.debug(f"[ANTI-AI-ISM] No AI-isms detected in {chapter_id}")
            #
            #     except Exception as e:
            #         logger.warning(f"[ANTI-AI-ISM] Self-healing failed: {e}")
            #         logger.warning("[ANTI-AI-ISM] Continuing without auto-correction (run 'mtl.py heal' manually)")

            validation_warnings = list(audit.warnings or [])

            # === LOG VOLUME CONTEXT COST SAVINGS (Phase 1.2) ===
            if self.volume_context_integration:
                savings_report = self.volume_context_integration.get_cost_savings_report()
                if savings_report['cache_hit_count'] > 0:
                    logger.info(
                        f"[VOLUME-CACHE] 💰 Cost savings: ${savings_report['total_cost_saved_usd']:.4f} "
                        f"({savings_report['cache_hit_count']} cache hits, "
                        f"{savings_report['cache_hit_rate']*100:.1f}% hit rate)"
                    )
            # === END COST SAVINGS ===

            return TranslationResult(
                success=True,
                output_path=output_path,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                audit_result=audit,
                warnings=validation_warnings
            )

        except Exception as e:
            logger.exception(f"Translation failed for {chapter_id}")
            return TranslationResult(False, output_path, error=str(e))

    def _translate_chapter_in_chunks(
        self,
        source_path: Path,
        output_path: Path,
        chapter_id: str,
        source_text: str,
        en_title: Optional[str],
        model_name: Optional[str],
        cached_content: Optional[str],
        scene_plan: Optional[Dict[str, Any]] = None,
    ) -> TranslationResult:
        """Translate massive chapters via resumable chunk JSON flow."""
        try:
            source_content_only = source_text
            jp_title_match = re.match(r'^#\s*(.*?)\n+', source_text)
            if jp_title_match:
                source_content_only = source_text[jp_title_match.end():].strip()

            chunks = self._split_large_chapter(source_content_only)
            if not chunks:
                return TranslationResult(False, output_path, error="Chunk splitter produced no chunks")

            total_chunks = len(chunks)
            temp_dir = self.context_manager.work_dir / "temp" / "chunks"
            temp_dir.mkdir(parents=True, exist_ok=True)

            total_input_tokens = 0
            total_output_tokens = 0

            for idx, chunk in enumerate(chunks, start=1):
                chunk_json_path = temp_dir / f"{chapter_id}_chunk_{idx:03d}.json"
                chunk_payload = self._load_chunk_payload(chunk_json_path)
                if chunk_payload and chunk_payload.get("content"):
                    logger.info(f"[CHUNK] Reusing existing chunk JSON {idx}/{total_chunks} for {chapter_id}")
                    total_input_tokens += int(chunk_payload.get("tokens_in", 0))
                    total_output_tokens += int(chunk_payload.get("tokens_out", 0))
                    continue

                chunk_source_path = temp_dir / f"{chapter_id}_chunk_{idx:03d}_JP.md"
                chunk_output_path = temp_dir / f"{chapter_id}_chunk_{idx:03d}_EN.md"
                chunk_source_path.write_text(str(chunk["content"]).strip() + "\n", encoding="utf-8")

                chunk_result = self.translate_chapter(
                    source_path=chunk_source_path,
                    output_path=chunk_output_path,
                    chapter_id=f"{chapter_id}_chunk_{idx:03d}",
                    en_title=None,
                    model_name=model_name,
                    cached_content=cached_content,
                    volume_cache=None,
                    scene_plan=None,  # Chunk-level ranges differ from full chapter scene plan.
                    allow_chunking=False,
                )
                if not chunk_result.success:
                    return TranslationResult(
                        False,
                        output_path,
                        input_tokens=total_input_tokens + chunk_result.input_tokens,
                        output_tokens=total_output_tokens + chunk_result.output_tokens,
                        error=f"Chunk {idx}/{total_chunks} failed: {chunk_result.error}",
                    )

                translated_chunk = chunk_output_path.read_text(encoding="utf-8").strip()
                chunk_payload = {
                    "chapter_id": chapter_id,
                    "chunk_index": idx,
                    "total_chunks": total_chunks,
                    "source_line_range": [chunk["line_start"], chunk["line_end"]],
                    "scene_break_before": chunk["scene_break_before"],
                    "scene_break_after": chunk["scene_break_after"],
                    "content": translated_chunk,
                    "last_sentence": self._extract_last_sentence(translated_chunk),
                    "tokens_in": chunk_result.input_tokens,
                    "tokens_out": chunk_result.output_tokens,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                with chunk_json_path.open("w", encoding="utf-8") as f:
                    json.dump(chunk_payload, f, ensure_ascii=False, indent=2)

                total_input_tokens += chunk_result.input_tokens
                total_output_tokens += chunk_result.output_tokens

                try:
                    chunk_source_path.unlink()
                    chunk_output_path.unlink()
                except Exception:
                    pass

            merger = ChunkMerger(self.context_manager.work_dir)
            merge_result = merger.merge_chapter(chapter_id, output_filename=output_path.name)
            merged_content = merge_result.output_path.read_text(encoding="utf-8")
            merged_content = self._compose_chapter_markdown(merged_content, en_title)

            merged_content, _ = SceneBreakFormatter.format_scene_breaks(merged_content)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(merged_content, encoding="utf-8")

            audit = QualityMetrics.quick_audit(merged_content, source_text)
            validation_warnings = list(audit.warnings or [])

            return TranslationResult(
                success=True,
                output_path=output_path,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                audit_result=audit,
                warnings=validation_warnings,
            )
        except Exception as e:
            logger.exception(f"Chunk translation failed for {chapter_id}")
            return TranslationResult(False, output_path, error=str(e))

    def _split_large_chapter(self, source_text: str) -> List[Dict[str, Any]]:
        """
        Split large chapter into line-accurate chunks.

        Prefers scene breaks ('◆') and blank lines as split boundaries.
        """
        lines = source_text.splitlines()
        if not lines:
            return []

        chunks: List[Dict[str, Any]] = []
        current: List[str] = []
        chunk_line_start = 1
        current_len = 0
        last_break_index = 0

        def flush(count: int) -> None:
            nonlocal current, chunk_line_start, current_len, last_break_index
            if count <= 0:
                return
            chunk_lines = current[:count]
            current = current[count:]

            chunk_line_end = chunk_line_start + count - 1
            chunk_text = "\n".join(chunk_lines).strip()
            if chunk_text:
                first_non_empty = next((ln.strip() for ln in chunk_lines if ln.strip()), "")
                last_non_empty = next((ln.strip() for ln in reversed(chunk_lines) if ln.strip()), "")
                chunks.append(
                    {
                        "content": chunk_text,
                        "line_start": chunk_line_start,
                        "line_end": chunk_line_end,
                        "scene_break_before": first_non_empty == "◆",
                        "scene_break_after": last_non_empty == "◆",
                    }
                )

            chunk_line_start = chunk_line_end + 1
            current_len = sum(len(ln) + 1 for ln in current)
            last_break_index = 0
            for i, ln in enumerate(current, start=1):
                if ln.strip() == "◆" or not ln.strip():
                    last_break_index = i

        for line in lines:
            current.append(line)
            current_len += len(line) + 1
            if line.strip() == "◆" or not line.strip():
                last_break_index = len(current)

            if current_len >= self.target_chunk_chars:
                split_at = last_break_index if last_break_index > 0 else len(current)
                flush(split_at)

        if current:
            flush(len(current))

        return chunks

    def _load_chunk_payload(self, chunk_json_path: Path) -> Optional[Dict[str, Any]]:
        if not chunk_json_path.exists():
            return None
        try:
            with chunk_json_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[CHUNK] Failed to read {chunk_json_path.name}: {e}")
            return None

    def _load_stage2_rhythm_targets(self) -> Dict[str, str]:
        """
        Load rhythm enum -> word range map from planning_config.json.

        Falls back to stable defaults if config is missing.
        """
        defaults = {
            "short_fragments": "4-6 words",
            "medium_casual": "8-10 words",
            "long_confession": "15-20 words",
        }
        config_path = PIPELINE_ROOT / "config" / "planning_config.json"
        if not config_path.exists():
            return defaults

        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.warning(f"[STAGE2] Failed reading planning_config.json: {e}")
            return defaults

        rhythm_targets = config.get("rhythm_targets", {})
        if not isinstance(rhythm_targets, dict):
            return defaults

        extracted: Dict[str, str] = {}
        for raw_key, raw_val in rhythm_targets.items():
            key = str(raw_key).strip()
            if not key:
                continue
            if isinstance(raw_val, dict):
                word_range = str(raw_val.get("word_range", "")).strip()
            else:
                word_range = str(raw_val).strip()
            if word_range:
                extracted[key] = word_range

        return extracted or defaults

    def _load_stage2_registers(self) -> List[str]:
        """Load allowed dialogue register enums from planning_config.json."""
        defaults = [
            "casual_teen",
            "flustered_defense",
            "smug_teasing",
            "formal_request",
            "breathless_shock",
        ]
        config_path = PIPELINE_ROOT / "config" / "planning_config.json"
        if not config_path.exists():
            return defaults

        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.warning(f"[STAGE2] Failed reading planning_config.json: {e}")
            return defaults

        registers = config.get("dialogue_registers", {})
        if isinstance(registers, dict):
            keys = [str(k).strip() for k in registers.keys() if str(k).strip()]
            return keys or defaults
        if isinstance(registers, list):
            keys = [str(v).strip() for v in registers if str(v).strip()]
            return keys or defaults
        return defaults

    @staticmethod
    def _normalize_stage2_token(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    @staticmethod
    def _parse_stage2_word_range(value: str) -> Optional[tuple]:
        if not value:
            return None
        match = re.search(r"(\d+)\s*[-–]\s*(\d+)", value)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            return (start, end)
        return None

    def _map_stage2_dialogue_register(self, raw_register: Any) -> str:
        """Map free-form dialogue register labels to configured enum values."""
        if not self._stage2_registers:
            return "casual_teen"

        fallback = "casual_teen" if "casual_teen" in self._stage2_registers else self._stage2_registers[0]
        text = str(raw_register or "").strip()
        if not text:
            return fallback
        norm = self._normalize_stage2_token(text)

        direct_map = {self._normalize_stage2_token(item): item for item in self._stage2_registers}
        if norm in direct_map:
            return direct_map[norm]
        for key, val in direct_map.items():
            if key and key in norm:
                return val

        tokens = set(norm.split("_")) if norm else set()
        if tokens.intersection({"formal", "polite", "request", "strategic", "assertive"}):
            return "formal_request" if "formal_request" in self._stage2_registers else fallback
        if tokens.intersection({"flustered", "defense", "defensive", "denial", "shy", "panic", "embarrassed"}):
            if "flustered_defense" in self._stage2_registers:
                return "flustered_defense"
            if "breathless_shock" in self._stage2_registers:
                return "breathless_shock"
            return fallback
        if tokens.intersection({"shock", "shocked", "breathless", "surprised"}):
            if "breathless_shock" in self._stage2_registers:
                return "breathless_shock"
            if "flustered_defense" in self._stage2_registers:
                return "flustered_defense"
            return fallback
        if tokens.intersection({"smug", "teasing", "playful", "competitive", "provocative", "banter"}):
            return "smug_teasing" if "smug_teasing" in self._stage2_registers else fallback
        if tokens.intersection({"internal", "monologue", "narration", "reflective"}):
            return fallback

        return fallback

    def _map_stage2_rhythm_key(self, raw_rhythm: Any) -> str:
        """Map free-form rhythm labels to configured rhythm target enum keys."""
        if not self._stage2_rhythm_targets:
            return "medium_casual"

        rhythm_keys = list(self._stage2_rhythm_targets.keys())
        default_key = "medium_casual" if "medium_casual" in self._stage2_rhythm_targets else rhythm_keys[0]
        text = str(raw_rhythm or "").strip()
        if not text:
            return default_key
        norm = self._normalize_stage2_token(text)

        direct_map = {self._normalize_stage2_token(key): key for key in rhythm_keys}
        if norm in direct_map:
            return direct_map[norm]
        for key_norm, key in direct_map.items():
            if key_norm and key_norm in norm:
                return key

        parsed = self._parse_stage2_word_range(text)
        if parsed:
            midpoint = (parsed[0] + parsed[1]) / 2.0
            best_key = default_key
            best_distance = float("inf")
            for key, word_range in self._stage2_rhythm_targets.items():
                parsed_key = self._parse_stage2_word_range(word_range)
                if not parsed_key:
                    continue
                key_midpoint = (parsed_key[0] + parsed_key[1]) / 2.0
                distance = abs(key_midpoint - midpoint)
                if distance < best_distance:
                    best_distance = distance
                    best_key = key
            return best_key

        tokens = set(norm.split("_")) if norm else set()
        if tokens.intersection({"quick", "fast", "rapid", "brief", "short", "snappy", "witty", "punchline", "reveal"}):
            return "short_fragments" if "short_fragments" in self._stage2_rhythm_targets else default_key
        if tokens.intersection({"slow", "deliberate", "reflective", "strategic", "tender", "confession", "sensual", "climactic"}):
            return "long_confession" if "long_confession" in self._stage2_rhythm_targets else default_key
        return default_key

    @staticmethod
    def _shorten_stage2_text(value: Any, limit: int = 110) -> str:
        text = str(value or "").strip().replace("\n", " ")
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 3)].rstrip()}..."

    def _format_stage2_scene_guidance(self, scene_plan: Optional[Dict[str, Any]]) -> str:
        """
        Build Stage 2 scene/rhythm scaffold injected into user prompt.

        Scope: English translation runs only.
        """
        if self.target_language.lower() not in {"en", "english"}:
            return ""
        if not isinstance(scene_plan, dict):
            return ""

        scenes = scene_plan.get("scenes", [])
        if not isinstance(scenes, list) or not scenes:
            return ""

        chapter_id = str(scene_plan.get("chapter_id") or "").strip()
        overall_tone = self._shorten_stage2_text(scene_plan.get("overall_tone"), 120)
        pacing = self._shorten_stage2_text(scene_plan.get("pacing_strategy"), 140)

        lines: List[str] = [
            "## STAGE 2 SCENE RHYTHM SCAFFOLD (MANDATORY)",
            "",
            "Apply this chapter-local scaffold while translating.",
            "Source precedence rule: Japanese source text is the only source of truth.",
            "Multimodal precedence rule: Visual/multimodal notes are descriptive only; never override source facts.",
            "Conflict rule: If scaffold conflicts with source, follow source text.",
            "",
            "Hard caps (English prose control):",
            "- Dialogue: <=10 words",
            "- Narration: <=15 words",
            "- Narration soft target: 12-14 words in descriptive passages",
            "- Punchline reaction beats: <=5 words",
            "",
            "Phase 2 anti-AI-ism blocklist (strict):",
            "- Do not use: \"couldn't help but\"",
            "- Rewrite directly: action/state without perception wrapper",
            "",
        ]
        if chapter_id:
            lines.append(f"Chapter scaffold ID: {chapter_id}")
        if overall_tone:
            lines.append(f"Overall tone: {overall_tone}")
        if pacing:
            lines.append(f"Pacing strategy: {pacing}")
        lines.append("")

        lines.append("Rhythm enum map:")
        for key, value in self._stage2_rhythm_targets.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

        lines.append("Scene beats:")
        for raw_scene in scenes:
            if not isinstance(raw_scene, dict):
                continue
            scene_id = str(raw_scene.get("id") or "scene").strip()
            beat_type = str(raw_scene.get("beat_type") or "setup").strip()
            start_para = raw_scene.get("start_paragraph")
            end_para = raw_scene.get("end_paragraph")
            para_range = "P?-?"
            if isinstance(start_para, int) and isinstance(end_para, int):
                para_range = f"P{start_para}-P{end_para}"
            elif isinstance(start_para, int):
                para_range = f"P{start_para}-P?"
            elif isinstance(end_para, int):
                para_range = f"P?-P{end_para}"

            register = str(raw_scene.get("dialogue_register") or "casual_teen").strip()
            register = self._map_stage2_dialogue_register(register)
            rhythm_key = self._map_stage2_rhythm_key(raw_scene.get("target_rhythm"))
            rhythm_range = self._stage2_rhythm_targets.get(rhythm_key, "")
            rhythm_display = f"{rhythm_key} ({rhythm_range})" if rhythm_range else rhythm_key
            arc = self._shorten_stage2_text(raw_scene.get("emotional_arc"), 100)

            lines.append(
                f"- {scene_id} [{para_range}] {beat_type} | register={register} | rhythm={rhythm_display}"
            )
            if arc:
                lines.append(f"  arc: {arc}")
            if bool(raw_scene.get("illustration_anchor")):
                lines.append("  note: illustration_anchor=true -> compress narration and trust the visual beat.")

        profiles = scene_plan.get("character_profiles", {})
        if isinstance(profiles, dict) and profiles:
            lines.append("")
            lines.append("Character rhythm anchors:")
            for name, raw_profile in list(profiles.items())[:12]:
                if not isinstance(raw_profile, dict):
                    continue
                bias = self._shorten_stage2_text(raw_profile.get("sentence_bias"), 80)
                emotional_state = self._shorten_stage2_text(raw_profile.get("emotional_state"), 80)
                lines.append(f"- {name}: bias={bias or 'N/A'}; state={emotional_state or 'N/A'}")

                victory = raw_profile.get("victory_patterns")
                if isinstance(victory, list) and victory:
                    sample = ", ".join(self._shorten_stage2_text(v, 45) for v in victory[:2])
                    lines.append(f"  victory cues: {sample}")

                denial = raw_profile.get("denial_patterns")
                if isinstance(denial, list) and denial:
                    sample = ", ".join(self._shorten_stage2_text(v, 45) for v in denial[:2])
                    lines.append(f"  denial cues: {sample}")

        return "\n".join(lines).strip()

    def _normalize_chapter_key(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        match = re.search(r"chapter[_\-\s]*0*(\d+)", raw, re.IGNORECASE)
        if not match:
            match = re.search(r"\bch[_\-\s]*0*(\d+)\b", raw, re.IGNORECASE)
        if not match:
            match = re.search(r"\b0*(\d{1,3})\b", raw)
        if not match:
            return ""
        return f"chapter_{int(match.group(1)):02d}"

    def _extract_chapter_key_from_location(self, location: str, scene_hint: str = "") -> str:
        if location:
            match = re.search(r"CHAPTER[_\-\s]*0*(\d+)", location, re.IGNORECASE)
            if match:
                return f"chapter_{int(match.group(1)):02d}"
        if scene_hint:
            match = re.search(r"CH(?:APTER)?[_\-\s]*0*(\d+)", scene_hint, re.IGNORECASE)
            if match:
                return f"chapter_{int(match.group(1)):02d}"
        return ""

    def _load_phase155_context_offload(self) -> Dict[str, Any]:
        """
        Load Phase 1.55 context offload caches from .context.

        Files are optional and translation remains functional when missing.
        """
        context_dir = self.context_manager.work_dir / ".context"
        cache_files = {
            "character_registry": context_dir / "character_registry.json",
            "cultural_glossary": context_dir / "cultural_glossary.json",
            "timeline_map": context_dir / "timeline_map.json",
            "idiom_transcreation_cache": context_dir / "idiom_transcreation_cache.json",
        }

        payload: Dict[str, Any] = {"_idiom_by_chapter": {}}
        loaded = 0
        for key, path in cache_files.items():
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    payload[key] = data
                    loaded += 1
            except Exception as e:
                logger.warning(f"[P1.55] Failed loading {path.name}: {e}")

        idiom_index: Dict[str, List[Dict[str, Any]]] = {}
        idiom_cache = payload.get("idiom_transcreation_cache", {})
        if isinstance(idiom_cache, dict):
            for key in ("transcreation_opportunities", "wordplay_transcreations"):
                records = idiom_cache.get(key, [])
                if not isinstance(records, list):
                    continue
                for item in records:
                    if not isinstance(item, dict):
                        continue
                    context = item.get("context", {})
                    chapter_key = self._extract_chapter_key_from_location(
                        str(item.get("location", "")),
                        str(context.get("scene", "")) if isinstance(context, dict) else "",
                    )
                    if not chapter_key:
                        continue
                    idiom_index.setdefault(chapter_key, []).append(item)
        payload["_idiom_by_chapter"] = idiom_index

        if loaded:
            logger.info(
                f"✓ Loaded Phase 1.55 context caches: {loaded}/4 "
                f"(idiom entries indexed: {sum(len(v) for v in idiom_index.values())})"
            )
        return payload

    def _select_idiom_opportunities(
        self,
        chapter_key: str,
        scene_plan: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        idiom_by_chapter = self._phase155_context.get("_idiom_by_chapter", {})
        if not isinstance(idiom_by_chapter, dict):
            return []
        candidates = idiom_by_chapter.get(chapter_key, [])
        if not isinstance(candidates, list) or not candidates:
            return []

        scene_ids = set()
        if isinstance(scene_plan, dict):
            scenes = scene_plan.get("scenes", [])
            if isinstance(scenes, list):
                for scene in scenes:
                    if isinstance(scene, dict):
                        sid = str(scene.get("id") or "").strip()
                        if sid:
                            scene_ids.add(sid.lower())
                            scene_ids.add(sid.upper())

        scoped: List[Dict[str, Any]] = []
        fallback: List[Dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            ctx = item.get("context", {})
            scene_hint = ""
            if isinstance(ctx, dict):
                scene_hint = str(ctx.get("scene", "")).strip()
            if scene_hint and scene_ids:
                if scene_hint in scene_ids or scene_hint.upper() in scene_ids or scene_hint.lower() in scene_ids:
                    scoped.append(item)
                else:
                    fallback.append(item)
            else:
                fallback.append(item)

        ranked = scoped or fallback

        priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def _score(item: Dict[str, Any]) -> tuple:
            priority = str(item.get("transcreation_priority", "medium")).lower()
            confidence = float(item.get("confidence", 0.0) or 0.0)
            return (priority_rank.get(priority, 4), -confidence)

        return sorted(ranked, key=_score)[:10]

    def _format_phase155_context_guidance(
        self,
        chapter_id: str,
        scene_plan: Optional[Dict[str, Any]],
    ) -> str:
        """
        Inject context offload outputs generated by Phase 1.55 co-processors.

        Focus: concise, stage-usable guidance without forcing rewrites.
        """
        if self.target_language.lower() not in {"en", "english"}:
            return ""
        if not isinstance(self._phase155_context, dict) or len(self._phase155_context) <= 1:
            return ""

        chapter_key = self._normalize_chapter_key(chapter_id)
        if not chapter_key:
            return ""

        lines: List[str] = [
            "## PHASE 1.55 CONTEXT OFFLOAD (CO-PROCESSORS)",
            "",
            "Use this as optional precision guidance. Japanese source text remains authoritative.",
            "Do not force transcreation where literal rendering is already natural.",
            "",
        ]

        char_registry = self._phase155_context.get("character_registry", {})
        if isinstance(char_registry, dict):
            chars = char_registry.get("characters", [])
            if isinstance(chars, list) and chars:
                lines.append("Character context (identity + relationships):")
                for char in chars[:6]:
                    if not isinstance(char, dict):
                        continue
                    name = str(
                        char.get("canonical_name")
                        or char.get("english_name")
                        or char.get("japanese_name")
                        or char.get("id")
                        or "character"
                    ).strip()
                    role = str(char.get("role") or "").strip()
                    register = str(char.get("voice_register") or "").strip()
                    snippet = f"- {name}"
                    if role:
                        snippet += f" | role={role}"
                    if register:
                        snippet += f" | voice={register}"
                    lines.append(snippet)
                lines.append("")

        cultural = self._phase155_context.get("cultural_glossary", {})
        if isinstance(cultural, dict):
            terms = cultural.get("terms", [])
            if isinstance(terms, list) and terms:
                lines.append("Cultural glossary (preferred renderings):")
                for term in terms[:8]:
                    if not isinstance(term, dict):
                        continue
                    jp = str(term.get("term_jp") or term.get("jp") or "").strip()
                    en = str(term.get("preferred_en") or term.get("en") or term.get("translation") or "").strip()
                    if not jp or not en:
                        continue
                    lines.append(f"- {jp} -> {en}")
                lines.append("")

        timeline_map = self._phase155_context.get("timeline_map", {})
        if isinstance(timeline_map, dict):
            chapter_timeline = timeline_map.get("chapter_timeline", [])
            if isinstance(chapter_timeline, list):
                matched = None
                for item in chapter_timeline:
                    if not isinstance(item, dict):
                        continue
                    if self._normalize_chapter_key(item.get("chapter_id")) == chapter_key:
                        matched = item
                        break
                if matched:
                    continuity = matched.get("continuity_constraints", [])
                    markers = matched.get("temporal_markers", [])
                    if isinstance(markers, list) and markers:
                        lines.append("Temporal markers for this chapter:")
                        for marker in markers[:4]:
                            lines.append(f"- {self._shorten_stage2_text(marker, 100)}")
                    if isinstance(continuity, list) and continuity:
                        lines.append("Continuity constraints:")
                        for note in continuity[:4]:
                            lines.append(f"- {self._shorten_stage2_text(note, 100)}")
                    if (isinstance(markers, list) and markers) or (isinstance(continuity, list) and continuity):
                        lines.append("")

        idiom_items = self._select_idiom_opportunities(chapter_key, scene_plan)
        if idiom_items:
            lines.append("Opportunistic idiom transcreation candidates:")
            lines.append("Apply only when it improves natural literary impact for this scene.")
            for item in idiom_items:
                if not isinstance(item, dict):
                    continue
                priority = str(item.get("transcreation_priority", "medium")).lower()
                confidence = float(item.get("confidence", 0.0) or 0.0)
                jp = self._shorten_stage2_text(item.get("japanese", ""), 80)
                meaning = self._shorten_stage2_text(item.get("meaning", ""), 90)
                location = self._shorten_stage2_text(item.get("location", ""), 40)
                lines.append(
                    f"- {location} | priority={priority} | conf={confidence:.2f} | jp=\"{jp}\" | meaning=\"{meaning}\""
                )
                options = item.get("options", [])
                if isinstance(options, list):
                    for option in options[:2]:
                        if not isinstance(option, dict):
                            continue
                        text = self._shorten_stage2_text(option.get("text", ""), 90)
                        o_conf = float(option.get("confidence", 0.0) or 0.0)
                        lines.append(f"  option: {text} (conf={o_conf:.2f})")
                guidance = str(item.get("stage_2_guidance", "")).strip()
                if guidance:
                    lines.append(f"  guidance: {self._shorten_stage2_text(guidance, 120)}")
            lines.append("")

        if len(lines) <= 4:
            return ""
        return "\n".join(lines).strip()

    def _extract_last_sentence(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return ""
        sentences = re.split(r"(?<=[.!?。！？])\s+", normalized)
        for sentence in reversed(sentences):
            cleaned = sentence.strip()
            if len(cleaned) >= 8:
                return cleaned
        return sentences[-1].strip() if sentences else ""

    def _build_user_prompt(
        self,
        chapter_id: str,
        source_text: str,
        context_str: str,
        chapter_title: Optional[str] = None,
        sino_vn_guidance: Optional[Dict] = None,
        gap_flags: Optional[Dict] = None,
        dialect_guidance: Optional[str] = None,  # v1.0 - Dialect detection
        en_pattern_guidance: Optional[Dict] = None,  # English grammar patterns
        vn_pattern_guidance: Optional[Dict] = None,  # Vietnamese grammar patterns
        visual_guidance: Optional[str] = None,  # Multimodal visual context
        scene_plan: Optional[Dict[str, Any]] = None,  # Stage 1 scene planner output
        volume_context: Optional[str] = None,  # Phase 1.2 - Volume-level context
    ) -> str:
        """Construct the user message part of the prompt."""
        # Build base prompt
        base_prompt = self.prompt_loader.build_translation_prompt(
            source_text=source_text,
            chapter_title=chapter_title or chapter_id,
            chapter_id=chapter_id,
            previous_context=context_str if context_str else None,
            name_registry=self.character_names if self.character_names else None
        )
        
        # Inject Sino-Vietnamese guidance if available (Vietnamese translations only)
        if sino_vn_guidance and sino_vn_guidance.get("high_confidence"):
            guidance_section = self._format_sino_vietnamese_guidance(sino_vn_guidance)
            # Insert guidance before the source text
            base_prompt = f"{base_prompt}\n\n{guidance_section}"
        
        # Inject Gap Analysis guidance if available (Week 2-3 integration)
        if gap_flags:
            gap_guidance = self._format_gap_guidance(gap_flags)
            if gap_guidance:
                base_prompt = f"{base_prompt}\n\n{gap_guidance}"
        
        # Inject Dialect Detection guidance if available (v1.0 - 2026-02-01)
        if dialect_guidance:
            base_prompt = f"{base_prompt}\n\n{dialect_guidance}"

        # Inject English grammar pattern guidance if available (English translations only)
        if en_pattern_guidance and en_pattern_guidance.get("high_confidence"):
            pattern_section = self._format_english_pattern_guidance(en_pattern_guidance)
            # Insert guidance before the source text
            base_prompt = f"{base_prompt}\n\n{pattern_section}"

        # Inject Vietnamese grammar pattern guidance if available (Vietnamese translations only)
        if vn_pattern_guidance and vn_pattern_guidance.get("high_confidence"):
            vn_pattern_section = self._format_vietnamese_pattern_guidance(vn_pattern_guidance)
            # Insert guidance before the source text
            base_prompt = f"{base_prompt}\n\n{vn_pattern_section}"

        # Inject multimodal visual context if available
        if visual_guidance:
            from modules.multimodal.prompt_injector import MULTIMODAL_STRICT_SUFFIX
            base_prompt = f"{base_prompt}\n\n{visual_guidance}\n{MULTIMODAL_STRICT_SUFFIX}"

        # === VOLUME CONTEXT INJECTION (Phase 1.2) ===
        # Per Gemini best practices: "context before query"
        # Volume context should appear early in prompt for best results
        if volume_context:
            logger.debug(f"[VOLUME-CTX] Injecting volume context ({len(volume_context)} chars)")
            volume_section = f"\n\n---\n\n# VOLUME-LEVEL CONTEXT\n\n{volume_context}\n\n---"
            base_prompt = f"{base_prompt}{volume_section}"
        # === END VOLUME CONTEXT ===

        # Inject Stage 2 scene/rhythm scaffold before source text section.
        stage2_scene_guidance = self._format_stage2_scene_guidance(scene_plan)
        if stage2_scene_guidance:
            marker = "<!-- SOURCE TEXT TO TRANSLATE -->"
            if marker in base_prompt:
                base_prompt = base_prompt.replace(
                    marker,
                    f"<!-- STAGE 2 SCENE GUIDANCE -->\n{stage2_scene_guidance}\n\n{marker}",
                    1,
                )
            else:
                base_prompt = f"{stage2_scene_guidance}\n\n{base_prompt}"

        # Inject Phase 1.55 context offload co-processor guidance.
        p155_context_guidance = self._format_phase155_context_guidance(chapter_id, scene_plan)
        if p155_context_guidance:
            marker = "<!-- SOURCE TEXT TO TRANSLATE -->"
            if marker in base_prompt:
                base_prompt = base_prompt.replace(
                    marker,
                    f"<!-- PHASE 1.55 CONTEXT OFFLOAD -->\n{p155_context_guidance}\n\n{marker}",
                    1,
                )
            else:
                base_prompt = f"{p155_context_guidance}\n\n{base_prompt}"

        # Inject RTAS character voice settings (English translations only)
        rtas_guidance = self._format_rtas_guidance()
        if rtas_guidance:
            base_prompt = f"{base_prompt}\n\n{rtas_guidance}"

        return base_prompt
    
    def _format_sino_vietnamese_guidance(self, guidance: Dict[str, Any]) -> str:
        """Format Sino-Vietnamese guidance for prompt injection."""
        lines = ["## Sino-Vietnamese Term Guidance", ""]
        lines.append("The following Vietnamese translations for Sino-Vietnamese (Hán Việt) terms are recommended:")
        lines.append("")
        
        # High confidence matches
        for item in guidance.get("high_confidence", [])[:10]:  # Limit to top 10
            hanzi = item["hanzi"]
            vn = item["vn"]
            meaning = item.get("meaning", "")
            avoid = item.get("avoid", "")
            
            entry = f"- **{hanzi}** → **{vn}**"
            if meaning:
                entry += f" ({meaning})"
            if avoid:
                entry += f" [Avoid: {avoid}]"
            lines.append(entry)
        
        lines.append("")
        return "\n".join(lines)
    
    def _format_gap_guidance(self, gap_flags: Dict) -> str:
        """
        Format gap analysis guidance for prompt injection.
        
        Provides translator with critical context about:
        - Gap A: Emotion+Action markers requiring special treatment
        - Gap B: Ruby visual jokes and kira-kira names
        - Gap C: Sarcasm/subtext markers
        """
        gap_a = gap_flags.get('gap_a', [])
        gap_b = gap_flags.get('gap_b', [])
        gap_c = gap_flags.get('gap_c', [])
        
        total_gaps = len(gap_a) + len(gap_b) + len(gap_c)
        if total_gaps == 0:
            return ""
        
        lines = ["## Translation Guidance: Semantic Gaps Detected", ""]
        lines.append(f"This chapter contains **{total_gaps} semantic gap(s)** requiring special attention:")
        lines.append("")
        
        # Gap A: Emotion + Action Surgery
        if gap_a:
            lines.append(f"### Gap A: Emotion+Action Markers ({len(gap_a)} instances)")
            lines.append("The following lines contain emotional state markers combined with physical actions.")
            lines.append("**Treatment:** Separate emotion from action. Translate emotion explicitly, keep action natural.")
            lines.append("")
            for flag in gap_a[:5]:  # Show top 5
                line_num = flag.get('line_number', 'N/A')
                context = flag.get('context', '')[:80]  # First 80 chars
                lines.append(f"- **Line {line_num}:** `{context}...`")
            if len(gap_a) > 5:
                lines.append(f"  _(+{len(gap_a) - 5} more instances)_")
            lines.append("")
        
        # Gap B: Ruby Visual Jokes
        if gap_b:
            lines.append(f"### Gap B: Ruby Visual Jokes ({len(gap_b)} instances)")
            lines.append("The following lines contain ruby annotations with semantic significance:")
            lines.append("")
            
            kira_kira_count = sum(1 for f in gap_b if f.get('ruby_type') == 'kira_kira')
            char_name_count = sum(1 for f in gap_b if f.get('ruby_type') == 'character_name')
            archaic_count = sum(1 for f in gap_b if f.get('ruby_type') == 'archaic')
            
            if kira_kira_count > 0:
                lines.append(f"**Kira-kira Names ({kira_kira_count}):** Unusual character name readings with wordplay.")
                lines.append("**Treatment:** Use romanized reading + TL note explaining the pun.")
                for flag in [f for f in gap_b if f.get('ruby_type') == 'kira_kira'][:3]:
                    kanji = flag.get('kanji', '')
                    reading = flag.get('reading', '')
                    lines.append(f"- `{kanji}{{読み: {reading}}}` → Add footnote explaining the name's meaning")
                lines.append("")
            
            if char_name_count > 0:
                lines.append(f"**Character Names ({char_name_count}):** Standard name rubies for pronunciation.")
                lines.append("**Treatment:** Use established romanization from character roster.")
                lines.append("")
            
            if archaic_count > 0:
                lines.append(f"**Archaic Kanji ({archaic_count}):** Old-style readings for atmosphere.")
                lines.append("**Treatment:** Use contextual English equivalent (e.g., 頷→nod, 呟→mutter).")
                lines.append("")
        
        # Gap C: Sarcasm/Subtext
        if gap_c:
            lines.append(f"### Gap C: Sarcasm/Subtext Markers ({len(gap_c)} instances)")
            lines.append("The following lines contain implicit meaning or tonal subtext:")
            lines.append("**Treatment:** Add narrative clarification or adjust tone to convey hidden meaning.")
            lines.append("")
            for flag in gap_c[:5]:
                line_num = flag.get('line_number', 'N/A')
                context = flag.get('context', '')[:80]
                marker = flag.get('marker_type', 'unknown')
                lines.append(f"- **Line {line_num}** ({marker}): `{context}...`")
            if len(gap_c) > 5:
                lines.append(f"  _(+{len(gap_c) - 5} more instances)_")
            lines.append("")
        
        lines.append("---")
        lines.append("**Note:** These gaps are automatically detected. Use your judgment to preserve intent.")
        lines.append("")

        return "\n".join(lines)

    def _format_english_pattern_guidance(self, guidance: Dict[str, Any]) -> str:
        """
        Format English grammar pattern guidance for prompt injection.

        Provides translator with natural English phrasing suggestions for
        detected Japanese grammar patterns.
        """
        lines = ["## Natural English Phrasing Guidance", ""]
        lines.append("The following Japanese grammar patterns were detected in this chapter.")
        lines.append("Consider using these natural English equivalents for more idiomatic phrasing:")
        lines.append("")

        # High confidence matches
        high_confidence = guidance.get("high_confidence", [])
        if not high_confidence:
            return ""  # No high-confidence patterns to inject

        for item in high_confidence[:8]:  # Limit to top 8 to avoid prompt bloat
            jp_structure = item.get("japanese_structure", "")
            en_pattern = item.get("english_pattern", "")
            natural_ex = item.get("natural_example", "")
            jp_ex = item.get("jp_example", "")
            similarity = item.get("similarity", 0.0)

            # Format pattern entry
            entry = f"- **{jp_structure}** → **{en_pattern}**"
            lines.append(entry)

            # Add natural example if available
            if natural_ex:
                lines.append(f"  *Example:* \"{natural_ex}\"")

            # Add confidence indicator for very high matches
            if similarity >= 0.90:
                lines.append(f"  _(High confidence: {similarity:.2f})_")

            lines.append("")

        lines.append("---")
        lines.append("**Note:** Use these patterns to achieve natural, conversational English instead of literal translations.")
        lines.append("")

        return "\n".join(lines)

    def _format_vietnamese_pattern_guidance(self, guidance: Dict[str, Any]) -> str:
        """
        Format Vietnamese grammar pattern guidance for prompt injection.

        Provides translator with natural Vietnamese phrasing suggestions for
        detected Japanese grammar patterns. Includes anti-AI-ism warnings.
        """
        lines = ["## Hướng Dẫn Diễn Đạt Tiếng Việt Tự Nhiên", ""]
        lines.append("Các mẫu ngữ pháp tiếng Nhật sau đã được phát hiện trong chương này.")
        lines.append("Sử dụng cách diễn đạt tiếng Việt tự nhiên sau thay vì dịch trực tiếp:")
        lines.append("")

        # High confidence matches
        high_confidence = guidance.get("high_confidence", [])
        if not high_confidence:
            return ""  # No high-confidence patterns to inject

        for item in high_confidence[:8]:  # Limit to top 8
            jp_structure = item.get("japanese_structure", "")
            vn_pattern = item.get("vietnamese_pattern", "")
            natural_ex = item.get("natural_example", "")
            jp_ex = item.get("jp_example", "")
            similarity = item.get("similarity", 0.0)
            usage_rules = item.get("usage_rules", [])

            # Format pattern entry
            entry = f"- **{jp_structure}** → **{vn_pattern}**"
            lines.append(entry)

            # Add natural example if available
            if natural_ex:
                lines.append(f"  *Ví dụ:* \"{natural_ex}\"")

            # Add first usage rule as hint
            if usage_rules and usage_rules[0]:
                lines.append(f"  _Lưu ý: {usage_rules[0]}_")

            # Add confidence indicator for very high matches
            if similarity >= 0.90:
                lines.append(f"  _(Độ tin cậy cao: {similarity:.2f})_")

            lines.append("")

        lines.append("---")
        lines.append("**QUAN TRỌNG:** Tránh các lỗi AI-ism: 'một cách [adj]', 'một cảm giác', 'Sự [verb]', 'Việc [verb]'.")
        lines.append("Dùng tiếng Việt tự nhiên như người bản xứ đọc light novel.")
        lines.append("")

        return "\n".join(lines)

    def _clean_output(self, text: str) -> str:
        """Clean up LLM output (remove markdown code blocks if present)."""
        # Remove ```markdown and ``` if fully wrapped
        # Sometimes models wrap the whole thing
        pattern = r"^```(?:markdown)?\s*(.*)\s*```$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _compose_chapter_markdown(self, body: str, en_title: Optional[str]) -> str:
        """
        Compose final chapter markdown with at most one top-level H1 title.

        If `en_title` is provided, any model-emitted leading H1 is removed first so
        we never produce duplicate chapter headers in EN output.
        """
        normalized_body = self._clean_output(body or "")
        if en_title:
            stripped_body, removed_h1 = self._strip_leading_h1(normalized_body)
            if removed_h1:
                logger.info(f"Removed model-emitted leading H1 before title injection: {removed_h1}")
            if stripped_body:
                composed = f"# {en_title}\n\n{stripped_body}"
            else:
                composed = f"# {en_title}"
        else:
            composed = normalized_body

        deduped, removed_count = self._dedupe_consecutive_top_h1(composed)
        if removed_count > 0:
            logger.info(f"Removed {removed_count} duplicate top-level chapter header(s)")
        return deduped

    def _strip_leading_h1(self, text: str) -> tuple[str, Optional[str]]:
        """Remove the first non-empty top-level H1 at file start, if present."""
        lines = (text or "").splitlines()
        if not lines:
            return "", None

        idx = 0
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return "", None

        first = lines[idx].strip()
        if not (first.startswith("# ") and not first.startswith("## ")):
            return text.strip(), None

        removed_h1 = first[2:].strip()
        remaining = lines[:idx] + lines[idx + 1 :]
        return "\n".join(remaining).strip(), removed_h1

    def _dedupe_consecutive_top_h1(self, text: str) -> tuple[str, int]:
        """
        Remove consecutive duplicate H1 headers near the top of content.

        Handles patterns like:
          # Chapter 1
          # Chapter 1
        """
        lines = (text or "").splitlines()
        if not lines:
            return "", 0

        changed = 0
        while True:
            idx = 0
            while idx < len(lines) and not lines[idx].strip():
                idx += 1
            if idx >= len(lines):
                break

            first = lines[idx].strip()
            if not (first.startswith("# ") and not first.startswith("## ")):
                break

            j = idx + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break

            second = lines[j].strip()
            if second != first:
                break

            # Drop duplicate header and keep surrounding body.
            del lines[j]
            changed += 1

        return "\n".join(lines).strip(), changed

    def _detect_cross_chapter_heading_bleed(
        self,
        text: str,
        chapter_id: str,
        en_title: Optional[str],
    ) -> List[str]:
        """
        Detect likely cross-chapter bleed by scanning top-level H1 chapter headings.

        Returns a list of suspicious top-level headings found in content.
        """
        if not text:
            return []
        lines = (text or "").splitlines()
        h1_lines = [ln.strip() for ln in lines if re.match(r"^#\s+.+", ln.strip()) and not ln.strip().startswith("## ")]
        if len(h1_lines) <= 1:
            return []

        expected_numbers = set()
        for candidate in (chapter_id, en_title):
            if not candidate:
                continue
            m = re.search(r"(\d+)", str(candidate))
            if m:
                try:
                    expected_numbers.add(int(m.group(1)))
                except Exception:
                    pass

        suspicious: List[str] = []
        for h in h1_lines[1:]:
            m = re.search(r"chapter\s+(\d+)", h, flags=re.IGNORECASE)
            if not m:
                suspicious.append(h)
                continue
            try:
                num = int(m.group(1))
            except Exception:
                suspicious.append(h)
                continue
            if expected_numbers and num not in expected_numbers:
                suspicious.append(h)

        return suspicious
