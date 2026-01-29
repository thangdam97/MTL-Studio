# Schema v3.6 Upgrade Script - Quick Reference

## Purpose
Automates the upgrade of novel metadata from v1.0 to v3.6 schema with enhanced character profiles and translation metadata.

## Location
```
pipeline/scripts/upgrade_to_schema_v36.py
```

## Usage

### Basic Usage
```bash
python scripts/upgrade_to_schema_v36.py "WORK/[volume_directory_name]"
```

### Example
```bash
# For novel 205c
python scripts/upgrade_to_schema_v36.py "WORK/友人に500円貸したら借金のカタに妹をよこしてきたのだけれど、俺は一体どうすればいいんだろう_20260129_205c"

# For novel 0dad
python scripts/upgrade_to_schema_v36.py "WORK/誰にも懐かないソロギャルが毎日お泊まりしたがってくる 【電子特典付き】_20260129_0dad"
```

## What It Does

### 1. Scans Content
- Reads all `JP/CHAPTER_*.md` files
- Extracts character names with furigana (e.g., 白木{しらぎ}求{もとむ})
- Counts chapters and displays frequency analysis
- Shows top 10 most mentioned character names

### 2. Creates Backups
- Saves `manifest.json.backup`
- Saves `metadata_en.json.backup`
- Safe to run multiple times (idempotent)

### 3. Upgrades Schema
Adds to **manifest.json**:
- `schema_version: "3.6"`
- `last_updated: [timestamp]`
- `metadata_en.character_profiles` - with templates
- `metadata_en.translation_metadata` - translation settings
- `metadata_en.content_info` - genre, tags, synopsis
- `metadata_en.chapters` - enhanced chapter metadata

Upgrades **metadata_en.json**:
- Converts to v3.6 structure
- Adds `schema_version: "3.6"`
- Includes all character profiles
- Enhanced chapter metadata with POV tracking

## Output Structure

### Character Profile Template
```json
{
  "Character_Name": {
    "full_name": "[KANJI] ([reading])",
    "nickname": "[nickname]",
    "age": "[age] years old",
    "pronouns": "he/him | she/her",
    "relationship_to_protagonist": "[describe]",
    "personality_traits": "[traits]",
    "speech_pattern": "[casual/formal/dialect]",
    "keigo_switch": {
      "narration": "[style]",
      "speaking_to": {
        "[character]": "[style with them]"
      }
    },
    "key_traits": "[notable features]",
    "appearance": "[description]",
    "character_arc": "[development]",
    "ruby_base": "[KANJI]",
    "ruby_reading": "[hiragana]",
    "occurrences": 8
  }
}
```

## Agent Workflow

### Phase 1: Run Script
```bash
python scripts/upgrade_to_schema_v36.py "WORK/your_novel_directory"
```

### Phase 2: Fill Placeholders
The script generates placeholder templates. **You must replace**:

1. **Character Profiles** - Fill all `[AGENT: ...]` fields:
   - Extract names from furigana scan results
   - Analyze personality from chapters 1-3
   - Map speech patterns from dialogue
   - Document keigo switches per situation
   - Write character arcs from narrative

2. **Content Info**:
   ```json
   "genre": ["Romance", "Comedy", "Slice of Life"],
   "tags": ["School Life", "Tsundere", "Childhood Friends"],
   "synopsis_en": "Write 2-3 sentence summary"
   ```

3. **Chapter Metadata** - For each chapter:
   - `pov_character`: Detect from first-person analysis
   - Verify `title_en` translations

### Phase 3: Validate
```bash
# Check for remaining placeholders
grep -r "\[AGENT:" WORK/your_novel_directory/manifest.json
grep -r "\[AGENT:" WORK/your_novel_directory/metadata_en.json

# Should return nothing when complete
```

## Validation Checklist

Before translation, verify:

- [ ] No `[AGENT: ...]` placeholders remain
- [ ] All character profiles filled with real data
- [ ] Genre and tags reflect actual content
- [ ] Synopsis written in English
- [ ] POV character set for each chapter
- [ ] Character names match furigana scan results
- [ ] Speech patterns documented
- [ ] Keigo switches mapped
- [ ] JSON files are valid (no syntax errors)

## Features

### Smart Detection
- Automatically extracts character names with readings
- Frequency analysis shows main vs supporting characters
- Preserves existing v3.6 data if already present

### Safe Execution
- Creates backups before modification
- Idempotent (safe to run multiple times)
- Non-destructive (adds fields, doesn't remove)

### Clear Output
- Shows scan progress per chapter
- Displays top character name frequencies
- Lists all placeholders requiring agent attention
- Provides next steps checklist

## Troubleshooting

### "Directory not found"
- Check volume directory name is correct
- Use full path or relative from `pipeline/`

### "JP directory not found"
- Ensure `JP/` folder exists with chapter files
- Files must be named `CHAPTER_*.md`

### "manifest.json not found"
- Run epub extraction first to generate base manifest
- Ensure you're in the correct volume directory

### JSON Syntax Errors
- Script preserves existing data structure
- If errors occur, restore from `.backup` files
- Validate JSON after manual edits

## Integration with SCHEMA_V3.5_AGENT.md

This script is referenced in the agent workflow at **Phase 6**:
1. Complete Phases 1-5 (scan, analyze, extract)
2. Run this script to generate v3.6 structure
3. Fill all agent placeholders with your analysis data
4. Validate completeness
5. Proceed to translation

## Notes

- Script designed for post-analysis automation
- Not a replacement for agent analysis work
- Templates guide agent on required data structure
- All `[AGENT: ...]` fields must be human/LLM filled
- Backup files preserved for safety
