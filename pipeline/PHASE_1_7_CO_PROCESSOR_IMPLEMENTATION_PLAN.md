# Phase 1.7 Co-Processor Implementation Plan

## Context
Based on `/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/17FB_FULL_VOLUME_VALIDATION_REPORT.md`, the four co-processors demonstrated production value at full-volume scale:

- AI-isms reduced to 1.4/chapter (about 60% down from baseline)
- Dialogue rhythm tightened to 4.5 words/sentence
- Narration stabilized at 13.1 words/sentence
- Character consistency reached 100%
- Cultural accuracy reached 95%

This plan productizes those gains into standard runtime behavior and repeatable QA.

## Objectives
1. Expose co-processors as a first-class standalone operation.
2. Keep Phase 2 compatibility unchanged while enabling pre-translation context refresh.
3. Make rollout measurable using stable scorecard gates.

## Scope
- In scope:
  - CLI/menu surface for standalone co-processor run.
  - Generation of all four context caches via cache-only mode:
    - `character_registry.json`
    - `cultural_glossary.json`
    - `timeline_map.json`
    - `idiom_transcreation_cache.json`
  - Documentation and operator workflow.
- Out of scope:
  - Rewriting co-processor prompting logic.
  - Replacing Stage 1 scene planner behavior.

## Implementation Workstreams

### Workstream A: CLI Productization
Status: Completed

- Added new standalone command: `phase1.7-cp`
- Wired command in:
  - `/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/scripts/mtl.py`
  - `/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/pipeline/cli/parser.py`
  - `/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/pipeline/cli/dispatcher.py`
- Added main-menu visibility in no-command help output.

Runtime behavior:
- `phase1.7-cp` executes Phase 1.55 cache-only path and refreshes all four context JSONs without metadata overwrite.

### Workstream B: Reliability Hardening
Status: In progress

- Standardize fallback semantics when external cache creation fails.
- Persist processor-level status in manifest pipeline state with clear reason codes.
- Add explicit warning tiers:
  - hard fail: malformed JSON output
  - soft fail/fallback: empty or partial co-processor payload

### Workstream C: Quality Gates
Status: Planned

Release gate targets:
- AI-isms: <= 2.0/chapter
- Dialogue rhythm: <= 5.0 words/sentence average
- Narration rhythm: 12.0-14.0 words/sentence average
- Character consistency: >= 99%
- Cultural accuracy proxy: >= 90%

Validation artifacts per volume:
- `QC/AUDIT_REVIEW_<id>.md`
- `.context/*.json` cache presence check
- chapter-level rhythm + AI-ism scan snapshot

### Workstream D: Rollout
Status: Planned

1. Canary volumes: 2 new runs with `phase1.7-cp` before `phase2`.
2. Compare against previous runs for:
   - AI-ism density
   - rhythm distributions
   - name/honorific consistency
3. Promote to default SOP if both canaries pass gate targets.

## Operator Workflow (New)
1. Run metadata pipeline: `phase1` -> `phase1.5`
2. Run co-processor pack:
   - `python3 /Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/scripts/mtl.py phase1.7-cp <volume_id>`
3. Run scene planner:
   - `python3 /Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/scripts/mtl.py phase1.7 <volume_id>`
4. Run translator:
   - `python3 /Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/scripts/mtl.py phase2 <volume_id>`

## Risks and Mitigations
- Risk: empty idiom cache on safe-content refusal or malformed response.
  - Mitigation: maintain fallback builder + JSON artifact logging.
- Risk: cache-only confusion with full metadata enrichment.
  - Mitigation: clear command naming and header text indicating no metadata overwrite.
- Risk: operator skips co-processor run.
  - Mitigation: include command in main menu and SOP docs.

## Success Criteria
Implementation is complete when:
1. `phase1.7-cp` is callable from main CLI and interactive volume resolution works.
2. All four context JSONs are regenerated in one standalone run.
3. Two consecutive new volumes meet quality gates without regressions versus baseline.
