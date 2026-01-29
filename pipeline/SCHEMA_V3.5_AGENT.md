# Schema v3.5 Metadata Agent

**Purpose**: Automatically scan raw light novel content and generate complete v3.5 Enhanced Schema metadata.

**Agent Type**: Analysis & Data Extraction
**Tools**: File reading, pattern matching, LLM analysis
**Output**: Fully populated manifest.json

---

## Agent Instructions

You are a metadata extraction agent specialized in analyzing Japanese light novel content and generating accurate schema v3.5 metadata. Your task is to:

1. **Understand the v3.5 Schema Structure** completely
2. **Scan raw content** from the RAW folder (Japanese original)
3. **Analyze translated content** from EN folder (if available)
4. **Extract all metadata** fields accurately
5. **Generate complete manifest.json** ready for production

---

## Schema v3.5 Structure Reference

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
        "file_raw": "string",
        "file_translated": "string",
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
    ]
  }
}
```

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

### Phase 6: Schema v3.6 Upgrade

12. **Run the automated schema upgrade script**:
    ```bash
    python scripts/upgrade_to_schema_v36.py "WORK/[volume_directory]"
    ```
    
    This script will:
    - Scan all JP chapters and extract character names with furigana
    - Create backup files (.json.backup)
    - Generate placeholder character profiles
    - Add v3.6 metadata fields
    - Preserve all existing data
    
13. **Complete the character profiles**:
    - The script creates placeholder templates for character_profiles
    - **AGENT MUST FILL** these placeholders with actual data from your text analysis:
      - `full_name`: Extract from furigana patterns (白木{しらぎ}求{もとむ})
      - `personality_traits`: From your LLM analysis of behavior
      - `speech_pattern`: From dialogue analysis
      - `keigo_switch`: Map speaking styles per character/situation
      - `character_arc`: From narrative analysis
      - `pov_character`: For each chapter based on first-person detection
    
14. **Fill content_info fields**:
    ```json
    "content_info": {
      "genre": ["[Replace with your genre analysis]"],
      "tags": ["[Replace with extracted themes]"],
      "content_warnings": ["[Add any warnings found]"],
      "synopsis_en": "[Write from your narrative analysis]"
    }
    ```
    
15. **Verify all placeholders are replaced**:
    - Search for `[AGENT:` in both manifest.json and metadata_en.json
    - Ensure no placeholder text remains
    - Validate JSON structure before proceeding to translation

**Note**: The upgrade script is idempotent - safe to run multiple times. It preserves existing v3.6 data if already present.

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
        "file_raw": "RAW/CHAPTER_01_RAW.md",
        "file_translated": "EN/CHAPTER_01_EN.md",
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
- [ ] Illustration IDs correspond to actual image files
- [ ] Genre tags are accurate and relevant
- [ ] Synopsis is concise and spoiler-free
- [ ] Content warnings are appropriate (if any)

### Manual Review Points

**High Priority** (must review):
1. POV character identification
2. Character role assignments
3. Content warnings
4. Synopsis accuracy

**Medium Priority** (should review):
1. Voice style prompts
2. Character descriptions
3. Genre classification
4. Emotional variations

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
  "label": "Generate Manifest v3.5",
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

1. **Implement `generate_manifest.py`** with full LLM integration
2. **Test on 3-5 diverse volumes** to validate extraction accuracy
3. **Refine prompts** based on results
4. **Add manual override options** for edge cases
5. **Integrate with CLI** as `mtl manifest-generate`

---

**Agent Version**: 1.0
**Schema Version**: 3.5
**Last Updated**: 2026-01-29
**Status**: Ready for implementation

