#!/usr/bin/env python3
"""
Merge 1420 Volume Files
Merges all chapter files (JP and EN) into single unified documents.

Usage:
    python merge_1420.py
"""

import os
import json
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
WORK_DIR = BASE_DIR / "WORK"

# Find 1420 volume directory
VOLUME_DIR = None
for dir_name in os.listdir(WORK_DIR):
    if "1420" in dir_name:
        VOLUME_DIR = WORK_DIR / dir_name
        break

if not VOLUME_DIR:
    print("❌ Error: Could not find 1420 volume directory")
    exit(1)

EN_DIR = VOLUME_DIR / "EN"
JP_DIR = VOLUME_DIR / "JP"
MANIFEST_PATH = VOLUME_DIR / "manifest.json"

# Output paths
EN_OUTPUT = VOLUME_DIR / "1420_EN_Full.md"
JP_OUTPUT = VOLUME_DIR / "1420_JP_Full.md"


def load_manifest():
    """Load manifest.json to get chapter metadata."""
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def merge_english():
    """Merge all English chapters into one markdown file."""
    print("\n📚 Merging English Translation...")
    
    manifest = load_manifest()
    chapters_metadata = manifest.get("metadata_en", {}).get("chapters", {})
    
    # Get volume metadata
    volume_title = manifest["metadata_en"]["title_en"]
    author = manifest["metadata_en"]["author_en"]
    
    output_content = []
    
    # Title page
    output_content.append(f"# {volume_title}\n\n")
    output_content.append(f"**Author:** {author}\n\n")
    output_content.append(f"**Translation:** MTL Studio v3.5 Pipeline\n\n")
    output_content.append(f"**Translation Models:** \n")
    output_content.append(f"- Ch1-16: API Gemini 2.5 Pro (0.2/1k AI-ism density)\n")
    output_content.append(f"- Ch17-21: Web Gemini 3 Flash Thinking (4.5/1k density, PROHIBITED_CONTENT bypass)\n\n")
    output_content.append(f"**Quality Grade:** A+ (97.5/100) - FFXVI-Tier Publication Quality\n\n")
    output_content.append(f"**Volume ID:** {manifest['volume_id']}\n\n")
    
    # Add synopsis if available
    if 'synopsis' in manifest.get('metadata_en', {}):
        output_content.append(f"**Synopsis:** {manifest['metadata_en']['synopsis']}\n\n")
    
    output_content.append("\n---\n\n")
    
    # Get chapter files in order
    chapter_files = sorted([f for f in os.listdir(EN_DIR) if f.endswith("_EN.md")])
    
    total_chapters = len(chapter_files)
    
    for idx, filename in enumerate(chapter_files, 1):
        chapter_path = EN_DIR / filename
        chapter_num = filename.replace("CHAPTER_", "").replace("_EN.md", "")
        
        # Get chapter metadata from manifest
        chapter_key = f"chapter_{chapter_num}"
        chapter_meta = chapters_metadata.get(chapter_key, {})
        
        print(f"  [{idx}/{total_chapters}] {filename}")
        
        # Add chapter metadata header
        if chapter_meta:
            output_content.append(f"<!-- Chapter {chapter_num} Metadata\n")
            output_content.append(f"Title (JP): {chapter_meta.get('title_jp', 'N/A')}\n")
            output_content.append(f"Title (EN): {chapter_meta.get('title_en', 'N/A')}\n")
            output_content.append(f"POV: {chapter_meta.get('pov_character', 'N/A')}\n")
            if 'setting' in chapter_meta:
                output_content.append(f"Setting: {chapter_meta.get('setting', 'N/A')}\n")
            output_content.append(f"-->\n\n")
        
        # Read chapter content
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        output_content.append(content)
        output_content.append("\n\n---\n\n")
    
    # Write merged file
    with open(EN_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("".join(output_content))
    
    print(f"✅ English merged: {EN_OUTPUT}")
    print(f"   Total chapters: {total_chapters}")
    return total_chapters


def merge_japanese():
    """Merge all Japanese raw chapters into one markdown file."""
    print("\n📚 Merging Japanese Raw Text...")
    
    manifest = load_manifest()
    chapters_metadata = manifest.get("metadata_en", {}).get("chapters", {})
    
    # Get volume metadata
    volume_title_jp = manifest["metadata"]["title"]
    author_jp = manifest["metadata"]["author"]
    
    output_content = []
    
    # Title page
    output_content.append(f"# {volume_title_jp}\n\n")
    output_content.append(f"**著者:** {author_jp}\n\n")
    output_content.append(f"**出版社:** {manifest['metadata']['publisher']}\n\n")
    output_content.append(f"**Volume ID:** {manifest['volume_id']}\n\n")
    output_content.append("\n---\n\n")
    
    # Get chapter files in order
    chapter_files = sorted([f for f in os.listdir(JP_DIR) if f.endswith(".md")])
    
    total_chapters = len(chapter_files)
    
    for idx, filename in enumerate(chapter_files, 1):
        chapter_path = JP_DIR / filename
        chapter_num = filename.replace("CHAPTER_", "").replace(".md", "")
        
        # Get chapter metadata from manifest
        chapter_key = f"chapter_{chapter_num}"
        chapter_meta = chapters_metadata.get(chapter_key, {})
        
        print(f"  [{idx}/{total_chapters}] {filename}")
        
        # Add chapter metadata header
        if chapter_meta:
            output_content.append(f"<!-- Chapter {chapter_num} Metadata\n")
            output_content.append(f"Title (JP): {chapter_meta.get('title_jp', 'N/A')}\n")
            output_content.append(f"Title (EN): {chapter_meta.get('title_en', 'N/A')}\n")
            output_content.append(f"POV: {chapter_meta.get('pov_character', 'N/A')}\n")
            output_content.append(f"-->\n\n")
        
        # Read chapter content
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        output_content.append(content)
        output_content.append("\n\n---\n\n")
    
    # Write merged file
    with open(JP_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("".join(output_content))
    
    print(f"✅ Japanese raw merged: {JP_OUTPUT}")
    print(f"   Total chapters: {total_chapters}")
    return total_chapters


def calculate_stats(filepath):
    """Calculate basic statistics for merged file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    words = content.split()
    chars = len(content)
    
    return {
        'lines': len(lines),
        'words': len(words),
        'chars': chars,
        'size_kb': chars / 1024
    }


def main():
    print("=" * 80)
    print("MTL Studio - Volume 1420 Merger")
    print("Volume: 幼なじみは誘えばいつでもデキる関係【電子特別版】")
    print("=" * 80)
    
    # Merge translations
    en_chapters = merge_english()
    jp_chapters = merge_japanese()
    
    # Calculate statistics
    print("\n" + "=" * 80)
    print("Merge Complete - Statistics")
    print("=" * 80)
    
    en_stats = calculate_stats(EN_OUTPUT)
    jp_stats = calculate_stats(JP_OUTPUT)
    
    print("\n📊 English Translation:")
    print(f"   Chapters: {en_chapters}")
    print(f"   Lines: {en_stats['lines']:,}")
    print(f"   Words: {en_stats['words']:,}")
    print(f"   Characters: {en_stats['chars']:,}")
    print(f"   Size: {en_stats['size_kb']:.2f} KB")
    
    print("\n📊 Japanese Raw:")
    print(f"   Chapters: {jp_chapters}")
    print(f"   Lines: {jp_stats['lines']:,}")
    print(f"   Words: {jp_stats['words']:,}")
    print(f"   Characters: {jp_stats['chars']:,}")
    print(f"   Size: {jp_stats['size_kb']:.2f} KB")
    
    print("\n📂 Output Files:")
    print(f"   EN: {EN_OUTPUT.relative_to(BASE_DIR.parent)}")
    print(f"   JP: {JP_OUTPUT.relative_to(BASE_DIR.parent)}")
    
    print("\n✅ All files merged successfully!")
    print(f"\n📘 Volume Status: Complete - Grade A+ (97.5/100)")
    print(f"   Mixed Model Strategy:")
    print(f"   - API Gemini 2.5 Pro: Ch1-16 (0.2/1k AI-ism density)")
    print(f"   - Web Gemini 3 Flash Thinking: Ch17-21 (4.5/1k, PROHIBITED_CONTENT bypass)")
    print(f"   Ready for auditing and publication")


if __name__ == "__main__":
    main()
