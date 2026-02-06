#!/usr/bin/env python3
"""
Compare Vol 3 new EN output with old EN_preJSON translations.
Focus on overlapping chapters: 02, 03, 04
"""

import re
from pathlib import Path
from difflib import unified_diff

def count_patterns(text):
    """Count various quality metrics in translation"""
    return {
        'total_chars': len(text),
        'total_lines': len(text.split('\n')),
        'emma_chan_narration': len(re.findall(r'(?<![""])\bEmma-chan\b(?!["""])', text)),
        'charlotte_san_narration': len(re.findall(r'(?<![""])\bCharlotte-san\b(?!["""])', text)),
        'emma_chan_total': len(re.findall(r'\bEmma-chan\b', text)),
        'charlotte_san_total': len(re.findall(r'\bCharlotte-san\b', text)),
        'illustrations': len(re.findall(r'!\[.*?\]\(.*?illust-\d+\.jpg\)', text)),
        'ai_isms': len(re.findall(r'\b(quite|rather|indeed|it cannot be helped|I shall)\b', text, re.IGNORECASE)),
    }

def compare_chapter(chapter_num, old_dir, new_dir):
    """Compare single chapter between old and new"""
    chapter_file = f"CHAPTER_{chapter_num:02d}_EN.md"
    old_path = old_dir / chapter_file
    new_path = new_dir / chapter_file
    
    if not old_path.exists():
        return None, f"Old file not found: {chapter_file}"
    if not new_path.exists():
        return None, f"New file not found: {chapter_file}"
    
    # Read files
    with open(old_path, 'r', encoding='utf-8') as f:
        old_text = f.read()
    with open(new_path, 'r', encoding='utf-8') as f:
        new_text = f.read()
    
    # Count metrics
    old_metrics = count_patterns(old_text)
    new_metrics = count_patterns(new_text)
    
    # Calculate differences
    char_diff = new_metrics['total_chars'] - old_metrics['total_chars']
    char_diff_pct = (char_diff / old_metrics['total_chars'] * 100) if old_metrics['total_chars'] > 0 else 0
    
    emma_reduction = old_metrics['emma_chan_narration'] - new_metrics['emma_chan_narration']
    charlotte_reduction = old_metrics['charlotte_san_narration'] - new_metrics['charlotte_san_narration']
    
    return {
        'chapter': chapter_num,
        'old_metrics': old_metrics,
        'new_metrics': new_metrics,
        'char_diff': char_diff,
        'char_diff_pct': char_diff_pct,
        'emma_reduction': emma_reduction,
        'charlotte_reduction': charlotte_reduction,
    }, None

def main():
    vol3_dir = Path("WORK/(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (3)_20260127_0019")
    old_dir = vol3_dir / "EN_preJSON"
    new_dir = vol3_dir / "EN"
    
    print("=" * 70)
    print("VOL 3 TRANSLATION COMPARISON: NEW vs OLD")
    print("=" * 70)
    print(f"Old translations: {old_dir}")
    print(f"New translations: {new_dir}")
    print()
    
    # Compare overlapping chapters
    overlapping_chapters = [2, 3, 4]
    results = []
    
    for chapter_num in overlapping_chapters:
        result, error = compare_chapter(chapter_num, old_dir, new_dir)
        if error:
            print(f"[SKIP] Chapter {chapter_num:02d}: {error}")
        else:
            results.append(result)
    
    if not results:
        print("No chapters to compare!")
        return
    
    # Print detailed comparison
    print("\n" + "=" * 70)
    print("DETAILED COMPARISON")
    print("=" * 70)
    
    for result in results:
        ch = result['chapter']
        old = result['old_metrics']
        new = result['new_metrics']
        
        print(f"\n{'─' * 70}")
        print(f"CHAPTER {ch:02d}")
        print(f"{'─' * 70}")
        
        print(f"\nSize:")
        print(f"  OLD: {old['total_chars']:,} chars, {old['total_lines']:,} lines")
        print(f"  NEW: {new['total_chars']:,} chars, {new['total_lines']:,} lines")
        print(f"  DIFF: {result['char_diff']:+,} chars ({result['char_diff_pct']:+.1f}%)")
        
        print(f"\nSuffix Usage (narration only):")
        print(f"  Emma-chan:")
        print(f"    OLD: {old['emma_chan_narration']} instances")
        print(f"    NEW: {new['emma_chan_narration']} instances")
        print(f"    REDUCTION: {result['emma_reduction']} ({result['emma_reduction']/old['emma_chan_narration']*100 if old['emma_chan_narration'] > 0 else 0:.1f}%)")
        
        print(f"  Charlotte-san:")
        print(f"    OLD: {old['charlotte_san_narration']} instances")
        print(f"    NEW: {new['charlotte_san_narration']} instances")
        print(f"    REDUCTION: {result['charlotte_reduction']} ({result['charlotte_reduction']/old['charlotte_san_narration']*100 if old['charlotte_san_narration'] > 0 else 0:.1f}%)")
        
        print(f"\nTotal Suffix Usage (including dialogue):")
        print(f"  Emma-chan: {old['emma_chan_total']} → {new['emma_chan_total']} ({new['emma_chan_total'] - old['emma_chan_total']:+d})")
        print(f"  Charlotte-san: {old['charlotte_san_total']} → {new['charlotte_san_total']} ({new['charlotte_san_total'] - old['charlotte_san_total']:+d})")
        
        print(f"\nQuality Metrics:")
        print(f"  Illustrations: {old['illustrations']} → {new['illustrations']} ({new['illustrations'] - old['illustrations']:+d})")
        print(f"  AI-isms: {old['ai_isms']} → {new['ai_isms']} ({new['ai_isms'] - old['ai_isms']:+d})")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY ACROSS ALL CHAPTERS")
    print("=" * 70)
    
    total_old_chars = sum(r['old_metrics']['total_chars'] for r in results)
    total_new_chars = sum(r['new_metrics']['total_chars'] for r in results)
    total_char_diff = total_new_chars - total_old_chars
    total_char_diff_pct = (total_char_diff / total_old_chars * 100) if total_old_chars > 0 else 0
    
    total_emma_old = sum(r['old_metrics']['emma_chan_narration'] for r in results)
    total_emma_new = sum(r['new_metrics']['emma_chan_narration'] for r in results)
    total_emma_reduction = total_emma_old - total_emma_new
    
    total_charlotte_old = sum(r['old_metrics']['charlotte_san_narration'] for r in results)
    total_charlotte_new = sum(r['new_metrics']['charlotte_san_narration'] for r in results)
    total_charlotte_reduction = total_charlotte_old - total_charlotte_new
    
    total_ai_isms_old = sum(r['old_metrics']['ai_isms'] for r in results)
    total_ai_isms_new = sum(r['new_metrics']['ai_isms'] for r in results)
    
    print(f"\nChapters compared: {len(results)}")
    print(f"\nTotal size:")
    print(f"  OLD: {total_old_chars:,} chars")
    print(f"  NEW: {total_new_chars:,} chars")
    print(f"  DIFF: {total_char_diff:+,} chars ({total_char_diff_pct:+.1f}%)")
    
    print(f"\nNarration suffix reduction:")
    print(f"  Emma-chan: {total_emma_old} → {total_emma_new} ({total_emma_reduction} cleaned, {total_emma_reduction/total_emma_old*100 if total_emma_old > 0 else 0:.1f}%)")
    print(f"  Charlotte-san: {total_charlotte_old} → {total_charlotte_new} ({total_charlotte_reduction} cleaned, {total_charlotte_reduction/total_charlotte_old*100 if total_charlotte_old > 0 else 0:.1f}%)")
    
    print(f"\nAI-isms:")
    print(f"  OLD: {total_ai_isms_old} instances")
    print(f"  NEW: {total_ai_isms_new} instances")
    print(f"  DIFF: {total_ai_isms_new - total_ai_isms_old:+d} ({(total_ai_isms_new - total_ai_isms_old)/total_ai_isms_old*100 if total_ai_isms_old > 0 else 0:+.1f}%)")
    
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    if total_emma_reduction > 0 or total_charlotte_reduction > 0:
        print("✓ NEW translation shows improved suffix handling")
        print(f"  - {total_emma_reduction + total_charlotte_reduction} narration suffixes cleaned")
    
    if total_char_diff_pct > -5 and total_char_diff_pct < 5:
        print("✓ Character count similar (within 5%)")
    elif total_char_diff_pct < -10:
        print("⚠ NEW translation is significantly shorter (check for content loss)")
    
    if total_ai_isms_new < total_ai_isms_old:
        print(f"✓ AI-isms reduced by {total_ai_isms_old - total_ai_isms_new} instances")
    elif total_ai_isms_new > total_ai_isms_old:
        print(f"⚠ AI-isms increased by {total_ai_isms_new - total_ai_isms_old} instances")
    
    print("=" * 70)

if __name__ == '__main__':
    main()
