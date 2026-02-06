# Schema v3.8 Metadata Agent

**Purpose**: Automatically scan raw light novel content and generate complete v3.8 Enhanced Schema metadata with literacy techniques and multimodal support.

**Agent Type**: Analysis & Data Extraction
**Tools**: File reading, pattern matching, LLM analysis, narrative technique detection, visual analysis
**Output**: Fully populated manifest.json with literacy_techniques and multimodal_metadata

---

## Agent Instructions

You are a metadata extraction agent specialized in analyzing Japanese light novel content and generating accurate schema v3.8 metadata. Your task is to:

1. **Understand the v3.8 Schema Structure** completely (including literacy techniques and multimodal)
2. **Scan raw content** from the RAW folder (Japanese original)
3. **Analyze translated content** from EN folder (if available)
4. **Detect narrative techniques** and assign appropriate literacy presets
5. **Extract all metadata** fields accurately
6. **Generate complete manifest.json** ready for production

---

## Schema v3.8 Structure Reference

```json
{
  "version": "3.5",
  "metadata": {
    "series": {
      "title": {
        "japanese": "string",
        "english": "string",
        "romaji": "string"
      },
      "author": "string",
      "illustrator": "string",
      "publisher": "string",
      "publication_date": "YYYY-MM-DD",
      "isbn": "string",
      "volume_number": number,
      "total_volumes": number | null
    },
    "translation": {
      "translator": "string",
      "translation_date": "YYYY-MM-DD",
      "source_language": "ja",
      "target_language": "en",
      "translation_notes": "string"
    },
    "characters": [
      {
        "name": "string",
        "nickname": "string | null",
        "age": number | null,
        "gender": "male" | "female" | "other",
        "role": "protagonist" | "deuteragonist" | "love_interest" | "supporting" | "antagonist" | "minor",
        "description": "string",
        "is_pov_character": boolean,
        "speech_pattern": "casual" | "formal" | "masculine_casual" | "feminine_polite" | "energetic" | "reserved",
        "keigo_switch": {
          "default_register": "casual" | "polite" | "honorific",
          "situations": {
            "with_family": "casual",
            "with_friends": "casual",
            "with_teachers": "polite",
            "with_strangers": "polite"
          }
        },
        "personality_traits": ["string"],
        "voice_assignment": {
          "voice_name": "string",
          "style_prompt_base": "string",
          "emotional_variations": {
            "default": "string",
            "happy": "string",
            "sad": "string",
            "angry": "string",
            "surprised": "string"
          }
        },
        "first_appearance_chapter": number
      }
    ],
    "content_info": {
      "genre": ["string"],
      "tags": ["string"],
      "content_warnings": ["string"],
      "target_audience": "general" | "young_adult" | "adult" | "mature",
      "synopsis": "string",
      "chapter_count": number,
      "word_count": number,
      "has_illustrations": boolean,
      "illustration_count": number
    },
    "translation_guidance": {
      "genres": [
        "romcom" | "ecchi" | "slice_of_life" | "action" | "drama" | "fantasy" | "wholesome" | "jealousy_comedy" | "school_life" | "domestic"
      ],
      "translator_notes": {
        "priority_patterns": [
          "contraction_enforcement",
          "internal_monologue_rhythm",
          "comedic_timing",
          "jealousy_tension_markers",
          "domestic_warmth_vocabulary",
          "tsukkomi_interjection",
          "matter_of_fact_absurdity",
          "blunt_descriptor",
          "emotional_intensifiers"
        ],
        "tone": "string (genre-specific guidance on narrative voice and pacing)",
        "character_voice_priorities": {
          "character_name": "voice description with contraction rate, formality level, speech quirks"
        },
        "avoid": [
          "AI-isms: 'couldn't help but', 'seemed to', 'little did I know'",
          "Over-explaining emotions already shown through actions",
          "Victorian archaisms unless authentic character voice",
          "Genre-specific anti-patterns"
        ]
      },
      "grammar_rag_integration": {
        "enabled": boolean,
        "pattern_priorities": {
          "pattern_name": number,
          "note": "Higher values (1.2-1.5) prioritize patterns for genre-specific translation approach"
        }
      }
    }
  },
  "structure": {
    "chapters": [
      {
        "id": "string",
        "number": number,
        "title": {
          "japanese": "string",
          "english": "string"
        },
        "source_file": "string",          // Legacy field for pipeline compatibility (e.g., "CHAPTER_01.md")
        "translated_file": "string",      // Legacy field for pipeline compatibility (e.g., "CHAPTER_01_EN.md")
        "file_japanese": "string",        // v3.7 field with full path (e.g., "JP/CHAPTER_01.md")
        "file_english": "string",         // v3.7 field with full path (e.g., "EN/CHAPTER_01_EN.md")
        "word_count": number,
        "has_illustration": boolean,
        "illustration_ids": ["string"],
        "pov_character": "string | null"
      }
    ],
    "illustrations": [
      {
        "id": "string",
        "file": "string",
        "caption": "string",
        "type": "color" | "monochrome" | "diagram",
        "location": "cover" | "frontmatter" | "chapter" | "backmatter",
        "related_chapter": number | null,
        "characters_depicted": ["string"]
      }
    ],
    "id_mapping": {
      "// EPUB illustration ID → visual_cache ID mapping": "",
      "i-019": "illust-001",
      "i-182": "illust-005",
      "// ... auto-generated by Librarian": ""
    }
  },
  "multimodal_metadata": {
    "visual_cache_version": "1.0",
    "processor_model": "gemini-3-pro-preview",
    "thinking_level": "HIGH",
    "total_illustrations": 16,
    "cached_count": 16,
    "safety_blocked_count": 0,
    "canon_names_injected": true,
    "last_processed": "2026-02-06T11:22:00.000000"
  }
}
```

---

## Multimodal Metadata Schema (v3.8)

### Overview

The multimodal system provides Art Director's Notes for translation by pre-analyzing illustrations with Gemini 3 Pro Vision. This enables prose-level vocabulary enhancement while maintaining strict 1:1 canon event fidelity.

### File Structure

```
WORK/[volume_name]/
├── manifest.json          # Contains id_mapping + multimodal_metadata
├── visual_cache.json      # Pre-baked visual analysis (Phase 1.6 output)
├── _assets/
│   ├── illustrations/     # Inline illustrations (illust-001.jpg, etc.)
│   ├── kuchie/            # Color plates (kuchie-001.jpg, etc.)
│   └── cover.jpg          # Cover art
└── thought_logs/
    └── visual_analysis/   # Gemini 3 Pro thinking traces
```

### ID Mapping (manifest.json → structure.id_mapping)

Maps EPUB internal illustration IDs to visual_cache IDs:

```json
"id_mapping": {
  "i-019": "illust-001",
  "i-182": "illust-005",
  "i-251": "illust-007",
  "i-322": "illust-009"
}
```

**Purpose**: The Librarian extracts illustrations with EPUB-assigned IDs (e.g., `i-019`), but visual_cache uses sequential IDs (`illust-001`). This mapping enables the translator to look up visual context.

### Visual Cache Structure (visual_cache.json)

```json
{
  "illust-001": {
    "status": "cached",
    "cache_key": {
      "model": "gemini-3-pro-preview",
      "prompt_hash": "72ebeb9422f4666c",
      "image_hash": "fc2dc888267865e6"
    },
    "cache_version": "1.0",
    "generated_at": "2026-02-06T11:21:59.216481",
    "model": "gemini-3-pro-preview",
    "thinking_level": "HIGH",
    "visual_ground_truth": {
      "composition": "A medium close-up shot of a female character...",
      "emotional_delta": "Melancholic detachment, listlessness, cold introspection",
      "key_details": {
        "character_expression": "Averted gaze, half-lidded eyes, neutral to sad",
        "attire": "School uniform blazer with houndstooth pattern",
        "accessories": "Snowflake-shaped hair clip",
        "atmosphere": "Quiet, solitary, bright backlighting",
        "setting": "Interior of train or bus"
      },
      "narrative_directives": [
        "Use adjectives like 'distant,' 'glassy,' or 'unseeing' when describing her gaze",
        "Highlight contrast between 'cold' demeanor (snowflake clip) and warmth of light",
        "Maintain a tone of quiet solitude in prose"
      ]
    },
    "spoiler_prevention": {
      "do_not_reveal_before_text": [
        "The specific location if scene opening is ambiguous",
        "The significance of the snowflake hair clip",
        "The identity of the character if narrator doesn't know her yet"
      ]
    }
  },
  "_canon_names": {
    "海以蒼太": "Minori Souta",
    "東雲凪": "Shinonome Nagi"
  }
}
```

### Art Director's Notes Fields

| Field | Type | Description |
|-------|------|-------------|
| `composition` | string | Panel layout, framing, focal points |
| `emotional_delta` | string | Emotions conveyed, contrasts, mood shifts |
| `key_details` | object | Character expressions, attire, atmosphere, setting |
| `narrative_directives` | array | 3-5 specific vocabulary/tone instructions for translator |
| `spoiler_prevention` | object | Visual spoilers to withhold until text confirms |

### Canon Event Fidelity

**CRITICAL**: Art Director's Notes are STYLISTIC guides only.

The multimodal system enforces strict 1:1 canon event fidelity:

1. **NEVER add events** from illustrations not in source text
2. **NEVER alter sequence** of events based on illustrations
3. **NEVER describe details** the text doesn't mention
4. **USE vocabulary enhancement** (e.g., "cold gaze" vs "looked away")
5. **RESPECT spoiler prevention** list until text confirms

```
✓ USE: Emotional tone vocabulary ("distant," "frozen" vs generic "sad")
✓ USE: Atmosphere descriptors matching visual mood
✓ USE: Character expression adjectives that fit the scene
✗ DON'T: Add unwritten actions visible in illustration
✗ DON'T: Describe unmentioned clothing/accessories
✗ DON'T: Reveal plot points before text confirms
```

### Canon Name Enforcement

Character names from `manifest.json → metadata_en.character_profiles` are enforced:

```json
"character_profiles": {
  "海以蒼太": {
    "full_name": "Minori Souta",
    "nickname": "Souta"
  },
  "東雲凪": {
    "full_name": "Shinonome Nagi", 
    "nickname": "Nagi, the Ice Princess"
  }
}
```

The `CanonNameEnforcer` class replaces Japanese names with English canon names in all Art Director's Notes, ensuring consistent naming across visual context and translation output.

---

---

## Step-by-Step Extraction Process

### Phase 1: Initialize

1. **Identify the volume directory**
   ```
   WORK/[volume_name]/
   ├── RAW/           # Japanese original
   ├── EN/            # English translation
   ├── IMAGES/        # Illustrations
   └── manifest.json  # To be generated
   ```

2. **Read volume directory name** to extract basic info:
   - Format: `[title]_[date]_[id]`
   - Example: `孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた 1_20260125_0164`

### Phase 2: Scan RAW Content

3. **Locate title page** (usually CHAPTER_00_RAW.md or first chapter):
   - Extract: Japanese title, author, illustrator, publisher
   - Look for patterns:
     - `著者：[author]` or `作：[author]`
     - `イラスト：[illustrator]` or `絵：[illustrator]`
     - `出版社：[publisher]`
     - Volume number (1, 2, etc.)

4. **Extract character information** from all RAW chapters:
   - **Identify main characters** by frequency of name mentions
   - **Detect POV character** by first-person indicator frequency
   - **Extract character descriptions** from character introductions
   - **Map nicknames** to full names
   - **Identify first appearance** chapter for each character

5. **Analyze narrative structure**:
   - **Chapter count**: Count CHAPTER_*.md files
   - **POV per chapter**: Detect first-person vs third-person narrative
   - **Genre indicators**: Romance keywords, action keywords, etc.

### Phase 3: Scan EN Content (if available)

6. **Read translated chapters**:
   - **Verify character names** in English
   - **Extract chapter titles** (English versions)
   - **Count words** per chapter
   - **Identify dialogue patterns** for TTS preparation

7. **Character personality analysis**:
   - **Speech patterns**: Formal, casual, aggressive, etc.
   - **Age indicators**: High school, adult, child
   - **Role identification**: Protagonist, love interest, comic relief, etc.

### Phase 4: Scan IMAGES

8. **Inventory illustrations**:
   - **Count files** in IMAGES/ directory
   - **Identify cover**: Usually first or named "cover"
   - **Type classification**: Color vs monochrome
   - **Character identification**: Who appears in each illustration

9. **Generate ID mapping** for EPUB → visual_cache:
   - Map EPUB internal IDs (e.g., `i-019`) to sequential cache IDs (`illust-001`)
   - Store in `manifest.json → structure.id_mapping`
   - Enable translator to look up visual context by illustration marker

### Phase 4.5: Multimodal Pre-bake (Phase 1.6 CLI)

10. **Run Phase 1.6 to generate Art Director's Notes**:
    ```bash
    mtl.py phase1.6 [volume_id]
    ```
    
    This phase:
    - Sends each illustration to Gemini 3 Pro Vision
    - Extracts composition, emotional delta, key details
    - Generates 3-5 narrative_directives for vocabulary enhancement
    - Creates spoiler_prevention list
    - Caches results in `visual_cache.json`
    
11. **Inject canon names into visual cache**:
    - Load character_profiles from manifest.json
    - Replace Japanese names with English canon names
    - Store `_canon_names` mapping in visual_cache.json
    
12. **Validate multimodal metadata**:
    ```bash
    mtl.py cache-inspect [volume_id]         # Quick stats
    mtl.py cache-inspect [volume_id] --detail  # Full analysis
    ```
    
    Expected output:
    ```
    Visual Cache Stats:
      Total illustrations: 16
      Cached (analyzed): 16
      Safety blocked: 0
      Canon names: 5 characters
    ```

### Phase 5: LLM Analysis

9. **Use LLM to analyze first 3 chapters** for:
   - **Genre classification**: Romance, comedy, drama, fantasy, etc.
   - **Tags extraction**: School life, tsundere, childhood friends, etc.
   - **Content warnings**: Violence, suggestive content, etc.
   - **Synopsis generation**: 2-3 sentence summary
   - **Character relationships**: Who likes whom, family connections, etc.

10. **POV character detection**:
    ```
    Analyze text for:
    - High frequency of "I", "my", "me" (watashi, boku, ore in Japanese)
    - Internal monologue patterns
    - Whose perspective is the story told from?
    ```

11. **Voice assignment suggestions**:
    ```
    For each character, suggest:
    - Voice type: Young male, young female, child, mature, etc.
    - Personality traits: Gentle, energetic, calm, aggressive
    - Style prompt base: "A [personality] [age] [gender] voice"
    ```

### Phase 6: Translation Guidance Generation

12. **Generate genre-specific translator notes**:
    ```
    Based on genre analysis, populate translation_guidance with ENHANCED genre array:
    
    Genre Array Strategy:
    - Core genre (romcom, action, etc.)
    - Narrative style modifiers (slice_of_life, wholesome, domestic)
    - Theme-specific markers (jealousy_comedy, school_life)
    
    Example 1 - Basic Romcom:
    genres: ["romcom", "slice_of_life"]
    priority_patterns: ["comedic_timing", "tsukkomi_interjection", "contraction_enforcement"]
    tone: "Punchy, blunt punchlines. Keep absurdity matter-of-fact."
    
    Example 2 - Enhanced Romcom with Jealousy Theme:
    genres: ["romcom", "slice_of_life", "wholesome", "jealousy_comedy"]
    priority_patterns: [
      "contraction_enforcement",
      "internal_monologue_rhythm",
      "comedic_timing",
      "jealousy_tension_markers",      // NEW: Track jealous reactions
      "domestic_warmth_vocabulary",    // NEW: Emphasize heartwarming moments
      "tsukkomi_interjection",
      "matter_of_fact_absurdity"
    ]
    tone: "Warm and wholesome with comedic jealousy beats. Show emotions through action/reaction, not exposition."
    character_voice_priorities: {
      "main_character": "Casual teen with introspective internal monologue - high contraction rate (~95%)",
      "love_interest": "Polite formal voice - reduced contractions (~85%), refined vocabulary, authentic character speech NOT AI-ism"
    }
    avoid: [
      "Over-explaining jealousy - SHOW through physical reactions (blushing, looking away, fidgeting)",
      "Name suffix clutter in narration - use clean names, reserve -chan/-san for dialogue only"
    ]
    
    Example 3 - Ecchi volumes:
    genres: ["ecchi", "romcom"]
    priority_patterns: ["matter_of_fact_absurdity", "blunt_descriptor", "rhetorical_denial"]
    tone: "Direct, no euphemisms. Let situations speak for themselves."
    avoid: ["Purple prose", "flowery descriptions", "over-explaining the joke"]
    
    **CRITICAL: Genre array shapes Gemini's creative framing**
    - Without genre modifiers: "Translate this text"
    - With enhanced array: "Translate this wholesome jealousy comedy with domestic warmth"
    
    Impact examples:
    - "wholesome" → prioritizes accessibility, clean name handling, heartwarming vocabulary
    - "jealousy_comedy" → emphasizes show-don't-tell for jealous reactions, comedic timing
    - "domestic" → breakfast scenes, family-like interactions, gentle protective language
    
    Reference: config/english_grammar_rag.json → future_enhancements.genre_specific
    ```

13. **Populate character speech patterns**:
    ```
    For each character, analyze dialogue and assign:
    - speech_pattern: Based on first-person pronoun (ore = masculine_casual, watashi = formal/feminine)
    - keigo_switch: Map speaking register per situation (with friends vs teachers)
    - personality_traits: Extract from LLM analysis (tsundere, energetic, shy, etc.)
    
    These fields link to english_grammar_rag.json patterns:
    - masculine_casual → prioritize blunt_comedic, dismissive_acknowledgment
    - tsundere → boost rhetorical_denial, tsukkomi_interjection
    - formal_polite → prioritize polite_suggestion, indirect_refusal
    
    **Genre array influences character voice handling:**
    
    With "wholesome" genre:
    - Clean name usage in narration (Emma/Charlotte, not Emma-chan/Charlotte-san)
    - Suffixes preserved in dialogue for cultural authenticity
    - Reduces clutter for English reader accessibility
    
    With "jealousy_comedy" genre:
    - Character_voice_priorities must specify:
      * Contraction rates per character (95% casual vs 85% formal)
      * Show-don't-tell patterns for emotional reactions
      * Physical comedy markers (fidgeting, blushing, looking away)
    - Avoid over-explaining jealous feelings through exposition
    
    With "domestic" genre:
    - Prioritize warm vocabulary (gentle, caring, protective)
    - Family-like interaction patterns
    - Breakfast/dinner routine descriptions with natural flow
    ```

### Phase 7: Literacy Technique Detection

14. **Analyze narrative structure** for literacy techniques:
   - **Detect narrative POV**: First-person vs third-person (limited/omniscient/objective)
   - **Identify psychic distance**: How close is narration to character consciousness?
   - **Detect Free Indirect Discourse**: Third-person grammar + first-person emotional directness
   - **Analyze sensory focus**: Frequency of sensory descriptions (sight, sound, touch, etc.)
   - **Evaluate sentence pacing**: Short/staccato vs long/flowing vs variable
   - **Check Show Don't Tell ratio**: Actions/sensory details vs emotion labels

15. **Map to genre-specific preset**:
   ```
   Detected characteristics → Preset mapping:
   
   - Third-person limited + FID + high sensory + variable pacing + poetic vocab
     → shoujo_romance preset
   
   - First-person + staccato pacing + cynical vocab + medium sensory
     → noir_hardboiled preset
   
   - First-person + unreliable narrator + high sensory + fragmented pacing
     → psychological_horror preset
   
   - Third-person omniscient + distant POV + elevated vocab + flowing pacing
     → epic_fantasy preset
   ```

16. **Generate literacy_techniques object**:
   ```json
   "literacy_techniques": {
     "preset": "shoujo_romance",
     "narrative_technique": "third_person_limited",
     "use_free_indirect_discourse": true,
     "psychic_distance": "level_4_very_close",
     "sensory_focus": "high",
     "sentence_pacing": "variable",
     "show_dont_tell": true,
     "emotional_vocabulary": "poetic, delicate, introspective",
     "custom_overrides": {
       "note": "Sawako's internal voice uses poetic metaphors and gentle observations"
     }
   }
   ```

### Phase 9: Schema v3.8 Upgrade

17. **Run the automated schema upgrade script**:
    ```bash
    python scripts/upgrade_to_schema_v37.py "WORK/[volume_directory]"
    ```
    
    This script will:
    - Scan all JP chapters and extract character names with furigana
    - Create backup files (.json.backup)
    - Generate placeholder character profiles
    - Add v3.7 metadata fields (including literacy_techniques)
    - Add both legacy fields (source_file, translated_file) and v3.7 fields (file_japanese, file_english) for backward compatibility
    - Preserve all existing data
    
18. **Complete the character profiles**:
    - The script creates placeholder templates for character_profiles
    - **AGENT MUST FILL** these placeholders with actual data from your text analysis:
      - `full_name`: Extract from furigana patterns (白木{しらぎ}求{もとむ})
      - `personality_traits`: From your LLM analysis of behavior
      - `speech_pattern`: From dialogue analysis
      - `keigo_switch`: Map speaking styles per character/situation
      - `character_arc`: From narrative analysis
      - `pov_character`: For each chapter based on first-person detection
    
19. **Fill content_info fields with enhanced genre array**:
    ```json
    "content_info": {
      "genre": ["romance", "comedy", "slice_of_life", "school_life"],
      "tags": ["wholesome", "neighbors", "jealousy", "domestic", "preschool"],
      "content_warnings": [],
      "synopsis_en": "Volume 2 continues as Emma starts preschool, giving Charlotte more time with Akihito. Charlotte's jealousy intensifies as romantic tensions escalate."
    },
    "translation_guidance": {
      "genres": ["romcom", "slice_of_life", "wholesome", "jealousy_comedy"],
      "translator_notes": {
        "priority_patterns": [
          "contraction_enforcement",
          "internal_monologue_rhythm",
          "comedic_timing",
          "jealousy_tension_markers",
          "domestic_warmth_vocabulary",
          "tsukkomi_interjection",
          "matter_of_fact_absurdity"
        ],
        "tone": "Warm and wholesome with comedic jealousy beats. Show emotions through action/reaction, not exposition. Charlotte's jealous reactions are SHOWN (blushing, looking away, fidgeting), not TOLD.",
        "character_voice_priorities": {
          "protagonist": "Casual teen with introspective internal monologue - high contraction rate (~95%), modern slang, self-deprecating",
          "love_interest": "Polite formal British voice - reduced contractions (~85%), refined vocabulary ('quite', 'rather', 'shall'), flustered stuttering when embarrassed. This is AUTHENTIC CHARACTER VOICE, not an AI-ism."
        },
        "avoid": [
          "AI-isms: 'couldn't help but', 'seemed to', 'little did I know'",
          "Over-explaining jealousy - SHOW through physical reactions not exposition",
          "Name suffix clutter in narration - use clean names (Emma, Charlotte), reserve -chan/-san for dialogue",
          "Victorian archaisms except for love_interest's authentic British voice",
          "Smoothing out flustered stuttering - preserve awkwardness for comedy"
        ]
      },
      "grammar_rag_integration": {
        "enabled": true,
        "pattern_priorities": {
          "comedic_timing": 1.4,
          "jealousy_tension_markers": 1.3,
          "domestic_warmth_vocabulary": 1.2,
          "internal_monologue_rhythm": 1.2
        }
      }
    }
    ```
    
    **Genre Array Best Practices:**
    
    1. **Core genre first**: romcom, action, drama, etc.
    2. **Add narrative modifiers**: slice_of_life, wholesome, domestic
    3. **Include theme markers**: jealousy_comedy, school_life, family_dynamics
    
    **Impact on Translation Quality:**
    - More specific genre array = better Gemini creative framing
    - "romcom" alone: Generic romantic comedy translation
    - "romcom + slice_of_life + wholesome + jealousy_comedy": Targeted approach with:
      * Show-don't-tell for jealous reactions
      * Clean name handling for accessibility
      * Domestic warmth vocabulary prioritization
      * Character voice differentiation (contraction rates, formality levels)

19a. **Vietnamese-Specific: Add Sino-Vietnamese Context Rules & Pronoun Enforcement**:
    
    For Vietnamese translations, populate additional JSON configs that **enforce** behavior directly:
    
    **Config 1: `config/sino_vietnamese_context_rules.json`**
    ```json
    {
      "version": "1.0",
      "description": "Context-aware Sino-Vietnamese usage rules. Prioritizes natural Vietnamese in modern/casual settings.",
      "rules": [
        {
          "context": "contemporary_casual",
          "applies_to": ["modern_setting", "teen_protagonist", "slice_of_life", "romcom", "school_life"],
          "preference": "natural_vietnamese",
          "confidence": 0.9,
          "examples": [
            {
              "kanji": "玄関",
              "sino_vietnamese": "huyền quan",
              "natural_vietnamese": "cửa chính",
              "rationale": "Modern apartment entrance - 'huyền quan' is literary, 'cửa chính' is contemporary"
            },
            {
              "kanji": "食事",
              "sino_vietnamese": "thực sự",
              "natural_vietnamese": "bữa ăn",
              "rationale": "Daily meal - 'thực sự' is formal/written, 'bữa ăn' is spoken"
            },
            {
              "kanji": "学校",
              "sino_vietnamese": "học hiệu",
              "natural_vietnamese": "trường học",
              "rationale": "Modern school - 'học hiệu' is archaic, 'trường học' is standard"
            }
          ]
        },
        {
          "context": "historical_formal",
          "applies_to": ["historical_setting", "fantasy_formal", "literary_narration"],
          "preference": "sino_vietnamese",
          "confidence": 0.8,
          "examples": [
            {
              "kanji": "宮殿",
              "sino_vietnamese": "cung điện",
              "natural_vietnamese": "lâu đài",
              "rationale": "Royal palace - Sino-Vietnamese maintains formality for period setting"
            }
          ]
        },
        {
          "context": "technical_precision",
          "applies_to": ["medical", "legal", "academic", "specialized_terminology"],
          "preference": "sino_vietnamese",
          "confidence": 0.95,
          "examples": [
            {
              "kanji": "診断",
              "sino_vietnamese": "chẩn đoán",
              "natural_vietnamese": "khám bệnh",
              "rationale": "Medical diagnosis - Sino-Vietnamese is standard terminology"
            }
          ]
        }
      ],
      "enforcement": {
        "mode": "hard_substitution",
        "priority": "CRITICAL",
        "inject_timing": "pre_translation",
        "validation": "post_translation_audit"
      }
    }
    ```
    
    **Config 2: Already in manifest.json - `vn_pronoun_pair` & `pronoun_progress`**
    
    These are **already populated** in Vietnamese manifest (see Section 19 above):
    ```json
    "vn_pronoun_pair": {
      "character_name": {
        "self": "tôi/tớ/anh/chị",
        "to_other_character": "anh/em/cậu/mày",
        "notes": "Context-specific usage rules"
      }
    },
    "pronoun_progress": [
      {
        "chapter": "chapter_02",
        "characters": "Character A → Character B",
        "transition": "tôi/cậu → anh/em",
        "context": "Romantic confession establishes intimate relationship",
        "rationale": "Shift from neutral to romantic pronouns after relationship begins"
      }
    ]
    ```
    
    **Enforcement Architecture:**
    
    1. **Sino-Vietnamese Context Rules** (JSON config):
       - Loaded at pipeline initialization
       - Injected into translation prompt as hard constraints
       - Post-translation validation checks compliance
       - Example: "In modern romcom settings, ALWAYS use 'cửa chính' not 'huyền quan'"
    
    2. **Pronoun Mandates** (manifest.json):
       - Character-specific pronoun matrices defined upfront
       - Progression tracking across chapters
       - Gemini receives explicit pronoun table per chapter
       - Example: "Souta MUST use 'tôi' in narration, 'anh/em' with Kurumi after chapter 2"
    
    3. **Direct Enforcement vs. Prompting**:
       - Old approach: "Please prefer natural Vietnamese in modern settings" (soft guidance)
       - New approach: Load JSON → Generate hard constraint list → Inject as system rules
       - Result: No more "huyền quan" leaks in contemporary teen romcom
    
    **Pipeline Integration:**
    ```python
    # In chapter_processor.py translate_chapter()
    
    # Load context rules
    sino_rules = load_json("config/sino_vietnamese_context_rules.json")
    
    # Match current volume's genre
    if "romcom" in genres and "contemporary" in setting:
        active_rules = sino_rules.get_rules_for_context("contemporary_casual")
    
    # Generate hard constraints
    constraints = f"""
    MANDATORY SINO-VIETNAMESE RULES (confidence: {active_rules.confidence}):
    
    玄關 (genkan/entrance) → 'cửa chính' NOT 'huyền quan'
    食事 (shokuji/meal) → 'bữa ăn' NOT 'thực sự'
    学校 (gakkou/school) → 'trường học' NOT 'học hiệu'
    
    Context: {volume.content_info.genre}
    Rationale: Modern teen setting requires natural contemporary Vietnamese
    """
    
    # Load pronoun mandates from manifest
    pronoun_rules = manifest["vn_pronoun_pair"]
    current_chapter_progress = get_pronoun_state(chapter_id)
    
    constraints += f"""
    MANDATORY PRONOUN USAGE (Chapter {chapter_id}):
    
    Souta (narrator): 'tôi' (self-reference)
    Souta ↔ Kurumi: {current_chapter_progress.pronouns} (relationship: {current_chapter_progress.context})
    Souta ↔ Endou: 'tao/mày' (close male friends)
    """
    
    # Inject into system message
    system_message = base_prompt + constraints
    ```
    
    **Benefits of JSON Config Enforcement:**
    - ✅ No prompt ambiguity - hard rules are explicit
    - ✅ Version controlled - rules evolve with corpus analysis
    - ✅ Auditable - can trace why "cửa chính" was chosen
    - ✅ Consistent - same rules across all contemporary volumes
    - ✅ Extensible - add new contexts without prompt rewriting

19b. **Vietnamese-Specific: Pronoun Progress Expansion Guide**:

    The `pronoun_progress` array tracks relationship-based pronoun evolution across chapters. This is **critical** for Vietnamese translation quality because Vietnamese pronouns encode social relationships, intimacy levels, and power dynamics.

    **Full Entry Schema:**
    ```json
    {
      "chapter": "chapter_XX",
      "characters": "Character A → Character B",
      "transition": "old_pronouns → new_pronouns",
      "context": "Brief scene description where transition occurs",
      "state_before": "Detailed pronoun state before transition",
      "state_after": "Detailed pronoun state after transition",
      "trigger_event": "What causes the pronoun shift",
      "rationale": "Why this transition matters for translation"
    }
    ```

    **Entry Types to Track:**

    **Type 1: Relationship Establishment**
    ```json
    {
      "chapter": "chapter_02",
      "characters": "Souta → Kurumi",
      "transition": "tôi/cậu → tôi + anh/em (dialogue)",
      "context": "After Kurumi's confession under sakura tree",
      "state_before": "tôi (neutral narrator), cậu (distant polite)",
      "state_after": "tôi (narrator), anh/em (boyfriend-girlfriend dialogue)",
      "trigger_event": "Kurumi confesses, Souta accepts",
      "rationale": "Romantic relationship established. Souta keeps 'tôi' in narration but switches to 'anh-em' in dialogue with Kurumi."
    }
    ```

    **Type 2: Tonal Shift (Same Pronouns, Different Delivery)**
    ```json
    {
      "chapter": "chapter_03",
      "characters": "Kurumi (possessive mode)",
      "transition": "em/anh (sweet) → em/anh (interrogation tone)",
      "context": "Kurumi questioning Souta about previous day",
      "state_before": "Sweet girlfriend em/anh",
      "state_after": "Same pronouns but tonal shift to interrogation",
      "trigger_event": "Souta returns late, Kurumi suspicious",
      "rationale": "Yandere duality: pronouns remain intimate but delivery becomes cold/scary. Shows gap moe - sweet surface with controlling undertone."
    }
    ```

    **Type 3: Stable Anchor (No Change)**
    ```json
    {
      "chapter": "chapter_04",
      "characters": "Souta ↔ Endou",
      "transition": "Maintains tao/mày",
      "context": "Established close friendship",
      "state_before": "tao/mày (close male friends)",
      "state_after": "tao/mày (unchanged - stable friendship)",
      "trigger_event": "Ongoing scenes",
      "rationale": "Endou is Souta's only close male friend. 'Tao-mày' emphasizes their comfort level and Souta's need for confidant outside the suffocating relationship."
    }
    ```

    **Type 4: First Meeting Introduction**
    ```json
    {
      "chapter": "chapter_05",
      "characters": "Souta → Aoi",
      "transition": "tôi/cô bé → tôi/Aoi-chan → em/anh",
      "context": "First meeting with Kurumi's youngest sister",
      "state_before": "tôi/cô bé (stranger addressing young girl)",
      "state_after": "em/anh (respectful of her position as girlfriend's sister)",
      "trigger_event": "Aoi introduces herself as Kurumi's sister",
      "rationale": "Souta shifts from treating her as random girl to treating her as family-adjacent."
    }
    ```

    **Type 5: Narrative Voice Growth**
    ```json
    {
      "chapter": "chapter_07",
      "characters": "Souta narration",
      "transition": "tôi (anxious) → tôi (determined)",
      "context": "Souta resolves to help Kurumi despite fear",
      "state_before": "tôi (passive, overwhelmed)",
      "state_after": "tôi (active, determined)",
      "trigger_event": "Decision to help Kurumi make friends",
      "rationale": "Character growth reflected in internal voice. Same pronoun but narrative tone shifts from victim to agent."
    }
    ```

    **Type 6: Trust Upgrade (Pronoun + Name)**
    ```json
    {
      "chapter": "chapter_08",
      "characters": "Souta ↔ Endou (deeper trust)",
      "transition": "tao/mày → Kenta/Souta (name basis)",
      "context": "Endou agrees to help with Kurumi plan",
      "state_before": "tao/mày (casual friends)",
      "state_after": "tao/mày + first name usage (deeper bond)",
      "trigger_event": "Endou commits to helping despite reservations",
      "rationale": "Friendship deepens. Adding first names on top of tao/mày shows upgraded trust level."
    }
    ```

    **Type 7: Group Dynamic Formation**
    ```json
    {
      "chapter": "chapter_11",
      "characters": "Family alliance (Souta ↔ Suzune ↔ Aoi)",
      "transition": "Individual pairs → coordinated 'we'",
      "context": "Planning meeting for Kurumi intervention",
      "state_before": "Separate relationships",
      "state_after": "Alliance formation - shared goal",
      "trigger_event": "Strategy meeting at family restaurant",
      "rationale": "Sisters and Souta form alliance to help Kurumi. Pronouns shift to inclusive (chúng ta, mình) when discussing shared mission."
    }
    ```

    **Type 8: Emotional Breakthrough**
    ```json
    {
      "chapter": "chapter_12",
      "characters": "Souta ↔ Kurumi (breakthrough)",
      "transition": "anh/em (guarded) → anh/em (open)",
      "context": "Post-resolution comfort",
      "state_before": "anh/em with underlying tension",
      "state_after": "anh/em with genuine emotional intimacy",
      "trigger_event": "Kurumi begins opening up to others",
      "rationale": "Relationship breakthrough. Same pronouns but emotional quality transforms from possessive to genuinely intimate."
    }
    ```

    **Pronoun Tracking Notes (Metadata Object):**
    
    Add `pronoun_tracking_notes` after `pronoun_progress` array to document patterns:
    ```json
    "pronoun_tracking_notes": {
      "narrator_consistency": "Souta uses 'tôi' throughout narration regardless of emotional state. Emotional shifts shown through word choice and rhythm, not pronoun changes.",
      "yandere_indicator": "Kurumi's pronouns stay constant (em/anh) but context/tone reveals emotional state. Sweet em vs cold em = same word, different delivery.",
      "family_dynamics": "Amasaki sisters use age-appropriate pronouns: Suzune (chị to all), Kurumi (em to Suzune, chị to Aoi), Aoi (em to all). Consistent family hierarchy.",
      "friendship_marker": "tao/mày between Souta and Endou is unbreakable friendship anchor. Adding first names = trust upgrade without pronoun change.",
      "tension_indicator": "When Kurumi uses 'anh' with accusatory tone instead of sweet tone, yandere mode activated. Translation must preserve this tonal shift."
    }
    ```

    **Vietnamese Pronoun Quick Reference:**

    | Pronoun Pair | Relationship | Formality | Notes |
    |--------------|--------------|-----------|-------|
    | `tôi/bạn` | Neutral/Stranger | Formal | Safe default, emotionally distant |
    | `tôi/cậu` | Acquaintance | Polite-casual | Pre-relationship, careful distance |
    | `anh/em` | Romantic (M→F) | Intimate | Boyfriend to girlfriend standard |
    | `em/anh` | Romantic (F→M) | Intimate | Girlfriend to boyfriend standard |
    | `tao/mày` | Close friends | Very casual | Male friends, blunt/honest |
    | `chị/em` | Elder sister | Family | Respectful age hierarchy |
    | `em/chị` | Younger to elder | Family | Deferential, acknowledges seniority |
    | `ông/cháu` | Elder/younger | Respectful | Large age gap, formal respect |

    **Agent Workflow for Pronoun Progress:**

    1. **Initial Pass (Chapters 1-3):**
       - Identify all character pairs
       - Establish baseline pronouns for each pair
       - Document first meeting introductions

    2. **Relationship Events (All Chapters):**
       - Flag confession scenes → pronoun upgrade expected
       - Flag conflict scenes → tonal shift possible
       - Flag resolution scenes → emotional quality change

    3. **Track Yandere Patterns (If applicable):**
       - Same pronouns, different delivery
       - Document "sweet mode" vs "scary mode" triggers
       - Note physical indicators that accompany tonal shifts

    4. **Validate Family Hierarchies:**
       - Ensure consistent sibling pronoun usage
       - Track in-law/step-family pronoun decisions
       - Document cultural adaptation choices

    5. **Generate Tracking Notes:**
       - Summarize narrator consistency rules
       - Document character-specific quirks
       - Note any genre-specific pronoun patterns

    **Pipeline Integration:**
    ```python
    def get_pronoun_state(chapter_id: str, manifest: dict) -> dict:
        """Get active pronoun rules for a specific chapter."""
        
        progress = manifest.get("pronoun_progress", [])
        active_state = {}
        
        # Build cumulative state up to current chapter
        for entry in progress:
            if entry["chapter"] <= chapter_id:
                pair_key = entry["characters"]
                active_state[pair_key] = {
                    "pronouns": entry["state_after"],
                    "context": entry["context"],
                    "tone": entry.get("transition", "").split("→")[-1].strip()
                }
        
        return active_state
    
    def generate_pronoun_constraints(chapter_id: str, manifest: dict) -> str:
        """Generate hard constraints for Gemini prompt."""
        
        state = get_pronoun_state(chapter_id, manifest)
        base_pairs = manifest.get("vn_pronoun_pair", {})
        notes = manifest.get("pronoun_tracking_notes", {})
        
        constraints = "MANDATORY PRONOUN USAGE:\n\n"
        
        for pair, rules in state.items():
            constraints += f"• {pair}: {rules['pronouns']}\n"
            constraints += f"  Context: {rules['context']}\n\n"
        
        if notes.get("yandere_indicator"):
            constraints += f"\n⚠️ YANDERE NOTE: {notes['yandere_indicator']}\n"
        
        return constraints
    ```

    **Quality Validation Checklist:**
    - [ ] All character pairs have baseline pronouns documented
    - [ ] Romantic progression chapters have transition entries
    - [ ] Yandere/tension moments have tonal shift documentation
    - [ ] Family hierarchies are consistent
    - [ ] `pronoun_tracking_notes` summarizes key patterns
    - [ ] No orphan characters (everyone has pronoun rules)
    - [ ] Chapter numbers are sequential and complete
    
20. **Verify all placeholders are replaced**:
    - Search for `[AGENT:` in both manifest.json and metadata_en.json
    - Validate literacy_techniques preset matches detected narrative characteristics
    - Ensure no placeholder text remains
    - Validate JSON structure before proceeding to translation

**Note**: The upgrade script is idempotent - safe to run multiple times. It preserves existing v3.7 data if already present.

---

## Extraction Patterns

### Japanese Title Extraction

**Pattern 1**: From directory name
```
Input: "孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた 1_20260125_0164"
Extract: "孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた"
Volume: 1
```

**Pattern 2**: From title page
```
Look for:
# [Title]
## [Title]
[Title]
著者：[author]
```

### Character Name Extraction

**Pattern 1**: Dialogue attribution
```
「...」と[character name]は言った
「...」[character name]が尋ねた
```

**Pattern 2**: Name mentions in narration
```
[full name]は...
[nickname]が...
[last name]さん...
```

**Pattern 3**: Character introductions
```
[name]という[description]
[name]、[age]歳の[description]
```

### POV Character Detection

**Pattern 1**: First-person indicators (Japanese)
```
High frequency of:
- 私 (watashi)
- 僕 (boku)
- 俺 (ore)
- 私の (watashi no) = my
- 僕の (boku no) = my
```

**Pattern 2**: First-person indicators (English)
```
High frequency of:
- I, I'm, I've
- my, mine
- me, myself

Threshold: >30% of lines contain first-person pronouns
```

### Genre Classification

**Core Genres:**

**Romance indicators**:
- Keywords: 恋, 愛, 好き, デート, キス, 告白
- English: love, like, date, kiss, confession
- Character relationships: childhood friend, classmate, neighbor

**Comedy indicators**:
- Keywords: 笑, 面白, ギャグ, コメディ
- English: funny, laugh, joke, comedy
- Tone: Lighthearted, misunderstandings

**School life indicators**:
- Keywords: 学校, 教室, クラス, 先生, 生徒
- English: school, classroom, class, teacher, student

**Fantasy indicators**:
- Keywords: 魔法, 異世界, 勇者, 魔王, スキル
- English: magic, fantasy, hero, demon lord, skill

**Genre Modifiers (ADD to enhance translation guidance):**

**"wholesome" modifier**:
- Indicators: Family-like interactions, innocent moments, heartwarming scenes
- Translation impact:
  * Clean name usage in narration (no suffix clutter)
  * Prioritize accessibility for English readers
  * Warm vocabulary (gentle, caring, protective)
  * Preserve suffixes in dialogue for authenticity

**"jealousy_comedy" modifier**:
- Indicators: Character shows jealous reactions when protagonist interacts with others
- Translation impact:
  * Add "jealousy_tension_markers" to priority_patterns
  * Show-don't-tell guidance: "SHOWN through physical reactions (blushing, looking away, fidgeting), not TOLD through exposition"
  * Comedic timing for jealous beats
  * Avoid over-explaining feelings

**"domestic" modifier**:
- Indicators: Breakfast/dinner routines, living together, daily life scenes
- Translation impact:
  * Add "domestic_warmth_vocabulary" to priority_patterns
  * Natural flow for routine descriptions
  * Family-like interaction patterns
  * Gentle protective language

**"slice_of_life" modifier**:
- Indicators: Everyday activities, no major plot events, character-focused
- Translation impact:
  * Conversational pacing
  * Natural dialogue flow
  * Matter-of-fact tone for daily activities

**Genre Array Assembly Strategy:**
```
1. Identify core genre (romcom, action, drama, fantasy)
2. Add narrative style (slice_of_life, school_life)
3. Add theme markers (wholesome, jealousy_comedy, domestic)

Example progression:
Basic:     ["romcom"]
Enhanced:  ["romcom", "slice_of_life", "wholesome", "jealousy_comedy"]

Result: More specific creative framing for Gemini
- Without modifiers: Generic translation approach
- With modifiers: Targeted patterns for specific story elements
```

### Narrative Technique Detection

**Pattern 1: POV Detection**
```python
first_person_indicators_jp = [
    '私', '僕', '俺', '私の', '僕の', '俺の',
    '私は', '僕は', '俺は', 'ボクは', 'わたし'
]

first_person_indicators_en = [
    'I ', "I'm", "I've", "I'd", "I'll",
    'my ', 'mine', 'me ', 'myself'
]

# Count frequency per chapter
if first_person_ratio > 30%:
    narrative_technique = "first_person"
elif first_person_ratio > 10%:
    # Check for Free Indirect Discourse
    if has_third_person_pronouns and has_first_person_emotions:
        narrative_technique = "third_person_limited"
        use_free_indirect_discourse = True
else:
    narrative_technique = "third_person_limited" or "third_person_omniscient"
```

**Pattern 2: Free Indirect Discourse Detection**
```python
fid_indicators = [
    # Third-person pronouns
    'she', 'he', 'her', 'his', 'herself', 'himself',
    # But with emotional directness (no filter words)
    'How [adjective]',  # "How miserable."
    'Oh no',            # "Oh no, what should she do?"
    '[Character] was approaching—',  # Em dash for internal thought
    'What [verb]',      # "What should she do?"
]

# If third-person pronouns + emotional interjections → FID
```

**Pattern 3: Psychic Distance Detection**
```python
psychic_distance_markers = {
    "level_1_maximum": [
        "In the kingdom of", "It was the year", "Once upon a time",
        "The story begins", "Long ago"
    ],
    "level_2_distant": [
        "[Character] walked", "[Character] looked", "[Character]'s footsteps",
        # Objective camera view, no internal access
    ],
    "level_3_close": [
        "[Character] felt", "[Character] noticed", "[Character] thought",
        # Standard third-person with filter words
    ],
    "level_4_very_close": [
        "Her heart pounded", "His palms were slick", "Oh no",
        # Direct sensory/emotional access, minimal filters
    ],
    "level_5_first_person": [
        "My heart pounded", "I felt", "I couldn't"
        # Maximum intimacy
    ]
}

# Analyze first 3 chapters for predominant distance
```

**Pattern 4: Sensory Focus Analysis**
```python
sensory_markers = {
    "sight": ['saw', 'looked', 'appeared', 'shimmered', 'glowed', 'sparkled'],
    "sound": ['heard', 'whispered', 'echoed', 'rustled', 'chimed', 'tinkled'],
    "touch": ['felt', 'warm', 'cold', 'soft', 'rough', 'smooth'],
    "smell": ['smelled', 'scent', 'fragrance', 'aroma', 'stench'],
    "taste": ['tasted', 'sweet', 'bitter', 'savory', 'sour'],
    "emotion": ['heart', 'chest', 'throat', 'stomach', 'trembled', 'pounded']
}

# Count per 1,000 words
sensory_density = count_sensory_markers(text) / word_count * 1000

if sensory_density > 15:
    sensory_focus = "high"  # Shoujo, literary fiction
elif sensory_density > 8:
    sensory_focus = "medium"  # Standard light novels
else:
    sensory_focus = "low"  # Action, plot-focused
```

**Pattern 5: Sentence Pacing Analysis**
```python
# Calculate average sentence length
sentences = text.split('.')
avg_length = sum(len(s.split()) for s in sentences) / len(sentences)
std_dev = calculate_std_dev(sentence_lengths)

if std_dev > 10 and avg_length > 15:
    sentence_pacing = "variable"  # Shoujo, literary (long contemplative + short emphatic)
elif avg_length < 12:
    sentence_pacing = "staccato"  # Noir, thriller (short punchy sentences)
else:
    sentence_pacing = "flowing"  # Epic fantasy (complex, flowing sentences)
```

**Pattern 6: Show Don't Tell Ratio**
```python
tell_indicators = [
    'felt [emotion]', 'was [emotion]', '[Character] felt',
    'seemed', 'appeared to be', 'looked [emotion]'
]

show_indicators = [
    'heart pounded', 'jaw clenched', 'hands trembled',
    'throat tight', 'palms slick', 'breath caught'
]

show_count = count_patterns(text, show_indicators)
tell_count = count_patterns(text, tell_indicators)

if show_count > tell_count * 2:
    show_dont_tell = True  # Strong show-don't-tell
else:
    show_dont_tell = False  # More telling than showing
```

**Pattern 7: Emotional Vocabulary Classification**
```python
vocab_categories = {
    "poetic": ['shimmered', 'danced', 'whispered', 'lingered', 'blossomed'],
    "clinical": ['observed', 'noted', 'examined', 'analyzed', 'determined'],
    "cynical": ['whatever', 'typical', 'figures', 'naturally', 'of course'],
    "archaic": ['verily', 'forsooth', 'mayhap', 'perchance', 'hitherto'],
    "fragmented": ['...', '—', 'no', 'wait', 'but', 'maybe']
}

# Analyze predominant vocabulary style
# Maps to emotional_vocabulary field
```

---

## Voice Assignment Logic

### Age Detection

```python
age_indicators = {
    "child": ["elementary", "小学生", "younger than 12"],
    "teenager": ["high school", "中学生", "高校生", "teen"],
    "young_adult": ["college", "university", "大学生", "20代"],
    "adult": ["working", "会社員", "30代", "adult"],
    "elderly": ["old", "お年寄り", "60代", "elderly"]
}
```

### Gender Detection

```python
gender_indicators = {
    "male": ["boy", "man", "男", "男の子", "kun suffix", "ore", "boku"],
    "female": ["girl", "woman", "女", "女の子", "san suffix", "chan suffix", "watashi (for girls)"]
}
```

### Personality Detection

```python
personality_indicators = {
    "gentle": ["優しい", "gentle", "kind", "soft", "calm"],
    "energetic": ["元気", "energetic", "cheerful", "lively", "active"],
    "shy": ["恥ずかしがり", "shy", "timid", "nervous", "quiet"],
    "aggressive": ["aggressive", "強気", "bold", "assertive", "confident"],
    "cool": ["クール", "cool", "aloof", "distant", "composed"]
}
```

### Voice Assignment Template

```json
{
  "voice_name": "[Suggested TTS voice name]",
  "style_prompt_base": "A [personality] [age_group] [gender] voice with [characteristics]",
  "emotional_variations": {
    "default": "speaking [naturally/politely/casually]",
    "happy": "speaking [cheerfully/joyfully/excitedly]",
    "sad": "speaking [sadly/softly/with melancholy]",
    "angry": "speaking [angrily/firmly/with frustration]",
    "surprised": "speaking [with surprise/shock/amazement]"
  }
}
```

---

## Complete Workflow Example

### Input
```
Volume: 孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた 1
Directory: WORK/孤高の華_1_20260125_0164/
```

### Step 1: Extract Basic Info

**From directory structure**:
```
RAW/
├── CHAPTER_00_RAW.md  → Title page
├── CHAPTER_01_RAW.md
├── CHAPTER_02_RAW.md
...
├── CHAPTER_07_RAW.md

EN/
├── CHAPTER_01_EN.md
├── CHAPTER_02_EN.md
...

IMAGES/
├── img_000.jpg  → Cover
├── img_001.jpg
...
```

**Result**:
- Chapter count: 7
- Has illustrations: Yes (2+ images)
- Has EN translation: Yes

### Step 2: Read Title Page (CHAPTER_00_RAW.md)

**Extract**:
```
Title (JP): 孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた
Title (EN): The Aloof British Beauty Called the Solitary Flower Became My Step-Sister and Started Awkwardly Doting on Me
Author: [Extract from page]
Illustrator: [Extract from page]
Publisher: [Extract from page]
Volume: 1
```

### Step 3: Character Analysis (First 3 Chapters)

**Character 1 Frequency Analysis**:
```
Name mentions in RAW:
- 白川健人: 45 times
- 健人: 120 times
- 俺: 230 times (first-person)

Name mentions in EN:
- Shirakawa Kento: 40 times
- Kento: 115 times
- I: 225 times

First appearance: Chapter 1
Role: Protagonist (first-person POV, most mentions)
Gender: Male (ore = masculine first-person)
Age: High school (context: 学校, クラス)
```

**Character 2 Frequency Analysis**:
```
Name mentions in RAW:
- ソフィア・フロスト: 35 times
- フロストさん: 60 times
- ソフィア: 45 times
- Frost: 25 times

Name mentions in EN:
- Sophia Frost: 40 times
- Frost-san: 55 times
- Sophia: 50 times

Nickname: "The Solitary Flower" (孤高の華)
First appearance: Chapter 1
Role: Love interest (title character, main heroine)
Gender: Female (san suffix, description)
Age: High school
Nationality: British (English mentioned)
```

### Step 4: LLM Analysis Prompt

```
Analyze the following light novel content:

Title: 孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた

First 3 chapters summary:
[Insert first 500 lines of Chapter 1-3]

Tasks:
1. Generate a 2-3 sentence English synopsis
2. Identify genre tags (romance, comedy, school life, etc.)
3. List content warnings (if any)
4. Identify character relationships
5. Detect POV character(s)
6. Suggest voice characteristics for each character

Return as structured JSON.
```

### Step 5: Generate Complete Manifest

**Output: manifest.json**

```json
{
  "version": "3.5",
  "metadata": {
    "series": {
      "title": {
        "japanese": "孤高の華と呼ばれる英国美少女、義妹になったら不器用に甘えてきた",
        "english": "The Aloof British Beauty Called the Solitary Flower Became My Step-Sister and Started Awkwardly Doting on Me",
        "romaji": "Kokō no Hana to Yobareru Eikoku Bishōjo, Imōto ni Nattara Bukiyō ni Amaete Kita"
      },
      "author": "[Extracted]",
      "illustrator": "[Extracted]",
      "publisher": "[Extracted]",
      "publication_date": "2026-01-25",
      "isbn": null,
      "volume_number": 1,
      "total_volumes": null
    },
    "translation": {
      "translator": "MTL Studio",
      "translation_date": "2026-01-25",
      "source_language": "ja",
      "target_language": "en",
      "translation_notes": "Machine translated with post-editing"
    },
    "characters": [
      {
        "name": "Shirakawa Kento",
        "nickname": null,
        "age": 16,
        "gender": "male",
        "role": "protagonist",
        "description": "A high school student who becomes step-siblings with Sophia. Kind but somewhat reserved, he serves as the narrator.",
        "is_pov_character": true,
        "speech_pattern": "masculine_casual",
        "keigo_switch": {
          "default_register": "casual",
          "situations": {
            "with_family": "casual",
            "with_sophia": "polite",
            "with_friends": "casual",
            "with_teachers": "polite"
          }
        },
        "personality_traits": ["kind", "reserved", "thoughtful", "considerate"],
        "voice_assignment": {
          "voice_name": "Aoede",
          "style_prompt_base": "A calm, thoughtful young male voice",
          "emotional_variations": {
            "default": "speaking naturally with a gentle tone",
            "happy": "speaking with warmth and contentment",
            "sad": "speaking softly with melancholy",
            "angry": "speaking firmly but controlled",
            "surprised": "speaking with genuine surprise"
          }
        },
        "first_appearance_chapter": 1
      },
      {
        "name": "Sophia Frost",
        "nickname": "The Solitary Flower",
        "age": 16,
        "gender": "female",
        "role": "love_interest",
        "description": "A beautiful British exchange student with blonde hair and blue eyes. Known as 'The Solitary Flower' for her aloof demeanor, she becomes Kento's step-sister.",
        "is_pov_character": false,
        "speech_pattern": "feminine_polite",
        "keigo_switch": {
          "default_register": "polite",
          "situations": {
            "with_kento": "polite_softening",
            "with_classmates": "polite",
            "with_family": "casual",
            "when_embarrassed": "formal_defensive"
          }
        },
        "personality_traits": ["tsundere", "aloof", "awkward_with_affection", "secretly_caring"],
        "voice_assignment": {
          "voice_name": "Erinome",
          "style_prompt_base": "A refined British girl's voice with a gentle English accent",
          "emotional_variations": {
            "default": "speaking politely with slight distance",
            "happy": "speaking warmly with a softer tone",
            "sad": "speaking quietly with vulnerability",
            "angry": "speaking coldly with controlled irritation",
            "surprised": "speaking with restrained surprise"
          }
        },
        "first_appearance_chapter": 1
      }
    ],
    "content_info": {
      "genre": ["romance", "comedy", "school_life", "slice_of_life"],
      "tags": ["step-siblings", "tsundere", "british_heroine", "school_life", "single_POV"],
      "content_warnings": [],
      "target_audience": "young_adult",
      "synopsis": "Shirakawa Kento's life changes when the famous 'Solitary Flower' Sophia Frost becomes his step-sister. Despite her aloof reputation, she begins awkwardly showing affection toward him, leading to heartwarming and comedic situations.",
      "chapter_count": 7,
      "word_count": 35000,
      "has_illustrations": true,
      "illustration_count": 8
    },
    "translation_guidance": {
      "genres": ["romcom", "slice_of_life"],
      "translator_notes": {
        "priority_patterns": ["comedic_timing", "tsukkomi_interjection", "emotional_intensifiers"],
        "tone": "Warm and lighthearted. Punchy punchlines for comedy moments, natural warmth for romance. Keep tsundere reactions blunt and matter-of-fact.",
        "avoid": ["Over-embellishing comedy", "softening tsundere reactions", "excessive formality in casual moments"]
      },
      "grammar_rag_integration": {
        "enabled": true,
        "pattern_priorities": {
          "comedic_timing": 1.4,
          "tsukkomi_interjection": 1.3,
          "emotional_intensifiers": 1.2,
          "high_frequency_transcreations": 1.1
        }
      }
    }
  },
  "literacy_techniques": {
    "preset": "shoujo_romance",
    "narrative_technique": "third_person_limited",
    "use_free_indirect_discourse": false,
    "psychic_distance": "level_3_close",
    "sensory_focus": "medium",
    "sentence_pacing": "variable",
    "show_dont_tell": true,
    "emotional_vocabulary": "warm, casual, lighthearted",
    "custom_overrides": {
      "note": "Contemporary romcom with tsundere dynamics - prioritize comedic timing over poetic language"
    }
  },
  "structure": {
    "chapters": [
      {
        "id": "ch01",
        "number": 1,
        "title": {
          "japanese": "義妹は孤高の華",
          "english": "My Step-Sister is the Solitary Flower"
        },
        "source_file": "CHAPTER_01.md",           // Legacy field for translator pipeline
        "translated_file": "CHAPTER_01_EN.md",    // Legacy field for translator pipeline
        "file_japanese": "JP/CHAPTER_01.md",      // v3.7 full path
        "file_english": "EN/CHAPTER_01_EN.md",    // v3.7 full path
        "word_count": 5200,
        "has_illustration": true,
        "illustration_ids": ["img_001"],
        "pov_character": "Shirakawa Kento"
      }
      // ... more chapters
    ],
    "illustrations": [
      {
        "id": "img_000",
        "file": "IMAGES/img_000.jpg",
        "caption": "Cover illustration",
        "type": "color",
        "location": "cover",
        "related_chapter": null,
        "characters_depicted": ["Sophia Frost"]
      }
      // ... more illustrations
    ]
  }
}
```

---

## Agent Prompts

### Prompt 1: Initial Analysis

```
You are analyzing a Japanese light novel for metadata extraction.

Volume directory: {volume_path}

Task 1: Read the first chapter (RAW/CHAPTER_01_RAW.md) and extract:
1. All character names mentioned
2. The narrative POV (first-person or third-person)
3. If first-person, identify the POV character
4. The setting (school, fantasy world, modern city, etc.)
5. The genre (romance, action, comedy, etc.)

Return as structured JSON.
```

### Prompt 2: Character Deep Dive

```
Analyze these characters from the light novel:

Characters found: {character_list}

For each character, provide:
1. Full name (Japanese and English if available)
2. Nicknames or titles
3. Approximate age (child, teen, young adult, adult)
4. Gender
5. Role (protagonist, love interest, supporting, etc.)
6. Personality traits (3-5 adjectives)
7. Speech style (formal, casual, energetic, reserved, etc.)
8. First appearance chapter

Use the first 3 chapters for analysis.
```

### Prompt 3: Voice Assignment

```
Based on character analysis:

Character: {character_name}
Age: {age}
Gender: {gender}
Personality: {personality_traits}
Speech style: {speech_style}

Generate voice assignment:
1. Suggest voice type (calm male, energetic female, child, etc.)
2. Write style_prompt_base
3. Write emotional variations for: default, happy, sad, angry, surprised

Format as JSON matching schema v3.5 voice_assignment structure.
```

### Prompt 4: Synopsis Generation

```
Generate a concise synopsis (2-3 sentences) for this light novel:

Title: {title}
Genre: {genre}
Main characters: {characters}
First chapter summary: {chapter_1_summary}

The synopsis should:
- Be engaging and concise
- Highlight the main premise
- Mention key characters and their relationship
- Not spoil major plot points
```

### Prompt 5: Literacy Technique Detection

```
Analyze the narrative technique of this light novel:

Title: {title}
First 3 chapters: {chapters_1_3_text}

Detect the following:

1. **Narrative POV**:
   - Is it first-person ("I", "my") or third-person ("she", "he")?
   - If third-person, is it limited (one character's thoughts) or omniscient (multiple characters' thoughts)?
   - If third-person, is it objective (camera view, no internal thoughts)?

2. **Free Indirect Discourse**:
   - Does the narrator use the character's vocabulary to describe objective reality?
   - Example: "Kazehaya was approaching—oh no, what should she do?" (third-person grammar + first-person emotion)
   - True/False

3. **Psychic Distance** (John Gardner scale 1-5):
   - Level 1 (Maximum): "In the kingdom of X, there lived a girl."
   - Level 2 (Distant): "Sawako walked down the hallway, her footsteps silent."
   - Level 3 (Close): "Sawako felt her heart pounding."
   - Level 4 (Very Close): "Her heart pounded—oh no, what should she do?"
   - Level 5 (First Person): "My heart pounded."
   - Which level best describes this text?

4. **Sensory Focus**:
   - Count sensory descriptions (sight, sound, touch, smell, taste, emotion) per 1,000 words
   - High (>15), Medium (8-15), or Low (<8)?

5. **Sentence Pacing**:
   - Staccato (short, punchy sentences)
   - Flowing (long, complex sentences)
   - Variable (mix of short and long)

6. **Show Don't Tell**:
   - Does the text show emotions through actions/sensory details?
   - Or does it tell emotions with labels ("she felt sad")?
   - Ratio: Show-heavy vs Tell-heavy

7. **Emotional Vocabulary Style**:
   - Poetic ("shimmered", "danced", "whispered")
   - Cynical ("whatever", "typical", "figures")
   - Clinical ("observed", "noted", "examined")
   - Archaic ("verily", "forsooth", "mayhap")
   - Fragmented ("...", "—", "no", "wait")

Return as structured JSON matching literacy_techniques schema.
```

### Prompt 6: Literacy Preset Mapping

```
Based on detected narrative characteristics:

Narrative technique: {narrative_technique}
Free Indirect Discourse: {use_fid}
Psychic distance: {psychic_distance}
Sensory focus: {sensory_focus}
Sentence pacing: {sentence_pacing}
Show don't tell: {show_dont_tell}
Emotional vocabulary: {emotional_vocabulary}

Map to the most appropriate preset:

Available presets:
1. **shoujo_romance**: Third-person limited, FID, very close distance, high sensory, variable pacing, poetic vocabulary
2. **noir_hardboiled**: First-person, level 5 distance, staccato pacing, cynical vocabulary, medium sensory
3. **psychological_horror**: First/third-person, very close distance, unreliable narrator, high sensory, fragmented vocabulary
4. **epic_fantasy**: Third-person omniscient, distant/maximum distance, flowing pacing, archaic vocabulary, medium sensory
5. **contemporary_ya**: Third-person limited, close distance, variable pacing, casual vocabulary, medium sensory
6. **action_adventure**: Third-person objective/limited, distant distance, staccato pacing, direct vocabulary, low sensory

Return:
- Best matching preset name
- Confidence score (0-100)
- Reasoning for the match
- Any custom overrides needed
```

---

## Automated Workflow

### Script: `generate_manifest.py`

```python
#!/usr/bin/env python3
"""
Automated manifest.json generator for schema v3.5

Usage:
    python generate_manifest.py <volume_directory>

Example:
    python generate_manifest.py "WORK/孤高の華_1_20260125_0164"
```

import os
import sys
import json
from pathlib import Path
from google import genai

def scan_volume(volume_dir: Path) -> dict:
    """Scan volume directory and extract metadata."""

    # Step 1: Basic structure
    raw_dir = volume_dir / "RAW"
    en_dir = volume_dir / "EN"
    images_dir = volume_dir / "IMAGES"

    # Step 2: Count chapters
    chapters = sorted(raw_dir.glob("CHAPTER_*.md"))
    chapter_count = len(chapters)

    # Step 3: Read first chapter for analysis
    first_chapter = chapters[0].read_text(encoding='utf-8')

    # Step 4: LLM analysis
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # ... (implement full analysis)

    return manifest

if __name__ == '__main__':
    volume_dir = Path(sys.argv[1])
    manifest = scan_volume(volume_dir)

    output_file = volume_dir / "manifest.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"✓ Generated: {output_file}")
```

---

## Quality Assurance

### Validation Checklist

After generation, verify:

- [ ] All required fields are populated (no nulls where not allowed)
- [ ] Character names match between RAW and EN
- [ ] POV character is correctly identified
- [ ] Voice assignments are appropriate for age/gender/personality
- [ ] Chapter count matches actual file count
- [ ] **Both legacy (source_file, translated_file) and v3.7 (file_japanese, file_english) fields are present for all chapters**
- [ ] Illustration IDs correspond to actual image files
- [ ] Genre tags are accurate and relevant
- [ ] Synopsis is concise and spoiler-free
- [ ] Content warnings are appropriate (if any)
- [ ] **Literacy techniques preset matches detected narrative style**
- [ ] **Psychic distance level is appropriate for genre**
- [ ] **Free Indirect Discourse flag matches actual usage**
- [ ] **Emotional vocabulary classification is accurate**

### Manual Review Points

**High Priority** (must review):
1. POV character identification
2. Character role assignments
3. Content warnings
4. Synopsis accuracy
5. **Literacy techniques preset selection**
6. **Psychic distance level accuracy**

**Medium Priority** (should review):
1. Voice style prompts
2. Character descriptions
3. Genre classification
4. Emotional variations
5. **Free Indirect Discourse detection**
6. **Sensory focus level**
7. **Show Don't Tell ratio**

**Low Priority** (optional review):
1. Word counts (approximate is fine)
2. Romaji transliteration
3. Illustration captions

---

## Usage in IDE

### VS Code Task

Add to `.vscode/tasks.json`:

```json
{
  "label": "Generate Manifest v3.8",
  "type": "shell",
  "command": "python",
  "args": [
    "${workspaceFolder}/pipeline/generate_manifest.py",
    "${input:volumeDirectory}"
  ],
  "problemMatcher": []
}
```

### Quick Command

```bash
# Generate manifest for specific volume
python pipeline/generate_manifest.py "WORK/volume_name"

# Batch generate for all volumes
for vol in WORK/*/; do
  python pipeline/generate_manifest.py "$vol"
done
```

---

## Next Steps

1. **Implement `generate_manifest.py`** with full LLM integration and literacy technique detection
2. **Test on 3-5 diverse volumes** (shoujo, action, fantasy) to validate extraction accuracy
3. **Refine narrative technique detection prompts** based on results
4. **Add manual override options** for edge cases and custom literacy configurations
5. **Integrate with CLI** as `mtl manifest-generate`
6. **Create preset library** for common genre/literacy combinations
7. **Build validation suite** for literacy technique accuracy
8. **Multimodal integration**: Run Phase 1.6 after manifest generation to pre-bake visual analysis

---

## Multimodal CLI Integration

### Full Pipeline (Automatic)

```bash
# Full pipeline includes Phase 1.6 (multimodal) automatically
mtl.py run INPUT/novel.epub

# Skip multimodal for faster processing
mtl.py run INPUT/novel.epub --skip-multimodal
```

### Manual Multimodal Workflow

```bash
# Step 1: Extract EPUB
mtl.py phase1 INPUT/novel.epub --id novel_v1

# Step 2: Process metadata
mtl.py phase1.5 novel_v1

# Step 3: Generate Art Director's Notes
mtl.py phase1.6 novel_v1

# Step 4: Translate with visual context (auto-enabled after Phase 1.6)
mtl.py phase2 novel_v1 --enable-multimodal

# Inspect visual cache
mtl.py cache-inspect novel_v1 --detail
```

### Multimodal Validation Checklist

- [ ] `visual_cache.json` exists and has entries for all illustrations
- [ ] All entries have `status: "cached"` (not `error` or `blocked`)
- [ ] `manifest.json → structure.id_mapping` maps EPUB IDs to cache IDs
- [ ] Canon names are injected (`_canon_names` section in visual_cache)
- [ ] `narrative_directives` arrays have 3-5 actionable instructions
- [ ] `spoiler_prevention.do_not_reveal_before_text` is populated

---

**Agent Version**: 2.1
**Schema Version**: 3.8 (with multimodal metadata)
**Last Updated**: 2026-02-06
**Status**: Ready for implementation
**New Features**: 
- Narrative technique detection
- Psychic distance analysis
- Genre-specific preset mapping
- Multimodal Art Director's Notes (Phase 1.6)
- Canon Event Fidelity enforcement
- ID mapping for EPUB ↔ visual_cache

