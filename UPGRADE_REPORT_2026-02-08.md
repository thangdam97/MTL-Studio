# MTL Studio Upgrade Report

Date: 2026-02-08
Scope: Consolidated summary of pipeline upgrades completed so far for massive LN handling, schema automation, and operator UX.

## 1) Executive Summary

The pipeline has been upgraded from a standard chapter translator into a large-volume-capable flow with:

- Massive chapter protections (smart chunking, chunk merge recovery, truncation checks)
- Better consistency controls (glossary/name locking and auditing)
- Configurable runtime toggles in both CLI menu and direct `mtl.py config` flags
- Metadata schema automation (Phase 1.5 now auto-updates schema before title/chapter translation)
- Official localization lookup directive in schema autofill (online grounding when localized series names are detected)

## 2) Core Upgrades Delivered

### A. Massive LN Translation Hardening

Implemented for long chapters and multi-volume EPUB edge cases:

- Smart chunk-based chapter translation flow with resumable chunk artifacts
- Chunk merge path for reconstructed final chapter outputs
- Truncation validation to detect/guard incomplete outputs
- Name/glossary lock enforcement to reduce drift
- Name consistency auditor integration for QA checks

Primary code locations:

- `pipeline/pipeline/translator/chapter_processor.py`
- `pipeline/pipeline/translator/chunk_merger.py`
- `pipeline/pipeline/post_processor/truncation_validator.py`
- `pipeline/pipeline/translator/glossary_lock.py`
- `pipeline/auditors/name_consistency_auditor.py`

### B. Smart Chunking Threshold Update

Threshold changed from `50,000` to `60,000` chars.

- Runtime fallback default updated in translator
- Runtime profile display defaults updated
- Config display fallback updated
- Config now explicitly includes `translation.massive_chapter`

Files:

- `pipeline/pipeline/translator/chapter_processor.py`
- `pipeline/scripts/mtl.py`
- `pipeline/config.yaml`

Current default block in config:

- `enable_smart_chunking: true`
- `chunk_threshold_chars: 60000`
- `chunk_threshold_bytes: 120000`
- `enable_volume_cache: true`

### C. CLI/Config Operator Controls

Added/verified direct non-menu controls:

- `mtl.py config --toggle-smart-chunking`
- `mtl.py config --toggle-multimodal`
- `mtl.py config --toggle-pre-toc`

Menu + parser + handler bridges now expose these toggles consistently.

Files:

- `pipeline/pipeline/cli/parser.py`
- `pipeline/pipeline/cli/menus/settings.py`
- `pipeline/pipeline/cli/utils/config_bridge.py`
- `pipeline/scripts/mtl.py`

### D. Phase 1.5 Schema Automation (Manual IDE-agent replacement)

Old flow:

- Librarian Extraction -> Title/Chapter title Translation -> Phase 2

New flow:

- Librarian Extraction -> Schema Agent autoupdate merge -> Title/Chapter title Translation -> Phase 2

Implemented with a dedicated module:

- `pipeline/pipeline/metadata_processor/schema_autoupdate.py`

Integrated into metadata processor:

- `pipeline/pipeline/metadata_processor/agent.py`

Behavior:

- Uses hardcoded Gemini settings for schema pass:
  - model: `gemini-2.5-flash`
  - temperature: `0.5`
  - top_p/top_k: defaults
  - max_output_tokens: `32768`
- Merges patch into `metadata_en` without overwriting translation-owned fields
- Writes `pipeline_state.schema_agent` status for observability
- Fails soft (does not block full Phase 1.5 if schema pass errors)

### E. Official Localization Directive + Online Grounding

Added schema-level directive:

- If localized series name is detected, perform online search and prefer official localization metadata.

Implementation details:

- Localized series hint detection from metadata series/title patterns
- Gemini tools support added in shared client
- Schema autoupdate enables Google Search grounding when hint is detected
- Official localization payload (`official_localization`) is stored in `metadata_en`
- Metadata translation step can override generated metadata with official values when confidence allows

Files:

- `pipeline/pipeline/common/gemini_client.py`
- `pipeline/pipeline/metadata_processor/schema_autoupdate.py`
- `pipeline/pipeline/metadata_processor/agent.py`

### F. Documentation/Architecture Refresh

Pipeline descriptions were updated to reflect the new Phase 1.5 semantics and architecture direction.

Files updated include:

- `README.md`
- `pipeline/scripts/mtl.py` (usage/help text)
- `pipeline/pipeline/cli/parser.py`
- `pipeline/pipeline/cli/dispatcher.py`
- `pipeline/pipeline/__init__.py`

## 3) Current Translator Runtime Behavior (Important)

Even with full-volume cache enabled, translation execution remains chapter-by-chapter:

- The run creates one cache containing full JP volume content/context
- Translator still iterates chapters one at a time
- Each chapter is translated in its own call unless chunk splitting is triggered for that chapter

This means cache improves context/cost behavior, but not chapter-level execution granularity.

## 4) Validation Performed

- Python compile checks passed on modified modules (`py_compile`)
- Config parse check passed (`config.yaml` loads with new `massive_chapter` block)
- Spot checks confirmed CLI toggle flags are present in parser/help and runtime output

## 5) Known Limitations / Risks

- Full-volume cache does not switch the translator to single-call whole-volume generation; it only provides shared context.
- Official localization lookup depends on model grounding quality and source ranking; confidence gate is applied but still should be spot-reviewed for critical releases.
- Sequel direct-copy path remains optimized and may bypass some schema-autofill heuristics by design.

## 6) Suggested Next Upgrade Targets

1. Add explicit `--whole-volume` translation mode (optional) for experiments with full-volume generation.
2. Add source-domain allowlist/scoring for official localization extraction (publisher + licensor priority rules).
3. Add post-schema validation step for `official_localization` shape and confidence thresholds.
4. Add structured telemetry file for cache hit rate, chunking decisions, and schema grounding outcomes.

