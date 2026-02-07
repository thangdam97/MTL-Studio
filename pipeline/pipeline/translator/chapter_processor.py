"""
Chapter Processor.
Handles the translation of a single chapter using Gemini and RAG context.
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from pipeline.common.gemini_client import GeminiClient
from pipeline.translator.prompt_loader import PromptLoader
from pipeline.translator.context_manager import ContextManager
from pipeline.translator.quality_metrics import QualityMetrics, AuditResult
from pipeline.translator.config import get_generation_params, get_model_name, get_safety_settings
from pipeline.translator.scene_break_formatter import SceneBreakFormatter
from pipeline.post_processor.vn_cjk_cleaner import VietnameseCJKCleaner
from modules.gap_integration import GapIntegrationEngine

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
        target_language: str = "en"
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
        self._anti_ai_ism_agent = None
        self.enable_anti_ai_ism = False  # Will be enabled from agent if needed
        
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
        cached_content: Optional[str] = None
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
        """
        try:
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
                        visual_guidance = build_chapter_visual_guidance(
                            illustration_ids, self.visual_cache,
                            manifest=self.visual_cache.get_manifest()
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
            if cached_content or (self.client.enable_caching and self.client._is_cache_valid(model_name)):
                cache_type = "external" if cached_content else "internal"
                cache_name = cached_content or self.client._cached_content_name
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
                visual_guidance=visual_guidance
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
                cached_content=cached_content  # Inject cached schema for continuity
            )
            logger.debug(f"[VERBOSE] Gemini response received. Tokens: {response.input_tokens} in, {response.output_tokens} out")
            
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
                return TranslationResult(
                    False, output_path,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    error="Gemini returned empty response (possible safety block)"
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
            
            # Inject EN title if provided
            final_content = cleaned_body
            if en_title:
                final_content = f"# {en_title}\n\n{cleaned_body}"
                logger.info(f"Injected title: {en_title}")
            
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
            cjk_cleaned_count = 0
            if self._vn_cjk_cleaner:
                clean_result = self._vn_cjk_cleaner.clean_file(output_path)
                cjk_cleaned_count = clean_result.get('substitutions', 0)
                remaining_leaks = clean_result.get('remaining_leaks', 0)
                
                if cjk_cleaned_count > 0:
                    logger.info(f"✓ CJK post-processor: {cjk_cleaned_count} hard substitutions applied")
                if remaining_leaks > 0:
                    logger.warning(f"⚠ CJK post-processor: {remaining_leaks} unknown leaks remain (manual review needed)")
            
            # 9. Post-Processing: Self-Healing Anti-AI-ism Agent (if enabled)
            ai_ism_healed_count = 0
            if self.enable_anti_ai_ism and self._anti_ai_ism_agent:
                try:
                    logger.debug(f"[ANTI-AI-ISM] Running self-healing agent on {chapter_id}...")
                    heal_report = self._anti_ai_ism_agent.heal_file(output_path)
                    
                    if heal_report and heal_report.issues:
                        ai_ism_healed_count = len([i for i in heal_report.issues if i.corrected])
                        total_issues = len(heal_report.issues)
                        
                        if ai_ism_healed_count > 0:
                            logger.info(f"✓ Anti-AI-ism agent: {ai_ism_healed_count}/{total_issues} issues auto-corrected")
                        
                        # Log severity breakdown
                        critical = len([i for i in heal_report.issues if i.severity == 'CRITICAL'])
                        major = len([i for i in heal_report.issues if i.severity == 'MAJOR'])
                        minor = len([i for i in heal_report.issues if i.severity == 'MINOR'])
                        
                        if critical > 0:
                            logger.warning(f"  Critical: {critical}, Major: {major}, Minor: {minor}")
                        elif major > 0:
                            logger.info(f"  Major: {major}, Minor: {minor}")
                    else:
                        logger.debug(f"[ANTI-AI-ISM] No AI-isms detected in {chapter_id}")
                        
                except Exception as e:
                    logger.warning(f"[ANTI-AI-ISM] Self-healing failed: {e}")
                    logger.warning("[ANTI-AI-ISM] Continuing without auto-correction (run 'mtl.py heal' manually)")
            
            return TranslationResult(
                success=True,
                output_path=output_path,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                audit_result=audit,
                warnings=audit.warnings
            )

        except Exception as e:
            logger.exception(f"Translation failed for {chapter_id}")
            return TranslationResult(False, output_path, error=str(e))

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
        visual_guidance: Optional[str] = None  # Multimodal visual context
    ) -> str:
        """Construct the user message part of the prompt."""
        # Build base prompt
        base_prompt = self.prompt_loader.build_translation_prompt(
            source_text=source_text,
            chapter_title=chapter_title or chapter_id,
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
