#!/usr/bin/env python3
"""
Sentence-level line breaker for light novel prose.
Formats prose so each sentence starts on a new line (OLD style).

NEW (incorrect): Multiple sentences per line
OLD (correct):   Each sentence on its own line for readability
"""

import re
from pathlib import Path
import sys


def is_dialogue_line(line: str) -> bool:
    """Check if line is dialogue (starts with quote or asterisk for italics)."""
    stripped = line.strip()
    return stripped.startswith('"') or stripped.startswith('*')


def is_heading_or_marker(line: str) -> bool:
    """Check if line is heading, image marker, or special formatting."""
    stripped = line.strip()
    return (
        stripped.startswith('#') or
        stripped.startswith('![]') or
        stripped.startswith('---') or
        stripped.startswith('***') or
        len(stripped) == 0
    )


def split_into_sentences(text: str) -> list[str]:
    """
    Split prose paragraph into sentences.
    Handles edge cases:
    - Abbreviations (Mr., Mrs., Dr., etc.)
    - Ellipsis (...)
    - Numbers (1.5, $2.99)
    - Initials (J.K. Rowling)
    """
    # Protect common abbreviations
    protected = text
    protected = re.sub(r'\bMr\.', 'Mr<ABBR>', protected)
    protected = re.sub(r'\bMrs\.', 'Mrs<ABBR>', protected)
    protected = re.sub(r'\bMs\.', 'Ms<ABBR>', protected)
    protected = re.sub(r'\bDr\.', 'Dr<ABBR>', protected)
    protected = re.sub(r'\bProf\.', 'Prof<ABBR>', protected)
    protected = re.sub(r'\bSr\.', 'Sr<ABBR>', protected)
    protected = re.sub(r'\bJr\.', 'Jr<ABBR>', protected)
    protected = re.sub(r'\bSt\.', 'St<ABBR>', protected)

    # Protect ellipsis
    protected = re.sub(r'\.\.\.', '<ELLIPSIS>', protected)

    # Split on sentence boundaries: . ! ? followed by space and capital letter
    # But NOT if preceded by single letter (initials like "J. K.")
    sentences = re.split(r'(?<!\b[A-Z])([.!?])\s+(?=[A-Z])', protected)

    # Reconstruct sentences with their punctuation
    result = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and sentences[i + 1] in '.!?':
            # Sentence + punctuation
            sentence = sentences[i] + sentences[i + 1]
            result.append(sentence)
            i += 2
        else:
            # Last sentence or orphaned text
            if sentences[i].strip():
                result.append(sentences[i])
            i += 1

    # Restore protected patterns
    result = [s.replace('<ABBR>', '.').replace('<ELLIPSIS>', '...') for s in result]

    return [s.strip() for s in result if s.strip()]


def format_chapter(input_path: Path, output_path: Path) -> dict:
    """
    Format a single chapter with sentence-level line breaks.

    Returns:
        dict: Statistics about the formatting operation
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    formatted_lines = []
    stats = {
        'original_lines': len(lines),
        'formatted_lines': 0,
        'prose_paragraphs_split': 0,
        'dialogue_lines_preserved': 0,
        'heading_lines_preserved': 0,
    }

    i = 0
    while i < len(lines):
        line = lines[i]

        # Preserve empty lines
        if not line.strip():
            formatted_lines.append(line)
            i += 1
            continue

        # Preserve headings, image markers, and special formatting
        if is_heading_or_marker(line):
            formatted_lines.append(line)
            stats['heading_lines_preserved'] += 1
            i += 1
            continue

        # Preserve dialogue lines (don't split)
        if is_dialogue_line(line):
            formatted_lines.append(line)
            stats['dialogue_lines_preserved'] += 1
            i += 1
            continue

        # Process prose paragraph
        # Collect consecutive prose lines that form a paragraph
        paragraph_lines = [line]
        j = i + 1

        # Look ahead to collect multi-line paragraphs
        while j < len(lines):
            next_line = lines[j]
            # Stop at empty line or special formatting
            if not next_line.strip() or is_heading_or_marker(next_line) or is_dialogue_line(next_line):
                break
            # Stop if next line starts with capital (likely already a sentence)
            if next_line.strip() and next_line.strip()[0].isupper():
                # Check if current paragraph ends with sentence-ending punctuation
                current_text = ' '.join(paragraph_lines).strip()
                if current_text and current_text[-1] in '.!?':
                    break
            paragraph_lines.append(next_line)
            j += 1

        # Join paragraph and split into sentences
        paragraph_text = ' '.join(line.strip() for line in paragraph_lines)
        sentences = split_into_sentences(paragraph_text)

        if len(sentences) > 1:
            stats['prose_paragraphs_split'] += 1

        # Write each sentence on its own line
        for sentence in sentences:
            formatted_lines.append(sentence + '\n')

        # Add blank line after paragraph (preserve paragraph breaks)
        formatted_lines.append('\n')

        i = j

    # Remove excessive blank lines (max 2 consecutive)
    final_lines = []
    blank_count = 0
    for line in formatted_lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)

    stats['formatted_lines'] = len(final_lines)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(final_lines)

    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python sentence_line_breaker.py <chapter_file> [output_file]")
        print("   or: python sentence_line_breaker.py <directory>")
        sys.exit(1)

    input_arg = Path(sys.argv[1])

    if input_arg.is_file():
        # Single file mode
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_arg

        # Create backup
        backup_path = input_arg.with_suffix(input_arg.suffix + '.backup_before_line_break')
        if not backup_path.exists():
            import shutil
            shutil.copy2(input_arg, backup_path)
            print(f"✓ Created backup: {backup_path.name}")

        stats = format_chapter(input_arg, output_path)
        print(f"\n✓ Formatted: {input_arg.name}")
        print(f"  Original lines: {stats['original_lines']}")
        print(f"  Formatted lines: {stats['formatted_lines']}")
        print(f"  Prose paragraphs split: {stats['prose_paragraphs_split']}")
        print(f"  Dialogue preserved: {stats['dialogue_lines_preserved']}")

    elif input_arg.is_dir():
        # Directory mode - process all CHAPTER_*_EN.md files
        chapter_files = sorted(input_arg.glob('CHAPTER_*_EN.md'))

        if not chapter_files:
            print(f"No CHAPTER_*_EN.md files found in {input_arg}")
            sys.exit(1)

        print(f"Found {len(chapter_files)} chapter files\n")

        total_stats = {
            'files_processed': 0,
            'total_prose_paragraphs_split': 0,
            'total_dialogue_preserved': 0,
        }

        for chapter_file in chapter_files:
            # Create backup
            backup_path = chapter_file.with_suffix(chapter_file.suffix + '.backup_before_line_break')
            if not backup_path.exists():
                import shutil
                shutil.copy2(chapter_file, backup_path)

            stats = format_chapter(chapter_file, chapter_file)
            total_stats['files_processed'] += 1
            total_stats['total_prose_paragraphs_split'] += stats['prose_paragraphs_split']
            total_stats['total_dialogue_preserved'] += stats['dialogue_lines_preserved']

            print(f"✓ {chapter_file.name}")
            print(f"  Lines: {stats['original_lines']} → {stats['formatted_lines']}")
            print(f"  Prose split: {stats['prose_paragraphs_split']}, Dialogue preserved: {stats['dialogue_lines_preserved']}\n")

        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"Files processed: {total_stats['files_processed']}")
        print(f"Total prose paragraphs split: {total_stats['total_prose_paragraphs_split']}")
        print(f"Total dialogue lines preserved: {total_stats['total_dialogue_preserved']}")

    else:
        print(f"Error: {input_arg} is neither a file nor a directory")
        sys.exit(1)


if __name__ == '__main__':
    main()
