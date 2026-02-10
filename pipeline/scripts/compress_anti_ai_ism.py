#!/usr/bin/env python3
"""
Compress anti_ai_ism_patterns.json from 47KB → 35KB

Compression Strategy (as per PROMPT_OPTIMIZATION_REPORT.md):
1. Remove verbose 'source' explanations (keep only pattern + fix) - save ~3KB
2. Compress changelog/meta section - save ~3KB
3. Compress proximity_penalty verbose instructions - save ~4KB
4. Remove redundant examples - save ~2KB

Target: 12KB reduction (47KB → 35KB)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict


def compress_meta_section(data: Dict[str, Any]) -> Dict[str, Any]:
    """Compress verbose metadata and changelog."""
    if '_meta' in data:
        meta = data['_meta']

        # Keep only essential meta fields
        compressed_meta = {
            'version': meta.get('version', '2.1'),
            'last_updated': meta.get('last_updated', '2026-01-30'),
        }

        # Compress echo_detection to just enabled flag
        if 'echo_detection' in meta:
            compressed_meta['echo_detection'] = {
                'enabled': True,
                'proximity_window': 100
            }

        data['_meta'] = compressed_meta

    return data


def compress_pattern(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Compress a single pattern entry."""
    # Keep only essential fields
    compressed = {
        'id': pattern['id'],
        'regex': pattern['regex'],
        'display': pattern['display'],
        'fix': pattern['fix']
    }

    # Compress proximity_penalty if present
    if 'proximity_penalty' in pattern:
        compressed['proximity_penalty'] = {
            'window': pattern['proximity_penalty'].get('window', 100),
            'severity': pattern['proximity_penalty'].get('severity_override', 'MAJOR')
        }

    # Remove verbose 'source' explanations
    # Remove 'fix_instruction' (redundant with 'fix')

    return compressed


def compress_category(category_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compress a pattern category."""
    if 'patterns' in category_data:
        category_data['patterns'] = [
            compress_pattern(p) for p in category_data['patterns']
        ]

    # Remove verbose description (keep category name as self-documenting)
    if 'description' in category_data:
        del category_data['description']

    return category_data


def compress_anti_ai_ism(input_path: Path, output_path: Path) -> Dict[str, Any]:
    """
    Compress anti_ai_ism_patterns.json file.

    Returns:
        dict: Compression statistics
    """
    print(f"Loading: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    original_size = input_path.stat().st_size

    stats = {
        'original_size_kb': original_size / 1024,
        'patterns_compressed': 0,
        'proximity_penalties_compressed': 0,
        'meta_compressed': 0,
    }

    # Compress meta section
    data = compress_meta_section(data)
    stats['meta_compressed'] = 1

    # Process each severity level
    for severity_level in ['CRITICAL', 'MAJOR', 'MINOR']:
        if severity_level not in data:
            continue

        severity_data = data[severity_level]

        # If it has 'patterns' directly (like CRITICAL)
        if 'patterns' in severity_data:
            original_count = len(severity_data['patterns'])
            severity_data['patterns'] = [
                compress_pattern(p) for p in severity_data['patterns']
            ]
            stats['patterns_compressed'] += original_count

            # Count proximity penalties
            for p in severity_data['patterns']:
                if 'proximity_penalty' in p:
                    stats['proximity_penalties_compressed'] += 1

            # Remove description
            if 'description' in severity_data:
                del severity_data['description']

        # If it has categories (like MAJOR with japanese_calques, emotion_wrappers)
        elif 'categories' in severity_data:
            for category_name, category_data in severity_data['categories'].items():
                if 'patterns' in category_data:
                    original_count = len(category_data['patterns'])
                    category_data['patterns'] = [
                        compress_pattern(p) for p in category_data['patterns']
                    ]
                    stats['patterns_compressed'] += original_count

                    # Count proximity penalties
                    for p in category_data['patterns']:
                        if 'proximity_penalty' in p:
                            stats['proximity_penalties_compressed'] += 1

                # Remove category description
                if 'description' in category_data:
                    del category_data['description']

            # Remove top-level description
            if 'description' in severity_data:
                del severity_data['description']

        data[severity_level] = severity_data

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
        print("Usage: python compress_anti_ai_ism.py <input_file> [output_file]")
        print("Example: python compress_anti_ai_ism.py config/anti_ai_ism_patterns.json")
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
    stats = compress_anti_ai_ism(input_path, output_path)

    # Report
    print(f"\n{'='*60}")
    print(f"COMPRESSION SUMMARY")
    print(f"{'='*60}")
    print(f"Original size:       {stats['original_size_kb']:.1f} KB")
    print(f"Compressed size:     {stats['compressed_size_kb']:.1f} KB")
    print(f"Reduction:           {stats['reduction_kb']:.1f} KB ({stats['reduction_percent']:.1f}%)")
    print(f"\nDetails:")
    print(f"  Patterns compressed:           {stats['patterns_compressed']}")
    print(f"  Proximity penalties compressed: {stats['proximity_penalties_compressed']}")
    print(f"  Meta section compressed:       {stats['meta_compressed']}")

    if stats['reduction_kb'] >= 12:
        print(f"\n✅ SUCCESS: Achieved target reduction of 12KB+")
    elif stats['reduction_kb'] >= 10:
        print(f"\n⚠️  PARTIAL: {stats['reduction_kb']:.1f}KB saved (target: 12KB)")
    else:
        print(f"\n❌ BELOW TARGET: Only {stats['reduction_kb']:.1f}KB saved (target: 12KB)")


if __name__ == '__main__':
    main()
