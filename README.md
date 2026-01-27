# MTL Studio

**Machine Translation Publishing Pipeline for Japanese Light Novels**

Version 3.0 LTS | Production Ready | January 2026

> Multi-Language Support: English & Vietnamese | V3 Enhanced Schema | AI-Powered QC | Interactive CLI

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Pipeline Phases](#pipeline-phases)
4. [Installation](#installation)
5. [Quick Start](#quick-start)
6. [CLI Reference](#cli-reference)
7. [Configuration](#configuration)
8. [Publisher Profiles System](#publisher-profiles-system)
9. [File Structure](#file-structure)
10. [RAG Modules](#rag-modules)
11. [Quality Control](#quality-control)
12. [Troubleshooting](#troubleshooting)
13. [API Reference](#api-reference)
    - [Manifest Schema](#manifest-schema)
    - [Name Registry Schema](#name-registry-schema)
    - [Semantic Metadata Schema](#semantic-metadata-schema)
14. [Performance Statistics](#performance-statistics)

---

## Overview

MTL Studio is a complete automated pipeline for translating Japanese Light Novel EPUBs to professional multi-language editions. The system leverages Google Gemini AI (2.5 Pro/Flash) with retrieval-augmented generation (RAG) to produce publication-quality translations with consistent character voices, proper typography, and accurate terminology.

### Core Capabilities

- **End-to-End Automation**: Single command transforms Japanese EPUB to translated EPUB
- **Multi-Language Support**: Full English and Vietnamese translation pipelines
- **RAG-Enhanced Translation**: 2.5MB+ knowledge base for context-aware translation
- **Intelligent Typography**: Professional quotation marks, em-dashes, ellipses
- **Illustration Management**: Automatic extraction, orientation detection, semantic insertion
- **Sequel Intelligence**: Character names and terminology inherit across volumes
- **Multi-Publisher Support**: KADOKAWA, Overlap, SB Creative, Hifumi Shobo, Hobby Japan, Media Factory, Shueisha
- **Publisher Pattern Database**: 65+ documented EPUB structure patterns across 7 major publishers
- **Automatic Publisher Detection**: Pattern-based image classification without hardcoded logic
- **AI-Powered QC**: Gemini CLI agent for auditing, formatting fixes, and illustration insertion
- **Interactive CLI**: Volume selection menus, configuration management, verbose mode
- **Post-Processing**: CJK artifact removal, format normalization, smart typography

### Translation Quality Standards

| Metric | Target | Description |
|--------|--------|-------------|
| Contraction Rate | 80%+ | Natural dialogue flow |
| AI-ism Count | <5/chapter | Elimination of translationese |
| Victorian Patterns | 0 | No archaic phrasing (with ojou-sama exceptions) |
| Name Consistency | 100% | Ruby-verified romanization |
| Content Fidelity | <5% deviation | 1:1 faithful to source |
| Character Voice | FFXVI-Tier | Distinct speech patterns per archetype |

---

## System Architecture

```
                                WORKSPACE/
                                   │
    ┌─────────────────────────────┼─────────────────────────────┐
    │                             │                             │
    ▼                             ▼                             ▼
┌─────────┐    JSON         ┌─────────┐    JSON         ┌─────────┐
│  INPUT/ │ ─────────────►  │  WORK/  │ ─────────────►  │ OUTPUT/ │
│ (EPUB)  │                 │ (MD+JSON)│                │ (EPUB)  │
└─────────┘                 └─────────┘                 └─────────┘
    │                             │                             ▲
    │                             │                             │
    ▼                             ▼                             │
┌─────────────┐            ┌─────────────┐            ┌─────────────┐
│  LIBRARIAN  │───────────►│  METADATA   │───────────►│ TRANSLATOR  │
│   (Python)  │            │  PROCESSOR  │            │(Gemini API) │
└─────────────┘            └─────────────┘            └──────┬──────┘
                                                              │
                                                              ▼
┌─────────────┐                                        ┌─────────────┐
│   BUILDER   │◄───────────────────────────────────────│   CRITICS   │
│   (Python)  │                                        │ (IDE Agent) │
└─────────────┘                                        └─────────────┘
      │
      ▼
┌─────────────┐
│  final.epub │
└─────────────┘
```

### Agent Communication Protocol

Agents communicate through a file-based protocol using `manifest.json` as the central state machine. Each agent reads the manifest, verifies predecessor completion, performs its work, and updates the manifest with its status.

```
LIBRARIAN completes → manifest.json (librarian.status = "completed")
                    → JP/*.md files created
                    
METADATA PROCESSOR  → manifest.json (metadata_processor.status = "completed")
                    → metadata_en.json created
                    
TRANSLATOR reads    → checks librarian.status == "completed"
                    → EN/*.md files created
                    → manifest.json (translator.status = "completed")
                    
CRITICS reads       → checks translator.status == "completed"
                    → QC/*.json reports created
                    
BUILDER reads       → assembles EPUB from all resources
                    → OUTPUT/[title]_EN.epub
```

---

## Pipeline Phases

### Phase 1: Librarian

**Purpose**: Extract, parse, and catalog Japanese EPUB content

**Components**:
- `epub_extractor.py` - EPUB unpacking and structure analysis
- `metadata_parser.py` - OPF metadata extraction
- `content_parser.py` - XHTML to Markdown conversion
- `ruby_extractor.py` - Character name extraction with furigana
- `image_extractor.py` - Asset cataloging and normalization

**Output Structure**:
```
WORK/[volume_id]/
├── manifest.json           # Book metadata + pipeline state
├── JP/                     # Japanese source (Markdown)
│   ├── CHAPTER_01.md
│   ├── CHAPTER_02.md
│   └── ...
├── EN/                     # English translations (populated by Translator)
├── QC/                     # QC reports (populated by Critics)
├── _assets/
│   ├── cover.jpg
│   ├── kuchie/
│   │   └── kuchie-001.jpg
│   └── illustrations/
│       └── illust-001.jpg
└── .context/
    └── name_registry.json  # Character name mappings
```

### Phase 1.5: Metadata Processor

**Purpose**: Translate and localize book metadata

**Responsibilities**:
- Translate main title with creative localization
- Romanize author/illustrator names (Standard Hepburn)
- Batch translate character names from ruby text
- Translate all chapter titles from TOC
- Detect sequels and inherit terminology

**Output**:
- `metadata_en.json` - Localized metadata configuration
- Updated `manifest.json` with English titles

### Phase 2: Translator

**Purpose**: Translate JP chapters to EN using Gemini API with RAG

**Translation Flow**:
```
┌─────────────┐    ┌──────────────────┐    ┌─────────────┐
│ JP/CHAPTER  │───►│   RAG Engine     │───►│ Gemini API  │
│    .md      │    │ (2.5MB modules)  │    │      │
└─────────────┘    └──────────────────┘    └──────┬──────┘
                            │                      │
                   ┌────────┴─────────┐           │
                   ▼                  ▼           ▼
             ┌──────────┐      ┌──────────┐ ┌──────────┐
             │Character │      │Localization│ │EN(VN)/CHAPTER│
             │ Voices   │      │  Primer   │ │   .md    │
             └──────────┘      └──────────┘ └──────────┘
```

**Key Features**:
- Context-aware translation with 2-chapter lookback
- Trope-aware Light Novel patterns
- Smart typography (curly quotes, em-dashes, proper ellipses)
- Character name consistency enforcement
- Safety block handling with fallback strategies

### Phase 3: Critics

**Purpose**: Quality control and revision via agentic IDE workflows

**QC Categories**:
1. **Semantic Analysis**: Meaning preservation, omission detection
2. **Technical Review**: AI-ism detection, contraction validation
3. **Style Compliance**: Character voice consistency, dialogue naturalness

**Grading Rubric**:
| Grade | Criteria |
|-------|----------|
| A+ | 0 critical issues, 0-1 warnings, 90%+ contractions, distinct character voices |
| A | 0 critical issues, 0-2 warnings, 90%+ contractions |
| B | 0-1 critical issues, 3-5 warnings, 80%+ contractions |
| C | 2-3 critical issues, 6-10 warnings, needs revision |
| D | 4+ critical issues, rewrite required |
| F | Major quality failure, blocks publication |

### Phase 4: Builder

**Purpose**: Assemble final EPUB from translated content

**Output Specifications**:
- EPUB 3.0 with EPUB 2.0 backward compatibility
- Dual navigation (nav.xhtml + toc.ncx)
- Automatic image orientation handling
- Professional English typography
- IDPF-compliant validation

**EPUB Structure**:
```
final.epub/
├── mimetype
├── META-INF/
│   └── container.xml
└── OEBPS/
    ├── content.opf
    ├── toc.ncx
    ├── nav.xhtml
    ├── Styles/
    │   └── style.css
    ├── Images/
    │   ├── cover.jpg
    │   └── *.jpg
    └── Text/
        ├── cover.xhtml
        ├── toc.xhtml
        └── chapter_*.xhtml
```

---

## Installation

### Prerequisites

- Python 3.10 or higher
- Google Gemini API key
- 10GB+ disk space for processing

### Automated Setup

**macOS/Linux**:
```bash
./scripts/setup_python_env.sh
```

**Windows**:
```batch
scripts\setup_python_env.bat
```

### Manual Setup

```bash
# Create virtual environment
python3 -m venv python_env

# Activate environment
source python_env/bin/activate  # Windows: python_env\Scripts\activate

# Install dependencies
pip install -r pipeline/requirements.txt
```

### API Configuration

Create `pipeline/.env`:

```bash
# Required
GEMINI_API_KEY=your-gemini-api-key

# Optional (for Claude integration)
ANTHROPIC_API_KEY=your-anthropic-api-key
```

**Obtaining Gemini API Key**:
1. Navigate to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create a new API key
3. Copy to `.env` file

### Verification

```bash
cd pipeline
python mtl.py list
```

---

## Quick Start

### Launch MTL Studio

**macOS/Linux**:
```bash
./Launch_Studio.sh
```

**Windows**:
```batch
Launch_Studio.bat
```

### Run Translation Pipeline

```bash
# Activate environment
source python_env/bin/activate

# Navigate to pipeline
cd pipeline

# Full pipeline (auto-pilot)
python mtl.py run INPUT/novel_v1.epub

# Full pipeline (verbose/interactive)
python mtl.py run INPUT/novel_v1.epub --verbose
```

### Pipeline Modes

**Minimal Mode (Default)**:
- Clean output with progress messages
- Auto-proceeds through all phases
- No interactive prompts
- Optimal for batch processing

**Verbose Mode (--verbose)**:
- Full details with interactive menus
- Metadata review options
- Sequel inheritance confirmation
- Phase-by-phase approval
- Recommended for first-time runs

---

## CLI Reference

### Core Commands

```bash
# Full pipeline
python mtl.py run INPUT/novel_v1.epub [--verbose] [--id custom_id]

# Individual phases
python mtl.py phase1 INPUT/novel_v1.epub [--id volume_id]
python mtl.py phase2 volume_id [--chapters 1,2,3] [--force]
python mtl.py phase4 volume_id

# Status and management
python mtl.py status volume_id
python mtl.py list

# Metadata schema inspection
python mtl.py metadata volume_id              # Quick schema detection
python mtl.py metadata volume_id --validate   # Full validation report

# Configuration
python mtl.py config --show
python mtl.py config --language en    # Switch to English
python mtl.py config --language vn    # Switch to Vietnamese
python mtl.py config --model gemini-2.5-pro
```

### Command Details

| Command | Description |
|---------|-------------|
| `run` | Execute full pipeline from EPUB input |
| `phase1` | Librarian: Extract EPUB to working directory |
| `phase2` | Translator: Translate chapters with Gemini |
| `phase4` | Builder: Package translated content to EPUB |
| `status` | Display volume processing status |
| `list` | List all volumes in WORK directory |
| `metadata` | Inspect metadata schema and validate translator compatibility |
| `config` | View or modify pipeline configuration |

### Options

| Option | Description |
|--------|-------------|
| `--verbose` | Enable interactive mode with confirmations |
| `--id` | Custom volume identifier |
| `--chapters` | Specific chapters to translate (comma-separated) |
| `--force` | Force re-translation of completed chapters |
| `--language` | Target language (en/vn) |
| `--model` | Gemini model to use |
| `--show` | Display current configuration |
| `--validate` | Run full metadata validation with detailed report |

### Interactive Features

- **Volume Selection**: Run `phase2` or `phase4` without volume_id for interactive menu
- **Partial IDs**: Use last 4 characters (e.g., `1b2e` instead of full name)
- **Ambiguous IDs**: Automatically shows selection menu when multiple matches found
- **Shell Menu**: Use `./start.sh` for full interactive TUI with all options

---

## Configuration

### Main Configuration (config.yaml)

```yaml
project:
  target_language: en   # or 'vn' for Vietnamese
  languages:
    en:
      master_prompt: prompts/master_prompt_en_compressed.xml
      modules_dir: modules/
      output_suffix: _EN
      language_code: en
    vn:
      master_prompt: VN/master_prompt_vn_pipeline.xml
      modules_dir: VN/modules/
      output_suffix: _VN
      language_code: vi

gemini:
  model: gemini-2.5-pro
  fallback_model: gemini-2.5-flash
  generation:
    temperature: 0.6
    top_p: 0.95
    top_k: 40
    max_output_tokens: 65535
    thinking_level: medium

translation:
  quality:
    contraction_rate_min: 0.8
    max_ai_isms_per_chapter: 5
  context:
    lookback_chapters: 2
    enforce_name_consistency: true

critics:
  auto_fix:
    enabled: true
    contractions: true
    punctuation: true
  thresholds:
    pass_min_score: 0.85

post_processing:
  format_normalizer:
    enabled: true
  cjk_cleaner:
    enabled: true

builder:
  epub_version: '3.0'
  images:
    cover_max_width: 1600
    illustration_max_width: 1200
    quality: 85

directories:
  input: INPUT/
  work: WORK/
  output: OUTPUT/
```

### Model Selection

| Model | Use Case | Performance |
|-------|----------|-------------|
| gemini-2.5-pro | Primary translation | Highest quality |
| gemini-2.5-flash | Fallback | Fast, reliable |
| gemini-2.0-flash-exp | Legacy fallback | Stable |

---

## Publisher Profiles System

MTL Studio includes a comprehensive reverse-engineered pattern database for major Japanese publishers, enabling automatic EPUB structure recognition and image classification.

### Supported Publishers

| Publisher | Patterns | Key Features |
|-----------|----------|--------------|
| **KADOKAWA** | 10 patterns | `gaiji` special chars, `p00X` kuchie, `allcover` spreads |
| **Media Factory** | 4 patterns | `o_` prefix system, `o_hyoushi.jpg` covers |
| **Overlap** | 6 patterns | `k###` kuchie, `k002-003.jpg` spreads |
| **SB Creative** | 5 patterns | `P000a/P000b` letter-suffixed kuchie |
| **Hifumi Shobo** | 7 patterns | `p002_003.jpg` spreads, spine fallback TOC |
| **Hobby Japan** | 3 patterns | Standard EPUB3 structure |
| **Shueisha** | 6 patterns | `embed####_HD.jpg`, spine-based kuchie extraction |

**Total Coverage**: 7 publishers, 65+ documented patterns, modular JSON-based system

### Pattern Categories

- **Cover Recognition**: 11 variations (including `allcover`, `hyoushi`, `frontcover`, `h1`)
- **Kuchie Detection**: 13 variations (including spine-based extraction for Shueisha)
- **Illustration Patterns**: 13 variations (with HD variants, prefix systems)
- **Exclusion Rules**: 2 patterns (`gaiji` special character glyphs)
- **Fallback Patterns**: 16 generic patterns for unknown publishers

### Unique Features Discovered

1. **Prefix Systems**: `o_` (Media Factory), `i-` (KADOKAWA), `P` uppercase (SB Creative)
2. **Spread Formats**: `k002-003.jpg`, `p002_003.jpg` (two-page illustrations)
3. **HD Variants**: Shueisha's dual-resolution system (`_HD` suffix vs standard)
4. **Spine-Based Extraction**: Kuchie embedded in XHTML spine entries (not Images/ folder)
5. **Letter Suffixes**: `P000a`, `P000b`, `p000z` for sequential color plates
6. **Japanese Names**: Automatic recognition of `hyoushi` (cover), `kuchie` (color plates)

### Publisher Profile Structure

Each publisher is documented in JSON format at `pipeline/librarian/publisher_profiles/`:

```json
{
  "canonical_name": "Publisher Name",
  "aliases": ["株式会社...", "English Name"],
  "country": "JP",
  "image_patterns": {
    "cover": [
      {"pattern": "regex", "priority": 1, "note": "explanation"}
    ],
    "kuchie": [...],
    "illustration": [...]
  },
  "content_patterns": {
    "toc_handling": "standard|spine_fallback|auto",
    "chapter_merging": true|false,
    "filename_pattern": "regex"
  }
}
```

### Benefits

- **Automatic Detection**: No manual configuration needed for supported publishers
- **Easy Maintenance**: Pattern updates tracked in version-controlled JSON files
- **Extensibility**: Add new publishers without code changes
- **Debugging Aid**: Compare actual files against documented patterns
- **Historical Record**: Test cases document verified volumes

---

## File Structure

```
MTL_Studio/
├── bin/                        # VSCodium portable executable
├── data/                       # VSCodium portable data
├── python_env/                 # Python virtual environment
├── pipeline/                   # Core pipeline system
│   ├── INPUT/                  # Source Japanese EPUBs
│   ├── WORK/                   # Processing workspace
│   │   └── [volume_id]/
│   │       ├── manifest.json
│   │       ├── JP/             # Japanese source
│   │       ├── EN/             # English translations
│   │       ├── VN/             # Vietnamese translations (if target=vn)
│   │       ├── QC/             # Quality reports
│   │       └── assets/         # Images
│   ├── OUTPUT/                 # Final translated EPUBs
│   ├── pipeline/               # Python modules
│   │   ├── librarian/          # Phase 1 extraction
│   │   ├── metadata/           # Phase 1.5 localization
│   │   ├── translator/         # Phase 2 translation
│   │   ├── builder/            # Phase 4 packaging
│   │   └── cli/                # Command interface
│   ├── modules/                # English RAG knowledge base
│   ├── VN/                     # Vietnamese translation resources
│   │   ├── modules/            # Vietnamese RAG modules
│   │   ├── Reference/          # Reference materials
│   │   └── master_prompt_vn_pipeline.xml
│   ├── scripts/                # Utility scripts
│   │   ├── mtl.py              # Extended CLI with TUI
│   │   ├── normalize_existing_volumes.py
│   │   ├── fix_name_order.py
│   │   └── ...(39 utility scripts)
│   ├── prompts/                # AI system prompts
│   ├── config.yaml             # Pipeline configuration
│   ├── start.sh                # Interactive TUI launcher
│   └── mtl.py                  # Main CLI entry point
├── VN/                         # External Vietnamese resources
├── AUDIT_AGENT.md              # Gemini CLI QC agent definition
├── Launch_Studio.sh            # Main launcher (macOS/Linux)
├── Launch_Studio.bat           # Main launcher (Windows)
└── README.md                   # This file
```

---

## RAG Modules

The translation system uses a 2.5MB retrieval-augmented generation knowledge base stored in `pipeline/modules/`:

| Module | Size | Purpose |
|--------|------|---------|
| MEGA_CORE_TRANSLATION_ENGINE.md | 100KB | Core translation rules and patterns |
| MEGA_CHARACTER_VOICE_SYSTEM.md | 27KB | Character archetype voice differentiation |
| MEGA_ELLIPSES_ONOMATOPOEIA_MODULE.md | 11KB | Japanese sound effect handling |
| Library_LOCALIZATION_PRIMER_EN.md | 78KB | Localization guidelines and examples |
| Library_REFERENCE_ICL_SAMPLES.md | 18KB | In-context learning examples |
| ANTI_FORMAL_LANGUAGE_MODULE.md | 17KB | Victorian pattern elimination |
| ANTI_EXPOSITION_DUMP_MODULE.md | 14KB | Natural prose flow |
| FANTASY_TRANSLATION_MODULE_EN.md | 19KB | Fantasy genre conventions |

### Vietnamese Translation Modules

The Vietnamese pipeline includes dedicated modules in `VN/modules/`:

| Module | Purpose |
|--------|---------|
| MEGA_CORE_TRANSLATION_ENGINE_VN.md | Core Vietnamese translation rules |
| MEGA_CHARACTER_VOICE_SYSTEM_VN.md | Vietnamese character voice patterns |
| ANTI_TRANSLATIONESE_MODULE_VN.md | Natural Vietnamese phrasing |
| Library_LOCALIZATION_PRIMER_VN.md | Vietnamese localization guidelines |
| Ref_ONOMATOPOEIA_PROTOCOL_v1.0.md | Onomatopoeia handling |

---

## Quality Control

### Automatic QC Features

- **Typography Fixes**: Smart quotes, em-dashes, ellipses standardization
- **Contraction Enforcement**: Expansion patterns detected and corrected
- **AI-ism Detection**: Victorian patterns, repetitive phrases flagged
- **Name Consistency**: Ruby text verification against translations

### QC Report Schema

```json
{
  "chapter": "CHAPTER_01",
  "timestamp": "2026-01-21T10:30:00Z",
  "verdict": "PASS",
  "scores": {
    "semantic_accuracy": 0.95,
    "naturalness": 0.88,
    "contraction_rate": 0.82,
    "voice_consistency": 0.91
  },
  "issues": [],
  "auto_fixes_applied": 3
}
```

### Gemini CLI Integration (AUDIT_AGENT.md)

The `AUDIT_AGENT.md` file defines an AI-powered QC agent with two modules:

**Module 1: Translation Audit**
- Victorian pattern detection (with ojou-sama exemptions)
- Contraction rate validation (80%+ target)
- AI-ism detection (FFXVI-tier zero tolerance)
- Character voice differentiation scoring
- 1:1 content fidelity validation (<5% deviation)
- Auto-fix for formatting violations

**Module 2: Illustration Insertion**
- Semantic matching with Japanese source context
- Dialogue and action sequence anchoring
- Position optimization for narrative beats

```bash
# Audit translated chapter
gemini -s AUDIT_AGENT.md 'Audit WORK/volume_id/EN/CHAPTER_01.md'

# Insert illustrations with semantic matching
gemini -s AUDIT_AGENT.md 'Insert illustrations for Chapter 3 in volume_id'
```

### Grading Rubric (FFXVI-Tier)

| Grade | Criteria |
|-------|----------|
| A+ | 0 critical, 0-1 warnings, 90%+ contractions, distinct voices, 0 AI-isms, <5% deviation |
| A | 0 critical, 0-2 warnings, 90%+ contractions, 0-1 AI-isms, 0 formatting issues |
| B | 0-1 critical, 3-5 warnings, 80%+ contractions, minor formatting (<10) |
| C | 2-3 critical, 6-10 warnings, 70%+ contractions, needs revision |
| F | Any name order errors OR >15% content deviation (blocks publication) |

---

## Troubleshooting

### Common Issues

**Gemini API Key not found**
```bash
cat pipeline/.env
# Verify: GEMINI_API_KEY=your-key-here
```

**Module not found: pipeline**
```bash
cd pipeline
python mtl.py list
```

**Safety block / Content policy refusal**
- Use Web Gemini interface as fallback
- Upload `prompts/master_prompt_en_compressed.xml`
- Copy output back to EN/ directory

**Illustration not appearing in EPUB**
- Check `manifest.json` → assets.illustrations
- Verify image exists in `_assets/illustrations/`
- Re-run Phase 4: `python mtl.py phase4 volume_id`

**Character name extraction failed**
- Check `.context/name_registry.json`
- Verify ruby text in JP source files
- Manually update name registry if needed

### Log Files

- `pipeline/pipeline.log` - Main pipeline log
- `WORK/[volume_id]/translation_log.json` - Translation metrics

### Post-Processing Features

**CJK Artifact Cleaner**:
- Automatically detects and removes leftover Japanese/Chinese characters
- Context-aware cleaning with configurable confidence threshold (default: 70%)
- Logs all detections for review

**Format Normalizer**:
- Smart quote conversion
- Em-dash standardization
- Ellipsis normalization
- Double space removal

---

## API Reference

### Manifest Schema

```json
{
  "version": "1.0",
  "volume_id": "unique-volume-identifier",
  "created_at": "2026-01-21T10:00:00Z",
  "metadata": {
    "title": "Japanese Title",
    "title_en": "English Title",
    "author": "Author Name",
    "author_en": "Author Name (Romanized)",
    "publisher": "Publisher Name",
    "source_epub": "/path/to/source.epub"
  },
  "pipeline_state": {
    "librarian": {
      "status": "completed",
      "timestamp": "2026-01-21T10:00:00Z",
      "chapters_completed": 12,
      "chapters_total": 12
    },
    "metadata_processor": {
      "status": "completed",
      "timestamp": "2026-01-21T10:05:00Z"
    },
    "translator": {
      "status": "completed",
      "chapters_completed": 12,
      "chapters_total": 12
    },
    "builder": {
      "status": "completed",
      "output_file": "Title_EN.epub",
      "chapters_built": 12,
      "images_included": 16
    }
  },
  "chapters": [
    {
      "id": "chapter_01",
      "source_file": "CHAPTER_01.md",
      "title": "Japanese Chapter Title",
      "title_en": "English Chapter Title",
      "word_count": 5000,
      "translation_status": "completed",
      "qc_status": "pass",
      "illustrations": ["illust-001.jpg"],
      "en_file": "CHAPTER_01.md"
    }
  ],
  "assets": {
    "cover": "cover.jpg",
    "kuchie": ["kuchie-001.jpg"],
    "illustrations": ["illust-001.jpg", "illust-002.jpg"]
  }
}
```

### Name Registry Schema

```json
{
  "Japanese Name (Kanji)": "Romanized Name",
  "高橋隆史": "Takahashi Takashi",
  "白雪姫乃": "Shirayuki Himeno"
}
```

### Semantic Metadata Schema

The translator supports **four metadata schema variants** for enhanced character voice and translation guidelines. Schema detection is automatic—the translator transforms any variant to a unified internal format.

#### Schema Variants

| Schema | Use Case | Key Fields |
|--------|----------|------------|
| **V3 Enhanced** | **Recommended** - Full character continuity | `character_profiles` with `keigo_switch`, `relationship_to_others`, `occurrences`, `inherited_from` |
| **Enhanced v2.1** | New volumes, full control | `characters`, `dialogue_patterns`, `translation_guidelines` |
| **Legacy V2** | Volumes 1-3 style | `character_profiles`, `localization_notes`, `speech_pattern` |
| **V4 Nested** | Compact character data | `character_names` with nested `{relationships, traits, pronouns}` |

#### V3 Enhanced Schema (Recommended)

```json
{
  "metadata_en": {
    "schema_version": "v3_enhanced",
    "inherited_from": "previous_volume_id",
    "character_profiles": {
      "Doumoto Hayato": {
        "full_name": "Doumoto Hayato",
        "nickname": "Hayato",
        "age": "16 (1st year high school)",
        "pronouns": "he/him",
        "relationship_to_protagonist": "PROTAGONIST",
        "relationship_to_others": "Dating both Shinjou sisters, friend to Souta",
        "personality_traits": "Kind, modest, thoughtful, reluctant hero",
        "speech_pattern": "Casual male teen speech, uses 俺 (ore)",
        "keigo_switch": {
          "narration": "casual_introspective",
          "speaking_to": {
            "Shinjou Arisa": "casual_boyfriend",
            "strangers": "polite_formal"
          },
          "emotional_shifts": {
            "embarrassed": "casual",
            "protective": "casual_boyfriend"
          }
        },
        "key_traits": "Lives alone, supported by grandfather",
        "character_arc": "Navigating relationship while ex-girlfriend reappears",
        "occurrences": 414
      }
    },
    "localization_notes": {
      "volume_specific_notes": {
        "sequel_context": "Volume 2 - relationship established",
        "character_dynamics": {
          "arisa": "Now girlfriend, jealous of ex"
        }
      }
    },
    "chapters": {
      "chapter_01": {
        "title_jp": "プロローグ",
        "title_en": "Prologue",
        "pov_tracking": [
          {
            "character": "Doumoto Hayato",
            "start_line": 1,
            "end_line": null,
            "context": "Full chapter"
          }
        ]
      }
    }
  }
}
```

#### Enhanced v2.1 Schema

```json
{
  "metadata_en": {
    "title_en": "Volume Title",
    "characters": [
      {
        "name_jp": "青柳明人",
        "name_en": "Aoyagi Akihito",
        "role": "protagonist",
        "archetype": "everyman_mc",
        "speech_style": "casual_polite",
        "voice_notes": "Self-deprecating, awkward with compliments"
      }
    ],
    "dialogue_patterns": {
      "protagonist": {
        "contractions": ["I'm", "don't", "can't"],
        "filler_words": ["well", "I mean"],
        "avoid": ["Indeed", "Furthermore"]
      }
    },
    "translation_guidelines": {
      "tone": "rom-com",
      "formality": "casual",
      "honorifics": "localize"
    }
  }
}
```

#### Legacy V2 Schema

```json
{
  "metadata_en": {
    "character_profiles": {
      "Akihito": {
        "full_name": "Aoyagi Akihito",
        "archetype": "everyman_mc",
        "speech_pattern": "casual, self-deprecating",
        "character_arc": "Growing confidence through relationships"
      }
    },
    "localization_notes": {
      "british_character_exceptions": ["Charlotte", "Emma"],
      "forbidden_patterns": ["Indeed", "Quite so"],
      "target_metrics": { "contraction_rate": 0.85 }
    }
  }
}
```

#### V4 Nested Schema

```json
{
  "metadata_en": {
    "character_names": {
      "青柳明人《あおやぎあきひと》": {
        "name_en": "Aoyagi Akihito",
        "role": "protagonist",
        "relationships": { "シャーロット": "girlfriend" },
        "traits": ["kind", "caring", "self_doubting"],
        "pronouns": { "subject": "he", "object": "him" }
      }
    }
  }
}
```

#### Schema Auto-Transformation

The translator automatically transforms all schemas to a unified internal format:

| Source | Transformed To | Notes |
|--------|---------------|-------|
| `character_profiles` | `characters` list | Extracts archetype, speech patterns |
| `localization_notes` | `translation_guidelines` | Includes forbidden patterns, metrics |
| `speech_pattern` in profiles | `dialogue_patterns` | Per-character voice rules |
| `keigo_switch` in profiles | Context-aware register | Automatic formality switching |
| V4 nested `character_names` | `characters` list | Flattens nested structure |

#### Keigo Switch System (Speech Register Control)

The `keigo_switch` feature enables automatic speech register switching based on:
- **Narration context**: Internal monologue vs external narration
- **Conversation partner**: Formal with superiors, casual with friends
- **Emotional state**: Register shifts during emotional moments

```json
{
  "keigo_switch": {
    "narration": "formal_polite",
    "internal_thoughts": "formal_polite",
    "speaking_to": {
      "Akihito": "polite_formal",
      "Emma": "gentle_sisterly",
      "Miyu-sensei": "respectful_formal",
      "classmates": "polite_formal",
      "strangers": "very_formal"
    },
    "emotional_shifts": {
      "jealous": "slightly_clipped_formal",
      "embarrassed": "stuttering_formal",
      "happy": "warm_polite"
    },
    "notes": "Charlotte maintains formal register in ALL contexts"
  }
}
```

**Proven Impact**: Testing showed Charlotte's POV chapters in V3 had **12x higher formal phrase rate** (3.7 vs 0.3 per 1000 words) compared to V1, demonstrating successful schema injection and character voice differentiation.

#### CLI Schema Inspection

```bash
# Quick schema detection
python mtl.py metadata volume_id

# Full validation report
python mtl.py metadata volume_id --validate
```

**Example Output:**
```
Detected Schema: Legacy V2
  ✓ character_profiles: 9 entries
  ✓ localization_notes: Present
  ✓ speech_pattern (in profiles): Yes

TRANSLATOR COMPATIBILITY:
  ✓ Auto-transform: character_profiles → characters
  ✓ Auto-transform: localization_notes → translation_guidelines
  ✓ Auto-extract: speech_pattern → dialogue_patterns

Status: ✓ COMPATIBLE
```

---

## Performance Statistics

| Metric | Value |
|--------|-------|
| Average processing time | 10-15 minutes per volume |
| Translation quality | Grade A/B (95%+ human-level) |
| EPUB validation | 100% IDPF compliant |
| Publisher compatibility | 5+ major Japanese publishers |
| Test corpus size | 23 EPUB volumes analyzed |
| Ruby tag support | 82.6% of volumes |

---

## Dependencies

```
google-genai>=0.5.0       # Gemini API
ebooklib>=0.18            # EPUB parsing
beautifulsoup4>=4.12      # HTML/XML parsing
lxml>=5.0                 # XML processing
markdown>=3.5             # Markdown processing
Pillow>=10.0              # Image processing
python-dotenv>=1.0        # Environment variables
rich>=13.0                # CLI formatting
pyyaml>=6.0               # Configuration parsing
inquirer>=3.0             # Interactive prompts
```

---

## License

See LICENSE.txt for licensing information.

---

## Credits

**Core System**:
- Pipeline Architecture: MTL Studio Development Team
- AI Engine: Google Gemini (3 Flash / 2.5 Flash)
- Typography: smartypants library
- EPUB Handling: ebooklib, BeautifulSoup

**Translation Standards**:
- FFXVI-Tier Localization Method (Michael-Christopher Koji Fox)
- Japanese Light Novel Translation Community

---

## Changelog

### Version 3.0 LTS (January 2026)
- **V3 Enhanced Schema**: Rich character profiles with `keigo_switch`, `relationship_to_others`, `speech_pattern`, `character_arc`, and `occurrences` tracking
- **POV Tracking System**: Per-chapter `pov_tracking` array supporting mid-chapter POV shifts with line ranges
- **Legacy System Disabled**: `.context/` continuity pack system replaced by superior v3 schema character_profiles
- **Double-Spread Illustration Detection**: Automatic pattern matching for `p###-p###.jpg` two-page spreads
- **Comprehensive Scene Break Patterns**: 30+ proprietary patterns (◆, ◇, ★, ☆, ※※※, etc.) normalized to unified standard
- **Sequel Inheritance**: `inherited_from` field tracks volume lineage for character profile continuity
- **Volume-Specific Context**: `volume_specific_notes` for sequel-aware translation (ex-girlfriend subplot, role expansions)
- **Character Occurrence Tracking**: Mention counts inform translation priorities and voice consistency
- **AUDIT_AGENT.md**: Renamed from GEMINI.md for clarity

### Version 2.5 (January 2026)
- **Multi-Language Support**: Full Vietnamese translation pipeline with dedicated modules
- **Gemini 2.5 Pro/Flash**: Updated to latest models with thinking mode
- **GEMINI.md QC Agent**: AI-powered quality control with auto-fix capabilities
- **Interactive CLI**: Volume selection menus, configuration commands
- **Semantic Metadata Schema System**: Three schema variants (Enhanced v2.1, Legacy V2, V4 Nested) with auto-transformation
- **Keigo Switch System**: Automatic speech register switching based on narration, conversation partner, and emotional state
- **Metadata Schema Inspector**: New `metadata` CLI command with `--validate` for schema compatibility checking
- **Post-Processing**: CJK artifact cleaner, format normalizer
- **Chapter Merging**: Utility to merge chapters into unified markdown files
- **Safety Block Handling**: Web Gemini fallback protocol for blocked content
- **39+ Utility Scripts**: Extended tooling for analysis, repair, and migration
- **Publisher Pattern System**: 7 publishers documented with 65+ EPUB structure patterns
- **EPUB Cover Metadata Fix**: Automatic kuchie-based cover metadata for Apple Books thumbnails

### Version 2.0 (January 2026)
- Initial production release
- English translation pipeline
- RAG-enhanced translation
- EPUB 3.0 builder

---

Version 3.0 LTS | January 2026 | Production Ready | EN/VN Supported
