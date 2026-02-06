#!/usr/bin/env python3
"""
Merge all EN chapters from a volume into a single markdown file for auditing.

Usage:
    python merge_volume.py <volume_id>
    
Example:
    python merge_volume.py 超かぐや姫！_20260201_095d
"""

import os
import sys
import json
from pathlib import Path

def merge_volume(volume_id):
    """Merge all EN chapters from specified volume."""
    
    BASE_DIR = Path(__file__).resolve().parent.parent
    WORK_DIR = BASE_DIR / "WORK" / volume_id
    EN_DIR = WORK_DIR / "EN"
    MANIFEST_PATH = WORK_DIR / "manifest.json"
    OUTPUT_DIR = WORK_DIR / "audits"
    OUTPUT_PATH = OUTPUT_DIR / "FULL_EN_MERGED.md"
    
    # Validate paths
    if not WORK_DIR.exists():
        print(f"❌ Error: Volume directory not found: {WORK_DIR}")
        return False
    
    if not EN_DIR.exists():
        print(f"❌ Error: EN directory not found: {EN_DIR}")
        return False
    
    if not MANIFEST_PATH.exists():
        print(f"❌ Error: manifest.json not found: {MANIFEST_PATH}")
        return False
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Load manifest
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    # Get volume metadata
    metadata = manifest.get('metadata_en', manifest.get('metadata', {}))
    volume_title = metadata.get('title_en', metadata.get('title_jp', 'Unknown Title'))
    author = metadata.get('author_en', metadata.get('author_jp', 'Unknown Author'))
    volume_num = metadata.get('volume_number', '1')
    
    output_content = []
    
    # Title page
    output_content.append(f"# {volume_title}\n")
    output_content.append(f"**Author:** {author}\n")
    output_content.append(f"**Volume:** {volume_num}\n")
    output_content.append(f"**Translation:** MTL Studio (Literacy Techniques Enhanced)\n")
    output_content.append(f"**Volume ID:** {manifest['volume_id']}\n")
    output_content.append(f"**Date Merged:** 2026-02-04\n")
    output_content.append("\n---\n\n")
    
    # Get chapter files in order
    chapter_files = sorted([f for f in os.listdir(EN_DIR) if f.endswith('_EN.md')])
    
    if not chapter_files:
        print(f"❌ Error: No EN chapter files found in {EN_DIR}")
        return False
    
    total_chapters = len(chapter_files)
    print(f"📚 Merging {total_chapters} chapters from {volume_id}...")
    
    for idx, filename in enumerate(chapter_files, 1):
        chapter_path = EN_DIR / filename
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
    
    print(f"\n✅ Successfully merged {total_chapters} chapters")
    print(f"📄 Output: {OUTPUT_PATH}")
    print(f"📊 File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python merge_volume.py <volume_id>")
        print("Example: python merge_volume.py 超かぐや姫！_20260201_095d")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    success = merge_volume(volume_id)
    sys.exit(0 if success else 1)
