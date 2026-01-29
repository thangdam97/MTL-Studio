#!/usr/bin/env python3
"""
Schema v3.6 Upgrade Script - Standalone Runtime
Upgrades manifest.json and metadata_en.json to v3.6 schema with enhanced character profiles.

Usage:
    python scripts/upgrade_to_schema_v36.py <volume_directory>
    
Example:
    python scripts/upgrade_to_schema_v36.py "WORK/novel_title_20260129_xxxx"

Required:
    - volume_directory/JP/ with chapter files
    - volume_directory/manifest.json (existing v1.0)
    - volume_directory/metadata_en.json (existing basic metadata)

Output:
    - Upgrades manifest.json to v3.6 with character_profiles
    - Upgrades metadata_en.json to v3.6 with enhanced metadata
    - Preserves all existing data, adds new v3.6 fields
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime


def scan_jp_chapters(jp_dir):
    """Scan all JP chapter files and return combined text."""
    all_text = ""
    chapter_files = sorted(jp_dir.glob("CHAPTER_*.md"))
    
    print(f"\n📚 Scanning {len(chapter_files)} Japanese chapters...")
    for ch_file in chapter_files:
        with open(ch_file, 'r', encoding='utf-8') as f:
            all_text += f.read() + "\n"
        print(f"  ✓ {ch_file.name}")
    
    return all_text, len(chapter_files)


def extract_character_names(text):
    """Extract character names with furigana from Japanese text."""
    # Pattern: 白木{しらぎ} or 求{もとむ}
    name_pattern = r'([一-龯]{2,4}){([ぁ-ん]+)}'
    names_found = re.findall(name_pattern, text)
    name_counter = Counter(names_found)
    
    print(f"\n🔍 Found {len(name_counter)} unique character names with furigana")
    
    # Display top 10 most frequent
    print("\nTop 10 most frequent names:")
    for (kanji, reading), count in name_counter.most_common(10):
        print(f"   {kanji}({reading}): {count} occurrences")
    
    return name_counter


def create_character_template():
    """Return template for character profile."""
    return {
        "full_name": "[CHARACTER_NAME_KANJI] ([reading])",
        "nickname": "[NICKNAME or leave empty]",
        "age": "[AGE] years old, [GRADE/YEAR if student]",
        "pronouns": "he/him or she/her or they/them",
        "origin": "Japanese",
        "relationship_to_protagonist": "[DESCRIBE RELATIONSHIP]",
        "relationship_to_others": "[MAP relationships to other characters]",
        "personality_traits": "[LIST personality traits from text analysis]",
        "speech_pattern": "[DESCRIBE how character speaks - casual/formal/dialect]",
        "keigo_switch": {
            "narration": "[IF POV: describe narration style]",
            "internal_thoughts": "[IF POV: describe internal voice]",
            "speaking_to": {
                "[character_name]": "[speech style with this person]"
            },
            "emotional_shifts": {
                "embarrassed": "[how speech changes]",
                "angry": "[how speech changes]",
                "comfortable": "[how speech changes]"
            },
            "notes": "[AGENT: Fill with specific observations about speech patterns]"
        },
        "key_traits": "[LIST key character traits, skills, background]",
        "appearance": "[PHYSICAL DESCRIPTION if available]",
        "character_arc": "[DESCRIBE character development across volume]",
        "ruby_base": "[KANJI NAME]",
        "ruby_reading": "[HIRAGANA READING]",
        "occurrences": 0
    }


def upgrade_to_v36(volume_dir):
    """Upgrade a volume directory to schema v3.6."""
    
    volume_path = Path(volume_dir)
    if not volume_path.exists():
        print(f"❌ Error: Volume directory not found: {volume_dir}")
        return False
    
    jp_dir = volume_path / "JP"
    manifest_path = volume_path / "manifest.json"
    metadata_en_path = volume_path / "metadata_en.json"
    
    # Verify required files exist
    if not jp_dir.exists():
        print(f"❌ Error: JP directory not found: {jp_dir}")
        return False
    if not manifest_path.exists():
        print(f"❌ Error: manifest.json not found: {manifest_path}")
        return False
    if not metadata_en_path.exists():
        print(f"❌ Error: metadata_en.json not found: {metadata_en_path}")
        return False
    
    print("="*60)
    print(f"Upgrading to Schema v3.6")
    print(f"Volume: {volume_path.name}")
    print("="*60)
    
    # Load existing files
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    with open(metadata_en_path, 'r', encoding='utf-8') as f:
        metadata_en = json.load(f)
    
    # Scan JP files
    all_text, chapter_count = scan_jp_chapters(jp_dir)
    name_counter = extract_character_names(all_text)
    
    # Create placeholder character profiles
    # AGENT INSTRUCTION: Replace this section with actual character data from your analysis
    print("\n⚠️  AGENT ACTION REQUIRED:")
    print("    Replace placeholder character profiles with actual data from your scan.")
    print("    Use create_character_template() structure for each character.\n")
    
    characters = {
        "Protagonist": create_character_template(),
        "Heroine": create_character_template(),
        "Supporting_Character_1": create_character_template()
    }
    
    # Update manifest to v3.6
    manifest["schema_version"] = "3.6"
    manifest["last_updated"] = datetime.now().isoformat()
    
    # Add enhanced character profiles
    if "metadata_en" not in manifest:
        manifest["metadata_en"] = {}
    
    manifest["metadata_en"]["character_profiles"] = characters
    
    # Add translation metadata section
    manifest["metadata_en"]["translation_metadata"] = {
        "translator": "MTL Studio v3.5 LTS",
        "translation_engine": "Claude Sonnet 3.5",
        "translation_date": datetime.now().strftime("%Y-%m-%d"),
        "translation_settings": {
            "temperature": 0.8,
            "context_window": "32k tokens",
            "prompt_version": "v3.5",
            "quality_target": "A+ (FFXIV-tier)"
        },
        "revision_history": []
    }
    
    # Add genre and content info (AGENT: Fill these from your analysis)
    manifest["metadata_en"]["content_info"] = {
        "genre": ["[AGENT: Fill from text analysis]"],
        "tags": ["[AGENT: Extract key themes and tags]"],
        "content_warnings": ["[AGENT: Identify any content warnings]"],
        "target_audience": "young_adult",
        "synopsis_en": "[AGENT: Generate English synopsis from your analysis]",
        "synopsis_jp": manifest["metadata"].get("description", ""),
        "chapter_count": chapter_count,
        "has_illustrations": True
    }
    
    # Update chapter metadata with enhanced info
    chapters_metadata = {}
    
    if isinstance(metadata_en.get("chapters"), list):
        # Convert old list format to dict format
        for ch_data in metadata_en["chapters"]:
            ch_id = ch_data.get("id", f"chapter_{len(chapters_metadata)+1:02d}")
            ch_num = int(ch_id.replace("chapter_", ""))
            
            chapters_metadata[ch_id] = {
                "title_jp": ch_data.get("title_jp", f"第{ch_num}話"),
                "title_en": ch_data.get("title_en", f"Chapter {ch_num}"),
                "chapter_number": ch_num,
                "pov_character": "[AGENT: Determine POV character from text analysis]",
                "word_count_estimate": 0,
                "translation_status": "pending",
                "quality_check_status": "pending"
            }
    else:
        # Already dict format, enhance it
        for ch_id, ch_data in metadata_en.get("chapters", {}).items():
            ch_num = ch_data.get("chapter_number", int(ch_id.replace("chapter_", "")))
            chapters_metadata[ch_id] = {
                "title_jp": ch_data.get("title_jp", f"第{ch_num}話"),
                "title_en": ch_data.get("title_en", f"Chapter {ch_num}"),
                "chapter_number": ch_num,
                "pov_character": ch_data.get("pov_character", "[AGENT: Determine from analysis]"),
                "word_count_estimate": ch_data.get("word_count_estimate", 0),
                "translation_status": ch_data.get("translation_status", "pending"),
                "quality_check_status": ch_data.get("quality_check_status", "pending")
            }
    
    manifest["metadata_en"]["chapters"] = chapters_metadata
    
    # Backup original files
    backup_manifest = manifest_path.with_suffix('.json.backup')
    backup_metadata = metadata_en_path.with_suffix('.json.backup')
    
    with open(backup_manifest, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    with open(backup_metadata, 'w', encoding='utf-8') as f:
        json.dump(metadata_en, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Backups created: .json.backup files")
    
    # Save updated manifest
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Manifest upgraded to v3.6: {manifest_path}")
    
    # Update metadata_en.json
    metadata_en_v36 = {
        "schema_version": "3.6",
        "title_en": metadata_en.get("title_en", "[AGENT: Fill English title]"),
        "author_en": metadata_en.get("author_en", "[AGENT: Fill author name]"),
        "illustrator_en": metadata_en.get("illustrator_en", "[AGENT: Fill illustrator name]"),
        "publisher_en": metadata_en.get("publisher_en", "KADOKAWA CORPORATION"),
        "volume_number": metadata_en.get("volume_number", 1),
        "chapters": chapters_metadata,
        "character_profiles": characters,
        "content_info": manifest["metadata_en"]["content_info"],
        "translation_metadata": manifest["metadata_en"]["translation_metadata"]
    }
    
    with open(metadata_en_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_en_v36, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Metadata_en upgraded to v3.6: {metadata_en_path}")
    
    # Summary
    print("\n" + "="*60)
    print("Schema v3.6 Upgrade Complete")
    print("="*60)
    print(f"\n📊 Character Profiles: {len(characters)} (PLACEHOLDERS - AGENT MUST FILL)")
    print(f"📚 Chapters: {len(chapters_metadata)}")
    print(f"\n⚠️  NEXT STEPS FOR AGENT:")
    print("   1. Review generated character templates")
    print("   2. Fill character_profiles with actual data from text analysis")
    print("   3. Update content_info.genre and tags from theme analysis")
    print("   4. Write synopsis_en based on volume content")
    print("   5. Set pov_character for each chapter")
    print("   6. Verify all [AGENT: ...] placeholders are filled")
    print(f"\n✅ Files ready for agent completion and translation!")
    
    return True


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/upgrade_to_schema_v36.py <volume_directory>")
        print("\nExample:")
        print('  python scripts/upgrade_to_schema_v36.py "WORK/novel_title_20260129_xxxx"')
        sys.exit(1)
    
    volume_dir = sys.argv[1]
    success = upgrade_to_v36(volume_dir)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
