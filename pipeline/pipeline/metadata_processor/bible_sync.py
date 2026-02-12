"""
Bible Auto-Sync Agent (Phase 1.5)
==================================

Two-way sync between series bible and volume manifest during
metadata processing. Runs BEFORE the Translator (Phase 2) starts,
ensuring canonical data is always up-to-date.

PULL (Bible → Manifest):
    Inherit known canonical terms into the current volume's metadata.
    Runs after SchemaAutoUpdater, before batch_translate_ruby.
    Effect: batch_translate_ruby can skip already-known names,
            inheritance_context includes bible canon.

PUSH (Manifest → Bible):
    Export newly discovered terms from manifest back to bible.
    Runs after final manifest write.
    Effect: Next volume in the series inherits these discoveries.

Usage in MetadataProcessor.process_metadata():
    sync = BibleSyncAgent(self.work_dir, PIPELINE_ROOT)
    if sync.resolve(self.manifest):
        pull_result = sync.pull(self.manifest)
        # ... use pull_result.known_names in batch_translate_ruby ...
        # ... use pull_result.context_block in inheritance_context ...
        # ... after final write ...
        push_result = sync.push(self.manifest)
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("BibleSync")


# ═══════════════════════════════════════════════════════════════════
#  Result Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BiblePullResult:
    """Result of pulling canonical terms from bible → manifest."""

    # JP→EN dict of ALL bible terms (flat glossary)
    known_terms: Dict[str, str] = field(default_factory=dict)

    # JP→EN dict of character names only (for batch_translate_ruby skip)
    known_characters: Dict[str, str] = field(default_factory=dict)

    # Context block for injection into Gemini prompt
    context_block: str = ""

    # Pull-override log: manifest terms that override bible terms
    overrides: List[str] = field(default_factory=list)

    # Stats
    characters_inherited: int = 0
    geography_inherited: int = 0
    weapons_inherited: int = 0
    other_inherited: int = 0

    @property
    def total_inherited(self) -> int:
        return (self.characters_inherited + self.geography_inherited
                + self.weapons_inherited + self.other_inherited)

    def summary(self) -> str:
        parts = []
        if self.characters_inherited:
            parts.append(f"characters={self.characters_inherited}")
        if self.geography_inherited:
            parts.append(f"geography={self.geography_inherited}")
        if self.weapons_inherited:
            parts.append(f"weapons={self.weapons_inherited}")
        if self.other_inherited:
            parts.append(f"other={self.other_inherited}")
        return f"PULL: {self.total_inherited} terms ({', '.join(parts)})" if parts else "PULL: 0 terms"


@dataclass
class BiblePushResult:
    """Result of pushing manifest discoveries → bible."""

    # New entries added to bible
    characters_added: int = 0
    characters_enriched: int = 0
    characters_skipped: int = 0

    # Conflict log (manifest disagrees with bible)
    conflicts: List[str] = field(default_factory=list)

    # Volume registration
    volume_registered: bool = False

    @property
    def total_changes(self) -> int:
        return self.characters_added + self.characters_enriched

    def summary(self) -> str:
        parts = [f"added={self.characters_added}",
                 f"enriched={self.characters_enriched}",
                 f"skipped={self.characters_skipped}"]
        if self.conflicts:
            parts.append(f"conflicts={len(self.conflicts)}")
        if self.volume_registered:
            parts.append("volume=registered")
        return f"PUSH: {', '.join(parts)}"


# ═══════════════════════════════════════════════════════════════════
#  BibleSyncAgent
# ═══════════════════════════════════════════════════════════════════

class BibleSyncAgent:
    """Two-way sync between series bible and Phase 1.5 metadata.

    Lifecycle:
        1. resolve(manifest)  — find the bible for this volume
        2. pull(manifest)     — inherit bible → manifest context
        3. (... Phase 1.5 processing happens ...)
        4. push(manifest)     — export discoveries → bible
    """

    def __init__(self, work_dir: Path, pipeline_root: Path):
        self.work_dir = work_dir
        self.pipeline_root = pipeline_root

        # Lazy import to avoid circular dependencies
        from pipeline.translator.series_bible import BibleController
        self.bible_ctrl = BibleController(pipeline_root)
        self.bible = None          # type: Optional[Any]  # SeriesBible
        self.series_id = None      # type: Optional[str]

    # ── Resolution ───────────────────────────────────────────────

    def resolve(self, manifest: dict) -> bool:
        """Resolve a bible for this manifest.

        Checks bible_id, volume_id, series metadata, and fuzzy match.
        Returns True if a bible was found (or bootstrapped) and loaded.
        """
        try:
            bible = self.bible_ctrl.load(manifest, self.work_dir)
            if bible:
                self.bible = bible
                self.series_id = bible.series_id
                logger.info(f"📖 Bible resolved: {self.series_id} "
                            f"({bible.entry_count()} entries)")
                return True
        except Exception as e:
            logger.warning(f"Bible resolution failed: {e}")

        # Auto-bootstrap flow:
        # For a brand-new series with no pre-existing bible, seed a new bible
        # from the current (base) manifest so this run and all subsequent runs
        # stay on the same continuity source of truth.
        if self._bootstrap_from_manifest(manifest):
            return True

        logger.info("📖 No bible found for this volume — sync skipped")
        return False

    def _bootstrap_from_manifest(self, manifest: dict) -> bool:
        """Create/seed a new bible from the current manifest when missing."""
        seed = self._derive_bootstrap_seed(manifest)
        if not seed:
            return False

        series_id = seed["series_id"]
        series_title = seed["series_title"]
        match_patterns = seed["match_patterns"]
        world_setting = seed["world_setting"]

        # If entry already exists but wasn't resolved earlier, try direct load once.
        # This handles stale pattern/volume links while preserving existing canon data.
        if self.bible_ctrl.index.get("series", {}).get(series_id):
            try:
                bible = self.bible_ctrl.get_bible(series_id)
                if bible:
                    self.bible = bible
                    self.series_id = series_id
                    manifest["bible_id"] = series_id
                    logger.info(
                        f"📖 Bible bootstrap recovered existing series: {series_id} "
                        f"({bible.entry_count()} entries)"
                    )
                    return True
            except Exception as e:
                logger.warning(f"Existing bible entry for {series_id} could not be loaded: {e}")

        try:
            self.bible_ctrl.create_bible(
                series_id=series_id,
                series_title=series_title,
                match_patterns=match_patterns,
                world_setting=world_setting,
            )
            logger.info(
                f"📖 Auto-created new bible: {series_id} "
                f"(patterns={len(match_patterns)})"
            )
        except FileExistsError:
            # Race-safe fallback: file appeared after checks.
            pass
        except Exception as e:
            logger.warning(f"Bible bootstrap create failed for {series_id}: {e}")
            return False

        try:
            summary = self.bible_ctrl.import_from_manifest(manifest, series_id)
            logger.info(f"📖 Seeded bible from base manifest: {summary}")
        except Exception as e:
            logger.warning(f"Bible bootstrap import failed for {series_id}: {e}")

        try:
            bible = self.bible_ctrl.get_bible(series_id)
        except Exception as e:
            logger.warning(f"Bible bootstrap load failed for {series_id}: {e}")
            return False

        if not bible:
            return False

        self.bible = bible
        self.series_id = series_id
        manifest["bible_id"] = series_id
        logger.info(
            f"📖 Bible bootstrapped: {series_id} "
            f"({bible.entry_count()} entries, volumes={len(bible.volumes_registered)})"
        )
        return True

    def _derive_bootstrap_seed(self, manifest: dict) -> Optional[Dict[str, Any]]:
        """Derive minimal deterministic bible seed data from a volume manifest."""
        if not isinstance(manifest, dict):
            return None

        metadata = manifest.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata_en = manifest.get("metadata_en", {})
        if not isinstance(metadata_en, dict):
            metadata_en = {}

        explicit_bible_id = str(manifest.get("bible_id", "") or "").strip()
        volume_id = str(manifest.get("volume_id", "") or "").strip()

        series_raw = metadata.get("series", "")
        series_ja = ""
        series_en = ""
        series_base = ""
        if isinstance(series_raw, dict):
            # Common variants:
            # 1) {"ja": "...", "en": "..."}
            # 2) {"title": "...", "title_english": "..."}
            # 3) {"title": {"japanese": "...", "english": "...", ...}, ...}
            series_ja = str(
                series_raw.get("ja", "")
                or series_raw.get("japanese", "")
                or ""
            ).strip()
            series_en = str(
                series_raw.get("en", "")
                or series_raw.get("english", "")
                or series_raw.get("title_english", "")
                or ""
            ).strip()

            series_title_block = series_raw.get("title", "")
            if isinstance(series_title_block, dict):
                series_ja = series_ja or str(
                    series_title_block.get("ja", "")
                    or series_title_block.get("japanese", "")
                    or ""
                ).strip()
                series_en = series_en or str(
                    series_title_block.get("en", "")
                    or series_title_block.get("english", "")
                    or ""
                ).strip()
            elif isinstance(series_title_block, str):
                series_ja = series_ja or series_title_block.strip()

            series_base = series_en or series_ja
        else:
            series_base = str(series_raw or "").strip()
            series_ja = series_base
            series_en = ""

        title_ja = str(metadata.get("title", "") or "").strip()
        title_sort_ja = str(metadata.get("title_sort", "") or "").strip()
        title_en = str(metadata_en.get("title_en", "") or metadata.get("title_en", "") or "").strip()
        series_title_en = str(
            metadata_en.get("series_title_en", "")
            or metadata_en.get("series_en", "")
            or series_en
            or ""
        ).strip()
        source_epub = str(metadata.get("source_epub", "") or "").strip()
        source_epub_stem = ""
        if source_epub:
            try:
                source_epub_stem = Path(source_epub).stem.replace("_", " ").strip()
            except Exception:
                source_epub_stem = ""

        canonical_series_ja = self._strip_volume_suffix(series_ja)
        canonical_series_en = self._strip_volume_suffix(series_title_en or series_en)
        canonical_series_title_sort = self._strip_volume_suffix(title_sort_ja)
        canonical_series_epub_stem = self._strip_volume_suffix(source_epub_stem)
        canonical_title_ja = self._strip_volume_suffix(title_ja)
        canonical_title_en = self._strip_volume_suffix(title_en)

        base_name = (
            explicit_bible_id
            # OPF and librarian-derived canonical fields (highest priority)
            or canonical_series_ja
            or canonical_series_en
            or canonical_series_title_sort
            or canonical_series_epub_stem
            # Fallbacks
            or canonical_title_ja
            or canonical_title_en
        )
        if not base_name:
            return None

        if explicit_bible_id:
            series_id = explicit_bible_id
        else:
            series_id = self._build_series_id(base_name, volume_id)

        series_title = {
            "ja": canonical_series_ja or canonical_series_en or base_name,
            "en": canonical_series_en or canonical_series_ja or base_name,
            "romaji": "",
        }

        match_patterns: List[str] = []
        for candidate in [
            canonical_series_ja,
            canonical_series_en,
            canonical_series_title_sort,
            canonical_series_epub_stem,
            canonical_title_ja,
            canonical_title_en,
            series_base,
            source_epub_stem,
        ]:
            text = str(candidate or "").strip()
            if text and text not in match_patterns:
                match_patterns.append(text)
        if not match_patterns:
            match_patterns = [base_name]

        world_setting = {}
        ws = metadata_en.get("world_setting", {})
        if isinstance(ws, dict):
            world_setting = ws

        return {
            "series_id": series_id,
            "series_title": series_title,
            "match_patterns": match_patterns,
            "world_setting": world_setting,
        }

    def _build_series_id(self, base_name: str, volume_id: str) -> str:
        """Build a deterministic series_id from series/title text."""
        normalized = re.sub(r"\s+", " ", str(base_name).strip().lower())
        ascii_slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        if ascii_slug:
            return ascii_slug[:80]

        # For non-ASCII titles, generate stable ID from content hash so
        # all volumes in the same series resolve to the same bible_id.
        if normalized:
            digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
            return f"series_{digest}"

        fallback = self.bible_ctrl._extract_short_id(volume_id) or "unknown"
        return f"series_{fallback}"

    def _strip_volume_suffix(self, text: str) -> str:
        """Best-effort removal of trailing volume markers for stable series matching."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        patterns = [
            r"\s*(?:Vol(?:ume)?\.?|VOL\.?)\s*[0-9０-９]+$",
            r"\s*(?:Lv\.?|LV\.?|level)\s*[0-9０-９]+$",
            r"\s*[Vv]\s*[0-9０-９]+$",
            r"\s*第\s*[0-9０-９一二三四五六七八九十百千]+(?:巻|話|章)$",
            r"\s*[0-9０-９]+$",
            r"\s*[（(][0-9０-９]+[）)]$",
        ]
        for pat in patterns:
            cleaned = re.sub(pat, "", cleaned).strip()
        return cleaned

    # ── PULL: Bible → Manifest ───────────────────────────────────

    def pull(self, manifest: dict) -> BiblePullResult:
        """Pull canonical terms from bible for use in metadata processing.

        Called AFTER _run_schema_autoupdate() but BEFORE _batch_translate_ruby().

        Returns:
            BiblePullResult with known terms, known characters, and
            a formatted context block for Gemini prompt injection.
        """
        if not self.bible:
            return BiblePullResult()

        result = BiblePullResult()

        # 1. Extract category-specific glossaries
        result.known_characters = self.bible.characters_glossary()
        result.characters_inherited = len(result.known_characters)

        geo_glossary = self.bible.geography_glossary()
        result.geography_inherited = len(geo_glossary)

        weapons_glossary = self.bible.weapons_glossary()
        result.weapons_inherited = len(weapons_glossary)

        cultural_glossary = self.bible.cultural_glossary()
        result.other_inherited = len(cultural_glossary)

        # 2. Flat glossary = union of all
        result.known_terms = self.bible.flat_glossary()

        # 3. Build context block for Gemini inheritance prompt
        result.context_block = self._build_pull_context()

        # 4. Inject bible character names into manifest's character_names
        #    Bible terms serve as base — existing manifest terms override
        metadata_en = manifest.get('metadata_en', {})
        existing_names = metadata_en.get('character_names', {})

        # Bible as base, manifest values override (manifest may have
        # volume-specific new characters that aren't in bible yet)
        merged_names = dict(result.known_characters)  # bible base

        # Log individual pull overrides where manifest disagrees with bible
        for jp, manifest_en in existing_names.items():
            bible_en = result.known_characters.get(jp)
            if bible_en and bible_en.lower() != manifest_en.lower():
                result.overrides.append(
                    f"  {jp}: bible='{bible_en}' → manifest='{manifest_en}' (manifest kept)"
                )

        merged_names.update(existing_names)             # manifest overrides
        metadata_en['character_names'] = merged_names
        manifest['metadata_en'] = metadata_en

        injected = len(merged_names) - len(existing_names)
        if injected > 0:
            logger.info(f"   Injected {injected} bible character names "
                        f"into manifest (total: {len(merged_names)})")

        if result.overrides:
            logger.warning(f"⚠️  {len(result.overrides)} pull override(s) (manifest kept over bible):")
            for o in result.overrides:
                logger.warning(o)

        logger.info(f"   {result.summary()}")
        return result

    def _build_pull_context(self) -> str:
        """Build a formatted context block from bible for Gemini prompts.

        This gets appended to the sequel inheritance context so
        batch_translate_ruby and title translation respect bible canon.
        """
        if not self.bible:
            return ""

        lines = [
            "",
            "=" * 60,
            "SERIES BIBLE — CANONICAL TERMS (USE EXACT SPELLINGS)",
            "=" * 60,
            ""
        ]

        # Characters
        chars = self.bible.get_all_characters()
        if chars:
            lines.append("CHARACTER NAMES (bible canon — use these EXACT spellings):")
            for jp_name, char_data in chars.items():
                if isinstance(char_data, dict):
                    en = char_data.get('canonical_en', '')
                    short = char_data.get('short_name', '')
                    suffix = f" (short: {short})" if short and short != en else ""
                    lines.append(f"  {jp_name} → {en}{suffix}")
            lines.append("")

        # Geography
        geo = self.bible.data.get('geography', {})
        geo_entries = []
        for sub in ('countries', 'regions', 'cities'):
            for jp, data in geo.get(sub, {}).items():
                if isinstance(data, dict) and data.get('canonical_en'):
                    geo_entries.append(f"  {jp} → {data['canonical_en']}")
        if geo_entries:
            lines.append("GEOGRAPHY (bible canon):")
            lines.extend(geo_entries)
            lines.append("")

        # Weapons/Artifacts
        weapons = self.bible.data.get('weapons_artifacts', {})
        weapon_entries = []
        for sub_cat, items in weapons.items():
            if isinstance(items, dict):
                for jp, data in items.items():
                    if isinstance(data, dict) and data.get('canonical_en'):
                        weapon_entries.append(f"  {jp} → {data['canonical_en']}")
        if weapon_entries:
            lines.append("WEAPONS & ARTIFACTS (bible canon):")
            lines.extend(weapon_entries)
            lines.append("")

        # Cultural + Organizations + Mythology (combined)
        misc_entries = []
        for cat in ('organizations', 'cultural_terms', 'mythology'):
            for jp, data in self.bible.data.get(cat, {}).items():
                if isinstance(data, dict) and data.get('canonical_en'):
                    misc_entries.append(f"  {jp} → {data['canonical_en']}")
        if misc_entries:
            lines.append("TERMINOLOGY (bible canon):")
            lines.extend(misc_entries)
            lines.append("")

        lines.append("=" * 60)
        lines.append("Any term above MUST use the exact spelling shown.")
        lines.append("Only translate NEW terms not listed above.\n")

        return "\n".join(lines)

    # ── PUSH: Manifest → Bible ───────────────────────────────────

    def push(self, manifest: dict) -> BiblePushResult:
        """Push newly discovered terms from manifest back to the bible.

        Called AFTER the final manifest write. Compares the manifest's
        finalized character_names against the bible and adds new entries.

        Args:
            manifest: The fully processed manifest dict

        Returns:
            BiblePushResult with counts and conflict log
        """
        if not self.bible:
            return BiblePushResult()

        result = BiblePushResult()
        metadata_en = manifest.get('metadata_en', {})

        # ── Push character names ─────────────────────────────────
        # Primary source: metadata_en.character_names
        # Fallback source: metadata_en.character_profiles (v3 flow may keep character_names empty)
        char_names = metadata_en.get('character_names', {})
        if not isinstance(char_names, dict):
            char_names = {}
        profiles = metadata_en.get('character_profiles', {})
        if not isinstance(profiles, dict):
            profiles = {}

        derived_names: Dict[str, str] = {}
        for profile_key, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue
            full_name = str(profile_data.get('full_name', '')).strip()
            if not full_name:
                continue

            jp_name = None
            if re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', profile_key):
                jp_name = profile_key
            else:
                ruby_base = str(profile_data.get('ruby_base', '')).strip()
                if ruby_base and re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', ruby_base):
                    jp_name = ruby_base

            if not jp_name or jp_name in char_names:
                continue
            derived_names[jp_name] = full_name

        if derived_names:
            logger.info(
                f"   Derived {len(derived_names)} character names from character_profiles "
                "(character_names fallback)."
            )

        combined_char_names = dict(char_names)
        combined_char_names.update(derived_names)

        for jp_name, en_name in combined_char_names.items():
            if not isinstance(en_name, str) or not en_name.strip():
                continue

            existing = self.bible.get_character(jp_name)
            if existing:
                # Already in bible — check for conflict
                bible_en = existing.get('canonical_en', '')
                if bible_en and bible_en.lower() != en_name.lower():
                    # Conflict: manifest says X, bible says Y
                    # Bible wins (canonical), log the conflict
                    result.conflicts.append(
                        f"  {jp_name}: manifest='{en_name}' vs bible='{bible_en}' → bible kept"
                    )
                result.characters_skipped += 1
            else:
                # New character — add to bible
                self.bible.add_entry('characters', jp_name, {
                    'canonical_en': en_name,
                    'source': (
                        'phase1.5_auto_sync_profiles'
                        if jp_name in derived_names
                        else 'phase1.5_auto_sync'
                    ),
                    'discovered_in': manifest.get('volume_id', ''),
                })
                result.characters_added += 1
                logger.debug(f"   New character: {jp_name} → {en_name}")

        # ── Enrich with character_profiles ───────────────────────
        for profile_key, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue

            # Find the corresponding bible entry
            jp_key = self._resolve_profile_key(profile_key, profile_data)
            if not jp_key:
                continue

            existing = self.bible.get_character(jp_key)
            if not existing:
                continue  # Not in bible, nothing to enrich

            # Build enrichment dict from profile
            enrichments = self._extract_enrichments(profile_data)
            if enrichments:
                self.bible.add_entry('characters', jp_key, enrichments)
                result.characters_enriched += 1

        # ── Register volume ──────────────────────────────────────
        volume_id = manifest.get('volume_id', '')
        if volume_id:
            short_id = self.bible_ctrl._extract_short_id(volume_id)
            title = manifest.get('metadata', {}).get('title', '')

            # Register in bible
            from pipeline.metadata_processor.agent import extract_volume_number
            idx = extract_volume_number(title) or len(self.bible.volumes_registered) + 1
            self.bible.register_volume(
                volume_id=short_id or volume_id,
                title=title,
                index=idx
            )

            # Also link in index
            if short_id:
                self.bible_ctrl.link_volume(volume_id, self.series_id)

            result.volume_registered = True

        # ── Save & report ────────────────────────────────────────
        if result.total_changes > 0 or result.volume_registered:
            self.bible.save()
            # Update index entry count
            entry = self.bible_ctrl.index.get('series', {}).get(self.series_id, {})
            entry['entry_count'] = self.bible.entry_count()
            self.bible_ctrl._save_index()
            logger.info(f"📖 Bible updated: {self.series_id}")

        if result.conflicts:
            logger.warning(f"⚠️  {len(result.conflicts)} name conflict(s) detected (bible kept):")
            for c in result.conflicts:
                logger.warning(c)

        logger.info(f"   {result.summary()}")
        return result

    # ── Helpers ───────────────────────────────────────────────────

    def _resolve_profile_key(
        self, profile_key: str, profile_data: dict
    ) -> Optional[str]:
        """Map a character_profiles key to a JP name in the bible.

        Profiles may use JP keys (V2) or English keys (V1).
        """
        # If key is JP (contains CJK characters), use directly
        if re.search(r'[\u3040-\u9fff]', profile_key):
            return profile_key

        # English key (V1 format) — try to match via canonical_en
        en_name = profile_data.get('full_name',
                                   profile_key.replace('_', ' '))
        for jp, char in self.bible.data.get('characters', {}).items():
            if isinstance(char, dict):
                if char.get('canonical_en', '').lower() == en_name.lower():
                    return jp
        return None

    def _extract_visual_identity_non_color(self, profile_data: dict) -> Dict[str, Any]:
        """Extract normalized non-color visual identity payload from a profile."""
        identity = profile_data.get("visual_identity_non_color")

        if isinstance(identity, str) and identity.strip():
            return {"identity_summary": identity.strip()}

        if isinstance(identity, list):
            markers = [str(v).strip() for v in identity if str(v).strip()]
            if markers:
                return {"non_color_markers": markers[:8]}

        if isinstance(identity, dict):
            cleaned: Dict[str, Any] = {}
            for key in (
                "hairstyle",
                "clothing_signature",
                "expression_signature",
                "posture_signature",
                "accessory_signature",
                "identity_summary",
                "body_silhouette",
                "non_color_markers",
            ):
                value = identity.get(key)
                if isinstance(value, str) and value.strip():
                    cleaned[key] = value.strip()
                elif isinstance(value, list):
                    items = [str(v).strip() for v in value if str(v).strip()]
                    if items:
                        cleaned[key] = items[:8]
            if cleaned:
                return cleaned

        appearance = profile_data.get("appearance")
        if isinstance(appearance, str) and appearance.strip():
            return {"identity_summary": appearance.strip()}
        return {}

    def _extract_enrichments(self, profile_data: dict) -> Dict[str, Any]:
        """Extract enrichable fields from a character profile."""
        enrichments: Dict[str, Any] = {}

        if profile_data.get('nickname'):
            enrichments['short_name'] = profile_data['nickname']
        if profile_data.get('relationship_to_protagonist'):
            enrichments['category'] = profile_data['relationship_to_protagonist']
        if profile_data.get('origin'):
            enrichments['affiliation'] = profile_data['origin']
        if profile_data.get('keigo_switch') and isinstance(
            profile_data['keigo_switch'], dict
        ):
            enrichments['keigo'] = profile_data['keigo_switch']
        visual_identity = self._extract_visual_identity_non_color(profile_data)
        if visual_identity:
            enrichments['visual_identity_non_color'] = visual_identity

        # Build notes from personality_traits
        traits = profile_data.get('personality_traits', [])
        if traits:
            if isinstance(traits, list):
                enrichments['notes'] = ', '.join(str(t) for t in traits)
            elif isinstance(traits, str):
                enrichments['notes'] = traits

        return enrichments

    # ── Continuity Diff Report ───────────────────────────────────

    def generate_continuity_report(
        self,
        manifest: dict,
        pull_result: Optional[BiblePullResult] = None,
        push_result: Optional[BiblePushResult] = None,
    ) -> Path:
        """Generate a continuity_diff_report.json artifact for this run.

        Captures: new terms, conflicts, overrides, rejected pushes,
        and per-run KPIs (name drift, glossary violations, sync status).

        Args:
            manifest: The processed manifest dict.
            pull_result: Result from pull(), if available.
            push_result: Result from push(), if available.

        Returns:
            Path to the written report file.
        """
        report: Dict[str, Any] = {
            "report_type": "continuity_diff",
            "timestamp": datetime.datetime.now().isoformat(),
            "volume_id": manifest.get("volume_id", ""),
            "series_id": self.series_id or "",
            "bible_resolved": self.bible is not None,
        }

        # ── Pull KPIs ────────────────────────────────────────────
        if pull_result:
            report["pull"] = {
                "characters_inherited": pull_result.characters_inherited,
                "geography_inherited": pull_result.geography_inherited,
                "weapons_inherited": pull_result.weapons_inherited,
                "other_inherited": pull_result.other_inherited,
                "total_inherited": pull_result.total_inherited,
                "overrides": pull_result.overrides,
                "override_count": len(pull_result.overrides),
            }
        else:
            report["pull"] = {"status": "skipped"}

        # ── Push KPIs ────────────────────────────────────────────
        if push_result:
            report["push"] = {
                "characters_added": push_result.characters_added,
                "characters_enriched": push_result.characters_enriched,
                "characters_skipped": push_result.characters_skipped,
                "conflicts": push_result.conflicts,
                "conflict_count": len(push_result.conflicts),
                "volume_registered": push_result.volume_registered,
                "total_changes": push_result.total_changes,
            }
        else:
            report["push"] = {"status": "skipped"}

        # ── Name Drift Detection ─────────────────────────────────
        drift_count = (
            len(getattr(pull_result, "overrides", []))
            + len(getattr(push_result, "conflicts", []))
        )
        report["kpis"] = {
            "name_drift_events": drift_count,
            "pull_overrides": len(getattr(pull_result, "overrides", [])),
            "push_conflicts": len(getattr(push_result, "conflicts", [])),
            "bible_sync_success": self.bible is not None,
            "total_inherited": getattr(pull_result, "total_inherited", 0),
            "total_pushed": getattr(push_result, "total_changes", 0),
        }

        # ── Write report ─────────────────────────────────────────
        report_path = self.work_dir / "continuity_diff_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"📋 Continuity diff report: {report_path.name} "
                     f"(drift={drift_count}, inherited={report['kpis']['total_inherited']}, "
                     f"pushed={report['kpis']['total_pushed']})")
        return report_path

    # ── Manual Sync (CLI) ────────────────────────────────────────

    @classmethod
    def manual_sync(cls, work_dir: Path, pipeline_root: Path,
                    direction: str = "both") -> dict:
        """Run bible sync manually from CLI.

        Args:
            work_dir: Volume's working directory
            pipeline_root: Pipeline root path
            direction: 'pull', 'push', or 'both'

        Returns:
            Summary dict with pull and/or push results
        """
        manifest_path = work_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        agent = cls(work_dir, pipeline_root)
        if not agent.resolve(manifest):
            return {'error': 'No bible found for this volume',
                    'volume_id': manifest.get('volume_id', '?')}

        result = {
            'series_id': agent.series_id,
            'volume_id': manifest.get('volume_id', ''),
        }

        if direction in ('pull', 'both'):
            pull = agent.pull(manifest)
            result['pull'] = {
                'characters_inherited': pull.characters_inherited,
                'geography_inherited': pull.geography_inherited,
                'weapons_inherited': pull.weapons_inherited,
                'other_inherited': pull.other_inherited,
                'total_inherited': pull.total_inherited,
            }
            # Write updated manifest if pull modified character_names
            if pull.total_inherited > 0:
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
                result['pull']['manifest_updated'] = True

        if direction in ('push', 'both'):
            push = agent.push(manifest)
            result['push'] = {
                'characters_added': push.characters_added,
                'characters_enriched': push.characters_enriched,
                'characters_skipped': push.characters_skipped,
                'conflicts': push.conflicts,
                'volume_registered': push.volume_registered,
                'total_changes': push.total_changes,
            }

        return result
