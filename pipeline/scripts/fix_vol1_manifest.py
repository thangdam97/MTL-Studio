#!/usr/bin/env python3
"""Fix Vol 1 manifest validation errors"""

import json
from pathlib import Path

vol1_dir = Path("WORK/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (1)_20260126_25b4")
manifest_path = vol1_dir / "manifest.json"

print("Loading manifest...")
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

# Fix translation_guidance - add genres array
print("Fixing translation_guidance.genres...")
manifest['metadata']['translation_guidance']['genres'] = manifest['metadata']['content_info']['genre']

# Fix content_info - add tags array and synopsis
print("Fixing content_info.tags and synopsis_en...")
manifest['metadata']['content_info']['tags'] = manifest['metadata']['content_info']['content_tags']
manifest['metadata']['content_info']['synopsis_en'] = "After helping a lost little girl, Akihito's life takes an unexpected turn when Charlotte, a beautiful foreign exchange student living next door, starts visiting his home regularly. As their friendship deepens, complications arise with the arrival of Emma, Charlotte's younger sister, leading to comedic situations filled with jealousy and misunderstandings."

# Save
print("Saving manifest...")
with open(manifest_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print("\n✓ Fixed translation_guidance.genres")
print("✓ Fixed content_info.tags and synopsis_en")
print("\nManifest updated successfully!")
