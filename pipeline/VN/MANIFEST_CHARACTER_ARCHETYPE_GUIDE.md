# Manifest Character Archetype Guide

## Overview
The Vietnamese Grammar RAG uses character archetypes from `manifest.json` to determine speech rhythm patterns. Different character types speak with different rhythms - warriors use terse staccato, scholars use measured cadence, children use erratic bursts.

## How It Works

### 1. Character Definition in manifest.json

```json
{
  "metadata": {
    "characters": [
      {
        "name": "田中剣",
        "name_en": "Tanaka Ken",
        "role": "protagonist",
        "personality_traits": [
          "disciplined",
          "combat_skilled",
          "tactical",
          "protective",
          "stoic"
        ],
        "speech_pattern": "terse_military",
        "archetype": "warrior_soldier",
        "rhythm_profile": {
          "override": false,
          "custom_max_length": 15
        }
      }
    ]
  }
}
```

### 2. Archetype Detection

The system matches `personality_traits` to archetype definitions:

- **Minimum 2 trait overlap** required for archetype assignment
- **Priority traits** (defined in rhythm_rules) carry more weight
- **Fallback to narrator_default** if no strong match

### 3. Rhythm Application

Once archetype is detected:
1. Sentence length limits adjusted per archetype
2. Amputation style applied (hard cuts vs logical breaks)
3. Conjunction/particle usage adapted
4. Rhythm variation pattern enforced

## Character Archetypes

### warrior_soldier
**Personality Traits:** `disciplined`, `combat_skilled`, `tactical`, `aggressive`, `protective`, `stoic`

**Rhythm Profile:**
- Sentence length: 3-10 words (max 15)
- Pattern: Staccato bursts
- Conjunctions: Minimal - periods instead of 'và'
- Particles: Rare - action over commentary

**Example:**
```
JP: 彼は剣を抜いて、敵を睨んで、前に踏み出した。
Default VN: Anh rút kiếm ra và nhìn kẻ địch và bước về phía trước.
Archetype VN: Rút kiếm. Nhìn. Tiến.
```

**Analysis:** Pure action. No elaboration. 2-word bursts. Military precision.

---

### scholar_intellectual
**Personality Traits:** `intelligent`, `analytical`, `bookish`, `methodical`, `strategic`, `contemplative`

**Rhythm Profile:**
- Sentence length: 12-22 words (max 28)
- Pattern: Measured cadence
- Conjunctions: Deliberate - 'mà', 'nhưng', 'vì' for logic
- Particles: Strategic - 'đấy', 'chứ' for emphasis

**Example:**
```
JP: この問題には三つの解決策があるが、どれも一長一短だ。
Default VN: Có ba giải pháp cho vấn đề này nhưng mỗi cái đều có ưu nhược điểm.
Archetype VN: Vấn đề này có ba giải pháp. Mỗi cái đều có điểm mạnh và yếu. Cần cân nhắc kỹ.
```

**Analysis:** Logical unpacking. Each sentence = one reasoning step. Measured tempo.

---

### child_energetic
**Personality Traits:** `cheerful`, `energetic`, `naive`, `excitable`, `childish`, `optimistic`

**Rhythm Profile:**
- Sentence length: 2-8 words (max 12)
- Pattern: Erratic bursts
- Conjunctions: Childish chains - 'rồi', 'nè', 'mà'
- Particles: Abundant - 'à', 'nhỉ', 'nè', 'ư'

**Example:**
```
JP: 見て見て！すごいでしょ？私が作ったんだよ！
Default VN: Nhìn này nhìn này! Tuyệt phải không? Em làm đấy!
Archetype VN: Nhìn này! Nhìn nè! Tuyệt không? Em làm đó! Em làm!
```

**Analysis:** Excited repetition. Particles everywhere. Uneven bursts. Child energy.

---

### noble_formal
**Personality Traits:** `refined`, `elegant`, `aristocratic`, `formal`, `composed`, `traditional`

**Rhythm Profile:**
- Sentence length: 10-18 words (max 22)
- Pattern: Elegant periods
- Conjunctions: Formal but natural - 'còn', 'song', 'tuy nhiên'
- Particles: Refined - 'ấy chứ', 'sao', 'đâu'

**Example:**
```
JP: お話は承りました。しかしながら、この件については熟考が必要です。
Default VN: Tôi đã nghe yêu cầu của ngài rồi. Tuy nhiên, vấn đề này cần xem xét kỹ lưỡng.
Archetype VN: Lời ngài nói, thiếp đã ghi nhận. Song vấn đề này, cần thời gian suy nghĩ.
```

**Analysis:** Balanced clauses. Classical inversion. Elegant pauses. Noble cadence.

---

### tsundere_guarded
**Personality Traits:** `tsundere`, `emotionally_guarded`, `defensive`, `prideful`, `secretly_caring`

**Rhythm Profile:**
- Sentence length: 4-12 words (max 16)
- Pattern: Clipped with softening
- Conjunctions: Defensive - 'đâu có', 'không phải'
- Particles: Mixed - harsh 'mà', 'chứ' → soft 'đấy', 'thôi'

**Example:**
```
JP: 別にあんたのためじゃないんだからね。ただ...作りすぎただけだし。
Default VN: Không phải vì cậu đâu nhé. Chỉ là... em làm nhiều quá thôi.
Archetype VN: Không phải vì cậu. Đừng hiểu lầm. Chỉ là... Làm nhiều. Thế thôi.
```

**Analysis:** Sharp denial → hesitation → soft admission. Rhythm mirrors tsundere emotion.

---

### kuudere_stoic
**Personality Traits:** `stoic`, `emotionless`, `detached`, `observant`, `secretly_emotional`

**Rhythm Profile:**
- Sentence length: 2-6 words (max 10)
- Pattern: Monotone minimal
- Conjunctions: Almost none
- Particles: Rare - only factual 'à', 'ư'

**Example:**
```
JP: そう。分かった。行く。
Default VN: Ừ. Hiểu rồi. Đi.
Archetype VN: Ừ. Hiểu. Đi.
```

**Analysis:** Absolute minimum. No elaboration. Emotionally flat. Pure kuudere.

---

### genki_optimist
**Personality Traits:** `cheerful`, `optimistic`, `energetic`, `friendly`, `outgoing`

**Rhythm Profile:**
- Sentence length: 4-10 words (max 14)
- Pattern: Bouncy repetitive
- Conjunctions: Excited - 'rồi', 'nè', 'mà', 'và' (OK here!)
- Particles: Excessive - all the particles!

**Example:**
```
JP: ねえねえ！今日めっちゃ楽しかったよね！また行こうね！
Default VN: Này này! Hôm nay vui lắm phải không! Đi lại nhé!
Archetype VN: Này nè! Hôm nay vui lắm! Vui lắm luôn! Đi lại nha! Phải đi nha!
```

**Analysis:** Repetition for emphasis. High energy. Particles drive bounce. Genki spirit!

---

### brooding_loner
**Personality Traits:** `brooding`, `introspective`, `loner`, `philosophical`, `melancholic`

**Rhythm Profile:**
- Sentence length: 8-16 words (max 20)
- Pattern: Weighted contemplation
- Conjunctions: Internal - 'nhưng', 'song', 'còn'
- Particles: Reflective - 'sao', 'nhỉ', 'chăng'

**Example:**
```
JP: この世界に意味はあるのか。誰も答えを知らない。
Default VN: Thế giới này có ý nghĩa không. Không ai biết câu trả lời.
Archetype VN: Thế giới này... có ý nghĩa gì không nhỉ. Câu trả lời. Không ai biết.
```

**Analysis:** Ellipses for weight. Fragmented thoughts. Heavy pauses. Brooding atmosphere.

---

### narrator_default
**Personality Traits:** (None - used for narration)

**Rhythm Profile:**
- Sentence length: 8-20 words (max 25)
- Pattern: Natural variation
- Conjunctions: Natural mix
- Particles: Moderate contextual usage

**Example:**
```
JP: 朝日が部屋に差し込んだ。彼は目を覚まして、窓の外を見た。
Default VN: Ánh sáng buổi sáng chiếu vào phòng. Anh thức dậy và nhìn ra ngoài cửa sổ.
Archetype VN: Ánh sáng rọi vào phòng. Anh thức dậy. Nhìn ra ngoài cửa sổ.
```

**Analysis:** Balanced variation. Mix short/medium. Natural narrative flow.

---

## Implementation in manifest.json

### Basic Character Definition
```json
{
  "name": "佐藤花子",
  "name_en": "Sato Hanako",
  "role": "protagonist",
  "personality_traits": [
    "cheerful",
    "energetic",
    "naive",
    "optimistic"
  ],
  "speech_pattern": "genki_cheerful"
}
```

**System auto-detects:** `genki_optimist` archetype (4 trait matches)

### Explicit Archetype Override
```json
{
  "name": "黒崎零",
  "name_en": "Kurosaki Rei",
  "role": "rival",
  "personality_traits": [
    "stoic",
    "mysterious",
    "detached"
  ],
  "speech_pattern": "monotone_minimal",
  "archetype": "kuudere_stoic",
  "rhythm_profile": {
    "override": true,
    "custom_max_length": 8
  }
}
```

**System uses:** Explicit `kuudere_stoic` + custom max length of 8 words

### Complex Character (Multi-Archetype)
```json
{
  "name": "白石美咲",
  "name_en": "Shiraishi Misaki",
  "role": "deuteragonist",
  "personality_traits": [
    "intelligent",
    "analytical",
    "tsundere",
    "prideful",
    "secretly_caring"
  ],
  "speech_pattern": "analytical_defensive",
  "archetype": "tsundere_guarded",
  "archetype_fallback": "scholar_intellectual",
  "rhythm_profile": {
    "switch_contexts": {
      "analyzing": "scholar_intellectual",
      "embarrassed": "tsundere_guarded",
      "default": "tsundere_guarded"
    }
  }
}
```

**System uses:** Context-aware switching between archetypes based on dialogue scene

---

## Trait Mapping Quick Reference

| Personality Traits | Detected Archetype | Rhythm Pattern |
|-------------------|-------------------|----------------|
| disciplined, combat_skilled, tactical | warrior_soldier | Staccato bursts |
| intelligent, analytical, bookish | scholar_intellectual | Measured cadence |
| cheerful, energetic, naive | child_energetic OR genki_optimist | Erratic/bouncy bursts |
| refined, aristocratic, formal | noble_formal | Elegant periods |
| tsundere, emotionally_guarded, prideful | tsundere_guarded | Clipped with softening |
| stoic, emotionless, detached | kuudere_stoic | Monotone minimal |
| brooding, introspective, melancholic | brooding_loner | Weighted contemplation |
| (none/mixed) | narrator_default | Natural variation |

---

## Usage in Translation Pipeline

### Phase 2 (Translation)
1. LLM reads character from manifest
2. Archetype detected from personality_traits
3. Rhythm profile injected into translation prompt
4. Vietnamese output follows archetype rhythm

### Validation
1. vietnamese_grammar_rag.py checks rhythm violations
2. Compares output against archetype expectations
3. Flags violations: "Warrior character using 20-word sentences"
4. Suggests fixes: "Cut to <15 words. Use staccato."

### Example Validation Output
```
Character: 田中剣 (warrior_soldier)
Violation: Sentence length 22 words (max 15 for archetype)
Text: "Anh ta rút kiếm ra và nhìn kẻ địch và bước về phía trước với sự quyết tâm..."
Suggestion: "Rút kiếm. Nhìn địch. Tiến. Quyết tâm."
Archetype Rhythm: Staccato bursts expected (3-10 words)
```

---

## Best Practices

### 1. Define Personality Traits Carefully
✅ DO: `["disciplined", "combat_skilled", "tactical", "protective"]`
❌ DON'T: `["nice", "good", "hero"]` (too generic)

### 2. Use Minimum 3-5 Traits Per Character
- More traits = better archetype detection
- Mix primary (combat_skilled) + secondary (protective) traits

### 3. Override When Needed
- Explicit `archetype` field overrides auto-detection
- Use `rhythm_profile.override` for fine-tuning
- Set `custom_max_length` for unique characters

### 4. Consider Context Switching
- Complex characters may need multiple archetypes
- Use `switch_contexts` for different moods/situations
- Example: Tsundere scholar switches between defensive and analytical

### 5. Test and Validate
- Run rhythm validation on test chapters
- Check if archetype rhythm feels natural
- Adjust personality_traits if rhythm is wrong

---

## Common Patterns

### Battle Scene
```json
"personality_traits": ["combat_skilled", "tactical", "aggressive"]
```
→ warrior_soldier → Staccato action beats

### Love Confession
```json
"personality_traits": ["shy", "emotionally_guarded", "secretly_caring"]
```
→ tsundere_guarded → Hesitant fragments with softening

### Strategic Planning
```json
"personality_traits": ["intelligent", "analytical", "methodical"]
```
→ scholar_intellectual → Measured logical steps

### Comic Relief
```json
"personality_traits": ["cheerful", "energetic", "optimistic"]
```
→ genki_optimist → Bouncy repetitive bursts

---

## Integration with Vietnamese Grammar RAG

### 1. Load Character Data
```python
from modules.vietnamese_grammar_rag import VietnameseGrammarRAG

rag = VietnameseGrammarRAG(config_path="VN/vietnamese_grammar_rag.json")

# Load character from manifest
character_data = {
    "name": "田中剣",
    "personality_traits": ["disciplined", "combat_skilled", "tactical"],
    "archetype": "warrior_soldier"
}
```

### 2. Check Rhythm with Archetype
```python
vietnamese_text = "Anh ta rút kiếm ra và nhìn kẻ địch và bước về phía trước với sự quyết tâm cao độ."

violations = rag.check_rhythm_violations(
    vietnamese_text,
    character_archetype="warrior_soldier"
)

# Output:
# [
#   {
#     "type": "archetype_mismatch",
#     "severity": "high",
#     "character": "田中剣",
#     "expected_archetype": "warrior_soldier",
#     "expected_max_length": 15,
#     "actual_length": 22,
#     "suggestion": "Rút kiếm. Nhìn địch. Tiến. Quyết tâm."
#   }
# ]
```

### 3. Generate Archetype-Aware Translation
```python
prompt_injection = rag.generate_prompt_injection(character_archetype="warrior_soldier")

# Includes:
# - Archetype rhythm rules
# - Max sentence length (15 for warrior)
# - Amputation style (hard cuts)
# - Example transformations
```

---

## Archetype Rhythm Philosophy

**Core Principle:** Character personality determines speech rhythm. Vietnamese rhythm isn't one-size-fits-all.

**Warrior speaks in blades:** Sharp. Fast. No waste.

**Scholar speaks in steps:** Premise. Evidence. Conclusion.

**Child speaks in bursts:** Yay! Look! See! Mine!

**Noble speaks in waves:** Rising clause, sustained thought, graceful fall.

**Tsundere speaks in spikes:** Hard denial → Pause → Soft truth.

**Kuudere speaks in stones:** Ừ. Không. Đi.

**Genki speaks in bounces:** Vui! Vui lắm! Vui lắm luôn!

**Brooding speaks in weights:** Heavy... pause... heavier.

**Narrator speaks in flows:** Mix all. Natural. Varied. Life.

---

## Future Enhancements

### Planned Features:
1. **Dynamic Archetype Switching** - Emotion-based rhythm changes
2. **Archetype Blending** - 70% warrior + 30% scholar
3. **Cultural Context** - Japanese honorifics affect Vietnamese rhythm
4. **Mood Modifiers** - Angry warrior = even shorter sentences
5. **Relationship Dynamics** - Speech changes based on who they're talking to

### Experimental:
- **Voice Actor Guidance** - Rhythm rules → TTS style prompts
- **Chapter-Level Consistency** - Track archetype adherence across chapters
- **Auto-Trait Detection** - ML model predicts archetype from dialogue samples

---

## Conclusion

Archetype-driven rhythm transforms Vietnamese translations from generic output to character-authentic speech patterns. By defining `personality_traits` in `manifest.json`, the system automatically adapts rhythm, sentence length, and amputation style to match character personality.

**Key Takeaway:** Vietnamese rhythm = character voice. Warriors cut sharp. Scholars elaborate. Children bounce. Match rhythm to soul.
