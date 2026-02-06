# Legacy Multimodal Modules

These files were part of the initial Gemini 3 Pro multimodal prototype
(the "function calling" approach where the translator could request
illustrations on-demand during translation).

They were **superseded** by the "pre-bake → inject" architecture:
- `asset_processor.py` (Phase 1.6 visual analysis)
- `prompt_injector.py` (Art Director's Notes injection into translation prompts)

## Archived Files

| File | Purpose | Why Archived |
|------|---------|-------------|
| `illustration_analyzer.py` | Per-illustration emotional analysis (XML format) | Replaced by `asset_processor.py` (JSON format, cached) |
| `vision_translator.py` | Gemini 3 Pro translator with function calling | Replaced by CPU+GPU dual-model architecture |
| `function_handler.py` | On-demand illustration retrieval via function calls | Replaced by pre-baked `visual_cache.json` |
| `GEMINI_3_INTEGRATION_PLAN.md` | Original integration plan | Historical reference only |
| `MULTIMODAL_TRANSLATION_FINDINGS.md` | Test findings during prototype | Historical reference only |

## Why Not Deleted?

These files contain useful reference code for future features:
- `IllustrationContext` dataclass has rich emotional fields (posture, gaze, subtext)
- `VisionEnhancedTranslator` shows function-calling patterns for Gemini 3 Pro
- Test files reference these modules for integration testing patterns

If disk space is a concern, these can be safely deleted.
