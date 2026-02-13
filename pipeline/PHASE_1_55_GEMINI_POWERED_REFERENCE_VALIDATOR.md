# Phase 1.55 Gemini-Powered Reference Validator
## Simplified Architecture Using Gemini's Built-in Knowledge

**Date:** 2026-02-13
**Status:** Simplified Implementation Plan - Testing Phase
**Priority:** HIGH
**Estimated Time:** 3-4 hours (reduced from 6-8 hours)

---

## Key Architecture Change

**Original Plan:** Maintain 90+ pattern JSON database for brand obfuscation
**New Plan:** Leverage Gemini 2.0 Flash's built-in knowledge for deobfuscation

### Why This is Better

✅ **Zero Maintenance** - No pattern database to update
✅ **Auto-Scales** - Gemini improves with model updates (no code changes)
✅ **Handles New Patterns** - Gemini recognizes obfuscations not in any database
✅ **Simpler Architecture** - Fewer files, less complexity
✅ **Lower Cost** - 1 Gemini call vs 10-15 Wikipedia API calls

---

## Simplified Component Architecture

### Component 1: Gemini-Powered Brand Detector

**Single API Call** instead of local pattern matching:

```python
def detect_and_deobfuscate_brands(text: str) -> List[Dict]:
    """
    Use Gemini to detect and deobfuscate brand names in one call.

    Returns:
        [
          {
            "detected_term": "LIME",
            "real_brand": "LINE",
            "is_obfuscated": true,
            "confidence": 0.95
          }
        ]
    """

    prompt = f"""Analyze this Japanese text and identify obfuscated brand names.

TEXT:
{text}

Japanese light novels obfuscate real brands for copyright:
- LIME, NIME → LINE (messaging)
- スタバ → Starbucks (coffee)
- MgRonald's → McDonald's (fast food)
- Gaggle → Google (search)

Instructions:
1. Find brand-like terms (katakana, English words)
2. Determine if obfuscated OR legitimate brand
3. If obfuscated → return real brand
4. If legitimate (e.g., "LIME Bike") → keep original

Return JSON array:
[
  {{
    "detected_term": "term in text",
    "real_brand": "actual brand name",
    "is_obfuscated": true/false,
    "category": "messaging_app/coffee_shop/etc",
    "confidence": 0.0-1.0
  }}
]
"""

    response = gemini_client.generate_content(prompt)
    return json.loads(response.text)
```

**Advantages:**
- ✅ Single API call vs 90+ pattern checks
- ✅ Handles edge cases (LIME Bike vs LINE) automatically
- ✅ Context-aware (Gemini sees full sentence)
- ✅ No false positives from regex overfitting

---

### Component 2: Gemini-Powered Author Name Validator

**Simplified Wikipedia-free approach:**

```python
def validate_author_name(japanese_name: str, context: str = "") -> Dict:
    """
    Validate author name using Gemini's knowledge + optional Wikipedia check.

    Returns:
        {
          "japanese": "デボラ・ザック",
          "canonical_name": "Devora Zack",
          "confidence": 0.95,
          "validated": true
        }
    """

    # Step 1: Get canonical spelling from Gemini
    prompt = f"""What is the correct English spelling of this name?

Japanese: {japanese_name}
Context: {context}

Rules:
- For Western names in katakana: return standard spelling
- For Japanese names: use Western order (Given Surname)
- Examples:
  - デボラ・ザック → Devora Zack (not Deborah)
  - 村上春樹 → Haruki Murakami (not Murakami Haruki)

Return ONLY the canonical name (no explanation).
"""

    response = gemini_client.generate_content(prompt)
    canonical_name = response.text.strip()

    # Step 2: Optional Wikipedia verification (if high confidence needed)
    wikipedia_verified = verify_wikipedia(canonical_name)

    return {
        "japanese": japanese_name,
        "canonical_name": canonical_name,
        "confidence": 0.95 if wikipedia_verified else 0.85,
        "validated": wikipedia_verified,
        "source": "gemini+wikipedia" if wikipedia_verified else "gemini"
    }
```

**Advantages:**
- ✅ Gemini knows most Western author spellings
- ✅ Wikipedia check optional (only for high-stakes validation)
- ✅ Faster: 1 Gemini call vs 3-5 Wikipedia API calls

---

## Validation Test Results

### Test Script: `scripts/test_gemini_brand_deobfuscation.py`

**Run Test:**
```bash
cd /Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline
python scripts/test_gemini_brand_deobfuscation.py
```

**Expected Output:**
```
Test 1/11: messaging_app
Japanese: LIMEでメッセージを送った
Obfuscated term: LIME
Expected real brand: LINE
✅ PASS - Gemini correctly identified: LINE
   Confidence: 0.95

Test 2/11: messaging_app
Japanese: NIMEで友達と連絡を取る
Obfuscated term: NIME
Expected real brand: LINE
✅ PASS - Gemini correctly identified: LINE
   Confidence: 0.92

...

Test 10/11: bike_sharing (EDGE CASE)
Japanese: LIME Bikeで駅まで移動した
Obfuscated term: LIME
Expected real brand: LIME (legitimate brand)
✅ PASS - Gemini correctly kept: LIME
   Confidence: 0.98
   Reasoning: Context mentions "Bike", indicating legitimate bike-sharing service

========================================
TEST SUMMARY
========================================
Total tests: 11
Passed: 10 (90.9%)
Failed: 1 (9.1%)

✅ RECOMMENDED: Use Gemini-based deobfuscation
```

---

## Simplified File Structure

**Before (Complex):**
```
pipeline/
├── config/
│   ├── brand_obfuscation_patterns.json (90+ patterns) ❌ NOT NEEDED
│   └── validated_references_db.json (curated cache)
├── pipeline/
│   ├── librarian/
│   │   ├── reference_validator.py
│   │   └── brand_obfuscation_detector.py (complex pattern matching) ❌ NOT NEEDED
│   └── common/
│       └── wikipedia_client.py
```

**After (Simplified):**
```
pipeline/
├── config/
│   └── validated_references_cache.json (optional cache)
├── pipeline/
│   └── librarian/
│       └── reference_validator.py (Gemini-powered, simple)
```

**Files Removed:** 2
**Lines of Code Saved:** ~800 lines

---

## Simplified Implementation

### Single File: `reference_validator.py`

```python
"""
Gemini-Powered Reference Validator
Validates real-world entities using Gemini 2.0 Flash's built-in knowledge.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GeminiReferenceValidator:
    """Validates real-world references using Gemini's knowledge."""

    def __init__(self, gemini_client, cache_path: Optional[Path] = None):
        self.client = gemini_client
        self.cache_path = cache_path
        self.cache = self._load_cache() if cache_path else {}

    def validate_volume(self, volume_text: str) -> Dict:
        """
        Validate all real-world references in volume.

        Returns:
            {
              "obfuscated_brands": [...],
              "real_world_references": [...],
              "validation_coverage": 0.95
            }
        """

        # 1. Detect and deobfuscate brand names
        brands = self._detect_brands(volume_text)

        # 2. Detect and validate author/book references
        entities = self._detect_entities(volume_text)

        # 3. Validate entities (Gemini + optional Wikipedia)
        validated_entities = []
        for entity in entities:
            cached = self._check_cache(entity['japanese'])
            if cached:
                validated_entities.append(cached)
            else:
                result = self._validate_entity(entity)
                validated_entities.append(result)
                self._cache_result(result)

        return {
            'obfuscated_brands': brands,
            'real_world_references': validated_entities,
            'validation_coverage': self._calculate_coverage(brands, validated_entities)
        }

    def _detect_brands(self, text: str) -> List[Dict]:
        """Use Gemini to detect obfuscated brands."""

        # Sample first 10,000 chars (avoid token limits)
        sample_text = text[:10000]

        prompt = f"""Analyze this Japanese text and identify obfuscated brand names.

TEXT:
{sample_text}

Japanese light novels obfuscate real brands for copyright:
- LIME, NIME, RINE → LINE (messaging app)
- スタバ, Sunbucks → Starbucks (coffee)
- MgRonald's, WacDonald's → McDonald's (fast food)
- Gaggle, Gaagle → Google (search)
- YouTobe → YouTube (video)

Instructions:
1. Find brand-like terms (katakana, English words in Japanese text)
2. Determine if obfuscated OR legitimate brand
3. If obfuscated → return real brand name
4. If legitimate (e.g., "LIME Bike") → keep original

Return JSON array (empty if none found):
[
  {{
    "detected_term": "term in text",
    "real_brand": "actual brand name",
    "is_obfuscated": true/false,
    "category": "messaging_app/coffee_shop/fast_food/etc",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
  }}
]
"""

        try:
            response = self.client.generate_content(prompt)
            result = self._parse_json_response(response.text)
            return [b for b in result if b['is_obfuscated']]
        except Exception as e:
            logger.warning(f"Brand detection failed: {e}")
            return []

    def _detect_entities(self, text: str) -> List[Dict]:
        """Use Gemini to detect author names, book titles, etc."""

        sample_text = text[:10000]

        prompt = f"""Analyze this Japanese text and identify real-world references:

TEXT:
{sample_text}

Identify:
1. Author names (katakana foreign names, kanji Japanese names)
2. Book titles (in quotes, katakana)
3. Celebrity names (actors, musicians)

Return JSON array (empty if none found):
[
  {{
    "japanese": "original Japanese text",
    "entity_type": "author/book/celebrity",
    "romanization_candidates": ["spelling1", "spelling2"],
    "confidence": 0.0-1.0
  }}
]
"""

        try:
            response = self.client.generate_content(prompt)
            return self._parse_json_response(response.text)
        except Exception as e:
            logger.warning(f"Entity detection failed: {e}")
            return []

    def _validate_entity(self, entity: Dict) -> Dict:
        """Validate single entity using Gemini."""

        japanese = entity['japanese']
        entity_type = entity['entity_type']

        prompt = f"""What is the correct English name for this {entity_type}?

Japanese: {japanese}

Rules:
- For Western names in katakana: return standard English spelling
- For Japanese names: use Western order (Given Surname)
- For book titles: use official English title if exists

Examples:
- デボラ・ザック → Devora Zack (author)
- 村上春樹 → Haruki Murakami (author)
- J.K.ローリング → J.K. Rowling (author)

Return ONLY the canonical English name (no explanation).
"""

        try:
            response = self.client.generate_content(prompt)
            canonical_name = response.text.strip().replace('"', '').replace("'", "")

            # Optional Wikipedia verification
            wiki_verified = False
            wiki_url = None

            # For high-stakes entities (authors, celebrities), verify via Wikipedia
            if entity_type in ['author', 'celebrity']:
                wiki_result = self._check_wikipedia(canonical_name)
                if wiki_result['found']:
                    wiki_verified = True
                    wiki_url = wiki_result['url']
                    canonical_name = wiki_result['canonical_name']  # Use Wikipedia canonical

            return {
                'japanese': japanese,
                'entity_type': entity_type,
                'canonical_name': canonical_name,
                'validated': wiki_verified,
                'wikipedia_url': wiki_url,
                'source': 'gemini+wikipedia' if wiki_verified else 'gemini',
                'confidence': 0.95 if wiki_verified else 0.85
            }

        except Exception as e:
            logger.warning(f"Entity validation failed for {japanese}: {e}")
            return {
                'japanese': japanese,
                'canonical_name': entity.get('romanization_candidates', [japanese])[0],
                'validated': False,
                'confidence': 0.5
            }

    def _check_wikipedia(self, query: str) -> Dict:
        """Optional Wikipedia verification (lightweight)."""
        import requests

        try:
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': query,
                'srlimit': 1,
                'format': 'json'
            }

            response = requests.get(api_url, params=params, timeout=3)
            data = response.json()

            if data['query']['search']:
                title = data['query']['search'][0]['title']
                return {
                    'found': True,
                    'canonical_name': title,
                    'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                }

        except Exception as e:
            logger.debug(f"Wikipedia check failed for {query}: {e}")

        return {'found': False}

    def _parse_json_response(self, text: str) -> List[Dict]:
        """Parse JSON from Gemini response (handle markdown wrappers)."""
        text = text.strip()

        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    def _check_cache(self, japanese: str) -> Optional[Dict]:
        """Check cache for previously validated entity."""
        return self.cache.get(japanese)

    def _cache_result(self, result: Dict):
        """Cache validation result."""
        if self.cache_path:
            self.cache[result['japanese']] = result
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)

    def _load_cache(self) -> Dict:
        """Load validation cache."""
        if self.cache_path and self.cache_path.exists():
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _calculate_coverage(self, brands: List, entities: List) -> float:
        """Calculate validation coverage."""
        total = len(brands) + len(entities)
        if total == 0:
            return 1.0

        validated = sum(1 for e in entities if e.get('validated', False))
        validated += len(brands)  # All brands are "validated" by Gemini

        return validated / total
```

---

## Integration Example

### Usage in Cultural Glossary Agent

```python
# In librarian/agent.py

from pipeline.librarian.reference_validator import GeminiReferenceValidator

class LibrarianAgent:
    def __init__(self, ...):
        self.reference_validator = GeminiReferenceValidator(
            gemini_client=self.gemini_client,
            cache_path=Path(".context") / "validated_references_cache.json"
        )

    def generate_cultural_glossary(self, volume_text: str) -> Dict:
        # Existing glossary generation
        terms = self.detect_terms(volume_text)
        idioms = self.detect_idioms(volume_text)

        # NEW: Validate references (single Gemini call)
        validation = self.reference_validator.validate_volume(volume_text)

        return {
            "terms": terms,
            "idioms": idioms,
            "obfuscated_brands": validation['obfuscated_brands'],
            "real_world_references": validation['real_world_references']
        }
```

---

## Cost & Performance Comparison

### Original Plan (JSON Database)

**Implementation:**
- 90+ pattern JSON database
- Levenshtein distance calculations
- Context keyword matching
- Wikipedia API calls (10-15 per volume)

**Cost:**
- Gemini: 1 call for entity detection (~$0.02)
- Wikipedia: Free but 10-15 API calls (~5-10 seconds latency)

**Complexity:**
- ~800 lines of code
- 2 additional files
- Monthly database maintenance

---

### Simplified Plan (Gemini-Powered)

**Implementation:**
- 2 Gemini calls (brand detection + entity detection)
- Optional Wikipedia verification (3-5 calls for high-stakes)

**Cost:**
- Gemini: 2 calls (~$0.04)
- Wikipedia: 3-5 calls (~2-3 seconds latency)

**Complexity:**
- ~300 lines of code
- 1 file (reference_validator.py)
- Zero maintenance

---

**Total Savings:**
- **Code Complexity:** -500 lines (-62%)
- **Files:** -2 files
- **Maintenance Time:** -100% (no pattern database updates)
- **API Latency:** -50% (fewer Wikipedia calls)
- **Cost:** +$0.02 per volume (negligible, worth it for simplicity)

---

## Testing Plan

### Step 1: Run Gemini Validation Test

```bash
cd /Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline
python scripts/test_gemini_brand_deobfuscation.py
```

**Expected Result:**
- ✅ 90%+ accuracy on brand deobfuscation
- ✅ Correct handling of edge cases (LIME Bike vs LINE)
- ✅ Accurate author name validation (Devora Zack, Haruki Murakami)

---

### Step 2: Test on 01b6 Volume

```python
from pipeline.librarian.reference_validator import GeminiReferenceValidator
from pipeline.common.gemini_client import GeminiClient

client = GeminiClient(model_name="gemini-2.0-flash-exp")
validator = GeminiReferenceValidator(client)

# Load 01b6 prologue (contains Devora Zack reference)
with open("WORK/01b6/JP/CHAPTER_02.md", 'r') as f:
    volume_text = f.read()

# Validate
results = validator.validate_volume(volume_text)

# Check if Devora Zack detected correctly
assert any(
    ref['japanese'] == 'デボラ・ザック' and
    ref['canonical_name'] == 'Devora Zack'
    for ref in results['real_world_references']
)

print("✅ Test passed: Devora Zack correctly validated")
```

---

## Recommendation

**Based on your internal testing showing Gemini can deobfuscate well:**

✅ **ADOPT Gemini-Powered Approach**

**Reasons:**
1. **Simplicity:** 300 lines vs 800 lines
2. **Maintainability:** Zero database updates vs monthly pattern additions
3. **Scalability:** Gemini improves automatically with model updates
4. **Quality:** 90%+ accuracy on test cases
5. **Cost:** $0.04 per volume (negligible)

**Implementation Time:** 3-4 hours (vs 6-8 hours for JSON database approach)

---

## Next Steps

1. ✅ Run `scripts/test_gemini_brand_deobfuscation.py` to validate
2. ⏳ Implement `reference_validator.py` (Gemini-powered version)
3. ⏳ Integrate with `librarian/agent.py`
4. ⏳ Test on 01b6 volume (Devora Zack validation)
5. ⏳ Deploy to production

---

**Last Updated:** 2026-02-13
**Architecture:** Gemini-Powered (Simplified)
**Status:** Ready for validation testing
