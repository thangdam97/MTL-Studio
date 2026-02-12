# Stage 3 Hybrid Validation Workflow

**Architecture:** v1.7 Multi-Stage
**Validation Model:** Gemini 2.5 Flash + Human Review Flagging
**Status:** Detection framework ✅ | Auto-fix framework ⏳

---

## Overview

Stage 3 Refinement uses a **hybrid validation approach**:

1. **Pattern-based detection** (confidence 0.7-1.0)
2. **Gemini 2.5 Flash validation** for ambiguous cases (confidence 0.5-0.8)
3. **Human review flagging** for low-confidence or critical issues (confidence <0.5)
4. **Auto-fix deployment** for high-confidence patterns (confidence ≥0.9)

**Goal:** Achieve 95%+ compliance on all metrics with minimal human intervention

---

## Validation Workflow

### Phase 1: Pattern-Based Detection
```
Input: EN chapter markdown file
↓
Process: Regex pattern matching + rule-based validation
↓
Output: List of RefinementIssues with confidence scores
```

**Detection Categories:**

1. **Hard Cap Violations** (confidence: 1.0)
   - Dialogue >10 words
   - Narration >15 words
   - **Action:** Flag for intelligent splitting

2. **AI-ism Patterns** (confidence: 0.7-0.95)
   - 15 patterns from anti_ai_ism_patterns.json
   - "couldn't help but", "a sense of", "heavy with", etc.
   - **Action:** Auto-fix (≥0.9) or human review (<0.9)

3. **Tense Consistency** (confidence: 0.75)
   - Present tense in past-tense narrative
   - Excludes dialogue, universal truths, conditionals
   - **Action:** Flag for context-aware validation

---

### Phase 2: Gemini 2.5 Flash Validation (Optional)
```
Input: RefinementIssue with confidence 0.5-0.8
↓
Process: Gemini 2.5 Flash contextual analysis
↓
Output: "GENUINE_ISSUE" | "ACCEPTABLE" | "SUGGEST_FIX: [fix]"
```

**Prompt Template:**
```
You are a literary editor reviewing English light novel prose.

Issue Type: [issue_type]
Severity: [severity]
Detected Text: "[matched_text]"
Context: ...[context]...
Issue Description: [issue_description]

Question: Is this a genuine issue that requires correction,
or is it acceptable in context?

Respond with ONE of:
1. "GENUINE_ISSUE: [brief reason]"
2. "ACCEPTABLE: [brief reason]"
3. "SUGGEST_FIX: [proposed fix]"

Keep response under 50 words.
```

**Use Cases:**
- Ambiguous AI-ism detection (e.g., "locked in my room" - literal vs metaphorical)
- Tense consistency edge cases (e.g., historical present for dramatic effect)
- Rhythm violations near thresholds (e.g., 10-word dialogue, 15-word narration)

**Performance:**
- Model: gemini-2.0-flash-exp (fastest, cheapest)
- Latency: ~500ms per validation
- Cost: ~$0.0001 per validation
- Batch processing: 100 validations in ~10 seconds

---

### Phase 3: Auto-Fix Deployment
```
Input: RefinementIssue with confidence ≥0.9
↓
Process: Pattern-based string replacement
↓
Output: Modified EN file + audit trail
```

**Auto-Fix Eligibility Criteria:**
1. **Confidence ≥0.9** (high-confidence pattern match)
2. **Deterministic replacement** (one-to-one mapping)
3. **Context-independent** (works regardless of surrounding text)
4. **Whitelisted pattern** (approved by human validation)

**Current Auto-Fix Patterns:**

| Pattern | Replacement | Confidence | Status |
|---------|-------------|------------|--------|
| "couldn't help but [verb]" | "[verb]" | 0.95 | ✅ Deployed |
| "a sense of [emotion]" | "felt [emotion]" | 0.85 | ⏳ Pending |
| "[temporal] he is today" | "[temporal] he was then" | 0.90 | ⏳ Pending |

**Audit Trail:**
Every auto-fix logs:
- Original text
- Fixed text
- Pattern matched
- Confidence score
- File location

**Rollback:** Full backup created before deployment

---

### Phase 4: Human Review Flagging
```
Input: RefinementIssue requiring human review
↓
Process: Categorize by severity + type
↓
Output: Prioritized review queue
```

**Review Queue Prioritization:**

**Priority 1 (CRITICAL):** 1,091 issues
- Hard cap violations (dialogue >10w, narration >15w)
- Requires intelligent sentence splitting
- **Estimated time:** 4-6 hours (build auto-splitter)

**Priority 2 (HIGH):** 211 issues
- Narration 16-17 words (close to hard cap)
- Borderline cases requiring judgment
- **Estimated time:** 2-3 hours (manual review)

**Priority 3 (MEDIUM):** 434 issues
- Tense consistency violations
- Can be partially auto-fixed (confidence 0.75-0.9)
- **Estimated time:** 2-3 hours (enhanced validation)

**Priority 4 (LOW):** 0 issues (current)
- Future: Minor style inconsistencies
- Non-blocking quality improvements

---

## Intelligent Sentence Splitter (Stage 3 Enhancement)

**Goal:** Automatically split long sentences while preserving meaning

### Algorithm Design

```python
def split_long_sentence(sentence: str, max_words: int) -> List[str]:
    """
    Intelligently split sentence at natural break points.

    Priority order:
    1. Coordinating conjunctions (but, and, yet, so)
    2. Subordinating conjunctions (while, when, because, although)
    3. Relative clauses (who, which, that)
    4. Participial phrases (verb+ing)
    5. Prepositional phrases (last resort)
    """

    # Count words
    word_count = count_words(sentence)

    if word_count <= max_words:
        return [sentence]

    # Use Gemini 2.5 Flash for intelligent splitting
    prompt = f"""Split this sentence at natural break points to create 2-3 shorter sentences.

    Original: {sentence}
    Max words per sentence: {max_words}

    Rules:
    1. Preserve all information
    2. Maintain natural flow and rhythm
    3. Split at conjunctions or clause boundaries
    4. Keep related ideas together

    Output format (JSON):
    {{
      "sentences": ["sentence 1", "sentence 2", ...]
    }}
    """

    response = gemini_client.generate_text(prompt)
    result = json.loads(response)

    return result['sentences']
```

### Example Transformations

**Dialogue Splitting (>10w):**
```
Before (16w): "Happy birthday to you, happy birthday to you, happy birthday dear Akihito-kun, happy birthday to you!"

After (7w + 9w):
"Happy birthday to you, happy birthday to you!"
"Happy birthday dear Akihito-kun, happy birthday to you!"
```

**Narration Splitting (>15w):**
```
Before (22w): "In Japan, you'd usually blow out the candles right away after everyone finishes singing, but I waited a moment before leaning forward to blow them out."

After (13w + 9w):
"In Japan, you'd usually blow out the candles right after the song."
"But I waited a moment before leaning forward to blow them out."
```

**Preserve Rhythm:**
```
Before (18w): "The morning sunlight streamed through the window, casting long shadows across the classroom floor as students slowly trickled in."

After (9w + 9w):
"The morning sunlight streamed through the window, casting long shadows."
"Students slowly trickled into the classroom as the day began."
```

---

## Quality Metrics Tracking

### Current Baseline (17fb Post-Phase 2.5)

| Metric | Score | Target | Gap |
|--------|-------|--------|-----|
| **Dialogue Hard Cap** | 31.8% | 95% | -63.2% |
| **Narration Hard Cap** | 42.1% | 95% | -52.9% |
| **AI-ism Density** | 0.7/ch | <1/ch | ✅ PASS |
| **Tense Consistency** | 79.3% | 95% | -15.7% |

### Expected After Stage 3 Auto-Splitter

| Metric | Projected Score | Improvement |
|--------|----------------|-------------|
| **Dialogue Hard Cap** | 95%+ | +63.2% |
| **Narration Hard Cap** | 95%+ | +52.9% |
| **AI-ism Density** | 0.3/ch | -57% |
| **Tense Consistency** | 95%+ | +15.7% |
| **Overall Grade** | S- (96/100) | +2 points |

---

## Implementation Roadmap

### ✅ Phase 1: Detection Framework (COMPLETE)
**Deliverables:**
- `stage3_refinement_validator.py` - comprehensive validation
- Pattern-based detection for hard caps, AI-isms, tense
- Confidence scoring system
- JSON + Markdown reporting

**Validation:** 17fb volume (7 chapters, 1,736 issues detected)

---

### ⏳ Phase 2: Intelligent Sentence Splitter (IN PROGRESS)
**Estimated Time:** 4-6 hours

**Tasks:**
1. Build Gemini 2.5 Flash integration for sentence splitting
2. Implement break point detection algorithm
3. Add validation to ensure no information loss
4. Test on 50 sample long sentences (dialogue + narration)
5. Deploy on full volume and measure compliance improvement

**Success Criteria:**
- Dialogue hard cap: 31.8% → 95%+
- Narration hard cap: 42.1% → 95%+
- No semantic distortion (human review of 10% sample)

---

### ⏳ Phase 3: Tense Auto-Fix Enhancement (PENDING)
**Estimated Time:** 2-3 hours

**Tasks:**
1. Expand auto-fix patterns for high-confidence tense violations
2. Add temporal anchor detection ("he is today" → "he was then")
3. Add state verb conversion ("she is beautiful" → "she was beautiful")
4. Implement exception whitelist (dialogue, universal truths)
5. Deploy and validate on 17fb

**Success Criteria:**
- Tense consistency: 79.3% → 95%+
- Auto-fix confidence: ≥0.85
- False positive rate: <5%

---

### ⏳ Phase 4: Production Automation (PENDING)
**Estimated Time:** 2-3 hours

**Tasks:**
1. Integrate Stage 3 into main translation pipeline
2. Add auto-fix toggle to CLI (default: off, requires explicit enable)
3. Create rollback mechanism (automatic backup before fixes)
4. Add progress tracking and reporting
5. Documentation for human review workflow

**Success Criteria:**
- One-command deployment: `python mtl.py translate --enable-stage3-autofix`
- Full audit trail for all modifications
- Zero data loss risk (rollback available)

---

## Best Practices

### Do's ✅
1. **Always create backup** before auto-fix deployment
2. **Run dry-run first** to preview changes
3. **Review audit trail** after auto-fix deployment
4. **Use high confidence thresholds** (≥0.9 for auto-fix)
5. **Validate on sample** before full-volume deployment
6. **Log all transformations** for reproducibility

### Don'ts ❌
1. **Don't auto-fix low-confidence patterns** (<0.9)
2. **Don't skip human review** for critical issues
3. **Don't modify source files** without backup
4. **Don't trust AI-generated fixes** without validation
5. **Don't batch too many patterns** (deploy incrementally)
6. **Don't ignore false positives** (improve detection rules)

---

## Performance Benchmarks

### Detection Performance (17fb - 7 chapters)
- **Execution time:** 8.2 seconds
- **Issues detected:** 1,736
- **Detection rate:** 211 issues/second
- **Memory usage:** ~50 MB
- **CPU usage:** Single-core, ~60%

### Gemini 2.5 Flash Validation (Estimated)
- **Latency:** ~500ms per validation
- **Cost:** ~$0.0001 per validation
- **Batch processing:** 100 validations in ~10 seconds
- **Total cost (1,736 validations):** ~$0.17

### Auto-Fix Deployment (Phase 2.5 - 5 fixes)
- **Execution time:** 2.1 seconds
- **Files modified:** 2 chapters
- **Fixes applied:** 5
- **Backup creation:** 0.8 seconds
- **Total time:** 2.9 seconds

---

## Monitoring and Metrics

### Quality Assurance Checklist

**Before Deployment:**
- [ ] Backup created and verified
- [ ] Dry-run executed and reviewed
- [ ] Sample validation (10% of issues)
- [ ] False positive rate check (<5% threshold)
- [ ] Confidence distribution analysis

**After Deployment:**
- [ ] Audit trail generated
- [ ] Metrics comparison (before/after)
- [ ] Regression check (no new issues introduced)
- [ ] Human review of auto-fixes (10% sample)
- [ ] Production readiness assessment

### Success Metrics

**Quantitative:**
- Hard cap compliance: 95%+ (dialogue + narration)
- AI-ism density: <0.5 per chapter
- Tense consistency: 95%+
- CJK leaks: 0 (maintain perfect record)
- Overall grade: S- (96/100) or higher

**Qualitative:**
- Natural reading flow (no robotic sentence splitting)
- Preserved authorial voice and rhythm
- Zero semantic distortion
- Professional-grade polish
- Human reviewer satisfaction: >90%

---

## Future Enhancements

### Phase 5: ML-Based Validation (Long-term)
- Train custom model on human-reviewed corrections
- Predict optimal sentence split points
- Context-aware tense correction
- Personalized style matching (author voice preservation)

### Phase 6: Real-time Validation (Integration)
- Stage 2 translation + Stage 3 validation in single pass
- Live feedback loop to model
- Adaptive prompt injection based on validation results
- Target: 95%+ compliance on first pass (no post-processing needed)

---

**Last Updated:** 2026-02-13
**Framework Version:** Stage 3 v1.0
**Next Milestone:** Intelligent sentence splitter deployment
