"""
Series Bible System — Universal Controller + Per-Series Bible
=============================================================

Manages canonical metadata for LN series across all volumes.
Provides glossary generation, prompt formatting, and world-setting
directives for the translation pipeline.

Architecture:
    BibleController  — singleton orchestrator, resolves manifest → bible
    SeriesBible      — per-series canonical data (characters, geography, etc.)

Bible files live in:  pipeline/bibles/<series_slug>.json
Index registry:       pipeline/bibles/index.json
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

BIBLE_SCHEMA_VERSION = "1.0"
INDEX_SCHEMA_VERSION = "1.0"
FUZZY_MATCH_THRESHOLD = 0.70  # For series detection via title matching


# ═══════════════════════════════════════════════════════════════════
#  SeriesBible — Per-Series Canonical Metadata
# ═══════════════════════════════════════════════════════════════════

class SeriesBible:
    """Single series' canonical metadata.

    Loads from a JSON bible file, provides glossary generation,
    prompt formatting, and mutation methods.
    """

    def __init__(self, bible_path: Path):
        self.path = bible_path
        self.data: dict = self._load()

    # ── I/O ──────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load bible JSON from disk."""
        if not self.path.exists():
            raise FileNotFoundError(f"Bible file not found: {self.path}")
        with open(self.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.debug(f"Loaded bible: {data.get('series_id', '?')} "
                      f"({self.entry_count(data)} entries)")
        return data

    def save(self) -> None:
        """Write bible JSON to disk."""
        self.data['last_updated'] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved bible: {self.series_id} → {self.path.name}")

    # ── Properties ───────────────────────────────────────────────

    @property
    def series_id(self) -> str:
        return self.data.get('series_id', '')

    @property
    def series_title(self) -> dict:
        return self.data.get('series_title', {})

    @property
    def world_setting(self) -> dict:
        return self.data.get('world_setting', {})

    @property
    def translation_rules(self) -> dict:
        return self.data.get('translation_rules', {})

    @property
    def volumes_registered(self) -> list:
        return self.data.get('volumes_registered', [])

    # ── Glossary Generation ──────────────────────────────────────

    def flat_glossary(self) -> Dict[str, str]:
        """Flatten ALL categories → single JP→EN dict.

        Walks characters, geography (countries/regions/cities),
        weapons_artifacts, organizations, cultural_terms, mythology.
        Emits canonical_en for each JP key, plus aliases_jp → canonical_en.
        """
        glossary: Dict[str, str] = {}

        # Characters
        for jp_name, char_data in self.data.get('characters', {}).items():
            if isinstance(char_data, dict):
                en = char_data.get('canonical_en', '')
                if en:
                    glossary[jp_name] = en
                # Aliases
                for alias in char_data.get('aliases_jp', []):
                    short = char_data.get('short_name', en)
                    if alias and short:
                        glossary[alias] = short

        # Geography (nested: countries, regions, cities)
        geo = self.data.get('geography', {})
        for sub_category in ('countries', 'regions', 'cities'):
            for jp_name, place_data in geo.get(sub_category, {}).items():
                if isinstance(place_data, dict):
                    en = place_data.get('canonical_en', '')
                    if en:
                        glossary[jp_name] = en

        # Weapons/Artifacts (nested: subcategories)
        weapons = self.data.get('weapons_artifacts', {})
        for sub_cat, items in weapons.items():
            if isinstance(items, dict):
                for jp_name, item_data in items.items():
                    if isinstance(item_data, dict):
                        en = item_data.get('canonical_en', '')
                        if en:
                            glossary[jp_name] = en

        # Organizations
        for jp_name, org_data in self.data.get('organizations', {}).items():
            if isinstance(org_data, dict):
                en = org_data.get('canonical_en', '')
                if en:
                    glossary[jp_name] = en

        # Cultural terms
        for jp_name, term_data in self.data.get('cultural_terms', {}).items():
            if isinstance(term_data, dict):
                en = term_data.get('canonical_en', '')
                if en:
                    glossary[jp_name] = en

        # Mythology
        for jp_name, myth_data in self.data.get('mythology', {}).items():
            if isinstance(myth_data, dict):
                en = myth_data.get('canonical_en', '')
                if en:
                    glossary[jp_name] = en

        return glossary

    def characters_glossary(self) -> Dict[str, str]:
        """JP→EN for character names only (including aliases)."""
        glossary: Dict[str, str] = {}
        for jp_name, char_data in self.data.get('characters', {}).items():
            if isinstance(char_data, dict):
                en = char_data.get('canonical_en', '')
                if en:
                    glossary[jp_name] = en
                for alias in char_data.get('aliases_jp', []):
                    short = char_data.get('short_name', en)
                    if alias and short:
                        glossary[alias] = short
        return glossary

    def geography_glossary(self) -> Dict[str, str]:
        """JP→EN for geography terms only."""
        glossary: Dict[str, str] = {}
        geo = self.data.get('geography', {})
        for sub_cat in ('countries', 'regions', 'cities'):
            for jp_name, data in geo.get(sub_cat, {}).items():
                if isinstance(data, dict) and data.get('canonical_en'):
                    glossary[jp_name] = data['canonical_en']
        return glossary

    def weapons_glossary(self) -> Dict[str, str]:
        """JP→EN for weapons/artifacts only."""
        glossary: Dict[str, str] = {}
        for sub_cat, items in self.data.get('weapons_artifacts', {}).items():
            if isinstance(items, dict):
                for jp_name, data in items.items():
                    if isinstance(data, dict) and data.get('canonical_en'):
                        glossary[jp_name] = data['canonical_en']
        return glossary

    def cultural_glossary(self) -> Dict[str, str]:
        """JP→EN for cultural terms + mythology."""
        glossary: Dict[str, str] = {}
        for jp_name, data in self.data.get('cultural_terms', {}).items():
            if isinstance(data, dict) and data.get('canonical_en'):
                glossary[jp_name] = data['canonical_en']
        for jp_name, data in self.data.get('mythology', {}).items():
            if isinstance(data, dict) and data.get('canonical_en'):
                glossary[jp_name] = data['canonical_en']
        return glossary

    # ── Rich Data ────────────────────────────────────────────────

    def get_character(self, jp_name: str) -> Optional[dict]:
        """Get a single character entry by JP name."""
        return self.data.get('characters', {}).get(jp_name)

    def get_all_characters(self) -> Dict[str, dict]:
        """Get all character entries."""
        return self.data.get('characters', {})

    def get_world_setting(self) -> dict:
        """Return world_setting block with honorific/name-order rules."""
        return self.world_setting

    # ── Prompt Formatting ────────────────────────────────────────

    def format_for_prompt(self) -> str:
        """Generate categorized prompt block for system instruction.

        Returns a structured text block like:
            <!-- SERIES BIBLE: Lord Marksman and Vanadis (CACHED) -->
            === WORLD SETTING ===
            Type: Medieval European Fantasy
            Honorifics: Localize (drop JP, use English equivalents)
            Name Order: Given-Family (Western)

            === CHARACTERS ===
            ティグルヴルムド＝ヴォルン = Tigrevurmud Vorn (Tigre)
            ...

            === GEOGRAPHY ===
            ジスタート = Zhcted | ブリューヌ = Brune
            ...
        """
        lines: List[str] = []
        title = self.series_title.get('en', self.series_id)
        lines.append(f"<!-- SERIES BIBLE: {title} (CACHED) -->")
        lines.append("")

        # World Setting directive
        ws = self.world_setting
        if ws:
            lines.append("=== WORLD SETTING ===")
            lines.append(f"Type: {ws.get('label', ws.get('type', 'unknown'))}")
            hon = ws.get('honorifics', {})
            if hon:
                mode_label = {
                    'localize': 'Localize — drop JP honorifics, use English register/titles',
                    'retain': 'Retain all JP honorifics (-san, -kun, -chan, etc.)'
                }.get(hon.get('mode', ''), hon.get('mode', ''))
                lines.append(f"Honorifics: {mode_label}")
                if hon.get('policy'):
                    lines.append(f"  Policy: {hon['policy']}")
            no = ws.get('name_order', {})
            if no:
                order_label = {
                    'given_family': 'Given-Family (Western first-name order)',
                    'family_given': 'Family-Given (Japanese surname-first order)'
                }.get(no.get('default', ''), no.get('default', ''))
                lines.append(f"Name Order: {order_label}")
                if no.get('policy'):
                    lines.append(f"  Policy: {no['policy']}")
            # Exceptions
            exceptions = ws.get('exceptions', [])
            if exceptions:
                lines.append(f"Exceptions ({len(exceptions)}):")
                for exc in exceptions:
                    en = exc.get('character_en', '?')
                    reason = exc.get('reason', '')
                    no_override = exc.get('name_order_override', '')
                    lines.append(f"  • {en}: {reason} → name order: {no_override}")
            lines.append("")

        # Characters
        chars = self.data.get('characters', {})
        if chars:
            lines.append("=== CHARACTERS ===")
            for jp_name, char_data in chars.items():
                if not isinstance(char_data, dict):
                    continue
                en = char_data.get('canonical_en', '')
                short = char_data.get('short_name', '')
                suffix = f" ({short})" if short and short != en else ""
                cat = char_data.get('category', '')
                cat_tag = f" [{cat}]" if cat else ""
                lines.append(f"  {jp_name} = {en}{suffix}{cat_tag}")
            lines.append("")

        # Geography
        geo = self.data.get('geography', {})
        for sub_name, sub_label in [('countries', 'COUNTRIES'),
                                     ('regions', 'REGIONS'),
                                     ('cities', 'CITIES')]:
            items = geo.get(sub_name, {})
            if items:
                entries = []
                for jp, data in items.items():
                    if isinstance(data, dict) and data.get('canonical_en'):
                        entries.append(f"{jp} = {data['canonical_en']}")
                if entries:
                    lines.append(f"=== GEOGRAPHY: {sub_label} ===")
                    lines.append("  " + " | ".join(entries))
                    lines.append("")

        # Weapons/Artifacts
        weapons = self.data.get('weapons_artifacts', {})
        if weapons:
            lines.append("=== WEAPONS & ARTIFACTS ===")
            for sub_cat, items in weapons.items():
                if isinstance(items, dict):
                    for jp, data in items.items():
                        if isinstance(data, dict) and data.get('canonical_en'):
                            extra = ""
                            if data.get('wielder'):
                                extra = f" (wielder: {data['wielder']})"
                            elif data.get('type'):
                                extra = f" ({data['type']})"
                            lines.append(f"  {jp} = {data['canonical_en']}{extra}")
            lines.append("")

        # Organizations
        orgs = self.data.get('organizations', {})
        if orgs:
            lines.append("=== ORGANIZATIONS ===")
            for jp, data in orgs.items():
                if isinstance(data, dict) and data.get('canonical_en'):
                    lines.append(f"  {jp} = {data['canonical_en']}")
            lines.append("")

        # Cultural terms
        cultural = self.data.get('cultural_terms', {})
        if cultural:
            lines.append("=== CULTURAL TERMS ===")
            for jp, data in cultural.items():
                if isinstance(data, dict) and data.get('canonical_en'):
                    literal = f" (lit. {data['literal']})" if data.get('literal') else ""
                    lines.append(f"  {jp} = {data['canonical_en']}{literal}")
            lines.append("")

        # Mythology
        myth = self.data.get('mythology', {})
        if myth:
            lines.append("=== MYTHOLOGY ===")
            for jp, data in myth.items():
                if isinstance(data, dict) and data.get('canonical_en'):
                    mtype = f" [{data['type']}]" if data.get('type') else ""
                    lines.append(f"  {jp} = {data['canonical_en']}{mtype}")
            lines.append("")

        # Translation rules
        rules = self.translation_rules
        if rules:
            lines.append("=== TRANSLATION RULES ===")
            if rules.get('style'):
                lines.append(f"  Style: {rules['style']}")
            titles = rules.get('titles', {})
            if titles:
                title_strs = [f"{jp}={en}" for jp, en in titles.items()]
                lines.append(f"  Titles: {' | '.join(title_strs)}")
            lines.append("")

        return "\n".join(lines)

    def format_world_setting_directive(self) -> str:
        """Generate just the world-setting directive for prompt injection.

        Shorter version for space-constrained prompts.
        """
        ws = self.world_setting
        if not ws:
            return ""

        parts = []
        parts.append(f"[World: {ws.get('label', ws.get('type', '?'))}]")

        hon = ws.get('honorifics', {})
        if hon.get('mode') == 'localize':
            parts.append("Honorifics: DROP all JP → English register/titles")
        elif hon.get('mode') == 'retain':
            parts.append("Honorifics: KEEP JP (-san, -kun, etc.)")

        no = ws.get('name_order', {})
        if no.get('default') == 'given_family':
            parts.append("Names: Given-Family order")
        elif no.get('default') == 'family_given':
            parts.append("Names: Family-Given order")

        exceptions = ws.get('exceptions', [])
        for exc in exceptions:
            en = exc.get('character_en', '')
            no_over = exc.get('name_order_override', '')
            if en:
                parts.append(f"Exception: {en} → {no_over}")

        return " | ".join(parts)

    # ── Mutation ─────────────────────────────────────────────────

    def add_entry(self, category: str, jp_key: str, data: dict) -> None:
        """Add or update an entry in a top-level category.

        Args:
            category: 'characters', 'organizations', 'cultural_terms', 'mythology'
                      For geography: 'geography.countries', 'geography.regions', 'geography.cities'
                      For weapons: 'weapons_artifacts.<sub_category>'
            jp_key: The Japanese key
            data: The entry data dict
        """
        parts = category.split('.')
        target = self.data

        # Navigate to nested dict
        for part in parts:
            if part not in target:
                target[part] = {}
            target = target[part]

        # Merge if exists, otherwise create
        if jp_key in target and isinstance(target[jp_key], dict):
            target[jp_key].update(data)
            logger.debug(f"Updated {category}/{jp_key}")
        else:
            target[jp_key] = data
            logger.debug(f"Added {category}/{jp_key}")

    def remove_entry(self, category: str, jp_key: str) -> bool:
        """Remove an entry. Returns True if found and removed."""
        parts = category.split('.')
        target = self.data
        for part in parts:
            if part not in target:
                return False
            target = target[part]
        if jp_key in target:
            del target[jp_key]
            return True
        return False

    def register_volume(self, volume_id: str, title: str, index: int) -> None:
        """Register a volume in volumes_registered (idempotent)."""
        volumes = self.data.setdefault('volumes_registered', [])
        # Check for existing
        for vol in volumes:
            if vol.get('volume_id') == volume_id:
                vol['title'] = title
                vol['index'] = index
                return
        volumes.append({
            'volume_id': volume_id,
            'title': title,
            'index': index
        })
        # Keep sorted by index
        volumes.sort(key=lambda v: v.get('index', 999))

    # ── Stats ────────────────────────────────────────────────────

    def entry_count(self, data: Optional[dict] = None) -> int:
        """Count total entries across all categories."""
        d = data or self.data
        count = 0
        count += len(d.get('characters', {}))
        geo = d.get('geography', {})
        for sub in ('countries', 'regions', 'cities'):
            count += len(geo.get(sub, {}))
        for sub_cat, items in d.get('weapons_artifacts', {}).items():
            if isinstance(items, dict):
                count += len(items)
        count += len(d.get('organizations', {}))
        count += len(d.get('cultural_terms', {}))
        count += len(d.get('mythology', {}))
        return count

    def stats(self) -> dict:
        """Detailed stats for this bible."""
        geo = self.data.get('geography', {})
        weapons = self.data.get('weapons_artifacts', {})
        weapon_count = sum(
            len(items) for items in weapons.values()
            if isinstance(items, dict)
        )
        return {
            'series_id': self.series_id,
            'bible_version': self.data.get('bible_version', '?'),
            'volumes': len(self.volumes_registered),
            'characters': len(self.data.get('characters', {})),
            'geography': {
                'countries': len(geo.get('countries', {})),
                'regions': len(geo.get('regions', {})),
                'cities': len(geo.get('cities', {})),
            },
            'weapons_artifacts': weapon_count,
            'organizations': len(self.data.get('organizations', {})),
            'cultural_terms': len(self.data.get('cultural_terms', {})),
            'mythology': len(self.data.get('mythology', {})),
            'total_entries': self.entry_count(),
            'world_setting': self.world_setting.get('type', 'not set'),
        }

    def __repr__(self) -> str:
        return (f"SeriesBible('{self.series_id}', "
                f"{self.entry_count()} entries, "
                f"{len(self.volumes_registered)} volumes)")


# ═══════════════════════════════════════════════════════════════════
#  BibleController — Universal Orchestrator
# ═══════════════════════════════════════════════════════════════════

class BibleController:
    """Universal controller for all series bibles.

    Manages the index registry, resolves manifests to bibles,
    and provides CRUD + import operations.
    """

    def __init__(self, pipeline_root: Path):
        self.pipeline_root = pipeline_root
        self.bibles_dir = pipeline_root / "bibles"
        self.index_path = self.bibles_dir / "index.json"
        self.index: dict = self._load_index()
        self._cache: Dict[str, SeriesBible] = {}

    # ── Index I/O ────────────────────────────────────────────────

    def _load_index(self) -> dict:
        """Load or initialize the index registry."""
        if self.index_path.exists():
            with open(self.index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'version': INDEX_SCHEMA_VERSION,
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'series': {}
        }

    def _save_index(self) -> None:
        """Persist the index registry to disk."""
        self.index['last_updated'] = datetime.now(timezone.utc).isoformat()
        self.bibles_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    # ── Resolution ───────────────────────────────────────────────

    def load(self, manifest: dict, work_dir: Optional[Path] = None) -> Optional[SeriesBible]:
        """Auto-resolve and load the bible for a volume.

        Resolution order:
            1. manifest.bible_id → direct lookup
            2. Volume ID match in index.volumes[]
            3. Pattern match on metadata.series against index.match_patterns
            4. Fuzzy match on metadata.title against index.match_patterns

        Returns SeriesBible or None (standalone volume with no series).
        """
        # 1. Explicit bible_id
        bible_id = manifest.get('bible_id')
        if bible_id:
            series_entry = self.index.get('series', {}).get(bible_id)
            if series_entry:
                logger.info(f"Bible resolved via bible_id: {bible_id}")
                return self._get_or_load(bible_id, series_entry)

        # 2. Volume ID lookup
        volume_id = manifest.get('volume_id', '')
        # Extract short hash (last 4 chars after underscore)
        short_id = self._extract_short_id(volume_id)
        if short_id:
            for sid, entry in self.index.get('series', {}).items():
                if short_id in entry.get('volumes', []):
                    logger.info(f"Bible resolved via volume ID {short_id}: {sid}")
                    return self._get_or_load(sid, entry)

        # 3. Series metadata pattern match
        series_id = self.detect_series(manifest)
        if series_id:
            entry = self.index['series'][series_id]
            logger.info(f"Bible resolved via series detection: {series_id}")
            return self._get_or_load(series_id, entry)

        logger.debug("No bible found for this volume")
        return None

    def detect_series(self, manifest: dict) -> Optional[str]:
        """Detect which registered series a manifest belongs to.

        Checks metadata.series and metadata.title against match_patterns.
        """
        metadata = manifest.get('metadata', {})
        series_str = metadata.get('series', '')
        title_str = metadata.get('title', '')

        best_match: Optional[str] = None
        best_score: float = 0.0

        for sid, entry in self.index.get('series', {}).items():
            patterns = entry.get('match_patterns', [])
            for pattern in patterns:
                # Exact substring match on series field
                if series_str and pattern.lower() in series_str.lower():
                    return sid
                # Exact substring match on title
                if title_str and pattern.lower() in title_str.lower():
                    return sid
                # Fuzzy match
                for candidate in [series_str, title_str]:
                    if candidate:
                        score = SequenceMatcher(
                            None, pattern.lower(), candidate.lower()
                        ).ratio()
                        if score > best_score:
                            best_score = score
                            best_match = sid

        if best_score >= FUZZY_MATCH_THRESHOLD:
            logger.debug(f"Fuzzy match: {best_match} (score: {best_score:.2f})")
            return best_match

        return None

    def _get_or_load(self, series_id: str, entry: dict) -> SeriesBible:
        """Get cached bible or load from disk."""
        if series_id in self._cache:
            return self._cache[series_id]

        bible_file = entry.get('bible_file', f'{series_id}.json')
        bible_path = self.bibles_dir / bible_file
        bible = SeriesBible(bible_path)
        self._cache[series_id] = bible
        return bible

    def _extract_short_id(self, volume_id: str) -> Optional[str]:
        """Extract 4-char hex hash from volume_id.

        E.g. '魔弾の王と戦姫 第1章―出逢い―_20260208_25d9' → '25d9'
        """
        match = re.search(r'_([0-9a-f]{4})$', volume_id)
        if match:
            return match.group(1)
        return None

    # ── CRUD ─────────────────────────────────────────────────────

    def create_bible(
        self,
        series_id: str,
        series_title: dict,
        match_patterns: list,
        world_setting: Optional[dict] = None
    ) -> SeriesBible:
        """Create a new empty bible for a series.

        Args:
            series_id: URL-safe slug (e.g. 'madan_no_ou_to_vanadis')
            series_title: {'ja': '...', 'en': '...', 'romaji': '...'}
            match_patterns: Strings to match against manifest metadata
            world_setting: Optional world_setting dict
        """
        bible_file = f"{series_id}.json"
        bible_path = self.bibles_dir / bible_file

        if bible_path.exists():
            raise FileExistsError(f"Bible already exists: {bible_path}")

        data = {
            'bible_version': BIBLE_SCHEMA_VERSION,
            'series_id': series_id,
            'series_title': series_title,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'volumes_registered': [],
            'world_setting': world_setting or {},
            'characters': {},
            'geography': {
                'countries': {},
                'regions': {},
                'cities': {}
            },
            'weapons_artifacts': {},
            'organizations': {},
            'cultural_terms': {},
            'mythology': {},
            'translation_rules': {}
        }

        # Write to disk
        self.bibles_dir.mkdir(parents=True, exist_ok=True)
        with open(bible_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Register in index
        self.index.setdefault('series', {})[series_id] = {
            'bible_file': bible_file,
            'match_patterns': match_patterns,
            'volumes': [],
            'entry_count': 0,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        self._save_index()

        bible = SeriesBible(bible_path)
        self._cache[series_id] = bible
        logger.info(f"Created bible: {series_id} ({bible_file})")
        return bible

    def get_bible(self, series_id: str) -> Optional[SeriesBible]:
        """Get a bible by series_id. Returns None if not found."""
        if series_id in self._cache:
            return self._cache[series_id]

        entry = self.index.get('series', {}).get(series_id)
        if not entry:
            return None

        return self._get_or_load(series_id, entry)

    def list_bibles(self) -> List[dict]:
        """List all registered bibles with summary stats."""
        result = []
        for sid, entry in self.index.get('series', {}).items():
            try:
                bible = self._get_or_load(sid, entry)
                result.append(bible.stats())
            except FileNotFoundError:
                result.append({
                    'series_id': sid,
                    'error': 'Bible file not found',
                    'bible_file': entry.get('bible_file', '?')
                })
        return result

    # ── Volume Management ────────────────────────────────────────

    def link_volume(self, volume_id: str, series_id: str) -> None:
        """Link a volume hash to a series (updates index)."""
        short_id = self._extract_short_id(volume_id) or volume_id
        entry = self.index.get('series', {}).get(series_id)
        if not entry:
            raise KeyError(f"Series not found: {series_id}")

        volumes = entry.setdefault('volumes', [])
        if short_id not in volumes:
            volumes.append(short_id)
            self._save_index()
            logger.info(f"Linked volume {short_id} → {series_id}")

    def unlink_volume(self, volume_id: str) -> Optional[str]:
        """Unlink a volume from its series. Returns the series_id or None."""
        short_id = self._extract_short_id(volume_id) or volume_id
        for sid, entry in self.index.get('series', {}).items():
            if short_id in entry.get('volumes', []):
                entry['volumes'].remove(short_id)
                self._save_index()
                logger.info(f"Unlinked volume {short_id} from {sid}")
                return sid
        return None

    # ── Import from Manifest ─────────────────────────────────────

    def import_from_manifest(
        self,
        manifest: dict,
        series_id: str,
        categories: Optional[List[str]] = None
    ) -> dict:
        """Extract terms from a manifest and add to bible.

        Args:
            manifest: Loaded manifest.json dict
            series_id: Target bible series_id
            categories: Which categories to import
                        ['character_names', 'character_profiles']
                        Default: all available

        Returns:
            Summary dict with counts per category.
        """
        bible = self.get_bible(series_id)
        if not bible:
            raise KeyError(f"Bible not found: {series_id}")

        if categories is None:
            categories = ['character_names', 'character_profiles']

        metadata_en = manifest.get('metadata_en', {})
        summary: Dict[str, int] = {}

        # Character names → characters (basic entry)
        if 'character_names' in categories:
            char_names = metadata_en.get('character_names', {})
            added = 0
            for jp_name, en_name in char_names.items():
                if not isinstance(en_name, str):
                    continue
                existing = bible.get_character(jp_name)
                if not existing:
                    bible.add_entry('characters', jp_name, {
                        'canonical_en': en_name,
                        'source': 'manifest_import'
                    })
                    added += 1
            summary['character_names'] = added

        # Character profiles → enrich existing character entries
        if 'character_profiles' in categories:
            profiles = metadata_en.get('character_profiles', {})
            enriched = 0
            for profile_key, profile_data in profiles.items():
                if not isinstance(profile_data, dict):
                    continue

                # Determine JP name key
                # V1 uses English keys, V2 uses JP keys
                jp_key = profile_key
                if re.match(r'^[A-Za-z_]+$', profile_key):
                    # English key (V1 format) — try to find JP match
                    en_name = profile_data.get('full_name', profile_key.replace('_', ' '))
                    # Search characters for matching canonical_en
                    found = False
                    for jp, char in bible.data.get('characters', {}).items():
                        if isinstance(char, dict):
                            if char.get('canonical_en', '').lower() == en_name.lower():
                                jp_key = jp
                                found = True
                                break
                    if not found:
                        continue

                # Enrich with profile data
                enrichments: Dict[str, Any] = {}
                if profile_data.get('nickname'):
                    enrichments['short_name'] = profile_data['nickname']
                if profile_data.get('relationship_to_protagonist'):
                    enrichments['category'] = profile_data['relationship_to_protagonist']
                if profile_data.get('origin'):
                    enrichments['affiliation'] = profile_data['origin']

                # Build notes from personality/traits
                notes_parts = []
                if 'personality_traits' in profile_data:
                    traits = profile_data['personality_traits']
                    if isinstance(traits, list):
                        notes_parts.append(', '.join(traits))
                    elif isinstance(traits, str):
                        notes_parts.append(traits)
                if notes_parts:
                    enrichments['notes'] = ' | '.join(notes_parts)

                if enrichments:
                    bible.add_entry('characters', jp_key, enrichments)
                    enriched += 1

            summary['character_profiles'] = enriched

        # Register volume
        volume_id = manifest.get('volume_id', '')
        title = manifest.get('metadata', {}).get('title', '')
        metadata = manifest.get('metadata', {})
        # Try to determine index
        idx = metadata.get('series_index') or len(bible.volumes_registered) + 1
        if isinstance(idx, str):
            try:
                idx = int(idx)
            except ValueError:
                idx = len(bible.volumes_registered) + 1
        bible.register_volume(
            volume_id=self._extract_short_id(volume_id) or volume_id,
            title=title,
            index=idx
        )

        # Update index entry count
        entry = self.index.get('series', {}).get(series_id, {})
        short_id = self._extract_short_id(volume_id) or volume_id
        volumes = entry.setdefault('volumes', [])
        if short_id and short_id not in volumes:
            volumes.append(short_id)
        entry['entry_count'] = bible.entry_count()
        entry['last_updated'] = datetime.now(timezone.utc).isoformat()

        bible.save()
        self._save_index()

        logger.info(f"Imported manifest → {series_id}: {summary}")
        return summary

    # ── Integrity ────────────────────────────────────────────────

    def validate_bible(self, series_id: str) -> dict:
        """Validate a single bible for issues.

        Checks:
            - Missing canonical_en
            - Duplicate JP keys across categories
            - Empty categories
            - Orphan aliases (alias points to non-existent character)
        """
        bible = self.get_bible(series_id)
        if not bible:
            return {'error': f'Bible not found: {series_id}'}

        issues: List[str] = []
        warnings: List[str] = []

        # Check characters
        chars = bible.data.get('characters', {})
        for jp, data in chars.items():
            if isinstance(data, dict):
                if not data.get('canonical_en'):
                    issues.append(f"Character missing canonical_en: {jp}")
                for alias in data.get('aliases_jp', []):
                    if not alias:
                        warnings.append(f"Empty alias for character: {jp}")

        # Check geography
        geo = bible.data.get('geography', {})
        for sub in ('countries', 'regions', 'cities'):
            for jp, data in geo.get(sub, {}).items():
                if isinstance(data, dict) and not data.get('canonical_en'):
                    issues.append(f"Geography/{sub} missing canonical_en: {jp}")

        # Check for cross-category JP key collisions
        all_jp_keys: Dict[str, str] = {}
        for jp in chars:
            all_jp_keys.setdefault(jp, []).append('characters') if jp not in all_jp_keys else None
        for sub in ('countries', 'regions', 'cities'):
            for jp in geo.get(sub, {}):
                if jp in all_jp_keys:
                    warnings.append(f"JP key '{jp}' appears in both characters and geography/{sub}")

        # World setting check
        ws = bible.world_setting
        if not ws:
            warnings.append("No world_setting defined")
        elif not ws.get('type'):
            warnings.append("world_setting.type is empty")

        return {
            'series_id': series_id,
            'entries': bible.entry_count(),
            'issues': issues,
            'warnings': warnings,
            'valid': len(issues) == 0
        }

    def find_orphan_volumes(self, work_dir: Path) -> List[str]:
        """Find WORK/ volumes not linked to any bible."""
        linked: set = set()
        for entry in self.index.get('series', {}).values():
            linked.update(entry.get('volumes', []))

        orphans = []
        if work_dir.exists():
            for d in work_dir.iterdir():
                if d.is_dir():
                    short_id = self._extract_short_id(d.name)
                    if short_id and short_id not in linked:
                        orphans.append(d.name)
        return orphans

    def stats(self) -> dict:
        """Global statistics across all bibles."""
        series_count = len(self.index.get('series', {}))
        total_entries = sum(
            e.get('entry_count', 0)
            for e in self.index.get('series', {}).values()
        )
        total_volumes = sum(
            len(e.get('volumes', []))
            for e in self.index.get('series', {}).values()
        )
        return {
            'series_count': series_count,
            'total_entries': total_entries,
            'total_volumes': total_volumes,
            'bibles_dir': str(self.bibles_dir),
        }

    def __repr__(self) -> str:
        s = self.stats()
        return (f"BibleController({s['series_count']} series, "
                f"{s['total_entries']} entries, "
                f"{s['total_volumes']} volumes)")
