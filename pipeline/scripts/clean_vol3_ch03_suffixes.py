#!/usr/bin/env python3
"""
Clean up narration suffixes in Vol 3 Chapter 03.
Target: Emma-chan and Charlotte-san in Akihito's narration.
Preserve: Suffixes in dialogue (between quotes).
"""

import re
from pathlib import Path

def is_in_dialogue(text, position):
    """Check if position is within dialogue (between quotes)"""
    # Count quotes before this position
    before = text[:position]
    # Check various quote types
    quote_count = before.count('"') + before.count('"') + before.count('"')
    # Odd number means we're inside dialogue
    return quote_count % 2 == 1

def clean_narration_suffixes(text):
    """Remove Emma-chan and Charlotte-san from narration only"""
    changes = []
    
    # Find all Emma-chan instances
    for match in re.finditer(r'\bEmma-chan\b', text):
        if not is_in_dialogue(text, match.start()):
            changes.append({
                'pos': match.start(),
                'old': 'Emma-chan',
                'new': 'Emma',
                'context': text[max(0, match.start()-40):match.end()+40]
            })
    
    # Find all Charlotte-san instances
    for match in re.finditer(r'\bCharlotte-san\b', text):
        if not is_in_dialogue(text, match.start()):
            changes.append({
                'pos': match.start(),
                'old': 'Charlotte-san',
                'new': 'Charlotte',
                'context': text[max(0, match.start()-40):match.end()+40]
            })
    
    # Sort by position (reverse) to apply changes from end to start
    changes.sort(key=lambda x: x['pos'], reverse=True)
    
    # Apply changes
    new_text = text
    for change in changes:
        pos = change['pos']
        old = change['old']
        new = change['new']
        new_text = new_text[:pos] + new + new_text[pos+len(old):]
    
    return new_text, changes

def main():
    vol3_dir = Path("WORK/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (3)_20260127_0019")
    chapter_path = vol3_dir / "EN" / "CHAPTER_03_EN.md"
    
    print("=" * 70)
    print("CLEANING VOL 3 CHAPTER 03 NARRATION SUFFIXES")
    print("=" * 70)
    
    # Load chapter
    with open(chapter_path, 'r', encoding='utf-8') as f:
        original_text = f.read()
    
    # Clean suffixes
    cleaned_text, changes = clean_narration_suffixes(original_text)
    
    print(f"\nFound {len(changes)} narration suffix instances to clean:")
    print()
    
    # Group by type
    emma_changes = [c for c in changes if 'Emma' in c['old']]
    charlotte_changes = [c for c in changes if 'Charlotte' in c['old']]
    
    print(f"Emma-chan: {len(emma_changes)} instances")
    for i, change in enumerate(emma_changes[:5], 1):
        print(f"  {i}. Line ~{change['context'][:50]}...")
    if len(emma_changes) > 5:
        print(f"  ... and {len(emma_changes) - 5} more")
    
    print(f"\nCharlotte-san: {len(charlotte_changes)} instances")
    for i, change in enumerate(charlotte_changes[:5], 1):
        print(f"  {i}. Line ~{change['context'][:50]}...")
    if len(charlotte_changes) > 5:
        print(f"  ... and {len(charlotte_changes) - 5} more")
    
    if not changes:
        print("\n✓ No narration suffixes found - chapter already clean!")
        return
    
    # Create backup
    backup_path = chapter_path.with_suffix('.md.backup_suffix_cleanup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(original_text)
    print(f"\n✓ Backup created: {backup_path.name}")
    
    # Save cleaned version
    with open(chapter_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_text)
    
    print(f"\n✓ Chapter cleaned successfully!")
    print(f"  Original length: {len(original_text):,} chars")
    print(f"  Cleaned length: {len(cleaned_text):,} chars")
    print(f"  Difference: {len(original_text) - len(cleaned_text):+,} chars")
    print(f"  Changes applied: {len(changes)}")
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    main()
