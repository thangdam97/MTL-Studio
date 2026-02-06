# MTL Studio Multimodal Processor Test Suite

## Overview

Internal test suite for validating the Gemini 3 Pro Cognitive Vision integration before pipeline integration.

**Model:** `gemini-3-pro-preview` (hardcoded)  
**Test Volume:** Ice Princess Volume 1 (1d46)  
**Test Illustrations:** 3 scenes with varying emotional complexity

## Key Features

### 🧠 Thinking Mode ENABLED
- **Reveals Gemini's internal reasoning** ("black box" exposed)
- `thinking_level: HIGH` by default
- `include_thoughts: True` captures thought process in output
- Useful for debugging translation decisions

### 📜 Pipeline Prompts Loaded
- Uses **exact same** EN master prompt as production pipeline
- All RAG modules injected:
  - `english_grammar_rag.json` (Tier 1)
  - `anti_ai_ism_patterns.json`
  - `literacy_techniques.json`
  - Core translation modules (MEGA_CORE, ANTI_TRANSLATIONESE, etc.)
- ~486KB system instruction (identical to production)

## Test Cases

| ID | Illustration | Scene | Focus |
|----|--------------|-------|-------|
| test_001 | illust-001.jpg | First train meeting | Character introduction, visual identity |
| test_002 | illust-002.jpg | Mont Blanc jealousy | **Spoiler prevention guardrail** |
| test_003 | illust-004.jpg | "It's a secret" | Emotional peak, facade breaking |

## Installation

```bash
# From MTL_STUDIO root
cd pipeline

# Install the NEW google-genai SDK (NOT google-generativeai)
pip install google-genai>=1.0.0

# Set API key (either works, GOOGLE_API_KEY takes precedence)
export GOOGLE_API_KEY="your-api-key-here"
# OR
export GEMINI_API_KEY="your-api-key-here"
```

**Important:** This module uses the newer `google-genai` SDK from [googleapis/python-genai](https://github.com/googleapis/python-genai), NOT the older `google-generativeai` package.

```python
# NEW SDK (used here)
from google import genai
from google.genai import types
client = genai.Client(api_key=...)

# OLD SDK (NOT used)
import google.generativeai as genai  # Different!
```

## Usage

### Full Test Suite
```bash
python -m modules.multimodal.test_multimodal_processor --mode full
```

### Analysis Only (no translation)
```bash
python -m modules.multimodal.test_multimodal_processor --mode analyze
```

### Function Handler Only (test image loading)
```bash
python -m modules.multimodal.test_multimodal_processor --mode handler
```

### Translation Only (requires API calls)
```bash
python -m modules.multimodal.test_multimodal_processor --mode translate
```

### Save Results
```bash
# Save JSON results
python -m modules.multimodal.test_multimodal_processor --mode full --save-results

# Save Markdown comparison (auto-enabled for translate/full mode)
python -m modules.multimodal.test_multimodal_processor --mode translate --markdown
```

## Output Files

### Markdown Comparison (`translation_comparison_*.md`)
Single markdown file with all translation results:

```markdown
# MTL Studio Multimodal Translation Comparison

## Scene 1: First Train Meeting - Good Morning
**Illustration:** `illust-001`

### 1. 📖 Japanese Source
```
電車内で座っている少女、東雲凪を見つけた...
```

### 2. 📚 Reference EN (Expected)
Something caught in her chest the moment she saw...

### 3. 🎨 Multimodal Translation
The instant her eyes found the girl sitting there...

### 4. 🧠 Thought Process
#### Iteration 1
```
Looking at the illustration, Nagi's posture is tense but composed...
I should NOT describe her expression since the marker comes BEFORE...
```
```

## Components Tested

### 1. IllustrationAnalyzer
- Extracts emotional and contextual metadata from illustrations
- Generates structured JSON output
- Formats as XML context for prompt injection

**Key Validations:**
- Character identification accuracy
- Primary/secondary emotion detection
- Subtext inference
- Prose tone recommendation

### 2. IllustrationFunctionHandler
- Handles `get_illustration`, `get_character_reference`, `get_kuchie` calls
- Returns image data with metadata
- Supports inline base64 (test) and GCS URIs (production)

**Key Validations:**
- Image loading from assets
- Metadata extraction from manifest
- Error handling for missing assets

### 3. VisionEnhancedTranslator
- Full translation with on-demand illustration access
- Function calling loop with iteration tracking
- Multimodal response handling

**Key Validations:**
- Function call triggering on [ILLUSTRATION] markers
- Image injection into conversation
- Translation quality with visual context

## Test Data Files

```
test_data/
├── test_manifest.json      # Extended manifest with illustration metadata
├── test_segments.json      # Japanese source + English reference for 3 scenes
└── test_results_*.json     # Output from test runs
```

## Expected Output

### Successful Analysis
```
[illust-001] First Train Meeting - Good Morning
----------------------------------------
  Primary emotion: nervous_anticipation
  Expected: nervous_anticipation
  Characters: ['Nagi', 'Souta']
  Subtext: First intimate encounter, overwhelming presence...
  ✓ Analysis complete
```

### Translation with Thoughts
When thinking mode is enabled, the output includes the model's reasoning:

```json
{
  "success": true,
  "translation": "Something caught in her chest the moment...",
  "iterations": 2,
  "function_calls": [
    {"function": "get_illustration", "args": {"illustration_id": "illust-001"}}
  ],
  "thoughts": [
    {
      "iteration": 1,
      "thoughts": "Looking at the illustration, I can see Nagi's posture is tense but composed. Her eyes are slightly downcast, suggesting nervousness rather than confidence. The lighting is soft morning light through the train window. I should NOT describe her expression directly since the [ILLUSTRATION] marker comes BEFORE she looks up..."
    }
  ]
}
```

### Successful Function Call
```
[illust-002] Mont Blanc Jealousy
----------------------------------------
  ✓ Function call successful
  Response: {"illustration_id": "illust-002", "chapter": 1, ...}
  Image: illust-002.jpg (245312 bytes)
  MIME: image/jpeg
```

### Spoiler Prevention Test (illust-002)

The Mont Blanc scene is specifically designed to test the **Chronological Visual Discipline** guardrail:

- The illustration shows Nagi's anguished face
- But the [ILLUSTRATION] tag appears *before* she sees Souta
- The AI must forecast mood without describing her expression

**Expected behavior:**
- ✓ "Something heavy pressed against her chest..."
- ✓ "An inexplicable dread crept over her..."
- ✗ "Her face twisted with jealousy..." (TOO EARLY)
- ✗ "Tears welled in her eyes..." (SPOILER)

## Troubleshooting

### API Key Issues
```
ValueError: API key required. Set GOOGLE_API_KEY environment variable
```
→ Export your API key: `export GOOGLE_API_KEY="..."`

### Model Not Available
```
google.api_core.exceptions.NotFound: 404 Model not found
```
→ `gemini-3-pro-preview` may not be available yet. Wait for stable release.

### Image Not Found
```
[WARN] Illustration not found: .../assets/illustrations/illust-001.jpg
```
→ Ensure the 1d46 volume has been processed with assets extracted.

## Integration Notes

This test suite validates the **foundation** before pipeline integration:

1. ✅ IllustrationAnalyzer works standalone
2. ✅ Function handler correctly loads images
3. ✅ Translator triggers function calls on markers
4. ⏳ Pipeline integration (Phase 2 after validation)

Once tests pass, integrate into:
- `pipeline/pipeline/translator/agent.py`
- `pipeline/config/config.yaml`
- `pipeline/prompts/master_prompt_en_compressed.xml`
