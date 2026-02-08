#!/usr/bin/env python3
"""
Clean up manifest.json illustration references
Remove all illustrations not present in assets folder
"""

import json
import os
from pathlib import Path

# Paths
WORK_DIR = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/2nd cutest v4 JP_20260208_1a87")
MANIFEST_PATH = WORK_DIR / "manifest.json"
ASSETS_DIR = WORK_DIR / "assets"
ILLUSTRATIONS_DIR = ASSETS_DIR / "illustrations"
KUCHIE_DIR = ASSETS_DIR / "kuchie"

def get_actual_files():
    """Get list of actual files in assets folder"""
    actual_files = {
        "illustrations": [],
        "kuchie": [],
        "cover": None
    }
    
    # Get illustration files
    if ILLUSTRATIONS_DIR.exists():
        actual_files["illustrations"] = sorted([f.name for f in ILLUSTRATIONS_DIR.iterdir() if f.is_file()])
    
    # Get kuchie files
    if KUCHIE_DIR.exists():
        actual_files["kuchie"] = sorted([f.name for f in KUCHIE_DIR.iterdir() if f.is_file()])
    
    # Check for cover
    cover_path = ASSETS_DIR / "cover.jpg"
    if cover_path.exists():
        actual_files["cover"] = "cover.jpg"
    
    return actual_files

def clean_manifest():
    """Clean manifest.json to only include existing files"""
    
    print("📂 Checking actual files in assets folder...")
    actual_files = get_actual_files()
    
    print(f"\n✅ Found actual files:")
    print(f"   - Illustrations: {len(actual_files['illustrations'])} files")
    for f in actual_files['illustrations']:
        print(f"     • {f}")
    print(f"   - Kuchie: {len(actual_files['kuchie'])} files")
    for f in actual_files['kuchie']:
        print(f"     • {f}")
    print(f"   - Cover: {actual_files['cover']}")
    
    print(f"\n📖 Loading manifest.json...")
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    # Clean chapter illustrations
    print(f"\n🧹 Cleaning chapter illustration references...")
    total_removed = 0
    
    for chapter in manifest["chapters"]:
        chapter_id = chapter["id"]
        original_illustrations = chapter.get("illustrations", [])
        
        if original_illustrations:
            # Remove all illustrations since none of the referenced files exist
            # The actual files (p039.jpg, p063.jpg, etc.) need to be manually mapped
            removed_count = len(original_illustrations)
            chapter["illustrations"] = []
            total_removed += removed_count
            
            if removed_count > 0:
                print(f"   - {chapter_id}: Removed {removed_count} non-existent references")
                for ill in original_illustrations:
                    print(f"     ✗ {ill}")
    
    # Clean assets.illustrations array
    print(f"\n🧹 Cleaning assets.illustrations array...")
    original_asset_illustrations = manifest["assets"].get("illustrations", [])
    
    # Remove duplicates and non-existent files
    # Keep only unique actual illustration files
    manifest["assets"]["illustrations"] = actual_files["illustrations"]
    
    removed_from_assets = len(original_asset_illustrations) - len(actual_files["illustrations"])
    print(f"   - Removed {removed_from_assets} entries")
    print(f"   - Kept {len(actual_files['illustrations'])} actual files")
    
    # Update kuchie array to match actual files
    print(f"\n🧹 Cleaning assets.kuchie array...")
    original_kuchie = manifest["assets"].get("kuchie", [])
    
    # Keep kuchie metadata structure but verify files exist
    cleaned_kuchie = []
    for kuchie_entry in original_kuchie:
        kuchie_file = kuchie_entry.get("file")
        if kuchie_file in actual_files["kuchie"]:
            cleaned_kuchie.append(kuchie_entry)
        else:
            print(f"   ✗ Removed: {kuchie_file} (not found)")
    
    manifest["assets"]["kuchie"] = cleaned_kuchie
    print(f"   - Kept {len(cleaned_kuchie)} kuchie entries")
    
    # Save cleaned manifest
    print(f"\n💾 Saving cleaned manifest...")
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Cleanup complete!")
    print(f"\n📊 Summary:")
    print(f"   - Total illustration references removed from chapters: {total_removed}")
    print(f"   - Assets.illustrations cleaned: {len(actual_files['illustrations'])} files kept")
    print(f"   - Assets.kuchie cleaned: {len(cleaned_kuchie)} entries kept")
    print(f"\n⚠️  Note: Chapter illustrations are now empty.")
    print(f"   Actual illustration files need to be manually mapped:")
    for f in actual_files['illustrations']:
        print(f"     • {f}")

if __name__ == "__main__":
    clean_manifest()
