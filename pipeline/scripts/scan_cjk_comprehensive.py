#!/usr/bin/env python3
"""
Comprehensive CJK Scanner for Novel Volumes
Uses the full Unicode block detector to scan all EN chapters
"""

import sys
from pathlib import Path

# Import the comprehensive detector
sys.path.insert(0, str(Path(__file__).parent.parent / 'pipeline' / 'post_processor'))
from cjk_unicode_detector import ComprehensiveCJKDetector, CJKBlock

def scan_volume(volume_id: str):
    """
    Scan all EN chapters in a volume for CJK characters.
    
    Args:
        volume_id: Volume ID to scan (e.g., '1d46', '05df')
    """
    
    # Find volume directory
    work_dir = Path(__file__).parent.parent / 'WORK'
    volume_dirs = [d for d in work_dir.iterdir() if d.is_dir() and volume_id in d.name]
    
    if not volume_dirs:
        print(f'❌ Volume {volume_id} not found in WORK directory')
        return
    
    volume_dir = volume_dirs[0]
    en_dir = volume_dir / 'EN'
    
    if not en_dir.exists():
        print(f'❌ EN directory not found for volume {volume_id}')
        return
    
    # Initialize detector
    detector = ComprehensiveCJKDetector(strict_mode=False)
    
    print("=" * 80)
    print(f"COMPREHENSIVE CJK UNICODE DETECTION - Volume {volume_id}")
    print(f"Volume: {volume_dir.name}")
    print("=" * 80)
    print()
    
    # Scan all EN markdown files
    chapter_files = sorted(en_dir.glob('*_EN.md'))
    
    if not chapter_files:
        print(f'⚠️  No EN chapter files found in {en_dir}')
        return
    
    print(f"📂 Scanning {len(chapter_files)} files...")
    print()
    
    all_issues = []
    
    for chapter_file in chapter_files:
        with open(chapter_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        chapter_issues = []
        
        for line_num, line in enumerate(lines, 1):
            # Detect all CJK in this line
            cjk_chars = detector.detect_all_cjk(line)
            
            for info in cjk_chars:
                # Calculate suspicion score
                idx = line.find(info.char)
                left = line[max(0, idx-5):idx] if idx >= 0 else ""
                right = line[idx+1:min(len(line), idx+6)] if idx >= 0 else ""
                
                score, reason = detector.calculate_suspicion(
                    info.char, left, right, info.block
                )
                
                issue = {
                    'file': chapter_file.name,
                    'line': line_num,
                    'char': info.char,
                    'codepoint': info.codepoint,
                    'unicode_name': info.unicode_name,
                    'block': info.block.block_name,
                    'rarity': info.block.rarity,
                    'japanese_compatible': info.is_japanese_compatible,
                    'suspicion_score': score,
                    'suspicion_reason': reason,
                    'context': line[max(0, idx-30):min(len(line), idx+30)].strip() if idx >= 0 else "",
                    'full_line': line.strip()
                }
                
                chapter_issues.append(issue)
                all_issues.append(issue)
    
    # Print results
    print(f"📊 Results: Found {len(all_issues)} CJK characters across {len(chapter_files)} files")
    print()
    
    if all_issues:
        print("⚠️  CJK CHARACTERS DETECTED:")
        print()
        
        # Group by file
        by_file = {}
        for issue in all_issues:
            file = issue['file']
            if file not in by_file:
                by_file[file] = []
            by_file[file].append(issue)
        
        for file, issues in sorted(by_file.items()):
            print(f"📄 {file}: {len(issues)} CJK characters")
            print()
            
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. Line {issue['line']}: [{issue['char']}] U+{issue['codepoint']:04X}")
                print(f"     Block: {issue['block']} ({issue['rarity']})")
                print(f"     Japanese Compatible: {'Yes' if issue['japanese_compatible'] else 'No'}")
                print(f"     Suspicion: {issue['suspicion_score']:.2f} - {issue['suspicion_reason']}")
                print(f"     Context: ...{issue['context']}...")
                print()
        
        # Summary statistics
        print("=" * 80)
        print("SUMMARY STATISTICS")
        print("=" * 80)
        
        # By block
        by_block = {}
        for issue in all_issues:
            block = issue['block']
            if block not in by_block:
                by_block[block] = []
            by_block[block].append(issue['char'])
        
        print("\nBy Unicode Block:")
        for block, chars in sorted(by_block.items()):
            unique_chars = list(set(chars))
            chars_preview = ''.join(unique_chars[:10])
            if len(unique_chars) > 10:
                chars_preview += "..."
            print(f"  {block}: {len(chars)} occurrences, {len(unique_chars)} unique ({chars_preview})")
        
        # By suspicion level
        high_suspicion = [i for i in all_issues if i['suspicion_score'] >= 0.7]
        medium_suspicion = [i for i in all_issues if 0.4 <= i['suspicion_score'] < 0.7]
        low_suspicion = [i for i in all_issues if i['suspicion_score'] < 0.4]
        
        print("\nBy Suspicion Level:")
        print(f"  High (≥0.7): {len(high_suspicion)} characters")
        print(f"  Medium (0.4-0.7): {len(medium_suspicion)} characters")
        print(f"  Low (<0.4): {len(low_suspicion)} characters")
        
        # Japanese compatibility
        incompatible = [i for i in all_issues if not i['japanese_compatible']]
        print(f"\nJapanese Incompatible: {len(incompatible)} characters")
        
        if incompatible:
            print("  (These are likely Chinese-only or Vietnamese Chu Nom)")
        
    else:
        print("✅ No CJK character leaks found! Translation is clean.")
        print()
        print("All Unicode blocks checked:")
        for block in CJKBlock:
            print(f"  ✓ {block.block_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scan_cjk_comprehensive.py <volume_id>")
        print("Example: python scan_cjk_comprehensive.py 1d46")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    scan_volume(volume_id)
