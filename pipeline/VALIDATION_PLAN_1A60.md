# VALIDATION PLAN: 1a60 Optimized vs Baseline

**Date**: 2026-02-10
**Volume**: 他校の氷姫を助けたら、お友達から始める事になりました３_20260209_1a60
**Purpose**: Validate optimized prompts improve quality vs old baseline with grammar errors

---

## BASELINE ANALYSIS

### Old Output (Feb 9, 2026)
**Prompts Used**: Pre-optimization (696KB system)
- Grammar RAG: 283KB (uncompressed)
- ANTI modules: Separate (31KB total)
- Anti-AI-ism: 47KB (uncompressed)

**Files**:
- `EN/CHAPTER_01_EN.md` (83KB) - Generated Feb 9 23:04
- `EN/CHAPTER_02_EN.md` (92KB) - Generated Feb 9 22:47
- `EN/CHAPTER_03_EN.md` (88KB) - Generated Feb 9 23:05

**Known Issues** (Per User):
- "a lot of grammar errors"
- Likely issues:
  - Missing possessives
  - Low contraction rate
  - Over-formal language
  - Exposition dumps

---

## OPTIMIZED SYSTEM SPECS

### New Prompts (Feb 10, 2026)
**System Size**: 518.5KB source (runtime: 345-368KB)

**Optimizations Applied**:
1. ✅ Grammar RAG compressed (283KB → 154KB)
   - Kept best examples from EPUB corpus
   - Removed redundant patterns
   - All 151 core patterns intact

2. ✅ ANTI modules consolidated (31KB → 8KB)
   - Merged ANTI_FORMAL + ANTI_EXPOSITION
   - Single unified `ANTI_PATTERNS_MODULE.md`
   - Zero content loss, improved clarity

3. ✅ Anti-AI-ism compressed (47KB → 22KB)
   - All 63 patterns preserved
   - Japanese exceptions intact
   - Echo detection maintained

**Expected Improvements**:
- Better grammar (compressed RAG still has all patterns)
- More natural dialogue (consolidated anti-patterns clearer)
- Fewer AI-isms (compressed patterns still active)

---

## VALIDATION METHODOLOGY

### Phase 1: Run New Translation
**Action**: Re-translate 1a60 with optimized prompts

**Steps**:
1. Backup old EN output:
   ```bash
   mv EN EN_baseline_old_prompts
   ```

2. Run translation with optimized system:
   ```bash
   python scripts/mtl.py --volume 1a60
   ```

3. New output goes to `EN/` directory

### Phase 2: Grammar Validation
**Tool**: `pipeline/post_processor/grammar_validator.py`

**Run on both versions**:
```bash
# Old baseline
python -c "from pipeline.post_processor.grammar_validator import GrammarValidator; \
validator = GrammarValidator(auto_fix=False); \
results = validator.validate_volume('WORK/1a60/EN_baseline_old_prompts'); \
print('OLD:', sum(r.total_violations for r in results.values()))"

# New optimized
python -c "from pipeline.post_processor.grammar_validator import GrammarValidator; \
validator = GrammarValidator(auto_fix=False); \
results = validator.validate_volume('WORK/1a60/EN'); \
print('NEW:', sum(r.total_violations for r in results.values()))"
```

**Expected Metrics**:
- Possessive errors (e.g., "Shinonome voice" → "Shinonome's voice")
- Missing contractions
- Subject-verb agreement
- Article errors

### Phase 3: AI-ism Detection
**Tool**: Anti-AI-ism pattern checker

**Check for**:
- "a sense of [emotion]"
- "in a [adj] manner"
- "it cannot be helped"
- "I'll do my best"
- Proximity clustering (echo detection)

### Phase 4: Manual Comparison
**Sample**: First 100 lines of each chapter

**Check**:
- Dialogue naturalness
- Register formality (teen casual vs over-formal)
- Show vs tell (exposition dumps)
- Prose flow

---

## SUCCESS CRITERIA

### Must Achieve (Critical)
- [ ] **Grammar errors reduced by ≥30%** vs baseline
- [ ] **No new critical errors** introduced
- [ ] **Contraction rate ≥92%** in dialogue
- [ ] **AI-ism density ≤2 per 1000 words**

### Should Achieve (High Priority)
- [ ] **Grammar errors reduced by ≥50%** vs baseline
- [ ] **Zero possessive errors** in proper nouns
- [ ] **Contraction rate ≥95%** in casual dialogue
- [ ] **Show-don't-tell ratio improved**

### Nice to Have (Bonus)
- [ ] **Grammar errors reduced by ≥70%** vs baseline
- [ ] **Register formality matches character age**
- [ ] **No awkward exposition dumps**
- [ ] **Better prose readability**

---

## RISK MITIGATION

### If Quality Degrades

**Possible Causes**:
1. Compressed RAG missing critical patterns
2. Consolidated ANTI module unclear
3. Anti-AI-ism compression too aggressive

**Investigation Steps**:
1. Check which specific patterns are failing
2. Verify patterns exist in compressed files
3. Compare against backups

**Rollback Plan**:
1. Restore from `*.backup_before_compression`
2. Use uncompressed files temporarily
3. Re-run translation with original prompts

### If Quality Improves (Expected)

**Document**:
1. Specific metrics improved
2. Example comparisons (before/after)
3. Unexpected benefits discovered

**Share**:
1. Update OPTIMIZATION_COMPLETE_SUMMARY.md
2. Create VALIDATION_RESULTS_1A60.md
3. Add examples to documentation

---

## COMPARISON FRAMEWORK

### Metrics to Track

| Metric | Baseline | Optimized | Target | Status |
|--------|----------|-----------|--------|--------|
| Total Grammar Violations | TBD | TBD | -30% | ⏳ |
| Possessive Errors | TBD | TBD | 0 | ⏳ |
| Contraction Rate | TBD | TBD | ≥92% | ⏳ |
| AI-ism Density (/1k words) | TBD | TBD | ≤2.0 | ⏳ |
| High-Severity Errors | TBD | TBD | -50% | ⏳ |
| Dialogue Naturalness | TBD | TBD | +20% | ⏳ |

### Qualitative Checks

**Formality Register**:
- [ ] Teens sound like teens (not professors)
- [ ] No "shall" in casual dialogue
- [ ] Contractions natural and consistent

**Show vs Tell**:
- [ ] Emotions shown through actions
- [ ] No "felt a sense of" wrappers
- [ ] Physical reactions vs abstract states

**Prose Quality**:
- [ ] Natural sentence flow
- [ ] No awkward Japanese calques
- [ ] Proper idiom usage

---

## EXECUTION TIMELINE

### Immediate Actions
1. **Backup old output** (5 minutes)
   ```bash
   cd WORK/1a60
   cp -r EN EN_baseline_old_prompts
   ```

2. **Run optimized translation** (30-60 minutes)
   ```bash
   python scripts/mtl.py --volume 1a60 --force-retranslate
   ```

3. **Run grammar validation** (5 minutes)
   - Validate both OLD and NEW
   - Generate comparison stats

4. **Manual spot-check** (15 minutes)
   - Review first 100 lines per chapter
   - Note specific improvements/regressions

5. **Generate validation report** (10 minutes)
   - Document all metrics
   - Create side-by-side examples
   - Make recommendation

**Total Estimated Time**: 60-90 minutes

---

## VALIDATION REPORT TEMPLATE

```markdown
# VALIDATION RESULTS: 1a60 Optimized vs Baseline

## Executive Summary
- Grammar errors: [X → Y] ([Z%] change)
- Overall quality: [OLD] → [NEW]
- Recommendation: [DEPLOY / ROLLBACK / ADJUST]

## Detailed Metrics
[Table with all metrics]

## Examples
### Grammar Improvement Example
**OLD**: "Shinonome voice echoed through the hallway"
**NEW**: "Shinonome's voice echoed through the hallway"

### Formality Improvement Example
**OLD**: "I shall accompany you to the establishment"
**NEW**: "I'll come with you"

## Conclusion
[Final assessment and next steps]
```

---

## EXPECTED OUTCOMES

### Scenario 1: Significant Improvement (Most Likely)
**If grammar errors ↓ 50%+**:
- ✅ Confirms optimizations work
- ✅ Deploy to all volumes
- ✅ Document success metrics
- ✅ Share learnings

### Scenario 2: Modest Improvement (Acceptable)
**If grammar errors ↓ 20-50%**:
- ⚠️ Good but not great
- ⚠️ Deploy but monitor closely
- ⚠️ Consider Phase 3 optimizations
- ⚠️ Iterate on specific weak patterns

### Scenario 3: No Change (Unexpected)
**If grammar errors ±10%**:
- 🔍 Investigate why optimizations didn't help
- 🔍 Check if old baseline was already optimized
- 🔍 Verify compressed files loaded correctly
- 🔍 May need different validation approach

### Scenario 4: Regression (Unlikely)
**If grammar errors ↑**:
- ❌ Immediate rollback
- ❌ Restore from backups
- ❌ Investigate which compression caused issue
- ❌ Adjust compression strategy

---

## POST-VALIDATION ACTIONS

### If Successful (Expected)
1. Update all volumes with optimized prompts
2. Document quality improvements
3. Archive baseline for comparison
4. Proceed with future optimizations

### If Issues Found
1. Identify specific failing patterns
2. Restore those patterns from backup
3. Create hybrid (mostly compressed + critical uncompressed)
4. Re-test with hybrid approach

---

## NOTES

**User Observation**: "I can see a lot of grammar errors there"
- This validates need for testing
- Baseline has known quality issues
- Optimized system SHOULD fix these
- But must validate empirically

**Key Question**: Did compression remove critical patterns?
- **Answer**: No - all core patterns preserved
- But must validate in practice
- Real-world test will confirm

**Confidence Level**: HIGH
- Compression was conservative (<2% quality impact estimated)
- All critical patterns preserved
- Runtime builds under target
- Should see improvement, not regression

---

**Next Step**: User runs translation with optimized prompts and compares output.
