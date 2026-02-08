# Massive LN Pipeline Patch — Implementation Plan

> **Goal**: Fix critical loopholes when handling massive light novels (15+ chapters, 40-50k chars/chapter)  
> **Date**: 2026-02-08  
> **Target**: Novel 25d9 "Lord Marksman and Vanadis" (2 volumes per EPUB, 850KB JP text)

---

## Problem Analysis

### Issues from 25d9 Audit Reports

| Issue | Count | Root Cause |
|-------|-------|------------|
| **Truncated sentences** | 248 (14 mid-word) | LLM output buffer exhaustion; no sentence-boundary validation |
| **Name drift** | 5 variants for "Rurick" | No glossary lock; chapters translated independently |
| **No validation** | — | Post-processing only cleans CJK/AI-isms, not completion |

### Token Budget (Validated)

| Component | Size | Tokens |
|-----------|------|--------|
| System Prompt + RAG | 500 KB | ~125K |
| Entire 25d9 JP | 850 KB | ~212K |
| **TOTAL** | 1.35 MB | ~337K |

**Gemini 2.5 Pro limit**: 1M tokens → **32% usage** ✅

---

## Components

### 1. GlossaryLock (Manifest-Based)

> Lock romanizations from `manifest.json` at run start.

#### [NEW] `pipeline/translator/glossary_lock.py`

```python
class GlossaryLock:
    """
    Manifest-based glossary enforcer.
    
    Flow:
    1. On translator init: load character_names from manifest.json
    2. Lock immediately — these are the ONLY valid romanizations
    3. Validate every chapter output against locked glossary
    4. Flag variants as CRITICAL errors
    """
    
    def __init__(self, work_dir: Path):
        self.manifest_path = work_dir / "manifest.json"
        self.locked_names = self._load_from_manifest()
        
    def _load_from_manifest(self) -> Dict[str, str]:
        manifest = json.load(open(self.manifest_path))
        return manifest.get('metadata_en', {}).get('character_names', {}) \
            or manifest.get('character_names', {})
    
    def validate_output(self, text: str) -> ValidationReport
    def get_locked_names(self) -> Dict[str, str]
    def is_locked(self) -> bool  # Always True after init
```

**Source of truth**: `manifest.json` (no separate lock file needed)

---

### 2. TruncationValidator

> Detect sentences ending mid-word or without terminal punctuation.

#### [NEW] `pipeline/post_processor/truncation_validator.py`

```python
class TruncationValidator:
    TERMINAL_PUNCTUATION = {'.', '!', '?', '"', "'", '—', '…', '"', '"'}
    DANGLING_CONJUNCTIONS = {'and', 'but', 'or', 'that', 'which', 'as', 'when'}
    
    def validate_chapter(self, chapter_path: Path) -> TruncationReport
    def validate_line(self, line: str, line_num: int) -> Optional[TruncationIssue]

@dataclass
class TruncationIssue:
    line_number: int
    truncated_text: str
    severity: str  # CRITICAL, HIGH, MEDIUM
    broken_word: Optional[str]
```

#### [MODIFY] `pipeline/translator/chapter_processor.py`

```python
# After saving translation output:
validator = TruncationValidator()
report = validator.validate_chapter(output_path)

if report.has_critical():
    logger.error(f"[TRUNCATION] {len(report.critical)} CRITICAL in {chapter_id}")
```

---

### 3. Volume-Level Caching Strategy

> Cache **entire LN** at translation start, then translate each chapter with full-volume context.

**Verified against**: [Google Gemini Caching Docs](https://ai.google.dev/gemini-api/docs/caching?lang=python) ✅

```
┌──────────────────────────────────────────────┐
│ PHASE 1: FULL VOLUME CACHE                   │
│  • Load ALL chapters (15 files = 850KB)      │
│  • Create single Gemini cache                │
│  • Cache ID shared across all translations   │
└──────────────────────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────┐
│ PHASE 2: SEQUENTIAL TRANSLATION              │
│  • For each chapter:                         │
│    - If <50k chars: direct translation       │
│    - If >50k chars: chunk translation flow   │
└──────────────────────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────┐
│ PHASE 3: CHUNK TRANSLATION (if needed)       │
│  • Split at ◆ scene breaks                   │
│  • Each chunk → temp/CHAPTER_XX_chunk_N.json │
│  • Resumable: skip already-translated chunks │
└──────────────────────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────┐
│ PHASE 4: MERGE & DEDUPLICATE                 │
│  • Load all chunk JSONs in order             │
│  • Remove duplicate scene breaks (◆◆ → ◆)    │
│  • Remove overlapping sentences at boundaries│
│  • Validate no truncations                   │
│  • Output: EN/CHAPTER_XX.md                  │
└──────────────────────────────────────────────┘
```

#### Temp Chunk JSON Format

```json
{
  "chapter_id": "chapter_07",
  "chunk_index": 1,
  "total_chunks": 3,
  "source_line_range": [1, 450],
  "scene_break_before": false,
  "scene_break_after": true,
  "content": "Translated text for this chunk...",
  "last_sentence": "The sun set behind the mountains.",
  "tokens_in": 12500,
  "tokens_out": 8200,
  "timestamp": "2026-02-08T21:42:00Z"
}
```

**Storage**: `temp/chunks/CHAPTER_07_chunk_001.json`, `..._chunk_002.json`, etc.

**Token Budget** (validated with 25d9):
- System + RAG: 125K tokens
- Entire volume: 212K tokens  
- **Total**: 337K / 1M = **32%** ✅

#### [MODIFY] `pipeline/translator/agent.py`

```python
class TranslatorAgent:
    def __init__(self, work_dir: Path, ...):
        ...
        self.volume_cache = None  # Created before translation starts
    
    def _create_volume_cache(self) -> str:
        """Cache entire volume for translation run.
        
        Uses Google's `contents` field per official docs:
        https://ai.google.dev/gemini-api/docs/caching?lang=python
        """
        all_chapters = self._load_all_jp_chapters()  # JP/*.md
        full_volume_text = "\n\n---\n\n".join([
            f"<CHAPTER id='{ch.id}'>\n{ch.content}\n</CHAPTER>"
            for ch in all_chapters
        ])
        
        # Per Google docs: use `contents` for cacheable content
        cache = self.client.caches.create(
            model=self.model,
            config=types.CreateCachedContentConfig(
                display_name=f"{self.volume_id}_full",
                system_instruction=self.system_prompt,
                contents=[full_volume_text],  # ← Full LN here
                ttl="7200s"  # 2 hours for long volumes
            )
        )
        logger.info(f"[CACHE] Created volume cache: {cache.name} ({len(all_chapters)} chapters)")
        return cache.name
    
    def translate_volume(self):
        # Create single cache for entire volume
        self.volume_cache = self._create_volume_cache()
        
        for chapter in self.chapters:
            self._translate_chapter_with_cache(chapter, self.volume_cache)
```

#### [MODIFY] `pipeline/translator/chapter_processor.py`

```python
def translate_chapter(self, ..., volume_cache: str = None):
    """Translate using volume-level cache."""
    
    prompt = f"""
Translate CHAPTER {chapter_id} from the cached volume context.
The full volume is in your cache - use it for name/term consistency.

<TRANSLATE_THIS>
{source_text}
</TRANSLATE_THIS>
"""
    
    response = self.client.generate(
        prompt=prompt,
        cached_content=volume_cache,  # Full volume context
        temperature=0.7
    )
```

---

### Google API Alignment Verification

| API Feature | Google Docs | Our Implementation | Status |
|-------------|------------|-------------------|--------|
| Cache creation | `client.caches.create()` | `gemini_client.py:109` | ✅ |
| Config class | `CreateCachedContentConfig` | `gemini_client.py:111` | ✅ |
| TTL format | `"300s"` string | `f"{ttl_seconds}s"` | ✅ |
| Using cache | `cached_content=cache.name` | `gemini_client.py:299` | ✅ |
| **Contents field** | `contents=[...]` | **NEW** (volume caching) | ✅ |
| Cache delete | `client.caches.delete()` | `gemini_client.py:153` | ✅ |

---

### 4. Name Consistency Auditor

> Cross-chapter fuzzy-match to detect variant drift.

#### [NEW] `pipeline/auditors/name_consistency_auditor.py`

```python
class NameConsistencyAuditor:
    """
    Detects name variant drift across translated chapters.
    
    Algorithm:
    1. Extract capitalized words from EN chapters
    2. Fuzzy-match (Levenshtein ≤ 2)
    3. Group variants: {Rurick, Rulic, Rulick}
    4. Flag if any character has 2+ variants
    """
    
    def audit_volume(self, en_dir: Path) -> NameConsistencyReport
    def find_variants(self, chapters: List[Path]) -> Dict[str, Set[str]]
```

---

### 5. Chunk Merger

> Merge temp chunk JSONs into final chapter, with deduplication and validation.

#### [NEW] `pipeline/translator/chunk_merger.py`

```python
class ChunkMerger:
    """
    Merges translated chunk JSONs into final chapter markdown.
    
    Responsibilities:
    1. Load all chunk JSONs for a chapter in order
    2. Deduplicate scene breaks (◆◆◆ → ◆)
    3. Detect and remove overlapping sentences at boundaries
    4. Validate no truncations in merged output
    5. Save final EN/CHAPTER_XX.md
    6. Archive or delete temp files
    """
    
    def __init__(self, work_dir: Path):
        self.temp_dir = work_dir / "temp" / "chunks"
        self.en_dir = work_dir / "EN"
    
    def merge_chapter(self, chapter_id: str) -> MergeResult:
        """Merge all chunks for a chapter."""
        chunk_files = sorted(self.temp_dir.glob(f"{chapter_id}_chunk_*.json"))
        
        if not chunk_files:
            raise ValueError(f"No chunks found for {chapter_id}")
        
        # Load and validate chunks
        chunks = [self._load_chunk(f) for f in chunk_files]
        self._validate_chunk_sequence(chunks)
        
        # Merge content
        merged = self._merge_chunks(chunks)
        
        # Deduplicate scene breaks
        merged = self._dedupe_scene_breaks(merged)
        
        # Remove boundary overlaps
        merged = self._remove_boundary_overlaps(chunks, merged)
        
        # Validate no truncations
        validator = TruncationValidator()
        report = validator.validate_text(merged)
        
        if report.has_critical():
            logger.warning(f"[MERGE] {len(report.critical)} truncations in merged {chapter_id}")
        
        # Save final output
        output_path = self.en_dir / f"{chapter_id.upper()}.md"
        output_path.write_text(merged, encoding='utf-8')
        
        return MergeResult(
            chapter_id=chapter_id,
            chunks_merged=len(chunks),
            output_path=output_path,
            truncation_issues=report.all_issues
        )
    
    def _dedupe_scene_breaks(self, text: str) -> str:
        """Reduce multiple consecutive scene breaks to single."""
        import re
        # ◆\n\n◆ or ◆\n◆ → single ◆
        return re.sub(r'(◆\s*\n)+', '◆\n\n', text)
    
    def _remove_boundary_overlaps(self, chunks: List[dict], merged: str) -> str:
        """Detect and remove sentences that appear at end of chunk N and start of chunk N+1."""
        for i in range(len(chunks) - 1):
            last_sentence = chunks[i].get('last_sentence', '')
            if last_sentence and last_sentence in merged:
                # Check if duplicated at boundary
                # (More sophisticated logic needed for production)
                pass
        return merged

@dataclass
class MergeResult:
    chapter_id: str
    chunks_merged: int
    output_path: Path
    truncation_issues: List[TruncationIssue]
```

---

## Files to Create/Modify

| Action | File |
|--------|------|
| **NEW** | `pipeline/translator/glossary_lock.py` |
| **NEW** | `pipeline/post_processor/truncation_validator.py` |
| **NEW** | `pipeline/auditors/name_consistency_auditor.py` |
| **NEW** | `pipeline/translator/chunk_merger.py` |
| **MODIFY** | `pipeline/translator/agent.py` |
| **MODIFY** | `pipeline/translator/chapter_processor.py` |
| **MODIFY** | `pipeline/common/gemini_client.py` |

---

## Verification Plan

### Test 1: Truncation Detection

```bash
python -c "
from pipeline.post_processor.truncation_validator import TruncationValidator
from pathlib import Path

validator = TruncationValidator()
report = validator.validate_chapter(
    Path('WORK/魔弾の王と戦姫 第1章―出逢い―_20260208_25d9/EN/CHAPTER_06_EN.md')
)
assert any('Tig' in i.truncated_text for i in report.critical)
print('✓ Truncation detection PASSED')
"
```

### Test 2: Glossary Lock

```bash
python -c "
from pipeline.translator.glossary_lock import GlossaryLock
from pathlib import Path

lock = GlossaryLock(Path('WORK/魔弾の王と戦姫 第1章―出逢い―_20260208_25d9'))
assert lock.is_locked()
assert 'Rurick' in lock.get_locked_names().values()
print('✓ Glossary lock PASSED')
"
```

### Test 3: Re-translate with Patches

```bash
python -m pipeline.translator.agent \
    --work-dir WORK/魔弾の王と戦姫\ 第1章―出逢い―_20260208_25d9 \
    --chapters chapter_06

# Expected: 0 truncations, consistent names
```

---

## Implementation Order

1. `truncation_validator.py` (standalone, low risk)
2. `glossary_lock.py` (new component)
3. `chunk_merger.py` (new component)
4. `agent.py` — volume cache creation
5. `chapter_processor.py` — chunk translation + temp JSON
6. `name_consistency_auditor.py` (standalone)
7. End-to-end testing on 25d9

**Estimated effort**: ~12 hours
