#!/usr/bin/env python3
"""
Clean up honorific suffixes in narrative text while preserving them in dialogue.

Replaces:
- Emma-chan → Emma (in narrative only)
- Charlotte-san → Charlotte (in narrative only)

Preserves honorifics in:
- Dialogue (text within quotes)
- Special cases (onii-chan, etc.)

Author: MTL Studio
Date: 2026-02-03
"""

import re
import sys
from pathlib import Path
from typing import Tuple, List

# Honorific patterns to remove in narrative
HONORIFIC_REPLACEMENTS = {
    r'\bEmma-chan\b': 'Emma',
    r'\bCharlotte-san\b': 'Charlotte',
}

# Honorifics to ALWAYS preserve (even in narrative)
PRESERVE_PATTERNS = [
    r'onii-chan',
    r'onee-chan',
    r'nii-chan',
    r'nee-chan',
    r'-sama',  # High respect
    r'-dono',  # Historical/formal
]


def is_inside_dialogue(text: str, position: int) -> bool:
    """
    Check if a position in text is inside dialogue (between quotes).

    Args:
        text: Full text
        position: Character position to check

    Returns:
        True if position is inside dialogue, False otherwise
    """
    # Count quotes before this position
    before_text = text[:position]

    # Count different quote types
    double_quotes = before_text.count('"')
    single_quotes = before_text.count("'")

    # If odd number of double quotes, we're inside dialogue
    # (Simple heuristic - assumes well-formed dialogue)
    return double_quotes % 2 == 1


def should_preserve_honorific(text: str, match_start: int, match_end: int) -> bool:
    """
    Check if this honorific should be preserved.

    Args:
        text: Full text
        match_start: Start position of match
        match_end: End position of match

    Returns:
        True if honorific should be preserved
    """
    matched_text = text[match_start:match_end]

    # Check if it's in the preserve list
    for preserve_pattern in PRESERVE_PATTERNS:
        if re.search(preserve_pattern, matched_text, re.IGNORECASE):
            return True

    # Check if inside dialogue
    return is_inside_dialogue(text, match_start)


def clean_narrative_honorifics(text: str, verbose: bool = False) -> Tuple[str, int]:
    """
    Remove honorific suffixes from narrative text while preserving dialogue.

    Args:
        text: Input text
        verbose: Print replacements if True

    Returns:
        Tuple of (cleaned_text, replacement_count)
    """
    cleaned_text = text
    total_replacements = 0

    for pattern, replacement in HONORIFIC_REPLACEMENTS.items():
        matches = list(re.finditer(pattern, cleaned_text, re.IGNORECASE))

        # Process matches in reverse to maintain positions
        for match in reversed(matches):
            start, end = match.span()

            # Check if we should preserve this honorific
            if should_preserve_honorific(cleaned_text, start, end):
                if verbose:
                    context_start = max(0, start - 20)
                    context_end = min(len(cleaned_text), end + 20)
                    context = cleaned_text[context_start:context_end]
                    print(f"  [PRESERVE] {match.group()} in dialogue: ...{context}...")
                continue

            # Replace the honorific
            cleaned_text = cleaned_text[:start] + replacement + cleaned_text[end:]
            total_replacements += 1

            if verbose:
                context_start = max(0, start - 20)
                context_end = min(len(cleaned_text), start + len(replacement) + 20)
                context = cleaned_text[context_start:context_end]
                print(f"  [REPLACE] {match.group()} → {replacement}: ...{context}...")

    return cleaned_text, total_replacements


def process_file(file_path: Path, dry_run: bool = False, verbose: bool = False) -> Tuple[int, bool]:
    """
    Process a single markdown file.

    Args:
        file_path: Path to markdown file
        dry_run: If True, don't write changes
        verbose: Print detailed info

    Returns:
        Tuple of (replacement_count, was_modified)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_text = f.read()

        cleaned_text, count = clean_narrative_honorifics(original_text, verbose=verbose)

        if count > 0:
            if not dry_run:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_text)
            return count, True

        return 0, False

    except Exception as e:
        print(f"[ERROR] Failed to process {file_path}: {e}")
        return 0, False


def process_directory(directory: Path, dry_run: bool = False, verbose: bool = False) -> None:
    """
    Process all markdown files in a directory.

    Args:
        directory: Directory containing markdown files
        dry_run: If True, don't write changes
        verbose: Print detailed info
    """
    md_files = sorted(directory.glob("*.md"))

    if not md_files:
        print(f"[WARNING] No markdown files found in {directory}")
        return

    total_files = len(md_files)
    modified_files = 0
    total_replacements = 0

    print(f"\nProcessing {total_files} files in {directory.name}/")
    print("=" * 80)

    for md_file in md_files:
        if verbose:
            print(f"\nProcessing: {md_file.name}")

        count, was_modified = process_file(md_file, dry_run=dry_run, verbose=verbose)

        if was_modified:
            modified_files += 1
            total_replacements += count
            mode = "DRY RUN" if dry_run else "MODIFIED"
            print(f"  [{mode}] {md_file.name}: {count} replacements")

    print("=" * 80)
    print(f"\nSummary:")
    print(f"  Files processed: {total_files}")
    print(f"  Files modified: {modified_files}")
    print(f"  Total replacements: {total_replacements}")

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No files were actually modified")
        print("   Run without --dry-run to apply changes")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up honorific suffixes in narrative text while preserving dialogue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run on Volume 1 EN directory
  python cleanup_narrative_honorifics.py WORK/volume1/EN --dry-run

  # Apply changes to Volume 1
  python cleanup_narrative_honorifics.py WORK/volume1/EN

  # Process with verbose output
  python cleanup_narrative_honorifics.py WORK/volume1/EN --verbose

  # Process single file
  python cleanup_narrative_honorifics.py WORK/volume1/EN/CHAPTER_04_EN.md
        """
    )

    parser.add_argument(
        'path',
        type=str,
        help='Path to directory containing markdown files or single markdown file'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed replacement information'
    )

    args = parser.parse_args()

    path = Path(args.path)

    if not path.exists():
        print(f"[ERROR] Path not found: {path}")
        sys.exit(1)

    print("=" * 80)
    print("Narrative Honorific Cleanup Script")
    print("=" * 80)
    print(f"\nTarget: {path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY CHANGES'}")
    print(f"Verbose: {'Yes' if args.verbose else 'No'}")
    print(f"\nRemoving honorifics in narrative:")
    for pattern, replacement in HONORIFIC_REPLACEMENTS.items():
        print(f"  - {pattern} → {replacement}")
    print(f"\nPreserving in dialogue and special cases:")
    for pattern in PRESERVE_PATTERNS:
        print(f"  - {pattern}")

    if path.is_file():
        if path.suffix != '.md':
            print(f"[ERROR] Not a markdown file: {path}")
            sys.exit(1)

        print(f"\nProcessing single file: {path.name}")
        count, was_modified = process_file(path, dry_run=args.dry_run, verbose=args.verbose)

        if was_modified:
            mode = "would be" if args.dry_run else "were"
            print(f"\n✓ {count} replacements {mode} made in {path.name}")
        else:
            print(f"\n✓ No changes needed for {path.name}")

    elif path.is_dir():
        process_directory(path, dry_run=args.dry_run, verbose=args.verbose)

    else:
        print(f"[ERROR] Invalid path: {path}")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("Done!")
    print("=" * 80)


if __name__ == "__main__":
    main()
