# FANTASY TRANSLATION MODULE (FFXVI Method)

**Version:** 1.0
**Date:** 2026-01-13
**Purpose:** Fantasy-specific translation framework for light novels with Western medieval/fantasy settings
**Based On:** Final Fantasy XVI English localization principles (Michael-Christopher Koji Fox method)
**Genre:** Fantasy romance, isekai, noble academy, sword & sorcery

---

## Table of Contents

1. [Core Philosophy](#core-philosophy)
2. [Fantasy Register System](#fantasy-register-system)
3. [Character Archetypes (Fantasy)](#character-archetypes-fantasy)
4. [Contraction Rules (Fantasy Override)](#contraction-rules-fantasy-override)
5. [Honorifics & Titles](#honorifics-titles)
6. [Japanese Interjection Adaptation](#japanese-interjection-adaptation)
7. [World-Building Terminology](#world-building-terminology)
8. [Anti-Victorian Guardrails](#anti-victorian-guardrails)

---

<a name="core-philosophy"></a>
## 1. Core Philosophy: Modern Fantasy Register

**Definition:** Modern fantasy register is **refined but accessible** - it sounds timeless without being archaic, elegant without being stuffy.

**The FFXVI Principle:**
> "Characters should sound like people from a fantasy world, not actors performing Shakespeare."

### Three Pillars

#### Pillar 1: ELEGANCE THROUGH WORD CHOICE, NOT GRAMMAR RIGIDITY

| ❌ Victorian Rigidity | ✅ FFXVI-Style Elegance | 🎯 Why It Works |
|----------------------|------------------------|------------------|
| "I do not believe that to be wise." | "I don't think that's wise." | Contraction doesn't reduce elegance |
| "Can you not see that I am occupied?" | "Can't you see I'm busy?" | Natural inversion, modern flow |
| "I shall take my leave, if you will excuse me." | "I'll take my leave." | Shorter = more confident |
| "I am entirely serious about this matter." | "I'm serious." | Directness = emotional weight |

**Rule:** Use **sophisticated vocabulary**, not **archaic grammar**, to convey nobility.

---

#### Pillar 2: PERSONALITY OVER PROTOCOL

**Japanese source:** ですます調 (desu-masu formal ending)
**Bad translation:** Translate formality → Victorian grammar
**FFXVI approach:** Translate formality → CHARACTER PERSONALITY

**Example:**

| Character Type | Japanese | ❌ Victorian | ✅ FFXVI Style |
|---------------|----------|--------------|----------------|
| Loyal Servant | 「お嬢様、準備が整いました」 | "My lady, the preparations have been completed." | "My lady, we're ready." |
| Tsundere Princess | 「別に気にしてないわよ」 | "I am not particularly concerned about it." | "I'm not worried about it." |
| Stoic Knight | 「承知しました」 | "I have understood your command." | "Understood." |

**Rule:** Let PERSONALITY drive formality, not rigid grammar rules.

---

#### Pillar 3: EMOTIONAL DIRECTNESS

**Japanese politeness:** 包み込む (tsutsumi-komu) = wrap feelings in politeness
**Fantasy English:** UNWRAP the feeling, express directly

| ❌ Over-Polite Wrapper | ✅ Direct Fantasy English | 🎯 Emotion |
|-----------------------|---------------------------|------------|
| "I would be grateful if you could answer me without reservation." | "Please, be honest with me." | Vulnerability |
| "I find myself experiencing a certain degree of unease." | "I'm uneasy." | Anxiety |
| "It would bring me great joy to hear of your acceptance." | "I'd be happy if you'd accept." | Hope |

**Rule:** Fantasy characters express emotions **directly**, not through layers of politeness.

---

<a name="fantasy-register-system"></a>
## 2. Fantasy Register System

### RTAS Still Applies, But With Fantasy Adjustments

**Standard RTAS Scale:** 1.0 (strangers) → 5.0 (lovers)

**Fantasy Modification:**
- **Base formality is LOWER** than modern Japanese settings
- **Contractions allowed at ALL levels** (even RTAS 1.0)
- **Title usage** determines formality, not grammar rigidity

---

### Formality Tiers (Fantasy)

#### Tier 1: CEREMONIAL (RTAS 1.0, formal ceremonies only)

**When to use:**
- Royal proclamations
- Knighting ceremonies
- Formal trials/judgments

**Characteristics:**
- Full forms allowed (but not required)
- Elevated vocabulary
- Passive voice acceptable

**Example:**
```
"By the authority vested in me, I hereby grant you the title of knight."
```

---

#### Tier 2: RESPECTFUL (RTAS 1.5-2.5, servant-noble, student-teacher)

**When to use:**
- Servant addressing noble
- Knight addressing commander
- Student addressing instructor

**Characteristics:**
- ✅ Contractions allowed: "don't," "can't," "won't"
- ✅ Title + name: "Lady Tetra," "Commander Clive"
- ✅ Polite vocabulary without stiffness
- ❌ No Victorian inversions: NOT "can you not," NOT "I shall"

**Example - Servant to Noble:**
```
"Lady Tetra, I don't think that's wise."
"My lady, I've finished the preparations."
"I'm honored to serve you."
```

**NOT:**
```
"Lady Tetra, I do not believe that to be wise." ❌
"My lady, the preparations have been completed." ❌
"It is an honor to be in your service." ❌
```

---

#### Tier 3: FAMILIAR (RTAS 3.0-4.0, friends, comrades)

**When to use:**
- Fellow knights
- Academy classmates
- Close servants/nobles with bond

**Characteristics:**
- Full contraction freedom
- Casual vocabulary while maintaining setting
- Direct emotion expression
- Optional title dropping (if close)

**Example:**
```
"You're worrying too much."
"I'm not letting you do this alone."
"Don't be ridiculous."
```

---

#### Tier 4: INTIMATE (RTAS 4.5-5.0, lovers, family)

**When to use:**
- Romantic partners
- Siblings
- Parent-child

**Characteristics:**
- Full casual English (within fantasy vocabulary)
- Emotional vulnerability
- Pet names acceptable
- Shortest sentence forms

**Example - Romantic:**
```
"I love you."
"Don't leave me."
"You're everything to me."
```

**NOT:**
```
"I harbor feelings of deep affection for you." ❌
"I would be greatly saddened by your departure." ❌
"You hold great significance in my life." ❌
```

---

<a name="character-archetypes-fantasy"></a>
## 3. Character Archetypes (Fantasy)

### New Archetypes for Fantasy Settings

These replace/augment modern archetypes when `WORLD_SETTING = FANTASY`:

---

#### ARCHETYPE: LOYAL_SERVANT

**Profile:**
- Devoted attendant to nobility
- Warm formality, not robotic
- Uses contractions naturally
- Shows personality within duty

**Vocabulary:**
- "My lady/lord"
- "Of course"
- "I'll handle it"
- "As you wish"

**Rhythm:** Legato (L) - flowing, composed

**Example Voice:**
```
"Lady Tetra, I've brought your tea."
"I don't mind at all, my lady."
"You're overworking yourself again."
```

**AVOID:**
- "If you will excuse me" ❌
- "I am humbled" ❌
- "That is quite admirable" ❌

---

#### ARCHETYPE: TSUNDERE_PRINCESS

**Profile:**
- Noble with defensive pride
- Sharp tongue with soft heart
- Uses contractions when flustered
- Maintains dignity while showing emotion

**Vocabulary:**
- "Hmph"
- "Honestly"
- "Don't misunderstand"
- "It's not like..."

**Rhythm:** Staccato (S) - clipped, defensive

**Example Voice:**
```
"Can't you see I'm busy?"
"I'm not worried about you!" (lying)
"Don't get the wrong idea."
```

**AVOID:**
- "Can you not see..." ❌
- "I am not particularly concerned..." ❌
- Victorian sentence inversions ❌

---

#### ARCHETYPE: STOIC_KNIGHT

**Profile:**
- Battle-hardened warrior
- Minimal words, maximum impact
- Direct speech, no flowery language
- Protective instinct

**Vocabulary:**
- "Understood"
- "Leave it to me"
- "Stay behind me"
- "I won't let them"

**Rhythm:** Tenuto (T) - weighted, deliberate

**Example Voice:**
```
"I'll protect you."
"Don't worry."
"They won't touch you."
```

**AVOID:**
- "I shall ensure your safety" ❌
- "You need not concern yourself" ❌
- Over-explanation ❌

---

#### ARCHETYPE: FRONTIER_NOBLE

**Profile:**
- Practical noble from border regions
- Direct communication style
- Elegant but not pretentious
- Action-oriented

**Vocabulary:**
- "Indeed"
- "Naturally"
- "Let's move"
- "I'll handle this"

**Rhythm:** Tenuto (T) - firm, confident

**Example Voice:**
```
"We don't have time for ceremony."
"I'll do what's necessary."
"That's unacceptable."
```

---

#### ARCHETYPE: COURT_NOBLE

**Profile:**
- High society, politically savvy
- Formal but not stiff
- Elegant phrasing
- Uses contractions in private

**Vocabulary:**
- "Indeed"
- "Quite"
- "I dare say"
- "Naturally"

**Rhythm:** Legato (L) - flowing, refined

**Example Voice (PUBLIC):**
```
"How delightful to see you."
"That would be most unwise."
"I'm afraid I must decline."
```

**Example Voice (PRIVATE):**
```
"Don't be foolish."
"I'm worried about you."
"You're impossible."
```

---

<a name="contraction-rules-fantasy-override"></a>
## 4. Contraction Rules (Fantasy Override)

### THE GOLDEN RULE: CONTRACTIONS ARE ALWAYS ALLOWED IN FANTASY

**Rationale:** FFXVI proves that nobles, servants, and royalty can use contractions without losing elegance. Formality comes from **vocabulary and tone**, not grammar rigidity.

---

### Contraction Usage by RTAS

| RTAS Level | Contraction Frequency | Example |
|------------|----------------------|---------|
| 1.0-1.5 (Ceremonial) | 50% (formal moments) | "I don't know" OR "I do not know" (both valid) |
| 1.5-2.5 (Respectful) | 80% (default contractions) | "I don't think that's wise" ✅ |
| 2.5-4.0 (Familiar) | 95% (full contractions) | "You're overthinking this" ✅ |
| 4.0-5.0 (Intimate) | 100% (always contract) | "I'm here" ✅ |

---

### Common Contractions (Fantasy-Approved)

| Full Form | Contracted | Fantasy-Appropriate Context |
|-----------|-----------|----------------------------|
| I am | I'm | ALL contexts |
| I will | I'll | ALL contexts |
| I would | I'd | ALL contexts |
| You are | You're | ALL contexts |
| You will | You'll | ALL contexts |
| He/She is | He's/She's | ALL contexts |
| Do not | Don't | ALL contexts |
| Cannot | Can't | ALL contexts |
| Will not | Won't | ALL contexts |
| Should not | Shouldn't | ALL contexts |
| I have | I've | ALL contexts |
| That is | That's | ALL contexts |

---

### Exception: Emphasis

**Rule:** Use full form for EMPHASIS, not formality.

**Example:**
```
"I will NOT allow this." ✅ (emphasis on refusal)
"I won't allow this." ✅ (normal statement)

"I do NOT trust him." ✅ (emphasis on distrust)
"I don't trust him." ✅ (normal statement)
```

---

<a name="honorifics-titles"></a>
## 5. Honorifics & Titles

### Japanese → Fantasy English Title Conversion

| Japanese | Fantasy English | When to Use |
|----------|----------------|-------------|
| お嬢様 (ojou-sama) | Lady [Name] | Noble woman, princess |
| 様 (sama) | Lord/Lady [Name] | High nobility |
| 殿 (dono) | Sir [Name] | Knights, warriors |
| 陛下 (heika) | Your Majesty | Royalty (king/queen) |
| 閣下 (kakka) | Your Grace | Dukes, high nobles |
| 先生 (sensei) | Master/Instructor [Name] | Teachers, mentors |

---

### Title Usage Rules

#### Rule 1: CONSISTENT TITLE FORMAT

**Format:** Title + First Name (Western style)
- ✅ "Lady Tetra"
- ✅ "Lord Clive"
- ✅ "Sir Leon"
- ❌ "Tetra-sama" (breaks immersion in Western fantasy)

---

#### Rule 2: TITLE DROPPING AT HIGH RTAS

**RTAS < 3.0:** Always use title
```
"Lady Tetra, I've finished."
```

**RTAS 3.0-4.0:** Optional title (signals growing closeness)
```
"Tetra, I've finished." (after bond forms)
```

**RTAS > 4.5:** First name only (intimate)
```
"Tetra, I love you."
```

---

#### Rule 3: SERVANTS CAN USE INFORMAL TITLES IN PRIVATE

**PUBLIC:** "Lady Tetra"
**PRIVATE (after bonding):** "My lady" or even "Tetra" (if RTAS > 3.5)

**Example - Leon to Tetra:**
```
PUBLIC (RTAS 2.0):
"Lady Tetra, the preparations are complete."

PRIVATE (RTAS 3.5):
"Tetra, you're overworking yourself."

INTIMATE (RTAS 4.5):
"Tetra... I can't lose you."
```

---

<a name="japanese-interjection-adaptation"></a>
## 6. Japanese Interjection Adaptation

### THE RULE: NO DIRECT JAPANESE IN WESTERN FANTASY

**Problem:** Translating え (e), あ (a), うん (un) directly as "Eh?", "Ah!", "Nn" breaks immersion.

**Solution:** Adapt to English interjections that fit fantasy settings.

---

### Interjection Conversion Table

| Japanese | ❌ Anime Dub | ✅ Fantasy English | Context |
|----------|-------------|-------------------|---------|
| え？ (e?) | "Eh?" | "Hm?" / "What?" / "Pardon?" | Surprise/confusion |
| あ (a) | "Ah" | "Oh" / "Ah" (acceptable) | Realization |
| あら (ara) | "Ara?" | "Oh?" / "My" | Refined surprise (noble women) |
| おい (oi) | "Oi!" | "Hey!" / "You there!" | Calling attention |
| うん (un) | "Nn" | "Mm" / "Mhm" | Agreement |
| ふふ (fufu) | "Fufu" | "Heh" / soft laugh | Amusement |
| ちっ (chi) | "Tch!" | "Tsk!" / "Damn!" | Frustration |
| はぁ (haa) | "Haa" | Sigh / "Ugh" | Exasperation |

---

### Examples in Context

**BAD (Anime dub style):**
```
"Eh? You're serious?"
"Ara, how unexpected."
"Nn, I see."
```

**GOOD (Fantasy adaptation):**
```
"What? You're serious?"
"Oh? How unexpected."
"Mm, I see."
```

---

<a name="world-building-terminology"></a>
## 7. World-Building Terminology

### Handling Fantasy-Specific Terms

#### Rule 1: PRIORITIZE ENGLISH EQUIVALENTS

**Japanese term → English equivalent (if one exists)**

| Japanese Concept | English Equivalent | Example |
|-----------------|-------------------|---------|
| 学園 (gakuen) | Academy | Wisteria Academy ✅ |
| 騎士団 (kishidan) | Knight Order / Knighthood | The Royal Knights ✅ |
| 魔法学院 (mahou gakuin) | School of Magic / Arcane Academy | Academy of Sorcery ✅ |
| 冒険者ギルド | Adventurer's Guild | Guild of Adventurers ✅ |

---

#### Rule 2: KEEP UNIQUE PROPER NOUNS

**When the term is a UNIQUE name (not a generic concept), keep it:**

| Term Type | Example | Handling |
|-----------|---------|----------|
| Character names | テトラ → Tetra | Keep romanized |
| Place names | ウィステリア → Wisteria | Keep romanized |
| Spell names | フレアストーム → Flare Storm | Translate |
| Monster names | ドラゴン → Dragon | Use English if equivalent exists |
| Unique items | エクスカリバー → Excalibur | Use established English name |

---

#### Rule 3: CONSISTENCY IN WORLD-BUILDING

**Once you establish a term, STICK TO IT.**

**Example - Magic Ranks:**
```
見習い魔法使い → Apprentice Mage ✅
Then consistently use: Apprentice → Adept → Master → Archmage
```

**NOT:**
```
Apprentice Mage → Intermediate Sorcerer → Expert Wizard ❌ (inconsistent)
```

---

<a name="anti-victorian-guardrails"></a>
## 8. Anti-Victorian Guardrails

### What Makes Translation "Victorian" (And How to Avoid It)

---

### Victorian Red Flag #1: "I Shall" / "You Shall"

**Victorian:**
```
"I shall return presently."
"You shall have your answer."
```

**Fantasy (FFXVI-style):**
```
"I'll return shortly."
"You'll have your answer."
```

**Rule:** "Shall" is ONLY acceptable in:
- Royal decrees: "You shall be knighted."
- Formal oaths: "I shall serve faithfully."
- Emphasis/threat: "You shall regret this."

---

### Victorian Red Flag #2: "Can You Not" / "Do You Not"

**Victorian:**
```
"Can you not see I am occupied?"
"Do you not understand?"
```

**Fantasy (FFXVI-style):**
```
"Can't you see I'm busy?"
"Don't you understand?"
```

**Rule:** NEVER use negative inversion. Use contractions with normal word order.

---

### Victorian Red Flag #3: "If You Will Excuse Me"

**Victorian:**
```
"If you will excuse me, I shall take my leave."
```

**Fantasy (FFXVI-style):**
```
"Excuse me, I'll take my leave."
```

**Rule:** Simplify politeness phrases. Remove unnecessary conditionals.

---

### Victorian Red Flag #4: "I Am Humbled"

**Victorian:**
```
"I am humbled by your praise."
```

**Fantasy (FFXVI-style):**
```
"I'm honored." / "Thank you."
```

**Rule:** Use direct gratitude, not performative humility.

---

### Victorian Red Flag #5: "That Is Quite [Adjective]"

**Victorian:**
```
"That is quite admirable."
"That is quite impressive."
```

**Fantasy (FFXVI-style):**
```
"That's impressive."
"Well done."
```

**Rule:** "Quite" is British formal, not fantasy formal. Use direct adjectives.

---

### Victorian Red Flag #6: Passive Voice Overuse

**Victorian:**
```
"The preparations have been completed."
"Your request will be attended to."
```

**Fantasy (FFXVI-style):**
```
"We're ready."
"I'll handle your request."
```

**Rule:** Use active voice. Make characters AGENTS, not observers.

---

## Summary: The FFXVI Method

### Three Commandments

1. **CONTRACTIONS ARE ELEGANT**
   - Don't avoid them
   - They make dialogue sound natural
   - Formality comes from vocabulary, not grammar

2. **PERSONALITY OVER PROTOCOL**
   - Character voice > rigid formality rules
   - A tsundere princess can say "Can't you see?"
   - A loyal servant can say "I'm honored"

3. **EMOTIONAL DIRECTNESS**
   - Express feelings directly
   - No safety wrappers ("I find myself experiencing...")
   - Strong verbs, clear emotions

---

### Quick Reference: Victorian vs FFXVI

| Victorian Translation | FFXVI-Style Translation |
|----------------------|------------------------|
| "I do not believe that to be wise." | "I don't think that's wise." |
| "Can you not see I am occupied?" | "Can't you see I'm busy?" |
| "I shall take my leave." | "I'll take my leave." |
| "If you will excuse me." | "Excuse me." |
| "I am humbled." | "I'm honored." / "Thank you." |
| "That is quite admirable." | "That's impressive." |
| "The preparations have been completed." | "We're ready." |
| "I assure you, I am entirely serious." | "I'm serious." / "I mean it." |

---

## Integration with Existing Modules

### Module Priority When `WORLD_SETTING = FANTASY`

1. **THIS MODULE (FANTASY_TRANSLATION_MODULE)** - Overrides base rules
2. **Module 08 (Anti-Translationese)** - Still applies fully
3. **Module 02 (Boldness)** - Still applies, with fantasy vocabulary
4. **Module 05 (Register)** - OVERRIDDEN by fantasy register rules
5. **Module 03 (Rhythm)** - Still applies (Legato/Staccato/Tenuto)

### Key Overrides

**Register Module Override:**
- Contractions allowed at ALL RTAS levels
- Formality through vocabulary, not grammar

**Archetype System Override:**
- Use LOYAL_SERVANT instead of generic formal voice
- Use TSUNDERE_PRINCESS instead of OJOU (for fantasy nobles)

**Honorifics Override:**
- Japanese honorifics → English titles
- "Ojou-sama" → "Lady [Name]"
- "Eh?" → "Hm?" / "What?"

---

## ACTIVATION TRIGGER

This module activates when:
```
WORLD_SETTING = FANTASY
GENRE = WESTERN_FANTASY | ISEKAI | NOBLE_ACADEMY | SWORD_AND_SORCERY
```

When active, it OVERRIDES modern-Japan-specific rules from the base translation engine.
