"""
Master Prompt and RAG Module Loader.
Handles loading of system instructions and injecting RAG knowledge modules.
Supports Three-Tier RAG system with context-aware selective injection.
Supports multi-language configuration (EN, VN, etc.)
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any, Union
from pipeline.translator.config import (
    get_master_prompt_path, get_modules_directory, get_genre_prompt_path
)
from pipeline.config import get_target_language, get_language_config, PIPELINE_ROOT

logger = logging.getLogger(__name__)


class PromptLoader:
    def __init__(self, target_language: str = None, prompts_dir: Path = None, modules_dir: Path = None):
        """
        Initialize PromptLoader.

        Args:
            target_language: Target language code (e.g., 'en', 'vn').
                            If None, uses current target language from config.
            prompts_dir: Override path to prompts directory.
            modules_dir: Override path to modules directory.
        """
        self.target_language = target_language if target_language else get_target_language()
        self.lang_config = get_language_config(self.target_language)

        self.prompts_path = prompts_dir if prompts_dir else get_master_prompt_path(self.target_language)
        self.modules_dir = modules_dir if modules_dir else get_modules_directory(self.target_language)
        
        # Three-Tier RAG paths
        self.reference_dir = None
        self.reference_index_path = None
        self.kanji_difficult_path = None
        self.cjk_prevention_path = None  # Initialize for all languages
        self.anti_ai_ism_path = None  # Anti-AI-ism pattern library (v3.5)
        self.english_grammar_rag_path = None  # English Grammar RAG (Tier 1) - EN only
        self.literacy_techniques_path = None  # Literary techniques (Tier 1) - language-agnostic

        # Setup Three-Tier RAG paths for VN
        self.vietnamese_grammar_rag_path = None  # Vietnamese Grammar RAG (Tier 1) - VN only
        if self.target_language == 'vn':
            reference_dir_config = self.lang_config.get('reference_dir')
            if reference_dir_config:
                self.reference_dir = PIPELINE_ROOT / reference_dir_config
            
            # kanji_difficult.json and reference_index.json are in VN/ root
            # cjk_prevention_schema_vn.json is in prompts/modules/rag/
            vn_root = PIPELINE_ROOT / 'VN'
            prompts_root = PIPELINE_ROOT / 'prompts' / 'modules' / 'rag'
            self.kanji_difficult_path = vn_root / 'kanji_difficult.json'
            self.cjk_prevention_path = prompts_root / 'cjk_prevention_schema_vn.json'
            self.reference_index_path = vn_root / 'reference_index.json'
            # Vietnamese Grammar RAG (Tier 1) - Anti-AI-ism + particle system for JP→VN
            self.vietnamese_grammar_rag_path = vn_root / 'vietnamese_grammar_rag.json'
        
        # Setup CJK prevention for EN (English also needs CJK prevention)
        elif self.target_language == 'en':
            prompts_root = PIPELINE_ROOT / 'prompts' / 'modules' / 'rag'
            self.cjk_prevention_path = prompts_root / 'cjk_prevention_schema_en.json'
            # Anti-AI-ism pattern library (v3.5) - EN only for now
            config_dir = PIPELINE_ROOT / 'config'
            self.anti_ai_ism_path = config_dir / 'anti_ai_ism_patterns.json'
            # English Grammar RAG (Tier 1) - Natural idiom patterns for JP→EN
            self.english_grammar_rag_path = config_dir / 'english_grammar_rag.json'

        # Literacy Techniques (Tier 1 - language-agnostic, applies to both EN and VN)
        config_dir = PIPELINE_ROOT / 'config'
        self.literacy_techniques_path = config_dir / 'literacy_techniques.json'

        self._master_prompt_cache = None
        self._rag_modules_cache = {}
        self._reference_index = None  # Three-Tier RAG metadata
        self._kanji_difficult = None  # Tier 1 kanji data
        self._cjk_prevention = None  # CJK prevention schema with substitution patterns
        self._anti_ai_ism = None  # Anti-AI-ism pattern library (v3.5)
        self._english_grammar_rag = None  # English Grammar RAG (Tier 1) - natural idioms
        self._vietnamese_grammar_rag = None  # Vietnamese Grammar RAG (Tier 1) - anti-AI-ism + particle system
        self._literacy_techniques = None  # Literary techniques (Tier 1) - language-agnostic narrative techniques
        self._continuity_pack = None  # Continuity pack from previous volume
        self._character_names = None  # Character names from manifest
        self._glossary = None  # Glossary terms from manifest
        self._semantic_metadata = None  # Full semantic metadata (Enhanced v2.1: dialogue patterns, scenes, emotional states)
        self._style_guide = None  # Style guide for Vietnamese translation (experimental)
        self._bible_prompt = None  # Series Bible categorized prompt block
        self._bible_world_directive = None  # World setting one-liner for top-of-prompt
        self._bible_glossary_keys = set()  # JP keys covered by bible (for glossary dedup)
        
        # Style guide paths (experimental - Vietnamese only for now)
        self.style_guides_dir = PIPELINE_ROOT / 'style_guides'
        # Normalize Vietnamese: vn→vi for file lookups (files use 'vi' suffix)
        style_lang = 'vi' if self.target_language in ['vi', 'vn'] else self.target_language
        self.style_lang = style_lang  # Store for reuse in load methods
        self.base_style_path = self.style_guides_dir / f'base_style_{style_lang}.json'
        self.genres_dir = self.style_guides_dir / 'genres'
        self.publishers_dir = self.style_guides_dir / 'publishers'

        logger.info(f"PromptLoader initialized for language: {self.target_language.upper()} ({self.lang_config.get('language_name', 'Unknown')})")
        logger.info(f"  Master Prompt: {self.prompts_path}")
        logger.info(f"  Modules Dir: {self.modules_dir}")
        if self.reference_dir:
            logger.info(f"  Reference Dir: {self.reference_dir}")
        if self.kanji_difficult_path and self.kanji_difficult_path.exists():
            logger.info(f"  Kanji Difficult: {self.kanji_difficult_path}")
        
        # Check for style guide system (experimental)
        if self.target_language in ['vi', 'vn'] and self.style_guides_dir.exists():
            logger.info(f"  Style Guides Dir: {self.style_guides_dir} [EXPERIMENTAL]")
    
    def set_continuity_pack(self, continuity_text: str):
        """Set continuity pack for injection into prompts."""
        self._continuity_pack = continuity_text
        logger.info(f"Continuity pack set ({len(continuity_text)} characters)")
    
    def set_character_names(self, character_names: Dict[str, str]):
        """Set character names for injection into cached system instruction."""
        self._character_names = character_names
        logger.info(f"Character names set ({len(character_names)} entries)")
    
    def set_glossary(self, glossary: Dict[str, str]):
        """Set glossary for injection into cached system instruction."""
        self._glossary = glossary
        logger.info(f"Glossary set ({len(glossary)} entries)")
    
    def set_semantic_metadata(self, semantic_metadata: Dict[str, Any]):
        """Set full semantic metadata for injection into system instruction (Enhanced v2.1)."""
        self._semantic_metadata = semantic_metadata
        char_count = len(semantic_metadata.get('characters', []))
        pattern_count = len(semantic_metadata.get('dialogue_patterns', {}))
        scene_count = len(semantic_metadata.get('scene_contexts', {}))
        logger.info(f"Semantic metadata set: {char_count} characters, {pattern_count} dialogue patterns, {scene_count} scenes")

    def set_bible_prompt(self, bible_prompt: str, world_directive: str = "",
                         bible_glossary_keys: set = None):
        """Set series bible prompt block for injection into system instruction.

        Args:
            bible_prompt: Full categorized bible block (CHARACTERS, GEOGRAPHY, etc.)
            world_directive: One-line world setting directive for top-of-prompt injection
            bible_glossary_keys: Set of JP keys covered by bible (deduplicates glossary)
        """
        self._bible_prompt = bible_prompt
        self._bible_world_directive = world_directive or None
        self._bible_glossary_keys = bible_glossary_keys or set()
        parts = [f"Bible prompt set ({len(bible_prompt)} chars)"]
        if world_directive:
            parts.append(f"world directive ({len(world_directive)} chars)")
        if bible_glossary_keys:
            parts.append(f"{len(bible_glossary_keys)} dedup keys")
        logger.info(" | ".join(parts))
    
    def load_style_guide(self, genres: Union[List[str], str, None] = None, publisher: str = None) -> Optional[Dict[str, Any]]:
        """
        Load and merge hierarchical style guides with multi-genre semantic selection (EXPERIMENTAL - Vietnamese only).
        
        Loading Order:
        1. base_style_vi.json (universal rules)
        2. genres/{genre}_vi.json (one or more genre-specific guides)
        3. publishers/{publisher}_vi.json (publisher preferences)
        
        Multi-Genre Semantic Selection:
        - If genres=[list]: Loads specified genres with conditional instructions
        - If genres=None: Loads ALL available genres for semantic selection
        - If genres='single': Loads single genre (legacy behavior)
        
        The AI will semantically select appropriate genre rules based on scene context:
        - Fantasy battle → applies fantasy rules
        - Romance confession → applies romcom rules
        - Mixed scenes → merges relevant genre rules
        
        Args:
            genres: Genre key(s). Can be:
                   - List[str]: ['fantasy', 'romcom'] - Load specific genres
                   - str: 'romcom_school_life' - Load single genre (legacy)
                   - None: Load ALL available genres for semantic selection
            publisher: Publisher key (e.g., 'overlap')
        
        Returns:
            Style guide dictionary with genre metadata or None if not available
        """
        # Only load for Vietnamese target language (vn)
        if self.target_language not in ['vi', 'vn']:
            logger.debug(f"Style guide system only available for Vietnamese (vi/vn), got: {self.target_language}")
            return None
        
        if not self.style_guides_dir.exists():
            logger.debug(f"Style guides directory not found: {self.style_guides_dir}")
            return None
        
        try:
            merged_guide = {
                '_metadata': {
                    'mode': 'multi-genre' if (isinstance(genres, list) or genres is None) else 'single-genre',
                    'genres_loaded': [],
                    'publisher': publisher
                },
                'base': {},
                'genres': {},  # Will contain individual genre guides
                'publisher': {}
            }
            
            # 1. Load base style (universal Vietnamese rules)
            if self.base_style_path.exists():
                with open(self.base_style_path, 'r', encoding='utf-8') as f:
                    base_guide = json.load(f)
                    merged_guide['base'] = base_guide
                    logger.info(f"✓ Loaded base style guide: {self.base_style_path.name}")
            else:
                logger.warning(f"Base style guide not found: {self.base_style_path}")
                return None
            
            # 2. Load genre-specific styles (MULTI-GENRE SUPPORT)
            genres_to_load = []
            
            if genres is None:
                # Load ALL available genres for semantic selection
                if self.genres_dir.exists():
                    genre_files = [f for f in self.genres_dir.glob(f'*_{self.style_lang}.json')]
                    genres_to_load = [f.stem.replace(f'_{self.style_lang}', '') for f in genre_files]
                    logger.info(f"Multi-genre mode: Loading ALL {len(genres_to_load)} available genres")
            elif isinstance(genres, list):
                # Load specified genres
                genres_to_load = genres
                logger.info(f"Multi-genre mode: Loading {len(genres_to_load)} specified genres")
            elif isinstance(genres, str):
                # Single genre (legacy behavior)
                genres_to_load = [genres]
                merged_guide['_metadata']['mode'] = 'single-genre'
                logger.info(f"Single-genre mode: Loading {genres}")
            
            # Load each genre guide
            for genre_key in genres_to_load:
                genre_path = self.genres_dir / f'{genre_key}_{self.style_lang}.json'
                if genre_path.exists():
                    with open(genre_path, 'r', encoding='utf-8') as f:
                        genre_guide = json.load(f)
                        merged_guide['genres'][genre_key] = genre_guide
                        merged_guide['_metadata']['genres_loaded'].append(genre_key)
                        logger.info(f"✓ Loaded genre style guide: {genre_path.name}")
                else:
                    logger.warning(f"Genre style guide not found: {genre_path}")
            
            # 3. Load publisher-specific style
            if publisher:
                publisher_path = self.publishers_dir / f'{publisher}_{self.style_lang}.json'
                if publisher_path.exists():
                    with open(publisher_path, 'r', encoding='utf-8') as f:
                        publisher_guide = json.load(f)
                        merged_guide['publisher'] = publisher_guide
                        logger.info(f"✓ Loaded publisher style guide: {publisher_path.name}")
                else:
                    logger.warning(f"Publisher style guide not found: {publisher_path}")
            
            self._style_guide = merged_guide
            guide_size_kb = len(json.dumps(merged_guide, ensure_ascii=False).encode('utf-8')) / 1024
            genres_loaded = len(merged_guide['_metadata']['genres_loaded'])
            mode = merged_guide['_metadata']['mode']
            logger.info(f"✓ Style guide loaded: {mode}, {genres_loaded} genre(s), {guide_size_kb:.1f}KB [EXPERIMENTAL]")
            return merged_guide
            
        except Exception as e:
            logger.error(f"Failed to load style guide: {e}")
            return None
    
    def _merge_guides(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two style guide dictionaries, with override taking precedence."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_guides(result[key], value)
            else:
                result[key] = value
        return result

    def load_master_prompt(self, genre: str = None) -> str:
        """
        Load the master prompt XML content.

        Args:
            genre: Optional genre key (e.g., 'romcom', 'fantasy') for genre-specific prompts.

        Returns:
            Master prompt content as string.
        """
        if self._master_prompt_cache:
            return self._master_prompt_cache

        # Determine path based on genre if specified
        target_path = self.prompts_path
        if genre:
            target_path = get_genre_prompt_path(genre, self.target_language)
            logger.info(f"Using genre-specific prompt for '{genre}': {target_path}")

        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._master_prompt_cache = content
            logger.info(f"Master prompt loaded: {len(content)} chars from {target_path.name}")
            return content
        except Exception as e:
            logger.error(f"Failed to load master prompt from {target_path}: {e}")
            raise

    def load_rag_modules(self) -> Dict[str, str]:
        """Load all RAG knowledge modules into memory."""
        if self._rag_modules_cache:
            return self._rag_modules_cache

        modules = {}
        if not self.modules_dir.exists():
            logger.warning(f"Modules directory not found: {self.modules_dir}")
            return modules

        # Load all .md files that are not explicitly disabled
        for file_path in self.modules_dir.glob("*.md"):
            if file_path.name.startswith("DISABLED_"):
                logger.info(f"Skipping disabled module: {file_path.name}")
                continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    modules[file_path.name] = content
                    module_size_kb = len(content.encode('utf-8')) / 1024
                    logger.info(f"Loaded RAG module: {file_path.name} ({module_size_kb:.1f}KB)")
            except Exception as e:
                logger.warning(f"Failed to load module {file_path.name}: {e}")

        # Log summary
        total_modules = len(modules)
        total_size_kb = sum(len(c.encode('utf-8')) for c in modules.values()) / 1024
        logger.info(f"Total RAG modules loaded: {total_modules} files ({total_size_kb:.1f}KB)")

        # Verify new anti-AI-ism modules are present
        anti_exposition = "ANTI_EXPOSITION_DUMP_MODULE.md" in modules
        anti_formality = "ANTI_FORMAL_LANGUAGE_MODULE.md" in modules
        anti_translationese = "ANTI_TRANSLATIONESE_MODULE_VN.md" in modules
        
        if anti_exposition and anti_formality:
            logger.info("✓ Anti-AI-ism modules detected (EXPOSITION + FORMALITY)")
        elif anti_translationese:
            logger.info("✓ Anti-AI-ism module detected (ANTI_TRANSLATIONESE v2.1 for VN)")
        elif anti_exposition:
            logger.warning("⚠ Only ANTI_EXPOSITION module found, ANTI_FORMALITY missing")
        elif anti_formality:
            logger.warning("⚠ Only ANTI_FORMALITY module found, ANTI_EXPOSITION missing")
        else:
            logger.warning("⚠ Anti-AI-ism modules NOT found - using legacy prompt only")

        self._rag_modules_cache = modules
        return modules

    def load_kanji_difficult(self) -> Optional[Dict[str, Any]]:
        """Load kanji_difficult.json (Tier 1 - always inject)."""
        if self._kanji_difficult:
            return self._kanji_difficult
        
        if not self.kanji_difficult_path or not self.kanji_difficult_path.exists():
            logger.debug("kanji_difficult.json not found")
            return None
        
        try:
            with open(self.kanji_difficult_path, 'r', encoding='utf-8') as f:
                self._kanji_difficult = json.load(f)
            entries_count = self._kanji_difficult.get('metadata', {}).get('total_entries', 0)
            size_kb = self.kanji_difficult_path.stat().st_size / 1024
            logger.info(f"✓ Loaded kanji_difficult.json: {entries_count} entries ({size_kb:.1f}KB)")
            return self._kanji_difficult
        except Exception as e:
            logger.warning(f"Failed to load kanji_difficult.json: {e}")
            return None

    def load_cjk_prevention(self) -> Optional[Dict[str, Any]]:
        """Load CJK prevention schema for target language (EN/VN)."""
        if self._cjk_prevention:
            return self._cjk_prevention
        
        if not self.cjk_prevention_path or not self.cjk_prevention_path.exists():
            logger.debug(f"CJK prevention schema not found for language: {self.target_language}")
            return None
        
        try:
            with open(self.cjk_prevention_path, 'r', encoding='utf-8') as f:
                self._cjk_prevention = json.load(f)
            size_kb = self.cjk_prevention_path.stat().st_size / 1024
            
            # Calculate total substitution patterns
            total_substitutions = sum([
                len(self._cjk_prevention.get('common_substitutions', {}).get(key, {}))
                for key in ['everyday_vocabulary', 'emotional_expressions', 'actions_and_states', 
                           'character_descriptions', 'chinese_phrases']
            ])
            
            schema_name = self.cjk_prevention_path.name
            logger.info(f"✓ Loaded {schema_name}: {total_substitutions} substitution patterns ({size_kb:.1f}KB)")
            return self._cjk_prevention
        except Exception as e:
            logger.warning(f"Failed to load CJK prevention schema: {e}")
            return None
    
    def load_anti_ai_ism_patterns(self) -> Optional[Dict[str, Any]]:
        """Load anti-AI-ism pattern library (v3.5)."""
        if self._anti_ai_ism:
            return self._anti_ai_ism
        
        if not self.anti_ai_ism_path or not self.anti_ai_ism_path.exists():
            logger.debug(f"Anti-AI-ism pattern library not found for language: {self.target_language}")
            return None
        
        try:
            with open(self.anti_ai_ism_path, 'r', encoding='utf-8') as f:
                self._anti_ai_ism = json.load(f)
            size_kb = self.anti_ai_ism_path.stat().st_size / 1024
            
            # Count patterns by severity (v2.0 structure)
            critical_patterns = len(self._anti_ai_ism.get('CRITICAL', {}).get('patterns', []))
            
            # Count MAJOR patterns across categories
            major_count = 0
            major_categories = self._anti_ai_ism.get('MAJOR', {}).get('categories', {})
            for category_data in major_categories.values():
                major_count += len(category_data.get('patterns', []))
            
            # Count MINOR patterns across categories
            minor_count = 0
            minor_categories = self._anti_ai_ism.get('MINOR', {}).get('categories', {})
            for category_data in minor_categories.values():
                minor_count += len(category_data.get('patterns', []))
            
            total_patterns = critical_patterns + major_count + minor_count
            
            # Check if echo detection is enabled (from _meta)
            meta = self._anti_ai_ism.get('_meta', {})
            echo_enabled = meta.get('echo_detection', {}).get('enabled', False)
            echo_status = "enabled" if echo_enabled else "disabled"
            
            logger.info(f"✓ Loaded anti_ai_ism_patterns.json: {total_patterns} patterns "
                       f"(CRITICAL: {critical_patterns}, MAJOR: {major_count}, "
                       f"MINOR: {minor_count}), echo detection {echo_status} ({size_kb:.1f}KB)")
            return self._anti_ai_ism
        except Exception as e:
            logger.warning(f"Failed to load anti-AI-ism pattern library: {e}")
            return None

    def load_english_grammar_rag(self) -> Optional[Dict[str, Any]]:
        """Load english_grammar_rag.json (Tier 1) - Natural idiom patterns for JP→EN translation."""
        if self._english_grammar_rag:
            return self._english_grammar_rag
        
        # Check for path attribute (only set for EN translations)
        if not hasattr(self, 'english_grammar_rag_path') or not self.english_grammar_rag_path:
            logger.debug("English Grammar RAG not configured for this language")
            return None
        
        if not self.english_grammar_rag_path.exists():
            logger.debug(f"English Grammar RAG not found: {self.english_grammar_rag_path}")
            return None
        
        try:
            with open(self.english_grammar_rag_path, 'r', encoding='utf-8') as f:
                self._english_grammar_rag = json.load(f)
            size_kb = self.english_grammar_rag_path.stat().st_size / 1024
            
            # Count patterns across categories
            pattern_categories = self._english_grammar_rag.get('pattern_categories', {})
            total_patterns = 0
            category_names = []
            
            for cat_name, cat_data in pattern_categories.items():
                patterns = cat_data.get('patterns', [])
                total_patterns += len(patterns)
                category_names.append(cat_name)
            
            # Count high-frequency transcreation patterns specifically
            hf_patterns = pattern_categories.get('high_frequency_transcreations', {}).get('patterns', [])
            transcreation_count = len(hf_patterns)
            
            logger.info(f"✓ Loaded english_grammar_rag.json: {total_patterns} patterns "
                       f"({transcreation_count} high-frequency transcreations) across "
                       f"{len(category_names)} categories ({size_kb:.1f}KB)")
            return self._english_grammar_rag
        except Exception as e:
            logger.warning(f"Failed to load English Grammar RAG: {e}")
            return None

    def load_vietnamese_grammar_rag(self) -> Optional[Dict[str, Any]]:
        """Load vietnamese_grammar_rag.json (Tier 1) - Anti-AI-ism + particle system for JP→VN translation."""
        if self._vietnamese_grammar_rag:
            return self._vietnamese_grammar_rag
        
        # Check for path attribute (only set for VN translations)
        if not hasattr(self, 'vietnamese_grammar_rag_path') or not self.vietnamese_grammar_rag_path:
            logger.debug("Vietnamese Grammar RAG not configured for this language")
            return None
        
        if not self.vietnamese_grammar_rag_path.exists():
            logger.debug(f"Vietnamese Grammar RAG not found: {self.vietnamese_grammar_rag_path}")
            return None
        
        try:
            with open(self.vietnamese_grammar_rag_path, 'r', encoding='utf-8') as f:
                self._vietnamese_grammar_rag = json.load(f)
            size_kb = self.vietnamese_grammar_rag_path.stat().st_size / 1024
            
            # Count patterns across all categories
            total_patterns = 0
            category_stats = []
            
            # Count AI-ism patterns
            sentence_ai_isms = self._vietnamese_grammar_rag.get('sentence_structure_ai_isms', {}).get('patterns', [])
            dialogue_ai_isms = self._vietnamese_grammar_rag.get('dialogue_ai_isms', {}).get('patterns', [])
            total_patterns += len(sentence_ai_isms) + len(dialogue_ai_isms)
            category_stats.append(f"{len(sentence_ai_isms) + len(dialogue_ai_isms)} AI-ism rules")
            
            # Count particles (question + statement + exclamation)
            particle_system = self._vietnamese_grammar_rag.get('particle_system', {})
            question_particles = particle_system.get('question_particles', [])
            statement_particles = particle_system.get('statement_particles', [])
            exclamation_particles = particle_system.get('exclamation_particles', [])
            particle_combos = particle_system.get('combination_patterns', [])
            particle_count = len(question_particles) + len(statement_particles) + len(exclamation_particles)
            total_patterns += particle_count + len(particle_combos)
            category_stats.append(f"{particle_count} particles + {len(particle_combos)} combos")
            
            # Count archetypes
            archetypes = self._vietnamese_grammar_rag.get('archetype_register_matrix', {}).get('archetypes', {})
            total_patterns += len(archetypes)
            category_stats.append(f"{len(archetypes)} archetypes")
            
            # Count pronoun tiers
            pronoun_tiers = self._vietnamese_grammar_rag.get('pronoun_tiers', {})
            pronoun_count = 0
            for tier_type in ['friendship', 'romance_scale']:
                tier_data = pronoun_tiers.get(tier_type, {})
                if isinstance(tier_data, dict):
                    pronoun_count += len(tier_data)
            total_patterns += pronoun_count
            category_stats.append(f"{pronoun_count} pronoun tiers")
            
            logger.info(f"✓ Loaded vietnamese_grammar_rag.json: {total_patterns} patterns "
                       f"({', '.join(category_stats)}) ({size_kb:.1f}KB)")
            return self._vietnamese_grammar_rag
        except Exception as e:
            logger.warning(f"Failed to load Vietnamese Grammar RAG: {e}")
            return None

    def load_literacy_techniques(self) -> Optional[Dict[str, Any]]:
        """Load literacy_techniques.json (Tier 1) - Language-agnostic narrative techniques."""
        if self._literacy_techniques:
            return self._literacy_techniques

        if not self.literacy_techniques_path or not self.literacy_techniques_path.exists():
            logger.debug(f"Literacy techniques not found: {self.literacy_techniques_path}")
            return None

        try:
            with open(self.literacy_techniques_path, 'r', encoding='utf-8') as f:
                self._literacy_techniques = json.load(f)
            size_kb = self.literacy_techniques_path.stat().st_size / 1024

            # Count techniques
            first_person = self._literacy_techniques.get('narrative_techniques', {}).get('first_person', {}).get('subtechniques', {})
            third_person = self._literacy_techniques.get('narrative_techniques', {}).get('third_person', {}).get('subtechniques', {})
            psychic_distance_levels = len(self._literacy_techniques.get('psychic_distance_levels', {}).get('levels', {}))
            genre_presets = len(self._literacy_techniques.get('genre_specific_presets', {}))

            total_techniques = len(first_person) + len(third_person) + 1  # +1 for FID

            logger.info(f"✓ Loaded literacy_techniques.json: {total_techniques} narrative techniques, "
                       f"{psychic_distance_levels} psychic distance levels, {genre_presets} genre presets ({size_kb:.1f}KB)")
            return self._literacy_techniques
        except Exception as e:
            logger.warning(f"Failed to load literacy techniques: {e}")
            return None

    def load_reference_index(self) -> Optional[Dict[str, Any]]:
        """Load reference_index.json (Three-Tier RAG metadata)."""
        if self._reference_index:
            return self._reference_index
        
        if not self.reference_index_path or not self.reference_index_path.exists():
            logger.debug("reference_index.json not found")
            return None
        
        try:
            with open(self.reference_index_path, 'r', encoding='utf-8') as f:
                self._reference_index = json.load(f)
            total_files = self._reference_index.get('total_files', 0)
            total_lines = self._reference_index.get('total_lines', 0)
            logger.info(f"✓ Loaded reference_index.json: {total_files} files, {total_lines} lines indexed")
            return self._reference_index
        except Exception as e:
            logger.warning(f"Failed to load reference_index.json: {e}")
            return None

    def load_reference_modules(self, genre: str = None) -> Dict[str, str]:
        """
        Load reference modules from VN/Reference/ (Tier 2 - context-aware).
        
        For now, implements simplified loading logic based on genre.
        Full context-aware loading (RTAS, scene types, etc.) is Week 2 enhancement.
        
        Args:
            genre: Novel genre (romcom, fantasy, etc.) for genre-based filtering
            
        Returns:
            Dictionary of reference module filenames to content
        """
        if not self.reference_dir or not self.reference_dir.exists():
            return {}
        
        reference_index = self.load_reference_index()
        if not reference_index:
            logger.warning("reference_index.json not loaded - skipping reference modules")
            return {}
        
        modules = {}
        
        # Get list of reference modules from config
        reference_module_names = self.lang_config.get('reference_modules', [])
        if not reference_module_names:
            logger.debug("No reference modules configured in config.yaml")
            return {}
        
        # Load reference modules
        for module_name in reference_module_names:
            module_path = self.reference_dir / module_name
            
            # Try with original name and common variants
            if not module_path.exists():
                # Try appending .md if missing
                if not module_name.endswith('.md'):
                    module_path = self.reference_dir / f"{module_name}.md"
                
                # Try with _VN suffix variations
                if not module_path.exists() and not '_VN' in module_name:
                    module_path = self.reference_dir / module_name.replace('.md', '_VN.md')
            
            if module_path.exists():
                try:
                    with open(module_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    modules[module_path.name] = content
                    size_kb = len(content.encode('utf-8')) / 1024
                    logger.info(f"Loaded reference module: {module_path.name} ({size_kb:.1f}KB)")
                except Exception as e:
                    logger.warning(f"Failed to load reference module {module_path.name}: {e}")
            else:
                logger.debug(f"Reference module not found: {module_name}")
        
        return modules

    def load_rag_modules(self) -> Dict[str, str]:
        """Load all RAG knowledge modules into memory."""
        if self._rag_modules_cache:
            return self._rag_modules_cache

        modules = {}
        if not self.modules_dir.exists():
            logger.warning(f"Modules directory not found: {self.modules_dir}")
            return modules

        # Load all .md files that are not explicitly disabled
        for file_path in self.modules_dir.glob("*.md"):
            if file_path.name.startswith("DISABLED_"):
                logger.info(f"Skipping disabled module: {file_path.name}")
                continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    modules[file_path.name] = content
                    module_size_kb = len(content.encode('utf-8')) / 1024
                    logger.info(f"Loaded RAG module: {file_path.name} ({module_size_kb:.1f}KB)")
            except Exception as e:
                logger.warning(f"Failed to load module {file_path.name}: {e}")

        # Log summary
        total_modules = len(modules)
        total_size_kb = sum(len(c.encode('utf-8')) for c in modules.values()) / 1024
        logger.info(f"Total RAG modules loaded: {total_modules} files ({total_size_kb:.1f}KB)")

        # Verify new anti-AI-ism modules are present
        anti_exposition = "ANTI_EXPOSITION_DUMP_MODULE.md" in modules
        anti_formality = "ANTI_FORMAL_LANGUAGE_MODULE.md" in modules
        anti_translationese = "ANTI_TRANSLATIONESE_MODULE_VN.md" in modules
        
        if anti_exposition and anti_formality:
            logger.info("✓ Anti-AI-ism modules detected (EXPOSITION + FORMALITY)")
        elif anti_translationese:
            logger.info("✓ Anti-AI-ism module detected (ANTI_TRANSLATIONESE v2.1 for VN)")
        elif anti_exposition:
            logger.warning("⚠ Only ANTI_EXPOSITION module found, ANTI_FORMALITY missing")
        elif anti_formality:
            logger.warning("⚠ Only ANTI_FORMALITY module found, ANTI_EXPOSITION missing")
        else:
            logger.warning("⚠ Anti-AI-ism modules NOT found - using legacy prompt only")

        self._rag_modules_cache = modules
        return modules

    def build_system_instruction(self, genre: str = None) -> str:
        """
        Construct the final system instruction with Three-Tier RAG injection.

        Tier 1 (Always inject):
          - Core modules (MEGA_CORE, ANTI_TRANSLATIONESE, MEGA_CHARACTER_VOICE)
          - kanji_difficult.json
          - cjk_prevention_schema_*.json (language-specific)
          - anti_ai_ism_patterns.json (EN only)
          - english_grammar_rag.json (EN only)
          - vietnamese_grammar_rag.json (VN only)
          - literacy_techniques.json (language-agnostic)

        Tier 2 (Context-aware):
          - Reference modules based on genre/triggers

        Tier 3 (On-demand):
          - Deferred to Week 3 (retrieval-based)

        Args:
            genre: Novel genre for context-aware module selection

        Returns:
            Complete system instruction with injected RAG modules
        """
        logger.debug("[VERBOSE] Building system instruction...")
        import time
        start_time = time.time()
        
        logger.debug("[VERBOSE] Loading master prompt...")
        master_prompt = self.load_master_prompt(genre)
        logger.debug(f"[VERBOSE] Master prompt loaded: {len(master_prompt)} chars")
        
        # Load Tier 1: Core RAG modules
        logger.debug("[VERBOSE] Loading Tier 1 RAG modules (core)...")
        tier1_modules = self.load_rag_modules()
        logger.debug(f"[VERBOSE] Tier 1 modules loaded: {len(tier1_modules)} files")
        
        # Load Tier 1: kanji_difficult.json
        logger.debug("[VERBOSE] Loading Tier 1: kanji_difficult.json...")
        kanji_data = self.load_kanji_difficult()
        
        # Load Tier 1: cjk_prevention_schema_vn.json
        logger.debug("[VERBOSE] Loading Tier 1: cjk_prevention_schema_vn.json...")
        cjk_prevention_data = self.load_cjk_prevention()
        
        # Load Tier 1: anti_ai_ism_patterns.json (v3.5)
        logger.debug("[VERBOSE] Loading Tier 1: anti_ai_ism_patterns.json...")
        anti_ai_ism_data = self.load_anti_ai_ism_patterns()
        
        # Load Tier 1: english_grammar_rag.json (EN only - natural idiom patterns)
        logger.debug("[VERBOSE] Loading Tier 1: english_grammar_rag.json...")
        english_grammar_rag_data = self.load_english_grammar_rag()
        
        # Load Tier 1: vietnamese_grammar_rag.json (VN only - anti-AI-ism + particle system)
        logger.debug("[VERBOSE] Loading Tier 1: vietnamese_grammar_rag.json...")
        vietnamese_grammar_rag_data = self.load_vietnamese_grammar_rag()

        # Load Tier 1: literacy_techniques.json (language-agnostic narrative techniques)
        logger.debug("[VERBOSE] Loading Tier 1: literacy_techniques.json...")
        literacy_techniques_data = self.load_literacy_techniques()

        # Load Tier 2: Reference modules (context-aware)
        logger.debug("[VERBOSE] Loading Tier 2 reference modules...")
        reference_modules = self.load_reference_modules(genre)
        logger.debug(f"[VERBOSE] Tier 2 modules loaded: {len(reference_modules)} files")
        
        # Merge all modules for injection
        all_modules = {**tier1_modules, **reference_modules}
        
        final_prompt = master_prompt
        injected_count = 0
        anti_ai_ism_injected = []

        # Inject markdown modules
        for filename, content in all_modules.items():
            if filename in final_prompt:
                 module_size_kb = len(content.encode('utf-8')) / 1024
                 # Size Check: Skip modules larger than 500KB to prevent TPM exhaustion
                 if module_size_kb > 500:
                     logger.warning(f"Skipping injection of massive module {filename} ({module_size_kb:.1f}KB) to prevent TPM exhaustion.")
                     continue

                 # Inject content
                 logger.info(f"Injecting RAG module: {filename} ({module_size_kb:.1f}KB)")
                 injected_content = f"\n<!-- START MODULE: {filename} -->\n{content}\n<!-- END MODULE: {filename} -->\n"
                 final_prompt = final_prompt.replace(filename, injected_content)
                 injected_count += 1

                 # Track anti-AI-ism modules
                 if "ANTI_EXPOSITION" in filename or "ANTI_FORMAL" in filename or "ANTI_TRANSLATIONESE" in filename:
                     anti_ai_ism_injected.append(filename)
            else:
                 logger.debug(f"Module {filename} loaded but not referenced in master prompt.")

        # Inject kanji_difficult.json (Tier 1)
        if kanji_data and "kanji_difficult.json" in final_prompt:
            kanji_entries = kanji_data.get('kanji_entries', [])
            kanji_formatted = self._format_kanji_for_injection(kanji_entries, genre)
            kanji_size_kb = len(kanji_formatted.encode('utf-8')) / 1024
            
            logger.info(f"Injecting kanji_difficult.json: {len(kanji_entries)} entries ({kanji_size_kb:.1f}KB)")
            kanji_injection = f"\n<!-- START MODULE: kanji_difficult.json -->\n{kanji_formatted}\n<!-- END MODULE: kanji_difficult.json -->\n"
            final_prompt = final_prompt.replace("kanji_difficult.json", kanji_injection)
            injected_count += 1

        # Inject cjk_prevention_schema_vn.json (Tier 1)
        if cjk_prevention_data and "cjk_prevention_schema_vn.json" in final_prompt:
            cjk_formatted = self._format_cjk_prevention_for_injection(cjk_prevention_data)
            cjk_size_kb = len(cjk_formatted.encode('utf-8')) / 1024
            
            logger.info(f"Injecting cjk_prevention_schema_vn.json: CJK prevention rules ({cjk_size_kb:.1f}KB)")
            cjk_injection = f"\n<!-- START MODULE: cjk_prevention_schema_vn.json -->\n{cjk_formatted}\n<!-- END MODULE: cjk_prevention_schema_vn.json -->\n"
            final_prompt = final_prompt.replace("cjk_prevention_schema_vn.json", cjk_injection)
            injected_count += 1
        
        # Inject anti_ai_ism_patterns.json (Tier 1 - v3.5)
        if anti_ai_ism_data and "anti_ai_ism_patterns.json" in final_prompt:
            anti_ai_ism_formatted = self._format_anti_ai_ism_for_injection(anti_ai_ism_data)
            anti_ai_ism_size_kb = len(anti_ai_ism_formatted.encode('utf-8')) / 1024
            
            # Count patterns
            critical_count = len(anti_ai_ism_data.get('CRITICAL', {}).get('patterns', []))
            major_categories = anti_ai_ism_data.get('MAJOR', {}).get('categories', {})
            major_count = sum(len(cat.get('patterns', [])) for cat in major_categories.values())
            total_count = critical_count + major_count
            
            logger.info(f"Injecting anti_ai_ism_patterns.json: {total_count} patterns ({critical_count} CRITICAL, {major_count} MAJOR) + echo detection ({anti_ai_ism_size_kb:.1f}KB)")
            anti_ai_ism_injection = f"\n<!-- START MODULE: anti_ai_ism_patterns.json -->\n{anti_ai_ism_formatted}\n<!-- END MODULE: anti_ai_ism_patterns.json -->\n"
            final_prompt = final_prompt.replace("anti_ai_ism_patterns.json", anti_ai_ism_injection)
            injected_count += 1
            anti_ai_ism_injected.append('anti_ai_ism_patterns.json (v3.5)')

        # Inject english_grammar_rag.json (Tier 1 - EN only, natural idioms)
        if english_grammar_rag_data and "english_grammar_rag.json" in final_prompt:
            english_grammar_formatted = self._format_english_grammar_rag_for_injection(english_grammar_rag_data)
            grammar_size_kb = len(english_grammar_formatted.encode('utf-8')) / 1024
            
            # Count patterns
            pattern_categories = english_grammar_rag_data.get('pattern_categories', {})
            total_patterns = sum(len(cat.get('patterns', [])) for cat in pattern_categories.values())
            hf_transcreations = len(pattern_categories.get('high_frequency_transcreations', {}).get('patterns', []))
            
            logger.info(f"Injecting english_grammar_rag.json: {total_patterns} patterns ({hf_transcreations} high-frequency transcreations) ({grammar_size_kb:.1f}KB)")
            grammar_injection = f"\n<!-- START MODULE: english_grammar_rag.json -->\n{english_grammar_formatted}\n<!-- END MODULE: english_grammar_rag.json -->\n"
            final_prompt = final_prompt.replace("english_grammar_rag.json", grammar_injection)
            injected_count += 1
            anti_ai_ism_injected.append('english_grammar_rag.json (Tier 1)')
        elif english_grammar_rag_data:
            # Auto-append if placeholder not found (fallback for prompts without placeholder)
            english_grammar_formatted = self._format_english_grammar_rag_for_injection(english_grammar_rag_data)
            grammar_size_kb = len(english_grammar_formatted.encode('utf-8')) / 1024
            
            pattern_categories = english_grammar_rag_data.get('pattern_categories', {})
            total_patterns = sum(len(cat.get('patterns', [])) for cat in pattern_categories.values())
            
            logger.info(f"Appending english_grammar_rag.json (no placeholder found): {total_patterns} patterns ({grammar_size_kb:.1f}KB)")
            final_prompt += f"\n\n<!-- START MODULE: english_grammar_rag.json (AUTO-APPENDED) -->\n{english_grammar_formatted}\n<!-- END MODULE: english_grammar_rag.json -->\n"
            injected_count += 1
            anti_ai_ism_injected.append('english_grammar_rag.json (Tier 1, auto-appended)')

        # Inject vietnamese_grammar_rag.json (Tier 1 - VN only, anti-AI-ism + particle system)
        if vietnamese_grammar_rag_data and "vietnamese_grammar_rag.json" in final_prompt:
            vietnamese_grammar_formatted = self._format_vietnamese_grammar_rag_for_injection(vietnamese_grammar_rag_data)
            grammar_size_kb = len(vietnamese_grammar_formatted.encode('utf-8')) / 1024
            
            # Count patterns
            sentence_ai_isms = len(vietnamese_grammar_rag_data.get('sentence_structure_ai_isms', {}).get('patterns', []))
            dialogue_ai_isms = len(vietnamese_grammar_rag_data.get('dialogue_ai_isms', {}).get('patterns', []))
            # Count particles from correct keys
            particle_system = vietnamese_grammar_rag_data.get('particle_system', {})
            particles = len(particle_system.get('question_particles', [])) + len(particle_system.get('statement_particles', [])) + len(particle_system.get('exclamation_particles', []))
            total_patterns = sentence_ai_isms + dialogue_ai_isms + particles
            
            logger.info(f"Injecting vietnamese_grammar_rag.json: {total_patterns} patterns ({sentence_ai_isms + dialogue_ai_isms} AI-isms, {particles} particles) ({grammar_size_kb:.1f}KB)")
            grammar_injection = f"\n<!-- START MODULE: vietnamese_grammar_rag.json -->\n{vietnamese_grammar_formatted}\n<!-- END MODULE: vietnamese_grammar_rag.json -->\n"
            final_prompt = final_prompt.replace("vietnamese_grammar_rag.json", grammar_injection)
            injected_count += 1
            anti_ai_ism_injected.append('vietnamese_grammar_rag.json (Tier 1)')
        elif vietnamese_grammar_rag_data:
            # Auto-append if placeholder not found (fallback for prompts without placeholder)
            vietnamese_grammar_formatted = self._format_vietnamese_grammar_rag_for_injection(vietnamese_grammar_rag_data)
            grammar_size_kb = len(vietnamese_grammar_formatted.encode('utf-8')) / 1024
            
            sentence_ai_isms = len(vietnamese_grammar_rag_data.get('sentence_structure_ai_isms', {}).get('patterns', []))
            dialogue_ai_isms = len(vietnamese_grammar_rag_data.get('dialogue_ai_isms', {}).get('patterns', []))
            # Count particles from correct keys
            particle_system = vietnamese_grammar_rag_data.get('particle_system', {})
            particles = len(particle_system.get('question_particles', [])) + len(particle_system.get('statement_particles', [])) + len(particle_system.get('exclamation_particles', []))
            total_patterns = sentence_ai_isms + dialogue_ai_isms + particles
            
            logger.info(f"Appending vietnamese_grammar_rag.json (no placeholder found): {total_patterns} patterns ({grammar_size_kb:.1f}KB)")
            final_prompt += f"\n\n<!-- START MODULE: vietnamese_grammar_rag.json (AUTO-APPENDED) -->\n{vietnamese_grammar_formatted}\n<!-- END MODULE: vietnamese_grammar_rag.json -->\n"
            injected_count += 1
            anti_ai_ism_injected.append('vietnamese_grammar_rag.json (Tier 1, auto-appended)')

        # Inject literacy_techniques.json (Tier 1 - language-agnostic narrative techniques)
        if literacy_techniques_data and "literacy_techniques.json" in final_prompt:
            literacy_formatted = self._format_literacy_techniques_for_injection(literacy_techniques_data)
            literacy_size_kb = len(literacy_formatted.encode('utf-8')) / 1024

            # Count techniques
            first_person = len(literacy_techniques_data.get('narrative_techniques', {}).get('first_person', {}).get('subtechniques', {}))
            third_person = len(literacy_techniques_data.get('narrative_techniques', {}).get('third_person', {}).get('subtechniques', {}))
            psychic_levels = len(literacy_techniques_data.get('psychic_distance_levels', {}).get('levels', {}))
            genre_presets = len(literacy_techniques_data.get('genre_specific_presets', {}))

            logger.info(f"Injecting literacy_techniques.json: {first_person + third_person + 1} narrative techniques, "
                       f"{psychic_levels} psychic distance levels, {genre_presets} genre presets ({literacy_size_kb:.1f}KB)")
            literacy_injection = f"\n<!-- START MODULE: literacy_techniques.json -->\n{literacy_formatted}\n<!-- END MODULE: literacy_techniques.json -->\n"
            final_prompt = final_prompt.replace("literacy_techniques.json", literacy_injection)
            injected_count += 1
        elif literacy_techniques_data:
            # Auto-append if placeholder not found (fallback for prompts without placeholder)
            literacy_formatted = self._format_literacy_techniques_for_injection(literacy_techniques_data)
            literacy_size_kb = len(literacy_formatted.encode('utf-8')) / 1024

            first_person = len(literacy_techniques_data.get('narrative_techniques', {}).get('first_person', {}).get('subtechniques', {}))
            third_person = len(literacy_techniques_data.get('narrative_techniques', {}).get('third_person', {}).get('subtechniques', {}))

            logger.info(f"Appending literacy_techniques.json (no placeholder found): {first_person + third_person + 1} techniques ({literacy_size_kb:.1f}KB)")
            final_prompt += f"\n\n<!-- START MODULE: literacy_techniques.json (AUTO-APPENDED) -->\n{literacy_formatted}\n<!-- END MODULE: literacy_techniques.json -->\n"
            injected_count += 1

        final_size_kb = len(final_prompt.encode('utf-8')) / 1024
        elapsed = time.time() - start_time
        logger.info(f"Final System Instruction Size: {final_size_kb:.1f}KB ({injected_count} modules injected) - built in {elapsed:.2f}s")

        # ── Token Budget Gate ────────────────────────────────────
        # Gemini 2.5 Pro context window is 1M tokens (~2.5MB text).
        # System instruction should stay well under 400KB to leave room
        # for the JP source text + visual notes + thinking tokens.
        WARN_THRESHOLD_KB = 300
        HARD_CAP_KB = 500
        if final_size_kb > HARD_CAP_KB:
            logger.error(
                f"🚨 SYSTEM INSTRUCTION EXCEEDS HARD CAP: {final_size_kb:.1f}KB > {HARD_CAP_KB}KB. "
                f"Risk of context overflow. Review bible block size, RAG modules, and glossary."
            )
        elif final_size_kb > WARN_THRESHOLD_KB:
            logger.warning(
                f"⚠ System instruction is large: {final_size_kb:.1f}KB > {WARN_THRESHOLD_KB}KB threshold. "
                f"Consider pruning lower-priority RAG modules or glossary terms."
            )

        # Confirm anti-AI-ism modules are active
        if anti_ai_ism_injected:
            logger.info(f"✓ Anti-AI-ism enforcement active: {', '.join(anti_ai_ism_injected)}")
        else:
            logger.warning("⚠ No anti-AI-ism modules injected into system instruction")
        
        # LEGACY CHARACTER NAME INJECTION DISABLED (v3 Enhanced Schema)
        # Character names are now loaded via character_profiles in semantic_metadata
        # which provides full context (keigo_switch, relationships, speech patterns)
        # instead of just JP→EN name mappings
        # The legacy _character_names dict is no longer used or logged
        
        # ── Phase E: World Setting Directive (TOP-LEVEL RULE) ─────────
        # Injected near the top of the final prompt so the LLM treats it as a
        # binding translation directive for honorifics and name order.
        if self._bible_world_directive:
            final_prompt = f"<!-- WORLD SETTING DIRECTIVE -->\n{self._bible_world_directive}\n\n{final_prompt}"
            logger.info(f"✓ Injected world setting directive at TOP of system instruction")

        # ── Phase E: Series Bible Block (BEFORE glossary) ────────────
        if self._bible_prompt:
            final_prompt += f"\n\n{self._bible_prompt}"
            logger.info(f"✓ Injected Series Bible block ({len(self._bible_prompt)} chars)")

        # Inject glossary into cached system instruction (if available)
        # Phase E: Deduplicate — skip terms already covered by bible block
        if self._glossary:
            if self._bible_glossary_keys:
                # Only emit volume-specific overrides not in bible
                volume_only = {jp: en for jp, en in self._glossary.items()
                               if jp not in self._bible_glossary_keys}
                if volume_only:
                    glossary_text = "\n\n<!-- GLOSSARY — Volume-Specific Overrides (CACHED) -->\n"
                    glossary_text += "Volume-specific terms (supplement the Series Bible above):\n"
                    for jp, en in volume_only.items():
                        glossary_text += f"  {jp} = {en}\n"
                    final_prompt += glossary_text
                    logger.info(f"✓ Injected {len(volume_only)} volume-specific glossary terms "
                                f"(deduplicated {len(self._glossary) - len(volume_only)} bible terms)")
                else:
                    logger.info(f"✓ Glossary fully covered by Series Bible ({len(self._glossary)} terms deduplicated)")
            else:
                glossary_text = "\n\n<!-- GLOSSARY (CACHED) -->\n"
                glossary_text += "Use these established term translations consistently throughout ALL chapters:\n"
                for jp, en in self._glossary.items():
                    glossary_text += f"  {jp} = {en}\n"
                final_prompt += glossary_text
                logger.info(f"✓ Injected {len(self._glossary)} glossary terms into cached system instruction")
        
        # Inject semantic metadata into system instruction (Enhanced v2.1)
        if self._semantic_metadata:
            semantic_injection = self._format_semantic_metadata(self._semantic_metadata)
            # Replace placeholder in master prompt
            if "SEMANTIC_METADATA_PLACEHOLDER" in final_prompt:
                final_prompt = final_prompt.replace("SEMANTIC_METADATA_PLACEHOLDER", semantic_injection)
                logger.info(f"✓ Injected semantic metadata ({len(semantic_injection)} chars)")
            else:
                # Fallback: append if placeholder not found
                final_prompt += f"\n\n<!-- SEMANTIC METADATA (Enhanced v2.1) -->\n{semantic_injection}\n"
                logger.warning("⚠ SEMANTIC_METADATA_PLACEHOLDER not found, appended to end")
        
        # Inject style guide into system instruction (EXPERIMENTAL - Vietnamese only)
        if self._style_guide and self.target_language in ['vi', 'vn']:
            style_guide_injection = self._format_style_guide(self._style_guide)
            # Replace placeholder in master prompt
            if "STYLE_GUIDE_PLACEHOLDER" in final_prompt:
                final_prompt = final_prompt.replace("STYLE_GUIDE_PLACEHOLDER", style_guide_injection)
                logger.info(f"✓ [EXPERIMENTAL] Injected Vietnamese style guide ({len(style_guide_injection)} chars)")
            else:
                # Fallback: append if placeholder not found
                final_prompt += f"\n\n<!-- VIETNAMESE STYLE GUIDE (Experimental) -->\n{style_guide_injection}\n"
                logger.info(f"✓ [EXPERIMENTAL] Vietnamese style guide appended ({len(style_guide_injection)} chars)")

        return final_prompt
    
    def _format_semantic_metadata(self, metadata: Dict[str, Any]) -> str:
        """
        Format semantic metadata for prompt injection.
        
        Supports both Enhanced v2.1 schema AND Legacy V2 schema (after transformation).
        
        Formats:
        - Character profiles with pronouns/relationships
        - Dialogue patterns with speech fingerprints
        - Scene contexts with formality guidance
        - Emotional pronoun shifts state machines
        - Translation guidelines priority system
        """
        lines = []
        
        # 1. CHARACTER PROFILES
        characters = metadata.get('characters', [])
        if characters:
            lines.append("=== CHARACTER PROFILES (Full Semantic Data) ===\n")
            for char in characters:
                # Handle both v2.1 format and transformed legacy format
                name_display = char.get('name_kanji') or char.get('name_en', 'Unknown')
                name_target = char.get('name_vn') or char.get('name_en', 'Unknown')
                
                # Include nickname in display if available
                nickname = char.get('nickname', '')
                if nickname:
                    name_target = f"{name_target} ({nickname})"
                
                lines.append(f"【{name_display} → {name_target}】")
                lines.append(f"  Role: {char.get('role', 'N/A')}")
                lines.append(f"  Gender: {char.get('gender', 'N/A')}, Age: {char.get('age', 'N/A')}")
                
                # Origin
                origin = char.get('origin', '')
                if origin:
                    lines.append(f"  Origin: {origin}")
                
                # Pronouns (handle both dict and string formats)
                pronouns = char.get('pronouns', {})
                if pronouns:
                    if isinstance(pronouns, dict):
                        pron_parts = [f"{k}: {v}" for k, v in pronouns.items()]
                        lines.append(f"  Pronouns: {', '.join(pron_parts)}")
                    else:
                        lines.append(f"  Pronouns: {pronouns}")
                
                # Keigo Switch / Register Shifts (PHASE 0 — PREVIOUSLY INVISIBLE)
                keigo = char.get('keigo_switch', {})
                if keigo and isinstance(keigo, dict):
                    speaking_to = keigo.get('speaking_to', {})
                    if speaking_to:
                        lines.append(f"  Register Shifts:")
                        contraction_data = char.get('contraction_rate', {})
                        contraction_speaking = contraction_data.get('speaking_to', {}) if isinstance(contraction_data, dict) else {}
                        for target, register in list(speaking_to.items())[:10]:
                            cr_info = ""
                            if target in contraction_speaking:
                                cr_info = f" (contraction: {contraction_speaking[target]})"
                            lines.append(f"    → {target}: {register}{cr_info}")
                    # Narration/internal thoughts register
                    narration = keigo.get('narration', '')
                    thoughts = keigo.get('internal_thoughts', '')
                    if narration or thoughts:
                        extras = []
                        if narration:
                            extras.append(f"narration={narration}")
                        if thoughts:
                            extras.append(f"thoughts={thoughts}")
                        lines.append(f"  Base Register: {', '.join(extras)}")
                
                # Contraction Rate baseline (if keigo not shown, show standalone)
                contraction = char.get('contraction_rate', {})
                if contraction and isinstance(contraction, dict) and not keigo:
                    baseline = contraction.get('baseline', '')
                    if baseline:
                        lines.append(f"  Contraction Rate: {baseline}")
                    cr_speaking = contraction.get('speaking_to', {})
                    if cr_speaking:
                        lines.append(f"  Per-Target Contraction:")
                        for target, rate in list(cr_speaking.items())[:8]:
                            lines.append(f"    → {target}: {rate}")
                
                # How Character Refers To Others (PHASE 0 — PREVIOUSLY INVISIBLE)
                refers = char.get('how_refers_to_others', {})
                if refers and isinstance(refers, dict):
                    lines.append(f"  Refers To Others:")
                    for jp_target, ref_pattern in list(refers.items())[:10]:
                        lines.append(f"    → {ref_pattern}")
                
                # RTAS Relationships (PHASE 0 — PREVIOUSLY INVISIBLE)
                relationships = char.get('relationships', {})
                if relationships and isinstance(relationships, dict):
                    # Check for structured RTAS format (not legacy {'context': ...})
                    if 'context' not in relationships:
                        lines.append(f"  Key Relationships:")
                        for target, rel_data in list(relationships.items())[:8]:
                            if isinstance(rel_data, dict):
                                rtype = rel_data.get('type', '')
                                score = rel_data.get('rtas_score', '')
                                rnotes = rel_data.get('notes', '')
                                score_str = f" ({score})" if score else ""
                                notes_str = f" — {rnotes}" if rnotes else ""
                                lines.append(f"    → {target}: {rtype}{score_str}{notes_str}")
                            else:
                                lines.append(f"    → {target}: {rel_data}")
                    else:
                        # Legacy format
                        lines.append(f"  Relationships: {relationships.get('context', '')}")
                
                # Notes (includes transformed personality/appearance from legacy)
                if 'notes' in char:
                    lines.append(f"  Notes: {char['notes']}")
                
                # Character arc (preserved from legacy transformation)
                if 'character_arc' in char:
                    lines.append(f"  Character Arc: {char['character_arc']}")
                
                lines.append("")
        
        # 2. DIALOGUE PATTERNS
        dialogue_patterns = metadata.get('dialogue_patterns', {})
        if dialogue_patterns:
            lines.append("\n=== DIALOGUE PATTERNS (Speech Fingerprints) ===\n")
            for char_name, pattern in dialogue_patterns.items():
                lines.append(f"【{char_name}】")
                lines.append(f"  Speech Style: {pattern.get('speech_style', 'N/A')}")
                
                # Common phrases
                phrases = pattern.get('common_phrases', [])
                if phrases:
                    lines.append(f"  Common Phrases: {', '.join(str(p) for p in phrases[:5])}")  # Limit to 5 for brevity
                
                # Sentence endings
                if 'sentence_endings' in pattern:
                    lines.append(f"  Sentence Endings: {pattern['sentence_endings']}")
                
                # Tone shifts (most important)
                tone_shifts = pattern.get('tone_shifts', {})
                if tone_shifts:
                    lines.append(f"  Tone Shifts:")
                    for context, shift_desc in list(tone_shifts.items())[:3]:  # Top 3 contexts
                        lines.append(f"    {context}: {shift_desc}")
                
                lines.append("")
        
        # 3. SCENE CONTEXTS
        scene_contexts = metadata.get('scene_contexts', {})
        if scene_contexts:
            lines.append("\n=== SCENE CONTEXTS (Location-Based Guidance) ===\n")
            for location, context in scene_contexts.items():
                lines.append(f"【{location}】")
                lines.append(f"  Privacy: {context.get('privacy', 'N/A')}, Formality: {context.get('formality', 'N/A')}")
                if 'pronoun_guidance' in context:
                    lines.append(f"  Pronoun Guidance: {context['pronoun_guidance']}")
                if 'special_note' in context:
                    lines.append(f"  ⚠ Special Note: {context['special_note']}")
                lines.append("")
        
        # 4. EMOTIONAL PRONOUN SHIFTS
        emotional_shifts = metadata.get('emotional_pronoun_shifts', {})
        if emotional_shifts:
            lines.append("\n=== EMOTIONAL PRONOUN SHIFTS (State Machines) ===\n")
            for char_states_key, states_data in emotional_shifts.items():
                lines.append(f"【{char_states_key}】")
                if isinstance(states_data, dict):
                    for state_name, state_info in list(states_data.items())[:3]:  # Top 3 states for brevity
                        lines.append(f"  State: {state_name}")
                        if isinstance(state_info, dict):
                            if 'self' in state_info:
                                lines.append(f"    Self: {state_info['self']}")
                            if 'triggers' in state_info:
                                triggers = state_info['triggers']
                                triggers_str = ', '.join(str(t) for t in triggers[:3]) if isinstance(triggers, list) else str(triggers)
                                lines.append(f"    Triggers: {triggers_str}")
                lines.append("")
        
        # 5. TRANSLATION GUIDELINES (Priority System) - Handles both v2.1 and transformed legacy
        guidelines = metadata.get('translation_guidelines', {})
        if guidelines:
            lines.append("\n=== TRANSLATION GUIDELINES (Priority System) ===\n")
            
            # v2.1 format: pronoun_selection_priority
            priority = guidelines.get('pronoun_selection_priority', [])
            if priority:
                lines.append("Pronoun Selection Priority (Highest → Lowest):")
                for i, step in enumerate(priority, 1):
                    lines.append(f"  {i}. {step}")
            
            # Legacy transformed: character_exceptions (from british_speech_exception)
            char_exceptions = guidelines.get('character_exceptions', {})
            if char_exceptions:
                lines.append("\n⚠ Character Speech Exceptions:")
                for char_name, exception in char_exceptions.items():
                    lines.append(f"  【{char_name}】")
                    allowed = exception.get('allowed_patterns', [])
                    if allowed:
                        lines.append(f"    Allowed patterns: {', '.join(allowed)}")
                    if 'rationale' in exception:
                        lines.append(f"    Rationale: {exception['rationale']}")
            
            # Legacy transformed: forbidden_patterns
            forbidden = guidelines.get('forbidden_patterns', [])
            if forbidden:
                lines.append(f"\n❌ Forbidden Patterns: {', '.join(forbidden)}")
            
            # Legacy transformed: preferred_alternatives
            alternatives = guidelines.get('preferred_alternatives', {})
            if alternatives:
                lines.append("\n✓ Preferred Alternatives:")
                for forbidden_word, replacements in alternatives.items():
                    lines.append(f"  {forbidden_word} → {replacements}")
            
            # Legacy transformed: target_metrics
            metrics = guidelines.get('target_metrics', {})
            if metrics:
                lines.append("\n📊 Target Metrics:")
                for metric_name, target_val in metrics.items():
                    lines.append(f"  {metric_name}: {target_val}")
            
            # Legacy transformed: narrator_voice
            narrator = guidelines.get('narrator_voice', '')
            if narrator:
                lines.append(f"\n🎭 Narrator Voice: {narrator}")
            
            # Legacy transformed: dialogue_rules
            dialogue_rules = guidelines.get('dialogue_rules', {})
            if dialogue_rules:
                lines.append("\n💬 Dialogue Rules (per character):")
                for char_name, rule in dialogue_rules.items():
                    lines.append(f"  {char_name}: {rule}")
            
            # Legacy transformed: naming_conventions
            naming = guidelines.get('naming_conventions', {})
            if naming:
                lines.append("\n📛 Naming Conventions:")
                for category, info in naming.items():
                    if isinstance(info, dict):
                        order = info.get('order', '')
                        chars = info.get('characters', [])
                        if order and chars:
                            lines.append(f"  {category}: {order} ({', '.join(chars[:3])}...)")
                    else:
                        lines.append(f"  {category}: {info}")
            
            # Legacy transformed: volume_context
            volume_ctx = guidelines.get('volume_context', {})
            if volume_ctx:
                lines.append("\n📖 Volume-Specific Context:")
                for key, val in volume_ctx.items():
                    lines.append(f"  {key}: {val}")
            
            # v2.1 format: consistency_rules
            consistency = guidelines.get('consistency_rules', {})
            if consistency:
                lines.append("\nConsistency Rules:")
                for rule_key, rule_desc in list(consistency.items())[:3]:
                    lines.append(f"  - {rule_key}: {rule_desc}")
            
            # v2.1 format: quality_markers
            quality = guidelines.get('quality_markers', {})
            if 'good_translation' in quality:
                lines.append("\n✓ Good Translation Markers:")
                for marker in quality['good_translation'][:3]:
                    lines.append(f"  - {marker}")
            
            if 'red_flags' in quality:
                lines.append("\n❌ Red Flags:")
                for flag in quality['red_flags'][:3]:
                    lines.append(f"  - {flag}")
        
        return '\n'.join(lines)
    
    def _format_style_guide(self, style_guide: Dict[str, Any]) -> str:
        """
        Format style guide for prompt injection with multi-genre semantic selection (EXPERIMENTAL - Vietnamese only).
        
        Supports two modes:
        1. SINGLE-GENRE: Traditional merged guide (legacy behavior)
        2. MULTI-GENRE: Multiple genre guides with conditional semantic selection
        
        In multi-genre mode, formats genre-specific rules with conditional instructions:
        - "For fantasy scenes, apply these rules..."
        - "For romance scenes, apply these rules..."
        - AI semantically determines which rules to apply based on scene context
        
        Converts JSON style guide into readable prompt instructions focusing on:
        1. Contextual Sino-Vietnamese decision framework
        2. Pronoun evolution system
        3. Forbidden archaic patterns
        4. Genre-specific vocabulary preferences
        
        Args:
            style_guide: Style guide dictionary with metadata and genre sections
            
        Returns:
            Formatted style guide text for prompt injection
        """
        metadata = style_guide.get('_metadata', {})
        mode = metadata.get('mode', 'single-genre')
        genres_loaded = metadata.get('genres_loaded', [])
        
        lines = ["# VIETNAMESE TRANSLATION STYLE GUIDE (Experimental)\n"]
        lines.append("## CRITICAL: This style guide addresses two core Vietnamese translation challenges:\n")
        lines.append("## 1. PRONOUN SYSTEM - Navigate complex age/gender/familiarity encoding")
        lines.append("## 2. CONTEXTUAL SINO-VIETNAMESE - Choose appropriate vocabulary register\n")
        
        # Mode indicator
        if mode == 'multi-genre':
            lines.append(f"🎭 MULTI-GENRE SEMANTIC SELECTION MODE ({len(genres_loaded)} genres loaded)\n")
            lines.append("INSTRUCTION: Analyze each scene's genre and apply appropriate style rules.")
            lines.append("You may combine rules from multiple genres for mixed scenes (e.g., fantasy romance).\n")
        else:
            lines.append("📖 SINGLE-GENRE MODE\n")
        
        # Extract base guide for universal rules
        base_guide = style_guide.get('base', style_guide)  # Fallback to root for single-genre mode
        
        # 1. CORE PRINCIPLES (from base guide)
        if 'fundamental_principles' in base_guide:
            lines.append("=== FUNDAMENTAL PRINCIPLES (Apply to ALL genres) ===\n")
            principles = base_guide['fundamental_principles']
            for key, value in principles.items():
                lines.append(f"• {key}: {value}")
            lines.append("")
        
        # 2. CONTEXTUAL SINO-VIETNAMESE (CRITICAL - from base guide)
        vocab_strategy = base_guide.get('vocabulary_strategy', {})
        if vocab_strategy:
            lines.append("=== CONTEXTUAL SINO-VIETNAMESE DECISION FRAMEWORK ===\n")
            
            core_principle = vocab_strategy.get('core_principle', '')
            if core_principle:
                lines.append(f"**{core_principle}**\n")
            
            # Decision framework
            decision_framework = vocab_strategy.get('decision_framework', {})
            if decision_framework:
                lines.append("DECISION TREE:")
                for context_type, rules in decision_framework.items():
                    lines.append(f"\n【{context_type.upper().replace('_', ' ')}】")
                    if 'ratio' in rules:
                        lines.append(f"  Sino-Vietnamese Ratio: {rules['ratio']}")
                    if 'situations' in rules:
                        situations = ', '.join(rules['situations'][:3])
                        lines.append(f"  Applies to: {situations}")
                    if 'examples' in rules:
                        for ex_key, ex_val in list(rules['examples'].items())[:2]:
                            lines.append(f"  {ex_key}: {ex_val}")
            
            # Forbidden patterns (MOST IMPORTANT)
            forbidden = vocab_strategy.get('critical_forbidden_patterns', {})
            if forbidden:
                lines.append("\n❌ CRITICAL FORBIDDEN PATTERNS (NEVER USE):\n")
                for category, data in forbidden.items():
                    if 'wrong' in data and 'correct' in data:
                        wrong_terms = ', '.join(data['wrong'][:5])
                        correct_terms = ', '.join(data['correct'][:5])
                        lines.append(f"  ❌ {category}:")
                        lines.append(f"     WRONG: {wrong_terms}")
                        lines.append(f"     CORRECT: {correct_terms}")
                        if 'explanation' in data:
                            lines.append(f"     Why: {data['explanation']}")
            lines.append("")
        
        # 3. GENRE-SPECIFIC RULES (MULTI-GENRE MODE)
        if mode == 'multi-genre' and genres_loaded:
            lines.append("=== GENRE-SPECIFIC STYLE RULES (Semantic Selection) ===\n")
            lines.append("🎯 INSTRUCTION: Apply the appropriate genre rules based on scene context:\n")
            
            genres_dict = style_guide.get('genres', {})
            for genre_key in genres_loaded:
                genre_guide = genres_dict.get(genre_key, {})
                if not genre_guide:
                    continue
                
                # Format genre header
                genre_name = genre_key.replace('_', ' ').title()
                lines.append(f"\n{'='*60}")
                lines.append(f"🎭 GENRE: {genre_name.upper()}")
                lines.append(f"{'='*60}\n")
                
                # Genre description/when to apply
                genre_desc = self._get_genre_description(genre_key)
                lines.append(f"📌 Apply these rules when: {genre_desc}\n")
                
                # Pronoun system (if genre has specific pronoun rules)
                if 'pronoun_system' in genre_guide:
                    lines.append(f"--- {genre_name} Pronoun Conventions ---\n")
                    pronoun_system = genre_guide['pronoun_system']
                    
                    framework = pronoun_system.get('framework', '')
                    if framework:
                        lines.append(f"Framework: {framework}\n")
                    
                    # Show key pronoun mappings (abbreviated)
                    for role_key, role_data in pronoun_system.items():
                        if role_key in ['framework', 'note', 'critical_fixes']:
                            continue
                        if isinstance(role_data, dict) and 'self_reference' in role_data:
                            lines.append(f"  • {role_key.replace('_', ' ')}: {role_data.get('self_reference', {}).get('casual', 'N/A')}")
                    lines.append("")
                
                # Dialogue style
                if 'dialogue_style' in genre_guide:
                    lines.append(f"--- {genre_name} Dialogue Style ---\n")
                    dialogue = genre_guide['dialogue_style']
                    
                    if 'teen_speech_patterns' in dialogue:
                        teen_speech = dialogue['teen_speech_patterns']
                        if 'exclamations' in teen_speech:
                            exclamations = teen_speech['exclamations']
                            # Show first 2 emotion types
                            for emotion, examples in list(exclamations.items())[:2]:
                                lines.append(f"  {emotion}: {', '.join(examples[:2])}")
                    lines.append("")
                
                # Vocabulary preferences
                if 'vocabulary_preferences' in genre_guide:
                    lines.append(f"--- {genre_name} Vocabulary ---\n")
                    vocab_prefs = genre_guide['vocabulary_preferences']
                    for category, data in list(vocab_prefs.items())[:3]:  # First 3 categories
                        if isinstance(data, dict) and 'prefer' in data:
                            prefer_terms = ', '.join(data['prefer'][:3])
                            lines.append(f"  • {category}: {prefer_terms}")
                    lines.append("")
            
            lines.append(f"{'='*60}\n")
        
        # 4. PRONOUN SYSTEM (SINGLE-GENRE MODE or fallback)
        elif 'pronoun_system' in style_guide:
            lines.append("=== PRONOUN EVOLUTION SYSTEM (Character Relationship Tracking) ===\n")
            pronoun_system = style_guide['pronoun_system']
            
            framework = pronoun_system.get('framework', '')
            if framework:
                lines.append(f"Framework: {framework}\n")
            
            note = pronoun_system.get('note', '')
            if note:
                lines.append(f"⚠️  {note}\n")
            
            # Protagonist pronoun maps
            for role_key, role_data in pronoun_system.items():
                if role_key in ['framework', 'note', 'critical_fixes']:
                    continue
                if isinstance(role_data, dict) and 'self_reference' in role_data:
                    lines.append(f"\n【{role_key.upper().replace('_', ' ')}】")
                    
                    # Self reference
                    self_ref = role_data.get('self_reference', {})
                    if self_ref:
                        lines.append("  Self Reference:")
                        for context, pronoun in list(self_ref.items())[:3]:
                            lines.append(f"    {context}: {pronoun}")
                    
                    # To other characters (with evolution)
                    for target_key, target_data in role_data.items():
                        if target_key in ['self_reference', 'avoid']:
                            continue
                        if isinstance(target_data, dict) and any('phase' in k for k in target_data.keys()):
                            lines.append(f"\n  To {target_key.replace('to_', '').replace('_', ' ')}:")
                            # Show evolution phases
                            for phase_key, phase_data in target_data.items():
                                if 'phase' in phase_key:
                                    chapters = phase_data.get('chapters', '')
                                    pronouns = phase_data.get('pronouns', '')
                                    note_phase = phase_data.get('note', '')
                                    lines.append(f"    Phase {phase_key.split('_')[1]}: {pronouns} ({chapters})")
                                    if note_phase:
                                        lines.append(f"       → {note_phase}")
            
            # Critical fixes
            critical_fixes = pronoun_system.get('critical_fixes', {})
            if critical_fixes:
                lines.append("\n⚠️  CRITICAL PRONOUN FIXES:\n")
                for fix_key, fix_data in critical_fixes.items():
                    if isinstance(fix_data, dict):
                        wrong = fix_data.get('wrong', '')
                        correct = fix_data.get('correct', '')
                        explanation = fix_data.get('explanation', '')
                        lines.append(f"  • {fix_key}:")
                        lines.append(f"    ❌ WRONG: {wrong}")
                        lines.append(f"    ✓ CORRECT: {correct}")
                        lines.append(f"    Why: {explanation}")
            lines.append("")
        
        # 5. PUBLISHER-SPECIFIC OVERRIDES
        publisher_guide = style_guide.get('publisher', {})
        if publisher_guide:
            lines.append("=== PUBLISHER-SPECIFIC PREFERENCES ===\n")
            lines.append("⚠️  These override genre conventions when specified.\n")
            
            if 'tone' in publisher_guide:
                tone = publisher_guide['tone']
                for key, value in tone.items():
                    lines.append(f"  • {key}: {value}")
            lines.append("")
        
        # 6. DIALOGUE STYLE (single-genre fallback)
        if mode == 'single-genre' and 'dialogue_style' in style_guide:
            lines.append("=== DIALOGUE STYLE (Teen Speech Patterns) ===\n")
            dialogue = style_guide['dialogue_style']
            
            teen_speech = dialogue.get('teen_speech_patterns', {})
            if teen_speech and 'exclamations' in teen_speech:
                exclamations = teen_speech['exclamations']
                lines.append("Teen Exclamations:")
                for emotion, examples in list(exclamations.items())[:4]:
                    lines.append(f"  {emotion}: {', '.join(examples[:3])}")
            
            avoid = teen_speech.get('avoid', [])
            if avoid:
                lines.append(f"\n❌ Avoid in teen dialogue: {', '.join(avoid[:5])}")
            lines.append("")
        
        # 7. QUALITY CHECKLIST
        quality_checklist = base_guide.get('quality_checklist', style_guide.get('quality_checklist', {}))
        if quality_checklist:
            lines.append("=== TRANSLATION QUALITY CHECKLIST ===\n")
            for item, desc in quality_checklist.items():
                lines.append(f"  ✓ {item}: {desc}")
            lines.append("")
        
        lines.append("---")
        if mode == 'multi-genre':
            lines.append("🎯 REMINDER: Semantically analyze each scene and apply appropriate genre rules.")
            lines.append("Mix rules from multiple genres for hybrid scenes (e.g., fantasy battle with romance tension).")
        lines.append("⚠️  EXPERIMENTAL FEATURE - Report issues for style guide refinement")
        
        return '\n'.join(lines)
    
    def _get_genre_description(self, genre_key: str) -> str:
        """
        Get human-readable description of when to apply genre rules.
        
        Args:
            genre_key: Genre identifier (e.g., 'romcom_school_life')
            
        Returns:
            Description of applicable scenes
        """
        descriptions = {
            'romcom_school_life': 'Romance scenes, teen dialogue, school life, slice-of-life moments',
            'fantasy': 'Magic, battles, world-building, fantasy elements, supernatural events',
            'action': 'Fight scenes, chase sequences, intense physical conflicts',
            'mystery': 'Investigation scenes, clue discovery, suspenseful moments',
            'slice_of_life': 'Everyday activities, casual conversations, mundane events',
            'drama': 'Emotional conflicts, serious discussions, character development moments'
        }
        return descriptions.get(genre_key, f'Scenes matching {genre_key.replace("_", " ")} genre')

    def _format_kanji_for_injection(self, kanji_entries: List[Dict], genre: str = None) -> str:
        """
        Format kanji_difficult.json entries for prompt injection.
        
        Applies genre filtering if specified to reduce token usage.
        
        Args:
            kanji_entries: List of kanji entry dictionaries
            genre: Optional genre for filtering (romcom, fantasy, historical, etc.)
            
        Returns:
            Formatted kanji reference text
        """
        lines = ["# KANJI DIFFICULT REFERENCE (108 entries - production-validated)\n"]
        lines.append("## Usage: Consult for difficult/archaic kanji with readings, Han-Viet, compounds\n")
        
        # Filter by genre if specified
        if genre:
            filtered_entries = [
                e for e in kanji_entries 
                if not e.get('genre_relevance') or genre in e.get('genre_relevance', []) or 'universal' in e.get('genre_relevance', [])
            ]
            if filtered_entries:
                lines.append(f"## Filtered for genre: {genre} ({len(filtered_entries)} relevant entries)\n")
                kanji_entries = filtered_entries
        
        # Prioritize TOP and HIGH priority entries
        kanji_entries_sorted = sorted(
            kanji_entries,
            key=lambda e: (
                0 if e.get('priority') == 'TOP' else
                1 if e.get('priority') == 'HIGH' else
                2 if e.get('priority') == 'MEDIUM' else 3
            )
        )
        
        for entry in kanji_entries_sorted:
            kanji = entry.get('kanji', '')
            on_reading = entry.get('on_reading', '')
            kun_reading = entry.get('kun_reading', '')
            han_viet = entry.get('han_viet', 'N/A')
            meaning = entry.get('meaning', '')
            notes = entry.get('translation_notes', '')
            priority = entry.get('priority', 'LOW')
            
            # Compact format for token efficiency
            line = f"{kanji} [{on_reading}|{kun_reading}] "
            if han_viet != 'N/A':
                line += f"HV:{han_viet} "
            line += f"({meaning})"
            if priority in ['TOP', 'HIGH']:
                line += f" **{priority}**"
            if notes:
                line += f" — {notes[:100]}"  # Truncate long notes
            lines.append(line)
        
        return "\n".join(lines)

    def _format_cjk_prevention_for_injection(self, cjk_data: Dict[str, Any]) -> str:
        """
        Format CJK prevention schema for prompt injection (EN/VN).
        
        Converts JSON schema into concise, actionable instructions for the AI.
        
        Args:
            cjk_data: CJK prevention schema dictionary
            
        Returns:
            Formatted CJK prevention instructions
        """
        lines = ["# CJK CHARACTER PREVENTION PROTOCOL\n"]
        lines.append("## ⚠️ CRITICAL: Zero CJK Tolerance Policy\n")
        lines.append("**ABSOLUTE RULE:** Output must contain ZERO CJK characters (U+4E00–U+9FFF).\n")
        
        # Language-specific warning
        if self.target_language == 'vn':
            lines.append("Vietnamese uses Latin alphabet exclusively. CJK characters = Translation failure.\n")
        elif self.target_language == 'en':
            lines.append("English uses Latin alphabet exclusively. CJK characters = Translation failure.\n")
        
        # Common substitutions - most important section
        substitutions = cjk_data.get('common_substitutions', {})
        
        # Determine language key (vietnamese or english)
        lang_key = 'vietnamese' if self.target_language == 'vn' else 'english'
        lang_name = 'Vietnamese' if self.target_language == 'vn' else 'English'
        
        # Everyday vocabulary (most common)
        everyday = substitutions.get('everyday_vocabulary', {})
        if everyday:
            lines.append(f"\n## Common Phrase Substitutions (Must Use {lang_name})")
            for jp_phrase, data in list(everyday.items())[:15]:  # Top 15 most common
                options = data.get(lang_key, [])
                if options:
                    lines.append(f"- {jp_phrase} → {', '.join(options[:3])}")
        
        # Emotional expressions
        emotions = substitutions.get('emotional_expressions', {})
        if emotions:
            lines.append("\n## Emotional Expressions")
            for jp_word, data in list(emotions.items())[:10]:  # Top 10
                options = data.get(lang_key, [])
                if options:
                    lines.append(f"- {jp_word} → {', '.join(options[:2])}")
        
        # Actions and states
        actions = substitutions.get('actions_and_states', {})
        if actions:
            lines.append("\n## Common Actions/States")
            for jp_word, data in list(actions.items())[:10]:  # Top 10
                options = data.get(lang_key, [])
                if options:
                    lines.append(f"- {jp_word} → {', '.join(options[:2])}")
        
        # Pre-output validation checklist
        lines.append("\n## ✅ MANDATORY PRE-OUTPUT CHECK")
        lines.append("Before submitting EACH sentence:")
        lines.append("1. Scan for ANY CJK characters (漢字) → If found: STOP and translate")
        lines.append(f"2. Verify 100% {lang_name} (Latin alphabet + diacritics only)")
        lines.append(f"3. Confirm all phrases have {lang_name} equivalents (no mixed scripts)")
        lines.append("4. Check quotation marks are standard \"...\" (not 「」 or 《》)")
        
        lines.append(f"\n**Golden Rule:** If {lang_name} reader with ZERO Japanese knowledge can understand 100% → Success.")
        lines.append("**Failure Condition:** Even 1 CJK character = Translation incomplete = Unacceptable quality.\n")
        
        return "\n".join(lines)
    
    def _format_anti_ai_ism_for_injection(self, anti_ai_ism_data: Dict[str, Any]) -> str:
        """
        Format anti-AI-ism pattern library for prompt injection (v3.5).
        
        Converts JSON pattern library into concise enforcement rules with proximity penalties.
        
        Args:
            anti_ai_ism_data: Anti-AI-ism pattern library dictionary
            
        Returns:
            Formatted anti-AI-ism enforcement instructions
        """
        lines = ["# ANTI-AI-ISM PATTERN LIBRARY (v3.5 LTS)\n"]
        lines.append("## ⚠️ CRITICAL: Human-Level Natural Prose Standard\n")
        
        meta = anti_ai_ism_data.get('_meta', {})
        target_density = meta.get('target_density_per_1k_words', 0.02)
        lines.append(f"**TARGET:** <{target_density} AI-ism instances per 1,000 words (Yen Press/J-Novel Club benchmark)\n")
        
        # CRITICAL patterns (max impact)
        critical_section = anti_ai_ism_data.get('CRITICAL', {})
        critical_patterns = critical_section.get('patterns', [])
        if critical_patterns:
            lines.append("\n## 🔴 CRITICAL PATTERNS (Eliminate 100%)")
            lines.append(critical_section.get('description', ''))
            for pattern in critical_patterns[:8]:  # Top 8
                display = pattern.get('display', '')
                fix = pattern.get('fix', '')
                lines.append(f"- **ELIMINATE:** \"{display}\" → {fix}")
        
        # MAJOR patterns (high priority)
        major_section = anti_ai_ism_data.get('MAJOR', {})
        major_categories = major_section.get('categories', {})
        if major_categories:
            lines.append("\n## 🟠 MAJOR PATTERNS (Minimize to <2 per chapter)")
            lines.append(major_section.get('description', ''))
            
            for category_name, category_data in list(major_categories.items())[:4]:  # Top 4 categories
                category_patterns = category_data.get('patterns', [])
                if category_patterns:
                    lines.append(f"\n### {category_name.replace('_', ' ').title()}")
                    for pattern in category_patterns[:3]:  # 3 samples per category
                        display = pattern.get('display', '')
                        fix = pattern.get('fix', '')
                        lines.append(f"- \"{display}\" → {fix}")
        
        # MINOR patterns (awareness level)
        minor_section = anti_ai_ism_data.get('MINOR', {})
        minor_categories = minor_section.get('categories', {})
        if minor_categories:
            lines.append("\n## 🟡 MINOR PATTERNS (Limit to 3-5 per chapter)")
            
            # Just show category names and 1-2 samples
            for category_name, category_data in list(minor_categories.items())[:2]:  # Just 2 categories
                category_patterns = category_data.get('patterns', [])
                if category_patterns:
                    lines.append(f"- {category_name.replace('_', ' ').title()}: Reduce hedge words, process verbs")
        
        # Echo detection rules (from _meta)
        meta_echo = meta.get('echo_detection', {})
        if meta_echo.get('enabled'):
            lines.append("\n## 🔵 ECHO DETECTION (Proximity-Based)")
            lines.append("**RULE:** Avoid repeating phrases within close proximity (triggers escalating penalties)\n")
            lines.append(f"**Default Window:** {meta_echo.get('default_proximity_window', 100)} words")
            
            thresholds = meta_echo.get('proximity_thresholds', {})
            if thresholds:
                lines.append("\n### Proximity Thresholds")
                for severity, distance in thresholds.items():
                    lines.append(f"- {severity.upper()}: within {distance} words")
            
            lines.append("\n**Note:** Many patterns have proximity_penalty fields that trigger when reused too close together.")
        
        # Enforcement checklist
        lines.append("\n## ✅ PRE-OUTPUT VALIDATION")
        lines.append("Before submitting translation:")
        lines.append("1. **Pattern Scan:** Check for CRITICAL/MAJOR AI-ism patterns")
        lines.append("2. **Echo Check:** Scan last 5 sentences for repeated phrases")
        lines.append("3. **Hedge Audit:** Count hedging words (somewhat, rather, quite) - limit to 3-5/chapter")
        lines.append("4. **Process Verbs:** Replace \"started to/began to\" with direct action verbs")
        lines.append("5. **Natural Flow:** Read aloud - does it sound like a human translator wrote it?")
        
        lines.append("\n**Success Metric:** Translation indistinguishable from human professional localizer.")
        lines.append(f"**Failure Condition:** AI-ism density >{target_density}/1k words = Below professional standard.\n")
        
        return "\n".join(lines)
    
    def _format_english_grammar_rag_for_injection(self, grammar_rag_data: Dict[str, Any]) -> str:
        """
        Format English Grammar RAG for prompt injection (Tier 1).
        
        Converts JSON pattern database into natural English idiom guidance.
        Focuses on high-frequency transcreation patterns for maximum impact.
        
        Args:
            grammar_rag_data: English Grammar RAG dictionary with pattern_categories
            
        Returns:
            Formatted natural idiom guidance for prompt injection
        """
        lines = ["# ENGLISH GRAMMAR RAG: NATURAL IDIOM PATTERNS (Tier 1)\n"]
        lines.append("## 📖 JP→EN Transcreation for Natural English Prose\n")
        lines.append("Apply these idiomatic patterns instead of literal translation.\n")
        
        pattern_categories = grammar_rag_data.get('pattern_categories', {})
        
        # HIGH PRIORITY: High-frequency transcreation patterns
        hf_patterns = pattern_categories.get('high_frequency_transcreations', {}).get('patterns', [])
        if hf_patterns:
            lines.append("## 🔥 HIGH-FREQUENCY TRANSCREATIONS (Top Priority)\n")
            lines.append("These patterns appear frequently in Japanese LN. Apply natural English equivalents:\n")
            
            # Sort by corpus_frequency if available
            sorted_patterns = sorted(hf_patterns, key=lambda x: x.get('corpus_frequency', 0), reverse=True)
            
            for pattern in sorted_patterns[:15]:  # Top 15 most frequent
                pattern_id = pattern.get('id', '')
                jp_indicators = pattern.get('japanese_indicators', [])
                en_pattern = pattern.get('english_pattern', '')
                examples = pattern.get('examples', [])
                usage_rules = pattern.get('usage_rules', [])
                
                # Format indicators
                jp_display = ', '.join(jp_indicators[:3])
                
                lines.append(f"### {jp_display}")
                lines.append(f"**Pattern:** {en_pattern}")
                
                # Add examples (first one)
                if examples:
                    ex = examples[0]
                    if ex.get('literal'):
                        lines.append(f"❌ Literal: \"{ex.get('literal', '')}\"")
                    if ex.get('natural'):
                        lines.append(f"✅ Natural: \"{ex.get('natural', '')}\"")
                
                # Add key usage rule
                if usage_rules:
                    lines.append(f"📌 {usage_rules[0]}")
                
                lines.append("")
        
        # EMOTIONAL INTENSIFIERS
        emotional_patterns = pattern_categories.get('emotional_intensifiers', {}).get('patterns', [])
        if emotional_patterns:
            lines.append("## 💥 EMOTIONAL INTENSIFIERS\n")
            for pattern in emotional_patterns[:5]:
                jp_indicators = pattern.get('japanese_indicators', [])[:2]
                en_pattern = pattern.get('english_pattern', '')
                lines.append(f"- **{', '.join(jp_indicators)}** → {en_pattern}")
            lines.append("")
        
        # CONTRASTIVE COMPARISON
        contrastive_patterns = pattern_categories.get('contrastive_comparison', {}).get('patterns', [])
        if contrastive_patterns:
            lines.append("## ⚖️ CONTRASTIVE COMPARISON\n")
            for pattern in contrastive_patterns[:3]:
                jp_indicators = pattern.get('japanese_indicators', [])[:2]
                en_pattern = pattern.get('english_pattern', '')
                examples = pattern.get('examples', [])
                lines.append(f"- **{', '.join(jp_indicators)}** → \"{en_pattern}\"")
                if examples and examples[0].get('natural'):
                    lines.append(f"  Example: {examples[0].get('natural', '')}")
            lines.append("")
        
        # CONDITIONAL RESTRUCTURING (important for natural flow)
        conditional_patterns = pattern_categories.get('conditional_restructuring', {}).get('patterns', [])
        if conditional_patterns:
            lines.append("## 🔀 CONDITIONAL RESTRUCTURING\n")
            for pattern in conditional_patterns[:3]:
                jp_indicators = pattern.get('japanese_indicators', [])[:2]
                en_pattern = pattern.get('english_pattern', '')
                lines.append(f"- **{', '.join(jp_indicators)}** → \"{en_pattern}\"")
            lines.append("")
        
        # QUICK REFERENCE: Avoid Literal Translations
        lines.append("## ⚠️ AVOID THESE LITERAL TRANSLATIONS\n")
        lines.append("| Japanese Pattern | ❌ Don't Write | ✅ Write Instead |")
        lines.append("|-----------------|----------------|------------------|")
        lines.append("| やっぱり | \"As expected\" | \"Sure enough\", \"I knew it\" |")
        lines.append("| さすが | \"As expected of X\" | \"That's X for you\", \"Classic X\" |")
        lines.append("| しょうがない | \"It can't be helped\" | \"Oh well\", \"What can you do\" |")
        lines.append("| まさか | \"Could it be...\" | \"Wait...\", \"No way\" |")
        lines.append("| 絶対 | \"Absolutely\" | \"No way\", \"For sure\", \"I swear\" |")
        lines.append("| まったく | \"Completely\" | \"Good grief\", \"Honestly\", \"Jeez\" |")
        lines.append("")
        
        lines.append("**Golden Rule:** Natural English TRUMPS dictionary accuracy.")
        lines.append("**Success Metric:** Native English reader experiences NO translation friction.\n")
        
        return "\n".join(lines)

    def _format_vietnamese_grammar_rag_for_injection(self, grammar_rag_data: Dict[str, Any]) -> str:
        """
        Format Vietnamese Grammar RAG for prompt injection (Tier 1).
        
        Converts JSON pattern database into Vietnamese translation guidance.
        Focuses on:
        1. AI-ism elimination (sentence + dialogue patterns)
        2. Particle system by archetype/RTAS
        3. Pronoun tier system (friendship/romance)
        4. Japanese structure carryover prevention
        
        Args:
            grammar_rag_data: Vietnamese Grammar RAG dictionary
            
        Returns:
            Formatted Vietnamese grammar guidance for prompt injection
        """
        lines = ["# VIETNAMESE GRAMMAR RAG: ANTI-AI-ISM + PARTICLE SYSTEM (Tier 1)\n"]
        lines.append("## 🇻🇳 JP→VN Transcreation for Natural Vietnamese Prose\n")
        lines.append("Sử dụng hệ thống particle và cấu trúc câu tự nhiên của tiếng Việt.\n")
        
        # CRITICAL: AI-ISM ELIMINATION
        lines.append("## 🚫 CRITICAL: XÓA AI-ISM PATTERNS\n")
        
        # Sentence structure AI-isms  
        sentence_ai_isms = grammar_rag_data.get('sentence_structure_ai_isms', {}).get('patterns', [])
        if sentence_ai_isms:
            lines.append("### Cấu Trúc Câu AI-ism (CẤM DÙNG)\n")
            for pattern in sentence_ai_isms:
                rule_id = pattern.get('id', '')
                rule = pattern.get('rule', '')
                severity = pattern.get('severity', 'high')
                forbidden = pattern.get('forbidden', [])[:3]  # First 3 examples
                corrections = pattern.get('corrections', {})
                
                lines.append(f"**{rule_id}** [{severity.upper()}]")
                lines.append(f"Rule: {rule}")
                if forbidden:
                    lines.append(f"❌ Forbidden: {', '.join(forbidden)}")
                if corrections:
                    # Show first correction
                    for wrong, correct in list(corrections.items())[:1]:
                        lines.append(f"   ❌ \"{wrong}\"")
                        lines.append(f"   ✅ \"{correct}\"")
                lines.append("")
        
        # Dialogue AI-isms
        dialogue_ai_isms = grammar_rag_data.get('dialogue_ai_isms', {}).get('patterns', [])
        if dialogue_ai_isms:
            lines.append("### Hội Thoại AI-ism (TRÁNH)\n")
            for pattern in dialogue_ai_isms:
                rule_id = pattern.get('id', '')
                rule = pattern.get('rule', '')
                
                lines.append(f"**{rule_id}**")
                lines.append(f"Rule: {rule}")
                
                # Handle different pattern structures
                if pattern.get('mappings'):
                    lines.append("Mappings:")
                    for jp, vn_options in list(pattern.get('mappings', {}).items())[:3]:
                        options = ', '.join(vn_options) if isinstance(vn_options, list) else vn_options
                        lines.append(f"  {jp} → {options}")
                elif pattern.get('correct_patterns'):
                    for style, example in list(pattern.get('correct_patterns', {}).items())[:2]:
                        lines.append(f"  {style}: {example}")
                lines.append("")
        
        # PARTICLE SYSTEM (CORE)
        lines.append("## 💬 PARTICLE SYSTEM: SẮC THÁI HỘI THOẠI\n")
        
        particle_system = grammar_rag_data.get('particle_system', {})
        
        # Question particles
        question_particles = particle_system.get('question_particles', [])
        if question_particles:
            lines.append("### Question Particles\n")
            lines.append("| Particle | Register | Gender | Archetype | Ví dụ |")
            lines.append("|----------|----------|--------|-----------|-------|")
            
            for p in question_particles[:8]:
                particle = p.get('particle', '')
                register = p.get('register', 'neutral')
                gender = p.get('gender', 'both')
                archetypes = p.get('archetype_affinity', ['universal'])[:2]
                examples = p.get('examples', [''])
                example = examples[0] if examples else ''
                arch_str = ', '.join(archetypes)
                lines.append(f"| **{particle}** | {register} | {gender} | {arch_str} | {example} |")
            lines.append("")
        
        # Statement particles
        statement_particles = particle_system.get('statement_particles', [])
        if statement_particles:
            lines.append("### Statement Particles\n")
            lines.append("| Particle | Register | Function | Ví dụ |")
            lines.append("|----------|----------|----------|-------|")
            
            for p in statement_particles[:8]:
                particle = p.get('particle', '')
                register = p.get('register', 'neutral')
                function = p.get('function', '')
                examples = p.get('examples', [''])
                example = examples[0] if examples else ''
                lines.append(f"| **{particle}** | {register} | {function} | {example} |")
            lines.append("")
        
        # Combination patterns
        combo_patterns = particle_system.get('combination_patterns', [])
        if combo_patterns:
            lines.append("### Particle Combinations\n")
            for combo in combo_patterns[:5]:
                combination = combo.get('combination', '')
                register = combo.get('register', '')
                function = combo.get('function', '')
                example = combo.get('example', '')
                lines.append(f"- **{combination}** ({register}): {function}")
                if example:
                    lines.append(f"  Ví dụ: \"{example}\"")
            lines.append("")
        
        # ARCHETYPE REGISTER MATRIX
        lines.append("## 🎭 ARCHETYPE-PARTICLE MAPPING\n")
        
        archetypes = grammar_rag_data.get('archetype_register_matrix', {}).get('archetypes', {})
        if archetypes:
            lines.append("| Archetype | Register | Casual | Forbidden |")
            lines.append("|-----------|----------|--------|-----------|")
            
            for arch_name, arch_data in list(archetypes.items())[:8]:
                register = arch_data.get('preferred_register', 'standard')
                casual = ', '.join(arch_data.get('casual_particles', [])[:3])
                forbidden = ', '.join(arch_data.get('forbidden_particles', [])[:3])
                lines.append(f"| **{arch_name}** | {register} | {casual} | {forbidden} |")
            lines.append("")
        
        # PRONOUN TIERS
        lines.append("## 👤 PRONOUN EVOLUTION BY RELATIONSHIP\n")
        
        pronoun_tiers = grammar_rag_data.get('pronoun_tiers', {})
        
        # Friendship tiers
        friendship = pronoun_tiers.get('friendship', {})
        if friendship:
            lines.append("### Friendship Progression\n")
            for tier_name, tier_data in friendship.items():
                if isinstance(tier_data, dict):
                    rtas_range = tier_data.get('rtas_range', '')
                    pronouns = tier_data.get('pronouns', {})
                    first_person = pronouns.get('first_person', [])[:2]
                    second_person = pronouns.get('second_person', [])[:2]
                    first_str = ', '.join(first_person) if first_person else '-'
                    second_str = ', '.join(second_person) if second_person else '-'
                    lines.append(f"**{tier_name}** (RTAS {rtas_range}): xưng {first_str} / gọi {second_str}")
            lines.append("")
        
        # Romance scale
        romance = pronoun_tiers.get('romance_scale', {})
        if romance:
            lines.append("### Romance Evolution\n")
            for stage, stage_data in list(romance.items())[:4]:
                if isinstance(stage_data, dict):
                    rtas = stage_data.get('rtas', '')
                    pronouns = stage_data.get('pronouns', {})
                    first = pronouns.get('first_person', [''])[:1]
                    second = pronouns.get('second_person', [''])[:1]
                    lines.append(f"**{stage}** (RTAS {rtas}): {first[0] if first else ''} ↔ {second[0] if second else ''}")
            lines.append("")
        
        # RTAS PARTICLE EVOLUTION
        rtas_evolution = grammar_rag_data.get('rtas_particle_evolution', {})
        if rtas_evolution:
            lines.append("## 📈 RTAS PARTICLE EVOLUTION\n")
            for rtas_tier, tier_data in list(rtas_evolution.items())[:4]:
                if isinstance(tier_data, dict):
                    register = tier_data.get('register', '')
                    particles_list = tier_data.get('particles', [])[:4]
                    lines.append(f"**{rtas_tier}** ({register}): {', '.join(particles_list)}")
            lines.append("")
        
        # FREQUENCY THRESHOLDS (warnings)
        frequency = grammar_rag_data.get('frequency_thresholds', {})
        if frequency:
            lines.append("## ⚠️ AI-ISM DENSITY WARNINGS\n")
            max_markers = frequency.get('max_markers_per_1k_words', {})
            if max_markers:
                lines.append("| Marker | Max/1000 từ | Severity |")
                lines.append("|--------|-------------|----------|")
                for marker, limit in list(max_markers.items())[:6]:
                    severity = "🔴" if limit <= 1 else "🟡" if limit <= 2 else "🟢"
                    lines.append(f"| {marker} | {limit} | {severity} |")
            lines.append("")
        
        # GOLDEN RULES
        lines.append("## 📌 GOLDEN RULES\n")
        lines.append("1. **Particle là Linh Hồn Hội Thoại** - Không có particle = đọc như robot")
        lines.append("2. **Match Archetype với Register** - Tsundere ≠ Ojou-sama particle set")
        lines.append("3. **RTAS Drives Pronoun Evolution** - Mức độ thân thiết → thay đổi xưng hô")
        lines.append("4. **Zero AI-ism Tolerance** - \"Có lẽ X...\" patterns = FAIL\n")
        lines.append("")
        lines.append("**Success Metric:** Người đọc Việt Nam không nhận ra là bản dịch.")
        lines.append("**Failure Condition:** AI-ism density >2/1k words = Chưa đạt chuẩn.\n")
        
        return "\n".join(lines)

    def _format_literacy_techniques_for_injection(self, literacy_data: Dict[str, Any]) -> str:
        """
        Format Literary Techniques for prompt injection (Tier 1).

        Converts JSON literary technique database into narrative transcreation guidance.
        Focuses on:
        1. Narrative POV techniques (1st person, 3rd person, Free Indirect Discourse)
        2. Psychic distance levels
        3. Show Don't Tell principles
        4. Genre-specific presets

        Args:
            literacy_data: Literary techniques dictionary with narrative_techniques, psychic_distance_levels, etc.

        Returns:
            Formatted literary technique guidance for prompt injection
        """
        lines = ["# LITERARY TECHNIQUES: CREATIVE TRANSCREATION (Tier 1 - Language-Agnostic)\n"]
        lines.append("## 🎭 What You Are Doing: NOT Translation, But Creative Transcreation\n")
        lines.append("You are not a dictionary—you are a **method actor** performing a script.")
        lines.append("Transform Japanese narrative quirks into natural prose using literary techniques.\n")

        # NARRATIVE TECHNIQUES
        narrative_techniques = literacy_data.get('narrative_techniques', {})

        # Third Person (most common in LN)
        third_person = narrative_techniques.get('third_person', {})
        if third_person:
            lines.append("## 📖 THIRD PERSON NARRATIVE TECHNIQUES\n")

            third_person_subs = third_person.get('subtechniques', {})

            # Third Person Limited (most important for Shoujo/Romance)
            tp_limited = third_person_subs.get('third_person_limited', {})
            if tp_limited:
                lines.append("### 🎯 Third Person Limited (Ngôi thứ ba hạn tri)\n")
                lines.append(f"**Definition:** {tp_limited.get('definition', '')}\n")
                lines.append(f"**Psychic Distance:** {tp_limited.get('psychic_distance', 'close')}")

                filter_removal = tp_limited.get('filter_removal', {})
                if filter_removal and filter_removal.get('enabled'):
                    banned_filters = filter_removal.get('banned_filters', [])
                    lines.append("\n**CRITICAL: Eliminate Filter Words**")
                    lines.append("❌ BANNED: " + ", ".join([f'"{f}"' for f in banned_filters[:5]]))
                    lines.append(f"✅ FIX: {filter_removal.get('instruction', '')}\n")

                vocab_infection = tp_limited.get('vocabulary_infection', {})
                if vocab_infection and vocab_infection.get('enabled'):
                    lines.append(f"**Vocabulary Infection:** {vocab_infection.get('instruction', '')}\n")

            # Third Person Omniscient
            tp_omniscient = third_person_subs.get('third_person_omniscient', {})
            if tp_omniscient:
                lines.append("### 🌍 Third Person Omniscient (Ngôi thứ ba toàn tri)\n")
                lines.append(f"**Definition:** {tp_omniscient.get('definition', '')}")
                lines.append(f"**Psychic Distance:** {tp_omniscient.get('psychic_distance', 'far')}\n")

            # Third Person Objective
            tp_objective = third_person_subs.get('third_person_objective', {})
            if tp_objective:
                lines.append("### 📹 Third Person Objective (Ngôi thứ ba khách quan)\n")
                lines.append(f"**Definition:** {tp_objective.get('definition', '')}")
                banned_content = tp_objective.get('banned_content', [])
                if banned_content:
                    lines.append("\n**BANNED:** " + ", ".join(banned_content[:4]))
                lines.append("")

        # FREE INDIRECT DISCOURSE (Critical for Shoujo)
        fid = narrative_techniques.get('free_indirect_discourse', {})
        if fid:
            lines.append("## 🎨 FREE INDIRECT DISCOURSE (Gián tiếp tự do)\n")
            lines.append(f"**Definition:** {fid.get('description', '')}\n")
            lines.append(f"**Instruction:** {fid.get('instruction', '')}\n")

            examples = fid.get('examples', {})
            if examples:
                lines.append("**Example Transformation:**")
                lines.append(f"❌ Standard 3rd: {examples.get('standard_third', '')}")
                lines.append(f"✅ Free Indirect: {examples.get('free_indirect', '')}")
                lines.append(f"📌 {examples.get('explanation', '')}\n")

            key_features = fid.get('key_features', [])
            if key_features:
                lines.append("**Key Features:**")
                for feature in key_features[:5]:
                    lines.append(f"- {feature}")
                lines.append("")

        # PSYCHIC DISTANCE LEVELS
        psychic_distance = literacy_data.get('psychic_distance_levels', {})
        if psychic_distance:
            levels = psychic_distance.get('levels', {})
            lines.append("## 📏 PSYCHIC DISTANCE SCALE (John Gardner)\n")
            lines.append("Control how close the narration is to the character's consciousness:\n")

            for level_key in ['level_4_very_close', 'level_3_close', 'level_2_distant']:
                level = levels.get(level_key, {})
                if level:
                    description = level.get('description', '')
                    example = level.get('example', '')
                    lines.append(f"**{level_key.replace('_', ' ').title()}**")
                    lines.append(f"- {description}")
                    if example:
                        lines.append(f"- Example: \"{example}\"")
                    lines.append("")

        # SHOW DON'T TELL
        show_dont_tell = literacy_data.get('show_dont_tell', {})
        if show_dont_tell and show_dont_tell.get('enabled'):
            lines.append("## 🎬 SHOW DON'T TELL (Fundamental Rule)\n")
            lines.append(f"**Principle:** {show_dont_tell.get('description', '')}\n")

            banned_phrases = show_dont_tell.get('banned_tell_phrases', [])
            if banned_phrases:
                lines.append("**❌ BANNED TELL PHRASES:**")
                for phrase in banned_phrases[:5]:
                    lines.append(f"- {phrase}")
                lines.append("")

            show_alternatives = show_dont_tell.get('show_alternatives', {})
            if show_alternatives:
                lines.append("**✅ SHOW ALTERNATIVES:**")
                for tell, show in list(show_alternatives.items())[:3]:
                    lines.append(f"- **{tell}** → \"{show}\"")
                lines.append("")

        # GENRE-SPECIFIC PRESETS
        genre_presets = literacy_data.get('genre_specific_presets', {})
        if genre_presets:
            lines.append("## 🎯 GENRE-SPECIFIC NARRATIVE PRESETS\n")

            # Shoujo Romance (most relevant)
            shoujo = genre_presets.get('shoujo_romance', {})
            if shoujo:
                lines.append("### 🌸 Shoujo Romance")
                lines.append(f"- **Technique:** {shoujo.get('narrative_technique', '')}")
                lines.append(f"- **Psychic Distance:** {shoujo.get('psychic_distance', '')}")
                lines.append(f"- **Sensory Focus:** {shoujo.get('sensory_focus', '')}")
                lines.append(f"- **Pacing:** {shoujo.get('sentence_pacing', '')}")
                lines.append(f"- **Vocabulary:** {shoujo.get('emotional_vocabulary', '')}\n")

            # Other genres (abbreviated)
            for genre_key in ['noir_hardboiled', 'psychological_horror']:
                genre = genre_presets.get(genre_key, {})
                if genre:
                    genre_name = genre_key.replace('_', ' ').title()
                    lines.append(f"### {genre_name}")
                    lines.append(f"- Technique: {genre.get('narrative_technique', '')}")
                    lines.append(f"- Distance: {genre.get('psychic_distance', '')}")
                    lines.append(f"- Pacing: {genre.get('sentence_pacing', '')}\n")

        # GOLDEN RULES
        lines.append("## 📌 INTEGRATION RULES\n")
        lines.append("1. **Match Narrative Technique to Source** - If JP uses 3rd person limited, maintain it")
        lines.append("2. **Remove Filter Words** - 'She saw', 'He felt' → Direct perception")
        lines.append("3. **Apply Free Indirect Discourse** - Merge narrator voice with character vocabulary")
        lines.append("4. **Show Emotions Through Actions** - Not 'sad', but 'throat tight, eyes stinging'")
        lines.append("5. **Psychic Distance = Genre** - Shoujo = Very Close, Epic Fantasy = Distant\n")

        lines.append("**Success Metric:** Translation reads as if originally written in target language.")
        lines.append("**Failure:** Reads like a translated document with stiff, unnatural phrasing.\n")

        return "\n".join(lines)

    def build_translation_prompt(
        self,
        source_text: str,
        chapter_title: str,
        previous_context: Optional[str] = None,
        name_registry: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build the complete translation prompt for a chapter.

        Args:
            source_text: Japanese source text to translate.
            chapter_title: Title of the chapter.
            previous_context: Context from previous chapters.
            name_registry: Character name mappings (JP -> Target Language).

        Returns:
            Complete prompt for translation.
        """
        parts = []

        # Continuity pack from previous volume
        if self._continuity_pack:
            parts.append(self._continuity_pack)
            parts.append("")

        # Previous chapter context
        if previous_context:
            parts.append("<!-- CONTEXT FROM PREVIOUS CHAPTERS -->")
            parts.append(previous_context)
            parts.append("")

        # Character name registry
        if name_registry:
            parts.append("<!-- CHARACTER NAME REGISTRY -->")
            parts.append("Use these established name translations consistently:")
            for jp, translated in name_registry.items():
                parts.append(f"  {jp} = {translated}")
            parts.append("")

        # Source text
        parts.append("<!-- SOURCE TEXT TO TRANSLATE -->")
        parts.append(f"# {chapter_title}")
        parts.append("")
        parts.append(source_text)
        parts.append("")

        # Language-specific instructions
        parts.append("<!-- INSTRUCTIONS -->")
        lang_name = self.lang_config.get('language_name', self.target_language.upper())

        if self.target_language == 'vn':
            # Vietnamese-specific instructions
            parts.append(f"Translate the above Japanese text to {lang_name} following all guidelines in the system prompt.")
            parts.append("IMPORTANT: Preserve all [ILLUSTRATION: filename] tags exactly as they appear.")
            parts.append("IMPORTANT: Apply character archetypes and pronoun systems as defined in the prompt.")
            parts.append("IMPORTANT: Transcreate SFX to Vietnamese prose (except for Gyaru archetype with high boldness).")
            parts.append("IMPORTANT: Maintain translation fidelity - 1:1 semantic preservation required.")
            parts.append("")
            parts.append("<!-- GAIJI TRANSCREATION PROTOCOL -->")
            parts.append("CRITICAL: Gaiji markers [ILLUSTRATION: gaiji-*.png] are special character glyphs, NOT real illustrations.")
            parts.append("They represent typographical elements that must be transcreated and the marker REMOVED:")
            parts.append("")
            parts.append("PATTERN RECOGNITION:")
            parts.append("  1. gaiji-dakuon-* (濁音 = voiced marks)")
            parts.append("     Context: Stuttering, hesitation, guttural sounds, emphasized reactions")
            parts.append("     Examples:")
            parts.append("       「[gaiji-dakuon_du_s]、う、うぅ……」 → \"U-Uuu...\" (stammering)")
            parts.append("       「[gaiji-dakuon-n]っ!?」 → \"Ngh?!\" (startled grunt)")
            parts.append("       「[gaiji-dakuon-na]っ……」 → \"Ngh...\" (suppressed sound)")
            parts.append("     Action: Render as phonetic sound effect matching emotional context")
            parts.append("")
            parts.append("  2. gaiji-exclhatena (exclamation + はてな)")
            parts.append("     Context: Surprised confusion, shocked question")
            parts.append("     Examples:")
            parts.append("       「っ[gaiji-exclhatena]」 → \"!?\" (standalone reaction)")
            parts.append("       「え[gaiji-exclhatena]」 → \"Eh!?\" (questioning surprise)")
            parts.append("     Action: Replace with '!?' punctuation, preserve surrounding dialogue")
            parts.append("")
            parts.append("  3. gaiji-handakuon (半濁音 = semi-voiced marks)")
            parts.append("     Context: Softer emphasis, gentler sounds")
            parts.append("     Action: Render as appropriate soft sound (\"Mm\", \"Hm\", etc.)")
            parts.append("")
            parts.append("  4. Other gaiji patterns:")
            parts.append("     - gaiji-ellipsis → Use standard '...' (remove marker)")
            parts.append("     - gaiji-dash → Use em-dash '—' (remove marker)")
            parts.append("     - gaiji-heart/star → Context-appropriate description or omit if purely decorative")
            parts.append("")
            parts.append("EXECUTION RULES:")
            parts.append("  ✓ ALWAYS remove the [ILLUSTRATION: gaiji-*] marker itself")
            parts.append("  ✓ Preserve surrounding dialogue structure (quotes, punctuation)")
            parts.append("  ✓ Match emotional intensity (hesitation vs. shock vs. emphasis)")
            parts.append("  ✓ Use character voice (timid character = softer sounds, bold character = stronger)")
            parts.append("  ✓ If gaiji appears mid-dialogue, integrate naturally without breaking flow")
        else:
            # English instructions (default)
            parts.append(f"Translate the above Japanese text to {lang_name} following all guidelines in the system prompt.")
            parts.append("IMPORTANT: Preserve all [ILLUSTRATION: filename] tags exactly as they appear.")
            parts.append("IMPORTANT: Use contractions naturally (target 80%+ contraction rate).")
            parts.append("IMPORTANT: Avoid AI-isms and formal language patterns.")
            parts.append("")
            parts.append("<!-- GAIJI TRANSCREATION PROTOCOL -->")
            parts.append("CRITICAL: Gaiji markers [ILLUSTRATION: gaiji-*.png] are special character glyphs, NOT real illustrations.")
            parts.append("They represent typographical elements that must be transcreated and the marker REMOVED:")
            parts.append("")
            parts.append("PATTERN RECOGNITION:")
            parts.append("  1. gaiji-dakuon-* (濁音 = voiced marks)")
            parts.append("     Context: Stuttering, hesitation, guttural sounds, emphasized reactions")
            parts.append("     Examples:")
            parts.append("       「[gaiji-dakuon_du_s]、う、うぅ……」 → \"U-Uuu...\" (stammering)")
            parts.append("       「[gaiji-dakuon-n]っ!?」 → \"Ngh?!\" (startled grunt)")
            parts.append("       「[gaiji-dakuon-na]っ……」 → \"Ngh...\" (suppressed sound)")
            parts.append("     Action: Render as phonetic sound effect matching emotional context")
            parts.append("")
            parts.append("  2. gaiji-exclhatena (exclamation + はてな)")
            parts.append("     Context: Surprised confusion, shocked question")
            parts.append("     Examples:")
            parts.append("       「っ[gaiji-exclhatena]」 → \"!?\" (standalone reaction)")
            parts.append("       「え[gaiji-exclhatena]」 → \"Eh!?\" (questioning surprise)")
            parts.append("     Action: Replace with '!?' punctuation, preserve surrounding dialogue")
            parts.append("")
            parts.append("  3. gaiji-handakuon (半濁音 = semi-voiced marks)")
            parts.append("     Context: Softer emphasis, gentler sounds")
            parts.append("     Action: Render as appropriate soft sound (\"Mm\", \"Hm\", etc.)")
            parts.append("")
            parts.append("  4. Other gaiji patterns:")
            parts.append("     - gaiji-ellipsis → Use standard '...' (remove marker)")
            parts.append("     - gaiji-dash → Use em-dash '—' (remove marker)")
            parts.append("     - gaiji-heart/star → Context-appropriate description or omit if purely decorative")
            parts.append("")
            parts.append("EXECUTION RULES:")
            parts.append("  ✓ ALWAYS remove the [ILLUSTRATION: gaiji-*] marker itself")
            parts.append("  ✓ Preserve surrounding dialogue structure (quotes, punctuation)")
            parts.append("  ✓ Match emotional intensity (hesitation vs. shock vs. emphasis)")
            parts.append("  ✓ Use character voice (timid character = softer sounds, bold character = stronger)")
            parts.append("  ✓ If gaiji appears mid-dialogue, integrate naturally without breaking flow")

        return "\n".join(parts)

    def get_total_rag_size(self) -> int:
        """Get total size of RAG modules in characters."""
        modules = self.load_rag_modules()
        return sum(len(c) for c in modules.values())
