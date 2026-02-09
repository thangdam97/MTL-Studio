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
        Returns True if a bible was found and loaded.
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

        logger.info("📖 No bible found for this volume — sync skipped")
        return False

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
        merged_names.update(existing_names)             # manifest overrides
        metadata_en['character_names'] = merged_names
        manifest['metadata_en'] = metadata_en

        injected = len(merged_names) - len(existing_names)
        if injected > 0:
            logger.info(f"   Injected {injected} bible character names "
                        f"into manifest (total: {len(merged_names)})")

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

        # ── Push character_names ─────────────────────────────────
        char_names = metadata_en.get('character_names', {})
        for jp_name, en_name in char_names.items():
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
                    'source': 'phase1.5_auto_sync',
                    'discovered_in': manifest.get('volume_id', ''),
                })
                result.characters_added += 1
                logger.debug(f"   New character: {jp_name} → {en_name}")

        # ── Enrich with character_profiles ───────────────────────
        profiles = metadata_en.get('character_profiles', {})
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

        # Build notes from personality_traits
        traits = profile_data.get('personality_traits', [])
        if traits:
            if isinstance(traits, list):
                enrichments['notes'] = ', '.join(str(t) for t in traits)
            elif isinstance(traits, str):
                enrichments['notes'] = traits

        return enrichments

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
