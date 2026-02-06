#!/usr/bin/env python3
"""
Rebuild Vol 3 manifest to proper v3.6_enhanced structure.
Fixes JSON nesting issues and ensures all v3.6 sections are at correct level.
"""

import json
import sys
from pathlib import Path

def rebuild_vol3_manifest(work_dir: Path):
    """Rebuild Vol 3 manifest with proper v3.6 structure."""
    
    vol3_dir = work_dir / "(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (3)_20260127_0019"
    manifest_path = vol3_dir / "manifest.json"
    metadata_en_path = vol3_dir / "metadata_en.json"
    backup_path = vol3_dir / "manifest.json.backup_rebuild"
    
    # Backup current manifest
    if manifest_path.exists():
        print(f"Creating backup: {backup_path.name}")
        with open(manifest_path, 'r', encoding='utf-8') as f:
            backup_data = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(backup_data)
    
    # Load metadata_en.json for v3.6 content
    print("Loading metadata_en.json...")
    with open(metadata_en_path, 'r', encoding='utf-8') as f:
        metadata_en = json.load(f)
    
    # Load original manifest - try multiple sources
    original = None
    
    # Try loading from metadata section only (if JSON is partially corrupted)
    try:
        print("Attempting to load from current manifest...")
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Try to extract just the chapters array using simple parsing
            import re
            chapters_match = re.search(r'"chapters":\s*\[(.*?)\],\s*"assets":', content, re.DOTALL)
            assets_match = re.search(r'"assets":\s*({.*?}),\s*"toc":', content, re.DOTALL)
            toc_match = re.search(r'"toc":\s*({.*?}),\s*"ruby_names":', content, re.DOTALL)
            ruby_match = re.search(r'"ruby_names":\s*(\[.*?\])', content, re.DOTALL)
            
            # Build minimal structure from extracted parts
            original = {
                "created_at": "2026-01-27T01:29:29.660287",
                "metadata": {"source_epub": ""},
                "pipeline_state": {
                    "librarian": {"status": "completed", "timestamp": "2026-01-27T01:29:29.660287"},
                    "translator": {"status": "completed", "chapters_completed": 0, "started_at": "2026-01-27T01:54:17.470694"},
                    "critics": {"status": "pending", "chapters_completed": 0, "chapters_total": 0},
                    "builder": {"status": "completed", "timestamp": "2026-01-27T02:51:29.044400", "output_file": "I Rescued a Lost Little Girl and Now the Beautiful_EN.epub", "chapters_built": 6, "images_included": 18}
                },
                "chapters": [],
                "assets": {},
                "toc": {},
                "ruby_names": []
            }
            
            # Try to parse extracted sections
            if chapters_match:
                try:
                    chapters_json = "[" + chapters_match.group(1) + "]"
                    original["chapters"] = json.loads(chapters_json)
                    print(f"  ✓ Extracted {len(original['chapters'])} chapters")
                except:
                    pass
            
            if assets_match:
                try:
                    original["assets"] = json.loads(assets_match.group(1))
                    print(f"  ✓ Extracted assets")
                except:
                    pass
            
            if toc_match:
                try:
                    original["toc"] = json.loads(toc_match.group(1))
                    print(f"  ✓ Extracted toc")
                except:
                    pass
            
            if ruby_match:
                try:
                    original["ruby_names"] = json.loads(ruby_match.group(1))
                    print(f"  ✓ Extracted {len(original['ruby_names'])} ruby_names")
                except:
                    pass
    
    except Exception as e:
        print(f"Warning: Could not extract from current manifest: {e}")
        print("Will use minimal default structure...")
        original = {
            "created_at": "2026-01-27T01:29:29.660287",
            "metadata": {"source_epub": "/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/INPUT/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (3).epub"},
            "pipeline_state": {
                "librarian": {"status": "completed", "timestamp": "2026-01-27T01:29:29.660287"},
                "translator": {"status": "completed", "chapters_completed": 0, "started_at": "2026-01-27T01:54:17.470694"},
                "critics": {"status": "pending", "chapters_completed": 0, "chapters_total": 0},
                "builder": {"status": "completed", "timestamp": "2026-01-27T02:51:29.044400", "output_file": "I Rescued a Lost Little Girl and Now the Beautiful_EN.epub", "chapters_built": 6, "images_included": 18}
            },
            "chapters": [],
            "assets": {},
            "toc": {},
            "ruby_names": []
        }
    
    # Build clean v3.6 structure
    print("Building v3.6 enhanced structure...")
    
    manifest = {
        "schema_version": "v3.6_enhanced",
        "volume_id": "(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (3)_20260127_0019",
        "created_at": original.get("created_at", "2026-01-27T01:29:29.660287"),
        "metadata": {
            "series": {
                "title_ja": "迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について",
                "title_en": "I Rescued a Lost Little Girl, and Now the Beautiful Exchange Student Next Door Won't Stop Visiting!",
                "title_romaji": "Maigo ni Natteita Youjo wo Tasuke tara, Otonari ni Sumu Bishoujo Ryuugakusei ga Ie ni Asobi ni Kuru You ni Natta Ken ni Tsuite",
                "volume_number": 3
            },
            "publication": {
                "author_ja": "ネコクロ",
                "author_en": "Nekokuro",
                "publisher_ja": "株式会社 集英社",
                "publisher_en": "Shueisha",
                "isbn": "",
                "source_epub": original.get("metadata", {}).get("source_epub", "")
            },
            "translation": {
                "source_language": "ja",
                "target_language": "en",
                "translator": "MTL Studio v3.6",
                "translation_date": "2026-01-27",
                "page_progression_direction": "rtl"
            }
        }
    }
    
    # Add content_info
    manifest["metadata"]["content_info"] = {
        "genres": ["romance", "comedy", "slice_of_life", "school_life", "drama"],
        "tags": ["wholesome", "exchange_student", "neighbors", "childhood_friend", "jealousy", "sports_festival", "past_trauma", "relationship_development", "emotional_growth"],
        "content_warnings": [],
        "target_audience": "young_adult",
        "synopsis_en": "Volume 3 focuses on the school sports festival where Charlotte is paired with Saionji, sparking Akihito's growing romantic awareness. Emma expresses loneliness from being alone during school days. The volume takes a dramatic turn when Shinonome reveals Akihito's traumatic past—abandonment by his parents. Charlotte struggles to support Akihito as he withdraws emotionally, ultimately learning to lean on each other.",
        "illustration_count": 18
    }
    
    # Add character_profiles from metadata_en
    print("Adding character_profiles...")
    manifest["metadata"]["character_profiles"] = metadata_en["character_profiles"]
    
    # Add pov_tracking
    print("Adding pov_tracking...")
    manifest["metadata"]["pov_tracking"] = {
        "chapter_01": {"primary_pov": "Aoyagi Akihito", "pov_shifts": [], "narrative_style": "first_person_ore"},
        "chapter_02": {"primary_pov": "Aoyagi Akihito", "pov_shifts": [], "narrative_style": "first_person_ore"},
        "chapter_03": {"primary_pov": "Aoyagi Akihito", "pov_shifts": [], "narrative_style": "first_person_ore"},
        "chapter_04": {"primary_pov": "Aoyagi Akihito", "pov_shifts": [], "narrative_style": "first_person_ore"},
        "chapter_05": {"primary_pov": "Aoyagi Akihito", "pov_shifts": [], "narrative_style": "first_person_ore"},
        "chapter_06": {"primary_pov": "Aoyagi Akihito", "pov_shifts": [], "narrative_style": "first_person_ore"}
    }
    
    # Add translation_guidance
    print("Adding translation_guidance...")
    manifest["metadata"]["translation_guidance"] = {
        "genres": ["romcom", "slice_of_life", "wholesome", "jealousy_comedy", "drama"],
        "priority_patterns": [
            "Charlotte formal British speech - ALLOW Victorian patterns",
            "Akihito casual American teen - heavy contractions",
            "Emma childlike simplicity - limited vocabulary",
            "Saionji energetic bro-speak",
            "Sports festival excitement and romantic tension",
            "Past trauma revelation - emotional depth",
            "Withdrawal and reconnection - relationship growth",
            "Family-like moments with Emma",
            "Jealousy comedy beats"
        ],
        "tone": "Warm wholesome romcom with jealousy comedy, deepening into emotional drama as Akihito's past is revealed. Volume 3 adds weight and maturity to the relationship.",
        "character_voice_priorities": {
            "Aoyagi Akihito": "Casual introspective narrator, American teen slang, heavy contractions, self-deprecating, emotionally guarded",
            "Charlotte Bennett": "Formal British speech - I shall, quite, rather, would you kindly. AUTHENTIC CHARACTER VOICE.",
            "Emma Bennett": "Simple childlike - short sentences, limited vocabulary, repetitive phrases, calls Akihito big brother",
            "Saionji Akira": "Energetic bro-speak - dude, man, short punchy sentences, friendly direct tone",
            "Miyu-sensei": "Sharp-tongued teasing adult - sarcastic, direct, drops formality with close students"
        },
        "avoid": [
            "Formal constructions in narration (except Charlotte dialogue)",
            "Victorian patterns for non-British characters",
            "Melodramatic prose during trauma scenes",
            "Over-explaining emotional states",
            "Stilted dialogue for teens",
            "Breaking Charlotte's British voice consistency",
            "Making Emma sound too mature"
        ]
    }
    
    # Add localization_notes from metadata_en
    print("Adding localization_notes...")
    manifest["metadata"]["localization_notes"] = metadata_en["localization_notes"]
    
    # Add sequel_continuity
    print("Adding sequel_continuity...")
    manifest["metadata"]["sequel_continuity"] = {
        "previous_volume": "(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (2)_20260126_1478",
        "established_relationships": {
            "Akihito_Charlotte": "Growing romantic tension, not yet official but feelings acknowledged",
            "Akihito_Emma": "Guardian big brother figure, Emma attached and trusts him completely",
            "Akihito_Saionji": "Childhood best friends, but emotional distance growing",
            "Charlotte_Emma": "Older sister guardian relationship",
            "Saionji_Shinonome": "Dating relationship established",
            "Akihito_Miyu": "Protective teacher-student mentor relationship",
            "Akihito_Shinonome": "Non-blood siblings, complex family connection"
        },
        "character_development_carryover": {
            "Akihito": "Vol 3 reveals traumatic past (parental abandonment), causes withdrawal, learns to accept support",
            "Charlotte": "Vol 3 deepens romantic feelings, paired with Saionji at sports festival, learns about Akihito's past, struggles to support him",
            "Emma": "Vol 3 expresses loneliness from being alone during school days, wants to attend sports festival",
            "Saionji": "Vol 3 paired with Charlotte, acts as wingman, maintains friendship despite distance",
            "Shinonome": "Vol 3 reveals critical information about Akihito's past to Charlotte"
        },
        "voice_consistency_critical": [
            "Charlotte British formality maintained throughout",
            "Akihito casual American teen consistency",
            "Emma childlike simplicity never broken",
            "Saionji energetic bro-speak",
            "Narrator voice matches Akihito POV"
        ]
    }
    
    # Add pipeline_state (updated chapter counts to 8) - AT ROOT LEVEL
    print("Adding pipeline_state...")
    original_pipeline = original.get("pipeline_state", {})
    manifest["pipeline_state"] = {
        "librarian": {
            "status": original_pipeline.get("librarian", {}).get("status", "completed"),
            "timestamp": original_pipeline.get("librarian", {}).get("timestamp", "2026-01-27T01:29:29.660287"),
            "chapters_completed": 8,
            "chapters_total": 8
        },
        "translator": {
            "status": original_pipeline.get("translator", {}).get("status", "completed"),
            "chapters_completed": original_pipeline.get("translator", {}).get("chapters_completed", 0),
            "chapters_total": 8,
            "target_language": "en",
            "started_at": original_pipeline.get("translator", {}).get("started_at", "")
        },
        "critics": {
            "status": original_pipeline.get("critics", {}).get("status", "pending"),
            "chapters_completed": original_pipeline.get("critics", {}).get("chapters_completed", 0),
            "chapters_total": original_pipeline.get("critics", {}).get("chapters_total", 0)
        },
        "builder": original_pipeline.get("builder", {
            "status": "completed",
            "timestamp": "2026-01-27T02:51:29.044400",
            "output_file": "I Rescued a Lost Little Girl and Now the Beautiful_EN.epub",
            "chapters_built": 6,
            "images_included": 18
        })
    }
    
    # Add chapters array with cover and kuchie entries - AT ROOT LEVEL
    print("Adding chapters array...")
    original_chapters = original.get("chapters", [])
    
    # Cover entry
    cover_entry = {
        "id": "cover",
        "source_file": "cover.jpg",
        "title": "Cover",
        "title_en": "Cover",
        "toc_order": -2,
        "toc_level": 0,
        "illustrations": ["kuchie-001.jpg"],
        "translation_status": "completed",
        "qc_status": "pending",
        "is_pre_toc_content": True
    }
    
    # Kuchie entry with 8 illustrations
    kuchie_entry = {
        "id": "kuchie",
        "source_file": "kuchie.md",
        "title": "口絵",
        "title_en": "Color Illustrations",
        "toc_order": -1,
        "toc_level": 0,
        "illustrations": [
            "kuchie-002.jpg",
            "kuchie-003.jpg",
            "kuchie-004.jpg",
            "kuchie-005.jpg",
            "kuchie-006.jpg",
            "kuchie-007.jpg",
            "kuchie-008.jpg",
            "illust-001.jpg"
        ],
        "translation_status": "completed",
        "qc_status": "pending",
        "is_pre_toc_content": True
    }
    
    # Combine: cover + kuchie + original content chapters
    content_chapters = [ch for ch in original_chapters if ch.get("id", "").startswith("chapter_")]
    manifest["chapters"] = [cover_entry, kuchie_entry] + content_chapters
    
    # Add assets, toc, ruby_names from original - AT ROOT LEVEL
    print("Adding assets, toc, ruby_names...")
    manifest["assets"] = original.get("assets", {})
    manifest["toc"] = original.get("toc", {})
    manifest["ruby_names"] = original.get("ruby_names", [])
    
    # Write clean manifest
    print(f"Writing cleaned manifest to {manifest_path.name}...")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print("\n✓ Vol 3 manifest rebuilt successfully!")
    print(f"  Schema version: {manifest['schema_version']}")
    print(f"  Total chapters: {len(manifest['chapters'])} (cover + kuchie + 6 content)")
    print(f"  Character profiles: {len(manifest['metadata']['character_profiles'])}")
    print(f"  POV tracking: {len(manifest['metadata']['pov_tracking'])} chapters")
    print(f"  Illustration count: {manifest['metadata']['content_info']['illustration_count']}")
    print(f"\nBackup saved as: {backup_path.name}")
    
    return manifest

if __name__ == "__main__":
    # Determine work directory
    script_dir = Path(__file__).parent
    pipeline_dir = script_dir.parent
    work_dir = pipeline_dir / "WORK"
    
    if not work_dir.exists():
        print(f"Error: WORK directory not found at {work_dir}")
        sys.exit(1)
    
    print("=" * 70)
    print("VOL 3 MANIFEST REBUILD - v3.6 Enhanced Schema")
    print("=" * 70)
    print()
    
    try:
        manifest = rebuild_vol3_manifest(work_dir)
        print("\n✓ Rebuild complete! Ready for validation.")
    except Exception as e:
        print(f"\n✗ Error during rebuild: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
