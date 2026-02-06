# Vietnamese Advanced Grammar Patterns - Integration Guide

**Created:** 2026-02-04
**Status:** Ready for Integration
**Target File:** `vietnamese_grammar_rag.json`

## Overview

This document describes the advanced grammar pattern sections created to bring Vietnamese grammar RAG to parity with the English pipeline's depth and sophistication.

## New Pattern Categories

### 1. **comedic_timing_advanced** (6 patterns, 4,390 corpus freq)
Vietnamese adaptations of English pipeline's comedic beat patterns:

- **vn-short-comedic-blunt** (freq: 850) - Split contrast into punchy 5-8 word beats
  - Pattern: "Ghét sách à? Không. Ghét suy nghĩ."
  - Usage: Question setup → Negation → Punchline (max 5-8 words)

- **vn-deadpan-timing-pause** (freq: 620) - Matter-of-fact absurdity with fragments
  - Pattern: "Vào phòng người ta. Trải nệm. Bình thường?"
  - Usage: 2-3 word fragments separated by periods

- **vn-callback-humor-structure** (freq: 340) - Reference earlier absurdity
  - Pattern: "Vụ nãy. Còn chưa xong à?"
  - Usage: 'vụ/chuyện' + time marker + brief surprise

- **vn-absurdist-escalation** (freq: 480) - Escalate with 'Còn nữa'
  - Pattern: "Xin lỗi à? Chưa. Còn cười nữa."
  - Usage: Expected action → Negate → Worse action

- **vn-one-word-devastation** (freq: 920) - Single syllable response
  - Pattern: "[Long confession]\n\n\"Ừ.\""
  - Usage: Ừ/Ồ/Thế/À/Hử with period, separate line

- **vn-self-aware-meta-commentary** (freq: 580) - Acknowledge absurdity
  - Pattern: "Nghe điên nhỉ."
  - Usage: Casual vocab + wondering particle (nhỉ/nhể/ta)

**Archetype Affinity:** tsundere_guarded, kuudere_stoic, narrator_default, genki_optimist

---

### 2. **high_frequency_transcreations_vn** (9 patterns, 15,890 corpus freq)
Vietnamese equivalents for ultra-common Japanese expressions:

| Japanese | Frequency | Vietnamese Pattern | Context |
|----------|-----------|-------------------|---------|
| やっぱり | 2,100 | đúng thật / thôi / quả nhiên | Confirmation vs reversion vs opinion |
| まあ | 3,400 | thôi / kệ đi / này này / tàm tàm | Hedging/acceptance/mediocre |
| さすが | 1,850 | đúng là [name] / quá đấy / đẳng cấp | Praise vs limit reached |
| なんだか | 1,200 | sao...thế / hình như / drop entirely | Vague feeling |
| 別に | 1,680 | có...đâu / kệ / tùy | Dismissal/tsundere |
| まさか | 840 | không lẽ / không đời nào | Disbelief/shock |
| 確かに | 920 | đúng đấy / phải nói là | Concession |
| もしかして | 760 | chẳng lẽ / hay là | Tentative guess |
| どうして | 1,540 | sao / sao lại / tại sao | Emotional why |

**Critical Priority Markers:**
- やっぱり, まあ, さすが, なんだか, 別に, まさか = **CRITICAL** (most common)
- 確かに, もしかして, どうして = **HIGH**

**Key Rule:** AVOID literal translations: "như mong đợi", "không hiểu sao", "một cách nào đó" are AI-isms

---

### 3. **modal_nuances_advanced** (4 patterns, 9,600 corpus freq)

#### a) Should/Obligation Scale (freq: 2,200)
```
nên đi (gentle suggestion)
  ↓
nên là (stronger advice)
  ↓
phải (obligation)
  ↓
bắt buộc phải (strong obligation)
  ↓
buộc phải (absolute)
```

#### b) Can: Ability vs Permission (freq: 3,100)
- **Ability/Skill:** biết bơi, bơi được
- **General capability:** có thể làm
- **Permission request:** được...không? / cho...không?
- **Permission grant:** được / cứ [verb]
- **Possibility:** có thể / có lẽ

#### c) May/Possibility Gradations (freq: 1,900)
```
có lẽ (30-50% certainty)
  ↓
có thể (50-70%)
  ↓
chắc (70-80%)
  ↓
chắc là (80-90%)
  ↓
hẳn là (90%+)
```

#### d) Want/Desire (freq: 2,400)
- Direct: muốn + verb/noun
- Wistful: muốn...nhỉ
- Third-person: Anh ấy muốn... / Trông có vẻ muốn...

---

### 4. **time_expressions_natural_advanced** (4 patterns, 8,300 corpus freq)

#### a) Just Now - Immediacy Levels (freq: 1,800)
```
vừa mới / mới (0-2 min - immediate)
  ↓
vừa nãy / lúc nãy (2-10 min - very recent)
  ↓
hồi nãy (10-30 min - recent)
  ↓
lúc sáng/chiều nay (30+ min - earlier today)
```

#### b) For a While - Duration (freq: 2,100)
```
tí / tý / xíu (< 1 min - ultra casual)
  ↓
chút / một chút (1-3 min)
  ↓
một lúc / lát (3-10 min)
  ↓
một hồi / chốc lát (10-30 min)
  ↓
một hồi lâu / lâu (30+ min)
```

#### c) Immediacy/Urgency (freq: 1,600)
```
ngay / liền (normal urgency)
  ↓
ngay đi / liền đi (urgent)
  ↓
ngay lập tức / lập tức (very urgent)
  ↓
tức thì / tức khắc (extreme - formal)
```

#### d) Already/Completion (freq: 2,800)
- đã...rồi / rồi (completed)
- từ lâu rồi / từ hồi nào (long past)
- Can drop 'đã' in casual: "Xong rồi" vs "Đã xong rồi"

---

### 5. **sentence_endings_advanced** (5 patterns, 11,500 corpus freq)

#### a) Confirmation Seeking (freq: 2,400)
- **Casual:** nhỉ / nhể / hả
- **Neutral:** đúng không / không
- **Formal:** phải không / có phải không

#### b) Wondering/Speculation (freq: 1,900)
- nhỉ (casual, common)
- nhể (softer, feminine lean)
- hở (surprised discovery)
- ta (literary, formal)

#### c) Emphasis/Assertion (freq: 3,200)
- đấy (general emphasis)
- đó (strong emphasis, demonstrative)
- mà (contradiction, insistence)
- kìa (pointing out obvious)
- nào (rallying, suggestion)

#### d) Gentle Suggestion (freq: 2,600)
- nhé (gentle, friendly - like ね)
- nhỉ (wondering, musing)
- nào (encouraging)

#### e) Tag Questions (freq: 1,400)
- mà (assertion of fact)
- kìa (pointing out obvious)
- đó (demonstrative - "see?")

---

### 6. **action_emphasis_advanced** (4 patterns, 7,800 corpus freq)

#### a) Completive Aspect (freq: 2,200)
- **Regret:** ...mất rồi / đã...mất
- **Neutral:** đã...rồi / ...rồi
- **Recent:** vừa...rồi / vừa mới...
- **Experience:** đã từng... / từng...

#### b) Progressive Aspect (freq: 2,900)
- **True progressive:** đang... / đang...đây
- **Continuing:** vẫn...đó / vẫn còn...
- **State:** drop đang, use simple form
- **Habitual:** hay... / thường...

#### c) Regrettable Action (freq: 1,100)
- **Repetition:** lại / lại...nữa
- **Irreversible:** ...mất rồi / đã...mất
- **Compounding:** lại còn / còn...thêm
- **Unfortunate:** lỡ / lỡ...rồi

#### d) Attempt/Effort (freq: 1,600)
- thử...xem (try and see - exploratory)
- ...thử (try doing - experimental)
- Both orders natural: "thử ăn" = "ăn thử"

---

## Integration Strategy

### Phase 1: System Prompt Injection (Tier 1)
Inject into master Vietnamese prompt alongside anti-AI-ism patterns:

```
CRITICAL PATTERNS - ALWAYS APPLY:
1. High-frequency transcreations (やっぱり→đúng thật/thôi, まあ→thôi/kệ, etc.)
2. Comedic timing for romcom (split sentences, deadpan particles)
3. Modal nuances (nên vs phải, có thể vs được)
4. Natural time expressions (vừa nãy vs hồi nãy)
5. Sentence-ending particles (nhỉ, đấy, mà, nhé)
6. Action emphasis (đã...rồi, đang...đây, lại...mất)
```

### Phase 2: Agent Reference During Translation
Agent queries patterns contextually:
- Character says やっぱり → check context → apply appropriate transcreation
- Comedy scene → boost comedic_timing patterns
- Modal verb → check gradation scale → apply correct Vietnamese form

### Phase 3: Critic Validation
Post-translation review checks:
- High-frequency expressions translated contextually (not literally)
- Comedic beats preserved (split sentences, proper particles)
- Modal strength matches Japanese nuance
- Time expressions feel natural (not "một khoảng thời gian")

### Phase 4: Post-Processor Pattern Fixes
Automated fixes for common misses:
- Detect "như mong đợi" → replace with contextual やっぱり equivalent
- Detect "một cách [adj]" → replace with adverb/vivid verb
- Detect textbook modals → upgrade to natural forms

---

## Archetype Priority Boosting

### Romcom/Comedy Genres
**Priority Boost:**
- comedic_timing_advanced (all patterns)
- high_frequency_transcreations_vn (betsu_ni, yappari, sasuga)
- sentence_endings_advanced (emphasis particles)

**Affected Archetypes:** tsundere_guarded, genki_optimist, kuudere_stoic

### Drama/Serious Genres
**Priority Boost:**
- modal_nuances_advanced (full gradation)
- time_expressions_natural_advanced (precise distinctions)
- action_emphasis_advanced (regrettable, completive)

**Affected Archetypes:** scholar_intellectual, warrior_soldier, noble_formal, brooding_loner

---

## Corpus Frequency Summary

| Category | Total Patterns | Total Corpus Frequency | Avg per Pattern |
|----------|----------------|------------------------|----------------|
| comedic_timing_advanced | 6 | 4,390 | 732 |
| high_frequency_transcreations_vn | 9 | 15,890 | 1,766 |
| modal_nuances_advanced | 4 | 9,600 | 2,400 |
| time_expressions_natural_advanced | 4 | 8,300 | 2,075 |
| sentence_endings_advanced | 5 | 11,500 | 2,300 |
| action_emphasis_advanced | 4 | 7,800 | 1,950 |
| **TOTAL** | **32** | **57,480** | **1,796** |

**Note:** Frequencies estimated from Japanese corpus analysis - Vietnamese corpus validation needed for calibration.

---

## Vector Search Integration

### Recommended for Embedding
1. **high_frequency_transcreations_vn** - semantic matching for やっぱり/まあ/さすが in context
2. **comedic_timing_advanced** - retrieve similar comedic patterns for genre consistency

### Embedding Strategy
- Embed all examples with Japanese source + Vietnamese natural translation
- During translation: embed Japanese sentence → retrieve top-3 similar patterns
- Apply pattern's Vietnamese strategy to current sentence

---

## Quality Gates

### Pre-Translation Checklist
- [ ] Identify high-frequency Japanese markers (やっぱり, まあ, etc.)
- [ ] Detect comedy genre → activate comedic_timing patterns
- [ ] Note modal verbs → reference gradation scales
- [ ] Mark time expressions → apply natural Vietnamese forms

### Post-Translation Validation
- [ ] No AI-isms: "như mong đợi", "một cách [adj]", "một cảm giác"
- [ ] High-frequency expressions contextually translated
- [ ] Comedic beats preserved (if comedy genre)
- [ ] Modal strength matches Japanese (nên vs phải)
- [ ] Time expressions natural (vừa nãy not "vừa rồi một chút")
- [ ] Sentence endings appropriate (nhỉ/đấy/mà present where needed)
- [ ] Action aspects correct (đã...rồi vs ...mất rồi)

---

## File Structure

```
vietnamese_advanced_grammar_patterns.json
├── version: "2.1"
├── metadata
│   ├── new_pattern_categories: 6
│   ├── total_new_patterns: 89 sub-patterns
│   └── estimated_tokens: 8,500
├── comedic_timing_advanced
│   └── patterns[6]
├── high_frequency_transcreations_vn
│   └── patterns[9]
├── modal_nuances_advanced
│   └── patterns[4]
├── time_expressions_natural_advanced
│   └── patterns[4]
├── sentence_endings_advanced
│   └── patterns[5]
├── action_emphasis_advanced
│   └── patterns[4]
└── integration_instructions
    ├── merge_strategy
    ├── phase_integration
    ├── llm_instruction_template
    └── vector_search_candidates
```

---

## Next Steps

### Immediate (Phase 1)
1. **Merge into vietnamese_grammar_rag.json**
   - Append after `rhythm_rules` section
   - Preserve JSON structure
   - Update metadata totals

2. **Update master_prompt_vn_pipeline.xml**
   - Add high-frequency transcreation reminders
   - Include comedic timing instructions for romcom
   - Reference modal/time expression guidelines

3. **Update Tier 1 injection list**
   - Add comedic_timing_advanced
   - Add high_frequency_transcreations_vn (critical patterns)

### Short-term (Phase 2-3)
4. **Agent Integration**
   - Modify `translator/agent.py` to query new patterns
   - Add context-aware pattern selection
   - Genre-based priority boosting

5. **Critic Enhancement**
   - Add validation rules for high-frequency expressions
   - Check comedic beat preservation
   - Modal/time expression accuracy verification

### Long-term (Phase 4+)
6. **Vector Search Implementation**
   - Embed high_frequency_transcreations examples
   - Semantic retrieval for やっぱり/まあ/さすが
   - Pattern suggestion during translation

7. **Corpus Validation**
   - Analyze Vietnamese translations for actual frequencies
   - Calibrate corpus_frequency estimates
   - Identify missing common patterns

8. **Feedback Loop**
   - Track pattern application rates
   - Log missed opportunities
   - Iterate on pattern definitions

---

## Example Application

### Before (Literal Translation)
```
JP: やっぱり彼女は可愛いな。まあ、別にそう思わないけど。
VN: Như mong đợi, cô ấy dễ thương. Chà, tôi không nghĩ vậy.
```

### After (Pattern Applied)
```
JP: やっぱり彼女は可愛いな。まあ、別にそう思わないけど。
VN: Đúng thật cô ấy đẹp nhỉ. Thôi, có nghĩ vậy đâu.

Patterns applied:
- やっぱり → đúng thật (confirmed expectation)
- 可愛い → đẹp (natural Vietnamese)
- な → nhỉ (wondering particle)
- まあ → thôi (hedging acceptance)
- 別に → có...đâu (tsundere dismissal)
```

### Comedy Example
```
JP: こいつ、本が苦手というより頭を使うことが嫌いなんだよな
Literal: Cô ấy không phải ghét sách mà là ghét dùng đầu.
Pattern: Ghét sách à? Không. Ghét suy nghĩ.

Pattern: vn-short-comedic-blunt
- Setup: Ghét sách à? (5 words)
- Negate: Không. (1 word)
- Punchline: Ghét suy nghĩ. (3 words)
```

---

## Maintenance Notes

- **Update Frequency:** Review quarterly based on translation audit findings
- **Pattern Addition:** New patterns require 3+ corpus examples and usage rules
- **Deprecation Policy:** Patterns with <50 corpus frequency reviewed for removal
- **Version Control:** Increment minor version (2.X) for pattern additions, major (X.0) for structural changes

---

**Document Version:** 1.0
**Last Updated:** 2026-02-04
**Maintainer:** MTL Studio Pipeline Team
