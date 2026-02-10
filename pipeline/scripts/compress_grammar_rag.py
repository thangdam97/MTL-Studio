#!/usr/bin/env python3
"""
Compress english_grammar_rag.json from 283KB → 203KB

Compression Strategy (as per PROMPT_OPTIMIZATION_REPORT.md):
1. Keep only 1 best example per pattern (remove 2nd-3rd examples) - save ~30KB
2. Remove negative_vectors sections (if present) - save ~15KB
3. Compress usage_rules to bullet format - save ~20KB
4. Remove priority:'low' patterns - save ~15KB

Target: 80KB reduction (283KB → 203KB)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def compress_examples(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only the BEST example (first one with 'source' field, or first overall).
    Remove 2nd and 3rd examples.
    """
    if 'examples' in pattern and len(pattern['examples']) > 1:
        # Find first example with 'source' field (likely from EPUB corpus)
        best_example = None
        for ex in pattern['examples']:
            if 'source' in ex:
                best_example = ex
                break

        if best_example is None:
            best_example = pattern['examples'][0]

        pattern['examples'] = [best_example]

    return pattern


def compress_usage_rules(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compress verbose usage_rules to concise bullet points.
    Remove redundant explanations.
    """
    if 'usage_rules' in pattern:
        rules = pattern['usage_rules']

        # Keep only first 3 rules (most important)
        if len(rules) > 3:
            pattern['usage_rules'] = rules[:3]

        # Compress verbose rules to shorter form
        compressed_rules = []
        for rule in pattern['usage_rules']:
            # Remove redundant prefixes
            rule = rule.replace('Use when ', '')
            rule = rule.replace('Especially effective ', 'Effective ')
            rule = rule.replace('Creates smoother ', 'Smoother ')

            # Trim to max 60 chars
            if len(rule) > 60:
                rule = rule[:57] + '...'

            compressed_rules.append(rule)

        pattern['usage_rules'] = compressed_rules

    return pattern


def remove_negative_vectors(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Remove negative_vectors sections (suppress match logic not critical)."""
    if 'negative_vectors' in pattern:
        del pattern['negative_vectors']
    return pattern


def remove_low_priority_patterns(category_data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove patterns with priority: 'low'."""
    if 'patterns' in category_data:
        category_data['patterns'] = [
            p for p in category_data['patterns']
            if p.get('priority', 'medium') != 'low'
        ]
    return category_data


def compress_grammar_rag(input_path: Path, output_path: Path) -> Dict[str, Any]:
    """
    Compress english_grammar_rag.json file.

    Returns:
        dict: Compression statistics
    """
    print(f"Loading: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    original_size = input_path.stat().st_size

    stats = {
        'original_size_kb': original_size / 1024,
        'patterns_removed': 0,
        'examples_removed': 0,
        'negative_vectors_removed': 0,
        'usage_rules_compressed': 0,
    }

    # Process pattern_categories
    if 'pattern_categories' in data:
        for category_name, category_data in data['pattern_categories'].items():
            original_pattern_count = len(category_data.get('patterns', []))

            # Remove low priority patterns
            category_data = remove_low_priority_patterns(category_data)

            new_pattern_count = len(category_data.get('patterns', []))
            stats['patterns_removed'] += original_pattern_count - new_pattern_count

            # Process each pattern
            for pattern in category_data.get('patterns', []):
                # Count original examples
                original_examples = len(pattern.get('examples', []))

                # Compress
                pattern = compress_examples(pattern)
                pattern = compress_usage_rules(pattern)
                pattern = remove_negative_vectors(pattern)

                # Count compression
                new_examples = len(pattern.get('examples', []))
                stats['examples_removed'] += original_examples - new_examples

                if 'negative_vectors' not in pattern:
                    stats['negative_vectors_removed'] += 1

                if 'usage_rules' in pattern:
                    stats['usage_rules_compressed'] += 1

            data['pattern_categories'][category_name] = category_data

    # Process advanced_patterns (same compression)
    if 'advanced_patterns' in data:
        for category_name, category_data in data['advanced_patterns'].items():
            # Skip non-pattern entries (like 'description')
            if not isinstance(category_data, dict) or 'patterns' not in category_data:
                continue

            original_pattern_count = len(category_data.get('patterns', []))

            category_data = remove_low_priority_patterns(category_data)

            new_pattern_count = len(category_data.get('patterns', []))
            stats['patterns_removed'] += original_pattern_count - new_pattern_count

            for pattern in category_data.get('patterns', []):
                original_examples = len(pattern.get('examples', []))

                pattern = compress_examples(pattern)
                pattern = compress_usage_rules(pattern)
                pattern = remove_negative_vectors(pattern)

                new_examples = len(pattern.get('examples', []))
                stats['examples_removed'] += original_examples - new_examples

                if 'negative_vectors' not in pattern:
                    stats['negative_vectors_removed'] += 1

                if 'usage_rules' in pattern:
                    stats['usage_rules_compressed'] += 1

            data['advanced_patterns'][category_name] = category_data

    # Compress metadata sections
    if 'future_enhancements' in data:
        # Remove verbose future plans (not needed in production)
        del data['future_enhancements']

    if 'pattern_addition_workflow' in data:
        # Remove workflow documentation (belongs in separate docs)
        del data['pattern_addition_workflow']

    # Write compressed version
    print(f"\nWriting: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    compressed_size = output_path.stat().st_size
    stats['compressed_size_kb'] = compressed_size / 1024
    stats['reduction_kb'] = (original_size - compressed_size) / 1024
    stats['reduction_percent'] = ((original_size - compressed_size) / original_size) * 100

    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python compress_grammar_rag.py <input_file> [output_file]")
        print("Example: python compress_grammar_rag.py config/english_grammar_rag.json")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    # Default output: add _compressed suffix
    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])
    else:
        output_path = input_path.with_stem(input_path.stem + '_compressed')

    # Create backup
    backup_path = input_path.with_suffix('.json.backup_before_compression')
    if not backup_path.exists():
        import shutil
        shutil.copy2(input_path, backup_path)
        print(f"✓ Created backup: {backup_path.name}\n")

    # Compress
    stats = compress_grammar_rag(input_path, output_path)

    # Report
    print(f"\n{'='*60}")
    print(f"COMPRESSION SUMMARY")
    print(f"{'='*60}")
    print(f"Original size:       {stats['original_size_kb']:.1f} KB")
    print(f"Compressed size:     {stats['compressed_size_kb']:.1f} KB")
    print(f"Reduction:           {stats['reduction_kb']:.1f} KB ({stats['reduction_percent']:.1f}%)")
    print(f"\nDetails:")
    print(f"  Patterns removed (low priority): {stats['patterns_removed']}")
    print(f"  Examples removed (2nd-3rd):      {stats['examples_removed']}")
    print(f"  Negative vectors removed:        {stats['negative_vectors_removed']}")
    print(f"  Usage rules compressed:          {stats['usage_rules_compressed']}")

    if stats['reduction_kb'] >= 80:
        print(f"\n✅ SUCCESS: Achieved target reduction of 80KB+")
    elif stats['reduction_kb'] >= 60:
        print(f"\n⚠️  PARTIAL: {stats['reduction_kb']:.1f}KB saved (target: 80KB)")
    else:
        print(f"\n❌ BELOW TARGET: Only {stats['reduction_kb']:.1f}KB saved (target: 80KB)")


if __name__ == '__main__':
    main()
