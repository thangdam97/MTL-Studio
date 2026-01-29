#!/usr/bin/env python3
"""
Merge Translation Files
Merges all chapter files from MTL Studio, FTL, and Japanese raw versions into single markdown files.

Usage:
    python merge_translations.py
"""

import os
import json
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORK_DIR = BASE_DIR / "pipeline" / "WORK"
AUDITING_DIR = BASE_DIR / ".auditing"
FTL_DIR = AUDITING_DIR / "1cca_FTL"

# Find 1cca volume directory
VOLUME_DIR = None
for dir_name in os.listdir(WORK_DIR):
    if "1cca" in dir_name:
        VOLUME_DIR = WORK_DIR / dir_name
        break

if not VOLUME_DIR:
    print("❌ Error: Could not find 1cca volume directory")
    exit(1)

MTL_EN_DIR = VOLUME_DIR / "EN"
MTL_JP_DIR = VOLUME_DIR / "JP"
MANIFEST_PATH = VOLUME_DIR / "manifest.json"

# Output paths
MTL_OUTPUT = AUDITING_DIR / "1cca_MTL_Studio_Full.md"
FTL_OUTPUT = AUDITING_DIR / "1cca_FTL_Full.md"
JP_OUTPUT = AUDITING_DIR / "1cca_JP_Raw_Full.md"


def load_manifest():
    """Load manifest.json to get chapter metadata."""
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def merge_mtl_studio():
    """Merge all MTL Studio EN chapters into one markdown file."""
    print("\n📚 Merging MTL Studio Translation...")
    
    manifest = load_manifest()
    chapters_metadata = manifest.get("metadata_en", {}).get("chapters", {})
    
    # Get volume metadata
    volume_title = manifest["metadata_en"]["title_en"]
    author = manifest["metadata_en"]["author_en"]
    
    output_content = []
    
    # Title page
    output_content.append(f"# {volume_title}\n")
    output_content.append(f"**Author:** {author}\n")
    output_content.append(f"**Translation:** MTL Studio v3.0 LTS\n")
    output_content.append(f"**Quality Grade:** A+ (FFXVI-Tier)\n")
    output_content.append(f"**Volume ID:** {manifest['volume_id']}\n")
    output_content.append("\n---\n\n")
    
    # Get chapter files in order
    chapter_files = sorted([f for f in os.listdir(MTL_EN_DIR) if f.endswith("_EN.md")])
    
    total_chapters = len(chapter_files)
    
    for idx, filename in enumerate(chapter_files, 1):
        chapter_path = MTL_EN_DIR / filename
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
            output_content.append(f"Setting: {chapter_meta.get('setting', 'N/A')}\n")
            output_content.append(f"-->\n\n")
        
        # Read chapter content
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        output_content.append(content)
        output_content.append("\n\n---\n\n")
    
    # Write merged file
    with open(MTL_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("".join(output_content))
    
    print(f"✅ MTL Studio merged: {MTL_OUTPUT}")
    print(f"   Total chapters: {total_chapters}")
    return total_chapters


def merge_ftl():
    """Merge all FTL chapters into one markdown file."""
    print("\n📚 Merging FTL Translation...")
    
    output_content = []
    
    # Title page
    output_content.append("# I Saved Two Man-Hating Beauties Without Giving My Name... Now What? - Volume 1\n")
    output_content.append("**Author:** Myon\n")
    output_content.append("**Translation:** Fan Translation (FTL)\n")
    output_content.append("**Quality Grade:** C (Serviceable)\n")
    output_content.append("\n---\n\n")
    
    # Define chapter order
    chapter_order = [
        ("Prologue.txt", "Prologue"),
        ("Chapter_1.txt", "Chapter 1: A pumpkin that laughs at the awakened female heart"),
        ("Chapter_2.txt", "Chapter 2: Serious time with the girls"),
        ("Chapter_3.txt", "Chapter 3"),
        ("Chapter_4.txt", "Chapter 4"),
        ("Chapter_5.txt", "Chapter 5"),
        ("Chapter_6.txt", "Chapter 6"),
        ("Epilogue.txt", "Epilogue"),
    ]
    
    total_chapters = 0
    
    for filename, title in chapter_order:
        chapter_path = FTL_DIR / filename
        
        if not chapter_path.exists():
            print(f"  ⚠️  Skipping {filename} (not found)")
            continue
        
        total_chapters += 1
        print(f"  [{total_chapters}] {filename}")
        
        # Add chapter header
        output_content.append(f"# {title}\n\n")
        
        # Read chapter content
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        output_content.append(content)
        output_content.append("\n\n---\n\n")
    
    # Write merged file
    with open(FTL_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("".join(output_content))
    
    print(f"✅ FTL merged: {FTL_OUTPUT}")
    print(f"   Total chapters: {total_chapters}")
    return total_chapters


def merge_jp_raw():
    """Merge all Japanese raw chapters into one markdown file."""
    print("\n📚 Merging Japanese Raw Text...")
    
    manifest = load_manifest()
    chapters_metadata = manifest.get("metadata_en", {}).get("chapters", {})
    
    # Get volume metadata
    volume_title_jp = manifest["metadata"]["title"]
    author_jp = manifest["metadata"]["author"]
    
    output_content = []
    
    # Title page
    output_content.append(f"# {volume_title_jp}\n")
    output_content.append(f"**著者:** {author_jp}\n")
    output_content.append(f"**出版社:** {manifest['metadata']['publisher']}\n")
    output_content.append(f"**Volume ID:** {manifest['volume_id']}\n")
    output_content.append("\n---\n\n")
    
    # Get chapter files in order
    chapter_files = sorted([f for f in os.listdir(MTL_JP_DIR) if f.endswith(".md")])
    
    total_chapters = len(chapter_files)
    
    for idx, filename in enumerate(chapter_files, 1):
        chapter_path = MTL_JP_DIR / filename
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
    print("=" * 60)
    print("MTL Studio - Translation Merger")
    print("Volume: 男嫌いな美人姉妹を名前も告げずに助けたら一体どうなる？1")
    print("=" * 60)
    
    # Ensure output directory exists
    AUDITING_DIR.mkdir(exist_ok=True)
    
    # Merge translations
    mtl_chapters = merge_mtl_studio()
    ftl_chapters = merge_ftl()
    jp_chapters = merge_jp_raw()
    
    # Calculate statistics
    print("\n" + "=" * 60)
    print("Merge Complete - Statistics")
    print("=" * 60)
    
    mtl_stats = calculate_stats(MTL_OUTPUT)
    ftl_stats = calculate_stats(FTL_OUTPUT)
    jp_stats = calculate_stats(JP_OUTPUT)
    
    print("\n📊 MTL Studio Version:")
    print(f"   Chapters: {mtl_chapters}")
    print(f"   Lines: {mtl_stats['lines']:,}")
    print(f"   Words: {mtl_stats['words']:,}")
    print(f"   Size: {mtl_stats['size_kb']:.2f} KB")
    
    print("\n📊 FTL Version:")
    print(f"   Chapters: {ftl_chapters}")
    print(f"   Lines: {ftl_stats['lines']:,}")
    print(f"   Words: {ftl_stats['words']:,}")
    print(f"   Size: {ftl_stats['size_kb']:.2f} KB")
    
    print("\n📊 Japanese Raw:")
    print(f"   Chapters: {jp_chapters}")
    print(f"   Lines: {jp_stats['lines']:,}")
    print(f"   Words: {jp_stats['words']:,}")
    print(f"   Size: {jp_stats['size_kb']:.2f} KB")
    
    print("\n📂 Output Files:")
    print(f"   MTL: {MTL_OUTPUT.relative_to(BASE_DIR)}")
    print(f"   FTL: {FTL_OUTPUT.relative_to(BASE_DIR)}")
    print(f"   JP:  {JP_OUTPUT.relative_to(BASE_DIR)}")
    
    print("\n✅ All translations merged successfully!")


if __name__ == "__main__":
    main()
