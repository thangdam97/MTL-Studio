# LN Bible & Continuity System Redesign

**Version:** 2.0 — IMPLEMENTATION COMPLETE  
**Date:** 2026-02-09  
**Status:** ✅ All phases implemented and validated (Phase 0 → Phase E)  
**Scope:** Series-level canonical metadata store + volume continuity overhaul  
**Affected Files:** 8 existing + 3 new modules  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Forensics](#2-current-state-forensics)
   - 2.1 [Glossary Pipeline](#21-glossary-pipeline)
   - 2.2 [Character Profile Data Loss](#22-character-profile-data-loss)
   - 2.3 [Continuity System (Dead)](#23-continuity-system-dead)
   - 2.4 [Schema Fragmentation](#24-schema-fragmentation)
   - 2.5 [Series Identification Gaps](#25-series-identification-gaps)
3. [Architecture: The LN Bible System](#3-architecture-the-ln-bible-system)
   - 3.1 [Universal Controller](#31-universal-controller)
   - 3.2 [Bible Schema V1.0](#32-bible-schema-v10)
   - 3.3 [Index Registry](#33-index-registry)
   - 3.4 [Resolution Flow](#34-resolution-flow)
4. [Architecture: Continuity Metadata Overhaul](#4-architecture-continuity-metadata-overhaul)
   - 4.1 [Transform Layer Fix](#41-transform-layer-fix)
   - 4.2 [Prompt Formatter Enhancement](#42-prompt-formatter-enhancement)
   - 4.3 [Schema Unification](#43-schema-unification)
5. [Implementation Plan](#5-implementation-plan)
   - 5.1 [Phase 0: Hotfix (Transform + Formatter)](#51-phase-0-hotfix) ✅
   - 5.2 [Phase A: Bible Infrastructure](#52-phase-a-bible-infrastructure) ✅
   - 5.3 [Phase B: Madan Bible Seed](#53-phase-b-madan-bible-seed) ✅
   - 5.4 [Phase C: Pipeline Integration](#54-phase-c-pipeline-integration) ✅
   - 5.5 [Phase D: CLI & Tooling](#55-phase-d-cli--tooling) ✅
   - 5.6 [Phase E: Categorized Prompt Injection](#56-phase-e-categorized-prompt-injection) ✅
   - 5.7 [Phase F: Migration & Validation (Future)](#57-phase-f-migration--validation-future)
6. [File Change Matrix](#6-file-change-matrix)
7. [Risk Assessment](#7-risk-assessment)
8. [Appendix: Workspace Series Inventory](#8-appendix-workspace-series-inventory)

---

## 1. Executive Summary

MTL Studio's translation pipeline has **no series-level canonical metadata store**. Each volume reinvents character names, place names, and terminology from scratch via per-manifest `metadata_en.character_names` — a flat `Dict[str, str]` injected into the system prompt as a glossary.

This caused:
- **"Zxtat" incident:** ザクスタン (Sachstein) was never locked → model invented "Zxtat" in Vol 2 Chapter 2. Vol 1 had 4 different spellings (Sachstein, Saxtein, Zakhstan, Zaxstan) across 15 chapters.
- **Cross-volume drift:** 68 volumes in WORK/, at least 15 multi-volume series with NO shared glossary.
- **Character profile data loss:** Rich RTAS data (keigo switches, contraction rates, relationship scores, nickname mappings) curated in `character_profiles` is **silently dropped** by the transform layer — the LLM never sees it.
- **Dead continuity system:** `continuity_manager.py` (429 lines) is fully disabled — `detect_and_offer_continuity()` always returns `None`.

### The Solution

1. **LN Bible System** — A universal controller managing per-series canonical JSON files at `pipeline/bibles/`. Each volume's manifest declares `bible_id` → the translator loads the bible → 200+ terms injected into the system prompt automatically. All volumes in a series share one truth.

2. **Continuity Metadata Overhaul** — Fix the lossy `_transform_character_profiles()` and `_format_semantic_metadata()` to pass through all rich data (RTAS, keigo, contractions, nicknames, how-refers-to-others) to the LLM.

3. **Kill Dead Code** — Replace `continuity_manager.py` with the Bible system. Remove the three-way schema split.

---

## 2. Current State Forensics

### 2.1 Glossary Pipeline

**Data flow (current):**

```
manifest.json
  └─ metadata_en.character_names: {"ザクスタン": "Sachstein", ...}
       │
       ▼
  GlossaryLock.__init__()          ← glossary_lock.py L65
  reads character_names dict
       │
       ▼
  agent.py L200-210
  glossary_lock.get_locked_names() → Dict[str, str]
       │
       ▼
  prompt_loader.set_glossary(dict) ← prompt_loader.py L131
       │
       ▼
  prompt_loader._build_system_instruction()  ← L938
  appends "<!-- GLOSSARY (CACHED) -->"
  with flat "JP = EN" lines
       │
       ▼
  chapter_processor.auto_fix_output()  ← L938-955
  GlossaryLock.validate_output() + auto_fix_output()
  post-translation regex replacement of near-miss variants
```

**Key files:**

| File | Lines | Role |
|------|-------|------|
| `glossary_lock.py` | 204 | Load manifest names, validate output, auto-fix variants |
| `agent.py` | 1,483 | Orchestrate: load names → set glossary → init processor |
| `prompt_loader.py` | 2,277 | Build system instruction with glossary injection |
| `chapter_processor.py` | 1,471 | Post-translation auto_fix_output via GlossaryLock |

**Critical limitation:** The glossary is **per-volume, flat, names-only**. No geography, weapons, cultural terms, mythology, or organizations.

### 2.2 Character Profile Data Loss

The 15c4 (Madan Vol 2) manifest contains beautifully curated profiles:

```json
"ティグルヴルムド＝ヴォルン": {
    "full_name": "Tigrevurmud Vorn",
    "nickname": "Tigre",                          // ❌ DROPPED
    "origin": "Brune",                             // ❌ DROPPED
    "rtas_relationships": [                        // ❌ DROPPED
      {"target": "エレオノーラ", "rtas_score": 4.5,
       "contraction_rate_override": 90, "notes": "..."}
    ],
    "keigo_switch": {                              // ❌ DROPPED
      "speaking_to": {
        "Ellen": "casual_affectionate",
        "King Faron": "polite_formal"
      }
    },
    "contraction_rate": {                          // ❌ DROPPED
      "baseline": 0.9,
      "speaking_to": {"Ellen": 0.9, "King Faron": 0.6}
    },
    "how_character_refers_to_others": {            // ❌ DROPPED
      "エレオノーラ": "エレオノーラ様 → エレン (Ellen)"
    },
    "personality_traits": ["kind-hearted", ...],   // ✅ Preserved (as notes)
    "speech_pattern": "casual_masculine"           // ✅ → dialogue_patterns
}
```

**`_transform_character_profiles()`** (agent.py L560-623) converts this to a flat `characters` list, preserving only:

| Field | Source | Preserved? |
|-------|--------|------------|
| `name_en` | profile key (JP name!) | ✅ (but wrong — uses JP key as EN name) |
| `name_kanji` | `full_name` (EN name!) | ✅ (but swapped — EN name in kanji field) |
| `role` | `relationship_to_protagonist` | ✅ |
| `gender` | parsed from `pronouns` string | ✅ |
| `age` | `age` | ✅ |
| `pronouns` | parsed string → `{subject, object, possessive}` | ✅ |
| `notes` | `personality_traits` + `key_traits` + `appearance` | ✅ |
| `character_arc` | `character_arc*` | ✅ |
| `nickname` | — | ❌ **DROPPED** |
| `origin` | — | ❌ **DROPPED** |
| `rtas_relationships` | — | ❌ **DROPPED** |
| `keigo_switch` | — | ❌ **DROPPED** |
| `contraction_rate` | — | ❌ **DROPPED** |
| `how_character_refers_to_others` | — | ❌ **DROPPED** |

**Result:** The LLM sees `Role: ally, Gender: male, Age: 16` — not the rich relational data that cost hours to curate.

**Additional bug:** `name_en` and `name_kanji` are **swapped**. The dict key is the JP name (ティグルヴルムド＝ヴォルン), but the code assigns it to `name_en`. `full_name` contains the EN name (Tigrevurmud Vorn) but goes to `name_kanji`.

### 2.3 Continuity System (Dead)

**`continuity_manager.py`** — 429 lines, 7 methods, all unreachable:

| Method | Purpose | State |
|--------|---------|-------|
| `detect_series_info()` | Regex parse title for vol number | Never called from active code |
| `find_previous_volume()` | Scan WORK/ for same-series | Never called |
| `load_continuity_pack()` | Read `.context/continuity_pack.json` | Never called |
| `save_continuity_pack()` | Write continuity pack | Never called |
| `extract_continuity_from_volume()` | Build ContinuityPack from manifest | Never called |
| `format_continuity_for_prompt()` | Format ROSTER/GLOSSARY block | Never called |
| `detect_and_offer_continuity()` | **Gateway function — always returns `None`** | Called but no-ops |

**The gate:** `detect_and_offer_continuity()` (the only externally-called function) always returns `None`:

```python
def detect_and_offer_continuity(work_dir, manifest, target_language='en'):
    """LEGACY SYSTEM - DISABLED"""
    # ... logging only ...
    return None  # ← ALWAYS
```

**The caller:** `agent.py` L151 — only invoked when `enable_continuity=True` (defaults to `False`, labeled "ALPHA EXPERIMENTAL - Highly unstable").

**Evidence of decay:**
- 25d9's `.context/continuity_pack.json` contains garbage: `技量→Ude`, `捕虜→Mono`, `蝙蝠→Koumori` (common words, not character names)
- 15c4's `.context/` directory is empty
- `inherited_from` manifest field exists on one volume — **no code reads it**

**Dead code in agent.py L208-244:** The continuity pack merge block (merging roster, glossary, formatting for prompt) is unreachable because `self.continuity_pack` is always `None`.

### 2.4 Schema Fragmentation

`_extract_semantic_metadata()` (agent.py L470-512) handles three incompatible schemas:

| Schema | Detection Key | Used By | Status |
|--------|---------------|---------|--------|
| **Enhanced v2.1** | `characters` key present | No volume | Ghost schema — never populated |
| **Legacy V2** | `character_profiles` key present | 15c4, most curated volumes | Active but lossy transform |
| **V4 nested** | `character_names` with dict values | No volume | Never triggered |

The "Enhanced v2.1" schema (flat `characters` list) was supposed to be the target format, but **no code ever generates it**. The Librarian creates Legacy V2, and it stays Legacy V2. The transform tries to convert Legacy V2 → v2.1 but loses data in the process.

### 2.5 Series Identification Gaps

**EPUB extraction** (metadata_parser.py L112-120):
- Reads `calibre:series` OPF meta → `metadata.series`
- Reads `calibre:series_index` → `metadata.series_index`
- Most LN EPUBs lack Calibre metadata → both are empty or null

**Title regex** (continuity_manager.py `detect_series_info()`):
- Patterns: `(.+?) Vol.? (\d+)`, `(.+?) V(\d+)`, `(.+?) (\d+)$`, `(.+?) (\d+)巻`
- Cannot handle `第2章` format (all Madan volumes)
- Never called from active code anyway

**Current state of Madan volumes:**
- `metadata.series`: `"Madan no Ou to Vanadis (Lord Marksman and Vanadis)"` (manually set, works)
- `metadata.series_index`: `null` (Calibre field empty, no fallback)

---

## 3. Architecture: The LN Bible System

### 3.1 Universal Controller

```
pipeline/
├── bibles/
│   ├── index.json                          ← Registry: series → bible mapping
│   ├── madan_no_ou_to_vanadis.json         ← Per-series canonical data
│   ├── kokou_no_hana.json
│   └── ...
└── pipeline/
    └── translator/
        ├── series_bible.py                  ← NEW: SeriesBible + BibleController
        ├── glossary_lock.py                 ← MODIFIED: accept bible_glossary
        ├── agent.py                         ← MODIFIED: load bible before glossary
        └── continuity_manager.py            ← DEPRECATED: replaced by bible
```

**`BibleController`** — The universal orchestrator:

```python
class BibleController:
    """Universal controller for all series bibles."""

    def __init__(self, pipeline_root: Path):
        self.bibles_dir = pipeline_root / "bibles"
        self.index_path = self.bibles_dir / "index.json"
        self.index = self._load_index()

    # === Resolution ===
    def load(self, manifest: dict, work_dir: Path) -> Optional[SeriesBible]:
        """Auto-resolve and load the bible for a volume.
        
        Resolution order:
        1. manifest.bible_id (explicit binding — fastest path)
        2. Volume ID match in index.volumes[] (previously linked)
        3. Pattern match on metadata.series against index.match_patterns
        4. Fuzzy match on metadata.title against index.match_patterns
        
        Returns SeriesBible or None (standalone volume with no series).
        """

    def detect_series(self, manifest: dict) -> Optional[str]:
        """Detect which registered series a manifest belongs to."""

    # === CRUD ===
    def create_bible(self, series_id: str, series_title: dict,
                     match_patterns: list) -> SeriesBible
    def get_bible(self, series_id: str) -> SeriesBible
    def list_bibles(self) -> List[dict]  # Summary with stats

    # === Volume Management ===
    def link_volume(self, volume_id: str, series_id: str)
    def unlink_volume(self, volume_id: str)
    def auto_link_all(self, work_dir: Path) -> dict  # Scan WORK/ + bind

    # === Term Management ===
    def import_from_volume(self, volume_id: str, work_dir: Path)
    def promote_terms(self, volume_id: str, terms: dict, category: str)

    # === Integrity ===
    def validate_all(self) -> dict          # Cross-bible collision check
    def find_orphan_volumes(self, work_dir: Path) -> List[str]
    def stats(self) -> dict                 # Global statistics
```

**`SeriesBible`** — Per-series data + flat glossary generation:

```python
class SeriesBible:
    """Single series' canonical metadata."""

    def __init__(self, bible_path: Path):
        self.path = bible_path
        self.data = self._load()

    # === Glossary Generation ===
    def flat_glossary(self) -> Dict[str, str]:
        """Flatten ALL categories → single JP: EN dict.
        
        Walks characters, geography, weapons, organizations,
        cultural_terms, mythology. Emits canonical_en for each
        JP key, plus aliases_jp → canonical_en for alias coverage.
        
        This is the dict that GlossaryLock consumes.
        """

    def characters_glossary(self) -> Dict[str, str]
    def geography_glossary(self) -> Dict[str, str]

    # === Rich Data ===
    def get_character_profiles(self) -> Dict:
        """Return character data with full RTAS/keigo/contraction info."""

    def get_translation_rules(self) -> Dict:
        """Return series-specific style rules."""

    # === Prompt Formatting ===
    def format_for_prompt(self) -> str:
        """Generate categorized prompt block for system instruction.
        
        <!-- SERIES BIBLE: Lord Marksman and Vanadis (CACHED) -->
        CHARACTERS:
          ティグルヴルムド＝ヴォルン = Tigrevurmud Vorn (Tigre)
        GEOGRAPHY:
          ジスタート = Zhcted | ブリューヌ = Brune | ザクスタン = Sachstein
        WEAPONS:
          アリファール = Arifar (Sword of Wind)
        CULTURAL:
          戦姫 = Vanadis | 竜具 = Dragonic Tool
        """

    # === Mutation ===
    def add_entry(self, category: str, jp_key: str, data: dict)
    def register_volume(self, volume_id: str, title: str, index: int)
    def save(self)
```

### 3.2 Bible Schema V1.0

Each bible file follows this structure:

```json
{
  "bible_version": "1.0",
  "series_id": "madan_no_ou_to_vanadis",
  "series_title": {
    "ja": "魔弾の王と戦姫",
    "en": "Lord Marksman and Vanadis",
    "romaji": "Madan no Ou to Vanadis"
  },
  "last_updated": "2026-02-09T14:30:00Z",
  "volumes_registered": [
    {"volume_id": "25d9", "title": "第1章―出逢い―", "index": 1},
    {"volume_id": "15c4", "title": "第2章―銀の流星―", "index": 2}
  ],

  "characters": {
    "ティグルヴルムド＝ヴォルン": {
      "canonical_en": "Tigrevurmud Vorn",
      "short_name": "Tigre",
      "aliases_jp": ["ティグル", "ティグレ"],
      "introduced_in": 1,
      "category": "protagonist",
      "affiliation": "Brune / Alsace",
      "notes": "Earl of Alsace. Nickname 'Tigre' used by Elen and close allies."
    }
  },

  "geography": {
    "countries": {
      "ザクスタン": {
        "canonical_en": "Sachstein",
        "demonym": "Sachsteinian",
        "notes": "Western neighbor of Brune. Frequently invades."
      }
    },
    "regions": {
      "アルサス": {
        "canonical_en": "Alsace",
        "parent": "Brune",
        "notes": "Tigre's territory"
      }
    },
    "cities": {
      "リュテティア": {
        "canonical_en": "Lutetia",
        "parent": "Brune",
        "notes": "Capital of Brune"
      }
    }
  },

  "weapons_artifacts": {
    "dragonic_tools": {
      "アリファール": {
        "canonical_en": "Arifar",
        "type": "sword",
        "wielder": "Eleonora Viltaria",
        "element": "wind"
      }
    },
    "legendary_weapons": {
      "デュランダル": {
        "canonical_en": "Durandal",
        "wielder": "Roland"
      }
    }
  },

  "organizations": {
    "ナヴァール騎士団": {
      "canonical_en": "Navarre Knights",
      "allegiance": "Brune"
    }
  },

  "cultural_terms": {
    "戦姫": {
      "canonical_en": "Vanadis",
      "literal": "War Princess",
      "notes": "Title for 7 wielders of Dragonic Tools"
    }
  },

  "mythology": {
    "ジルニトラ": {
      "canonical_en": "Zirnitra",
      "type": "deity",
      "notes": "Black Dragon god of Zhcted"
    }
  },

  "world_setting": {
    "type": "fantasy",
    "label": "Medieval European Fantasy",
    "honorifics": {
      "mode": "localize",
      "policy": "Drop all JP honorifics. Convey respect through register, word choice, and English-equivalent titles (Lord, Lady, Sir, Your Majesty, etc.)."
    },
    "name_order": {
      "default": "given_family",
      "policy": "Western first-name order for all characters."
    },
    "exceptions": []
  },

  "translation_rules": {
    "style": "Medieval European fantasy — period-appropriate English, not archaic.",
    "titles": {
      "王": "King",
      "公爵": "Duke",
      "伯爵": "Earl"
    }
  }
}
```

#### World Setting Type Reference

| Setting Type | `honorifics.mode` | `name_order.default` | Example Series |
|---|---|---|---|
| `fantasy` | `localize` — Drop JP honorifics, use English equivalents (Lord, Lady, Sir) | `given_family` — Western first-name order | Madan no Ou (25d9/15c4) |
| `modern_japan` | `retain` — Keep -san, -kun, -chan, -sama, -sensei, -senpai | `family_given` — Japanese surname-first order | Otonari Asobi (25b4) |
| `historical_japan` | `retain` — Keep honorifics + period-specific titles (殿→-dono, 御前→gozen) | `family_given` | — |
| `isekai` | `localize` — Drop JP honorifics in fantasy world; may retain for Japanese-origin protagonist | `given_family` (fantasy world), `family_given` (Japan flashbacks) | — |
| `mixed` | Per-character override via `exceptions` array | Per-character override | — |

**Exception Handling — Modern Japan Example (Otonari no Tenshi-sama / 25b4):**

```json
"world_setting": {
  "type": "modern_japan",
  "label": "Contemporary Japanese High School",
  "honorifics": {
    "mode": "retain",
    "policy": "Keep all JP honorifics (-san, -kun, -chan, -sama, -senpai, -sensei). Attach to family name by default."
  },
  "name_order": {
    "default": "family_given",
    "policy": "Japanese surname-first order for Japanese characters."
  },
  "exceptions": [
    {
      "character_jp": "シャルロット",
      "character_en": "Charlotte",
      "reason": "Foreign exchange student (French)",
      "honorifics_override": "retain",
      "name_order_override": "given_family",
      "notes": "Other characters may still attach -san/-chan to her given name (Charlotte-san)."
    },
    {
      "character_jp": "エマ",
      "character_en": "Emma",
      "reason": "Foreign character (Western)",
      "honorifics_override": "retain",
      "name_order_override": "given_family",
      "notes": "Uses given-name order per Western convention."
    }
  ]
}
```

> **Key Design Principle:** `world_setting` governs the _default_ honorific and name-order policy for the entire series. The `exceptions` array provides per-character overrides without breaking the global rule. This means the translator prompt can be dynamically assembled: the global policy goes into the system instruction header, and exceptions are injected per-character in the glossary/profile section.

### 3.3 Index Registry

`pipeline/bibles/index.json` — The controller's brain:

```json
{
  "version": "1.0",
  "last_updated": "2026-02-09T14:30:00Z",
  "series": {
    "madan_no_ou_to_vanadis": {
      "bible_file": "madan_no_ou_to_vanadis.json",
      "match_patterns": [
        "魔弾の王と戦姫",
        "Madan no Ou to Vanadis",
        "Lord Marksman and Vanadis"
      ],
      "volumes": ["25d9", "15c4"],
      "entry_count": 147,
      "last_updated": "2026-02-09T14:30:00Z"
    }
  }
}
```

**`match_patterns`** are checked against `metadata.series` and `metadata.title` during auto-resolution. Supports both Japanese and romanized forms.

### 3.4 Resolution Flow

```
TranslatorAgent.__init__(work_dir)
    │
    ├── 1. Load manifest.json
    │
    ├── 2. BibleController.load(manifest, work_dir)
    │       │
    │       ├── Check manifest.bible_id → direct lookup
    │       ├── Check volume_id in index.volumes[] → reverse lookup
    │       ├── Match metadata.series against index.match_patterns
    │       └── Fuzzy match metadata.title against patterns
    │       │
    │       ▼
    │   Returns SeriesBible or None
    │
    ├── 3. IF bible found:
    │       │
    │       ├── bible.flat_glossary() → bible_terms: Dict[str, str]
    │       ├── manifest character_names → volume_terms: Dict[str, str]
    │       ├── merged = {**bible_terms, **volume_terms}  # volume overrides
    │       │
    │       ├── GlossaryLock(work_dir, bible_glossary=merged)
    │       ├── prompt_loader.set_glossary(merged)
    │       │
    │       └── bible.get_character_profiles() → enrich semantic_metadata
    │
    ├── 4. ELSE (no bible — standalone volume):
    │       │
    │       └── Existing behavior: character_names from manifest only
    │
    └── 5. Continue with prompt building, processor init...
```

---

## 4. Architecture: Continuity Metadata Overhaul

### 4.1 Transform Layer Fix

**File:** `agent.py` → `_transform_character_profiles()`

**Problem:** Only extracts 8 of 14 profile fields. Also swaps `name_en`/`name_kanji`.

**Fix:** Pass through all fields, fix the name swap:

```python
def _transform_character_profiles(self, profiles: Dict) -> List[Dict]:
    characters = []
    for jp_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        
        pronouns_raw = profile.get('pronouns', '')
        if not isinstance(pronouns_raw, str):
            pronouns_raw = str(pronouns_raw)
        
        char = {
            # FIX: jp_name IS the kanji name, full_name is the EN name
            'name_kanji': jp_name,
            'name_en': profile.get('full_name', jp_name),
            'nickname': profile.get('nickname', ''),
            'role': profile.get('relationship_to_protagonist', 'supporting'),
            'gender': ('female' if 'she/her' in pronouns_raw 
                       else 'male' if 'he/him' in pronouns_raw 
                       else 'unknown'),
            'age': profile.get('age', 'unknown'),
            'origin': profile.get('origin', ''),
        }
        
        # Pronouns (parsed)
        if 'she/her' in pronouns_raw.lower():
            char['pronouns'] = {'subject': 'she', 'object': 'her', 'possessive': 'her'}
        elif 'he/him' in pronouns_raw.lower():
            char['pronouns'] = {'subject': 'he', 'object': 'him', 'possessive': 'his'}
        
        # === PREVIOUSLY DROPPED FIELDS — NOW PRESERVED ===
        
        # RTAS Relationships → structured relationships
        rtas = profile.get('rtas_relationships', [])
        if rtas and isinstance(rtas, list):
            char['relationships'] = {}
            for rel in rtas:
                if isinstance(rel, dict):
                    target = rel.get('target', '')
                    char['relationships'][target] = {
                        'type': rel.get('relationship_type', ''),
                        'rtas_score': rel.get('rtas_score', 0),
                        'contraction_rate': rel.get('contraction_rate_override', None),
                        'notes': rel.get('notes', '')
                    }
        elif 'relationship_to_others' in profile:
            char['relationships'] = {'context': profile['relationship_to_others']}
        
        # Keigo switch (pass through)
        keigo = profile.get('keigo_switch', {})
        if keigo:
            char['keigo_switch'] = keigo
        
        # Contraction rate (pass through)
        contraction = profile.get('contraction_rate', {})
        if contraction:
            char['contraction_rate'] = contraction
        
        # How character refers to others (pass through)
        refers = profile.get('how_character_refers_to_others', {})
        if refers:
            char['how_refers_to_others'] = refers
        
        # Notes (personality, traits, appearance)
        notes = []
        if 'personality_traits' in profile:
            traits = profile['personality_traits']
            if isinstance(traits, list):
                notes.append(f"Personality: {', '.join(traits)}")
            else:
                notes.append(f"Personality: {traits}")
        if 'key_traits' in profile:
            notes.append(f"Key traits: {profile['key_traits']}")
        if 'appearance' in profile:
            notes.append(f"Appearance: {profile['appearance']}")
        if notes:
            char['notes'] = ' | '.join(notes)
        
        # Character arc
        for key in profile:
            if key.startswith('character_arc'):
                char['character_arc'] = profile[key]
                break
        
        characters.append(char)
    
    return characters
```

### 4.2 Prompt Formatter Enhancement

**File:** `prompt_loader.py` → `_format_semantic_metadata()`

**Problem:** Only renders name, role, gender, age, pronouns, notes. Ignores keigo, contraction, RTAS, nicknames, refers-to-others.

**Fix:** Render all rich fields in a format the LLM can act on:

```python
# After existing lines for name/role/gender/age/pronouns...

# Nickname (NEW)
nickname = char.get('nickname', '')
if nickname:
    name_display = f"{name_display} ({nickname})"

# Origin (NEW)
origin = char.get('origin', '')
if origin:
    lines.append(f"  Origin: {origin}")

# Keigo Switch (NEW)
keigo = char.get('keigo_switch', {})
if keigo:
    speaking_to = keigo.get('speaking_to', {})
    if speaking_to:
        lines.append(f"  Register Shifts:")
        for target, register in list(speaking_to.items())[:8]:
            contraction_info = ""
            cr = char.get('contraction_rate', {})
            if isinstance(cr, dict):
                st = cr.get('speaking_to', {})
                if target in st:
                    contraction_info = f" (contraction: {st[target]})"
            lines.append(f"    → {target}: {register}{contraction_info}")

# How Refers To Others (NEW)
refers = char.get('how_refers_to_others', {})
if refers:
    lines.append(f"  Refers To Others:")
    for jp_target, ref_pattern in list(refers.items())[:8]:
        lines.append(f"    → {ref_pattern}")

# RTAS Relationships (NEW)
relationships = char.get('relationships', {})
if relationships and isinstance(relationships, dict):
    # Skip if it's just the legacy {'context': ...} format
    if 'context' not in relationships:
        lines.append(f"  Key Relationships:")
        for target, rel_data in list(relationships.items())[:6]:
            if isinstance(rel_data, dict):
                rtype = rel_data.get('type', '')
                score = rel_data.get('rtas_score', '')
                rnotes = rel_data.get('notes', '')
                score_str = f" ({score})" if score else ""
                lines.append(f"    → {target}: {rtype}{score_str} — {rnotes}")
            else:
                lines.append(f"    → {target}: {rel_data}")
```

**Sample output after fix (what LLM will see):**

```
=== CHARACTER PROFILES (Full Semantic Data) ===

【ティグルヴルムド＝ヴォルン → Tigrevurmud Vorn (Tigre)】
  Role: protagonist
  Gender: male, Age: 16
  Origin: Brune
  Pronouns: he/him
  Register Shifts:
    → Ellen: casual_affectionate (contraction: 0.9)
    → King Faron: polite_formal (contraction: 0.6)
    → Soldiers: casual_commanding (contraction: 0.9)
    → Enemies: direct_challenging (contraction: 0.7)
  Refers To Others:
    → エレオノーラ様 (Eleonora-sama) -> エレン (Ellen)
    → リュドミラ様 (Ludmila-sama) -> ミラ (Mila)
    → マスハス卿 (Sir Mashas)
  Key Relationships:
    → エレオノーラ: romantic_interest (4.5) — Deeply cares for, intimate when alone
    → リュドミラ: ally (3.8) — Initially wary, grows to trust
    → バートラン: loyal_retainer_father_figure (4.5) — Deep respect, like family
  Notes: Personality: kind-hearted, responsible, self-deprecating, strategic_archer
```

### 4.3 Schema Unification

**Current:** Three schema variants competing in `_extract_semantic_metadata()`.

**Proposed:** One canonical path:

| Status | Schema | Detection | Action |
|--------|--------|-----------|--------|
| **PRIMARY** | Legacy V2 (`character_profiles`) | `character_profiles` key in metadata_en | Fixed transform → prompt |
| **KEEP** | Enhanced v2.1 (`characters`) | `characters` key present | Direct use (no transform needed) |
| **REMOVE** | V4 nested (`character_names` with dict values) | `character_names` values are dicts | Dead code — remove |

The Legacy V2 format is the richest and most actively used. The fixed transform preserves all its data. v2.1 stays as a passthrough for any future direct-format volumes. V4 nested is removed — nothing generates it, nothing uses it.

---

## 5. Implementation Plan

### 5.1 Phase 0: Hotfix (Transform + Formatter) ✅ COMPLETE

**Goal:** Fix the data loss bug so all existing volumes immediately benefit.  
**Risk:** Low — additive changes only, no API changes.  
**Status:** ✅ Implemented and validated. 56/56 checks passed.

| # | Task | File | Status |
|---|------|------|--------|
| 0.1 | Fix `_transform_character_profiles()` — preserve all rich fields, fix name swap | `agent.py` | ✅ |
| 0.2 | Fix `_format_semantic_metadata()` — render keigo, RTAS, contraction, nickname, refers-to-others | `prompt_loader.py` | ✅ |
| 0.3 | Remove V4 nested schema path | `agent.py` | ✅ |
| 0.4 | Fix `_extract_dialogue_patterns()` — use RTAS-derived patterns, not hardcoded phrase lists | `agent.py` | ✅ |

### 5.2 Phase A: Bible Infrastructure ✅ COMPLETE

**Goal:** Create the bible system — file structure, data model, controller.  
**Risk:** None — new code, no existing behavior changed.  
**Status:** ✅ `series_bible.py` (~985 lines), index.json, config.yaml updated. 56/56 checks passed.

| # | Task | File | Status |
|---|------|------|--------|
| A.1 | Create `pipeline/bibles/` directory | — | ✅ |
| A.2 | Create `pipeline/bibles/index.json` (registry) | New file | ✅ |
| A.3 | Create `SeriesBible` class | `series_bible.py` | ✅ |
| A.4 | Create `BibleController` class | `series_bible.py` | ✅ |
| A.5 | Add `bibles:` config section to `config.yaml` | `config.yaml` | ✅ |

### 5.3 Phase B: Madan Bible Seed ✅ COMPLETE

**Goal:** Seed the prototype bible from existing manifest data.  
**Status:** ✅ 121 entries (73 chars, 26 geo, 9 weapons, 3 orgs, 7 cultural, 3 mythology). world_setting: fantasy/localize/given_family.

| # | Task | File | Status |
|---|------|------|--------|
| B.1 | Create `madan_no_ou_to_vanadis.json` | `bibles/` | ✅ |
| B.2 | Seed from V1 (25d9) manifests (84 character_names) | Script | ✅ |
| B.3 | Seed from V2 (15c4) manifests (87 character_names + geography + weapons) | Script | ✅ |
| B.4 | Register in `index.json` with match_patterns | `index.json` | ✅ |

### 5.4 Phase C: Pipeline Integration ✅ COMPLETE

**Goal:** Wire the bible system into the translation pipeline.  
**Risk:** Medium — modifies hot path in `agent.py`. Backward-compatible (no `bible_id` = no change).  
**Status:** ✅ 16/16 checks passed. 87→118 locked names (+31 from bible), 3,630-char bible block in system prompt.

| # | Task | File | Status |
|---|------|------|--------|
| C.1 | Modify `agent.py` `__init__()` — load bible before glossary | `agent.py` | ✅ |
| C.2 | Modify `GlossaryLock.__init__()` — accept `bible_glossary` param | `glossary_lock.py` | ✅ |
| C.3 | Add `set_bible_prompt()` to prompt_loader | `prompt_loader.py` | ✅ |
| C.4 | Add `bible_id` field to 25d9 and 15c4 manifests | 2 manifest files | ✅ |

### 5.5 Phase D: CLI & Tooling ✅ COMPLETE

**Goal:** Add `mtl bible` subcommand group for managing bibles.  
**Risk:** Low — additive CLI, no existing commands changed.  
**Status:** ✅ 8 subcommands, 13/13 checks passed + 4 end-to-end runs.

| # | Command | File | Status |
|---|---------|------|--------|
| D.1 | `mtl bible list` | `bible_commands.py` | ✅ |
| D.2 | `mtl bible show <bible_id>` | `bible_commands.py` | ✅ |
| D.3 | `mtl bible validate <bible_id>` | `bible_commands.py` | ✅ |
| D.4 | `mtl bible import <volume_id>` | `bible_commands.py` | ✅ |
| D.5 | `mtl bible link <volume_id> [--bible <id>]` | `bible_commands.py` | ✅ |
| D.6 | `mtl bible unlink <volume_id>` | `bible_commands.py` | ✅ |
| D.7 | `mtl bible orphans` | `bible_commands.py` | ✅ |
| D.8 | `mtl bible prompt <bible_id>` | `bible_commands.py` | ✅ |

### 5.6 Phase E: Categorized Prompt Injection ✅ COMPLETE

**Goal:** Enhance prompt injection with world-setting directive at TOP, categorized bible block BEFORE glossary, and glossary deduplication.  
**Risk:** Low — additive enhancement to existing injection flow.  
**Status:** ✅ 8/8 checks passed.

| # | Task | File | Status |
|---|------|------|--------|
| E.1 | Add `_bible_world_directive` slot to prompt_loader | `prompt_loader.py` | ✅ |
| E.2 | Inject world directive at TOP of system instruction | `prompt_loader.py` | ✅ |
| E.3 | Glossary deduplication — skip terms already in bible block | `prompt_loader.py` | ✅ |
| E.4 | Agent passes `world_directive` + `bible_glossary_keys` to prompt_loader | `agent.py` | ✅ |
| E.5 | `set_bible_prompt()` accepts 3 params: prompt, directive, dedup keys | `prompt_loader.py` | ✅ |

**Prompt injection order (final):**
```
1. <!-- WORLD SETTING DIRECTIVE -->     ← TOP (one-line binding rule)
   [World: Medieval European Fantasy] | Honorifics: DROP all JP → ...

2. [Master Prompt + Modules]            ← Existing system instruction

3. <!-- SERIES BIBLE: ... (CACHED) -->  ← Categorized (3,630 chars for Madan)
   === WORLD SETTING ===
   === CHARACTERS ===
   === GEOGRAPHY ===
   === WEAPONS/ARTIFACTS ===
   ...

4. <!-- GLOSSARY — Volume-Specific -->  ← Only non-bible terms (deduplicated)

5. <!-- SEMANTIC METADATA -->           ← Character profiles with full RTAS data
```

### 5.7 Phase F: Migration & Validation (Future)

**Goal:** Migrate existing multi-volume series, clean up dead code.  
**Risk:** Medium — removes legacy code.  
**Status:** Deferred — run when ready to onboard remaining 13 multi-volume series.

| # | Task | File | Description |
|---|------|------|-------------|
| F.1 | Run `mtl bible auto-link` on all 68 WORK/ volumes | CLI | Auto-detect series groupings |
| F.2 | Create bibles for top series (孤高の華, 貴族令嬢, 幼馴染の妹, etc.) | Script | Seed from manifests |
| F.3 | Fix series_index fallback in metadata_parser.py | `metadata_parser.py` | ~5 lines |
| F.4 | Delete dead `.context/` directories | Manual | Cleanup |
| F.5 | Mark `continuity_manager.py` as deprecated | `continuity_manager.py` | Module docstring |
| F.6 | Remove `enable_continuity` parameter from agent.py | `agent.py` | ~20 lines |
| F.7 | Remove dead continuity merge block | `agent.py` | ~40 lines |

---

## 6. File Change Matrix

| File | Phase | Action | Status |
|------|-------|--------|--------|
| **agent.py** (1,510 lines) | 0, C, E | Fix transform, load bible, pass world directive | ✅ Done |
| **prompt_loader.py** (2,354 lines) | 0, C, E | Fix formatter, bible injection, world directive, glossary dedup | ✅ Done |
| **glossary_lock.py** (~220 lines) | C | Accept `bible_glossary` param | ✅ Done |
| **series_bible.py** (NEW, 985 lines) | A | SeriesBible + BibleController | ✅ Done |
| **bible_commands.py** (NEW, ~300 lines) | D | 8 CLI handlers for `mtl bible` | ✅ Done |
| **parser.py** (310 lines) | D | `bible` subparser with sub-subparsers | ✅ Done |
| **dispatcher.py** (70 lines) | D | Register `bible` in HANDLERS | ✅ Done |
| **config.yaml** | A | Add `bibles:` config section | ✅ Done |
| **bibles/index.json** (NEW) | A | Registry with Madan registered | ✅ Done |
| **bibles/madan_no_ou_to_vanadis.json** (NEW) | B | 121 entries, world_setting | ✅ Done |
| **25d9 manifest.json** | C | Added `bible_id` | ✅ Done |
| **15c4 manifest.json** | C | Added `bible_id` | ✅ Done |
| **chapter_processor.py** | — | No changes needed | — |
| **continuity_manager.py** | F | Deprecate entire module | Deferred |
| **metadata_parser.py** | F | series_index fallback | Deferred |

**Total new code:** ~1,285 lines (series_bible.py + bible_commands.py)  
**Total modified:** ~250 lines across 5 files  
**Validation:** 56 + 16 + 13 + 8 = **93 automated checks passed**

---

## 7. Risk Assessment

### High Confidence (Low Risk)

| Change | Why Low Risk |
|--------|-------------|
| Phase 0 (transform + formatter) | Additive — adds fields to output, doesn't change any API signatures |
| Phase 1 (bible infrastructure) | Entirely new files — zero impact on existing pipeline |
| Phase 3 (CLI) | New commands — no existing commands modified |

### Medium Confidence (Moderate Risk)

| Change | Risk | Mitigation |
|--------|------|------------|
| Phase 2.1 (agent.py bible loading) | Could fail to load bible → fall through to existing behavior | Resolution returns `None` on any failure → backward compatible |
| Phase 2.2 (GlossaryLock bible_glossary) | Bible terms could conflict with manifest terms | Volume terms override bible on conflict (explicit > inherited) |
| Phase 2.3 (prompt injection change) | Categorized glossary block could confuse LLM | Keep flat fallback; categorized is opt-in via `bible.format_for_prompt()` |

### Backward Compatibility Guarantee

- **Volumes without `bible_id`:** Zero behavioral change. `BibleController.load()` returns `None`, existing glossary path executes.
- **Volumes with `bible_id` but bible deleted:** `BibleController.load()` logs warning, returns `None`, falls back to manifest-only.
- **All changes gated by bible existence:** No bible → no change.

---

## 8. Appendix: Workspace Series Inventory

### Multi-Volume Series (Bible Status)

| # | Series | Vols | Chars | Status |
|---|--------|------|-------|--------|
| 1 | 魔弾の王と戦姫 (Lord Marksman and Vanadis) | 3 (25d9, 15c4, 0721) | 136 | ✅ **DONE** — Phase B seed + manual curation |
| 2 | この中に1人、妹がいる! (NAKAIMO) | 5 | 42 | ✅ Auto-built |
| 3 | 孤高の華…英国美少女 (British Ice Queen) | 4 | 22 | ✅ Auto-built |
| 4 | 幼馴染の妹の家庭教師をはじめたら (Tutoring Sister) | 4 | 22 | ✅ Auto-built |
| 5 | 貴族令嬢。俺にだけなつく (Noble Lady) | 4 | 44 | ✅ Auto-built (fantasy) |
| 6 | 男嫌いな美人姉妹を名前も告げずに助けたら (Man-Hating Beauties) | 3 | 76 | ✅ Auto-built |
| 7 | 俺の背徳メシ (Idol Next Door) | 3 | 19 | ✅ Auto-built |
| 8 | 迷子になっていた幼女を助けたら (Lost Little Girl) | 3 (0b24, 0fa9, 0a51) | 7 | ✅ Auto-built + manual 0fa9 merge |
| 9 | 他校の氷姫を助けたら (Ice Princess) | 2 (1d46, 1ab4) | 24 | ✅ Manual build |
| 10 | クラスで２番目に可愛い女の子 (2nd Cutest) | 2 | 60 | ✅ Auto-built |
| 11 | 義妹生活 (Days with my Step Sister) | 2 | 7 | ✅ Auto-built |
| 12 | 油断できない彼女 (My Girlfriend) | 2 | 13 | ✅ Auto-built |
| 13 | 君に届け (Kimi ni Todoke) | 2 | 3 | ✅ Auto-built |
| 14 | 俺のスマホに心の声が漏れちゃう (Smartphone Beauties) | 2 | 12 | ✅ Auto-built |
| 15 | 学園一かわいい後輩 (Cutest Kouhai) | 2 | 0 | ✅ Auto-built |
| 16 | 学年一の金髪碧眼美少女 (Golden Girl) | 2 | 2 | ✅ Auto-built |
| 17 | 幼なじみは負けフラグ (Childhood Friend Flag) | 2 | 11 | ✅ Auto-built |
| 18 | 負けヒロインと俺が付き合っていると (Losing Heroine) | 2 | 26 | ✅ Auto-built |
| 19 | 隣国から来た嫁 (Neighboring Kingdom Bride) | 2 | 43 | ✅ Auto-built (fantasy) |

**Totals:** 19 series, 49 volumes linked, 569 character entries (136 curated + 433 auto-seeded)

### Standalone Volumes (No Bible Needed)

~26 single volumes with no sequel detected in WORK/.

---

## 9. Implementation Completion Summary

**Date completed:** 2026-02-09  
**Total phases:** 7 implemented (Phase 0 → E + Auto-Sync), 1 deferred (Phase F)

### What was built:

1. **Series Bible Engine** (`series_bible.py`, 985 lines) — `SeriesBible` + `BibleController` classes with full CRUD, import, validation, resolution, and prompt generation.

2. **Madan Bible** (`madan_no_ou_to_vanadis.json`, 121→136 entries) — Prototype bible seeded from V1+V2 manifests. 73+ characters, 26 geography, 9 weapons, 3 orgs, 7 cultural, 3 mythology. World setting: Medieval European Fantasy / localize honorifics / given-family names.

3. **Pipeline Integration** — Agent loads bible → supplements GlossaryLock → injects categorized prompt block into system instruction. World directive at TOP, categorized bible BEFORE glossary, glossary deduplication active.

4. **CLI Tooling** (`bible_commands.py`, ~500 lines) — 9 subcommands: `list`, `show`, `validate`, `import`, `link`, `unlink`, `orphans`, `prompt`, `sync`. Full parser + dispatcher integration.

5. **Phase E Enhancement** — World setting directive injected as top-level binding rule. Glossary deduplication eliminates 118 redundant terms when bible is active.

6. **Bible Auto-Sync** (`bible_sync.py`, ~340 lines) — Two-way sync during Phase 1.5 metadata processing. PULL: inherit 133 canonical terms from bible before ruby translation. PUSH: export newly discovered terms back to bible after final manifest write. Also accessible via `mtl bible sync <volume_id>`.

### What it solved:

- **"Zxtat" incident:** Eliminated. All 136 canonical terms locked via bible.
- **Cross-volume drift:** Bible shared across volumes. One truth per series.
- **Character profile data loss:** Phase 0 fixed transform to preserve all 14 fields.
- **Dead continuity system:** Superseded by bible system (deprecation in Phase F).
- **Stale bible problem:** Auto-sync keeps bible current as each volume is processed.

### Backward compatibility:

- Volumes without `bible_id`: **Zero behavioral change.**
- Bible system errors: **Non-fatal**, falls back to manifest-only path.
- Auto-sync errors: **Non-fatal**, wrapped in try/except, logs warning and continues.
- 75 orphan volumes identified via `mtl bible orphans` — ready for future linking.

---

## 10. Bible Auto-Sync Architecture (Phase 1.5 Enhancement)

**Date implemented:** 2026-02-09  
**Module:** `pipeline/metadata_processor/bible_sync.py`

### Problem

The bible was only updated manually via `mtl bible import`. When processing new volumes, the Translator in Phase 2 could encounter terms not yet in the bible, while the bible might have canonical terms unknown to the current volume's manifest.

### Solution: Two-Way Sync During Phase 1.5

```
Phase 1.5 Flow (with Bible Sync):
┌───────────────────────────────────────────────────────────┐
│ _run_schema_autoupdate()    ← Gemini enriches profiles    │
│                                                           │
│ ★ BIBLE PULL ★                                            │
│   Load bible → inject 133 canonical terms                 │
│   Pre-populate character_names for ruby skip list         │
│   Build context block for Gemini prompt                   │
│                                                           │
│ _batch_translate_ruby()     ← Skip known bible names      │
│ Gemini title/chapter translation (with bible context)     │
│ _update_manifest_preserve_schema()                        │
│ Final manifest write                                      │
│                                                           │
│ ★ BIBLE PUSH ★                                            │
│   Compare manifest vs bible                               │
│   Push new characters → bible.add_entry()                 │
│   Enrich existing characters ← profiles                   │
│   Register volume in bible                                │
│   Save bible + update index                               │
└───────────────────────────────────────────────────────────┘
```

### PULL (Bible → Manifest)

Runs after `_run_schema_autoupdate()`, before `_batch_translate_ruby()`.

1. Resolve bible via `BibleController.load(manifest)`
2. Extract `flat_glossary()` — all 133 canonical JP→EN terms
3. Pre-populate `name_registry` with bible character names (ruby translation skips these)
4. Build "SERIES BIBLE — CANONICAL TERMS" context block for Gemini prompt
5. Inject bible `character_names` into manifest's `metadata_en.character_names`

### PUSH (Manifest → Bible)

Runs after the final `manifest.json` write.

1. Compare `metadata_en.character_names` vs bible's `characters`
2. New names → `bible.add_entry('characters', jp, {canonical_en, source: 'phase1.5_auto_sync'})`
3. Existing characters → enrich with profile data (nickname, category, affiliation, keigo)
4. Conflicts → bible wins (canonical), logged as warnings
5. Register volume → `bible.register_volume()`
6. Save bible + update index entry count

### CLI Access

```bash
mtl bible sync <volume_id>                    # Full sync (pull + push)
mtl bible sync <volume_id> --direction pull    # Pull only (bible → manifest)
mtl bible sync <volume_id> --direction push    # Push only (manifest → bible)
```

### Safety

- All sync operations wrapped in try/except — non-fatal on failure
- Bible is canonical: conflicts always resolved in bible's favor
- PULL is additive (bible terms as base, manifest overrides for new chars)
- PUSH never overwrites existing bible entries (add new + enrich only)

### Test Results

```
PULL: 133 terms (characters=88, geography=26, weapons=9, other=10)
  Manifest char_names: 87 → 88 (1 bible term injected)
PUSH: added=0, enriched=4, skipped=88, volume=registered
  Total changes: 4 (profile enrichments)
```

---

*End of report.*
