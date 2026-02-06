# Archetype Quick Reference Table

## Archetype → Rhythm Mapping

| Archetype | Ideal Length | Max | Pattern | Conjunctions | Particles | Example |
|-----------|-------------|-----|---------|--------------|-----------|---------|
| **warrior_soldier** | 3-10 | 15 | Staccato bursts | Minimal (periods) | Rare (action focus) | "Rút kiếm. Nhìn. Tiến." |
| **scholar_intellectual** | 12-22 | 28 | Measured cadence | Deliberate (logic) | Strategic (emphasis) | "Vấn đề có ba giải pháp. Mỗi cái có ưu nhược điểm." |
| **child_energetic** | 2-8 | 12 | Erratic bursts | Childish chains | Abundant (excited) | "Nhìn này! Tuyệt không? Em làm!" |
| **noble_formal** | 10-18 | 22 | Elegant periods | Formal natural | Refined classical | "Lời ngài nói, thiếp ghi nhận. Song cần thời gian." |
| **tsundere_guarded** | 4-12 | 16 | Clipped → soft | Defensive denial | Mixed harsh→soft | "Không phải vì cậu. Chỉ là... Thế thôi." |
| **kuudere_stoic** | 2-6 | 10 | Monotone minimal | Almost none | Rare factual | "Ừ. Hiểu. Đi." |
| **genki_optimist** | 4-10 | 14 | Bouncy repetitive | Excited chains | Excessive! | "Vui lắm! Vui lắm luôn! Đi nha!" |
| **brooding_loner** | 8-16 | 20 | Weighted contemplation | Internal flow | Reflective pauses | "Thế giới... có ý nghĩa không nhỉ. Không ai biết." |
| **narrator_default** | 8-20 | 25 | Natural variation | Natural mix | Moderate contextual | "Ánh sáng rọi vào. Anh thức dậy. Nhìn ra ngoài." |

---

## Personality Traits → Archetype Detection

### Priority Trait Mapping

| Personality Traits | Detected Archetype | Confidence |
|-------------------|-------------------|-----------|
| disciplined, combat_skilled, tactical | **warrior_soldier** | HIGH |
| intelligent, analytical, bookish | **scholar_intellectual** | HIGH |
| cheerful, energetic, naive, childish | **child_energetic** | HIGH |
| refined, aristocratic, formal | **noble_formal** | HIGH |
| tsundere, emotionally_guarded, prideful | **tsundere_guarded** | HIGH |
| stoic, emotionless, detached | **kuudere_stoic** | HIGH |
| cheerful, optimistic, friendly, outgoing | **genki_optimist** | MEDIUM* |
| brooding, introspective, melancholic | **brooding_loner** | MEDIUM |

*Note: `genki_optimist` may overlap with `child_energetic` - use age context.

### Minimum Overlap Requirements

- **2+ matching traits** = Archetype assigned
- **<2 matching traits** = Falls back to `narrator_default`
- **Explicit `archetype` field** = Overrides auto-detection

---

## Amputation Style Guide

| Archetype | Amputation Style | Japanese て-form | Vietnamese Result |
|-----------|-----------------|------------------|------------------|
| **warrior_soldier** | Hard cuts | 立って走って戦った | Đứng. Chạy. Chiến. |
| **scholar_intellectual** | Logical breaks | AでBでCだ | A. Do đó B. Vì vậy C. |
| **child_energetic** | Excitement breaks | 見て見て！ | Nhìn này! Nhìn nè! |
| **noble_formal** | Graceful pauses | AてBて | A, rồi B một cách nhẹ nhàng. |
| **tsundere_guarded** | Defensive cuts | 違って...でも | Không phải. Đừng... Nhưng. |
| **kuudere_stoic** | Extreme cuts | そうで行く | Ừ. Đi. |
| **genki_optimist** | Enthusiasm breaks | 楽しくて嬉しい！ | Vui! Vui lắm! Tuyệt! |
| **brooding_loner** | Thoughtful pauses | 考えて...悩んで | Suy nghĩ... Rồi băn khoăn... |
| **narrator_default** | Contextual | て-form chains | Natural Vietnamese flow |

---

## Conjunction Usage Matrix

| Archetype | 'và' | 'rồi' | 'mà' | 'nhưng' | 'vì' | Notes |
|-----------|------|-------|------|---------|------|-------|
| **warrior_soldier** | ❌ | ❌ | ❌ | ❌ | ❌ | Use periods instead |
| **scholar_intellectual** | ✅ | ✅ | ✅ | ✅ | ✅ | For logical flow |
| **child_energetic** | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | Simple conjunctions only |
| **noble_formal** | ✅ | ✅ | ✅ | ✅ | ✅ | Classical alternatives OK |
| **tsundere_guarded** | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ | Defensive tone key |
| **kuudere_stoic** | ❌ | ❌ | ❌ | ❌ | ❌ | Absolute minimum |
| **genki_optimist** | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | Excited chains OK |
| **brooding_loner** | ✅ | ✅ | ✅ | ✅ | ✅ | For internal monologue |
| **narrator_default** | ✅ | ✅ | ✅ | ✅ | ✅ | Contextual natural use |

Legend: ✅ = Encouraged | ⚠️ = Use sparingly | ❌ = Avoid

---

## Particle Frequency Guide

| Archetype | Question (không/sao) | Affirmation (à/nhỉ) | Softening (thôi/đấy) | Exclamation (nha/nè) |
|-----------|---------------------|---------------------|---------------------|---------------------|
| **warrior_soldier** | RARE | RARE | NONE | NONE |
| **scholar_intellectual** | MODERATE | LOW | LOW | RARE |
| **child_energetic** | HIGH | HIGH | HIGH | VERY HIGH |
| **noble_formal** | LOW | MODERATE | MODERATE | RARE |
| **tsundere_guarded** | LOW | MODERATE | HIGH | LOW |
| **kuudere_stoic** | RARE | RARE | NONE | NONE |
| **genki_optimist** | HIGH | VERY HIGH | HIGH | VERY HIGH |
| **brooding_loner** | MODERATE | HIGH | MODERATE | RARE |
| **narrator_default** | MODERATE | MODERATE | MODERATE | MODERATE |

Frequency: NONE < RARE < LOW < MODERATE < HIGH < VERY HIGH

---

## Common Mistakes & Fixes

### Warrior Character - Too Long
❌ **BAD:** "Anh ta rút kiếm ra và nhìn kẻ địch và bước về phía trước với quyết tâm."
✅ **GOOD:** "Rút kiếm. Nhìn địch. Tiến. Quyết tâm."

### Scholar Character - Too Terse
❌ **BAD:** "Có ba cách. Mỗi cách có lỗi."
✅ **GOOD:** "Vấn đề này có ba giải pháp. Mỗi giải pháp có ưu và nhược điểm riêng."

### Tsundere Character - Missing Rhythm Breaks
❌ **BAD:** "Không phải vì cậu đâu vì em chỉ làm nhiều."
✅ **GOOD:** "Không phải vì cậu. Đừng nghĩ nhiều. Chỉ là... Làm nhiều. Thế thôi."

### Kuudere Character - Too Elaborate
❌ **BAD:** "Ừ thì em hiểu rồi và em sẽ đi."
✅ **GOOD:** "Ừ. Hiểu. Đi."

### Child Character - Missing Particles
❌ **BAD:** "Nhìn này. Tuyệt. Em làm."
✅ **GOOD:** "Nhìn này! Nhìn nè! Tuyệt không? Em làm đó! Em làm!"

---

## Archetype Blending (Advanced)

### Mixed Personality Characters

#### Tsundere Scholar (70% tsundere / 30% scholar)
```
Analyzing mode: "Vấn đề này có ba giải pháp logic. Nhưng đừng nghĩ em lo cho cậu đâu."
Embarrassed mode: "Không phải vậy. Em chỉ... phân tích khách quan. Thế thôi."
```

#### Warrior Noble (60% warrior / 40% noble)
```
Combat: "Rút kiếm. Chuẩn bị."
Formal setting: "Mệnh lệnh của ngài, thiếp đã nhận. Sẽ thực hiện ngay lập tức."
```

#### Genki Scholar (50% genki / 50% scholar)
```
Excited discovery: "Tìm ra rồi! Có ba lý thuyết! Cả ba đều hợp lý! Phải thử hết!"
```

---

## manifest.json Configuration Examples

### Basic Auto-Detection
```json
{
  "name": "田中剣",
  "personality_traits": ["disciplined", "combat_skilled"]
}
```
→ Auto-detects: `warrior_soldier`

### Explicit Override
```json
{
  "name": "黒崎零",
  "personality_traits": ["stoic", "detached"],
  "archetype": "kuudere_stoic"
}
```
→ Uses: `kuudere_stoic` (explicit)

### Custom Limits
```json
{
  "name": "カスタム",
  "archetype": "warrior_soldier",
  "rhythm_profile": {
    "override": true,
    "custom_max_length": 12
  }
}
```
→ Uses warrior rhythm but max 12 words instead of 15

### Context Switching
```json
{
  "name": "美咲",
  "personality_traits": ["intelligent", "tsundere"],
  "archetype": "tsundere_guarded",
  "rhythm_profile": {
    "switch_contexts": {
      "analyzing": "scholar_intellectual",
      "embarrassed": "tsundere_guarded",
      "default": "tsundere_guarded"
    }
  }
}
```
→ Switches between archetypes based on scene context

---

## Validation Workflow

```python
# 1. Load character from manifest
character = manifest["characters"][0]

# 2. Detect archetype
archetype = rag.detect_character_archetype(
    character["personality_traits"],
    character.get("archetype")
)

# 3. Validate Vietnamese output
violations = rag.check_rhythm_violations(
    vietnamese_text,
    character_archetype=archetype
)

# 4. Check violations
for v in violations:
    if v["type"] == "sentence_too_long":
        print(f"⚠️  {v['word_count']} words (max {v['max_allowed']})")
        print(f"   Archetype: {v['archetype']}")
        print(f"   Fix: {v['suggestion']}")
```

---

## LLM Prompt Injection

When translating dialogue:
```python
context = {
    "character_archetype": "warrior_soldier",
    "character_name": "Ken"
}

prompt_injection = rag.generate_prompt_injection(context=context)
```

LLM receives:
- Archetype description
- Ideal sentence length
- Rhythm pattern guidelines
- Speech pattern rules
- Before/after examples
- Amputation style instructions

---

## Testing Command

```bash
cd /Users/.../MTL_STUDIO/pipeline/VN
python test_archetype_rhythm.py
```

Expected output:
- ✅ 6 examples demonstrating all archetypes
- ✅ Auto-detection from personality_traits
- ✅ Rhythm violation checking
- ✅ Multi-character dialogue
- ✅ Prompt injection samples

---

## Performance Metrics

### Target Adherence Rates

| Archetype | Target Adherence | Typical Violation Rate |
|-----------|-----------------|----------------------|
| **warrior_soldier** | 90%+ (strict) | <10% |
| **scholar_intellectual** | 85%+ (flexible) | <15% |
| **kuudere_stoic** | 95%+ (ultra-strict) | <5% |
| **genki_optimist** | 80%+ (irregular OK) | <20% |
| **narrator_default** | 85%+ (balanced) | <15% |

Lower adherence = More flexible archetype (genki, child)
Higher adherence = Stricter rhythm (warrior, kuudere)

---

## Summary

**9 archetypes** × **unique rhythm profiles** = **character-authentic Vietnamese**

Each archetype defines:
- Sentence length expectations
- Amputation style
- Conjunction/particle usage
- Rhythm pattern

System automatically:
- Detects archetype from `personality_traits`
- Validates against archetype expectations
- Injects archetype-specific translation guidance
- Flags rhythm violations with context

**Result:** Vietnamese translations that sound like the character, not a generic translator.
