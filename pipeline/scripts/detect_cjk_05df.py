#!/usr/bin/env python3
"""CJK Character Leak Detector for 05df Volume"""

import re
from pathlib import Path

# CJK pattern
cjk_pattern = re.compile(
    r'[\u4E00-\u9FFF]|'  # CJK Unified Ideographs
    r'[\u3040-\u309F]|'  # Hiragana
    r'[\u30A0-\u30FF]|'  # Katakana
    r'[\uFF00-\uFFEF]|'  # Full-width forms
    r'[\u3000-\u303F]'   # CJK Punctuation
)

# Find 05df EN directory
work_dir = Path('WORK')
volume_dirs = [d for d in work_dir.iterdir() if d.is_dir() and '05df' in d.name]

if not volume_dirs:
    print('❌ 05df volume not found')
    exit(1)

en_dir = volume_dirs[0] / 'EN'
issues = []

print("=" * 80)
print("CJK CHARACTER LEAK DETECTION - Volume 05df")
print("=" * 80)

for chapter_file in sorted(en_dir.glob('CHAPTER_*_EN.md')):
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

print(f'\n📊 Results: Found {len(issues)} CJK characters in {len(list(en_dir.glob("CHAPTER_*_EN.md")))} chapters\n')

if issues:
    print('CJK Leaks Found:\n')
    for i, issue in enumerate(issues, 1):
        print(f'{i}. {issue["file"]}:{issue["line"]}')
        print(f'   Character: [{issue["char"]}] {issue["unicode"]}')
        print(f'   Context: ...{issue["context"]}...')
        print()
else:
    print('✅ No CJK character leaks found! Translation is clean.')
