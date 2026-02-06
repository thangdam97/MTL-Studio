#!/usr/bin/env python3
"""
Reset Vol 3 translation status: 
- Mark cover/kuchie as not_applicable (no source files to translate)
- Reset all content chapters to pending
- Update pipeline_state accordingly
"""

import json
from pathlib import Path

def reset_translation_status():
    vol3_dir = Path("WORK/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (3)_20260127_0019")
    manifest_path = vol3_dir / "manifest.json"
    
    # Load manifest
    print("Loading manifest...")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    # Create backup
    backup_path = vol3_dir / "manifest.json.backup_before_status_reset"
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"✓ Backup created: {backup_path.name}\n")
    
    # Update chapter translation statuses
    chapters = manifest.get('chapters', [])
    total_chapters = len(chapters)
    reset_count = 0
    
    print("Updating chapter statuses:")
    for chapter in chapters:
        chapter_id = chapter.get('id', '')
        current_status = chapter.get('translation_status', '')
        
        # Handle cover and kuchie - mark as not_applicable
        if chapter_id == 'cover':
            chapter['translation_status'] = 'not_applicable'
            chapter['skip_reason'] = 'cover_is_image_file'
            print(f"  ✓ {chapter_id}: {current_status} → not_applicable (image file)")
            reset_count += 1
        elif chapter_id == 'kuchie':
            chapter['translation_status'] = 'not_applicable'
            chapter['skip_reason'] = 'no_source_file_embedded_in_epub'
            print(f"  ✓ {chapter_id}: {current_status} → not_applicable (embedded content)")
            reset_count += 1
        # Reset content chapters to pending
        else:
            if current_status == 'completed':
                chapter['translation_status'] = 'pending'
                print(f"  ✓ {chapter_id}: {current_status} → pending")
                reset_count += 1
            elif current_status == 'failed':
                chapter['translation_status'] = 'pending'
                print(f"  ✓ {chapter_id}: {current_status} → pending")
                reset_count += 1
    
    # Update pipeline_state
    if 'pipeline_state' in manifest:
        translator_state = manifest['pipeline_state'].get('translator', {})
        
        # Calculate translatable chapters (exclude not_applicable)
        translatable_chapters = [ch for ch in chapters if ch.get('translation_status') != 'not_applicable']
        translator_state['chapters_total'] = len(translatable_chapters)
        translator_state['chapters_completed'] = 0
        translator_state['status'] = 'pending'
        translator_state['started_at'] = None
        translator_state['completed_at'] = None
        
        manifest['pipeline_state']['translator'] = translator_state
        print(f"\n✓ Pipeline state updated:")
        print(f"    chapters_total: {len(translatable_chapters)} (excluding cover/kuchie)")
        print(f"    chapters_completed: 0")
        print(f"    status: pending")
    
    # Save updated manifest
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Manifest updated successfully!")
    print(f"    Total chapters: {total_chapters}")
    print(f"    Status changes: {reset_count}")
    print(f"    Translatable chapters: {len(translatable_chapters)}")
    print(f"    Non-translatable (cover/kuchie): 2")

if __name__ == '__main__':
    reset_translation_status()
