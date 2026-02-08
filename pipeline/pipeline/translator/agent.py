"""
Translator Agent Orchestrator.
Main entry point for Phase 2: Translation.
Supports multi-language configuration (EN, VN, etc.)
"""

import json
import logging
import argparse
import sys
import os
import time
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
from pipeline.config import get_target_language, get_language_config, PIPELINE_ROOT
from pipeline.post_processor.format_normalizer import FormatNormalizer
from modules.gap_integration import GapIntegrationEngine

try:
    from pipeline.post_processor.cjk_cleaner import CJKArtifactCleaner, format_results_report
    CJK_CLEANER_AVAILABLE = True
except ModuleNotFoundError:
    CJK_CLEANER_AVAILABLE = False

    class CJKArtifactCleaner:  # type: ignore[override]
        """No-op fallback when legacy CJK cleaner module is unavailable."""

        def __init__(self, *args, **kwargs):
            pass

        def clean_volume(self, work_dir: Path) -> Dict[str, Any]:
            return {
                "volume": work_dir.name,
                "languages_processed": 0,
                "total_files": 0,
                "total_artifacts": 0,
                "files_modified": 0,
                "language_results": {},
            }

    def format_results_report(_results: Dict[str, Any]) -> str:
        return "CJK artifact cleaner unavailable: skipped legacy CJK detection."


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

if not CJK_CLEANER_AVAILABLE:
    logger.warning("Legacy cjk_cleaner module not found; CJK artifact detection will be skipped.")

class TranslatorAgent:
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
        cache_ttl = caching_config.get("ttl_minutes", 60)

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

        # Load and inject character names from manifest (for cached system instruction)
        character_names = self._load_character_names()
        self.glossary_lock = GlossaryLock(work_dir, target_language=self.target_language)
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

        # Initialize Self-Healing Anti-AI-ism Agent (always enabled for EN/VN)
        if self.target_language in ['en', 'vn', 'vi']:
            try:
                from modules.anti_ai_ism_agent import AntiAIismAgent
                
                # Get API key from config (using already imported get_gemini_config)
                gemini_config = get_gemini_config()
                api_key = gemini_config.get('api_key', os.getenv('GEMINI_API_KEY'))
                
                # Get config directory from PIPELINE_ROOT
                config_dir = PIPELINE_ROOT / 'config'
                
                # Initialize agent with auto_heal=True for automatic corrections
                anti_ai_ism_agent = AntiAIismAgent(
                    config_dir=config_dir,
                    persist_directory=work_dir / "chroma_anti_ai_ism",
                    auto_heal=True,  # Enable automatic corrections
                    dry_run=False,
                    target_language=self.target_language,
                    gemini_api_key=api_key,
                    use_vector=True  # Enable Layer 2 (vector Bad Prose DB)
                )
                
                # Enable anti-AI-ism in processor
                self.processor.enable_anti_ai_ism = True
                self.processor._anti_ai_ism_agent = anti_ai_ism_agent
                logger.info("✓ Self-Healing Anti-AI-ism Agent initialized and connected to processor")
                logger.info("  3-layer detection + auto-correction enabled (runs after CJK cleaning)")
            except Exception as e:
                logger.warning(f"Failed to initialize anti-AI-ism agent: {e}")
                logger.warning("Continuing without self-healing (run 'mtl.py heal' manually after translation)")
                self.processor.enable_anti_ai_ism = False
                self.processor._anti_ai_ism_agent = None

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
                    return metadata_lang.get('character_names', {})
            
            # Fallback to metadata_en for backward compatibility
            metadata_en_path = self.work_dir / "metadata_en.json"
            if metadata_en_path.exists():
                with open(metadata_en_path, 'r', encoding='utf-8') as f:
                    metadata_en = json.load(f)
                    return metadata_en.get('character_names', {})
            
            # Fallback to manifest.json
            if self.manifest:
                metadata_key = f'metadata_{self.target_language}'
                metadata_lang = self.manifest.get(metadata_key, {})
                if metadata_lang:
                    return metadata_lang.get('character_names', {})
                # Last resort: metadata_en from manifest
                metadata_en = self.manifest.get('metadata_en', {})
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
                    semantic_data = self._extract_semantic_metadata(full_metadata)
                    
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
                
                if metadata_lang:
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
        
        # ===== V4 NESTED SCHEMA (character_names with objects) =====
        # Check if character_names contains nested objects (not flat strings)
        if 'character_names' in full_metadata and 'characters' not in semantic_data:
            char_names = full_metadata['character_names']
            # Detect V4 schema: first value is dict, not string
            first_value = next(iter(char_names.values()), None) if char_names else None
            if isinstance(first_value, dict):
                transformed_v4 = self._transform_v4_character_names(char_names)
                if transformed_v4:
                    semantic_data['characters'] = transformed_v4
                    logger.debug(f"  → Transformed {len(transformed_v4)} V4 nested character_names to characters format")
        
        return semantic_data
    
    def _transform_v4_character_names(self, char_names: Dict) -> List[Dict]:
        """
        Transform V4 nested character_names to Enhanced v2.1 characters list.
        
        V4 schema: {"青柳明人《あおやぎあきひと》": {"name_en": "...", "relationships": {...}, "traits": [...]}}
        Enhanced v2.1: [{"name_en": "...", "name_kanji": "...", "pronouns": {...}, ...}]
        """
        characters = []
        for jp_key, char_data in char_names.items():
            if not isinstance(char_data, dict):
                continue  # Skip flat entries (legacy character_names)
            
            char = {
                'name_en': char_data.get('name_en', jp_key),
                'name_kanji': jp_key.split('《')[0] if '《' in jp_key else jp_key,
                'role': char_data.get('role', 'supporting'),
                'gender': char_data.get('gender', 'unknown'),
                'age': char_data.get('age', 'unknown'),
            }
            
            # Pronouns (already in dict format in V4)
            if 'pronouns' in char_data:
                char['pronouns'] = char_data['pronouns']
            
            # Relationships (already dict in V4)
            if 'relationships' in char_data:
                char['relationships'] = char_data['relationships']
            
            # Traits as notes
            if 'traits' in char_data:
                traits = char_data['traits']
                if isinstance(traits, list):
                    char['notes'] = f"Traits: {', '.join(traits)}"
            
            # Nicknames
            if 'nicknames' in char_data:
                char['nicknames'] = char_data['nicknames']
            
            # Nationality
            if 'nationality' in char_data:
                char['nationality'] = char_data['nationality']
            
            characters.append(char)
        
        return characters
    
    def _transform_character_profiles(self, profiles: Dict) -> List[Dict]:
        """
        Transform legacy character_profiles dict to Enhanced v2.1 characters list.
        
        Legacy V2: {"Charlotte Bennett": {"full_name": "...", "pronouns": "she/her", ...}}
        Enhanced v2.1: [{"name_en": "Charlotte Bennett", "pronouns": {"subject": "she"}, ...}]
        """
        characters = []
        for name, profile in profiles.items():
            char = {
                'name_en': name,
                'name_kanji': profile.get('full_name', name),
                'role': profile.get('relationship_to_protagonist', 'supporting'),
                'gender': 'female' if 'she/her' in profile.get('pronouns', '') else 'male' if 'he/him' in profile.get('pronouns', '') else 'unknown',
                'age': profile.get('age', 'unknown'),
            }
            
            # Parse pronouns string to dict
            pronouns_str = profile.get('pronouns', '')
            if pronouns_str:
                if 'she/her' in pronouns_str.lower():
                    char['pronouns'] = {'subject': 'she', 'object': 'her', 'possessive': 'her'}
                elif 'he/him' in pronouns_str.lower():
                    char['pronouns'] = {'subject': 'he', 'object': 'him', 'possessive': 'his'}
            
            # Map relationships
            if 'relationship_to_others' in profile:
                char['relationships'] = {'context': profile['relationship_to_others']}
            
            # Preserve key traits as notes
            notes = []
            if 'personality_traits' in profile:
                notes.append(f"Personality: {profile['personality_traits']}")
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
        
        # British speech exception → character_exceptions
        if 'british_speech_exception' in notes:
            bse = notes['british_speech_exception']
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
        Extract dialogue_patterns from character_profiles speech_pattern fields.
        
        Legacy V2: character_profiles.{name}.speech_pattern = "Formal British English..."
        Enhanced v2.1: dialogue_patterns.{name} = {"speech_style": "...", "common_phrases": [...]}
        """
        patterns = {}
        for name, profile in profiles.items():
            if 'speech_pattern' in profile:
                patterns[name] = {
                    'speech_style': profile['speech_pattern'],
                    'common_phrases': [],  # Will be populated from profile analysis
                    'tone_shifts': {}
                }
                
                # Extract common phrases from speech_pattern description
                speech = profile['speech_pattern'].lower()
                if 'i shall' in speech or 'quite' in speech:
                    patterns[name]['common_phrases'] = ['I shall', 'quite', 'rather', 'would you kindly']
                elif 'casual' in speech or 'slang' in speech:
                    patterns[name]['common_phrases'] = ['pretty', 'really', 'I mean', 'kinda']
                elif 'energetic' in speech or 'bro' in speech:
                    patterns[name]['common_phrases'] = ['dude', 'man', 'totally', 'let\'s go']
                elif 'childlike' in speech or 'simple' in speech:
                    patterns[name]['common_phrases'] = ['big brother', 'yay', 'want to']
        
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
        missing_files = 0

        for chapter in chapter_configs:
            chapter_id = chapter.get("id", "unknown")
            jp_file = chapter.get("jp_file") or chapter.get("source_file")
            if not jp_file:
                continue

            source_path = self.work_dir / "JP" / jp_file
            if not source_path.exists():
                missing_files += 1
                continue

            try:
                jp_text = source_path.read_text(encoding="utf-8")
                chapter_blocks.append(f"<CHAPTER id='{chapter_id}'>\n{jp_text}\n</CHAPTER>")
            except Exception as e:
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
                logger.info(
                    f"[CACHE] Created volume cache {cache_name} "
                    f"({len(chapter_blocks)} chapters, {len(full_volume_text)} chars, "
                    f"missing={missing_files})"
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
            else:
                logger.info("Pre-warming context cache (volume cache unavailable)...")
                self._prewarm_cache()
        
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
            translated_title = chapter.get(title_key) or chapter.get("title_en")

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
            
            # Run format normalization on all target language outputs
            logger.info("\n" + "="*60)
            logger.info("POST-PROCESSING: Format Normalization")
            logger.info("="*60)
            try:
                normalizer = FormatNormalizer(aggressive=False)
                results = normalizer.normalize_volume(self.work_dir)
                
                # Log aggregate statistics
                total_modified = sum(stats['files_modified'] for stats in results.values())
                if total_modified > 0:
                    logger.info(f"\n✓ Format normalization completed: {total_modified} files cleaned across {len(results)} language(s)")
                else:
                    logger.info("\n✓ Format normalization completed: No issues detected")
            except Exception as e:
                logger.warning(f"Format normalization failed: {e}")
            
            # Run CJK artifact cleanup on all language outputs
            logger.info("\n" + "="*60)
            logger.info("POST-PROCESSING: CJK Artifact Detection")
            logger.info("="*60)
            try:
                # Use detection-only mode (strict_mode=False) to flag artifacts without auto-removal
                cjk_cleaner = CJKArtifactCleaner(strict_mode=False, min_confidence=0.7, context_window=5)
                cjk_results = cjk_cleaner.clean_volume(self.work_dir)
                
                # Log detailed report
                if cjk_results['total_artifacts'] > 0:
                    report = format_results_report(cjk_results)
                    logger.warning(report)
                    logger.warning(f"\n⚠️  Found {cjk_results['total_artifacts']} potential CJK artifacts across {cjk_results['total_files']} files")
                    logger.warning("Review artifacts above and consider manual cleanup or enabling strict_mode for auto-removal")
                else:
                    logger.info("\n✓ CJK artifact detection completed: No artifacts detected")
            except Exception as e:
                logger.warning(f"CJK artifact detection failed: {e}")
            
            # Run automated audit system (v2.0 - 3 subagents)
            logger.info("\n" + "="*60)
            logger.info("POST-PROCESSING: Automated Quality Audit (v2.0)")
            logger.info("="*60)
            try:
                self._run_quality_audit()
            except Exception as e:
                logger.warning(f"Quality audit failed: {e}")
                logger.warning("Continuing without audit report...")

            # Run cross-chapter name consistency audit (romanization drift detection)
            if self.target_language == "en":
                logger.info("\n" + "=" * 60)
                logger.info("POST-PROCESSING: Name Consistency Audit")
                logger.info("=" * 60)
                try:
                    self._run_name_consistency_audit(output_dir)
                except Exception as e:
                    logger.warning(f"Name consistency audit failed: {e}")
                    logger.warning("Continuing without name consistency report...")
            
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
    
    def _run_quality_audit(self) -> None:
        """
        Run the automated quality audit system (v2.0).
        
        Executes 3 subagents in sequence:
        1. Fidelity Auditor - Content preservation check
        2. Integrity Auditor - Names, terms, formatting validation
        3. Prose Auditor - English naturalness via Grammar RAG
        
        Then aggregates results into final report.
        """
        try:
            # Import auditors (lazy import to avoid circular deps)
            from auditors import FidelityAuditor, IntegrityAuditor, ProseAuditor, FinalAuditor
        except ImportError:
            logger.warning("Audit system not available (auditors module not found)")
            logger.warning("Run: pip install -e . or ensure auditors/ is in PYTHONPATH")
            return
        
        # Create audits output directory
        audit_dir = self.work_dir / "audits"
        audit_dir.mkdir(exist_ok=True)
        
        # Config directory for Grammar RAG
        config_dir = Path(__file__).parent.parent.parent / "config"
        
        logger.info(f"Audit output directory: {audit_dir}")
        
        # === SUBAGENT 1: Fidelity Auditor ===
        logger.info("\n🔍 Running Subagent 1: Content Fidelity Audit...")
        try:
            fidelity_auditor = FidelityAuditor(self.work_dir)
            fidelity_report = fidelity_auditor.save_report(audit_dir)
            logger.info(f"✅ Fidelity audit complete: {fidelity_report}")
        except Exception as e:
            logger.error(f"❌ Fidelity audit failed: {e}")
        
        # === SUBAGENT 2: Integrity Auditor ===
        logger.info("\n✍️ Running Subagent 2: Content Integrity Audit...")
        try:
            integrity_auditor = IntegrityAuditor(self.work_dir)
            integrity_report = integrity_auditor.save_report(audit_dir)
            logger.info(f"✅ Integrity audit complete: {integrity_report}")
        except Exception as e:
            logger.error(f"❌ Integrity audit failed: {e}")
        
        # === SUBAGENT 3: Prose Auditor ===
        logger.info("\n💬 Running Subagent 3: Prose Quality Audit...")
        try:
            prose_auditor = ProseAuditor(self.work_dir, config_dir)
            prose_report = prose_auditor.save_report(audit_dir)
            logger.info(f"✅ Prose audit complete: {prose_report}")
        except Exception as e:
            logger.error(f"❌ Prose audit failed: {e}")
        
        # === FINAL AGGREGATION ===
        logger.info("\n📊 Running Final Auditor: Report Aggregation...")
        try:
            final_auditor = FinalAuditor(audit_dir, self.work_dir)
            json_path, md_path = final_auditor.save_reports(audit_dir)
            
            # Display final result
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
            
            grade = summary.get("grade", "?")
            score = summary.get("scores", {}).get("final", 0)
            verdict = summary.get("verdict", "UNKNOWN")
            
            logger.info("")
            logger.info("╔════════════════════════════════════════════════════════════╗")
            logger.info(f"║  AUDIT COMPLETE                                           ║")
            logger.info(f"║  Grade: {grade:<5}  Score: {score:>5.1f}/100  Verdict: {verdict:<14} ║")
            logger.info("╚════════════════════════════════════════════════════════════╝")
            logger.info(f"\n📄 Full report: {md_path}")
            
            # Store audit result in manifest
            self.manifest["pipeline_state"]["translator"]["audit_result"] = {
                "grade": grade,
                "score": score,
                "verdict": verdict,
                "report_path": str(md_path)
            }
            self._save_manifest()
            
        except Exception as e:
            logger.error(f"❌ Final aggregation failed: {e}")

    def _run_name_consistency_audit(self, en_output_dir: Path) -> None:
        """Detect cross-chapter name-variant drift and write audit report."""
        try:
            from auditors import NameConsistencyAuditor
        except ImportError:
            logger.warning("NameConsistencyAuditor unavailable (auditors module not found)")
            return

        auditor = NameConsistencyAuditor()
        canonical_names_set = set()

        metadata = (
            self.manifest.get(f"metadata_{self.target_language}", {})
            or self.manifest.get("metadata_en", {})
            or {}
        )
        character_profiles = metadata.get("character_profiles", {})
        if isinstance(character_profiles, dict):
            for profile in character_profiles.values():
                if not isinstance(profile, dict):
                    continue
                for key in ("full_name", "nickname", "ruby_reading"):
                    value = profile.get(key)
                    if isinstance(value, str) and self._is_likely_person_name(value):
                        canonical_names_set.add(value.strip())

        if not canonical_names_set and getattr(self, "glossary_lock", None):
            for value in self.glossary_lock.get_locked_names().values():
                if isinstance(value, str) and self._is_likely_person_name(value):
                    canonical_names_set.add(value.strip())

        canonical_names = sorted(canonical_names_set)

        report = auditor.audit_volume(en_output_dir, canonical_names=canonical_names or None)

        audit_dir = self.work_dir / "audits"
        audit_dir.mkdir(exist_ok=True)
        report_path = audit_dir / "name_consistency_report.json"
        report_payload = {
            "chapter_count": report.chapter_count,
            "variant_groups": [
                {
                    "canonical": group.canonical,
                    "variants": sorted(group.variants),
                    "occurrences": group.occurrences,
                }
                for group in report.groups
            ],
        }
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2, ensure_ascii=False)

        if report.has_variants():
            logger.warning(
                f"[NAME-CONSISTENCY] Detected {len(report.groups)} variant group(s). "
                f"Report: {report_path}"
            )
            for group in report.groups[:5]:
                variants = ", ".join(sorted(group.variants))
                logger.warning(
                    f"  Canonical '{group.canonical}' has variants: {variants}"
                )
        else:
            logger.info(f"✓ Name consistency audit passed (no drift). Report: {report_path}")

    def _is_likely_person_name(self, value: str) -> bool:
        token = value.strip()
        if not token or len(token) < 3:
            return False
        stopwords = {
            "The", "This", "That", "Some", "Soon", "Many", "More", "Maybe",
            "Skill", "Sword", "Kingdom", "Army", "War", "Act", "Chapter",
        }
        if token in stopwords:
            return False
        if not any(ch.isalpha() for ch in token):
            return False
        # Reject lowercase terms like "sword", "skill", etc.
        if token.lower() == token:
            return False
        if any(char.isdigit() for char in token):
            return False
        # Accept "Tigre", "Eleonora Viltaria", "Ludmila's" style tokens.
        return bool(token[0].isupper())

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
