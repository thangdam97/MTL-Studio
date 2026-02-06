# MTL STUDIO AUDIT SYSTEM V2.0

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AUDIT ORCHESTRATOR                               │
│                    (Dispatches to Subagents)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────────────┐
          │                         │                                 │
          ▼                         ▼                                 ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  SUBAGENT 1      │    │  SUBAGENT 2      │    │  SUBAGENT 3      │    │  SUBAGENT 4      │
│  CONTENT         │    │  CONTENT         │    │  PROSE           │    │  GAP             │
│  FIDELITY        │    │  INTEGRITY       │    │  QUALITY         │    │  PRESERVATION    │
│                  │    │                  │    │                  │    │                  │
│  Zero tolerance  │    │  Structural      │    │  English         │    │  Semantic gap    │
│  for truncation  │    │  validation      │    │  naturalness     │    │  analysis        │
│  /censorship     │    │  (names, terms,  │    │  via Grammar     │    │  (Gaps A/B/C)    │
│                  │    │  formatting)     │    │  RAG patterns    │    │  + Genre traits  │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ fidelity_audit   │    │ integrity_audit  │    │ prose_audit      │    │ gap_preservation │
│ _report.json     │    │ _report.json     │    │ _report.json     │    │ _audit_report    │
│                  │    │ + genre_traits   │    │                  │    │ .json            │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │                       │
         └───────────────────────┼───────────────────────┼───────────────────────┘
                                 │                       │
                                 ▼                       ▼
                    ┌──────────────────────────┐
                    │     FINAL AUDITOR        │
                    │  Aggregates 4 JSONs      │
                    │  → Final Grade + Report  │
                    └──────────────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────┐
                    │   FINAL_AUDIT_REPORT.md  │
                    │   + audit_summary.json   │
                    └──────────────────────────┘
```

---

## SUBAGENT 1: CONTENT FIDELITY AUDITOR

### Mission
**ZERO TOLERANCE** for truncation, censorship, or lazy summarization. Every Japanese source line must have a corresponding English translation.

### Input
- `JP/*.md` - Japanese source chapters
- `EN/*.md` - English translated chapters

### Output Schema: `fidelity_audit_report.json`

```json
{
  "audit_type": "content_fidelity",
  "volume_id": "05df",
  "timestamp": "2026-01-31T14:30:00Z",
  "auditor_version": "2.0",
  
  "summary": {
    "total_jp_lines": 6433,
    "total_en_lines": 6451,
    "line_variance_percent": 0.28,
    "total_jp_content_units": 850,
    "missing_content_units": 2,
    "altered_content_units": 3,
    "deviation_percent": 0.59,
    "verdict": "PASS"
  },
  
  "thresholds": {
    "pass": "<5% deviation",
    "review": "5-10% deviation", 
    "fail": ">10% deviation",
    "critical_fail": ">15% deviation (blocks publication)"
  },
  
  "chapters": [
    {
      "chapter_id": "01",
      "jp_title": "第一章　出会い",
      "en_title": "Chapter 1: The Encounter",
      "jp_lines": 712,
      "en_lines": 718,
      "jp_content_units": 95,
      "issues": []
    },
    {
      "chapter_id": "03",
      "jp_title": "第三章　波乱",
      "en_title": "Chapter 3: Turbulence",
      "jp_lines": 680,
      "en_lines": 675,
      "jp_content_units": 88,
      "issues": [
        {
          "issue_id": "FID-03-001",
          "type": "TRUNCATION",
          "severity": "CRITICAL",
          "jp_line": 245,
          "jp_content": "彼女は長い髪を風になびかせながら、夕日に照らされた校庭を歩いていた。その姿はまるで絵画のようだった。",
          "en_line": 242,
          "en_content": "She walked across the schoolyard.",
          "analysis": "Second sentence describing her appearance like a painting was truncated",
          "content_loss": "Descriptive atmosphere, visual imagery",
          "recommendation": "Restore: 'Her figure, with her long hair swaying in the wind as the setting sun illuminated the schoolyard, was like something out of a painting.'"
        }
      ]
    }
  ],
  
  "issue_categories": {
    "TRUNCATION": {
      "description": "Content removed or shortened without justification",
      "count": 1,
      "severity": "CRITICAL",
      "examples": ["FID-03-001"]
    },
    "CENSORSHIP": {
      "description": "Content altered due to perceived sensitivity",
      "count": 0,
      "severity": "CRITICAL",
      "examples": []
    },
    "SUMMARIZATION": {
      "description": "Multiple sentences lazily combined into one",
      "count": 1,
      "severity": "HIGH",
      "examples": ["FID-05-002"]
    },
    "OMISSION": {
      "description": "Entire paragraph or dialogue exchange missing",
      "count": 0,
      "severity": "CRITICAL",
      "examples": []
    },
    "ADDITION": {
      "description": "Content added not present in source",
      "count": 1,
      "severity": "MEDIUM",
      "examples": ["FID-07-001"]
    }
  },
  
  "validation_checks": {
    "dialogue_count_match": {
      "jp_dialogue_lines": 342,
      "en_dialogue_lines": 340,
      "variance": 2,
      "status": "PASS"
    },
    "paragraph_count_match": {
      "jp_paragraphs": 156,
      "en_paragraphs": 158,
      "variance": 2,
      "status": "PASS"
    },
    "scene_break_match": {
      "jp_scene_breaks": 12,
      "en_scene_breaks": 12,
      "variance": 0,
      "status": "PASS"
    },
    "character_appearance_match": {
      "characters_in_jp": ["真理亜", "如月", "主人公"],
      "characters_in_en": ["Maria", "Kisaragi", "Protagonist"],
      "missing_characters": [],
      "status": "PASS"
    }
  },
  
  "final_verdict": {
    "grade": "A",
    "deviation_percent": 0.59,
    "status": "PASS",
    "blocking_issues": 0,
    "recommendation": "Content fidelity verified. Proceed to integrity audit."
  }
}
```

### Detection Rules

```xml
<FIDELITY_DETECTION_RULES>
  <RULE id="TRUNCATION">
    <TRIGGER>
      - EN sentence significantly shorter than JP equivalent
      - JP has 2+ clauses, EN has only 1
      - Descriptive content (adjectives, adverbs, imagery) missing
    </TRIGGER>
    <THRESHOLD>
      - JP sentence: 50+ characters → EN must have 20+ words (approximate)
      - If EN has <50% expected length → FLAG
    </THRESHOLD>
  </RULE>
  
  <RULE id="CENSORSHIP">
    <TRIGGER>
      - Romantic content softened ("kissed" → "looked at")
      - Physical descriptions removed
      - Emotional intensity reduced
      - Violence/tension sanitized
    </TRIGGER>
    <KEYWORDS_JP>
      キス, 抱き, 胸, 触, 唇, ドキドキ, 恥ずかし
    </KEYWORDS_JP>
    <CHECK>
      If JP contains intimate keywords, verify EN preserves intent
    </CHECK>
  </RULE>
  
  <RULE id="SUMMARIZATION">
    <TRIGGER>
      - Multiple JP paragraphs → Single EN paragraph
      - Step-by-step actions compressed into summary
      - Dialogue exchanges reduced
    </TRIGGER>
    <EXAMPLE>
      JP: "まず靴を脱いだ。それから鍵を置いた。そして部屋に入った。"
      BAD EN: "He entered the room."
      GOOD EN: "First, he took off his shoes. Then he set down his keys. Finally, he stepped into the room."
    </EXAMPLE>
  </RULE>
  
  <RULE id="OMISSION">
    <TRIGGER>
      - Entire paragraph in JP has no EN equivalent
      - Character dialogue completely missing
      - Scene description gap
    </TRIGGER>
    <SEVERITY>CRITICAL - BLOCKS PUBLICATION</SEVERITY>
  </RULE>
</FIDELITY_DETECTION_RULES>
```

---

## SUBAGENT 2: CONTENT INTEGRITY AUDITOR

### Mission
Validate structural elements: chapter titles, names, terms, formatting standards, illustration markers, and cross-reference with source.

### Input
- `EN/*.md` - English translated chapters
- `JP/*.md` - Japanese source (for title verification)
- `metadata_en.json` - Character profiles and terms
- `.context/name_registry.json` - Canonical name spellings
- `.context/manifest.json` - Glossary terms

### Output Schema: `integrity_audit_report.json`

```json
{
  "audit_type": "content_integrity",
  "volume_id": "05df",
  "timestamp": "2026-01-31T14:35:00Z",
  "auditor_version": "2.0",
  
  "summary": {
    "total_checks": 245,
    "passed": 240,
    "warnings": 4,
    "failures": 1,
    "pass_rate": 97.96,
    "verdict": "PASS_WITH_WARNINGS"
  },
  
  "chapter_titles": {
    "status": "PASS",
    "chapters": [
      {
        "chapter_id": "01",
        "jp_title": "第一章　出会い",
        "en_title": "Chapter 1: The Encounter",
        "title_match": true,
        "format_correct": true
      }
    ],
    "issues": []
  },
  
  "character_names": {
    "status": "PASS",
    "registry_loaded": true,
    "characters_verified": 8,
    "checks": [
      {
        "character_id": "maria",
        "canonical_name": "Maria",
        "jp_source": "真理亜",
        "ruby": "まりあ",
        "occurrences_checked": 156,
        "inconsistencies": 0,
        "status": "PASS"
      },
      {
        "character_id": "kisaragi",
        "canonical_name": "Kisaragi",
        "jp_source": "如月",
        "ruby": "きさらぎ",
        "occurrences_checked": 89,
        "inconsistencies": 1,
        "status": "WARNING",
        "issues": [
          {
            "issue_id": "INT-NAME-001",
            "chapter": "05",
            "line": 234,
            "found": "Kisargi",
            "expected": "Kisaragi",
            "type": "TYPO"
          }
        ]
      }
    ]
  },
  
  "name_order": {
    "status": "PASS",
    "standard": "JAPANESE_ORDER",
    "description": "Surname First (Kisaragi Yuki, not Yuki Kisaragi)",
    "violations": []
  },
  
  "honorifics": {
    "status": "PASS",
    "standard": "HYBRID_LOCALIZATION",
    "retained": ["-san", "-kun", "-chan", "-senpai", "-sensei", "-sama"],
    "localized": ["Onii-chan", "Onee-san"],
    "violations": [],
    "consistency_score": 100
  },
  
  "glossary_terms": {
    "status": "PASS",
    "terms_loaded": 24,
    "checks": [
      {
        "term_jp": "学園",
        "term_en": "academy",
        "occurrences": 45,
        "consistent": true
      },
      {
        "term_jp": "幼馴染",
        "term_en": "childhood friend",
        "occurrences": 78,
        "consistent": true
      }
    ],
    "inconsistencies": []
  },
  
  "formatting": {
    "status": "PASS_WITH_WARNINGS",
    "checks": {
      "smart_quotes": {
        "status": "PASS",
        "straight_quotes_found": 0
      },
      "em_dashes": {
        "status": "WARNING",
        "issues": [
          {
            "issue_id": "INT-FMT-001",
            "chapter": "03",
            "line": 156,
            "found": "--",
            "expected": "—",
            "auto_fixable": true
          }
        ]
      },
      "ellipsis": {
        "status": "PASS",
        "triple_dots_found": 0,
        "proper_ellipsis_used": true
      },
      "spacing": {
        "status": "PASS",
        "double_spaces_found": 0
      },
      "line_breaks": {
        "status": "PASS",
        "excessive_breaks": 0
      }
    },
    "auto_fixable_count": 3
  },
  
  "illustration_markers": {
    "status": "PASS",
    "jp_illustrations": 12,
    "en_illustrations": 12,
    "markers": [
      {
        "image_id": "i-001",
        "jp_location": "Chapter 01, after line 45",
        "en_location": "Chapter 01, after line 47",
        "semantic_match": true,
        "format_correct": true
      }
    ],
    "missing": [],
    "misplaced": []
  },
  
  "scene_breaks": {
    "status": "PASS",
    "jp_breaks": 15,
    "en_breaks": 15,
    "format": "* * *",
    "consistent": true
  },
  
  "sequel_continuity": {
    "is_sequel": false,
    "previous_volume": null,
    "checks_performed": [],
    "status": "N/A"
  },
  
  "genre_specific_traits": {
    "genre": "fantasy_idol_slice_of_life",
    "required_traits": [
      "idol_terminology_preserved",
      "vtuber_culture_authentic",
      "gaming_terminology_consistent",
      "kansai_dialect_markers_present"
    ],
    "validation": {
      "idol_terms": {
        "status": "PASS",
        "kept_japanese": ["VTuber", "oshi", "fanservice", "jirai-kei"],
        "localized": ["stream", "subscriber", "viewer"],
        "consistent": true
      },
      "gaming_terms": {
        "status": "PASS",
        "kept_japanese": ["KASSEN", "Tsukuyomi"],
        "localized": ["aim", "rank", "pro player"],
        "consistent": true
      },
      "dialect_handling": {
        "status": "PASS",
        "kansai_characters": ["Iroha's Mother", "Grandfather"],
        "markers_used": ["thanks so much", "ain't", "can't be helped"],
        "avoided_stereotypes": true
      }
    },
    "series_specific": {
      "title": "Cosmic Princess Kaguya!",
      "key_themes": ["performative_identity", "dual_persona", "digital_trauma"],
      "critical_elements": [
        "Kaguya's IRL gremlin vs VR idol mode switching",
        "Iroha's phone anxiety as PTSD trigger",
        "Classical folklore framing juxtaposed with modern slang"
      ],
      "validation_status": "PASS"
    }
  },
  
  "final_verdict": {
    "grade": "A",
    "pass_rate": 97.96,
    "status": "PASS_WITH_WARNINGS",
    "blocking_issues": 0,
    "auto_fixable_issues": 3,
    "recommendation": "Minor formatting issues detected. Auto-fix available. Proceed to prose and gap audits."
  }
}
```

### Validation Rules

```xml
<INTEGRITY_VALIDATION_RULES>
  <RULE id="NAME_REGISTRY">
    <SOURCE>.context/name_registry.json</SOURCE>
    <CHECK>
      For each character in registry:
      1. Search all EN chapters for character name
      2. Verify spelling matches canonical form EXACTLY
      3. Flag ANY deviation (typos, alternate spellings)
    </CHECK>
    <SEVERITY>
      - Typo: WARNING (auto-fixable)
      - Wrong name entirely: CRITICAL (blocks publication)
      - Name order reversed: CRITICAL (blocks publication)
    </SEVERITY>
  </RULE>
  
  <RULE id="SEQUEL_CONTINUITY">
    <APPLIES_TO>Volume 2+ only</APPLIES_TO>
    <CHECK>
      1. Load previous volume's name_registry.json
      2. Compare ALL character names with current volume
      3. Verify pronouns unchanged (ore/boku/watashi)
      4. Verify relationship dynamics preserved
    </CHECK>
    <SEVERITY>CRITICAL - ANY deviation blocks publication</SEVERITY>
  </RULE>
  
  <RULE id="FORMATTING_STANDARDS">
    <QUOTES>
      - Dialogue: "curly quotes" (U+201C, U+201D)
      - NOT: "straight quotes" (U+0022)
    </QUOTES>
    <DASHES>
      - Interruption/range: em dash — (U+2014)
      - NOT: double hyphen --
      - NOT: en dash – for interruption
    </DASHES>
    <ELLIPSIS>
      - Use: … (U+2026)
      - NOT: ... (three periods)
    </ELLIPSIS>
    <SPACING>
      - Single space after periods
      - No double spaces anywhere
    </SPACING>
  </RULE>
  
  <RULE id="ILLUSTRATION_MARKERS">
    <FORMAT>
      <img class="fit" src="../image/i-XXX.jpg" alt=""/>
    </FORMAT>
    <CHECK>
      1. Count illustrations in JP source
      2. Verify same count in EN
      3. Verify semantic placement matches narrative beat
      4. Verify no duplicate tags
    </CHECK>
  </RULE>
</INTEGRITY_VALIDATION_RULES>
```

---

## SUBAGENT 3: PROSE QUALITY AUDITOR

### Mission
Ensure English translation adheres to natural prose standards using the Grammar RAG pattern database. Detect AI-isms, Victorian patterns, contraction issues, and missed transcreation opportunities.

### Input
- `EN/*.md` - English translated chapters
- `config/english_grammar_rag.json` - Pattern database (53 patterns)
- `config/anti_ai_ism_patterns.json` - AI-ism detection rules

### Output Schema: `prose_audit_report.json`

```json
{
  "audit_type": "prose_quality",
  "volume_id": "05df",
  "timestamp": "2026-01-31T14:40:00Z",
  "auditor_version": "2.0",
  "grammar_rag_version": "1.0",
  "patterns_loaded": 53,
  
  "summary": {
    "total_words": 45088,
    "total_sentences": 3200,
    "ai_ism_count": 12,
    "ai_ism_density": 0.27,
    "contraction_rate": 94.5,
    "victorian_patterns": 3,
    "missed_transcreations": 8,
    "prose_score": 91.2,
    "verdict": "PASS"
  },
  
  "thresholds": {
    "ai_ism_density": {
      "excellent": "<0.1 per 1k words",
      "good": "0.1-0.5 per 1k words",
      "acceptable": "0.5-1.0 per 1k words",
      "poor": ">1.0 per 1k words"
    },
    "contraction_rate": {
      "ffxvi_tier": "99%+",
      "excellent": "95%+",
      "good": "90%+",
      "acceptable": "80%+",
      "poor": "<80%"
    }
  },
  
  "ai_isms": {
    "status": "GOOD",
    "count": 12,
    "density_per_1k": 0.27,
    "by_severity": {
      "critical": 0,
      "major": 3,
      "minor": 9
    },
    "issues": [
      {
        "issue_id": "PRO-AI-001",
        "chapter": "02",
        "line": 156,
        "severity": "MAJOR",
        "pattern": "couldn't help but",
        "context": "I couldn't help but notice her smile.",
        "suggestion": "I noticed her smile." OR "Her smile caught my attention.",
        "category": "VERBOSE_CONSTRUCTION"
      },
      {
        "issue_id": "PRO-AI-002",
        "chapter": "04",
        "line": 89,
        "severity": "MINOR",
        "pattern": "a sense of",
        "context": "A sense of unease washed over me.",
        "suggestion": "Unease washed over me.",
        "category": "FILLER_PHRASE"
      }
    ],
    "categories": {
      "VERBOSE_CONSTRUCTION": 3,
      "FILLER_PHRASE": 4,
      "REDUNDANT_ADVERB": 2,
      "EMOTIONAL_TELLING": 2,
      "STIFF_PHRASING": 1
    }
  },
  
  "contractions": {
    "status": "EXCELLENT",
    "rate": 94.5,
    "total_opportunities": 1100,
    "contracted": 1039,
    "expanded": 61,
    "violations": [
      {
        "issue_id": "PRO-CON-001",
        "chapter": "03",
        "line": 234,
        "found": "I am",
        "expected": "I'm",
        "context": "I am sure she noticed.",
        "exception_applies": false
      }
    ],
    "by_type": {
      "I'm/I am": { "contracted": 156, "expanded": 3 },
      "don't/do not": { "contracted": 89, "expanded": 2 },
      "can't/cannot": { "contracted": 45, "expanded": 1 },
      "it's/it is": { "contracted": 78, "expanded": 4 }
    }
  },
  
  "victorian_patterns": {
    "status": "PASS",
    "count": 3,
    "exempted": 2,
    "flagged": 1,
    "issues": [
      {
        "issue_id": "PRO-VIC-001",
        "chapter": "05",
        "line": 167,
        "pattern": "I shall",
        "context": "I shall return shortly.",
        "character": "Protagonist",
        "archetype": "CASUAL_TEEN",
        "exemption_applies": false,
        "suggestion": "I'll be right back."
      }
    ],
    "exemptions_applied": [
      {
        "chapter": "02",
        "line": 89,
        "pattern": "If you would be so kind",
        "character": "Ojou-sama",
        "archetype": "NOBLE_LADY",
        "reason": "Character archetype permits formal speech"
      }
    ]
  },
  
  "transcreation_opportunities": {
    "status": "NEEDS_IMPROVEMENT",
    "patterns_detected": 45,
    "well_handled": 37,
    "missed": 8,
    "improvement_suggestions": [
      {
        "issue_id": "PRO-TRC-001",
        "chapter": "01",
        "line": 78,
        "jp_pattern": "やっぱり",
        "current_en": "As expected, she was there.",
        "suggested_en": "Sure enough, she was there." OR "She was there, just as I thought.",
        "pattern_id": "yappari_transcreation",
        "priority": "high"
      },
      {
        "issue_id": "PRO-TRC-002",
        "chapter": "03",
        "line": 156,
        "jp_pattern": "さすが",
        "current_en": "As expected of Maria.",
        "suggested_en": "That's Maria for you." OR "Classic Maria.",
        "pattern_id": "sasuga_transcreation",
        "priority": "high"
      },
      {
        "issue_id": "PRO-TRC-003",
        "chapter": "04",
        "line": 234,
        "jp_pattern": "仕方ない",
        "current_en": "It can't be helped.",
        "suggested_en": "Oh well." OR "What can you do?",
        "pattern_id": "shikata_nai_transcreation",
        "priority": "high"
      }
    ],
    "pattern_usage_stats": {
      "yappari_transcreation": { "detected": 12, "well_handled": 9, "missed": 3 },
      "sasuga_transcreation": { "detected": 8, "well_handled": 6, "missed": 2 },
      "maa_transcreation": { "detected": 15, "well_handled": 14, "missed": 1 },
      "betsu_ni_transcreation": { "detected": 6, "well_handled": 5, "missed": 1 }
    }
  },
  
  "character_voice": {
    "status": "GOOD",
    "characters_analyzed": 5,
    "voice_differentiation_score": 78,
    "analysis": [
      {
        "character": "Protagonist",
        "archetype": "CASUAL_TEEN_MALE",
        "expected_markers": ["contractions", "casual idioms", "short sentences"],
        "markers_found": ["contractions: 96%", "casual idioms: good", "sentence variety: moderate"],
        "score": 82
      },
      {
        "character": "Maria",
        "archetype": "CHILDHOOD_FRIEND_FEMALE",
        "expected_markers": ["contractions", "teasing tone", "familiarity"],
        "markers_found": ["contractions: 94%", "teasing: present", "familiarity: strong"],
        "score": 85
      }
    ]
  },
  
  "sentence_quality": {
    "average_length": 14.2,
    "variety_score": 76,
    "opening_variety": {
      "pronoun_starts": 34,
      "action_starts": 28,
      "description_starts": 22,
      "dialogue_starts": 16,
      "score": "GOOD"
    },
    "passive_voice_rate": 8.5,
    "nominalization_rate": 4.2
  },
  
  "final_verdict": {
    "grade": "A",
    "prose_score": 91.2,
    "status": "PASS",
    "blocking_issues": 0,
    "improvement_areas": [
      "8 missed transcreation opportunities (especially やっぱり, さすが)",
      "3 contraction violations in casual dialogue",
      "1 Victorian pattern in casual character"
    ],
    "recommendation": "High-quality prose. Minor improvements available for transcreation patterns. Ready for final audit."
  }
}
```

### Detection Integration with Grammar RAG

```python
# Prose Quality Auditor - Pattern Detection Logic

from modules.english_grammar_rag import EnglishGrammarRAG

class ProseQualityAuditor:
    def __init__(self):
        self.rag = EnglishGrammarRAG()
        self.ai_ism_patterns = self.load_ai_ism_patterns()
    
    def audit_chapter(self, jp_text: str, en_text: str, chapter_id: str) -> dict:
        """Audit a single chapter for prose quality."""
        
        results = {
            "chapter_id": chapter_id,
            "ai_isms": self.detect_ai_isms(en_text),
            "contractions": self.analyze_contractions(en_text),
            "victorian_patterns": self.detect_victorian(en_text),
            "transcreation": self.check_transcreation(jp_text, en_text)
        }
        
        return results
    
    def check_transcreation(self, jp_text: str, en_text: str) -> dict:
        """Check if transcreation patterns were properly applied."""
   SUBAGENT 4: GAP PRESERVATION AUDITOR

### Mission
Validate that semantic gaps (emotion+action, ruby text, subtext) identified in the Japanese source were properly preserved in translation. Detect gap-specific translation failures and ensure genre/series-specific traits are maintained.

### Input
- `JP/*.md` - Japanese source chapters
- `EN/*.md` - English translated chapters
- `metadata_en.json` - Gap analysis priorities and context
- `manifest.json` - Gap analysis integration config
- `.context/gap_analysis_results.json` - Pre-translation gap detection results (if available)

### Output Schema: `gap_preservation_audit_report.json`

```json
{
  "audit_type": "gap_preservation",
  "volume_id": "095d",
  "timestamp": "2026-02-01T14:45:00Z",
  "auditor_version": "2.0",
  "gap_analysis_enabled": true,
  
  "summary": {
    "total_gaps_detected": 127,
    "gap_a_count": 45,
    "gap_b_count": 38,
    "gap_c_count": 44,
    "properly_preserved": 115,
    "preservation_rate": 90.6,
    "failed_preservation": 12,
    "verdict": "GOOD"
  },
  
  "thresholds": {
    "excellent": ">95% preservation",
    "good": "90-95% preservation",
    "acceptable": "85-90% preservation",
    "poor": "<85% preservation",
    "critical_fail": "<75% preservation (blocks publication)"
  },
  
  "gap_a_emotion_action": {
    "description": "Simultaneous emotion + physical action translation",
    "priority"four subagent JSON reports into a comprehensive final audit report with overall grade and publication verdict.

### Input
- `fidelity_audit_report.json`
- `integrity_audit_report.json`
- `prose_audit_report.json`
- `gap_preservation
    "detection_context": {
      "source": "metadata_en.json gap_a_context",
      "key_patterns": [
        "work exhaustion + continuing to work",
        "sigh/breath + action",
        "trembling hands + drinking/typing",
        "piano playing + emotional memory",
        "Kaguya's weaponized wink as action sequence"
      ]
    },
    
    "issues": [
      {
        "issue_id": "GAP-A-001",
        "chapter": "04",
        "severity": "HIGH",
        "jp_line": 156,
        "jp_content": "溜息を吐いて、首を横に振る。",
        "jp_analysis": "TWO ACTIONS: (1) Sighing (emotion/breath), (2) Shaking head (physical)",
        "en_line": 154,
        "en_content": "She sighed and shook her head.",
        "en_analysis": "✅ PRESERVED: Both actions present, natural coordination with 'and'",
        "status": "PASS"
      },
      {
        "issue_id": "GAP-A-002",
        "chapter": "03",
        "severity": "CRITICAL",
        "jp_line": 89,
        "jp_content": "手が震えて、グラスの縁がカチカチと前歯に当たる。",
        "jp_analysis": "EMOTION+PHYSICAL: (1) Hands trembling (emotion/nervousness), (2) Glass chattering against teeth (physical consequence)",
        "en_line": 87,
        "en_content": "Her hands shook.",
        "en_analysis": "❌ FAILED: Second action (glass chattering) was TRUNCATED. Lost physical detail and atmosphere.",
        "recommendation": "Restore: 'Her hands trembled, the rim of the glass chattering against her teeth.'",
        "content_loss": "Physical sensation, nervous detail, atmospheric tension"
      },
      {
        "issue_id": "GAP-A-003",
        "chapter": "04",
        "severity": "HIGH",
        "jp_line": 234,
        "jp_content": "かぐやが完璧なウインクを決めながら、「お願～～い☆」と言った。",
        "jp_analysis": "VISUAL GAG + DIALOGUE: (1) Perfect wink execution (performative action), (2) Pleading tone with elongated vowels",
        "en_line": 231,
        "en_content": "\"Pleeeease!\" Kaguya said with a wink.",
        "en_analysis": "⚠️ PARTIAL: Wink present but not emphasized as deliberate PERFORMANCE. Lacks 'weaponized cuteness' framing.",
        "recommendation": "Enhance: '\"Pleeeease~☆\" Kaguya punctuated it with a perfectly executed wink—weaponized adorableness.'",
        "missed_nuance": "Performative nature of her cuteness as tactical manipulation"
      }
    ],
    
    "pattern_preservation": {
      "exhaustion_markers": {
        "detected": 12,
        "preserved": 11,
        "rate": 91.7
      },
      "breath_action_combos": {
        "detected": 8,
        "preserved": 7,
        "rate": 87.5
      },
      "visual_gags": {
        "detected": 6,
        "preserved": 4,
        "rate": 66.7
      },
      "piano_memory_sequences": {
        "detected": 3,
        "preserved": 3,
        "rate": 100
      }
    }
  },
  
  "gap_b_ruby_text": {
    "description": "Furigana/ruby annotations indicating wordplay, names, or specialized readings",
    "priority": "MEDIUM",
    "total_detected": 38,
    "properly_preserved": 35,
    "preservation_rate": 92.1,
    "status": "GOOD",
    
    "detection_context": {
      "source": "metadata_en.json gap_b_context",
      "key_patterns": [
        "Character names with furigana",
        "Game/VR terminology with ruby",
        "Idol terminology with readings",
        "Technical terms with explanatory annotations"
      ]
    },
    
    "issues": [
      {
        "issue_id": "GAP-B-001",
        "chapter": "02",
        "severity": "MEDIUM",
        "jp_line": 45,
        "jp_content": "彩葉{いろは}",
        "jp_analysis": "NAME WITH RUBY: 彩葉 (kanji) read as いろは (hiragana). Character name requiring specific romanization.",
        "en_line": 43,
        "en_content": "Iroha",
        "en_analysis": "✅ PRESERVED: Correct romanization 'Iroha' matches ruby reading",
        "status": "PASS"
      },
      {
        "issue_id": "GAP-B-002",
        "chapter": "05",
        "severity": "LOW",
        "jp_line": 123,
        "jp_content": "鎧武者{よろいむしゃ}",
        "jp_analysis": "STANDARD READING: No special wordplay, just clarification reading",
        "en_line": 121,
        "en_content": "armored warriors",
        "en_analysis": "✅ PRESERVED: Standard translation, no special handling needed",
        "status": "PASS"
      }
    ],
    
    "kira_kira_names": {
      "description": "Names with creative/unusual readings",
      "detected": 5,
      "preserved": 5,
      "examples": [
        {"jp": "彩葉{いろは}", "en": "Iroha", "status": "CORRECT"},
        {"jp": "月見{つきみ}", "en": "Tsukimi", "status": "CORRECT"}
      ]
    }
  },
  
  "gap_c_subtext": {
    "description": "Hidden meanings, sarcasm, performative speech vs true feelings",
    "priority": "HIGH",
    "total_detected": 44,
    "properly_preserved": 39,
    "preservation_rate": 88.6,
    "status": "GOOD",
    
    "detection_context": {
      "source": "metadata_en.json gap_c_context + tone_shift_instructions",
      "key_patterns": [
        "Kaguya's cute manipulation vs genuine emotion",
        "Iroha's internal sarcasm vs polite external speech",
        "Mother's harsh criticism with grief subtext",
        "Service industry smile vs genuine frustration",
        "Phone anxiety as PTSD trigger (not laziness)"
      ],
      "neutral_option_applied": true
    },
    
    "issues": [
      {
        "issue_id": "GAP-C-001",
        "chapter": "04",
        "severity": "CRITICAL",
        "jp_line": 167,
        "jp_context": "Kaguya says 'お願～～い☆' with perfect wink after Iroha refuses. Previous line shows Iroha is tired and annoyed.",
        "jp_analysis": "MANIPULATION DETECTED: Kaguya is weaponizing cuteness to override Iroha's boundary. This is PERFORMATIVE, not genuine pleading.",
        "en_line": 165,
        "en_content": "\"Please~!\" Kaguya begged sweetly.",
        "en_analysis": "⚠️ PARTIAL: 'Begged sweetly' captures cuteness but misses the MANIPULATION layer. 'Begged' implies genuine desperation when she's actually performing.",
        "recommendation": "Enhance with subtext: '\"Pleeeease~☆\" Kaguya deployed her most devastating weapon—weaponized adorableness.' OR 'turned on the charm offensive'",
        "missed_nuance": "Performative manipulation, tactical cuteness, boundary violation attempt"
      },
      {
        "issue_id": "GAP-C-002",
        "chapter": "04",
        "severity": "HIGH",
        "jp_line": 234,
        "jp_context": "Iroha sees '不在着信（１０件）' from mother. Internal monologue shows dread. Next line: 字面からすでに機嫌の悪さが伝わってくる",
        "jp_analysis": "DIGITAL TRAUMA: Phone vibration = PTSD trigger. 10 missed calls = intrusive stalking. 'Can feel bad mood from text' = learned fear response. This is FREEZE/AVOIDANCE, not laziness.",
        "en_line": 231,
        "en_content": "Ten missed calls from Mom. I groaned and put the phone down.",
        "en_analysis": "❌ FAILED: 'Groaned' implies annoyance/laziness. COMPLETELY MISSED the trauma/anxiety angle. No mention of freeze response, dread, or PTSD.",
        "recommendation": "Rewrite with trauma framing: 'Ten missed calls from Mom. My stomach dropped. I could already feel her anger seeping through the screen—that familiar, suffocating weight. I set the phone down like it might explode.'",
        "content_loss": "CRITICAL: Trauma response, PTSD trigger, anxiety paralysis, digital stalking context, mother's intrusive tech use as control mechanism"
      },
      {
        "issue_id": "GAP-C-003",
        "chapter": "07",
        "severity": "MEDIUM",
        "jp_line": 89,
        "jp_context": "Depression Protocol chapter. Iroha acts 機械的に (mechanically), 淡々と (matter-of-factly). Rain scene.",
        "jp_analysis": "TONE SHIFT: Prose should be STERILE, GRAY, NUMB to match her emotional shutdown. '雨音以外はなにも聞こえなかった' = sensory deprivation.",
        "en_line": 87,
        "en_content": "The rain drummed against the window, a steady, soothing rhythm that filled the quiet room.",
        "en_analysis": "❌ FAILED: 'Soothing rhythm' is FLOWERY and HOPEFUL. Should be sterile: 'Rain. Nothing else. No other sound reached me.' Depression protocol NOT applied.",
        "recommendation": "Apply depression tone: 'I heard nothing but the rain. The sound was flat, empty. Everything else had gone silent.'",
        "missed_instruction": "metadata_en.json → gap_c_focus → tone_shift_instructions → chapter_7_8_depression_protocol"
      },
      {
        "issue_id": "GAP-C-004",
        "chapter": "02",
        "severity": "LOW",
        "jp_line": 45,
        "jp_context": "Roka and Masami casual conversation about school, no tension",
        "jp_analysis": "NEUTRAL OPTION: Simple friendly dialogue. No subtext indicators present.",
        "en_line": 43,
        "en_content": "\"See you at lunch!\" Roka waved.",
        "en_analysis": "✅ NEUTRAL CORRECTLY APPLIED: Straightforward translation, no forced subtext. Gap C detection correctly skipped.",
        "status": "PASS"
      }
    ],
    
    "subtext_categories": {
      "performative_manipulation": {
        "detected": 8,
        "preserved": 6,
        "rate": 75.0,
        "status": "NEEDS_IMPROVEMENT"
      },
      "internal_vs_external": {
        "detected": 12,
        "preserved": 11,
        "rate": 91.7,
        "status": "GOOD"
      },
      "grief_subtext": {
        "detected": 5,
        "preserved": 4,
        "rate": 80.0,
        "status": "ACCEPTABLE"
      },
      "digital_trauma": {
        "detected": 3,
        "preserved": 1,
        "rate": 33.3,
        "status": "CRITICAL_FAILURE"
      },
      "depression_protocol": {
        "detected": 2,
        "preserved": 1,
        "rate": 50.0,
        "status": "POOR"
      },
      "neutral_option": {
        "applied_correctly": 14,
        "false_positives": 0,
        "accuracy": 100
      }
    }
  },
  
  "genre_trait_validation": {
    "status": "PASS",
    "genre": "fantasy_idol_slice_of_life_psychological",
    "series": "Cosmic Princess Kaguya!",
    
    "dual_persona_preservation": {
      "trait": "Kaguya's IRL gremlin mode vs VR idol performance",
      "priority": "CRITICAL",
      "status": "GOOD",
      "irl_gremlin_markers": {
        "detected": 15,
        "preserved": 13,
        "markers": ["Gen Z slang", "chaotic energy", "ssho/ukeru/yabai"],
        "rate": 86.7
      },
      "vr_idol_markers": {
        "detected": 8,
        "preserved": 7,
        "markers": ["polite nanodesu", "graceful tone", "ethereal speech"],
        "rate": 87.5
      },
      "code_switching": {
        "transitions_detected": 6,
        "properly_signaled": 5,
        "rate": 83.3
      }
    },
    
    "classical_framing": {
      "trait": "今は昔 classical phrases juxtaposed with modern slang",
      "priority": "HIGH",
      "status": "EXCELLENT",
      "classical_phrases": {
        "detected": 5,
        "translated_correctly": 5,
        "examples": [
          {"jp": "今は昔", "en": "Long, long ago...", "status": "PERFECT"},
          {"jp": "では、なくて", "en": "—Or not.", "status": "PERFECT"},
          {"jp": "ありけり", "en": "And so there was...", "status": "PERFECT"}
        ]
      },
      "modern_snap_back": {
        "transitions_smooth": true,
        "slang_authentic": true
      }
    },
    
    "idol_culture_authenticity": {
      "trait": "VTuber/idol terminology and subculture accuracy",
      "priority": "HIGH",
      "status": "EXCELLENT",
      "japanese_terms_kept": ["VTuber", "oshi", "fanservice", "jirai-kei"],
      "english_terms_used": ["stream", "subscriber", "viewer"],
      "consistency": 100,
      "over_explanation_avoided": true
    },
    
    "psychological_depth": {
      "trait": "Gimai Seikatsu-style performative identity crisis",
      "priority": "CRITICAL",
      "status": "NEEDS_IMPROVEMENT",
      "iroha_phone_anxiety": {
        "detected": 3,
        "preserved_as_ptsd": 1,
        "rate": 33.3,
        "status": "CRITICAL_FAILURE"
      },
      "mother_grief_subtext": {
        "detected": 5,
        "preserved": 4,
        "rate": 80.0,
        "status": "ACCEPTABLE"
      },
      "kaguya_manipulation": {
        "detected": 8,
        "preserved": 6,
        "rate": 75.0,
        "status": "ACCEPTABLE"
      }
    }
  },
  
  "final_verdict": {
    "grade": "B+",
    "preservation_rate": 90.6,
    "status": "GOOD_WITH_IMPROVEMENTS_NEEDED",
    "blocking_issues": 0,
    "critical_gaps": 2,
    "improvement_areas": [
      "Gap C: Digital trauma (phone anxiety) severely under-preserved (33.3%)",
      "Gap C: Depression protocol tone shifts missed (50%)",
      "Gap A: Visual gags need more performative framing (66.7%)",
      "Genre: Psychological depth elements require attention"
    ],
    "recommendation": "Gap preservation generally good but critical psychological elements under-translated. Recommend manual review of chapters 4, 7-8 for trauma/depression framing."
  }
}
```

### Gap Detection Rules

```xml
<GAP_DETECTION_RULES>
  <RULE id="GAP_A_EMOTION_ACTION">
    <DESCRIPTION>
      Simultaneous emotion and physical action must BOTH be preserved.
      Japanese: "verb-te, verb" structure often indicates coordination.
    </DESCRIPTION>
    <DETECTION>
      1. Search for て-form verb followed by another verb
      2. Check if first verb = emotion/breath/sensation
      3. Check if second verb = physical action
      4. Verify both present in English with coordination
    </DETECTION>
    <EXAMPLES>
      JP: 溜息を吐いて、首を横に振る
      GOOD EN: She sighed and shook her head.
      BAD EN: She sighed. (TRUNCATION - second action missing)
      
      JP: 手が震えて、グラスの縁がカチカチと前歯に当たる
      GOOD EN: Her hands trembled, the rim of the glass chattering against her teeth.
      BAD EN: Her hands shook. (CRITICAL TRUNCATION)
    </EXAMPLES>
    <SEVERITY>
      - Missing second action: CRITICAL
      - Flattened into summary: HIGH
      - Both present but awkward: MEDIUM
    </SEVERITY>
  </RULE>
  
  <RULE id="GAP_B_RUBY_TEXT">
    <DESCRIPTION>
      Furigana/ruby annotations indicate special readings, wordplay, or emphasis.
      Character names with ruby must use exact romanization.
    </DESCRIPTION>
    <DETECTION>
      1. Extract all {ruby} annotations from JP source
      2. Identify category: name / wordplay / standard reading
      3. Verify English preserves intent (romanization for names, explanation for wordplay)
    </DETECTION>
    <EXAMPLES>
      JP: 彩葉{いろは}
      GOOD EN: Iroha (matches ruby reading いろは)
      BAD EN: Ayaba (ignores ruby, uses kanji reading)
      
      JP: 愛梨{ラブリ} (kira-kira name: Lovely)
      GOOD EN: Airi (Lovely) [preserves both readings]
      BAD EN: Airi [loses the wordplay]
    </EXAMPLES>
  </RULE>
  
  <RULE id="GAP_C_SUBTEXT">
    <DESCRIPTION>
      Hidden meanings, internal vs external speech, performative vs genuine emotion.
      Must check metadata gap_c_context for scene-specific subtext indicators.
    </DESCRIPTION>
    <DETECTION>
      1. Load gap_c_context from metadata_en.json
      2. Search for scenes matching described patterns
      3. Verify English captures BOTH surface and subtext layers
      4. Apply NEUTRAL_OPTION: Skip if no subtext indicators present
    </DETECTION>
    <NEUTRAL_OPTION>
      If scene has NO subtext indicators (internal thoughts, character history, visual cues), 
      then subtext analysis is NOT required. Simple friendly dialogue = neutral translation.
      Example: "See you at lunch!" between friends = no subtext needed
    </NEUTRAL_OPTION>
    <EXAMPLES>
      <!-- Kaguya Manipulation -->
      JP: かぐやが完璧なウインクを決めながら、「お願～～い☆」
      Context: After Iroha refused. Character profile says "manipulatively cute, weaponized adorableness"
      GOOD EN: "Pleeeease~☆" Kaguya deployed her secret weapon—a perfectly executed wink.
      BAD EN: "Please!" Kaguya begged sweetly. (Misses manipulation layer)
      
      <!-- Digital Trauma -->
      JP: 母　不在着信（１０件）字面からすでに機嫌の悪さが伝わってくる
      Context: metadata says "phone anxiety = PTSD trigger, freeze response"
      GOOD EN: Ten missed calls from Mom. My stomach dropped. I could already feel her anger seeping through the screen.
      BAD EN: Ten missed calls from Mom. I groaned. (Reads as laziness, not trauma)
      
      <!-- Depression Protocol -->
      JP: 雨音以外はなにも聞こえなかった (Chapter 7-8)
      Context: metadata says "depression protocol: sterile, numb prose"
      GOOD EN: I heard nothing but the rain. Flat. Empty.
      BAD EN: The rain drummed soothingly. (Flowery, violates depression tone)
    </EXAMPLES>
    <SEVERITY>
      - Missed trauma framing: CRITICAL
      - Missed manipulation layer: HIGH
      - Missed depression tone: HIGH
      - Over-analyzing neutral scene: MEDIUM (false positive)
    </SEVERITY>
  </RULE>
  
  <RULE id="GENRE_TRAIT_VALIDATION">
    <DESCRIPTION>
      Series-specific traits from metadata must be validated.
      Example: Dual persona characters must show mode switching.
    </DESCRIPTION>
    <SOURCE>
      metadata_en.json → character_profiles → speech_pattern_modes
      metadata_en.json → genre_specific_traits
    </SOURCE>
    <VALIDATION>
      For "Cosmic Princess Kaguya!":
      - Kaguya IRL gremlin mode: Check for Gen Z slang, chaos energy
      - Kaguya VR idol mode: Check for polite, graceful, ethereal speech
      - Code-switching: Verify transitions are signaled
      - Classical framing: Verify 今は昔 → "Long, long ago..." (NOT "Now is the past")
    </VALIDATION>
  </RULE>
</GAP_DETECTION_RULES>
```

---

##      
        # Detect which patterns should have been applied
        detected_patterns = self.rag.detect_patterns(jp_text)
        
        issues = []
        for pattern in detected_patterns:
            # Check if literal translation was used instead of natural
            if self.has_literal_translation(en_text, pattern):
                issues.append({
                    "pattern_id": pattern["id"],
                    "jp_indicator": pattern["matched_indicator"],
                    "suggestion": self.rag.get_natural_alternative(pattern["id"])
                })
        
        return {
            "patterns_detected": len(detected_patterns),
            "missed": len(issues),
            "issues": issues
        }
    
    def has_literal_translation(self, en_text: str, pattern: dict) -> bool:
        """Check if the literal translation appears instead of natural."""
        literal_markers = {
            "yappari_transcreation": ["as expected", "as i expected"],
            "sasuga_transcreation": ["as expected of"],
            "shikata_nai_transcreation": ["it can't be helped", "it cannot be helped"],
            "maa_transcreation": [],  # Hard to detect literal
            "betsu_ni_transcreation": ["not particularly"],
            "zettai_transcreation": ["absolutely"],
            "mattaku_transcreation": ["completely", "totally"],
        }
        
        markers = literal_markers.get(pattern["id"], [])
        en_lower = en_text.lower()
        
        return any(marker in en_lower for marker in markers)
```

---

## FINAL AUDITOR: REPORT AGGREGATOR

### Mission
Aggregate all three subagent JSON reports into a comprehensive final audit report with overall grade and publication verdict.

### Input
- `fidelity_audit_report.json`
- `integrity_audit_report.json`
- `prose_audit_report.json`

### Output: `FINAL_AUDIT_REPORT.md` + `audit_summary.json`

### Grading Matrix

```─────────┐
│                            GRADING MATRIX V2.0                                    │
├─────────────────┬───────────┬───────────┬───────────┬──────────┬──────────────────┤
│     GRADE       │ FIDELITY  │ INTEGRITY │   PROSE   │   GAPS   │    VERDICT       │
├─────────────────┼───────────┼───────────┼───────────┼──────────┼──────────────────┤
│ A+ (FFXVI-Tier) │   PASS    │   PASS    │  95%+     │  >95%    │ PUBLISH READY    │
│ A  (Excellent)  │   PASS    │   PASS    │  90%+     │  90-95%  │ PUBLISH READY    │
│ B  (Good)       │   PASS    │  WARNINGS │  85%+     │  85-90%  │ MINOR FIXES      │
│ C  (Acceptable) │   PASS    │  WARNINGS │  80%+     │  80-85%  │ REVISION NEEDED  │
│ D  (Poor)       │  REVIEW   │   FAIL    │  <80%     │  75-80%  │ MAJOR REVISION   │
│ F  (Fail)       │   FAIL    │   FAIL    │    ANY    │  <75%    │ BLOCKS PUBLISH   │
├─────────────────┴───────────┴───────────┴───────────┴──────────┴──────────────────┤
│                         BLOCKING CONDITIONS                                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ • Content Fidelity: >10% deviation → AUTOMATIC F                                 │
│ • Content Integrity: Name order wrong → AUTOMATIC F                              │
│ • Content Integrity: Sequel continuity violation → AUTOMATIC F                   │
│ • Prose Quality: >5 critical AI-isms → GRADE CAP AT C                            │
│ • Gap Preservation: <75% rate → AUTOMATIC F                                      │
│ • Gap Preservation: Critical genre trait missing → GRADE CAP AT C                │
│ • Gap Preservation: Digital trauma/PTSD misrepresented → MANUAL REVIEW REQUIRED  │
└───────── • Prose Quality: >5 critical AI-isms → GRADE CAP AT C                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Final Report Template

```markdown
# FINAL AUDIT REPORT

## Volume Information
- **Volume ID:** {volume_id}
- **Title (JP):** {jp_title}
- **Title (EN):** {en_title}
- **Chapters:** {chapter_count}
- **Total Words:** {word_count}
- **Audit Date:** {timestamp}

---

## OVERALL VERDICT

### Grade: {grade}
### Status: {PUBLISH_READY | MINOR_FIXES | REVISION_NEEDED | BLOCKED}

---

## SUBAGENT RESULTS SUMMARY

### 1. Content Fidelity ✅ PASS
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Line Variance | 0.28% | <5% | ✅ |
| Content Deviation | 0.59% | <5% | ✅ |
| Missing Content | 2 units | 0 | ⚠️ |
| Truncations | 1 | 0 | ⚠️ |
| Censorship | 0 | 0 | ✅ |

**Verdict:** PASS (0.59% deviation within acceptable range)

### 2. Content Integrity ✅ PASS WITH WARNINGS
| Metric | Value | Status |
|--------|-------|--------|
| Name Consistency | 99.2% | ✅ |
| Genre Traits | PASS | ✅ |

**Warnings:** 3 auto-fixable formatting issues
**Verdict:** PASS (auto-fix available)

### 3. Prose Quality ✅ PASS
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| AI-ism Density | 0.27/1k | <0.5/1k | ✅ |
| Contraction Rate | 94.5% | >90% | ✅ |
| Victorian Patterns | 1 | 0 | ⚠️ |
| Transcreation | 82% | >80% | ✅ |
| Prose Score | 91.2 | >85 | ✅ |

**Improvements Available:** 8 transcreation opportunities
**Verdict:** PASS (high quality)

### 4. Gap Preservation ⚠️ GOOD (IMPROVEMENTS NEEDED)
| Gap Type | Detected | Preserved | Rate | Status |
|----------|----------|-----------|------|--------|
| Gap A (Emotion+Action) | 45 | 41 | 91.1% | ✅ GOOD |
| Gap B (Ruby Text) | 38 | 30%)  →  28.5
Integrity: 92/100 (weight: 25%)  →  23.0
Prose:     91/100 (weight: 25%)  →  22.75
Gaps:      87/100 (weight: 20%)  →  17.4
─────────────────────────────────────────
TOTAL:                              91.65/100
```

### FINAL GRADE: A- (Lowered from A due to Gap C critical issues)g | EXCELLENT | 0 |
| Idol Culture | EXCELLENT | 0 |
| Psychological Depth | ⚠️ NEEDS WORK | 3 critical |

**Critical Issues:**
- Digital trauma (phone anxiety) severely under-preserved (33.3%)
- Depression protocol tone shifts missed (50%)

**Verdict:** GOOD overall but critical psychological elements need attention |
| Prose Score | 91.2 | >85 | ✅ |
11 items - PRIORITY ORDER)

**CRITICAL (Must Fix):**
1. [GAP-C-002] Ch04:234 - Phone anxiety scene MISSING trauma framing (PTSD trigger)
2. [GAP-C-003] Ch07:89 - Depression protocol tone NOT applied (too flowery)

**HIGH PRIORITY:**
3. [GAP-A-002] Ch03:89 - Truncated emotion+action (glass chattering detail lost)
4. [GAP-C-001] Ch04:167 - Kaguya manipulation subtext partially missed
5. [PRO-TRC-001] Ch01:78 - Consider "Sure enough" instead of "As expected"
6. [PRO-TRC-002] Ch03:156 - Consider "That's Maria for you" instead of "As expected of Maria"

**MEDIUM PRIORITY:**
7. [GAP-A-003] Ch04:231 - Visual gag (wink) needs performative framing
⚠️ **CONDITIONAL APPROVAL - MANUAL REVIEW REQUIRED**

This volume meets most quality standards but has critical gap preservation issues:
- Content fidelity: 99.41% (excellent) ✅
- Structural integrity: 97.96% (auto-fixes available) ✅
- Prose quality: 91.2/100 (A grade) ✅
- Gap preservation: 90.6% overall (good) BUT:
  - ❌ Digital trauma scenes critically under-preserved (33.3%)
  - ❌ Depression protocol tone shifts missed (50%)
  
**REQUIRED ACTIONS:**
1. **Manual review** of chapters 4, 7-8 for psychological depth
2. **Rewrite** phone anxiety scene (Ch04:234) with PTSD framing
3. **Apply** depression protocol tone to chapter 7-8
4. **Enhance** Kaguya manipulation subtext where missed

**After fixes applied:** Re-run Gap Preservation Audit → Expected upgrade to A/A+

**Current Status:** Ready for publication with improvements, OR publish as-is with known psychological depth limitations
Integrity: 92/100 (weight: 30%)  →  27.6  
Prose:     91/100 (weight: 30%)  →  27.3
─────────────────────────────────────────
TOTAL:                              92.9/100
```

### FINAL GRADE: A

---

## ACTION ITEMS

### Auto-Fixable (3 items)
1. [INT-FMT-001] Chapter 03, Line 156: Replace `--` with `—`
2. [INT-FMT-002] Chapter 05, Line 89: Replace `--` with `—`
3. [INT-FMT-003] Chapter 07, Line 234: Replace `--` with `—`

### Manual Review Recommended (8 items)
1. [PRO-TRC-001] Ch01:78 - Consider "Sure enough" instead of "As expected"
2. [PRO-TRC-002] Ch03:156 - Consider "That's Maria for you" instead of "As expected of Maria"
...

### No Action Required
- Content fidelity verified
- All character names correct
- All illustrations properly placed

---

## PUBLICATION READINESS

✅ **APPROVED FOR PUBLICATION**

This volume meets all quality standards:
- Content fidelity: 99.41% (excellent)
- Structural integrity: 97.96% (auto-fixes available)
- Prose quality: 91.2/100 (A grade)

**Recommended:** Apply auto-fixes before final export.

---

## DETAILED REPORTS

- [fidelity_audit_report.json](./audits/fidelity_audit_report.json)
- [integrity_audit_report.json](./audits/integrity_audit_report.json)
- [prose_audit_report.json](./audits/prose_audit_report.json)
```

### Summary JSON Schema: `audit_summary.json`

```json
{
  "volume_id": "05df",
  "audit_timestamp": "2026-01-31T14:45:00Z",
  "auditor_version": "2.0",
  
  "overall": {
    "grade": "A",
    "score": 92.9,
    "status": "PUBLISH_READY",
    "blocking_issues": 0
  },
  
  "subagent_results": {
    "fidelity": {
      "grade": "A",
      "score": 95,
      "deviation_percent": 0.59,
      "status": "PASS"
    },
    "integrity": {
      "grade": "A",
      "score": 92,
      "pass_rate": 97.96,
      "status": "PASS_WITH_WARNINGS",
      "auto_fixable": 3
    },30,
    "integrity": 0.25,
    "prose": 0.25,
    "gaps": 0.2A",
      "score": 91.2,
      "ai_ism_density": 0.27,
      "contraction_rate": 94.5,
      "status": "PASS"
    }
  },
  ,
    "gap_preservation_min": 85,
    "gap_preservation_critical": 75,
    "gap_c_trauma_min": 80
  },
  "auto_fix_enabled": true,
  "sequel_mode": false,
  "gap_analysis_enabled": true,
  "genre_validation_enabled": tru8,
    "blocking": 0
  },
  
  "publication_verdict": {
    1 | 2026-02-01 | Added Subagent 4 (Gap Preservation), genre/series trait validation, psychological depth detection |
| 2."approved": true,
    "conditions": ["Apply auto-fixes"],
    "recommendation": "Ready for Phase 4 EPUB build"
  }
}
```

---

## EXECUTION WORKFLOW

```bash
# Run full audit pipeline
python audit_pipeline.py --volume 05df

# Or run individual subagents
python -m auditors.fidelity --volume 05df --output audits/
python -m auditors.integrity --volume 05df --output audits/
python -m auditors.prose --volume 05df --output audits/

# Generate final report
python -m auditors.final --volume 05df --input audits/ --output FINAL_AUDIT_REPORT.md
```

---

## CONFIGURATION

### Weights (adjustable in config/audit_config.json)

```json
{
  "grading_weights": {
    "fidelity": 0.40,
    "integrity": 0.30,
    "prose": 0.30
  },
  "thresholds": {
    "fidelity_deviation_fail": 10,
    "fidelity_deviation_critical": 15,
    "integrity_pass_rate_min": 90,
    "prose_score_min": 80,
    "ai_ism_density_max": 1.0,
    "contraction_rate_min": 80
  },
  "auto_fix_enabled": true,
  "sequel_mode": false
}
```

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-01-31 | Split into 3 subagents + final aggregator |
| 1.0 | 2026-01-15 | Initial monolithic audit agent |
