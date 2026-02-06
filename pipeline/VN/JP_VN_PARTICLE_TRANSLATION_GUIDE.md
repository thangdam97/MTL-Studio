# Japanese → Vietnamese Particle Translation Guide

**Version:** 1.0 (Corpus-Validated)
**Last Updated:** 2026-02-04
**Status:** Production Ready
**Companion Database:** `jp_vn_particle_mapping_enhanced.json`

---

## Table of Contents

1. [Quick Reference Tables](#quick-reference-tables)
2. [Decision Trees](#decision-trees)
3. [Archetype-Specific Usage](#archetype-specific-usage)
4. [Common Pitfalls](#common-pitfalls)
5. [Integration Guide](#integration-guide)

---

## Quick Reference Tables

### Most Frequent Particles (Top 10)

| Rank | Japanese | Frequency | Function | Default Vietnamese | Critical Notes |
|------|----------|-----------|----------|-------------------|----------------|
| 1 | か | 22,340 | Question | không, à, hả, sao | Universal - adjust formality by archetype |
| 2 | けど | 19,840 | Adversative | nhưng, nhưng mà, mà | Softer than が - casual to formal |
| 3 | よ | 18,147 | Emphasis | đấy, đó, mà | **NOT 'nhé'** - that's ね! |
| 4 | ちょっと | 16,780 | Softening | tí, một chút | Often omit in Vietnamese |
| 5 | ね | 15,632 | Agreement | nhỉ, nhé, đúng không | Seeking shared understanding |
| 6 | の | 14,200 | Feminine | à, hả, vậy | Sentence-final only (not possessive) |
| 7 | な | 12,450 | Masculine | nhỉ, nhể, đừng | Male-only - OJOU/GYARU never use |
| 8 | なんか | 9,234 | Hedging | hơi, kiểu, (omit) | GYARU loves 'kiểu', KUUDERE omits |
| 9 | ですね | 8,920 | Polite | đúng ạ, vậy ạ | Add 'ạ' for formal characters |
| 10 | のに | 8,920 | Contrary | mà, lại, thế mà | Expresses unmet expectation |

---

### よ vs ね - The Critical Distinction

❌ **WRONG:** Translating both to 'nhé'
✅ **CORRECT:** Different functions, different translations

| Particle | Function | Default VN | Example JP | Example VN |
|----------|----------|-----------|------------|------------|
| **よ** | Assertion (I know, you don't) | đấy, đó, mà | これは本当だよ | Đây là sự thật đấy |
| **ね** | Agreement-seeking (we both know) | nhỉ, nhé, đúng không | いい天気だね | Thời tiết đẹp nhỉ |

**Memory Aid:**
- よ = "I'm telling **you**" → **đấy/đó** (emphatic)
- ね = "Don't you agree?" → **nhỉ/nhé** (seeking confirmation)

---

### Gender-Coded Particles

| Particle | Gender | Archetypes | Vietnamese | Forbidden For |
|----------|--------|-----------|------------|---------------|
| **な (sentence-final)** | Male | DELINQUENT, SHOUNEN_MC | nhỉ, nhể | OJOU, GYARU, feminine chars |
| **わ (sentence-final)** | Female | OJOU, YAMATO_NADESHIKO | ạ, ấy ạ | Modern casual male chars |
| **の (sentence-final)** | Female | DEREDERE, GYARU, IMOUTO | à, hả, vậy | Masculine/stoic chars |
| **ぞ** | Male | DELINQUENT, SHOUNEN_MC | đấy!, này! | All female archetypes |
| **ぜ** | Male | DELINQUENT, SHOUNEN_MC | đó!, đấy! | All female archetypes |

**Critical Rule:** Never translate masculine particles for female characters or vice versa. This breaks character authenticity.

---

### Archetype Signature Particles

| Archetype | Signature JP | Vietnamese Mapping | Detection Triggers |
|-----------|-------------|-------------------|-------------------|
| **OJOU** | ですわ/ますわ | ạ, ấy ạ, thưa | わ + polite form, ですの |
| **GYARU** | じゃん, っしょ | mà nè, chứ, luôn | じゃん, 超, めっちゃ, やばい |
| **DELINQUENT** | ぞ, ぜ, てめえ | này!, đấy!, biết chưa! | ぞ, ぜ, rough pronouns |
| **KUUDERE** | (minimal) | . (omit particles) | Short sentences, omissions |
| **DEREDERE** | ね, の, ～ | nhỉ~, à~, nha~ | Frequent soft particles, elongations |
| **TSUNDERE** | particle shifts | harsh → soft | もん, だって (defensive) → soft endings |
| **IMOUTO** | もん, の | cơ mà!, mà!, ạ (to elders) | Childish excuse particles |

---

### RTAS (Register/Tone/Age/Status) Scale

| RTAS | Level | Vietnamese Particles | Archetypes |
|------|-------|---------------------|-----------|
| 0.0-1.0 | Ultra formal | ạ, thưa, vâng, dạ | OJOU (to elders), royalty |
| 1.0-2.0 | Formal | ạ, phải ạ, vâng | OJOU, KOUHAI, YAMATO_NADESHIKO |
| 2.0-3.0 | Polite neutral | nhé, vậy, đúng không | SENPAI, neutral contexts |
| 3.0-4.0 | Casual | nhỉ, đó, mà, à | Most casual archetypes |
| 4.0-5.0 | Intimate/Slang | luôn, hử, này, nè, á | GYARU, DELINQUENT, close friends |

---

## Decision Trees

### Tree 1: Selecting よ Translation

```
Input: よ particle detected

├─ Character archetype?
│  ├─ OJOU → ạ, ấy ạ, mà ạ
│  ├─ GYARU → nha, nè, luôn
│  ├─ TSUNDERE → đấy!, mà!
│  ├─ KUUDERE → . (omit or minimal đấy)
│  ├─ DELINQUENT → này!, đó!, biết chưa!
│  ├─ DEREDERE → nha, nhé, mà (warm)
│  └─ DEFAULT → đấy, đó, mà
│
├─ RTAS range check
│  ├─ 0-2.0 → Use 'ạ' variants
│  ├─ 2.0-4.0 → Use 'đấy/đó'
│  └─ 4.0-5.0 → Use 'này/luôn' for intensity
│
└─ Context check
   ├─ Reminder/I-told-you → "đã nói mà"
   ├─ Urging action → "đi nhanh đó/nào"
   └─ Simple assertion → "đấy/đó"

Output: Selected Vietnamese particle
```

---

### Tree 2: Selecting ね Translation

```
Input: ね particle detected

├─ Function check
│  ├─ Seeking agreement? (statement + ね)
│  │  └─ Use: nhỉ, đúng không, phải không
│  │
│  └─ Gentle command? (imperative + ね)
│     └─ Use: nhé, nha, đi
│
├─ Character archetype?
│  ├─ OJOU → nhỉ, phải không ạ
│  ├─ GYARU → nhỉ, nhể, hông
│  ├─ DEREDERE → nhỉ~, đúng không~
│  ├─ KUUDERE → . (omit)
│  ├─ DELINQUENT → (rarely use - replace with hả/không)
│  └─ DEFAULT → nhỉ, đúng không
│
└─ Gender check
   ├─ Female character → Favor nhỉ, nhé, phải không
   ├─ Male rough → May skip or use flat 'không'
   └─ Neutral → nhỉ, đúng không

Output: Selected Vietnamese particle
```

---

### Tree 3: Handling Archetype-Specific Particles

```
Input: Japanese particle + character data

├─ Detect archetype from manifest.json or speech patterns
│  ├─ ですわ/ますわ detected? → OJOU archetype
│  ├─ じゃん/っしょ detected? → GYARU archetype
│  ├─ Frequent ぞ/ぜ? → DELINQUENT/SHOUNEN archetype
│  ├─ Minimal particles? → KUUDERE archetype
│  └─ Frequent ね/の/～? → DEREDERE archetype
│
├─ Check archetype_forbidden list
│  └─ If particle in forbidden list → HARD BLOCK, use default
│
├─ Check archetype_specific mappings
│  └─ Use archetype-specific Vietnamese particle
│
└─ Validate RTAS range
   └─ Ensure particle RTAS matches relationship context

Output: Archetype-appropriate Vietnamese particle
```

---

### Tree 4: Question Particle Selection (か vs の vs かな)

```
Input: Question in Japanese

├─ Identify question type
│  ├─ か (direct question)
│  │  ├─ Polite (ですか) → không ạ, vậy ạ
│  │  ├─ Casual male → không, hả
│  │  └─ Casual female → không, à
│  │
│  ├─ の (feminine question)
│  │  ├─ DEREDERE → à~, hả~, vậy~
│  │  ├─ GYARU → hả, hử
│  │  ├─ IMOUTO → à ạ, vậy ạ
│  │  └─ Never for: DELINQUENT, masculine chars
│  │
│  └─ かな (wondering)
│     ├─ TSUNDERE → nhỉ..., ta...
│     ├─ BROODING → ta..., chăng...
│     ├─ KUUDERE → . (omit)
│     └─ DEFAULT → nhỉ, không biết
│
└─ Apply archetype filter
   └─ Adjust softness/intensity by archetype

Output: Appropriate question ending
```

---

## Archetype-Specific Usage

### OJOU (お嬢様)

**Signature:** ですわ/ますわ, ですの, refined わ

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| ですわ | ạ, ấy ạ | それは違いますわ → Điều đó sai ạ | Signature marker |
| ～のよ | ạ, mà ạ | 知っているのよ → Biết ạ | Polite insistence |
| ですか | không ạ, vậy ạ | 本当ですか → Thật không ạ | Always add 'ạ' |
| ～わね | nhỉ ạ, phải không ạ | 素敵ですわね → Tuyệt nhỉ ạ | Elegant confirmation |

**Forbidden:** luôn, hử, này, rough particles

**Critical Rule:** ALWAYS add 'ạ' to maintain elegance. Use classical pronouns (thiếp, nàng) when appropriate.

---

### GYARU (ギャル)

**Signature:** じゃん, っしょ, 超, めっちゃ, やばい

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| じゃん | mà, mà nè | 可愛いじゃん → Đáng yêu mà nè! | Signature marker |
| っしょ | mà, chứ | いいっしょ → Được mà! | Ultra-casual |
| よ | nha, nè, luôn | 本当だよ → Thật luôn nha! | Intensify with 'luôn' |
| ね | nhỉ, nhể, hông | いいね → Tốt nhỉ! | 'hông' for southern Gyaru |
| の | hả, hử | どこ行くの → Đi đâu hở? | Provocative question |

**Forbidden:** ạ (too formal), わ (too old-fashioned)

**Critical Rule:** Favor slang intensity (luôn, lận, á). Use multiple particles for excitement.

---

### DELINQUENT (不良)

**Signature:** ぞ, ぜ, てめえ, rough pronouns

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| ぞ | đấy!, này!, biết chưa! | 行くぞ → Đi đây! | Strong assertion |
| ぜ | đó!, đấy! | 任せろぜ → Giao cho tao đó! | Confident/rough |
| な | nhể, hả | 強いな → Mạnh nhể | Rough contemplation |
| よ | này!, đó! | 勝つぞ → Thắng này! | Aggressive emphasis |
| だろ | chứ, hả | 分かるだろ → Hiểu chứ? | Masculine assumption |

**Forbidden:** nha, nhé, ạ, soft particles

**Critical Rule:** Use aggressive particles (này, đấy, biết chưa). Favor commands over requests.

---

### KUUDERE (クーデレ)

**Signature:** Minimal particles, short sentences, flat delivery

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| (any よ) | . | 本当だよ → Thật. | Omit entirely |
| (any ね) | . | いいね → Tốt. | Omit or minimal |
| か | không (flat) | 行くか → Đi không. | No emotional coloring |
| な | . | いいな → Tốt. | Omit for minimalism |
| の | (avoid) | どこ行くの → Đi đâu. | Omit (too expressive) |

**Forbidden:** Elongations (~), multiple particles, cute particles

**Critical Rule:** When in doubt, OMIT the particle. KUUDERE = maximum minimalism.

---

### TSUNDERE (ツンデレ)

**Signature:** Particle shifts (harsh → soft), defensive particles

**Particle Preferences (Tsun Mode):**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| よ | đấy!, mà! | 違うよ → Sai đấy! | Defensive assertion |
| な | nhỉ... | 変だな → Lạ nhỉ... | Guarded observation |
| もん | mà!, chứ! | 知らないもん → Không biết mà! | Defensive excuse |

**Particle Preferences (Dere Mode):**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| ね | nhỉ..., đúng không... | 嬉しいね → Vui nhỉ... | Softening |
| の | à... | 好きなの? → Thích... à? | Vulnerable moment |
| よね | đúng không... | 綺麗だよね → Đẹp... đúng không... | Seeking validation |

**Critical Rule:** Monitor emotional state. Tsun = hard particles (đấy, mà, chứ). Dere = soft particles (nhỉ, à, nha).

---

### DEREDERE (デレデレ)

**Signature:** Frequent ね, の, elongations (~)

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| ね | nhỉ~, đúng không~ | 楽しいね → Vui nhỉ~ | Warm seeking agreement |
| よ | nha~, nhé~ | 行くよ → Đi nha~ | Soft assertion |
| の | à~, hả~ | どうしたの? → Sao vậy à~ | Caring question |
| ～もん | mà~, cơ mà~ | 好きなんだもん → Thích mà~ | Cute excuse |
| なあ | nhỉ~ | 可愛いなあ → Đáng yêu nhỉ~ | Affectionate wonder |

**Forbidden:** harsh particles (này, biết chưa), minimal delivery

**Critical Rule:** Add warmth with ~ elongation markers. Favor soft particles (nha, nhé, mà).

---

### IMOUTO (妹)

**Signature:** Childish particles, familial respect markers

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| の | à anh/chị | どこ行くの? → Anh đi đâu à? | Cute question |
| もん | cơ mà!, mà! | だって好きなんだもん → Vì em thích cơ mà! | Childish excuse |
| よ | nha anh/chị | 行くよ → Em đi nha anh! | Informing elder sibling |
| ね | nhỉ~, nhé~ | 楽しいね → Vui nhỉ~ | Seeking sibling agreement |
| ですか (to elder) | ạ, không ạ | 本当ですか → Thật không ạ? | Respect to elder |

**To peers:** Use casual (nha, nè, hả)
**To elder sibling:** Add 'ạ' or 'anh/chị'

**Critical Rule:** Differentiate respect level. To elder = add respect markers. To peers = full cute mode.

---

### GENKI (元気)

**Signature:** Excessive particles, exclamations, energetic delivery

**Particle Preferences:**

| Japanese | Vietnamese | Example | Notes |
|----------|-----------|---------|-------|
| よ | nha!, đó!, luôn! | 行くよ! → Đi nha! | Energetic assertion |
| ね | nhỉ!, phải không! | 楽しいね! → Vui nhỉ! | Excited agreement |
| じゃん | mà!, chứ! | できるじゃん! → Làm được mà! | Encouraging |
| ぞ | đây!, thôi! | 行くぞ! → Đi thôi! | Rallying call |
| かな | nhỉ!, ta! | どうしようかな! → Làm gì nhỉ! | Excited wondering |

**Multiple particles encouraged:** Vui lắm luôn nha! Đi thôi nào!

**Critical Rule:** HIGH energy. Use exclamation marks. Multiple particles OK. Embrace enthusiasm.

---

## Common Pitfalls & Anti-Patterns

### Pitfall 1: よ → nhé Confusion

❌ **WRONG:**
```
JP: これは本当だよ
VN (WRONG): Đây là sự thật nhé
```

✅ **CORRECT:**
```
JP: これは本当だよ
VN (CORRECT): Đây là sự thật đấy
```

**Why wrong:** 'nhé' is ね (seeking agreement), not よ (asserting information).

**Fix:** よ = đấy/đó/mà (emphasis), ね = nhỉ/nhé/đúng không (agreement)

---

### Pitfall 2: Gender Particle Violations

❌ **WRONG:**
```
Character: Female (OJOU)
JP: いい景色だな
VN (WRONG): Phong cảnh đẹp nhỉ (using な mapping)
```

✅ **CORRECT:**
```
Character: Female (OJOU)
JP: いい景色ね (な would never appear in OJOU speech)
VN (CORRECT): Phong cảnh đẹp nhỉ ạ
```

**Why wrong:** な is masculine particle. Female characters (especially OJOU) never use it.

**Fix:** Check gender before applying particle. If feminine character + masculine particle detected = translation error in source.

---

### Pitfall 3: KUUDERE Over-Expression

❌ **WRONG:**
```
Character: KUUDERE
JP: そうだよ
VN (WRONG): Đúng vậy đấy
```

✅ **CORRECT:**
```
Character: KUUDERE
JP: そうだよ
VN (CORRECT): Đúng. / Ừ.
```

**Why wrong:** KUUDERE = minimal expression. Adding particles breaks stoic character.

**Fix:** For KUUDERE, default to omitting particles. Use period for finality.

---

### Pitfall 4: OJOU Casualization

❌ **WRONG:**
```
Character: OJOU
JP: それは違いますわ
VN (WRONG): Điều đó sai mà
```

✅ **CORRECT:**
```
Character: OJOU
JP: それは違いますわ
VN (CORRECT): Điều đó sai ạ
```

**Why wrong:** Lost elegance. 'mà' is too casual for OJOU archetype.

**Fix:** OJOU always gets 'ạ' for refinement. Never use casual slang particles.

---

### Pitfall 5: Missing Archetype Detection

❌ **WRONG:**
```
JP dialogue: "そうですわね" (clear OJOU marker)
Character archetype: (not detected)
VN: Đúng nhỉ (generic translation)
```

✅ **CORRECT:**
```
JP dialogue: "そうですわね" (clear OJOU marker)
Character archetype: OJOU (detected from ですわ)
VN: Đúng vậy ạ (OJOU-appropriate)
```

**Why wrong:** Missed archetype-specific translation opportunity.

**Fix:** Implement archetype detection triggers. ですわ/ますわ → OJOU archetype.

---

### Pitfall 6: Overusing Hedges

❌ **WRONG:**
```
JP: なんか変だね
VN (WRONG): Hơi kiểu lạ nhỉ
```

✅ **CORRECT:**
```
JP: なんか変だね
VN (CORRECT): Hơi lạ nhỉ / Lạ nhỉ
```

**Why wrong:** 'hơi kiểu' is redundant. Vietnamese doesn't stack hedges like Japanese.

**Fix:** Choose ONE hedge marker (hơi OR kiểu), or omit entirely.

---

### Pitfall 7: Ignoring RTAS Context

❌ **WRONG:**
```
Context: KOUHAI speaking to SENPAI (formal)
JP: 本当ですか
VN (WRONG): Thật không? (missing formality)
```

✅ **CORRECT:**
```
Context: KOUHAI speaking to SENPAI (formal)
JP: 本当ですか
VN (CORRECT): Thật không ạ? (formal respect marker)
```

**Why wrong:** RTAS (relationship status) requires formality marker.

**Fix:** Check RTAS range. If formal context (0.0-3.0), add 'ạ' to questions.

---

## Integration Guide

### Step 1: Setup

```python
import json

# Load particle mapping database
with open('jp_vn_particle_mapping_enhanced.json', 'r', encoding='utf-8') as f:
    particle_db = json.load(f)

# Load Vietnamese grammar RAG
with open('vietnamese_grammar_rag.json', 'r', encoding='utf-8') as f:
    vn_grammar_rag = json.load(f)

# Load character manifest
with open('manifest.json', 'r', encoding='utf-8') as f:
    manifest = json.load(f)
```

---

### Step 2: Detect Japanese Particles

```python
import re

def detect_particles(japanese_text):
    """
    Detect Japanese particles in text.
    Returns list of particles with positions.
    """
    particles = []

    # Sentence-ending particles
    sentence_endings = [
        r'よ(?![ぁ-ん])',  # よ (not part of another word)
        r'ね(?![ぁ-ん])',  # ね
        r'な(?![ぁ-ん])',  # な
        r'わ(?![ぁ-ん])',  # わ
        r'ぞ(?![ぁ-ん])',  # ぞ
        r'ぜ(?![ぁ-ん])',  # ぜ
        r'の(?![ぁ-ん])',  # の (sentence-final)
        r'か(?![ぁ-ん])',  # か
        r'かな',           # かな
        r'だよね',         # だよね
        r'でしょ',         # でしょ
        r'だろ',           # だろ
        r'ですわ',         # ですわ (OJOU marker!)
        r'ますわ',         # ますわ (OJOU marker!)
        r'じゃん',         # じゃん (GYARU marker!)
        r'っしょ',         # っしょ (GYARU marker!)
    ]

    for pattern in sentence_endings:
        for match in re.finditer(pattern, japanese_text):
            particles.append({
                'particle': match.group(),
                'position': match.start(),
                'type': 'sentence_ending'
            })

    return particles
```

---

### Step 3: Detect Character Archetype

```python
def detect_archetype(character_data, dialogue_text):
    """
    Detect character archetype from manifest or speech patterns.
    """
    # Check explicit archetype field
    if 'archetype' in character_data:
        return character_data['archetype']

    # Auto-detect from personality_traits
    traits = character_data.get('personality_traits', [])

    archetype_map = {
        'OJOU': ['refined', 'aristocratic', 'formal', 'elegant'],
        'GYARU': ['cheerful', 'trendy', 'casual', 'modern'],
        'DELINQUENT': ['rough', 'aggressive', 'rebellious', 'combat_skilled'],
        'KUUDERE': ['stoic', 'emotionless', 'detached', 'cold'],
        'TSUNDERE': ['tsundere', 'emotionally_guarded', 'prideful'],
        'DEREDERE': ['cheerful', 'affectionate', 'warm', 'loving'],
        'IMOUTO': ['younger_sister', 'childish', 'cute', 'dependent'],
        'GENKI': ['energetic', 'optimistic', 'cheerful', 'outgoing']
    }

    for archetype, keywords in archetype_map.items():
        matches = sum(1 for trait in traits if trait in keywords)
        if matches >= 2:
            return archetype

    # Detect from speech patterns
    if 'ですわ' in dialogue_text or 'ますわ' in dialogue_text:
        return 'OJOU'
    elif 'じゃん' in dialogue_text or 'っしょ' in dialogue_text:
        return 'GYARU'

    # Default fallback
    return 'narrator_default'
```

---

### Step 4: Select Vietnamese Particle

```python
def select_vietnamese_particle(japanese_particle, character_archetype, rtas_value, gender):
    """
    Select appropriate Vietnamese particle based on context.
    """
    # Get particle data from database
    particle_data = None

    # Search in all categories
    for category in ['sentence_ending_particles', 'softening_diminutive_particles',
                     'archetype_signature_particles', 'confirmation_emphasis_particles']:
        if japanese_particle in particle_db.get(category, {}):
            particle_data = particle_db[category][japanese_particle]
            break

    if not particle_data:
        return None  # No mapping found

    # Check forbidden archetypes (HARD BLOCK)
    if character_archetype in particle_data.get('archetype_forbidden', []):
        return particle_data['vietnamese_mappings']['default'][0]

    # Check archetype-specific mappings
    archetype_mappings = particle_data['vietnamese_mappings'].get('archetype_specific', {})
    if character_archetype in archetype_mappings:
        return archetype_mappings[character_archetype][0]  # Return first option

    # Check RTAS range compatibility
    rtas_range = particle_data.get('rtas_range', [0.0, 5.0])
    if not (rtas_range[0] <= rtas_value <= rtas_range[1]):
        # RTAS out of range - use default
        return particle_data['vietnamese_mappings']['default'][0]

    # Check gender compatibility
    particle_gender = particle_data.get('gender', 'neutral')
    if particle_gender == 'male' and gender == 'female':
        return None  # Gender violation - skip particle
    elif particle_gender == 'female' and gender == 'male':
        return None  # Gender violation - skip particle

    # Return default mapping
    return particle_data['vietnamese_mappings']['default'][0]
```

---

### Step 5: Full Translation Pipeline

```python
def translate_with_particles(japanese_text, character_name, manifest):
    """
    Full translation pipeline with particle mapping.
    """
    # 1. Get character data
    character = next((c for c in manifest['characters'] if c['name'] == character_name), None)
    if not character:
        character = {'archetype': 'narrator_default', 'gender': 'neutral'}

    # 2. Detect archetype
    archetype = detect_archetype(character, japanese_text)

    # 3. Get RTAS value (from relationship context)
    rtas = character.get('rtas', 3.5)  # Default casual

    # 4. Get gender
    gender = character.get('gender', 'neutral')

    # 5. Detect particles
    particles = detect_particles(japanese_text)

    # 6. Translate base text (your existing translation engine)
    vietnamese_base = your_translation_engine(japanese_text)

    # 7. Apply particle mappings
    for particle_info in particles:
        jp_particle = particle_info['particle']
        vn_particle = select_vietnamese_particle(jp_particle, archetype, rtas, gender)

        if vn_particle:
            # Replace or append Vietnamese particle
            vietnamese_base = apply_particle(vietnamese_base, vn_particle, particle_info)

    return vietnamese_base
```

---

### Step 6: Validation

```python
def validate_particle_usage(vietnamese_text, character_archetype):
    """
    Validate that particle usage matches archetype.
    """
    violations = []

    # KUUDERE should have minimal particles
    if character_archetype == 'KUUDERE':
        particle_count = sum(vietnamese_text.count(p) for p in ['nha', 'nè', 'nhỉ', 'à', 'hả'])
        if particle_count > 2:
            violations.append({
                'type': 'excessive_particles_kuudere',
                'count': particle_count,
                'fix': 'Remove particles - KUUDERE uses minimal expression'
            })

    # OJOU should never use slang
    if character_archetype == 'OJOU':
        slang_particles = ['luôn', 'hử', 'nè', 'này']
        for slang in slang_particles:
            if slang in vietnamese_text:
                violations.append({
                    'type': 'ojou_slang_violation',
                    'particle': slang,
                    'fix': f"Replace '{slang}' with 'ạ' or elegant alternative"
                })

    # GYARU should use casual/slang particles
    if character_archetype == 'GYARU':
        if 'ạ' in vietnamese_text and 'thưa' not in character_archetype:
            violations.append({
                'type': 'gyaru_formality_violation',
                'particle': 'ạ',
                'fix': "Replace 'ạ' with 'nha/nè/luôn' for GYARU"
            })

    return violations
```

---

## Production Checklist

Before deploying translations, verify:

- [ ] **Particle frequency matches corpus** (~80% of dialogue lines have particles)
- [ ] **Archetype detection working** (ですわ → OJOU, じゃん → GYARU)
- [ ] **Gender rules enforced** (no masculine particles for female characters)
- [ ] **RTAS ranges respected** (formal contexts use formal particles)
- [ ] **Forbidden lists checked** (no OJOU using 'luôn', no KUUDERE over-expressing)
- [ ] **KUUDERE minimalism** (fewer particles, shorter sentences)
- [ ] **GYARU intensity** (slang particles, multiple particles OK)
- [ ] **Question types differentiated** (か vs の vs かな mapped correctly)
- [ ] **よ ≠ ね distinction** (emphatic vs agreement-seeking)
- [ ] **Compound particles handled** (だよね, でしょ, かな as units)

---

## Advanced: Archetype Blending

For characters with multiple personality traits:

```python
def blend_archetype_particles(primary_archetype, secondary_archetype, context):
    """
    Handle characters with blended archetypes.
    Example: TSUNDERE + OJOU = formal but emotionally guarded
    """
    # TSUNDERE OJOU (70% tsun / 30% ojou)
    if primary_archetype == 'TSUNDERE' and secondary_archetype == 'OJOU':
        if context == 'tsun_mode':
            return 'TSUNDERE'  # Use tsundere particles
        elif context == 'formal_setting':
            return 'OJOU'  # Use elegant particles
        else:
            return 'TSUNDERE'  # Default to primary

    # GYARU + GENKI (80% gyaru / 20% genki)
    if primary_archetype == 'GYARU' and secondary_archetype == 'GENKI':
        # Both love energetic particles - intensify
        return 'GYARU'  # Use GYARU particles with high frequency

    # Default: use primary archetype
    return primary_archetype
```

---

## Examples: Before & After

### Example 1: Generic → Archetype-Aware

**Before (Generic):**
```
JP: それは違いますわね
VN: Điều đó sai nhỉ
```

**After (OJOU-aware):**
```
JP: それは違いますわね (detected: ですわ → OJOU)
Archetype: OJOU
VN: Điều đó sai ạ
```

---

### Example 2: Particle Confusion Fixed

**Before (よ/ね confusion):**
```
JP: 本当だよ!
VN (WRONG): Thật đấy nhé!
```

**After (Corrected):**
```
JP: 本当だよ!
VN (CORRECT): Thật đấy!
Reason: よ = emphasis (đấy), not agreement (nhé is ね)
```

---

### Example 3: Gender Violation Fixed

**Before (Gender error):**
```
Character: Female DEREDERE
JP: いい景色だな
VN (WRONG): Phong cảnh đẹp nhể
```

**After (Corrected):**
```
Character: Female DEREDERE
JP: いい景色ね (な → ね correction - females don't use な)
VN (CORRECT): Phong cảnh đẹp nhỉ~
Reason: な is masculine; female characters use ね
```

---

### Example 4: KUUDERE Minimalism

**Before (Over-expressed):**
```
Character: KUUDERE
JP: そうだね
VN (WRONG): Đúng vậy nhỉ
```

**After (KUUDERE-appropriate):**
```
Character: KUUDERE
JP: そうだね → (minimized)
VN (CORRECT): Ừ. / Đúng.
Reason: KUUDERE omits softening particles
```

---

## Summary

**Critical Takeaways:**

1. **よ ≠ ね** - Different functions, different Vietnamese particles
2. **Gender matters** - Never violate gender-coded particles (な, わ, の, ぞ, ぜ)
3. **Archetype detection** - ですわ → OJOU, じゃん → GYARU, minimal → KUUDERE
4. **RTAS awareness** - Formal contexts need 'ạ', casual contexts use 'nha/nè'
5. **Forbidden lists** - Hard blockers prevent character-breaking translations
6. **KUUDERE exception** - When in doubt, omit particles for stoic characters
7. **Corpus frequency** - Top 10 particles account for 50k+ instances - prioritize these
8. **Question differentiation** - か (direct) vs の (feminine) vs かな (wondering)
9. **Compound handling** - Treat だよね, でしょ, かな as semantic units
10. **Validation required** - Check particle usage matches archetype expectations

**Implementation Priority:**

1. よ, ね, か (50k+ combined frequency) - CRITICAL
2. Archetype detection (ですわ, じゃん, minimal speech) - HIGH
3. Gender filters (な, わ, の, ぞ, ぜ) - HIGH
4. RTAS validation - MEDIUM
5. Softeners (ちょっと, なんか) - MEDIUM
6. Dialectal particles (やん, で) - LOW

---

## Related Resources

- **Database:** `jp_vn_particle_mapping_enhanced.json`
- **Grammar RAG:** `vietnamese_grammar_rag.json`
- **Archetype Guide:** `ARCHETYPE_QUICK_REFERENCE.md`
- **Rhythm System:** `ARCHETYPE_RHYTHM_IMPLEMENTATION.md`
- **Advanced Patterns:** `vietnamese_advanced_grammar_patterns.json`

---

**Questions? Issues?**

If particle translations sound unnatural, check:
1. Archetype detection (is it correct?)
2. RTAS range (is formality appropriate?)
3. Gender (does it match character?)
4. Forbidden list (is particle blocked for archetype?)
5. Frequency (are you over-using particles?)

Default fallback: Use 'default' mapping from database, then manually adjust.

---

**Version History:**
- v1.0 (2026-02-04): Initial production release with 58 particles, 12 archetypes, corpus validation
