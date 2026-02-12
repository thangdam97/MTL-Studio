#!/usr/bin/env python3
"""
Quick fix script for 25e8 AI-ism violations.
Applies auto-fix for "I couldn't help but" pattern (confidence: 0.95).
"""

import re
import json
from pathlib import Path
from datetime import datetime
import shutil

def fix_couldnt_help_but(text: str):
    """Fix 'I couldn't help but [verb]' -> 'I [verb]'"""
    pat = re.compile(r"\bI couldn't help but (\w+)")
    changes = []

    def repl(m):
        verb = m.group(1)
        changes.append({
            'original': m.group(0),
            'fixed': f"I {verb}",
            'position': m.start()
        })
        return f"I {verb}"

    fixed = pat.sub(repl, text)
    return fixed, changes

def main(dry_run=True):
    # Target directory for 25e8 (Vol 2)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    en_dir = project_root / 'WORK/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (2)_20260212_25e8/EN'

    if not en_dir.exists():
        print(f"ERROR: Directory not found: {en_dir}")
        return 1

    files = sorted(en_dir.glob('CHAPTER_*_EN.md'))

    print(f"\n{'='*60}")
    print(f"AI-ism Auto-Fix: 'I couldn't help but' pattern (25e8 Vol 2)")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE - APPLYING FIXES'}")
    print(f"{'='*60}\n")

    print(f"Found {len(files)} files")

    total_fixes = 0
    results = []

    for file_path in files:
        original = file_path.read_text(encoding='utf-8')
        fixed, changes = fix_couldnt_help_but(original)

        result = {
            'file': file_path.name,
            'fixes': len(changes),
            'changes': changes
        }

        if changes:
            total_fixes += len(changes)
            results.append(result)

            print(f"\n{file_path.name}:")
            for change in changes:
                print(f"  → '{change['original']}' => '{change['fixed']}'")

            if not dry_run:
                # Create backup
                backup_path = file_path.with_suffix('.md.backup')
                shutil.copy2(file_path, backup_path)

                # Write fixed version
                file_path.write_text(fixed, encoding='utf-8')
                print(f"  ✓ Applied {len(changes)} fixes")
                print(f"  ✓ Backup: {backup_path.name}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"\nTotal files processed: {len(files)}")
    print(f"Files with violations: {len(results)}")
    print(f"Total fixes: {total_fixes}")

    if dry_run:
        print(f"\n⚠️  DRY RUN MODE - No files were modified")
        print(f"\nRun with --apply to apply changes:")
        print(f"  python3 pipeline/scripts/fix_25e8_ai_isms.py --apply")
    else:
        print(f"\n✓ Fixes applied successfully")
        print(f"✓ Backups created (.md.backup)")

    # Generate JSON report
    report_path = project_root / '25E8_AI_ISM_FIX_REPORT.json'
    report = {
        'volume': 'Vol 2 (25e8)',
        'timestamp': datetime.now().isoformat(),
        'mode': 'dry_run' if dry_run else 'live',
        'pattern': 'I couldn\'t help but [verb]',
        'confidence': 0.95,
        'total_fixes': total_fixes,
        'files_modified': len(results),
        'details': results
    }

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n✓ JSON report saved: {report_path}")
    print(f"\n{'='*60}\n")

    return 0

if __name__ == '__main__':
    import sys
    dry_run = '--apply' not in sys.argv
    sys.exit(main(dry_run=dry_run))
