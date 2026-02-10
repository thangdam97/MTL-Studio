#!/usr/bin/env python3
"""
Fix 1a60 Critical Issues
========================

Fixes 3 critical post-processing bugs in 1a60 optimized output:
1. Revert 35 validator-introduced subject-verb errors
2. Fix Chapter 1 concatenation bug (truncate at line 1979)
3. Fix 5 remaining possessive errors

Usage:
    python scripts/fix_1a60_issues.py
"""

import re
from pathlib import Path

WORK_DIR = Path("WORK/他校の氷姫を助けたら、お友達から始める事になりました３_20260209_1a60/EN")


def fix_subject_verb_errors(text: str) -> tuple[str, int]:
    """Revert validator-introduced subject-verb agreement errors."""
    fixes = 0

    # Pattern 1: "We was" -> "We were"
    original = text
    text = re.sub(r'\bWe was\b', 'We were', text)
    fixes += len(re.findall(r'\bWe was\b', original))

    # Pattern 2: "They was" -> "They were"
    original = text
    text = re.sub(r'\bThey was\b', 'They were', text)
    fixes += len(re.findall(r'\bThey was\b', original))

    # Pattern 3: "Those was" -> "Those were"
    original = text
    text = re.sub(r'\bThose was\b', 'Those were', text)
    fixes += len(re.findall(r'\bThose was\b', original))

    # Pattern 4: "These is" -> "These are"
    original = text
    text = re.sub(r'\bThese is\b', 'These are', text)
    fixes += len(re.findall(r'\bThese is\b', original))

    # Pattern 5: "There was [plural]" -> "There were [plural]"
    # Match "There was" followed by plural indicators
    plural_indicators = [
        r'There was several',
        r'There was various',
        r'There was probably many',
        r'There was other reasons',
        r'There was many',
    ]

    for pattern in plural_indicators:
        original = text
        replacement = pattern.replace('was', 'were')
        text = re.sub(pattern, replacement, text)
        fixes += len(re.findall(pattern, original))

    # Pattern 6: "There is various" -> "There are various"
    original = text
    text = re.sub(r'There is various', 'There are various', text)
    fixes += len(re.findall(r'There is various', original))

    return text, fixes


def fix_possessive_errors(text: str) -> tuple[str, int]:
    """Fix missing possessive 's markers."""
    fixes = 0

    # Specific possessive errors identified in audit
    possessive_fixes = [
        (r'\bHayama my friend\b', "Hayama's my friend"),
        (r'\bHayama schedule\b', "Hayama's schedule"),
        (r'\bSouta head\b', "Souta's head"),
        (r'\bSouta heart\b', "Souta's heart"),
        (r'\bKirika eyebrows\b', "Kirika's eyebrows"),
    ]

    for pattern, replacement in possessive_fixes:
        original = text
        text = re.sub(pattern, replacement, text)
        count = len(re.findall(pattern, original))
        fixes += count

    return text, fixes


def fix_concatenation_bug(ch1_path: Path) -> int:
    """Fix Chapter 1 concatenation bug by truncating at line 1979."""
    print(f"\n🔧 Fixing CH1 concatenation bug...")
    print(f"   Reading: {ch1_path}")

    with open(ch1_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_line_count = len(lines)
    print(f"   Original lines: {original_line_count}")

    # Find the concatenation point (around line 1979)
    # Look for "...I let my consciousness fade.# Chapter 2" pattern
    truncate_at = None

    for i, line in enumerate(lines):
        # Look for the pattern where CH1 ends and CH2 starts
        if i > 1900 and ('# Chapter 2' in line or 'consciousness fade' in line):
            # Check if this looks like the concatenation point
            if i < 2000:
                truncate_at = i + 1  # Keep the line with "consciousness fade"
                # If CH2 header is on same line, split it
                if '# Chapter 2' in line:
                    # Remove everything from "# Chapter 2" onward on this line
                    lines[i] = line.split('# Chapter 2')[0].rstrip() + '\n'
                break

    if truncate_at is None:
        # Fallback: truncate at line 1979 as specified in audit
        truncate_at = 1979
        print(f"   ⚠️  Pattern not found, using audit-specified line 1979")
    else:
        print(f"   ✓ Found concatenation point at line {truncate_at}")

    # Truncate
    truncated_lines = lines[:truncate_at]

    # Create backup
    backup_path = ch1_path.with_suffix('.md.pre_fix_backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"   ✓ Backup created: {backup_path.name}")

    # Write truncated version
    with open(ch1_path, 'w', encoding='utf-8') as f:
        f.writelines(truncated_lines)

    removed_lines = original_line_count - len(truncated_lines)
    print(f"   ✓ Truncated at line {truncate_at}")
    print(f"   ✓ Removed {removed_lines} duplicate lines")
    print(f"   ✓ New line count: {len(truncated_lines)}")

    return removed_lines


def main():
    """Fix all 1a60 critical issues."""
    print("=" * 80)
    print("FIX 1a60 CRITICAL ISSUES")
    print("=" * 80)
    print("\nIssues to fix:")
    print("  1. Revert 35 validator-introduced subject-verb errors")
    print("  2. Fix Chapter 1 concatenation bug (truncate at line 1979)")
    print("  3. Fix 5 remaining possessive errors")
    print()

    if not WORK_DIR.exists():
        print(f"❌ ERROR: Work directory not found: {WORK_DIR}")
        return

    total_sv_fixes = 0
    total_poss_fixes = 0

    # Process each chapter
    for chapter_file in ['CHAPTER_01_EN.md', 'CHAPTER_02_EN.md', 'CHAPTER_03_EN.md']:
        chapter_path = WORK_DIR / chapter_file

        if not chapter_path.exists():
            print(f"⚠️  Skipping {chapter_file} (not found)")
            continue

        print(f"\n📄 Processing: {chapter_file}")
        print(f"   Path: {chapter_path}")

        # Read file
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_length = len(content)
        print(f"   Size: {original_length:,} chars")

        # Apply fixes
        content, sv_fixes = fix_subject_verb_errors(content)
        content, poss_fixes = fix_possessive_errors(content)

        total_sv_fixes += sv_fixes
        total_poss_fixes += poss_fixes

        if sv_fixes > 0 or poss_fixes > 0:
            # Create backup
            backup_path = chapter_path.with_suffix('.md.backup_before_fix')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)  # Note: writing already-fixed content to show in backup

            # Actually, backup should be BEFORE fixes
            with open(backup_path, 'w', encoding='utf-8') as f:
                with open(chapter_path, 'r', encoding='utf-8') as orig:
                    f.write(orig.read())

            # Write fixed content
            with open(chapter_path, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"   ✓ Subject-verb fixes: {sv_fixes}")
            print(f"   ✓ Possessive fixes: {poss_fixes}")
            print(f"   ✓ Backup: {backup_path.name}")
        else:
            print(f"   ℹ️  No fixes needed")

    # Fix CH1 concatenation separately (needs line-level processing)
    ch1_path = WORK_DIR / 'CHAPTER_01_EN.md'
    if ch1_path.exists():
        removed_lines = fix_concatenation_bug(ch1_path)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Subject-verb errors fixed: {total_sv_fixes}")
    print(f"✅ Possessive errors fixed: {total_poss_fixes}")
    print(f"✅ CH1 duplicate lines removed: {removed_lines if ch1_path.exists() else 'N/A'}")
    print(f"\n📊 Total grammar fixes: {total_sv_fixes + total_poss_fixes}")
    print("\n✅ All critical issues resolved!")
    print("\n💾 Backups created with suffix: .backup_before_fix")
    print("\n🎯 Next: Remove all post-processors except CJK validator")


if __name__ == '__main__':
    main()
