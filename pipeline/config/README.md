# MTL Studio Configuration Files

**Location**: `/pipeline/config/`  
**Version**: 3.5 LTS  
**Last Updated**: January 30, 2026

This directory contains three major quality control configuration systems for the MTL Studio translation pipeline:

1. **Anti-AI-ism Pattern Library** - 63-pattern detection with severity classification
2. **Echo Detection System** - Proximity-based clustering analysis (23 patterns)
3. **CJK Artifact Validation** - Chinese character leak detection

---

## Table of Contents

- [Anti-AI-ism Pattern Library](#anti-ai-ism-pattern-library)
- [Echo Detection System](#echo-detection-system)
- [CJK Artifact Validation](#cjk-artifact-validation)
- [Configuration Files](#configuration-files)
- [Integration](#integration)
- [Usage Examples](#usage-examples)

---

## Anti-AI-ism Pattern Library

### Overview

**File**: `anti_ai_ism_patterns.json`  
**Version**: 2.0  
**Total Patterns**: 63  
**Purpose**: Industrial-standard AI-generated text detection and cleanup

The pattern library detects AI-generated translationese patterns that degrade prose quality. Organized into three severity tiers with specialized subcategories.

### Architecture

```
anti_ai_ism_patterns.json
├── _meta (metadata and Echo Detection config)
├── CRITICAL (6 patterns)
│   └── Publication blockers
├── MAJOR (28 patterns)
│   ├── emotion_wrappers (3)
│   ├── filter_phrases (7)
│   ├── ai_crutch_phrases (3)
│   ├── process_verbs (4)
│   ├── perception_verbs (3)
│   ├── nominalizations (4)
│   ├── manner_phrases (1)
│   └── hedging (2)
└── MINOR (29 patterns)
    ├── formal_vocabulary (5)
    ├── transitional_overuse (1)
    ├── japanese_sounds (4)
    ├── wordy_connectors (5)
    ├── perception_verbs (3)
    ├── reaction_verbs (3)
    ├── gaze_verbs (3)
    └── hedge_words (5)
```

### Severity Tiers

#### 🔴 CRITICAL (6 patterns)
**Publication blockers** - Direct translations that must be eliminated:

| Pattern | Example | Fix |
|---------|---------|-----|
| `asserting_presence` | "asserting their presence" | "obvious" / "impossible to ignore" |
| `release_pheromones` | "release pheromones" | "ooze allure" / "exude charm" |
| `noun_bridge` | "had a sadness to it" | "sounded sad" |
| `adverb_bridge` | "in a [adj] way" | Use adverb directly |
| `translationese` | Various patterns | Context-specific fixes |

#### 🟡 MAJOR (28 patterns)
**Quality degraders** - AI safety wrappers and hedging:

**Categories**:
- **Emotion Wrappers** (3): `a sense of [emotion]`, `felt a sense of`, `could sense`
- **Filter Phrases** (7): `seemed to`, `appeared to`, `found myself`, `couldn't help but`, `almost seemed`
- **AI Crutch Phrases** (3): `to be honest`, `to be fair`, `at the end of the day`
- **Process Verbs** (4): `started to`, `began to`, `proceeded to`, `managed to`
- **Perception Verbs** (3): `could feel`, `was aware`, `realized that`
- **Nominalizations** (4): `the fact that`, `the idea that`, `the reason why`, `due to the fact`

**Example**:
```
❌ "I couldn't help but feel a sense of unease"
✅ "Unease gnawed at me"
```

#### 🟢 MINOR (29 patterns)
**Style polish** - Formal vocabulary and overused transitions:

**Categories**:
- **Formal Vocabulary** (5): `shall we`, `I shall`, `procure`, `inquire`, `commence`
- **Hedge Words** (5): `somewhat`, `rather`, `a bit`, `kind of`, `sort of`
- **Gaze Verbs** (3): `glanced at`, `looked at`, `turned to`
- **Reaction Verbs** (3): `let out a sigh`, `nodded head`, `shrugged shoulders`

**Example**:
```
❌ "Shall we proceed to procure sustenance?"
✅ "Wanna grab some food?"
```

### Pattern Structure

Each pattern includes:

```json
{
    "id": "pattern_identifier",
    "regex": "\\bpattern regex\\b",
    "display": "human-readable name",
    "fix": "How to fix this pattern",
    "source": "Why AI generates this",
    "proximity_penalty": {
        "window": 100,
        "action": "FLAG_ECHO",
        "severity_override": "CRITICAL",
        "fix_instruction": "Specific remediation"
    }
}
```

### Usage

**Detection**:
```python
import json
import re

with open('anti_ai_ism_patterns.json') as f:
    patterns = json.load(f)

# Check text for AI-isms
for severity in ['CRITICAL', 'MAJOR', 'MINOR']:
    for category in patterns[severity]['categories'].values():
        for pattern in category['patterns']:
            matches = re.findall(pattern['regex'], text, re.IGNORECASE)
            if matches:
                print(f"{severity}: {pattern['id']} - {len(matches)} occurrences")
```

**Target Metrics**:
- CRITICAL patterns: 0 occurrences (blocks publication)
- MAJOR patterns: <5 per chapter
- MINOR patterns: <10 per chapter
- Overall AI-ism density: <0.3 per 1000 words

---

## Echo Detection System

### Overview

**Integrated with**: `anti_ai_ism_patterns.json`  
**Coverage**: 23 patterns (36.5% of total)  
**Purpose**: Catch AI tendency to cluster "safe" sentence structures

Echo Detection moves quality checking from **count-based** ("Is this word bad?") to **flow-based** ("Is this rhythm bad?") analysis.

### Core Concept

**The Problem**:
```
❌ BAD (Clustered):
"He started to walk toward her. She started to speak. They started to argue."
3x "started to" in 15 words = robotic drone effect

✅ GOOD (Distributed):
"He started to walk..." [2000 words later] "...They started to argue."
Same count, different flow = acceptable
```

### Metadata Configuration

```json
{
  "_meta": {
    "echo_detection": {
      "enabled": true,
      "default_proximity_window": 100,
      "proximity_thresholds": {
        "critical": 50,
        "major": 100,
        "minor": 150
      },
      "rationale": "AI reuses 'safe' structures too close together"
    }
  }
}
```

### Proximity Windows

| Window Size | Pattern Count | Use Case |
|-------------|---------------|----------|
| **50 words** | 3 patterns | Tight clustering (redundant constructions) |
| **75 words** | 5 patterns | Close proximity (agency-removal patterns) |
| **100 words** | 12 patterns | Default detection (common AI-isms) |
| **150 words** | 3 patterns | Loose monitoring (legitimate patterns) |

### Pattern Coverage

**🔴 CRITICAL Escalation** (5 patterns):
- `started_to`, `began_to` (100-word windows)
- `found_myself`, `couldnt_help_but` (75-word windows)
- `felt_sense_of` (75-word window)

**🟡 MAJOR Escalation** (16 patterns):
- Emotion wrappers: `sense_of_emotion`, `could_sense`
- Filter phrases: `seemed_to`, `appeared_to`, `almost_seemed`
- Gaze verbs: `glanced_at`, `looked_at`, `turned_to`
- Reaction verbs: `let_out_sigh`, `nodded_head`, `shrugged_shoulders`
- Hedge words: `a_bit`, `kind_of`, `sort_of`
- Process: `managed_to`
- Perception: `realized_that`

**🟢 MINOR Monitoring** (2 patterns):
- `somewhat`, `rather` (150-word windows)

### Proximity Penalty Structure

```json
{
    "proximity_penalty": {
        "window": 100,
        "action": "FLAG_ECHO",
        "severity_override": "CRITICAL",
        "fix_instruction": "Vary with synonyms or use direct verb"
    }
}
```

**Logic**:
```
Instance 1: "started to walk" at word 100 → MINOR flag
Instance 2: "started to run" at word 150 → Distance: 50 words
Trigger: 50 < 100-word window → Escalate to CRITICAL
Result: Forces variation ("ran" / "took off running")
```

### Detection Algorithm

```python
def check_echo(pattern_id, current_position, last_seen_positions):
    """
    Check if pattern creates an echo within proximity window
    """
    if pattern_id not in last_seen_positions:
        last_seen_positions[pattern_id] = []
        return False
    
    window = get_proximity_window(pattern_id)
    
    for prev_position in reversed(last_seen_positions[pattern_id]):
        distance = current_position - prev_position
        
        if distance < window:
            # Echo detected - escalate severity
            return True
        
        if distance > window * 2:
            break
    
    last_seen_positions[pattern_id].append(current_position)
    return False
```

### Statistics

```
📊 Total Patterns: 63
🔍 Echo Detection: 23 patterns (36.5% coverage)
   • CRITICAL escalation: 5 patterns
   • MAJOR escalation: 16 patterns
   • MINOR monitoring: 2 patterns

📏 Window Distribution:
   • 50-word windows: 3 patterns (4.8%)
   • 75-word windows: 5 patterns (7.9%)
   • 100-word windows: 12 patterns (19.0%)
   • 150-word windows: 3 patterns (4.8%)
```

### Coverage by Category

| Category | Total | Echo Detection | Coverage |
|----------|-------|----------------|----------|
| Process Verbs | 4 | 3 | 75% |
| Filter Phrases | 7 | 5 | 71% |
| Emotion Wrappers | 3 | 3 | 100% |
| Gaze Verbs | 3 | 3 | 100% |
| Reaction Verbs | 3 | 3 | 100% |
| Hedge Words | 5 | 5 | 100% |
| Perception Verbs | 3 | 1 | 33% |

---

## CJK Artifact Validation

### Overview

**File**: `cjk_validation_rules.json`  
**Purpose**: Detect and remove stray Chinese characters in Japanese source text  
**Method**: Context-aware multi-factor scoring

The CJK Artifact Validator detects Chinese character leaks that corrupt Japanese source text during EPUB extraction, using a sophisticated confidence scoring system.

### Configuration

```json
{
  "detection": {
    "min_confidence_threshold": 0.7,
    "context_window_size": 5,
    "scoring_weights": {
      "character_frequency": 0.25,
      "neighboring_context": 0.30,
      "compound_patterns": 0.30,
      "script_boundaries": 0.15
    }
  },
  "character_lists": {
    "common_japanese_kanji": ["一", "二", "三", ...],
    "chinese_only_chars": ["爲", "這", "個", "們", ...],
    "chinese_compounds": ["有好", "爲了", "這個", ...]
  },
  "strict_mode": false,
  "auto_removal": false
}
```

### Detection Algorithm

**Multi-Factor Scoring**:

1. **Character Frequency (25%)**
   - Checks against 2000+ common Japanese Kanji
   - Rare/Chinese-only characters flagged

2. **Neighboring Context (30%)**
   - Examines 5 characters on each side
   - Looks for hiragana/katakana presence
   - Isolated CJK without kana = suspicious

3. **Compound Patterns (30%)**
   - Detects known Chinese pairs: 有好, 爲了, 這個
   - Combinations rarely used in Japanese

4. **Script Boundaries (15%)**
   - Flags CJK surrounded by Latin/Vietnamese
   - Indicates extraction corruption

### Confidence Scoring

| Score Range | Classification | Action |
|-------------|----------------|--------|
| 0.9-1.0 | Definite artifact | Flag for immediate removal |
| 0.8-0.9 | Very suspicious | Review required |
| 0.7-0.8 | Likely artifact | Default threshold |
| 0.0-0.7 | Possibly valid | No action |

### Character Lists

**Common Japanese Kanji** (2000+ characters):
```json
"common_japanese_kanji": [
  "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
  "百", "千", "万", "円", "年", "月", "日", "時", "分",
  "人", "大", "小", "中", "学", "生", "先", "本", "文", "字",
  ...
]
```

**Chinese-Only Characters**:
```json
"chinese_only_chars": [
  "爲",  // Traditional "為"
  "這",  // Chinese "this"
  "個",  // Used differently in Chinese
  "們",  // Plural marker
  "嗎", "呢", "啊", "吧",  // Chinese particles
  "係", "喺", "啲", "嘅"   // Cantonese
]
```

**Chinese Compound Patterns**:
```json
"chinese_compounds": [
  "有好",  // ✓ Found in production volume
  "爲了", "這個", "那個",
  "什麼", "怎麼",
  "沒有", "已經"
]
```

### Operating Modes

#### Detection Mode (Default)
```json
{
  "strict_mode": false,
  "auto_removal": false,
  "min_confidence_threshold": 0.7
}
```
- Logs all detected artifacts
- Does NOT modify files
- Allows manual review
- ⭐ **RECOMMENDED** for first-time use

#### Auto-Removal Mode
```json
{
  "strict_mode": true,
  "auto_removal": true,
  "min_confidence_threshold": 0.8
}
```
- Automatically removes detected artifacts
- Higher confidence threshold required
- Logs all removals
- Use after validating detection accuracy

### Example Detection Report

```
============================================================
CJK ARTIFACT DETECTION REPORT
============================================================

Volume: example_volume_20260130
Files processed: 16
Total artifacts found: 1

File: VN/CHAPTER_02.md
  Line 63: '有' (U+6709) confidence=0.80
  Context: ... cũng [有]好 ý. ...
  Reason: Chinese compound: 有好
          No kana neighbors
          Left context: Latin/Vietnamese
  Status: FLAGGED FOR REVIEW
============================================================
```

### Performance Benchmarks

- **Processing speed**: <100ms per volume
- **Memory usage**: <5MB
- **Detection accuracy**: 100% on known artifacts
- **False positive rate**: <5%

---

## Configuration Files

### Directory Structure

```
pipeline/config/
├── README.md                         # This file
├── anti_ai_ism_patterns.json        # AI-ism detection + Echo Detection
├── cjk_validation_rules.json        # CJK artifact detection rules
└── (other config files)
```

### File Specifications

#### anti_ai_ism_patterns.json

**Size**: ~30KB  
**Format**: JSON  
**Encoding**: UTF-8  
**Schema Version**: 2.0

**Structure**:
```json
{
  "_meta": {
    "version": "2.0",
    "echo_detection": { ... }
  },
  "CRITICAL": {
    "description": "...",
    "patterns": [ ... ]
  },
  "MAJOR": {
    "categories": {
      "emotion_wrappers": { "patterns": [...] },
      "filter_phrases": { "patterns": [...] },
      ...
    }
  },
  "MINOR": {
    "categories": { ... }
  }
}
```

#### cjk_validation_rules.json

**Size**: ~5KB  
**Format**: JSON  
**Encoding**: UTF-8  
**Schema Version**: 1.0

**Structure**:
```json
{
  "version": "1.0",
  "detection": {
    "min_confidence_threshold": 0.7,
    "context_window_size": 5,
    "scoring_weights": { ... }
  },
  "character_lists": {
    "common_japanese_kanji": [...],
    "chinese_only_chars": [...],
    "chinese_compounds": [...]
  },
  "strict_mode": false,
  "auto_removal": false
}
```

---

## Integration

### Pipeline Phase Integration

| Phase | Integration Point | Features Used |
|-------|-------------------|---------------|
| **Phase 1: Librarian** | EPUB extraction | CJK validation (optional pre-check) |
| **Phase 2: Translator** | Post-translation | AI-ism detection, Echo Detection, CJK cleanup, **Safety Fallback** |
| **Phase 3: Critics** | Quality audit | Pattern validation, clustering analysis |
| **Phase 4: Builder** | Final assembly | Pre-build validation |

### Safety Fallback Integration (Phase 2)

**Validated with Volume 1420**:
- Ch1-16: API Level 0 (standard) ✅
- Ch17-21: Web Gemini Fallback ✅
- Quality: A+ grade (97.5/100)

**Four-Tier Fallback System**:
1. Level 0: gemini-2.5-pro + cached_content
2. Level 1: gemini-2.5-flash + system_instruction  
3. Level 2: gemini-2.5-pro + context flush (Amnesia Protocol)
4. **Web Gemini**: Manual fallback with BLOCKED document generation

When API fails, the system generates `BLOCKED/CHAPTER_XX_BLOCKED.md` with:
- Translation prompt optimized for Web Gemini
- Full Japanese source text
- CLI instructions explaining why and how to proceed

### Python Integration

```python
# Anti-AI-ism Pattern Detection
import json
import re
from pathlib import Path

with open('config/anti_ai_ism_patterns.json') as f:
    patterns = json.load(f)

def detect_ai_isms(text, severity='MAJOR'):
    """Detect AI-isms of specified severity"""
    detections = []
    
    if severity == 'CRITICAL':
        pattern_list = patterns['CRITICAL']['patterns']
    else:
        pattern_list = []
        for category in patterns[severity]['categories'].values():
            pattern_list.extend(category['patterns'])
    
    for pattern in pattern_list:
        matches = list(re.finditer(pattern['regex'], text, re.IGNORECASE))
        if matches:
            detections.append({
                'pattern': pattern['id'],
                'count': len(matches),
                'severity': severity,
                'fix': pattern['fix']
            })
    
    return detections

# Echo Detection
def detect_echoes(text, patterns_config):
    """Detect clustered patterns within proximity windows"""
    last_seen = {}
    echoes = []
    
    words = text.split()
    
    for severity in ['MAJOR', 'MINOR']:
        for category in patterns_config[severity]['categories'].values():
            for pattern in category['patterns']:
                if 'proximity_penalty' not in pattern:
                    continue
                
                window = pattern['proximity_penalty']['window']
                pattern_id = pattern['id']
                
                for match in re.finditer(pattern['regex'], text):
                    word_pos = len(text[:match.start()].split())
                    
                    if pattern_id in last_seen:
                        distance = word_pos - last_seen[pattern_id]
                        if distance < window:
                            echoes.append({
                                'pattern': pattern_id,
                                'distance': distance,
                                'window': window,
                                'severity': pattern['proximity_penalty']['severity_override']
                            })
                    
                    last_seen[pattern_id] = word_pos
    
    return echoes

# CJK Artifact Detection
with open('config/cjk_validation_rules.json') as f:
    cjk_config = json.load(f)

def detect_cjk_artifacts(text, config):
    """Detect Chinese character leaks"""
    artifacts = []
    threshold = config['detection']['min_confidence_threshold']
    
    for i, char in enumerate(text):
        if is_cjk(char):
            confidence = calculate_confidence(text, i, config)
            if confidence >= threshold:
                artifacts.append({
                    'char': char,
                    'position': i,
                    'confidence': confidence,
                    'context': text[max(0,i-10):i+10]
                })
    
    return artifacts
```

---

## Usage Examples

### Example 1: Full Quality Audit

```python
from pathlib import Path
import json

def audit_chapter(chapter_file):
    """Comprehensive quality audit using all three systems"""
    
    # Load configurations
    with open('config/anti_ai_ism_patterns.json') as f:
        ai_patterns = json.load(f)
    
    with open('config/cjk_validation_rules.json') as f:
        cjk_config = json.load(f)
    
    # Read chapter
    text = Path(chapter_file).read_text(encoding='utf-8')
    
    # 1. Critical AI-ism check (publication blockers)
    critical = detect_ai_isms(text, severity='CRITICAL')
    if critical:
        print(f"🔴 CRITICAL: {len(critical)} publication blockers found")
        return False
    
    # 2. Major AI-ism check
    major = detect_ai_isms(text, severity='MAJOR')
    if len(major) > 5:
        print(f"🟡 MAJOR: {len(major)} quality degraders (target: <5)")
    
    # 3. Echo detection
    echoes = detect_echoes(text, ai_patterns)
    if echoes:
        print(f"🔍 ECHO: {len(echoes)} clustering patterns detected")
        for echo in echoes:
            print(f"  • {echo['pattern']}: {echo['distance']} words apart "
                  f"(window: {echo['window']})")
    
    # 4. CJK artifact check
    artifacts = detect_cjk_artifacts(text, cjk_config)
    if artifacts:
        print(f"⚠️  CJK: {len(artifacts)} Chinese character leaks found")
    
    # Overall grade
    score = 100
    score -= len(critical) * 20  # Critical = -20 each
    score -= len(major) * 2       # Major = -2 each
    score -= len(echoes) * 5      # Echo = -5 each
    score -= len(artifacts) * 3   # Artifact = -3 each
    
    grade = 'A+' if score >= 95 else 'A' if score >= 90 else 'B' if score >= 80 else 'C'
    print(f"\n📊 Final Score: {score}/100 (Grade {grade})")
    
    return score >= 80  # Pass threshold

# Usage
audit_chapter('WORK/volume_id/EN/CHAPTER_01.md')
```

### Example 2: Real-Time Translation Filter

```python
def validate_translation(source_jp, translation_en):
    """Validate translation output before saving"""
    
    issues = []
    
    # Check AI-isms
    critical = detect_ai_isms(translation_en, 'CRITICAL')
    if critical:
        issues.append(f"CRITICAL: {[p['pattern'] for p in critical]}")
    
    # Check Echo clustering
    echoes = detect_echoes(translation_en, ai_patterns)
    if len(echoes) > 3:
        issues.append(f"ECHO: {len(echoes)} clustered patterns")
    
    # Check CJK leaks (in Japanese source)
    artifacts = detect_cjk_artifacts(source_jp, cjk_config)
    if artifacts:
        issues.append(f"CJK: {len(artifacts)} artifacts in source")
    
    if issues:
        print("⚠️  Validation failed:")
        for issue in issues:
            print(f"  • {issue}")
        return False
    
    print("✅ Translation validated")
    return True

# Usage in translator
translation = translate_with_gemini(source_text)
if validate_translation(source_text, translation):
    save_translation(translation)
else:
    # Retry with stricter prompt
    translation = translate_with_gemini(source_text, strict_mode=True)
```

### Example 3: Batch Volume Analysis

```python
def analyze_volume(volume_path):
    """Analyze entire volume for quality metrics"""
    
    stats = {
        'total_chapters': 0,
        'ai_isms': {'CRITICAL': 0, 'MAJOR': 0, 'MINOR': 0},
        'echoes': 0,
        'cjk_artifacts': 0,
        'avg_score': 0
    }
    
    # Process all chapters
    en_dir = Path(volume_path) / 'EN'
    chapters = sorted(en_dir.glob('CHAPTER_*.md'))
    
    scores = []
    for chapter in chapters:
        text = chapter.read_text(encoding='utf-8')
        
        # Count AI-isms
        for severity in ['CRITICAL', 'MAJOR', 'MINOR']:
            count = len(detect_ai_isms(text, severity))
            stats['ai_isms'][severity] += count
        
        # Count echoes
        echoes = detect_echoes(text, ai_patterns)
        stats['echoes'] += len(echoes)
        
        # Calculate chapter score
        score = 100 - (stats['ai_isms']['CRITICAL'] * 20 + 
                       stats['ai_isms']['MAJOR'] * 2 +
                       len(echoes) * 5)
        scores.append(score)
        stats['total_chapters'] += 1
    
    stats['avg_score'] = sum(scores) / len(scores) if scores else 0
    
    # Print report
    print(f"""
    📊 Volume Quality Report
    ════════════════════════════════════════
    Chapters analyzed: {stats['total_chapters']}
    
    AI-isms:
      • CRITICAL: {stats['ai_isms']['CRITICAL']}
      • MAJOR: {stats['ai_isms']['MAJOR']}
      • MINOR: {stats['ai_isms']['MINOR']}
    
    Echo Detection:
      • Total clusters: {stats['echoes']}
    
    Average Score: {stats['avg_score']:.1f}/100
    ════════════════════════════════════════
    """)
    
    return stats

# Usage
analyze_volume('WORK/volume_20260130_abcd')
```

---

## Best Practices

### Configuration Tuning

**For Strict Quality Control** (Publication):
```json
{
  "anti_ai_ism": {
    "critical_tolerance": 0,
    "major_tolerance": 3,
    "echo_detection": {
      "enabled": true,
      "min_confidence": 0.8
    }
  },
  "cjk_validation": {
    "strict_mode": true,
    "min_confidence_threshold": 0.8
  }
}
```

**For Draft/Development**:
```json
{
  "anti_ai_ism": {
    "critical_tolerance": 1,
    "major_tolerance": 8,
    "echo_detection": {
      "enabled": true,
      "min_confidence": 0.6
    }
  },
  "cjk_validation": {
    "strict_mode": false,
    "min_confidence_threshold": 0.7
  }
}
```

### Performance Optimization

1. **Load configurations once** at pipeline start
2. **Compile regex patterns** and cache them
3. **Use parallel processing** for batch volumes
4. **Implement early exit** for CRITICAL issues
5. **Cache proximity calculations** for Echo Detection

### Maintenance

**Regular Updates**:
- Review new AI-ism patterns monthly
- Add discovered Chinese compound patterns
- Adjust confidence thresholds based on false positive rate
- Update common Japanese Kanji list for new volumes

**Validation**:
- Test on known good/bad samples quarterly
- Validate detection accuracy on edge cases
- Review false positive reports
- Benchmark performance on large volumes

---

## Related Documentation

### Technical Guides
- [ECHO_DETECTION_GUIDE.md](../docs/ECHO_DETECTION_GUIDE.md) - Complete Echo Detection technical specifications
- [CJK_ARTIFACT_CLEANER.md](../documents/CJK_ARTIFACT_CLEANER.md) - CJK detection implementation
- [ANTI_AI_ISM_INTEGRATION_COMPLETE.md](../documents/ANTI_AI_ISM_INTEGRATION_COMPLETE.md) - AI-ism system integration

### API Documentation
- [anti_ai_ism_patterns.json](anti_ai_ism_patterns.json) - Pattern library schema
- [cjk_validation_rules.json](cjk_validation_rules.json) - Validation rules schema

### Pipeline Integration
- [README.md](../../README.md) - Main MTL Studio documentation
- Phase 2 Translator integration
- Phase 3 Critics QC workflow

---

## Support

For issues, questions, or contributions:
- Review related documentation above
- Check configuration schema version compatibility
- Test on sample chapters before production use
- Validate JSON syntax after manual edits

---

**Version**: 3.5 LTS  
**Last Updated**: January 30, 2026  
**Status**: ✅ Production Ready  
**Features**: Anti-AI-ism Patterns (63), Echo Detection (23), CJK Validation
