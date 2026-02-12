#!/usr/bin/env python3
"""
Phase 2.5 Auto-fix Deployment for 17fb
Fixes high-confidence AI-ism patterns with 0.95+ confidence threshold.

Target patterns:
1. "couldn't help but [verb]" → "[verb]" (5 instances)
"""

import re
from pathlib import Path
from typing import List, Tuple, Dict
import json


class Phase25AutoFixer:
    """Auto-fix high-confidence AI-ism patterns."""

    def __init__(self, work_dir: Path, dry_run: bool = False):
        self.work_dir = work_dir
        self.dry_run = dry_run
        self.fixes_applied = []

    def fix_couldnt_help_but(self, text: str, file_path: str) -> Tuple[str, int]:
        """
        Fix pattern: "couldn't help but [verb]" → "[verb]"
        Confidence: 0.95

        Examples:
        - "I couldn't help but feel" → "I felt"
        - "couldn't help but protest" → "protested"
        - "couldn't help but worry" → "worried"
        - "couldn't help but shout" → "shouted"
        - "couldn't help but ask" → "asked"
        """
        pattern = r'\b(I |he |she |they |we )?couldn\'t help but (\w+)'

        def replacement(match):
            subject = match.group(1) or ""
            verb = match.group(2)

            # Convert verb to past tense if needed
            verb_conversions = {
                "feel": "felt",
                "protest": "protested",
                "worry": "worried",
                "shout": "shouted",
                "ask": "asked",
                "notice": "noticed",
                "stare": "stared",
                "think": "thought",
                "wonder": "wondered",
                "smile": "smiled",
                "laugh": "laughed",
            }

            past_verb = verb_conversions.get(verb, verb + "ed")

            # Handle subject-verb agreement
            if subject.strip() in ["I", "he", "she", "it"]:
                return f"{subject}{past_verb}"
            elif subject.strip() in ["they", "we"]:
                return f"{subject}{past_verb}"
            else:
                return past_verb

        fixed_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Count fixes
        fixes_count = len(re.findall(pattern, text, re.IGNORECASE))

        if fixes_count > 0:
            # Log fixes
            for match in re.finditer(pattern, text, re.IGNORECASE):
                original = match.group(0)
                fixed = replacement(match)
                self.fixes_applied.append({
                    "file": str(file_path),
                    "pattern": "couldn't help but",
                    "original": original,
                    "fixed": fixed,
                    "confidence": 0.95
                })

        return fixed_text, fixes_count

    def process_file(self, file_path: Path) -> Dict:
        """Process a single EN markdown file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            original_text = f.read()

        # Apply fixes
        fixed_text, fixes_count = self.fix_couldnt_help_but(original_text, file_path.name)

        if fixes_count > 0 and not self.dry_run:
            # Write fixed text
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_text)

        return {
            "file": file_path.name,
            "fixes_applied": fixes_count,
            "dry_run": self.dry_run
        }

    def process_volume(self) -> Dict:
        """Process all EN files in volume."""
        en_dir = self.work_dir / "EN"

        if not en_dir.exists():
            raise FileNotFoundError(f"EN directory not found: {en_dir}")

        results = {
            "volume": self.work_dir.name,
            "files_processed": 0,
            "total_fixes": 0,
            "file_results": [],
            "fixes_applied": []
        }

        # Process each chapter
        for chapter_file in sorted(en_dir.glob("CHAPTER_*.md")):
            file_result = self.process_file(chapter_file)
            results["files_processed"] += 1
            results["total_fixes"] += file_result["fixes_applied"]
            results["file_results"].append(file_result)

        results["fixes_applied"] = self.fixes_applied

        return results


def main():
    """Run Phase 2.5 auto-fix on 17fb."""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2.5 Auto-fix for 17fb")
    parser.add_argument("--dry-run", action="store_true", help="Preview fixes without applying")
    parser.add_argument("--output", type=str, help="Output report path",
                        default="17FB_PHASE25_AUTOFIX_REPORT.json")

    args = parser.parse_args()

    # Target directory
    work_dir = Path(__file__).parent.parent / "WORK" / "(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (4)_20260212_17fb"

    if not work_dir.exists():
        print(f"❌ Work directory not found: {work_dir}")
        return 1

    # Create fixer
    fixer = Phase25AutoFixer(work_dir, dry_run=args.dry_run)

    # Process volume
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {work_dir.name}...")
    results = fixer.process_volume()

    # Save report
    output_path = Path(__file__).parent.parent / args.output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Phase 2.5 Auto-fix {'Preview' if args.dry_run else 'Results'}")
    print(f"{'=' * 60}")
    print(f"Files processed: {results['files_processed']}")
    print(f"Total fixes: {results['total_fixes']}")
    print(f"Report saved: {output_path}")

    if results['total_fixes'] > 0:
        print(f"\nFixes by file:")
        for file_result in results['file_results']:
            if file_result['fixes_applied'] > 0:
                print(f"  - {file_result['file']}: {file_result['fixes_applied']} fix(es)")

    if args.dry_run:
        print(f"\n⚠️  DRY RUN: No files were modified. Run without --dry-run to apply fixes.")
    else:
        print(f"\n✅ Auto-fixes applied successfully!")

    return 0


if __name__ == "__main__":
    exit(main())
