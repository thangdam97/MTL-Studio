#!/usr/bin/env python3
"""CJK Character Leak Detector v2 - Universal for any volume ID"""

import re
import sys
from pathlib import Path

def detect_cjk_leaks(volume_id: str):
    """
    Detect CJK character leaks in English translation.
    
    Args:
        volume_id: Volume ID to scan (e.g., '1d46', '05df')
    """
    
    # CJK pattern - comprehensive detection
    cjk_pattern = re.compile(
        r'[\u4E00-\u9FFF]|'  # CJK Unified Ideographs
        r'[\u3040-\u309F]|'  # Hiragana
        r'[\u30A0-\u30FF]|'  # Katakana
        r'[\uFF00-\uFFEF]|'  # Full-width forms
        r'[\u3000-\u303F]'   # CJK Punctuation
    )
    
    # Find volume directory
    work_dir = Path(__file__).parent.parent / 'WORK'
    volume_dirs = [d for d in work_dir.iterdir() if d.is_dir() and volume_id in d.name]
    
    if not volume_dirs:
        print(f'❌ Volume {volume_id} not found in WORK directory')
        return None
    
    volume_dir = volume_dirs[0]
    en_dir = volume_dir / 'EN'
    
    if not en_dir.exists():
        print(f'❌ EN directory not found for volume {volume_id}')
        return None
    
    issues = []
    
    print("=" * 80)
    print(f"CJK CHARACTER LEAK DETECTION v2 - Volume {volume_id}")
    print(f"Volume: {volume_dir.name}")
    print("=" * 80)
    
    # Scan all EN markdown files
    chapter_files = sorted(en_dir.glob('CHAPTER_*_EN.md'))
    
    if not chapter_files:
        print(f'\n⚠️  No chapter files found in {en_dir}')
        return None
    
    for chapter_file in chapter_files:
        with open(chapter_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            matches = list(cjk_pattern.finditer(line))
            if matches:
                for match in matches:
                    char = match.group()
                    pos = match.start()
                    context_start = max(0, pos - 30)
                    context_end = min(len(line), pos + 30)
                    context = line[context_start:context_end].strip()
                    issues.append({
                        'file': chapter_file.name,
                        'line': line_num,
                        'char': char,
                        'unicode': f'U+{ord(char):04X}',
                        'context': context,
                        'full_line': line.strip()
                    })
    
    # Print results
    print(f'\n📊 Results: Found {len(issues)} CJK characters in {len(chapter_files)} chapters\n')
    
    if issues:
        print('⚠️  CJK Leaks Found:\n')
        for i, issue in enumerate(issues, 1):
            print(f'{i}. {issue["file"]}:{issue["line"]}')
            print(f'   Character: [{issue["char"]}] {issue["unicode"]}')
            print(f'   Context: ...{issue["context"]}...')
            print()
        
        # Summary by character type
        hiragana = [i for i in issues if '\u3040' <= i['char'] <= '\u309F']
        katakana = [i for i in issues if '\u30A0' <= i['char'] <= '\u30FF']
        kanji = [i for i in issues if '\u4E00' <= i['char'] <= '\u9FFF']
        punctuation = [i for i in issues if '\u3000' <= i['char'] <= '\u303F' or '\uFF00' <= i['char'] <= '\uFFEF']
        
        print("=" * 80)
        print("SUMMARY BY CHARACTER TYPE")
        print("=" * 80)
        if hiragana:
            print(f'  Hiragana: {len(hiragana)} occurrences')
        if katakana:
            print(f'  Katakana: {len(katakana)} occurrences')
        if kanji:
            print(f'  Kanji: {len(kanji)} occurrences')
        if punctuation:
            print(f'  CJK Punctuation: {len(punctuation)} occurrences')
        print()
        
        return issues
    else:
        print('✅ No CJK character leaks found! Translation is clean.')
        return []


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python detect_cjk_v2.py <volume_id>")
        print("Example: python detect_cjk_v2.py 1d46")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    detect_cjk_leaks(volume_id)
