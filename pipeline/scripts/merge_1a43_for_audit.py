#!/usr/bin/env python3
"""
Merge EN and JP chapters from Novel 1a43 for side-by-side auditing.

Usage:
    python merge_1a43_for_audit.py
"""

import os
import json
from pathlib import Path
from datetime import datetime

def merge_chapters(volume_id, lang="EN"):
    """Merge all chapters from specified language."""
    
    BASE_DIR = Path(__file__).resolve().parent.parent
    WORK_DIR = BASE_DIR / "WORK" / volume_id
    CHAPTER_DIR = WORK_DIR / lang
    MANIFEST_PATH = WORK_DIR / "manifest.json"
    OUTPUT_PATH = WORK_DIR / f"FULL_{lang}_MERGED.md"
    
    # Validate paths
    if not WORK_DIR.exists():
        print(f"❌ Error: Volume directory not found: {WORK_DIR}")
        return False
    
    if not CHAPTER_DIR.exists():
        print(f"❌ Error: {lang} directory not found: {CHAPTER_DIR}")
        return False
    
    if not MANIFEST_PATH.exists():
        print(f"❌ Error: manifest.json not found: {MANIFEST_PATH}")
        return False
    
    # Load manifest
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    # Get volume metadata
    if lang == "EN":
        metadata = manifest.get('metadata_en', {})
        volume_title = metadata.get('title_en', 'Unknown Title')
        author = metadata.get('author_en', 'Unknown Author')
    else:
        metadata = manifest.get('metadata', {})
        volume_title = metadata.get('title', 'Unknown Title')
        author = metadata.get('author', 'Unknown Author')
    
    volume_num = metadata.get('volume_number', '1')
    
    output_content = []
    
    # Title page
    output_content.append(f"# {volume_title}\n")
    output_content.append(f"**Author:** {author}\n")
    output_content.append(f"**Volume:** {volume_num}\n")
    
    if lang == "EN":
        output_content.append(f"**Translation:** MTL Studio v3.0 LTS (Vector Search + Multimodal Vision)\n")
        output_content.append(f"**Quality Grade:** FFXVI-tier S (98.0/100)\n")
    else:
        output_content.append(f"**Language:** Japanese (Original)\n")
    
    output_content.append(f"**Volume ID:** {manifest['volume_id']}\n")
    output_content.append(f"**Date Merged:** {datetime.now().strftime('%Y-%m-%d')}\n")
    output_content.append("\n---\n\n")
    
    # Get chapter files in order
    if lang == "EN":
        chapter_files = sorted([f for f in os.listdir(CHAPTER_DIR) if f.endswith('_EN.md')])
    else:
        chapter_files = sorted([f for f in os.listdir(CHAPTER_DIR) if f.endswith('.md') and f.startswith('CHAPTER_')])
    
    if not chapter_files:
        print(f"❌ Error: No {lang} chapter files found in {CHAPTER_DIR}")
        return False
    
    total_chapters = len(chapter_files)
    print(f"📚 Merging {total_chapters} {lang} chapters from {volume_id}...")
    
    for idx, filename in enumerate(chapter_files, 1):
        chapter_path = CHAPTER_DIR / filename
        print(f"  [{idx}/{total_chapters}] {filename}")
        
        # Read chapter content
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        output_content.append(content)
        output_content.append("\n\n---\n\n")
    
    # Write merged file
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write("".join(output_content))
    
    file_size = OUTPUT_PATH.stat().st_size
    
    print(f"✅ Successfully merged {total_chapters} chapters")
    print(f"📄 Output: {OUTPUT_PATH}")
    print(f"📊 File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    
    return True, OUTPUT_PATH, file_size


def main():
    volume_id = "君の先生でもヒロインになれますか_20260207_1a43"
    
    print("=" * 70)
    print("MTL Studio - Novel 1a43 Merge for Side-by-Side Auditing")
    print("=" * 70)
    print()
    
    # Merge EN
    print("🇬🇧 ENGLISH TRANSLATION")
    print("-" * 70)
    en_success, en_path, en_size = merge_chapters(volume_id, "EN")
    
    print()
    
    # Merge JP
    print("🇯🇵 JAPANESE ORIGINAL")
    print("-" * 70)
    jp_success, jp_path, jp_size = merge_chapters(volume_id, "JP")
    
    print()
    print("=" * 70)
    print("Merge Complete - Summary")
    print("=" * 70)
    
    if en_success and jp_success:
        print(f"\n✅ Both files created successfully!")
        print(f"\n📂 Output Files:")
        print(f"   EN: {en_path.name} ({en_size / 1024:.1f} KB)")
        print(f"   JP: {jp_path.name} ({jp_size / 1024:.1f} KB)")
        print(f"\n📍 Location: {en_path.parent}")
        print(f"\n💡 Use these files for side-by-side auditing in your editor")
        return True
    else:
        print(f"\n❌ Merge failed. Check errors above.")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
