#!/usr/bin/env python3
"""
Japanese Prose Breakline Script.

Adds line breaks after sentence-ending punctuation in Japanese markdown files
to improve readability and translation quality.

Rules:
1. Break after 。 (period) - but not inside quotes
2. Break after 」 (closing quote) when followed by text
3. Break after ！ or ？ when followed by non-quote text  
4. Preserve scene break markers (◆◆◆, ◇◇◇, etc.)
5. Preserve illustration markers [ILLUSTRATION: ...]
6. Preserve headings (# lines)
7. Do NOT break inside dialogue quotes 「...」
"""

import re
import sys
from pathlib import Path
from typing import List


def breakline_japanese_prose(text: str) -> str:
    """
    Add line breaks to Japanese prose after sentence endings.
    
    Args:
        text: Raw Japanese markdown text
        
    Returns:
        Text with proper line breaks
    """
    lines = text.split('\n')
    result_lines = []
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            result_lines.append(line)
            continue
            
        # Skip headings
        if line.strip().startswith('#'):
            result_lines.append(line)
            continue
            
        # Skip scene break markers
        if re.match(r'^[◆◇\*]{2,}$', line.strip()):
            result_lines.append(line)
            continue
            
        # Skip illustration markers
        if '[ILLUSTRATION:' in line or '![' in line:
            result_lines.append(line)
            continue
            
        # Skip very short lines (already broken)
        if len(line.strip()) < 30:
            result_lines.append(line)
            continue
        
        # Apply breakline logic
        broken_lines = break_sentence(line)
        result_lines.extend(broken_lines)
    
    return '\n'.join(result_lines)


def break_sentence(line: str) -> List[str]:
    """
    Break a single line into multiple lines at sentence boundaries.
    
    Args:
        line: A single line of Japanese text
        
    Returns:
        List of broken lines
    """
    if not line.strip():
        return [line]
    
    # Pattern to match sentence endings
    # Break after:
    # - 。 followed by anything except closing brackets
    # - 」 followed by non-whitespace (continuing narrative after dialogue)
    # - ！ or ？ followed by non-quote text
    
    # First, handle dialogue endings 」 followed by narrative
    # Pattern: 」 followed by text that's not another quote or whitespace
    result = line
    
    # Break after 」 when followed by non-quote continuation
    # e.g., 「話した」俺は → 「話した」\n俺は
    result = re.sub(r'」([^」「\n\s])', r'」\n\1', result)
    
    # Break after 。 when NOT inside quotes and followed by text
    # This is tricky - we need to avoid breaking inside 「...」
    # Simple approach: break after 。 if not immediately followed by 」
    result = re.sub(r'。([^」\n\s])', r'。\n\1', result)
    
    # Break after standalone ！ or ？ followed by narrative (not more dialogue)
    result = re.sub(r'([！？])([^」「！？\n\s])', r'\1\n\2', result)
    
    # Clean up: remove any double newlines created
    result = re.sub(r'\n\n+', '\n', result)
    
    # Split and return
    broken = result.split('\n')
    return [l for l in broken if l.strip()]  # Remove empty lines


def process_file(file_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Process a single markdown file.
    
    Args:
        file_path: Path to the markdown file
        dry_run: If True, don't write changes
        
    Returns:
        Tuple of (original_lines, new_lines)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        original_text = f.read()
    
    original_lines = len(original_text.split('\n'))
    
    processed_text = breakline_japanese_prose(original_text)
    new_lines = len(processed_text.split('\n'))
    
    if not dry_run and processed_text != original_text:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(processed_text)
    
    return original_lines, new_lines


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Add line breaks to Japanese prose markdown files')
    parser.add_argument('paths', nargs='+', help='Paths to markdown files or directories')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing')
    parser.add_argument('--pattern', default='*.md', help='File pattern to match (default: *.md)')
    
    args = parser.parse_args()
    
    files_to_process = []
    
    for path_str in args.paths:
        path = Path(path_str)
        if path.is_file():
            files_to_process.append(path)
        elif path.is_dir():
            files_to_process.extend(path.glob(args.pattern))
    
    if not files_to_process:
        print("No files found to process")
        return
    
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(files_to_process)} file(s)...\n")
    
    total_original = 0
    total_new = 0
    
    for file_path in sorted(files_to_process):
        original, new = process_file(file_path, args.dry_run)
        total_original += original
        total_new += new
        
        diff = new - original
        status = f"+{diff}" if diff > 0 else str(diff)
        print(f"  {file_path.name}: {original} → {new} lines ({status})")
    
    print(f"\nTotal: {total_original} → {total_new} lines (+{total_new - total_original})")
    
    if args.dry_run:
        print("\n[DRY RUN] No files were modified. Remove --dry-run to apply changes.")


if __name__ == '__main__':
    main()
