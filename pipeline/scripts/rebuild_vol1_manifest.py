#!/usr/bin/env python3
"""
Rebuild Vol 1 (25b4) manifest to v3.6_enhanced schema.
Upgrades from legacy format to full v3.6 compliance.
"""

import json
import re
from pathlib import Path
from datetime import datetime

def rebuild_vol1_manifest():
    vol1_dir = Path("WORK/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (1)_20260126_25b4")
    manifest_path = vol1_dir / "manifest.json"
    metadata_en_path = vol1_dir / "metadata_en.json"
    
    print("=" * 70)
    print("VOL 1 (25b4) MANIFEST REBUILD TO v3.6_enhanced")
    print("=" * 70)
    
    # Create backup
    backup_path = vol1_dir / f"manifest.json.backup_rebuild_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if manifest_path.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            current_manifest = json.load(f)
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(current_manifest, f, ensure_ascii=False, indent=2)
        print(f"✓ Backup created: {backup_path.name}\n")
    
    # Load metadata_en.json for character profiles
    print("Loading metadata_en.json...")
    if metadata_en_path.exists():
        with open(metadata_en_path, 'r', encoding='utf-8') as f:
            metadata_en = json.load(f)
    else:
        print("⚠ metadata_en.json not found, using defaults")
        metadata_en = {}
    
    # Extract from current manifest
    print("Extracting data from current manifest...")
    chapters = current_manifest.get('chapters', [])
    assets = current_manifest.get('assets', {})
    toc = current_manifest.get('toc', [])
    ruby_names = current_manifest.get('ruby_names', [])
    
    print(f"  ✓ Extracted {len(chapters)} chapters")
    print(f"  ✓ Extracted assets")
    print(f"  ✓ Extracted toc")
    print(f"  ✓ Extracted {len(ruby_names)} ruby_names")
    
    # Check JP folder for source files
    jp_dir = vol1_dir / "JP"
    has_cover_file = (jp_dir / "cover.jpg").exists() or (jp_dir / "cover.md").exists()
    has_kuchie_file = (jp_dir / "kuchie.md").exists()
    
    # Build v3.6_enhanced structure
    print("\nBuilding v3.6 enhanced structure...")
    
    manifest = {
        "schema_version": "v3.6_enhanced",
        "volume_id": "25b4",
        "created_at": datetime.now().isoformat(),
        "metadata": {
            "series": {
                "title": "迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について",
                "title_english": "About How a Beautiful Foreign Exchange Student Started Visiting My Home After I Helped a Lost Little Girl",
                "author": "鏡遊",
                "author_english": "Kagami Yu",
                "publisher": "ファンタジア文庫",
                "publisher_english": "Fantasia Bunko"
            },
            "publication": {
                "volume_number": 1,
                "publication_date": "2023-08-18",
                "isbn": "9784040751214"
            },
            "translation": {
                "translator": "MTL Studio",
                "translation_date": datetime.now().strftime("%Y-%m-%d"),
                "source_language": "Japanese",
                "target_language": "English",
                "model_primary": "gemini-2.0-flash-exp",
                "model_fallback": "gemini-2.5-flash"
            },
            "content_info": {
                "genre": ["slice_of_life", "romance", "comedy", "wholesome"],
                "genre_modifiers": ["wholesome", "jealousy_comedy"],
                "content_tags": [
                    "childhood_friends",
                    "foreign_exchange_student",
                    "neighbor_romance",
                    "slice_of_life",
                    "comedy",
                    "jealousy",
                    "wholesome",
                    "daily_life",
                    "school_life"
                ],
                "target_audience": "young_adult",
                "content_rating": "PG-13"
            },
            "character_profiles": metadata_en.get('character_profiles', []),
            "pov_tracking": [],
            "translation_guidance": {
                "tone": "casual_modern",
                "formality_level": "informal",
                "cultural_adaptation": "moderate",
                "honorifics_handling": "preserve_key_only",
                "genre_specific_notes": [
                    "wholesome: Keep narration clean, avoid Emma-chan/Charlotte-san in narration",
                    "jealousy_comedy: Preserve comedic timing and jealous reactions",
                    "slice_of_life: Natural conversational flow"
                ]
            },
            "localization_notes": {
                "name_order": "western_order_for_english_names",
                "cultural_references": [],
                "terminology": {},
                "style_notes": []
            },
            "sequel_continuity": {
                "volume_number": 1,
                "continuing_from": None,
                "continues_to": "Volume 2",
                "character_development_notes": [],
                "plot_threads": []
            }
        },
        "pipeline_state": {
            "preprocessor": current_manifest.get('pipeline_state', {}).get('preprocessor', {
                "status": "completed",
                "chapters_processed": len([ch for ch in chapters if not ch.get('is_pre_toc_content')]),
                "started_at": None,
                "completed_at": None
            }),
            "translator": current_manifest.get('pipeline_state', {}).get('translator', {
                "status": "completed",
                "chapters_total": len([ch for ch in chapters if not ch.get('is_pre_toc_content')]),
                "chapters_completed": len([ch for ch in chapters if ch.get('translation_status') == 'completed' and not ch.get('is_pre_toc_content')]),
                "started_at": None,
                "completed_at": None
            }),
            "quality_checker": current_manifest.get('pipeline_state', {}).get('quality_checker', {
                "status": "pending",
                "chapters_checked": 0,
                "started_at": None,
                "completed_at": None
            }),
            "epub_builder": current_manifest.get('pipeline_state', {}).get('epub_builder', {
                "status": "pending",
                "started_at": None,
                "completed_at": None
            })
        }
    }
    
    # Add POV tracking based on chapters
    print("Adding pov_tracking...")
    for chapter in chapters:
        if not chapter.get('is_pre_toc_content') and chapter.get('id', '').startswith('chapter_'):
            manifest['metadata']['pov_tracking'].append({
                "chapter_id": chapter['id'],
                "primary_pov": "akihito",
                "pov_switches": []
            })
    
    # Add chapters array (preserve existing or create new)
    print("Adding chapters array...")
    if chapters:
        # Use existing chapters
        manifest['chapters'] = chapters
        
        # Update cover/kuchie entries if they exist
        for chapter in manifest['chapters']:
            if chapter.get('id') == 'cover':
                if not has_cover_file:
                    chapter['translation_status'] = 'not_applicable'
                    chapter['skip_reason'] = 'cover_is_image_file'
            elif chapter.get('id') == 'kuchie':
                if not has_kuchie_file:
                    chapter['translation_status'] = 'not_applicable'
                    chapter['skip_reason'] = 'no_source_file_embedded_in_epub'
    else:
        # Create chapters from JP folder
        manifest['chapters'] = []
        
        # Add cover if exists
        if has_cover_file:
            manifest['chapters'].append({
                "id": "cover",
                "title": "Cover",
                "source_file": "cover.jpg" if (jp_dir / "cover.jpg").exists() else "cover.md",
                "output_file": "cover_EN.md",
                "translation_status": "pending",
                "is_pre_toc_content": True,
                "illustrations": ["kuchie-001.jpg"]
            })
        
        # Add kuchie if exists
        if has_kuchie_file:
            kuchie_illustrations = sorted([f.name for f in jp_dir.parent.glob("assets/kuchie-*.jpg")])
            manifest['chapters'].append({
                "id": "kuchie",
                "title": "Kuchi-e (Color Illustrations)",
                "source_file": "kuchie.md",
                "output_file": "kuchie_EN.md",
                "translation_status": "pending",
                "is_pre_toc_content": True,
                "illustrations": kuchie_illustrations
            })
        
        # Add chapter files from JP folder
        chapter_files = sorted(jp_dir.glob("CHAPTER_*.md"))
        for chapter_file in chapter_files:
            chapter_num = re.search(r'CHAPTER_(\d+)', chapter_file.name).group(1)
            manifest['chapters'].append({
                "id": f"chapter_{chapter_num}",
                "title": f"Chapter {chapter_num}",
                "source_file": chapter_file.name,
                "output_file": f"CHAPTER_{chapter_num}_EN.md",
                "translation_status": "pending",
                "is_pre_toc_content": False
            })
    
    # Add assets, toc, ruby_names
    print("Adding assets, toc, ruby_names...")
    manifest['assets'] = assets
    manifest['toc'] = toc
    manifest['ruby_names'] = ruby_names
    
    # Write manifest
    print("\nWriting cleaned manifest to manifest.json...")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    # Count chapters and illustrations
    content_chapters = [ch for ch in manifest['chapters'] if not ch.get('is_pre_toc_content')]
    pre_toc_chapters = [ch for ch in manifest['chapters'] if ch.get('is_pre_toc_content')]
    
    all_illustrations = []
    for chapter in manifest['chapters']:
        all_illustrations.extend(chapter.get('illustrations', []))
    
    cover_illustrations = [ill for ill in all_illustrations if 'kuchie-001' in ill or 'cover' in ill]
    kuchie_illustrations = [ill for ill in all_illustrations if 'kuchie' in ill]
    in_chapter_illustrations = [ill for ill in all_illustrations if 'illust' in ill]
    
    print("\n" + "=" * 70)
    print("✓ Vol 1 manifest rebuilt successfully!")
    print("=" * 70)
    print(f"  Schema version: v3.6_enhanced")
    print(f"  Total chapters: {len(manifest['chapters'])} ({len(content_chapters)} content + {len(pre_toc_chapters)} pre-TOC)")
    print(f"  Character profiles: {len(manifest['metadata']['character_profiles'])}")
    print(f"  POV tracking: {len(manifest['metadata']['pov_tracking'])} chapters")
    print(f"  Illustration count: {len(set(all_illustrations))}")
    print(f"    - Cover: {len(set(cover_illustrations))}")
    print(f"    - Kuchie: {len(set(kuchie_illustrations))}")
    print(f"    - In-chapter: {len(set(in_chapter_illustrations))}")
    print(f"\nBackup saved as: {backup_path.name}")
    print("=" * 70)

if __name__ == '__main__':
    rebuild_vol1_manifest()
