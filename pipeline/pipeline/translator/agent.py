"""
Translator Agent Orchestrator.
Main entry point for Phase 2: Translation.
Supports multi-language configuration (EN, VN, etc.)
"""

import json
import logging
import argparse
import sys
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

from pipeline.common.gemini_client import GeminiClient
from pipeline.translator.config import get_gemini_config, get_translation_config, get_model_name, get_fallback_model_name
from pipeline.translator.prompt_loader import PromptLoader
from pipeline.translator.context_manager import ContextManager
from pipeline.translator.chapter_processor import ChapterProcessor, TranslationResult
from pipeline.translator.continuity_manager import detect_and_offer_continuity, ContinuityPackManager
from pipeline.translator.per_chapter_workflow import PerChapterWorkflow
from pipeline.translator.glossary_lock import GlossaryLock
from pipeline.translator.series_bible import BibleController
from pipeline.config import get_target_language, get_language_config, PIPELINE_ROOT
from modules.gap_integration import GapIntegrationEngine


@dataclass
class TranslationReport:
    """Summary report from Translator agent."""
    volume_id: str
    chapters_total: int
    chapters_completed: int
    chapters_failed: int
    total_input_tokens: int
    total_output_tokens: int
    average_quality_score: float
    status: str  # 'completed', 'partial', 'failed'
    started_at: str
    completed_at: str
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for verbose output
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TranslatorAgent")

class TranslatorAgent:
    _CHAPTER_ID_PATTERN = re.compile(r"chapter[_\-](\d+)", re.IGNORECASE)
    _EN_CHAPTER_NUM_PATTERN = re.compile(r"\bchapter\s+(\d+)\b", re.IGNORECASE)

    def __init__(self, work_dir: Path, target_language: str = None, enable_continuity: bool = False,
                 enable_gap_analysis: bool = False, enable_multimodal: bool = False):
        """
        Initialize TranslatorAgent.

        Args:
            work_dir: Path to the volume working directory.
            target_language: Target language code (e.g., 'en', 'vn').
                            If None, uses current target language from config.
            enable_continuity: Enable schema extraction and continuity features (default: False).
                             ⚠️  ALPHA EXPERIMENTAL - Highly unstable, may cause interruptions.
            enable_gap_analysis: Enable semantic gap analysis (Week 2-3 integration).
                               Detects and guides translation of emotion+action, ruby jokes, and sarcasm.
            enable_multimodal: Enable multimodal visual context injection (default: False).
                             Injects pre-baked visual analysis into translation prompts.
                             Requires Phase 1.6 (mtl.py phase1.6) to have been run first.
        """
        self.work_dir = work_dir
        self.manifest_path = work_dir / "manifest.json"
        self.enable_continuity = enable_continuity
        self.enable_gap_analysis = enable_gap_analysis

        # Language configuration
        self.target_language = target_language if target_language else get_target_language()
        self.lang_config = get_language_config(self.target_language)
        self.language_name = self.lang_config.get('language_name', self.target_language.upper())

        logger.info(f"TranslatorAgent initialized for language: {self.target_language.upper()} ({self.language_name})")
        
        if enable_continuity:
            logger.warning("⚠️  [ALPHA EXPERIMENTAL] Continuity system enabled - highly unstable!")
            logger.warning("   This feature may cause interruptions and requires manual schema review.")
        else:
            logger.info("✓ Using standard translation mode (continuity disabled)")
        
        if enable_gap_analysis:
            logger.info("✓ Gap analysis enabled (Week 2-3 integration)")
            logger.info("  Semantic gaps will be detected and guide translation decisions")

        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {self.manifest_path}")

        self.manifest = self._load_manifest()
        self.translation_config = get_translation_config()

        massive_cfg = self.translation_config.get("massive_chapter", {})
        self.volume_cache_enabled = massive_cfg.get("enable_volume_cache", True)
        self.volume_cache_ttl_seconds = int(massive_cfg.get("volume_cache_ttl_seconds", 7200))
        self.volume_cache_name: Optional[str] = None
        self._volume_cache_stats: Dict[str, Any] = {}
        
        # Auto-detect enable_multimodal from config.yaml if not explicitly set
        if not enable_multimodal:
            enable_multimodal = self.translation_config.get('enable_multimodal', False)
            if enable_multimodal:
                logger.info("✓ Multimodal translation enabled (config.yaml)")
        
        self.enable_multimodal = enable_multimodal

        if self.enable_multimodal:
            logger.info("✓ Multimodal visual analysis active")
            logger.info("  Pre-baked visual context will be injected into translation prompts")

        # Detect and offer continuity pack injection (only if continuity enabled)
        if enable_continuity:
            self.continuity_pack = detect_and_offer_continuity(work_dir, self.manifest, target_language=self.target_language)
        else:
            self.continuity_pack = None

        # Initialize components with model from config
        model_name = get_model_name()
        logger.info(f"Using model: {model_name}")

        # Get caching config
        gemini_config = get_gemini_config()
        caching_config = gemini_config.get("caching", {})
        enable_caching = caching_config.get("enabled", True)
        cache_ttl = caching_config.get("ttl_minutes", 120)

        if enable_caching:
            logger.info(f"✓ Context caching enabled (TTL: {cache_ttl} minutes)")
        else:
            logger.info("Context caching disabled")

        self.client = GeminiClient(model=model_name, enable_caching=enable_caching)
        self.client.set_cache_ttl(cache_ttl)

        # Initialize PromptLoader with target language
        self.prompt_loader = PromptLoader(target_language=self.target_language)
        
        # Load style guide for Vietnamese translations (genre-specific selection)
        if self.target_language in ['vi', 'vn']:
            logger.info("Loading Vietnamese style guide system...")
            try:
                # Extract publisher from manifest if available
                publisher = self.manifest.get('publisher_id', 'overlap')
                
                # Determine genre from manifest metadata (default to romcom for modern settings)
                genre_from_manifest = self.manifest.get('genre', 'romcom_school_life')
                genres_to_load = [genre_from_manifest] if genre_from_manifest else ['romcom_school_life']
                
                # Load specific genre (not all genres - avoids fantasy rules in modern romcom)
                self.prompt_loader.load_style_guide(genres=genres_to_load, publisher=publisher)
            except Exception as e:
                logger.warning(f"Failed to load style guide: {e}")
                logger.warning("Continuing without style guide (translation quality may be reduced)")
        
        self.context_manager = ContextManager(work_dir)

        # ── Bible System (Phase C) ─────────────────────────────────
        # Load series bible BEFORE glossary — bible terms supplement manifest names
        self.bible = None
        self._bible_glossary = {}
        try:
            bible_ctrl = BibleController(PIPELINE_ROOT)
            self.bible = bible_ctrl.load(self.manifest, work_dir)
            if self.bible:
                self._bible_glossary = self.bible.flat_glossary()
                stats = self.bible.stats()
                logger.info(f"✓ Series Bible loaded: {self.bible.series_id}")
                logger.info(f"  {stats['total_entries']} entries across {stats['volumes']} volumes")
                logger.info(f"  World: {self.bible.world_setting.get('label', self.bible.world_setting.get('type', '?'))}")
                logger.info(f"  Bible glossary: {len(self._bible_glossary)} terms")
                # Phase E: Inject bible prompt + world directive + dedup keys
                bible_prompt = self.bible.format_for_prompt()
                world_directive = self.bible.format_world_setting_directive()
                self.prompt_loader.set_bible_prompt(
                    bible_prompt,
                    world_directive=world_directive,
                    bible_glossary_keys=set(self._bible_glossary.keys())
                )
            else:
                logger.debug("No series bible found for this volume (standalone)")
        except Exception as e:
            # Hard fallback path: ignore bible and continue with manifest-only continuity.
            self.bible = None
            self._bible_glossary = {}
            logger.warning(
                f"Bible system error (non-fatal): {e}. "
                "Falling back to manifest-based continuity."
            )

        # Load and inject character names from manifest (for cached system instruction)
        character_names = self._load_character_names()
        self.glossary_lock = GlossaryLock(
            work_dir,
            target_language=self.target_language,
            bible_glossary=self._bible_glossary
        )
        locked_glossary = self.glossary_lock.get_locked_names()
        if locked_glossary:
            logger.info(f"✓ GlossaryLock loaded {len(locked_glossary)} locked name mappings")
        else:
            logger.warning("GlossaryLock found no manifest name mappings; name drift checks may be weaker")
        
        # Load full semantic metadata (Enhanced v2.1)
        semantic_metadata = self._load_semantic_metadata()
        
        # Inject continuity pack if available (merge with current volume)
        if self.continuity_pack:
            # Extract character names and glossary from continuity pack
            continuity_names = self.continuity_pack.roster
            continuity_glossary = self.continuity_pack.glossary or {}
            
            # Merge with current volume's names (current volume overrides continuity)
            merged_names = {**continuity_names, **character_names}  # Current volume takes precedence
            
            # Set merged names for caching
            if merged_names:
                self.prompt_loader.set_character_names(merged_names)
                logger.info(f"✓ Loaded {len(merged_names)} character names (including {len(continuity_names)} from continuity pack)")
            
            # Set glossary for caching
            merged_glossary = {**continuity_glossary, **locked_glossary}
            if merged_glossary:
                self.prompt_loader.set_glossary(merged_glossary)
                logger.info(
                    f"✓ Loaded {len(merged_glossary)} glossary terms "
                    f"({len(continuity_glossary)} continuity + {len(locked_glossary)} locked)"
                )
            
            # Format and inject full continuity pack (relationships, narrative flags, etc.)
            continuity_manager = ContinuityPackManager(work_dir)
            continuity_text = continuity_manager.format_continuity_for_prompt(self.continuity_pack)
            self.prompt_loader.set_continuity_pack(continuity_text)
            logger.info(f"✓ Continuity pack formatted and injected ({len(continuity_text)} characters)")
        elif character_names:
            # No continuity pack, just use current volume's names
            self.prompt_loader.set_character_names(character_names)
            logger.info(f"✓ Character names loaded and set for caching ({len(character_names)} entries)")
            if locked_glossary:
                self.prompt_loader.set_glossary(locked_glossary)
                logger.info(f"✓ Loaded {len(locked_glossary)} locked glossary terms from manifest")
        elif locked_glossary:
            self.prompt_loader.set_glossary(locked_glossary)
            logger.info(f"✓ Loaded {len(locked_glossary)} locked glossary terms from manifest")
        
        # Inject semantic metadata (Enhanced v2.1) into system instruction
        if semantic_metadata:
            self.prompt_loader.set_semantic_metadata(semantic_metadata)
            char_count = len(semantic_metadata.get('characters', []))
            pattern_count = len(semantic_metadata.get('dialogue_patterns', {}))
            scene_count = len(semantic_metadata.get('scene_contexts', {}))
            logger.info(f"✓ Semantic metadata injected: {char_count} characters, {pattern_count} dialogue patterns, {scene_count} scenes")

        self.processor = ChapterProcessor(
            self.client,
            self.prompt_loader,
            self.context_manager,
            target_language=self.target_language
        )
        self.processor.set_glossary_lock(self.glossary_lock)

        # Initialize multimodal visual cache if enabled
        self.visual_cache_manager = None
        if self.enable_multimodal:
            try:
                from modules.multimodal.cache_manager import VisualCacheManager
                self.visual_cache_manager = VisualCacheManager(work_dir)
                if self.visual_cache_manager.has_cache():
                    stats = self.visual_cache_manager.get_cache_stats()
                    logger.info(f"✓ Visual cache loaded: {stats['total']} entries "
                               f"({stats['cached']} cached, {stats['safety_blocked']} blocked, "
                               f"{stats['manual_override']} manual)")
                    # Connect to processor
                    self.processor.enable_multimodal = True
                    self.processor.visual_cache = self.visual_cache_manager
                else:
                    logger.warning("⚠️  No visual cache found. Run 'mtl.py phase0 <volume_id>' first.")
                    logger.warning("   Continuing without multimodal context (text-only mode)")
                    self.enable_multimodal = False
            except Exception as e:
                logger.warning(f"Failed to initialize multimodal: {e}")
                logger.warning("Continuing without multimodal context")
                self.enable_multimodal = False

        # Initialize gap analyzer if enabled (Week 2-3 integration)
        if self.enable_gap_analysis:
            try:
                from modules.gap_integration import GapIntegrationEngine
                self.gap_analyzer = GapIntegrationEngine(self.work_dir, target_language=self.target_language)
                # Enable gap analysis in processor
                self.processor.enable_gap_analysis = True
                self.processor.gap_analyzer = self.gap_analyzer
                logger.info("✓ Gap analyzer initialized and connected to processor")
            except Exception as e:
                logger.warning(f"Failed to initialize gap analyzer: {e}")
                logger.warning("Continuing without gap analysis")
                self.enable_gap_analysis = False
                self.gap_analyzer = None
        else:
            self.gap_analyzer = None

        # Stability mode: force-disable automatic self-healing Anti-AI-ism in Translator.
        # Manual pass is still available via `mtl.py heal`.
        if self.target_language in ['en', 'vn', 'vi']:
            self.processor.enable_anti_ai_ism = False
            self.processor._anti_ai_ism_agent = None
            logger.info("Self-healing Anti-AI-ism agent is force-disabled in codebase for translator runs.")

        # Translation Log
        self.log_path = work_dir / "translation_log.json"
        self.translation_log = self._load_log()
        
        # Per-Chapter Workflow (schema extraction, review, caching)
        self.per_chapter_workflow = PerChapterWorkflow(
            work_dir=work_dir,
            target_language=self.target_language,
            enable_caching=enable_caching,
            gemini_client=self.client.client if hasattr(self.client, 'client') else None
        )

    def _load_character_names(self) -> Dict[str, str]:
        """
        Load character names from language-specific metadata file.
        
        LEGACY SUPPORT: This method loads the simple character_names dict (JP→EN mappings)
        for continuity pack merging. With v3 enhanced schema, character names are now
        part of character_profiles (loaded via _load_semantic_metadata), which provides
        full context including keigo_switch, relationships, and speech patterns.
        
        This simple name dict is NO LONGER injected into prompts but is still loaded
        for continuity pack operations.
        """
        try:
            # Try language-specific metadata file first (preferred)
            metadata_lang_path = self.work_dir / f"metadata_{self.target_language}.json"
            if metadata_lang_path.exists():
                with open(metadata_lang_path, 'r', encoding='utf-8') as f:
                    metadata_lang = json.load(f)
                    if isinstance(metadata_lang, dict):
                        return metadata_lang.get('character_names', {})
            
            # Fallback to metadata_en for backward compatibility
            metadata_en_path = self.work_dir / "metadata_en.json"
            if metadata_en_path.exists():
                with open(metadata_en_path, 'r', encoding='utf-8') as f:
                    metadata_en = json.load(f)
                    if isinstance(metadata_en, dict):
                        return metadata_en.get('character_names', {})
            
            # Fallback to manifest.json
            if self.manifest:
                metadata_key = f'metadata_{self.target_language}'
                metadata_lang = self.manifest.get(metadata_key, {})
                if isinstance(metadata_lang, dict) and metadata_lang:
                    return metadata_lang.get('character_names', {})
                # Last resort: metadata_en from manifest
                metadata_en = self.manifest.get('metadata_en', {})
                if not isinstance(metadata_en, dict):
                    return {}
                return metadata_en.get('character_names', {})
            
            return {}
            
        except Exception as e:
            logger.warning(f"Failed to load character names: {e}")
            return {}
    
    def _load_semantic_metadata(self) -> Dict:
        """
        Load full semantic metadata from language-specific metadata file.
        
        Supports both Enhanced v2.1 schema AND legacy V2 schema (backward compatible).
        
        Enhanced v2.1 schema fields:
        - characters: Full profiles with pronouns/relationships
        - dialogue_patterns: Speech fingerprints per character
        - scene_contexts: Location-based formality guidance
        - emotional_pronoun_shifts: State machines for dynamic pronouns
        - translation_guidelines: Priority system and quality markers
        
        Legacy V2 schema fields (auto-transformed):
        - character_profiles → characters
        - localization_notes → translation_guidelines
        - character_profiles.{name}.speech_pattern → dialogue_patterns
        
        Returns:
            Dictionary containing semantic metadata or empty dict if not found
        """
        try:
            # Load from metadata_{language}.json (preferred)
            metadata_lang_path = self.work_dir / f"metadata_{self.target_language}.json"
            if metadata_lang_path.exists():
                with open(metadata_lang_path, 'r', encoding='utf-8') as f:
                    full_metadata = json.load(f)
                    semantic_data = self._extract_semantic_metadata(full_metadata if isinstance(full_metadata, dict) else {})
                    
                    if semantic_data:
                        schema_type = "Enhanced v2.1" if 'characters' in full_metadata else "Legacy V2 (transformed)"
                        logger.info(f"✓ Loaded semantic metadata ({schema_type}) from {metadata_lang_path.name}")
                        return semantic_data
                    else:
                        logger.debug("No semantic metadata found in metadata file")
            
            # Fallback to manifest.json
            if self.manifest:
                metadata_key = f'metadata_{self.target_language}'
                metadata_lang = self.manifest.get(metadata_key, {})
                
                if isinstance(metadata_lang, dict) and metadata_lang:
                    semantic_data = self._extract_semantic_metadata(metadata_lang)
                    
                    if semantic_data:
                        schema_type = "Enhanced v2.1" if 'characters' in metadata_lang else "Legacy V2 (transformed)"
                        logger.info(f"✓ Loaded semantic metadata ({schema_type}) from manifest.json")
                        return semantic_data
            
            return {}
            
        except Exception as e:
            logger.warning(f"Failed to load semantic metadata: {e}")
            return {}
    
    def _extract_semantic_metadata(self, full_metadata: Dict) -> Dict:
        """
        Extract semantic metadata from any of the three schema variants:
        
        1. Enhanced v2.1 schema (preferred): characters, dialogue_patterns, scene_contexts...
        2. Legacy V2 schema: character_profiles, localization_notes
        3. V4 nested schema: character_names with nested objects containing relationships/traits
        
        Handles all schema versions with automatic transformation.
        """
        if not isinstance(full_metadata, dict):
            return {}

        semantic_data = {}
        
        # ===== ENHANCED V2.1 SCHEMA (preferred) =====
        if 'characters' in full_metadata:
            semantic_data['characters'] = full_metadata['characters']
        if 'dialogue_patterns' in full_metadata:
            semantic_data['dialogue_patterns'] = full_metadata['dialogue_patterns']
        if 'scene_contexts' in full_metadata:
            semantic_data['scene_contexts'] = full_metadata['scene_contexts']
        if 'emotional_pronoun_shifts' in full_metadata:
            semantic_data['emotional_pronoun_shifts'] = full_metadata['emotional_pronoun_shifts']
        if 'translation_guidelines' in full_metadata:
            semantic_data['translation_guidelines'] = full_metadata['translation_guidelines']
        
        # ===== LEGACY V2 SCHEMA (backward compatibility) =====
        # Transform character_profiles → characters (if not already present)
        if 'character_profiles' in full_metadata and 'characters' not in semantic_data:
            transformed_characters = self._transform_character_profiles(full_metadata['character_profiles'])
            if transformed_characters:
                semantic_data['characters'] = transformed_characters
                logger.debug(f"  → Transformed {len(transformed_characters)} character_profiles to characters format")
        
        # Transform localization_notes → translation_guidelines (if not already present)
        if 'localization_notes' in full_metadata and 'translation_guidelines' not in semantic_data:
            transformed_guidelines = self._transform_localization_notes(full_metadata['localization_notes'])
            if transformed_guidelines:
                semantic_data['translation_guidelines'] = transformed_guidelines
                logger.debug(f"  → Transformed localization_notes to translation_guidelines format")
        
        # Extract dialogue_patterns from character_profiles speech_pattern (if not already present)
        if 'character_profiles' in full_metadata and 'dialogue_patterns' not in semantic_data:
            dialogue_patterns = self._extract_dialogue_patterns(full_metadata['character_profiles'])
            if dialogue_patterns:
                semantic_data['dialogue_patterns'] = dialogue_patterns
                logger.debug(f"  → Extracted {len(dialogue_patterns)} dialogue_patterns from character_profiles")
        
        # V4 NESTED SCHEMA REMOVED (Phase 0) — no volume uses this format.
        # character_names with dict values is not generated by any code path.
        
        return semantic_data
    
    # _transform_v4_character_names REMOVED (Phase 0) — dead code, no volume uses V4 nested schema.
    
    def _transform_character_profiles(self, profiles: Dict) -> List[Dict]:
        """
        Transform legacy character_profiles dict to Enhanced v2.1 characters list.
        
        Legacy V2: {"ティグル＝ヴォルン": {"full_name": "Tigrevurmud Vorn", "pronouns": "he/him", ...}}
        Enhanced v2.1: [{"name_kanji": "ティグル＝ヴォルン", "name_en": "Tigrevurmud Vorn", ...}]
        
        PHASE 0 FIX: Preserves ALL rich fields (RTAS, keigo, contraction, nickname,
        how_character_refers_to_others) that were previously dropped.
        Also fixes the name_en/name_kanji swap — dict key is JP, full_name is EN.
        """
        characters = []
        if not isinstance(profiles, dict):
            return characters

        for jp_name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue

            pronouns_raw = profile.get('pronouns', '')
            if not isinstance(pronouns_raw, str):
                pronouns_raw = str(pronouns_raw)

            char = {
                # FIX: dict key IS the JP name, full_name is the EN name
                'name_kanji': jp_name,
                'name_en': profile.get('full_name', jp_name),
                'nickname': profile.get('nickname', ''),
                'role': profile.get('relationship_to_protagonist', 'supporting'),
                'gender': 'female' if 'she/her' in pronouns_raw else 'male' if 'he/him' in pronouns_raw else 'unknown',
                'age': profile.get('age', 'unknown'),
                'origin': profile.get('origin', ''),
            }
            
            # Parse pronouns string to dict
            if pronouns_raw:
                if 'she/her' in pronouns_raw.lower():
                    char['pronouns'] = {'subject': 'she', 'object': 'her', 'possessive': 'her'}
                elif 'he/him' in pronouns_raw.lower():
                    char['pronouns'] = {'subject': 'he', 'object': 'him', 'possessive': 'his'}
            
            # === RTAS Relationships (PREVIOUSLY DROPPED) ===
            rtas = profile.get('rtas_relationships', [])
            if rtas and isinstance(rtas, list):
                char['relationships'] = {}
                for rel in rtas:
                    if isinstance(rel, dict):
                        target = rel.get('target', '')
                        if target:
                            char['relationships'][target] = {
                                'type': rel.get('relationship_type', ''),
                                'rtas_score': rel.get('rtas_score', 0),
                                'contraction_rate': rel.get('contraction_rate_override', None),
                                'notes': rel.get('notes', '')
                            }
            elif 'relationship_to_others' in profile:
                char['relationships'] = {'context': profile['relationship_to_others']}
            
            # === Keigo Switch (PREVIOUSLY DROPPED) ===
            keigo = profile.get('keigo_switch', {})
            if keigo and isinstance(keigo, dict):
                char['keigo_switch'] = keigo
            
            # === Contraction Rate (PREVIOUSLY DROPPED) ===
            contraction = profile.get('contraction_rate', {})
            if contraction and isinstance(contraction, dict):
                char['contraction_rate'] = contraction
            
            # === How Character Refers To Others (PREVIOUSLY DROPPED) ===
            refers = profile.get('how_character_refers_to_others', {})
            if refers and isinstance(refers, dict):
                char['how_refers_to_others'] = refers
            
            # Preserve key traits as notes
            notes = []
            if 'personality_traits' in profile:
                traits = profile['personality_traits']
                if isinstance(traits, list):
                    notes.append(f"Personality: {', '.join(str(t) for t in traits)}")
                else:
                    notes.append(f"Personality: {traits}")
            if 'key_traits' in profile:
                notes.append(f"Key traits: {profile['key_traits']}")
            if 'appearance' in profile:
                notes.append(f"Appearance: {profile['appearance']}")
            if notes:
                char['notes'] = ' | '.join(notes)
            
            # Preserve character arc info
            for key in profile:
                if key.startswith('character_arc'):
                    char['character_arc'] = profile[key]
                    break
            
            characters.append(char)
        
        return characters
    
    def _transform_localization_notes(self, notes: Dict) -> Dict:
        """
        Transform legacy localization_notes to Enhanced v2.1 translation_guidelines.
        """
        guidelines = {}
        if not isinstance(notes, dict):
            return guidelines
        
        # British speech exception → character_exceptions
        if 'british_speech_exception' in notes:
            bse = notes['british_speech_exception']
            if isinstance(bse, dict):
                guidelines['character_exceptions'] = {
                    bse.get('character', 'Unknown'): {
                        'allowed_patterns': bse.get('allowed_patterns', []),
                        'rationale': bse.get('rationale', ''),
                        'examples': bse.get('examples', [])
                    }
                }
        
        # All other characters → forbidden_patterns & target_metrics
        if 'all_other_characters' in notes:
            aoc = notes['all_other_characters']
            if isinstance(aoc, dict):
                guidelines['forbidden_patterns'] = aoc.get('forbidden_patterns', [])
                guidelines['preferred_alternatives'] = aoc.get('preferred_alternatives', {})
                guidelines['target_metrics'] = aoc.get('target_metrics', {})
                guidelines['narrator_voice'] = aoc.get('narrator_voice', '')
        
        # Name order → naming_conventions
        if 'name_order' in notes:
            guidelines['naming_conventions'] = notes['name_order']
        
        # Dialogue guidelines → dialogue_rules
        if 'dialogue_guidelines' in notes:
            guidelines['dialogue_rules'] = notes['dialogue_guidelines']
        
        # Volume-specific notes → volume_context
        for key in notes:
            if 'volume' in key.lower() and 'specific' in key.lower():
                guidelines['volume_context'] = notes[key]
                break
        
        return guidelines
    
    def _extract_dialogue_patterns(self, profiles: Dict) -> Dict:
        """
        Extract dialogue_patterns from character_profiles.
        
        Phase 0 rewrite: Derives tone_shifts from keigo_switch data instead of
        using hardcoded phrase lists. The keigo_switch.speaking_to map directly
        tells us how a character's register shifts per conversation partner.
        """
        patterns = {}
        if not isinstance(profiles, dict):
            return patterns

        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue

            speech_pattern = profile.get('speech_pattern')
            if not (isinstance(speech_pattern, str) and speech_pattern):
                continue
            
            pattern_entry = {
                'speech_style': speech_pattern,
                'tone_shifts': {}
            }
            
            # Derive tone_shifts from keigo_switch (real data, not guesses)
            keigo = profile.get('keigo_switch', {})
            if isinstance(keigo, dict):
                speaking_to = keigo.get('speaking_to', {})
                if isinstance(speaking_to, dict):
                    for target, register in speaking_to.items():
                        pattern_entry['tone_shifts'][target] = register
                # Add narration/thought register
                narration = keigo.get('narration', '')
                if narration:
                    pattern_entry['tone_shifts']['[narration]'] = narration
                thoughts = keigo.get('internal_thoughts', '')
                if thoughts:
                    pattern_entry['tone_shifts']['[internal_thoughts]'] = thoughts
            
            # Contraction rate as speech metric
            contraction = profile.get('contraction_rate', {})
            if isinstance(contraction, dict):
                baseline = contraction.get('baseline')
                if baseline is not None:
                    pattern_entry['contraction_baseline'] = baseline
            
            patterns[name] = pattern_entry
        
        return patterns

    def _load_manifest(self) -> Dict:
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_manifest(self):
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

    def _load_log(self) -> Dict:
        if self.log_path.exists():
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"chapters": []}
        return {"chapters": []}

    def _save_log(self):
        with open(self.log_path, 'w', encoding='utf-8') as f:
            json.dump(self.translation_log, f, indent=2, ensure_ascii=False)

    def _canonical_title_from_chapter_id(self, chapter_id: str) -> Optional[str]:
        """Derive stable title from chapter_id (chapter_01 -> Chapter 1)."""
        match = self._CHAPTER_ID_PATTERN.search(str(chapter_id or ""))
        if not match:
            return None
        try:
            number = int(match.group(1))
        except Exception:
            return None
        return f"Chapter {number}"

    def _extract_english_chapter_number(self, title: str) -> Optional[int]:
        """Extract Arabic chapter number from EN-style titles like 'Chapter 4 (Part 1)'."""
        if not title:
            return None
        match = self._EN_CHAPTER_NUM_PATTERN.search(title)
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    def _resolve_prompt_titles(self, chapters: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        """
        Resolve chapter titles for prompt/output usage.

        Ambiguous generic titles (duplicates, mismatched chapter numbers) are normalized to
        canonical titles derived from chapter_id.
        """
        title_key = f"title_{self.target_language}"
        raw_by_id: Dict[str, Optional[str]] = {}
        normalized_counter: Dict[str, int] = {}

        for chapter in chapters:
            chapter_id = chapter.get("id", "")
            raw = chapter.get(title_key) or chapter.get("title_en")
            raw = raw.strip() if isinstance(raw, str) else None
            raw_by_id[chapter_id] = raw
            if raw:
                norm = re.sub(r"\s+", " ", raw).strip().lower()
                normalized_counter[norm] = normalized_counter.get(norm, 0) + 1

        resolved: Dict[str, Optional[str]] = {}
        for chapter in chapters:
            chapter_id = chapter.get("id", "")
            raw = raw_by_id.get(chapter_id)
            canonical = self._canonical_title_from_chapter_id(chapter_id)

            if not raw:
                resolved[chapter_id] = canonical
                continue

            norm = re.sub(r"\s+", " ", raw).strip().lower()
            duplicate = normalized_counter.get(norm, 0) > 1
            title_num = self._extract_english_chapter_number(raw)
            canonical_num = self._extract_english_chapter_number(canonical or "")
            mismatch = (
                title_num is not None
                and canonical_num is not None
                and title_num != canonical_num
            )

            if canonical and (duplicate or mismatch):
                reason = "duplicate title" if duplicate else "title/chapter_id mismatch"
                logger.warning(
                    f"[TITLE] Normalizing ambiguous title for {chapter_id}: "
                    f"'{raw}' -> '{canonical}' ({reason})"
                )
                resolved[chapter_id] = canonical
            else:
                resolved[chapter_id] = raw

        return resolved
    
    def _prewarm_cache(self):
        """Pre-warm context cache with system instruction before translation starts."""
        try:
            # Build system instruction (same as what translation will use)
            system_instruction = self.prompt_loader.build_system_instruction()
            
            # Get target model
            model_name = get_model_name()
            
            # Create cache
            success = self.client.warm_cache(system_instruction, model_name)
            
            if success:
                logger.info("✓ Cache pre-warmed successfully. All chapters will use cached context.")
            else:
                logger.warning("Cache pre-warming failed. First chapter will create cache.")
                
        except Exception as e:
            logger.warning(f"Cache pre-warming error: {e}. Will create cache during first chapter.")

    def _create_volume_cache(
        self,
        chapter_configs: List[Dict[str, Any]],
        model_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create one Gemini cache containing full JP volume text + system instruction.

        This cache is shared across all chapter translations in the run.
        """
        if not self.client.enable_caching:
            return None
        if not self.volume_cache_enabled:
            logger.info("Volume-level cache disabled by translation.massive_chapter.enable_volume_cache")
            return None

        chapter_blocks: List[str] = []
        cached_chapter_ids: List[str] = []
        missing_chapter_ids: List[str] = []
        total_target_chapters = len(chapter_configs)
        missing_files = 0

        for chapter in chapter_configs:
            chapter_id = chapter.get("id", "unknown")
            jp_file = chapter.get("jp_file") or chapter.get("source_file")
            if not jp_file:
                missing_chapter_ids.append(chapter_id)
                continue

            source_path = self.work_dir / "JP" / jp_file
            if not source_path.exists():
                missing_files += 1
                missing_chapter_ids.append(chapter_id)
                continue

            try:
                jp_text = source_path.read_text(encoding="utf-8")
                canonical_title = self._canonical_title_from_chapter_id(chapter_id) or chapter_id
                chapter_blocks.append(
                    f"<CHAPTER id='{chapter_id}' canonical_title='{canonical_title}' source_file='{jp_file}'>\n"
                    f"<!-- TARGET_CHAPTER: {chapter_id} | {canonical_title} -->\n"
                    f"{jp_text}\n"
                    f"</CHAPTER>"
                )
                cached_chapter_ids.append(chapter_id)
            except Exception as e:
                missing_chapter_ids.append(chapter_id)
                logger.warning(f"Failed reading JP source for cache ({chapter_id}): {e}")

        if not chapter_blocks:
            logger.warning("Volume cache skipped: no JP chapter text available")
            return None

        full_volume_text = "\n\n---\n\n".join(chapter_blocks)
        system_instruction = self.prompt_loader.build_system_instruction()

        try:
            target_model = model_name or get_model_name()
            cache_name = self.client.create_cache(
                model=target_model,
                system_instruction=system_instruction,
                contents=[full_volume_text],
                ttl_seconds=self.volume_cache_ttl_seconds,
                display_name=f"{self.manifest.get('volume_id', self.work_dir.name)}_full",
            )
            if cache_name:
                self._volume_cache_stats = {
                    "target_chapters": total_target_chapters,
                    "cached_chapters": len(cached_chapter_ids),
                    "missing_files": missing_files,
                    "missing_chapter_ids": missing_chapter_ids,
                    "cached_chapter_ids": cached_chapter_ids,
                    "volume_chars": len(full_volume_text),
                }
                logger.info(
                    f"[CACHE] Created volume cache {cache_name} "
                    f"({len(chapter_blocks)} chapters, {len(full_volume_text)} chars, "
                    f"missing={missing_files})"
                )
                logger.info(
                    f"[CACHE] Source coverage verification: "
                    f"{len(cached_chapter_ids)}/{total_target_chapters} chapters packaged"
                )
                if missing_chapter_ids:
                    logger.warning(
                        f"[CACHE] Chapters missing from cache payload: "
                        f"{', '.join(missing_chapter_ids[:10])}"
                    )
                return cache_name
        except Exception as e:
            logger.warning(f"Failed to create volume-level cache: {e}")

        return None

    def translate_volume(self, clean_start: bool = False, chapters: List[str] = None):
        """
        Run translation for the volume.
        """
        logger.info(f"Starting translation for volume in {self.work_dir}")
        
        # ===== PRE-FLIGHT VALIDATION: v3.6 Manifest Check =====
        schema_version = self.manifest.get("schema_version", "unknown")
        if schema_version == "v3.6_enhanced":
            logger.info("Detected v3.6 enhanced schema - running manifest validator...")
            validator_script = Path(__file__).parent.parent.parent / "scripts" / "validate_manifest_v3_6.py"
            manifest_path = self.work_dir / "manifest.json"
            
            if validator_script.exists():
                import subprocess
                result = subprocess.run(
                    ["python3", str(validator_script), str(manifest_path)],
                    capture_output=True,
                    text=True
                )
                
                # Print validator output
                print(result.stdout)
                
                if result.returncode != 0:
                    logger.warning(
                        "Manifest validation found issues. "
                        "Translation can proceed but quality may be affected."
                    )
                    response = input("Continue anyway? (y/N): ")
                    if response.lower() != 'y':
                        logger.info("Translation cancelled by user.")
                        return
                else:
                    logger.info("✓ Manifest validation passed - ready for quality translation")
            else:
                logger.warning(f"Validator script not found at {validator_script}")
        
        # Check prerequisite
        librarian_status = self.manifest.get("pipeline_state", {}).get("librarian", {}).get("status")
        if librarian_status != "completed":
            logger.warning(f"Librarian phase not marked as completed (status: {librarian_status})")
            # Proceed with warning? Or stop? Let's stop to be safe unless forced (not imp yet)
            # For now, just warn.
        
        # Support both v2 (chapters at root) and v3.5 (chapters under structure)
        manifest_chapters = self.manifest.get("chapters", [])
        if not manifest_chapters:
            manifest_chapters = self.manifest.get("structure", {}).get("chapters", [])
        
        if not manifest_chapters:
            logger.error("No chapters found in manifest (checked both root and structure.chapters)")
            return

        # Filter chapters if specific list provided
        target_chapters = manifest_chapters
        if chapters:
            target_chapters = [c for c in manifest_chapters if c["id"] in chapters]
            
        total = len(target_chapters)
        logger.info(f"Targeting {total} chapters")
        resolved_titles = self._resolve_prompt_titles(target_chapters)

        # Update pipeline state
        if "translator" not in self.manifest["pipeline_state"]:
            self.manifest["pipeline_state"]["translator"] = {}
        self.manifest["pipeline_state"]["translator"]["status"] = "in_progress"
        self.manifest["pipeline_state"]["translator"]["target_language"] = self.target_language
        self.manifest["pipeline_state"]["translator"]["started_at"] = datetime.now().isoformat()
        self._save_manifest()

        # Create single full-volume cache for this run (fallback to internal prewarm)
        if self.client.enable_caching:
            self.volume_cache_name = self._create_volume_cache(target_chapters, model_name=get_model_name())
            if self.volume_cache_name:
                logger.info(f"[CACHE] Volume cache ready for run: {self.volume_cache_name}")
                if self._volume_cache_stats:
                    logger.info(
                        f"[CACHE] Run verification: "
                        f"cached {self._volume_cache_stats.get('cached_chapters', 0)}/"
                        f"{self._volume_cache_stats.get('target_chapters', 0)} chapter sources"
                    )
                logger.info(
                    "[CACHE VERIFY] Full-LN JP corpus + system instruction are bundled "
                    "in the active external cache for chapter translation."
                )
            else:
                logger.info("Pre-warming context cache (volume cache unavailable)...")
                self._prewarm_cache()
                logger.info(
                    "[CACHE VERIFY] Falling back to prompt-only internal cache "
                    "(no full-LN external cache)."
                )
        
        success_count = 0
        
        # Language-specific output directory (e.g., EN/, VN/)
        output_dir_name = self.target_language.upper()
        output_dir = self.work_dir / output_dir_name
        output_dir.mkdir(exist_ok=True)

        for i, chapter in enumerate(target_chapters):
            chapter_id = chapter["id"]
            # File names from manifest
            jp_file = chapter.get("jp_file") or chapter.get("source_file")
            # Usually Librarian outputs simple filenames, assume paths relative to JP/ and output dir

            if not jp_file:
                logger.error(f"Chapter {chapter_id} missing source filename config")
                continue

            source_path = self.work_dir / "JP" / jp_file

            # Target file: Use manifest's translated_file or language-specific file
            # Fallback: add language suffix to source filename if not specified
            translated_filename = (
                chapter.get(f"{self.target_language}_file") or 
                chapter.get("translated_file") or
                jp_file.replace('.md', f'_{self.target_language.upper()}.md')
            )
            output_path = output_dir / translated_filename

            # Check if already done (unless clean_start)
            if not clean_start and chapter.get("translation_status") == "completed":
                # Check if file actually exists
                if output_path.exists():
                    logger.info(f"Skipping completed chapter {chapter_id}")
                    success_count += 1
                    continue

            # Get translated title from manifest (language-specific or fallback to EN)
            title_key = f"title_{self.target_language}"
            translated_title = resolved_titles.get(chapter_id)

            logger.info(f"Translating [{i+1}/{total}] {chapter_id} to {self.language_name}...")

            # Check for model override in chapter metadata
            chapter_model = chapter.get("model")
            if chapter_model:
                logger.info(f"     [OVERRIDE] Using model: {chapter_model}")
            
            # Select cache for this chapter:
            # 1) Volume-level full JP cache (preferred for massive LNs)
            # 2) Continuity schema cache (legacy fallback)
            cached_content_name = self.volume_cache_name
            if self.enable_continuity and i > 0 and not cached_content_name:  # Not first chapter
                try:
                    cached_content_name = self.per_chapter_workflow.get_cache_for_chapter(i + 1)
                    if cached_content_name:
                        logger.info(f"     [CONTINUITY] Using cached schema from Chapter {i}")
                except Exception as e:
                    logger.warning(f"Could not load cached schema: {e}")
            # === END CACHE CHECK ===

            effective_cache_name = cached_content_name
            default_model = get_model_name()
            if chapter_model and chapter_model != default_model and cached_content_name:
                logger.info(
                    f"     [CACHE] Skipping cache for model override "
                    f"({chapter_model} != {default_model})"
                )
                effective_cache_name = None

            if i == 0:
                if self.volume_cache_name and effective_cache_name:
                    logger.info(
                        "[CACHE VERIFY] Chapter translation will use external full-LN cache "
                        "with embedded prompt instructions."
                    )
                elif effective_cache_name:
                    logger.info("[CACHE VERIFY] Chapter translation will use cached prompt context.")
                else:
                    logger.warning("[CACHE VERIFY] Chapter translation running without cache.")

            result = self.processor.translate_chapter(
                source_path,
                output_path,
                chapter_id,
                en_title=translated_title,  # en_title param kept for backward compatibility
                model_name=chapter_model,
                cached_content=effective_cache_name,
                volume_cache=effective_cache_name if self.volume_cache_name else None,
            )

            # Fallback to configured fallback model on failure (safety blocks, rate limits, etc)
            if not result.success and not chapter_model:
                fallback_model = get_fallback_model_name()
                logger.warning(f"Translation failed, retrying with fallback model ({fallback_model})...")

                # Clear cache since we're switching models (cache is model-specific)
                if self.client.enable_caching:
                    logger.info("Clearing cache before switching to fallback model...")
                    self.client.clear_cache()

                result = self.processor.translate_chapter(
                    source_path,
                    output_path,
                    chapter_id,
                    en_title=translated_title,
                    model_name=fallback_model,
                    cached_content=None,
                    volume_cache=None,
                )
                if result.success:
                    logger.info(f"     [FALLBACK] Successfully translated with {fallback_model}")
                    # Save fallback model to manifest for tracking
                    chapter["model"] = fallback_model
            
            # Update Log
            log_entry = {
                "chapter_id": chapter_id,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "success": result.success,
                "error": result.error,
                "quality": result.audit_result.to_dict() if result.audit_result else None
            }
            
            # Remove old entry if exists
            self.translation_log["chapters"] = [c for c in self.translation_log["chapters"] if c["chapter_id"] != chapter_id]
            self.translation_log["chapters"].append(log_entry)
            self._save_log()

            if result.success:
                chapter["translation_status"] = "completed"
                # Use language-specific key (e.g., "vn_file" or "en_file")
                file_key = f"{self.target_language}_file"
                # Store the actual output filename (not the fallback variable)
                chapter[file_key] = output_path.name  # e.g., "CHAPTER_01_EN.md"
                
                # === PER-CHAPTER WORKFLOW: Extract schema, review, cache ===
                if self.enable_continuity:
                    logger.info(f"\n{'─'*60}")
                    logger.info(f"  Starting per-chapter schema workflow...")
                    logger.info(f"{'─'*60}\n")
                    
                    try:
                        # Read the translated chapter
                        with open(output_path, 'r', encoding='utf-8') as f:
                            translation_text = f.read()
                        
                        # Process chapter (extract, review, cache)
                        workflow_success, cache_name = self.per_chapter_workflow.process_chapter(
                            chapter_num=i + 1,  # 1-indexed chapter number
                            chapter_id=chapter_id,
                            translation_text=translation_text,
                            skip_review=False  # User review required
                        )
                        
                        if not workflow_success:
                            logger.warning("Per-chapter workflow failed or was cancelled by user")
                            # User cancelled - should we stop the pipeline?
                            if input("\nContinue to next chapter anyway? (y/N): ").strip().lower() != 'y':
                                logger.info("Pipeline stopped by user")
                                break
                        
                        # Store cache info in chapter metadata
                        if cache_name:
                            chapter["schema_cache"] = cache_name
                        
                    except Exception as e:
                        logger.error(f"Per-chapter workflow error: {e}")
                        logger.warning("Continuing without schema extraction...")
                else:
                    logger.info(f"\n{'─'*60}")
                    logger.info(f"  [CONTINUITY DISABLED] Skipping schema extraction")
                    logger.info(f"{'─'*60}\n")
                
                # === END PER-CHAPTER WORKFLOW ===
                
                # Add context summaries context_manager handles internally?
                # Actually context_manager needs explicit add. 
                # Since we don't extract summary from LLM output yet, we might generate a dummy or simple one.
                # For now, just logging completion.
                self.context_manager.add_chapter_context(chapter_id, "Translated", {}) 
                
                success_count += 1
                if result.warnings:
                    logger.warning(
                        f"{chapter_id} completed with {len(result.warnings)} warning(s): "
                        f"{'; '.join(result.warnings[:3])}"
                    )
                logger.info(f"Completed {chapter_id}. Audit passed: {result.audit_result.passed if result.audit_result else 'N/A'}")
            else:
                chapter["translation_status"] = "failed"
                logger.error(f"Failed {chapter_id}: {result.error}")
            
            # Update manifest checkpoint
            self._save_manifest()

            # Rate limiting delay for TPM management
            # With context caching, TPM usage is reduced by 87%, so only need short delay
            if i < total - 1:
                delay = 5 if self.client.enable_caching else 60
                logger.info(f"Waiting {delay} seconds before next chapter (TPM management)...")
                time.sleep(delay)

        # Final Status
        if success_count == total:
            self.manifest["pipeline_state"]["translator"]["status"] = "completed"
            logger.info("Volume translation COMPLETED")
            logger.info("Post-processing stages are disabled (Gemini's native quality is excellent).")
            logger.info("Only CJK validator remains active (Vietnamese translations only).")
            logger.info("Grammar validator REMOVED (inverted logic damaged 1a60 output).")
            logger.info("Anti-AI-ism agent DISABLED (over-correction damages natural prose).")
            
            # Finalize continuity pack (aggregate all chapter snapshots)
            logger.info("\nFinalizing continuity pack...")
            try:
                pack_summary = self.per_chapter_workflow.finalize()
                logger.info(f"✓ Continuity pack finalized with {len(pack_summary.get('chapter_snapshots', []))} snapshots")
            except Exception as e:
                logger.error(f"Failed to finalize continuity pack: {e}")
            
            # Save continuity pack for future volumes (old system for backward compat)
            logger.info("Saving legacy continuity pack format...")
            try:
                continuity_manager = ContinuityPackManager(self.work_dir)
                pack = continuity_manager.extract_continuity_from_volume(self.work_dir, self.manifest, target_language=self.target_language)
                continuity_manager.save_continuity_pack(pack)
                logger.info(f"✓ Continuity pack saved ({len(pack.roster)} names, {len(pack.glossary)} terms)")
            except Exception as e:
                logger.warning(f"Failed to save continuity pack: {e}")
        else:
            self.manifest["pipeline_state"]["translator"]["status"] = "partial"
            logger.warning(f"Volume translation PARTIAL ({success_count}/{total} completed)")

        self._save_manifest()

        # Clean up context cache
        if self.client.enable_caching:
            if self.volume_cache_name:
                logger.info(f"Clearing volume cache: {self.volume_cache_name}...")
                self.client.delete_cache(self.volume_cache_name)
                self.volume_cache_name = None
            logger.info("Clearing context cache...")
            self.client.clear_cache()
    
    def generate_report(self) -> TranslationReport:
        """Generate a summary report of the translation."""
        log_chapters = self.translation_log.get("chapters", [])

        total_input = sum(c.get("input_tokens", 0) for c in log_chapters)
        total_output = sum(c.get("output_tokens", 0) for c in log_chapters)

        quality_scores = []
        for c in log_chapters:
            if c.get("quality") and c["quality"].get("overall_score"):
                quality_scores.append(c["quality"]["overall_score"])

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        completed = sum(1 for c in log_chapters if c.get("success"))
        failed = sum(1 for c in log_chapters if not c.get("success"))
        errors = [c.get("error") for c in log_chapters if c.get("error")]

        status = self.manifest.get("pipeline_state", {}).get("translator", {}).get("status", "unknown")

        return TranslationReport(
            volume_id=self.manifest.get("volume_id", "unknown"),
            chapters_total=len(log_chapters),
            chapters_completed=completed,
            chapters_failed=failed,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            average_quality_score=avg_quality,
            status=status,
            started_at=self.manifest.get("pipeline_state", {}).get("translator", {}).get("started_at", ""),
            completed_at=datetime.now().isoformat(),
            errors=errors
        )


def run_translator(
    volume_id: str,
    chapters: Optional[List[str]] = None,
    force: bool = False,
    work_base: Optional[Path] = None,
    enable_continuity: bool = False,
    enable_multimodal: bool = False
) -> TranslationReport:
    """
    Main entry point for Translator agent.

    Args:
        volume_id: Volume identifier (directory name in WORK/).
        chapters: Specific chapter IDs to translate (None = all).
        force: Force re-translation of completed chapters.
        work_base: Base working directory (defaults to WORK/).
        enable_continuity: Enable schema extraction and continuity features (ALPHA - unstable).
        enable_multimodal: Enable multimodal visual context injection.

    Returns:
        TranslationReport with results.
    """
    from pipeline.config import WORK_DIR

    work_base = work_base or WORK_DIR
    volume_dir = work_base / volume_id

    if not volume_dir.exists():
        raise FileNotFoundError(f"Volume directory not found: {volume_dir}")

    agent = TranslatorAgent(volume_dir, enable_continuity=enable_continuity, enable_multimodal=enable_multimodal)
    agent.translate_volume(clean_start=force, chapters=chapters)
    return agent.generate_report()


def main():
    parser = argparse.ArgumentParser(description="Run Translator Agent")
    parser.add_argument("--volume", type=str, required=True, help="Volume ID (directory name in WORK)")
    parser.add_argument("--chapters", nargs="+", help="Specific chapter IDs to translate")
    parser.add_argument("--force", action="store_true", help="Force re-translation of completed chapters")
    parser.add_argument("--enable-continuity", action="store_true", 
                       help="[ALPHA] Enable schema extraction and continuity (experimental, unstable)")
    parser.add_argument("--enable-gap-analysis", action="store_true",
                       help="Enable semantic gap analysis (Week 2-3 integration) for improved translation quality")
    parser.add_argument("--enable-multimodal", action="store_true",
                       help="Enable multimodal visual context injection (requires Phase 1.6)")

    args = parser.parse_args()
    
    # Locate work dir
    # Assuming run from pipeline root
    config = get_translation_config()
    # Or get global directories config... relying on config.py having implicit access
    # But usually we need the root path.
    # Hardcoding path relative to CWD for this CLI:
    root_work = Path("WORK") 
    volume_dir = root_work / args.volume
    
    if not volume_dir.exists():
        logger.error(f"Volume directory not found: {volume_dir}")
        sys.exit(1)
        
    try:
        agent = TranslatorAgent(volume_dir, enable_continuity=args.enable_continuity,
                               enable_gap_analysis=args.enable_gap_analysis,
                               enable_multimodal=args.enable_multimodal)
        agent.translate_volume(clean_start=args.force, chapters=args.chapters)
    except Exception as e:
        logger.exception("Translator Agent crashed")
        sys.exit(1)

if __name__ == "__main__":
    main()
