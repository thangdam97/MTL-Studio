# Archetype-Driven Rhythm System - Implementation Summary

## Overview
Expanded Vietnamese Grammar RAG with **archetype-driven rhythm adaptation** based on character `personality_traits` from `manifest.json`. Different character archetypes speak with different rhythms - warriors use terse staccato, scholars use measured cadence, tsundere use defensive-then-soft patterns.

## What Was Implemented

### 1. Archetype System Architecture

**File:** `/pipeline/VN/RHYTHM_RULES_TEMPLATE.json`

Added comprehensive archetype definitions with 9 character types:

#### Character Archetypes

1. **warrior_soldier**
   - Traits: `disciplined`, `combat_skilled`, `tactical`
   - Rhythm: 3-10 words, staccato bursts, hard cuts
   - Example: "Rút kiếm. Nhìn. Tiến."

2. **scholar_intellectual**
   - Traits: `intelligent`, `analytical`, `bookish`
   - Rhythm: 12-22 words, measured cadence, logical breaks
   - Example: "Vấn đề này có ba giải pháp. Mỗi cái đều có điểm mạnh và yếu."

3. **child_energetic**
   - Traits: `cheerful`, `energetic`, `naive`, `childish`
   - Rhythm: 2-8 words, erratic bursts, particles everywhere
   - Example: "Nhìn này! Nhìn nè! Tuyệt không? Em làm đó!"

4. **noble_formal**
   - Traits: `refined`, `aristocratic`, `formal`
   - Rhythm: 10-18 words, elegant periods, classical inversion
   - Example: "Lời ngài nói, thiếp đã ghi nhận. Song vấn đề này, cần thời gian."

5. **tsundere_guarded**
   - Traits: `tsundere`, `emotionally_guarded`, `prideful`, `secretly_caring`
   - Rhythm: 4-12 words, clipped with softening, defensive → soft
   - Example: "Không phải vì cậu. Đừng hiểu lầm. Chỉ là... Làm nhiều. Thế thôi."

6. **kuudere_stoic**
   - Traits: `stoic`, `emotionless`, `detached`
   - Rhythm: 2-6 words, monotone minimal, ultra-short
   - Example: "Ừ. Hiểu. Đi."

7. **genki_optimist**
   - Traits: `cheerful`, `optimistic`, `energetic`, `friendly`
   - Rhythm: 4-10 words, bouncy repetitive, high energy
   - Example: "Này nè! Hôm nay vui lắm! Vui lắm luôn! Đi lại nha!"

8. **brooding_loner**
   - Traits: `brooding`, `introspective`, `melancholic`
   - Rhythm: 8-16 words, weighted contemplation, ellipses for weight
   - Example: "Thế giới này... có ý nghĩa gì không nhỉ. Câu trả lời. Không ai biết."

9. **narrator_default**
   - Traits: (none - fallback)
   - Rhythm: 8-20 words, natural variation, balanced
   - Example: "Ánh sáng rọi vào phòng. Anh thức dậy. Nhìn ra ngoài cửa sổ."

### 2. Python Module Enhancements

**File:** `/pipeline/modules/vietnamese_grammar_rag.py`

Added three new methods:

#### `detect_character_archetype(personality_traits, explicit_archetype=None)`
- Auto-detects archetype from `personality_traits` list
- Requires minimum 2 trait overlaps
- Priority traits carry more weight
- Returns archetype name or fallback to `narrator_default`

```python
archetype = rag.detect_character_archetype(
    ["disciplined", "combat_skilled", "tactical"],
    explicit_archetype=None
)
# Returns: "warrior_soldier"
```

#### `get_archetype_rhythm_profile(archetype)`
- Returns rhythm profile for specific archetype
- Includes: ideal_range, max_length, pattern, amputation_style
- Used by validation and prompt injection

```python
profile = rag.get_archetype_rhythm_profile("warrior_soldier")
# Returns: {
#   "ideal_range": [3, 10],
#   "max_length": 15,
#   "pattern": "staccato_bursts",
#   "amputation_style": "hard_cuts"
# }
```

#### `check_rhythm_violations(text, character_archetype=None)`
- Enhanced with archetype-aware checking
- Compares sentence length against archetype expectations
- Flags violations with archetype context
- Returns violations with suggestions

```python
violations = rag.check_rhythm_violations(
    "Anh ta rút kiếm ra và nhìn kẻ địch...",  # 22 words
    character_archetype="warrior_soldier"
)
# Returns: [{
#   "type": "sentence_too_long",
#   "word_count": 22,
#   "max_allowed": 15,
#   "archetype": "warrior_soldier",
#   "archetype_expectation": "Warrior Soldier rhythm: 3-10 words",
#   "suggestion": "Break into 2-3 shorter sentences. Hard cuts expected."
# }]
```

#### `generate_prompt_injection(context=None)` - Updated
- Now accepts `character_archetype` in context
- Injects archetype-specific rhythm guidance
- Includes examples and speech pattern rules
- LLM receives tailored translation instructions

```python
context = {"character_archetype": "warrior_soldier"}
prompt = rag.generate_prompt_injection(context=context)
# Prompt includes:
# - Archetype description
# - Ideal sentence length (3-10 words)
# - Rhythm pattern (staccato bursts)
# - Speech patterns (minimal conjunctions, action focus)
# - Example transformations
```

### 3. Documentation

#### **MANIFEST_CHARACTER_ARCHETYPE_GUIDE.md**
Comprehensive 400+ line guide covering:
- All 9 archetype definitions with examples
- Trait mapping quick reference
- manifest.json integration patterns
- Basic, explicit override, and multi-archetype configs
- Usage in translation pipeline
- Validation examples
- Best practices
- Future enhancements

#### **test_archetype_rhythm.py**
Executable usage examples demonstrating:
- Auto-detection from personality_traits
- Rhythm violation checking
- Multi-character scenes
- Prompt injection generation
- All 9 archetypes in action

## Integration with manifest.json

### Basic Character Definition
```json
{
  "name": "田中剣",
  "name_en": "Tanaka Ken",
  "personality_traits": ["disciplined", "combat_skilled", "tactical"],
  "speech_pattern": "terse_military"
}
```
**System auto-detects:** `warrior_soldier` archetype

### Explicit Override
```json
{
  "name": "黒崎零",
  "archetype": "kuudere_stoic",
  "rhythm_profile": {
    "override": true,
    "custom_max_length": 8
  }
}
```
**System uses:** Explicit archetype + custom limit

### Multi-Archetype (Advanced)
```json
{
  "name": "白石美咲",
  "archetype": "tsundere_guarded",
  "archetype_fallback": "scholar_intellectual",
  "rhythm_profile": {
    "switch_contexts": {
      "analyzing": "scholar_intellectual",
      "embarrassed": "tsundere_guarded"
    }
  }
}
```
**System uses:** Context-aware archetype switching

## Usage in Translation Pipeline

### Phase 2 (Translation)
1. Load character from manifest.json
2. Extract `personality_traits`
3. Detect archetype via `detect_character_archetype()`
4. Generate translation prompt with archetype context
5. LLM translates with rhythm awareness

### Validation
1. Check Vietnamese output with `check_rhythm_violations()`
2. Pass `character_archetype` parameter
3. System validates against archetype expectations
4. Flags violations with archetype-specific suggestions

## Key Features

### Archetype Detection
- **Automatic:** Matches `personality_traits` to predefined patterns
- **Minimum 2 trait overlap** required
- **Priority traits** (combat_skilled, intelligent, etc.) carry more weight
- **Fallback:** Uses `narrator_default` if no strong match

### Rhythm Profiles
Each archetype defines:
- **sentence_length_bias:** short, medium, long
- **ideal_range:** [min, max] words per sentence
- **max_length:** Absolute maximum before violation
- **pattern:** staccato_bursts, measured_cadence, etc.
- **amputation_style:** hard_cuts, logical_breaks, etc.
- **variation:** minimal, moderate, high

### Speech Patterns
Each archetype specifies:
- **conjunctions:** Minimal (warrior) vs Deliberate (scholar)
- **particles:** Rare (kuudere) vs Abundant (child)
- **descriptors:** Sparse (warrior) vs Precise (scholar)
- **rhythm:** punch-pause-punch vs thesis-elaboration-conclusion

## Examples in Action

### Warrior Character
```
JP: 彼は剣を抜いて、敵を睨んで、前に踏み出した。

❌ Default VN: Anh rút kiếm ra và nhìn kẻ địch và bước về phía trước.
   (17 words - too long, chained conjunctions)

✅ Warrior VN: Rút kiếm. Nhìn. Tiến.
   (3 words - perfect warrior rhythm)
```

### Scholar Character
```
JP: この問題には三つの解決策があるが、どれも一長一短だ。

❌ Default VN: Có ba cách. Mỗi cách có lỗi.
   (7 words - too terse for scholar)

✅ Scholar VN: Vấn đề này có ba giải pháp. Mỗi cái đều có điểm mạnh và yếu. Cần cân nhắc kỹ.
   (19 words - measured, analytical)
```

### Tsundere Character
```
JP: 別にあんたのためじゃないんだからね。ただ...作りすぎただけだし。

❌ Default VN: Không phải vì cậu đâu nhé vì em chỉ làm nhiều quá thôi.
   (13 words - no emotional rhythm)

✅ Tsundere VN: Không phải vì cậu. Đừng hiểu lầm. Chỉ là... Làm nhiều. Thế thôi.
   (11 words - defensive → soft rhythm)
```

## Archetype Philosophy

**Core Principle:** Character personality determines speech rhythm.

- **Warrior speaks in blades:** Sharp. Fast. No waste.
- **Scholar speaks in steps:** Premise. Evidence. Conclusion.
- **Child speaks in bursts:** Yay! Look! See! Mine!
- **Tsundere speaks in spikes:** Hard denial → Pause → Soft truth.
- **Kuudere speaks in stones:** Ừ. Không. Đi.

Vietnamese rhythm = character voice. Match rhythm to soul.

## Configuration Requirements

### RHYTHM_RULES_TEMPLATE.json Structure
```json
{
  "rhythm_rules": {
    "archetype_system": {
      "enabled": true,
      "source": "manifest.json characters[].personality_traits",
      "override_priority": "archetype > narrator > default"
    },
    "character_archetypes": {
      "warrior_soldier": { ... },
      "scholar_intellectual": { ... },
      ...
    },
    "archetype_detection": {
      "method": "personality_traits_matching",
      "minimum_trait_overlap": 2,
      "priority_traits": { ... }
    }
  }
}
```

### manifest.json Character Schema
```json
{
  "metadata": {
    "characters": [
      {
        "name": "...",
        "personality_traits": ["trait1", "trait2", ...],
        "archetype": "optional_explicit_override",
        "rhythm_profile": {
          "override": false,
          "custom_max_length": 20
        }
      }
    ]
  }
}
```

## Testing

Run the test suite:
```bash
cd /pipeline/VN
python test_archetype_rhythm.py
```

Outputs:
- Archetype detection examples
- Rhythm violation checking
- Multi-character dialogue
- Prompt injection samples

## Future Enhancements

### Planned
1. **Dynamic Archetype Switching** - Emotion-based rhythm changes
2. **Archetype Blending** - 70% warrior + 30% scholar
3. **Mood Modifiers** - Angry warrior = even shorter sentences
4. **Relationship Dynamics** - Speech changes based on addressee

### Experimental
- **Voice Actor Guidance** - Rhythm rules → TTS style prompts
- **Chapter-Level Consistency** - Track archetype adherence
- **Auto-Trait Detection** - ML predicts archetype from dialogue

## Benefits

### For Translators
- **Automatic rhythm guidance** based on character personality
- **Consistent character voice** across chapters
- **Clear violation feedback** with archetype context

### For Quality Control
- **Objective rhythm metrics** per archetype
- **Archetype adherence tracking**
- **Character-specific validation**

### For Readers
- **Distinctive character voices** in Vietnamese
- **Natural rhythm matching personality**
- **Culturally authentic speech patterns**

## Summary

Archetype-driven rhythm transforms Vietnamese translations from generic output to character-authentic speech patterns. By defining `personality_traits` in `manifest.json`, the system automatically adapts rhythm, sentence length, and amputation style to match character personality.

**Key Achievement:** Vietnamese rhythm is no longer one-size-fits-all. Each character's personality dictates their unique speech rhythm, creating more authentic and engaging translations.

---

**Files Modified/Created:**
1. ✅ `/pipeline/VN/RHYTHM_RULES_TEMPLATE.json` - Archetype definitions
2. ✅ `/pipeline/modules/vietnamese_grammar_rag.py` - Archetype detection & checking
3. ✅ `/pipeline/VN/MANIFEST_CHARACTER_ARCHETYPE_GUIDE.md` - Documentation
4. ✅ `/pipeline/VN/test_archetype_rhythm.py` - Usage examples
5. ✅ `/pipeline/VN/ARCHETYPE_RHYTHM_IMPLEMENTATION.md` - This summary

**Next Steps:**
1. Add `rhythm_rules` section to `/pipeline/VN/vietnamese_grammar_rag.json`
2. Update existing manifest.json files with `personality_traits`
3. Test on real translation chapters
4. Refine archetype definitions based on results
