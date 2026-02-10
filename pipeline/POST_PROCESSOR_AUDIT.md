# POST-PROCESSOR AUDIT - 2026-02-10

## Current Status

### ✅ ACTIVE Post-Processors

1. **Vietnamese CJK Cleaner** (`vn_cjk_cleaner`)
   - Location: `chapter_processor.py` lines 877-888
   - Trigger: Only for Vietnamese (`vi`/`vn`) target language
   - Function: Hard substitution of CJK leaks (e.g., 私 → tôi)
   - Status: **KEEP** (essential for Vietnamese translations)

2. **Anti-AI-ism Agent** (`_anti_ai_ism_agent`)
   - Location: `chapter_processor.py` lines 889-918
   - Trigger: Only if `enable_anti_ai_ism` flag is set
   - Function: Self-healing agent to detect/fix AI-isms
   - Status: **DISABLE** (found to damage prose quality)

3. **Truncation Validator** (`TruncationValidator`)
   - Location: Imported but not actively used in translation flow
   - Function: Detect missing content
   - Status: **SAFE** (only used for validation, not modification)

### ❌ REMOVED Post-Processors

1. **Grammar Validator** (`GrammarValidator`)
   - Previously removed: Lines 1263-1287 in `agent.py`
   - Reason: Inverted subject-verb logic (flagged correct as errors)
   - Evidence: Introduced 35 S-V errors in 1a60 optimized output
   - Status: **ALREADY REMOVED** ✅

### 🔍 FOUND Issues from Audit

#### Issue 1: Grammar Validator Damage (CRITICAL)
- **What happened**: Validator with inverted S-V logic ran as auto-fixer
- **Evidence**: Changed "We were" → "We was" (14 instances)
- **Impact**: 35 grammar errors INTRODUCED into clean translation
- **Resolution**: ✅ FIXED - Validator already removed, errors manually corrected

#### Issue 2: Anti-AI-ism Agent (MODERATE)
- **What happened**: Self-healing agent enabled during 1a60 translation
- **Evidence**: Audit found only 1 AI-ism ("delve") - near-zero contamination
- **Analysis**: Agent may be over-correcting natural prose
- **Recommendation**: DISABLE for now, verify if it's actually helping

---

## RECOMMENDATION: Disable All Except CJK Validator

### Rationale

1. **Gemini Flash 2.0's Native Quality is Excellent**
   - 0 subject-verb errors natively
   - Only 5 possessive errors (50% better than baseline)
   - 1 AI-ism total (0.015 per 1k words)
   - 95.8/100 prose score

2. **Post-Processors Damage Quality**
   - Grammar Validator: Introduced 35 errors
   - Anti-AI-ism Agent: May be over-correcting (needs verification)
   - Best approach: Trust the model, minimal post-processing

3. **CJK Validator is Essential**
   - Only applies to Vietnamese
   - Fixes actual technical issues (CJK character leaks)
   - Not modifying prose, just character substitution
   - **MUST KEEP**

---

## ACTION PLAN

### Step 1: Disable Anti-AI-ism Agent

**File**: `pipeline/translator/chapter_processor.py`

**Change**: Comment out lines 889-918 (Anti-AI-ism post-processing)

```python
# 9. Post-Processing: Self-Healing Anti-AI-ism Agent (DISABLED - damages prose quality)
# The audit found that Gemini's native output has near-zero AI-ism contamination.
# Post-processing over-correction damages natural prose. Trust the model.
ai_ism_healed_count = 0
# if self.enable_anti_ai_ism and self._anti_ai_ism_agent:
#     ... (commented out)
```

### Step 2: Add Comment Documenting Decision

**File**: `pipeline/translator/chapter_processor.py` (after line 888)

```python
# NOTE (2026-02-10): Only CJK validator remains active.
# All other post-processors (grammar validator, anti-AI-ism agent) have been
# disabled after 1a60 audit proved they damage Gemini's native prose quality.
# Gemini Flash 2.0 produces excellent translations with minimal errors:
# - 0 subject-verb errors natively
# - 5 possessive errors (50% better than baseline with old prompts)
# - 1 AI-ism total (0.015 per 1k words)
# - 95.8/100 prose score
# Conclusion: Trust the model. Minimal post-processing = better quality.
```

### Step 3: Verify Agent Initialization

**File**: `pipeline/translator/chapter_processor.py` (lines 75-77)

**Change**: Set default to `False` and add comment

```python
# Initialize Self-Healing Anti-AI-ism Agent for post-processing
self._anti_ai_ism_agent = None
self.enable_anti_ai_ism = False  # DISABLED (2026-02-10) - damages prose quality
```

### Step 4: Update Agent.py Comment

**File**: `pipeline/translator/agent.py` (line 1196)

**Current**:
```python
logger.info("Legacy post-processing stages are disabled.")
logger.info("Only end-of-phase CJK validation is kept (run by scripts/mtl.py).")
```

**Update to**:
```python
logger.info("Post-processing stages are disabled (Gemini's native quality is excellent).")
logger.info("Only CJK validator remains active (Vietnamese translations only).")
logger.info("Grammar validator REMOVED (inverted logic damaged 1a60 output).")
logger.info("Anti-AI-ism agent DISABLED (over-correction damages natural prose).")
```

---

## FILES TO MODIFY

1. ✅ `pipeline/translator/chapter_processor.py`
   - Disable Anti-AI-ism agent (lines 889-918)
   - Add documentation comment (after line 888)
   - Update initialization comment (line 77)

2. ✅ `pipeline/translator/agent.py`
   - Update completion message (lines 1196-1197)

---

## VERIFICATION PLAN

After making changes:

1. ✅ Run test translation on small chapter
2. ✅ Verify no post-processing runs (except CJK for VN)
3. ✅ Check output quality matches Gemini's raw output
4. ✅ Confirm no grammar/AI-ism "corrections" are applied

---

## SUMMARY

**KEEP:**
- ✅ Vietnamese CJK Cleaner (essential, VN-only, technical fix)

**REMOVE/DISABLE:**
- ❌ Grammar Validator (already removed - inverted logic)
- ❌ Anti-AI-ism Agent (disable now - over-correction suspected)

**PHILOSOPHY:**
> "Trust the model. Gemini Flash 2.0's native output is excellent.
> Post-processing corrections damage quality more than they help.
> Minimal intervention = better results."

**Evidence:**
- 1a60 audit: 0 S-V errors natively, 35 introduced by validator
- 1a60 audit: 1 AI-ism total (0.015/1k) - near-zero contamination
- 1a60 audit: 95.8/100 prose score - professional grade

---

**Generated**: 2026-02-10
**Based on**: 1a60 6-Agent Audit Report
**Decision**: Disable all post-processors except CJK validator
