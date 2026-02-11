"""
Metadata Processor Agent (Phase 1.5)
===================================

Handles translation of book metadata ONLY:
- Title (title_en)
- Author (author_en)
- Illustrator (illustrator_en)
- Publisher (publisher_en)
- Chapter titles (chapters[].title_en)
- Character names (character_names mapping)

IMPORTANT: This agent PRESERVES the v3 enhanced schema created by Librarian.
It only updates the translation fields without touching:
- character_profiles
- localization_notes
- keigo_switch configurations
- schema_version

Supports multi-language configuration (EN, VN, etc.)
"""

import json
import logging
import argparse
import sys
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from pipeline.common.gemini_client import GeminiClient
from pipeline.metadata_processor.schema_autoupdate import SchemaAutoUpdater
from pipeline.config import (
    PROMPTS_DIR, get_target_language, get_language_config
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MetadataProcessor")


def sanitize_json_strings(obj: Any) -> Any:
    """
    Recursively sanitize JSON objects to escape unescaped quotes in string values.

    Fixes Gemini LLM output that may contain unescaped quotes like:
    "key": "value with "quotes" inside"

    Args:
        obj: JSON object (dict, list, str, etc.)

    Returns:
        Sanitized object with properly escaped quotes
    """
    if isinstance(obj, dict):
        return {k: sanitize_json_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_strings(item) for item in obj]
    elif isinstance(obj, str):
        # Check if string contains unescaped quotes (not at boundaries)
        # This is a heuristic - if we find " in the middle, escape it
        # But skip if it's already escaped (\")
        if '"' in obj and not obj.startswith('"') and not obj.endswith('"'):
            # Replace unescaped quotes with escaped quotes
            # But preserve already escaped quotes
            obj = obj.replace('\\"', '\x00')  # Temporarily mark escaped quotes
            obj = obj.replace('"', '\\"')      # Escape unescaped quotes
            obj = obj.replace('\x00', '\\"')  # Restore escaped quotes
        return obj
    else:
        return obj


# Japanese to Arabic number mapping
JAPANESE_NUMBERS = {
    '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
    '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
    '十一': '11', '十二': '12', '十三': '13', '十四': '14', '十五': '15'
}

# Full-width to half-width number mapping
FULLWIDTH_TO_HALFWIDTH = {
    '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
    '５': '5', '６': '6', '７': '7', '８': '8', '９': '9'
}

# Vietnamese number word mapping
VIETNAMESE_NUMBERS = {
    'Một': '1', 'Hai': '2', 'Ba': '3', 'Bốn': '4', 'Năm': '5',
    'Sáu': '6', 'Bảy': '7', 'Tám': '8', 'Chín': '9', 'Mười': '10'
}


def extract_volume_number(title: str) -> Optional[int]:
    """
    Extract volume number from Japanese book title using prioritized pattern matching.

    Strategy:
    1. Check for numbers in parentheses: (3), （3）, (三), （三）
    2. Check for trailing space + number: "Title 3", "Title ３", "Title 三"
    3. Check for volume markers: "Vol.3", "Volume 3", "巻3"
    4. Fall back to first number found (lowest priority)

    Handles formats:
    - Arabic numerals: 0-9
    - Full-width numerals: ０-９
    - Kanji numerals: 一, 二, 三, etc.

    Examples:
        "この中に1人、妹がいる! 3" → 3 (not 1)
        "タイトル (5)" → 5
        "タイトル　Vol.4" → 4
        "タイトル　第三巻" → 3

    Args:
        title: Japanese book title from .opf metadata

    Returns:
        Volume number as integer, or None if not found
    """
    import re

    if not title:
        return None

    # Helper function to convert any number format to int
    def normalize_number(num_str: str) -> int:
        # Try full-width conversion
        if num_str in FULLWIDTH_TO_HALFWIDTH:
            num_str = FULLWIDTH_TO_HALFWIDTH[num_str]

        # Try multi-character full-width
        normalized = ''.join(FULLWIDTH_TO_HALFWIDTH.get(c, c) for c in num_str)

        # Try kanji conversion
        if normalized in JAPANESE_NUMBERS:
            normalized = JAPANESE_NUMBERS[normalized]

        # Convert to int
        try:
            return int(normalized)
        except ValueError:
            return None

    # Priority 1: Numbers in parentheses (half-width)
    # Matches: (3), (12), etc.
    match = re.search(r'\(([0-9０-９一二三四五六七八九十]+)\)', title)
    if match:
        vol_num = normalize_number(match.group(1))
        if vol_num:
            return vol_num

    # Priority 2: Numbers in full-width parentheses
    # Matches: （3）, （12）, etc.
    match = re.search(r'（([0-9０-９一二三四五六七八九十]+)）', title)
    if match:
        vol_num = normalize_number(match.group(1))
        if vol_num:
            return vol_num

    # Priority 3: Volume markers (Vol., Volume, 巻, etc.)
    # Matches: "Vol.3", "Volume 3", "第3巻", etc.
    match = re.search(r'(?:Vol\.?|Volume|巻|第)\s*([0-9０-９一二三四五六七八九十]+)', title, re.IGNORECASE)
    if match:
        vol_num = normalize_number(match.group(1))
        if vol_num:
            return vol_num

    # Priority 4: Trailing space + number at end of title
    # Matches: "Title 3", "Title　３", "Title 三"
    match = re.search(r'[\s　]+([0-9０-９一二三四五六七八九十]+)$', title)
    if match:
        vol_num = normalize_number(match.group(1))
        if vol_num:
            return vol_num

    # Priority 5: First number found (lowest priority)
    # This catches edge cases but may be wrong for titles like "この中に1人、妹がいる!"
    match = re.search(r'([0-9０-９]+|[一二三四五六七八九十]+)', title)
    if match:
        vol_num = normalize_number(match.group(1))
        if vol_num:
            return vol_num

    return None


def standardize_chapter_title(title: str, target_language: str = 'vn') -> str:
    """
    Standardize chapter titles to consistent Vietnamese format.
    
    Converts chapter number prefixes while preserving subtitles:
    - プロローグ → Chương Mở Đầu
    - 第X話/第X章 → Chương X (preserves subtitle if present)
    - Chuyện X, Hồi thứ X → Chương X (preserves subtitle if present)
    - 間章 → Chương Giữa
    - エピローグ → Chương Cuối
    - あとがき → Lời Bạt
    
    Examples:
        "第一章　一人ラブコメレース編" → "Chương 1　一人ラブコメレース編"
        "第二話" → "Chương 2"
        "Chuyện Hai: Tình Yêu Đầu" → "Chương 2: Tình Yêu Đầu"
    
    Args:
        title: Original chapter title
        target_language: Target language code (currently only 'vn' supported)
        
    Returns:
        Standardized chapter title with subtitle preserved
    """
    if target_language != 'vn':
        return title  # Only standardize for Vietnamese
    
    title = title.strip()
    original_title = title
    
    # Helper function to extract subtitle (everything after separator)
    def extract_subtitle(text, separators=['　', ':', '：', ' - ', '－']):
        for sep in separators:
            if sep in text:
                parts = text.split(sep, 1)
                if len(parts) == 2 and parts[1].strip():
                    return sep + parts[1]  # Include separator
        return ''
    
    # Prologue patterns (no subtitle expected)
    if title in ['プロローグ', 'Khúc Dạo Đầu', 'Lời Mở Đầu', 'Mở Đầu']:
        return 'Chương Mở Đầu'
    
    # Epilogue patterns (no subtitle expected)
    if title in ['エピローグ', 'Kết Thúc', 'Chương Cuối']:
        return 'Chương Cuối'
    
    # Afterword patterns (no subtitle expected)
    if title in ['あとがき', 'Lời bạt', 'Hậu kí']:
        return 'Lời Bạt'
    
    # Interlude/Side Story patterns (no subtitle expected)
    if title in ['間章', 'Chuyện Bên Lề', 'Màn Giữa', 'Giữa Chương']:
        return 'Chương Giữa'
    
    # Extract chapter numbers from various formats (PRESERVE SUBTITLE)
    
    # Japanese: 第二話 or 第二章 → Chương 2 (+ subtitle if present)
    if title.startswith('第') and ('話' in title or '章' in title):
        # Extract the number between 第 and 話/章
        import re
        match = re.match(r'^第([一二三四五六七八九十]+)([話章])(.*)', title)
        if match:
            jp_num = match.group(1)
            marker = match.group(2)
            subtitle = match.group(3)
            
            # Convert Japanese number to Arabic
            if jp_num in JAPANESE_NUMBERS:
                arabic = JAPANESE_NUMBERS[jp_num]
                return f'Chương {arabic}{subtitle}'
    
    # Vietnamese variants: Chuyện Hai, Hồi thứ năm → Chương 2, Chương 5 (+ subtitle)
    for vn_word, arabic in VIETNAMESE_NUMBERS.items():
        # Match: "Chuyện Hai", "Hồi thứ hai"
        patterns = [
            f'Chuyện {vn_word}',
            f'Chuyện {vn_word.lower()}',
            f'thứ {vn_word.lower()}',
            f'Hồi {vn_word}',
            f'Hồi {vn_word.lower()}'
        ]
        
        for pattern in patterns:
            if pattern in title:
                # Extract subtitle after the pattern
                subtitle = extract_subtitle(title)
                return f'Chương {arabic}{subtitle}'
        
        # Direct match: just the number word (no subtitle expected)
        if title == vn_word or title == vn_word.lower():
            return f'Chương {arabic}'
    
    # Already standardized: Chương X (preserve as-is with any subtitle)
    if title.startswith('Chương '):
        return title
    
    # If no pattern matches, return original
    return title


class MetadataProcessor:
    """
    MetadataProcessor - Phase 1 metadata extraction and translation.
    
    V3 SCHEMA MIGRATION (2026-01-28):
    - REMOVED: .context/name_registry.json creation (legacy system)
    - NOW USES: manifest.json metadata_en.character_profiles (v3 enhanced schema)
    - PRESERVED: Reading name_registry.json for backward compatibility with legacy volumes
    
    Character data now stored in manifest.json with full profiles including:
    - keigo_switch, speech_pattern, character_arc, occurrences tracking
    - Richer metadata vs flat JP→EN name mapping
    """
    
    def __init__(self, work_dir: Path, model: str = None, target_language: str = None):
        """
        Initialize MetadataProcessor.

        Args:
            work_dir: Path to the volume working directory.
            model: Optional Gemini model override.
            target_language: Target language code (e.g., 'en', 'vn').
                            If None, uses current target language from config.
        """
        self.work_dir = work_dir
        self.manifest_path = work_dir / "manifest.json"

        # Language configuration
        self.target_language = target_language if target_language else get_target_language()
        self.lang_config = get_language_config(self.target_language)
        self.language_name = self.lang_config.get('language_name', self.target_language.upper())
        self.language_code = self.lang_config.get('language_code', self.target_language)

        logger.info(f"MetadataProcessor initialized for language: {self.target_language.upper()} ({self.language_name})")

        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {self.manifest_path}")

        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            self.manifest = json.load(f)

        # Prioritize hardcoded gemini-2.5-flash for metadata (fast, simple task)
        # Only use config.yaml model if explicitly overridden via parameter
        model = model or "gemini-2.5-flash"
        logger.info(f"Using model: {model}")

        # Disable caching for metadata processor (only 1-2 API calls per volume, not worth overhead)
        self.client = GeminiClient(model=model, enable_caching=False)
        
        # Language-specific prompt
        prompt_filename = f"metadata_processor_prompt_{self.target_language}.xml"
        language_prompt = PROMPTS_DIR / prompt_filename
        self.prompt_path = language_prompt if language_prompt.exists() else PROMPTS_DIR / "metadata_processor_prompt.xml"
        logger.info(f"Using prompt: {self.prompt_path.name}")

        # Language-specific metadata key suffix
        self.metadata_key = f"metadata_{self.target_language}"  # e.g., metadata_en, metadata_vn

    def _run_schema_autoupdate(self) -> None:
        """
        Phase 1.5 pre-step:
        Auto-fill metadata_en schema fields before title/chapter translation.

        This replaces the manual IDE-agent manifest schema filling workflow.
        """
        logger.info("🤖 Running Schema Agent autoupdate (manifest schema enrichment)...")
        updater = None
        try:
            updater = SchemaAutoUpdater(self.work_dir)
            result = updater.apply(self.manifest)
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump(self.manifest, f, indent=2, ensure_ascii=False)

            updated_keys = ", ".join(result.get("updated_keys", [])) or "none"
            logger.info(
                f"✓ Schema Agent autoupdate merged into manifest "
                f"(keys: {updated_keys}, output_tokens: {result.get('output_tokens', 0)})"
            )
        except Exception as e:
            logger.warning(f"Schema Agent autoupdate failed, continuing with existing schema: {e}")
            try:
                if updater:
                    updater.mark_failed(self.manifest, e)
                else:
                    self.manifest.setdefault("pipeline_state", {})["schema_agent"] = {
                        "status": "failed",
                        "timestamp": datetime.datetime.now().isoformat(),
                        "model": "gemini-2.5-flash",
                        "temperature": 0.5,
                        "max_output_tokens": 32768,
                        "error": str(e)[:500],
                    }
                with open(self.manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(self.manifest, f, indent=2, ensure_ascii=False)
            except Exception:
                # Best-effort status write only.
                pass

    def _ensure_ruby_names(self) -> List[Dict[str, Any]]:
        """
        Ruby name extraction is intentionally disabled in MetadataProcessor.

        Canon character metadata is sourced from grounding/canonical pipelines
        (Google Search + bible sync), not ruby extraction fallback.
        """
        logger.debug("Ruby extraction/recording disabled in MetadataProcessor")
        return []

    def _apply_official_localization_overrides(self, metadata_translated: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prefer official localized metadata discovered by schema autoupdate.

        Applies only when schema step marked official data as usable.
        """
        metadata_en = self.manifest.get("metadata_en", {})
        official = metadata_en.get("official_localization", {})
        if not isinstance(official, dict) or not official:
            return metadata_translated

        should_use = official.get("should_use_official")
        confidence = str(official.get("confidence", "")).lower()
        if should_use is False:
            return metadata_translated
        if should_use is None and confidence not in {"high", "medium"}:
            return metadata_translated

        mapping = {
            "volume_title_en": "title_en",
            "author_en": "author_en",
            "publisher_en": "publisher_en",
            "series_title_en": "series_en",
        }
        overridden = []
        for source_key, target_key in mapping.items():
            value = official.get(source_key)
            if isinstance(value, str) and value.strip():
                metadata_translated[target_key] = value.strip()
                overridden.append(target_key)

        if overridden:
            logger.info(
                "🌐 Applied official localization metadata overrides: %s (confidence=%s)",
                ", ".join(overridden),
                confidence or "unknown",
            )

        return metadata_translated
    
    def _update_manifest_preserve_schema(
        self,
        title_en: str,
        author_en: str,
        chapters: Dict[str, str],
        character_names: Dict[str, str],
        glossary: Dict[str, str] = None,
        extra_fields: Dict[str, Any] = None
    ) -> None:
        """
        Update manifest's metadata_en while PRESERVING v3 enhanced schema.
        
        This method merges translated metadata into existing metadata_en without
        overwriting character_profiles, localization_notes, keigo_switch configs, etc.
        
        Args:
            title_en: Translated title
            author_en: Translated author name
            chapters: Dict mapping chapter_id to title_en
            character_names: Dict mapping JP name to EN name
            glossary: Optional glossary terms
            extra_fields: Optional extra fields to add
        """
        existing_metadata_en = self.manifest.get("metadata_en", {})
        
        # Check if v3 enhanced schema exists
        has_v3_schema = (
            "schema_version" in existing_metadata_en or
            "character_profiles" in existing_metadata_en or
            "localization_notes" in existing_metadata_en
        )
        
        if has_v3_schema:
            logger.info("✨ V3 Enhanced Schema detected - preserving structure")
            
            # Update only translation fields, preserve schema
            existing_metadata_en["title_en"] = title_en
            existing_metadata_en["author_en"] = author_en
            existing_metadata_en["character_names"] = character_names
            existing_metadata_en["target_language"] = self.target_language
            existing_metadata_en["language_code"] = self.language_code
            
            if glossary:
                existing_metadata_en["glossary"] = glossary
            
            # Update chapter title_en within existing chapters structure
            if "chapters" in existing_metadata_en:
                existing_chapters = existing_metadata_en["chapters"]
                
                # Handle both list and dict formats
                if isinstance(existing_chapters, list):
                    # List format: [{"id": "chapter_01", "title_en": [...], ...}]
                    for ch in existing_chapters:
                        ch_id = ch.get("id", "")
                        if ch_id in chapters:
                            ch["title_en"] = chapters[ch_id]
                elif isinstance(existing_chapters, dict):
                    # Dict format: {"chapter_01": {"title_jp": ..., "title_en": [...]}}
                    for ch_id, ch_data in existing_chapters.items():
                        if ch_id in chapters:
                            if isinstance(ch_data, dict):
                                ch_data["title_en"] = chapters[ch_id]
                            else:
                                existing_chapters[ch_id] = chapters[ch_id]
            else:
                # No existing chapters, add simple format
                existing_metadata_en["chapters"] = [
                    {"id": ch_id, "title_en": title}
                    for ch_id, title in chapters.items()
                ]
            
            # Add extra fields
            if extra_fields:
                for key, value in extra_fields.items():
                    existing_metadata_en[key] = value
            
            # Add timestamp
            existing_metadata_en["translation_timestamp"] = datetime.datetime.now().isoformat()
            visual_backfilled = self._backfill_visual_identity_non_color(existing_metadata_en)
            if visual_backfilled:
                logger.info(f"   Visual identity backfilled: {visual_backfilled} profile(s)")
            
            self.manifest["metadata_en"] = existing_metadata_en
            
            # Log preserved schema elements
            preserved = []
            if "character_profiles" in existing_metadata_en:
                preserved.append(f"character_profiles({len(existing_metadata_en['character_profiles'])})")
            if "localization_notes" in existing_metadata_en:
                preserved.append("localization_notes")
            if "schema_version" in existing_metadata_en:
                preserved.append(f"schema_version={existing_metadata_en['schema_version']}")
            
            logger.info(f"   Preserved: {', '.join(preserved)}")
        else:
            logger.info("📝 No v3 schema found - using simple metadata format")
            
            # Simple format (legacy/new volumes without Librarian schema)
            self.manifest["metadata_en"] = {
                "title_en": title_en,
                "author_en": author_en,
                "chapters": [
                    {"id": ch_id, "title_en": title}
                    for ch_id, title in chapters.items()
                ],
                "character_names": character_names,
                "glossary": glossary or {},
                "target_language": self.target_language,
                "language_code": self.language_code,
                "timestamp": datetime.datetime.now().isoformat(),
                **(extra_fields or {})
            }
            visual_backfilled = self._backfill_visual_identity_non_color(self.manifest["metadata_en"])
            if visual_backfilled:
                logger.info(f"   Visual identity backfilled: {visual_backfilled} profile(s)")
        
        # Also update chapter title_en in manifest chapters list
        for ch_manifest in self.manifest.get("chapters", []):
            ch_id = ch_manifest.get("id", "")
            if ch_id in chapters:
                ch_manifest["title_en"] = chapters[ch_id]
        
        # Update pipeline state
        if "pipeline_state" not in self.manifest:
            self.manifest["pipeline_state"] = {}
        self.manifest["pipeline_state"]["metadata_processor"] = {
            "status": "completed",
            "target_language": self.target_language,
            "timestamp": datetime.datetime.now().isoformat(),
            "schema_preserved": has_v3_schema
        }

    def _backfill_visual_identity_non_color(self, metadata_block: Dict[str, Any]) -> int:
        """
        Ensure character_profiles include non-color visual identity payload.

        This is additive-only and does not overwrite existing explicit values.
        """
        profiles = metadata_block.get("character_profiles", {})
        if not isinstance(profiles, dict):
            return 0

        updated = 0
        for _, profile in profiles.items():
            if not isinstance(profile, dict):
                continue

            existing = profile.get("visual_identity_non_color")
            has_existing = False
            if isinstance(existing, dict):
                has_existing = any(
                    isinstance(v, str) and v.strip() or isinstance(v, list) and len(v) > 0
                    for v in existing.values()
                )
            elif isinstance(existing, str):
                has_existing = bool(existing.strip())
            elif isinstance(existing, list):
                has_existing = any(str(v).strip() for v in existing)
            if has_existing:
                continue

            appearance = profile.get("appearance", "")
            if isinstance(appearance, str) and appearance.strip():
                profile["visual_identity_non_color"] = {
                    "identity_summary": appearance.strip()
                }
                updated += 1

        return updated
        
    def detect_sequel_parent(self) -> Optional[Dict]:
        """
        Detect if a predecessor volume exists in WORK_DIR.
        Returns comprehensive inheritance data including:
        - metadata_en (title, author)
        - character roster (from name_registry.json)
        - glossary terms
        - chapters (for deduplication)
        - source_volume (for tracking)

        Validation:
        - Ensures metadata_en.json exists and is complete
        - Checks for required fields (title_en, author_en, character_names)
        - Validates that predecessor completed Phase 1.5 successfully

        Selection Strategy:
        - Collects ALL matching volumes in the series
        - Selects the most recent (highest volume number) as prequel
        - Ensures subsequential inheritance (V5 inherits from V4, not V1)
        """
        current_title = self.manifest.get("metadata", {}).get("title", "")
        if not current_title:
            return None

        import re

        # Extract current volume number using smart pattern matching
        current_vol_num = extract_volume_number(current_title)
        if current_vol_num:
            logger.debug(f"Current volume number detected: {current_vol_num} from title: {current_title}")

        # Collect ALL potential prequels
        candidates = []

        # Search for predecessor volumes
        for vol_dir in self.work_dir.parent.iterdir():
            if not vol_dir.is_dir() or vol_dir.name == self.work_dir.name:
                continue

            manifest_path = vol_dir / "manifest.json"
            metadata_en_path = vol_dir / "metadata_en.json"

            # Validation: Both files must exist
            if not (manifest_path.exists() and metadata_en_path.exists()):
                continue

            # Validation: metadata_en.json must be readable and complete
            try:
                with open(metadata_en_path, 'r') as f:
                    metadata_en = json.load(f)

                # Check for required fields
                required_fields = ['title_en', 'author_en', 'target_language']
                if not all(field in metadata_en for field in required_fields):
                    logger.debug(f"⚠️  Skipping {vol_dir.name}: incomplete metadata_en.json")
                    continue

                # Check that it's not a template (has actual translations)
                if metadata_en.get('title_en', '').startswith('[TO BE FILLED]'):
                    logger.debug(f"⚠️  Skipping {vol_dir.name}: metadata not yet processed")
                    continue

            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"⚠️  Skipping {vol_dir.name}: invalid metadata_en.json ({e})")
                continue

            # Files exist and metadata_en is valid, now check if it's same series
            try:
                with open(manifest_path, 'r') as f:
                    m_data = json.load(f)
                other_title = m_data.get("metadata", {}).get("title", "")

                # Heuristic: Shared first 10 chars indicates same series
                if current_title[:10] == other_title[:10]:
                    # Extract volume number from candidate using smart pattern matching
                    other_vol_num = extract_volume_number(other_title)

                    if other_vol_num is None:
                        # No volume number in title = assume Volume 1
                        other_vol_num = 1
                        logger.debug(f"✓ Found series match: {vol_dir.name} (assumed vol 1, no number in title)")
                    else:
                        logger.debug(f"✓ Found series match: {vol_dir.name} (vol {other_vol_num})")

                    # Load character roster from name_registry.json
                    name_registry_path = vol_dir / ".context" / "name_registry.json"
                    character_roster = {}
                    if name_registry_path.exists():
                        try:
                            with open(name_registry_path, 'r') as f:
                                character_roster = json.load(f)
                        except Exception as e:
                            logger.warning(f"Could not load name registry: {e}")

                    # Load glossary from metadata_en.json
                    glossary = metadata_en.get("glossary", {})
                    if not glossary:
                        glossary = m_data.get("glossary", {})

                    # Load chapter info for deduplication
                    chapters = []
                    if 'chapters' in metadata_en:
                        chapters_data = metadata_en['chapters']

                        # Handle both formats: list or dict
                        if isinstance(chapters_data, list):
                            for ch in chapters_data:
                                manifest_chapters = m_data.get('chapters', [])
                                jp_title = next(
                                    (c['title'] for c in manifest_chapters if c['id'] == ch['id']),
                                    ''
                                )
                                if jp_title:
                                    chapters.append({
                                        'id': ch['id'],
                                        'title_jp': jp_title,
                                        'title_en': ch.get('title_en', ch.get('title', ''))
                                    })
                        elif isinstance(chapters_data, dict):
                            manifest_chapters = m_data.get('chapters', [])
                            for ch_id, title_en in chapters_data.items():
                                jp_title = next(
                                    (c['title'] for c in manifest_chapters if c['id'] == ch_id),
                                    ''
                                )
                                if jp_title:
                                    chapters.append({
                                        'id': ch_id,
                                        'title_jp': jp_title,
                                        'title_en': title_en
                                    })

                    # Store candidate with volume number for sorting
                    candidates.append({
                        'vol_num': other_vol_num,
                        'vol_dir': vol_dir,
                        'metadata_en': metadata_en,
                        'character_roster': character_roster,
                        'glossary': glossary,
                        'chapters': chapters
                    })

            except Exception:
                continue

        # No candidates found
        if not candidates:
            return None

        # Select the most recent prequel (highest volume number less than current)
        if current_vol_num is not None:
            # Current has volume number - select immediate predecessor (n-1)
            valid_prequels = [c for c in candidates if c['vol_num'] < current_vol_num]
            if valid_prequels:
                # Sort by volume number (descending) and take the highest
                best_match = sorted(valid_prequels, key=lambda x: x['vol_num'], reverse=True)[0]
                logger.info(f"✓ Selected prequel: {best_match['vol_dir'].name} (vol {best_match['vol_num']} → vol {current_vol_num})")
            else:
                # No valid predecessors (current might be V1)
                return None
        else:
            # Current has no volume number - select highest numbered prequel
            best_match = sorted(candidates, key=lambda x: x['vol_num'], reverse=True)[0]
            logger.info(f"✓ Selected prequel: {best_match['vol_dir'].name} (vol {best_match['vol_num']})")

        # Build inheritance data from best match
        inheritance_data = {
            **best_match['metadata_en'],
            "character_roster": best_match['character_roster'],
            "glossary": best_match['glossary'],
            "chapters": best_match['chapters'],
            "source_volume": best_match['vol_dir'].name,
            "prequel_volume_number": best_match['vol_num']
        }

        return inheritance_data
    
    def _batch_translate_ruby(
        self,
        ruby_names: List[Dict],
        parent_data: Optional[Dict] = None
    ) -> Dict[str, str]:
        """
        Batch translate ruby-extracted character names.

        Returns:
            Dict mapping Japanese names to translated names
        """
        # Filter out kira-kira names (stylistic ruby, not real character names)
        real_names = [n for n in ruby_names if n.get("name_type") != "kirakira"]
        
        if len(real_names) < len(ruby_names):
            logger.info(f"Filtered out {len(ruby_names) - len(real_names)} kira-kira names (stylistic ruby)")
        
        # Filter out inherited entries
        inherited_names = parent_data.get("character_roster", {}) if parent_data else {}

        # Only translate NEW entries
        new_names = [n for n in real_names if n["kanji"] not in inherited_names]

        logger.info(f"Romanizing {len(new_names)} names")

        if not new_names:
            logger.info("No new names to translate (all inherited)")
            return inherited_names.copy()

        # Build batch translation prompt - language-specific
        if self.target_language == 'vn':
            # Vietnamese-specific name handling
            prompt_parts = [
                f"Translate the following character names from Japanese to {self.language_name}.",
                "Follow these rules:\n",
                "CHARACTER NAMES:",
                "1. Apply Hepburn romanization (keep Japanese pronunciation)",
                "2. Long vowel rules:",
                "   - For 'ou' sounds (こう, そう, etc.): KEEP both vowels (Kouki not Koki, Sousuke not Sosuke)",
                "   - For 'uu' sounds (ゆう, しゅう): Drop second 'u' (Yuki not Yuuki, Ryota not Ryouta)",
                "   - For 'ei' sounds: Use 'ei' (Kei not Kē)",
                "3. Surname-first order: Shinonome Sena not Sena Shinonome",
                "4. Match ruby reading exactly (東雲《しののめ》→ Shinonome, 康貴《こうき》→ Kouki)",
                "5. Keep romanized names (do not translate to Vietnamese equivalents)\n",
                "Output as JSON: {\"names\": {\"jp\": \"romanized\"}}\n"
            ]
        else:
            # English (default) name handling
            prompt_parts = [
                f"Translate the following character names from Japanese to {self.language_name}.",
                "Follow these rules:\n",
                "CHARACTER NAMES:",
                "1. Apply Hepburn romanization (natural English phonetics)",
                "2. Long vowel rules:",
                "   - For 'ou' sounds (こう, そう, etc.): KEEP both vowels (Kouki not Koki, Sousuke not Sosuke)",
                "   - For 'uu' sounds (ゆう, しゅう): Drop second 'u' (Yuki not Yuuki, Ryota not Ryouta)",
                "   - For 'ei' sounds: Use 'ei' (Kei not Kē)",
                "3. Surname-first order: Shinonome Sena not Sena Shinonome",
                "4. Match ruby reading exactly (東雲《しののめ》→ Shinonome, 康貴《こうき》→ Kouki)",
                "5. Consider character context for cultural adaptation\n",
                "Output as JSON: {\"names\": {\"jp\": \"en\"}}\n"
            ]
        
        # Add inherited context if present
        if inherited_names:
            prompt_parts.append("\nEXISTING CHARACTERS (maintain consistency):")
            for jp, en in list(inherited_names.items())[:10]:  # Show first 10
                prompt_parts.append(f"  {jp} → {en}")
            if len(inherited_names) > 10:
                prompt_parts.append(f"  ... and {len(inherited_names)-10} more")
        
        # Add new character names to translate
        prompt_parts.append("\nNEW CHARACTERS TO TRANSLATE:")
        for entry in new_names:
            kanji = entry["kanji"]
            ruby = entry["ruby"]
            context = entry["context"][:100]  # Truncate context
            prompt_parts.append(f"  {kanji}《{ruby}》")
            prompt_parts.append(f"    Context: \"{context}...\"")
        
        prompt = "\n".join(prompt_parts)
        
        # Call Gemini
        try:
            response = self.client.generate(
                prompt=prompt,
                temperature=0.2  # Low temp for consistency
            )
            
            # Parse response
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
            
            translations = json.loads(content)
            
            # Merge with inherited
            name_registry = {**inherited_names, **translations.get("names", {})}
            
            logger.info(f"✓ Translated {len(translations.get('names', {}))} character names")
            
            return name_registry
            
        except Exception as e:
            logger.error(f"Batch translation failed: {e}")
            # Fallback: return inherited only
            return inherited_names.copy()

    def _sync_bible_post_metadata(
        self,
        bible_sync=None,
        bible_pull=None,
    ) -> None:
        """Finalize Bible continuity after manifest write.

        Ensures sequel and non-sequel paths both:
        - resolve series bible
        - persist manifest.bible_id when detected
        - push/register current volume into bible index
        - emit continuity diff report
        """
        try:
            if bible_sync is None:
                from pipeline.metadata_processor.bible_sync import BibleSyncAgent
                from pipeline.config import PIPELINE_ROOT
                bible_sync = BibleSyncAgent(self.work_dir, PIPELINE_ROOT)

            if not getattr(bible_sync, "bible", None):
                if not bible_sync.resolve(self.manifest):
                    return

            if bible_sync.series_id and self.manifest.get("bible_id") != bible_sync.series_id:
                self.manifest["bible_id"] = bible_sync.series_id
                with open(self.manifest_path, "w", encoding="utf-8") as f:
                    json.dump(self.manifest, f, indent=2, ensure_ascii=False)
                logger.info(f"📖 Linked manifest to bible_id: {bible_sync.series_id}")

            push_result = bible_sync.push(self.manifest)
            logger.info(f"📖 Bible PUSH complete: {push_result.summary()}")

            try:
                bible_sync.generate_continuity_report(
                    self.manifest,
                    pull_result=bible_pull,
                    push_result=push_result,
                )
            except Exception as report_err:
                logger.warning(f"Continuity report generation failed: {report_err}")
        except Exception as e:
            logger.warning(f"Bible sync (post-metadata) failed: {e}")

    def _process_sequel_metadata_direct_copy(
        self,
        parent_data: Dict,
        original_metadata: Dict,
        chapter_titles: List[Dict]
    ) -> None:
        """
        FULL sequel mode: Direct copy metadata_en.json from prequel.
        Skips ALL name extraction, only translates NEW chapter titles.

        This is the most cost-effective approach for sequential volumes where:
        - Character roster is 100% inherited
        - No new characters introduced
        - Title/author remain consistent
        - Only chapter content is new

        Args:
            parent_data: Predecessor volume data (from detect_sequel_parent)
            original_metadata: Current volume's original metadata
            chapter_titles: Current volume's chapter titles
        """
        logger.info("="*70)
        logger.info("🔄 FULL SEQUEL MODE: Direct Metadata Copy")
        logger.info("="*70)

        predecessor_volume = parent_data.get('source_volume', 'Unknown')
        logger.info(f"📦 Source: {predecessor_volume}")

        # === STEP 1: Direct copy entire metadata_en.json structure ===
        metadata_translated = {
            'title_en': parent_data.get('title_en', ''),
            'author_en': parent_data.get('author_en', ''),
            'character_names': parent_data.get('character_roster', {}).copy(),
            'glossary': parent_data.get('glossary', {}).copy(),
            'character_profiles': parent_data.get('character_profiles', {}).copy(),
            'localization_notes': parent_data.get('localization_notes', {}).copy(),
            'inherited_from': predecessor_volume,
            'sequel_mode': 'direct_copy'
        }

        # Fix volume number in title using smart extraction
        import re
        current_jp_title = original_metadata.get('title', '')
        base_title = metadata_translated['title_en']

        # Extract volume number from current Japanese title using prioritized pattern matching
        current_vol_num = extract_volume_number(current_jp_title)

        if current_vol_num:
            # Update English title with current volume number
            vol_pattern = r'(\s+\d+|\s+[IVX]+|\s+Vol\.?\s+\d+|\s+Volume\s+\d+)$'
            if re.search(vol_pattern, base_title):
                metadata_translated['title_en'] = re.sub(vol_pattern, f' {current_vol_num}', base_title)
            else:
                metadata_translated['title_en'] = f"{base_title} {current_vol_num}"

            logger.info(f"  📝 Updated title: '{base_title}' → '{metadata_translated['title_en']}'")
        else:
            logger.info(f"  ℹ️  No volume number found in Japanese title, keeping: '{base_title}'")

        logger.info(f"  ✓ Title: {metadata_translated['title_en']}")
        logger.info(f"  ✓ Author: {metadata_translated['author_en']}")
        logger.info(f"  ✓ Character names: {len(metadata_translated['character_names'])} inherited")
        logger.info(f"  ✓ Glossary: {len(metadata_translated['glossary'])} terms inherited")

        # === STEP 2: Handle chapter titles (NEW only) ===
        predecessor_chapters = parent_data.get('chapters', [])
        predecessor_titles_jp = {ch['title_jp'] for ch in predecessor_chapters}

        new_chapter_titles = [
            ch for ch in chapter_titles
            if ch['title_jp'] not in predecessor_titles_jp
        ]

        # Copy matching chapter titles directly
        chapter_translations = {}
        for ch in chapter_titles:
            matching_pred = next(
                (p for p in predecessor_chapters if p['title_jp'] == ch['title_jp']),
                None
            )
            if matching_pred:
                chapter_translations[ch['id']] = matching_pred['title_en']
                logger.info(f"  ♻️  Chapter '{ch['id']}': Copied from predecessor")

        # Translate only NEW chapter titles
        if new_chapter_titles:
            logger.info(f"\n📝 Translating {len(new_chapter_titles)} NEW chapter titles...")

            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()

            # Simplified prompt: only chapter titles
            prompt = (
                f"Translate these chapter titles to {self.language_name}:\n\n"
                f"{json.dumps(new_chapter_titles, indent=2, ensure_ascii=False)}\n\n"
                f"Return JSON format: {{'chapters': [{{'id': 'XX', 'title_en': '...'}}]}}"
            )

            response = self.client.generate(
                prompt=prompt,
                system_instruction=system_prompt,
                temperature=0.3
            )

            try:
                content = response.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()

                result = json.loads(content)

                for ch in result.get('chapters', []):
                    chapter_translations[ch['id']] = ch['title_en']
                    logger.info(f"  ✨ Chapter '{ch['id']}': {ch['title_en']}")

                logger.info(f"  ✓ Translated {len(new_chapter_titles)} new chapters")

            except Exception as e:
                logger.error(f"  ✗ Chapter translation failed: {e}")
                # Fallback: use raw titles
                for ch in new_chapter_titles:
                    chapter_translations[ch['id']] = ch['title_jp']
        else:
            logger.info("  ✓ All chapter titles found in predecessor (0 new chapters)")

        metadata_translated['chapters'] = chapter_translations

        # === STEP 3: Save results ===
        metadata_translated['target_language'] = self.target_language
        metadata_translated['language_code'] = self.language_code

        output_filename = f"metadata_{self.target_language}.json"
        output_path = self.work_dir / output_filename

        # Sanitize JSON to fix any unescaped quotes from LLM output
        metadata_translated = sanitize_json_strings(metadata_translated)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_translated, f, indent=2, ensure_ascii=False)

        logger.info(f"\n💾 Saved to {output_path}")

        # Update manifest - PRESERVE v3 enhanced schema
        self._update_manifest_preserve_schema(
            title_en=metadata_translated["title_en"],
            author_en=metadata_translated["author_en"],
            chapters=metadata_translated["chapters"],
            character_names=metadata_translated["character_names"],
            glossary=metadata_translated.get("glossary", {}),
            extra_fields={"inherited_from": predecessor_volume, "sequel_mode": "direct_copy"}
        )

        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

        # Keep sequel flow in sync with bible registry and volume linking.
        self._sync_bible_post_metadata()

        logger.info("="*70)
        logger.info("✅ FULL SEQUEL MODE COMPLETE - Maximum API savings achieved!")
        logger.info(f"   • Inherited: {len(metadata_translated['character_names'])} names, "
                    f"{len(metadata_translated['glossary'])} terms")
        logger.info(f"   • New translations: {len(new_chapter_titles)} chapters only")
        logger.info(f"   • Name extraction: SKIPPED (100% inherited)")
        logger.info("="*70)

    def _process_sequel_metadata_optimized(
        self,
        parent_data: Dict,
        original_metadata: Dict,
        chapter_titles: List[Dict],
        ruby_names: List
    ) -> None:
        """
        Optimized sequel processing: Copy predecessor metadata directly,
        only translate NEW content (chapter titles, characters).
        
        Args:
            parent_data: Predecessor volume data (from detect_sequel_parent)
            original_metadata: Current volume's original metadata
            chapter_titles: Current volume's chapter titles
            ruby_names: Current volume's ruby-extracted names
        """
        logger.info("="*70)
        logger.info("🎯 SEQUEL OPTIMIZATION: Direct metadata inheritance")
        logger.info("="*70)
        
        predecessor_volume = parent_data.get('source_volume', 'Unknown')
        logger.info(f"📦 Inheriting from: {predecessor_volume}")
        
        # === STEP 1: Direct copy of inherited metadata ===
        # Fix volume number in title (e.g., "...Me 2" → "...Me 3")
        base_title = parent_data.get('title_en', '')
        current_jp_title = original_metadata.get('title', '')
        
        # Try to update volume number if present using smart extraction
        import re
        # Match patterns like "Vol 2", "Volume 2", "2", "II", etc. at end of title
        vol_pattern = r'(\s+\d+|\s+[IVX]+|\s+Vol\.?\s+\d+|\s+Volume\s+\d+)$'

        # Extract volume number from current Japanese title using prioritized pattern matching
        current_vol_num = extract_volume_number(current_jp_title)

        if current_vol_num:
            # Check if prequel has a volume number in its title
            prequel_has_vol_num = bool(re.search(vol_pattern, base_title))

            # Update English title with current volume number
            if prequel_has_vol_num:
                # Replace existing number (e.g., "Title 1" → "Title 2")
                updated_title = re.sub(vol_pattern, f' {current_vol_num}', base_title)
            else:
                # Prequel has no volume number - assume it's v1, append current volume number
                # e.g., "Title" (v1) → "Title 2" (for v2)
                updated_title = f"{base_title} {current_vol_num}"

            logger.info(f"  📝 Updated title: '{base_title}' → '{updated_title}'")
        else:
            updated_title = base_title
        
        metadata_translated = {
            'title_en': updated_title,
            'author_en': parent_data.get('author_en', ''),
            'character_names': parent_data.get('character_roster', {}).copy(),
            'glossary': parent_data.get('glossary', {}).copy(),
            'inherited_from': predecessor_volume,
            'optimization': 'sequel_direct_copy'
        }
        
        logger.info(f"  ✓ Title: {metadata_translated['title_en']}")
        logger.info(f"  ✓ Author: {metadata_translated['author_en']}")
        logger.info(f"  ✓ Character names: {len(metadata_translated['character_names'])} inherited")
        logger.info(f"  ✓ Glossary: {len(metadata_translated['glossary'])} terms inherited")
        
        # === STEP 2: Translate NEW chapter titles only ===
        predecessor_chapters = parent_data.get('chapters', [])
        predecessor_titles_jp = {ch['title_jp'] for ch in predecessor_chapters}
        
        new_chapter_titles = [
            ch for ch in chapter_titles 
            if ch['title_jp'] not in predecessor_titles_jp
        ]
        
        # Copy matching chapter titles directly
        chapter_translations = {}
        for ch in chapter_titles:
            # Check if this chapter title exists in predecessor
            matching_pred = next(
                (p for p in predecessor_chapters if p['title_jp'] == ch['title_jp']),
                None
            )
            if matching_pred:
                chapter_translations[ch['id']] = matching_pred['title_en']
                logger.info(f"  ♻️  Chapter '{ch['id']}': Copied from predecessor")
        
        # Translate only NEW chapter titles
        if new_chapter_titles:
            logger.info(f"\n📝 Translating {len(new_chapter_titles)} NEW chapter titles...")
            
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
            
            # Simplified prompt: only chapter titles
            prompt = (
                f"Translate these chapter titles to {self.language_name}:\n\n"
                f"{json.dumps(new_chapter_titles, indent=2, ensure_ascii=False)}\n\n"
                f"Return JSON format: {{'chapters': [{{'id': 'XX', 'title_en': '...'}}]}}"
            )
            
            response = self.client.generate(
                prompt=prompt,
                system_instruction=system_prompt,
                temperature=0.3
            )
            
            try:
                content = response.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()
                
                result = json.loads(content)
                
                for ch in result.get('chapters', []):
                    chapter_translations[ch['id']] = ch['title_en']
                    logger.info(f"  ✨ Chapter '{ch['id']}': {ch['title_en']}")
                
                logger.info(f"  ✓ Translated {len(new_chapter_titles)} new chapters")
                
            except Exception as e:
                logger.error(f"  ✗ Chapter translation failed: {e}")
                # Fallback: copy from original metadata or use raw titles
                for ch in new_chapter_titles:
                    chapter_translations[ch['id']] = ch['title_jp']
        else:
            logger.info("  ✓ All chapter titles found in predecessor (0 new chapters)")
        
        metadata_translated['chapters'] = chapter_translations
        
        # === STEP 3: Handle NEW character names ===
        inherited_char_keys = set(metadata_translated['character_names'].keys())
        new_ruby_names = [
            name for name in ruby_names 
            if name.get('kanji', '') not in inherited_char_keys
        ]
        
        if new_ruby_names:
            logger.info(f"\n👥 Translating {len(new_ruby_names)} NEW character names...")
            
            # Use existing batch translate logic
            new_name_registry = self._batch_translate_ruby(
                new_ruby_names, 
                parent_data  # Pass parent data for context
            )
            
            # Merge new names with inherited
            metadata_translated['character_names'].update(new_name_registry)
            logger.info(f"  ✓ Added {len(new_name_registry)} new character names")
        else:
            logger.info("  ✓ All character names found in predecessor (0 new names)")
        
        # === STEP 4: Save results ===
        metadata_translated['target_language'] = self.target_language
        metadata_translated['language_code'] = self.language_code
        
        output_filename = f"metadata_{self.target_language}.json"
        output_path = self.work_dir / output_filename

        # Sanitize JSON to fix any unescaped quotes from LLM output
        metadata_translated = sanitize_json_strings(metadata_translated)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_translated, f, indent=2, ensure_ascii=False)

        logger.info(f"\n💾 Saved to {output_path}")
        
        # Save name registry to .context
        context_dir = self.work_dir / ".context"
        context_dir.mkdir(exist_ok=True)
        
        name_registry = metadata_translated['character_names']
        # NOTE: name_registry.json DEPRECATED - v3 schema uses manifest.json character_profiles
        # Legacy .context/name_registry.json no longer created
        
        # Update manifest - PRESERVE v3 enhanced schema
        self._update_manifest_preserve_schema(
            title_en=metadata_translated["title_en"],
            author_en=metadata_translated["author_en"],
            chapters=metadata_translated["chapters"],
            character_names=name_registry,
            glossary=metadata_translated.get("glossary", {}),
            extra_fields={"inherited_from": predecessor_volume}
        )
        
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

        # Keep sequel flow in sync with bible registry and volume linking.
        self._sync_bible_post_metadata()

        logger.info("="*70)
        logger.info("✅ SEQUEL OPTIMIZATION COMPLETE - API calls minimized!")
        logger.info(f"   • Inherited: {len(parent_data.get('character_roster', {}))} names, "
                    f"{len(parent_data.get('glossary', {}))} terms")
        logger.info(f"   • New translations: {len(new_chapter_titles)} chapters, "
                    f"{len(new_ruby_names)} names")
        logger.info("="*70)

    def process_metadata(self, ignore_sequel: bool = False, sequel_mode: bool = False):
        """Translate metadata and save to metadata_en.json.

        Args:
            ignore_sequel: If True, ignore sequel detection and process as independent volume
            sequel_mode: If True, enable full sequel mode (direct metadata copy, skip name extraction)
        """
        logger.info(f"Processing metadata for {self.work_dir.name}")

        # Prepare context for LLM
        original_metadata = self.manifest.get("metadata", {})

        # Pre-process chapter titles: standardize format BEFORE translation
        raw_chapters = self.manifest.get("chapters", [])
        chapter_titles = []

        for c in raw_chapters:
            original_title = c["title"]
            standardized_title = standardize_chapter_title(original_title, self.target_language)

            # Log standardization if changed
            if standardized_title != original_title:
                logger.info(f"📝 Standardized: '{original_title}' → '{standardized_title}'")

            chapter_titles.append({
                "id": c["id"],
                "title_jp": standardized_title  # Use standardized version for translation
            })

        # Get ruby-extracted character names (skip in sequel_mode)
        ruby_names = []
        if not sequel_mode:
            ruby_names = self._ensure_ruby_names()
        else:
            logger.info("🔄 SEQUEL MODE: Skipping ruby name extraction (will inherit from prequel)")

        # Check for sequel inheritance
        parent_data = None
        if not ignore_sequel:
            parent_data = self.detect_sequel_parent()

        # === NEW OPTIMIZATION: Direct inheritance for sequels ===
        if parent_data:
            if sequel_mode:
                logger.info("🚀 FULL SEQUEL MODE ACTIVE - Direct metadata copy from prequel")
                return self._process_sequel_metadata_direct_copy(
                    parent_data,
                    original_metadata,
                    chapter_titles
                )
            else:
                logger.info("🚀 SEQUEL OPTIMIZATION ACTIVE - Skipping API for inherited data")
                return self._process_sequel_metadata_optimized(
                    parent_data,
                    original_metadata,
                    chapter_titles,
                    ruby_names
                )

        # New flow:
        # Librarian Extraction -> Schema Agent autoupdate -> Bible Sync -> Title/Chapter translation -> Phase 2
        self._run_schema_autoupdate()

        # ── Bible Auto-Sync: PULL (Bible → Manifest) ─────────────
        # Inherit canonical terms from the series bible BEFORE ruby
        # translation, so batch_translate_ruby can skip known names.
        bible_sync = None
        bible_pull = None
        bible_known_names = {}
        try:
            from pipeline.metadata_processor.bible_sync import BibleSyncAgent
            from pipeline.config import PIPELINE_ROOT
            bible_sync = BibleSyncAgent(self.work_dir, PIPELINE_ROOT)
            if bible_sync.resolve(self.manifest):
                if bible_sync.series_id and self.manifest.get("bible_id") != bible_sync.series_id:
                    self.manifest["bible_id"] = bible_sync.series_id
                    # Persist immediately so bible linkage survives mid-phase failures.
                    with open(self.manifest_path, "w", encoding="utf-8") as f:
                        json.dump(self.manifest, f, indent=2, ensure_ascii=False)
                    logger.info(f"📖 Linked manifest to bible_id: {bible_sync.series_id}")
                bible_pull = bible_sync.pull(self.manifest)
                bible_known_names = bible_pull.known_characters
                logger.info(f"📖 Bible PULL complete: {bible_pull.summary()}")
        except Exception as e:
            logger.warning(f"Bible sync (pull) skipped: {e}")
            bible_sync = None

        inheritance_context = ""

        # Append bible context block if available
        if bible_pull and bible_pull.context_block:
            inheritance_context += bible_pull.context_block

        if parent_data:
            match_title = parent_data.get('title_en', 'Unknown')
            match_author = parent_data.get('author_en', 'Unknown')
            character_roster = parent_data.get('character_roster', {})
            glossary = parent_data.get('glossary', {})
            
            logger.info(f"✨ Sequel Detected! Inheriting context from: {match_title}")
            logger.info(f"   Characters: {len(character_roster)}, Glossary terms: {len(glossary)}")
            
            # Build comprehensive inheritance context
            context_parts = [
                "\n" + "="*60,
                "IMPORTANT - SEQUEL INHERITANCE (MAINTAIN CONSISTENCY)",
                "="*60,
                f"\nSeries Title: {match_title}",
                f"Author Name: {match_author}\n"
            ]
            
            # Add character roster
            if character_roster:
                context_parts.append("\nCHARACTER ROSTER (use these exact spellings):")
                for jp_name, en_name in character_roster.items():
                    context_parts.append(f"  {jp_name} → {en_name}")
                context_parts.append("")
            
            # Add glossary terms
            if glossary:
                context_parts.append("GLOSSARY (established terminology):")
                for jp_term, en_term in glossary.items():
                    context_parts.append(f"  {jp_term} → {en_term}")
                context_parts.append("")
            
            context_parts.append("="*60)
            context_parts.append("Ensure all character names and terms above remain consistent.")
            context_parts.append("Only translate NEW characters/terms not listed above.\n")
            
            inheritance_context += "\n".join(context_parts)
        
        # Batch translate ruby-extracted character names
        # Pre-populate with bible known names so they can be skipped
        if bible_known_names:
            name_registry = dict(bible_known_names)  # Bible as base
            logger.info(f"   Pre-populated {len(bible_known_names)} bible character names → ruby skip list")
        else:
            name_registry = {}

        if ruby_names:
            logger.info("Batch translating ruby entries...")
            ruby_translated = self._batch_translate_ruby(
                ruby_names, parent_data
            )
            # Merge: ruby translated names override bible (for newly discovered chars)
            name_registry.update(ruby_translated)
        # else: name_registry already has bible names (or empty dict)
        
        # No term glossary in simplified version
        term_glossary = {}
        
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
            
        prompt = (
            f"Original Metadata:\n{json.dumps(original_metadata, indent=2, ensure_ascii=False)}\n\n"
            f"Chapter Titles:\n{json.dumps(chapter_titles, indent=2, ensure_ascii=False)}"
            f"{inheritance_context}"
        )
        
        response = self.client.generate(
            prompt=prompt,
            system_instruction=system_prompt,
            temperature=0.3 # Lower temperature for metadata reliability
        )
        
        try:
            # Clean response if it contains markdown code blocks
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()

            metadata_translated = json.loads(content)

            # Prefer official localization metadata from schema autoupdate when available.
            metadata_translated = self._apply_official_localization_overrides(metadata_translated)

            # Add character names and glossary to metadata
            if name_registry:
                metadata_translated['character_names'] = name_registry
            if term_glossary:
                metadata_translated['glossary'] = term_glossary

            # Add language metadata
            metadata_translated['target_language'] = self.target_language
            metadata_translated['language_code'] = self.language_code

            # Save to language-specific metadata file (e.g., metadata_en.json, metadata_vn.json)
            output_filename = f"metadata_{self.target_language}.json"
            output_path = self.work_dir / output_filename

            # Sanitize JSON to fix any unescaped quotes from LLM output
            metadata_translated = sanitize_json_strings(metadata_translated)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(metadata_translated, f, indent=2, ensure_ascii=False)

            logger.info(f"Metadata translated to {self.language_name} and saved to {output_path}")

            # Save glossary to manifest (v3 schema)
            context_dir = self.work_dir / ".context"
            context_dir.mkdir(exist_ok=True)

            # NOTE: name_registry.json DEPRECATED - v3 schema uses manifest.json character_profiles
            # Character names now stored in manifest.json metadata_en.character_names

            if term_glossary:
                # Update manifest glossary
                if "glossary" not in self.manifest:
                    self.manifest["glossary"] = {}
                self.manifest["glossary"].update(term_glossary)
                logger.info(f"Added {len(term_glossary)} terms to glossary")

            # Extract chapter translations to dict format
            chapter_translations = {}
            for ch in metadata_translated.get("chapters", []):
                ch_id = ch.get("id", "")
                ch_title = ch.get("title_en", ch.get(f"title_{self.target_language}", ""))
                if ch_id and ch_title:
                    chapter_translations[ch_id] = ch_title

            # Update manifest - PRESERVE v3 enhanced schema
            self._update_manifest_preserve_schema(
                title_en=metadata_translated.get("title_en", ""),
                author_en=metadata_translated.get("author_en", ""),
                chapters=chapter_translations,
                character_names=name_registry,
                glossary=term_glossary
            )

            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump(self.manifest, f, indent=2, ensure_ascii=False)

            # ── Bible Auto-Sync: PUSH (Manifest → Bible) ─────────
            # Export newly discovered terms and register volume.
            self._sync_bible_post_metadata(bible_sync=bible_sync, bible_pull=bible_pull)

        except Exception as e:
            logger.error(f"Failed to parse metadata response: {e}")
            logger.error(f"Response content: {response.content}")
            raise

def main():
    parser = argparse.ArgumentParser(description="Run Metadata Processor Agent")
    parser.add_argument("--volume", type=str, required=True, help="Volume ID (directory name in WORK)")
    parser.add_argument("--ignore-sequel", action="store_true", help="Ignore sequel detection")
    parser.add_argument("--sequel-mode", action="store_true",
                        help="Enable full sequel mode: copy metadata_en.json directly, skip name extraction")

    args = parser.parse_args()

    from pipeline.config import WORK_DIR
    volume_dir = WORK_DIR / args.volume

    if not volume_dir.exists():
        logger.error(f"Volume directory not found: {volume_dir}")
        sys.exit(1)

    processor = MetadataProcessor(volume_dir)
    processor.process_metadata(ignore_sequel=args.ignore_sequel, sequel_mode=args.sequel_mode)

if __name__ == "__main__":
    main()
