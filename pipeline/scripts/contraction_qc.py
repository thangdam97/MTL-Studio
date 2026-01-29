#!/usr/bin/env python3
"""
Contraction Rate QC Tool - Yen Press/J-Novel Club Gold Standard

Scans translation files for non-contracted forms and provides:
1. Critical violations (MUST contract)
2. High-priority violations (SHOULD contract)
3. Statistics and projected improvement

Usage:
    python contraction_qc.py <file_or_directory>
    python contraction_qc.py --fix <file>  # Auto-fix (creates backup)
"""

import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

# ============================================================
# GOLD STANDARD DEFINITIONS (Yen Press / J-Novel Club)
# ============================================================

# Priority 1: CRITICAL - Must contract in ALL casual contexts
CRITICAL_CONTRACTIONS = [
    (r"\bit is\b", "it's", "it is"),
    (r"\bthat is\b", "that's", "that is"),
    (r"\bthere is\b", "there's", "there is"),
    (r"\bhere is\b", "here's", "here is"),
    (r"\bwhat is\b", "what's", "what is"),
    (r"\bwho is\b", "who's", "who is"),
    (r"\bdo not\b", "don't", "do not"),
    (r"\bdoes not\b", "doesn't", "does not"),
]

# Priority 2: HIGH - Should contract unless emphatic/formal
HIGH_PRIORITY_CONTRACTIONS = [
    (r"\bwas not\b", "wasn't", "was not"),
    (r"\bwere not\b", "weren't", "were not"),
    (r"\bcould not\b", "couldn't", "could not"),
    (r"\bshould not\b", "shouldn't", "should not"),
    (r"\bwould not\b", "wouldn't", "would not"),
    (r"\bdid not\b", "didn't", "did not"),
    (r"\bhad not\b", "hadn't", "had not"),
    (r"\bcould do nothing\b", "couldn't do anything", "could do nothing"),
]

# Priority 3: STANDARD - Contract in casual dialogue
STANDARD_CONTRACTIONS = [
    (r"\bis not\b", "isn't", "is not"),
    (r"\bare not\b", "aren't", "are not"),
    (r"\bhave not\b", "haven't", "have not"),
    (r"\bhas not\b", "hasn't", "has not"),
    (r"\bwill not\b", "won't", "will not"),
    (r"\bcannot\b", "can't", "cannot"),
    (r"\bI am\b", "I'm", "I am"),
    (r"\byou are\b", "you're", "you are"),
    (r"\bwe are\b", "we're", "we are"),
    (r"\bthey are\b", "they're", "they are"),
    (r"\bI will\b", "I'll", "I will"),
    (r"\byou will\b", "you'll", "you will"),
    (r"\bI have\b", "I've", "I have"),
    (r"\byou have\b", "you've", "you have"),
    (r"\blet us\b", "let's", "let us"),
]

# Priority 4: J-Novel Club perfect tense (internal monologue)
PERFECT_TENSE_CONTRACTIONS = [
    (r"\bwould have\b", "would've", "would have"),
    (r"\bcould have\b", "could've", "could have"),
    (r"\bshould have\b", "should've", "should have"),
    (r"\bmight have\b", "might've", "might have"),
    (r"\bmust have\b", "must've", "must have"),
]

@dataclass
class Violation:
    """Represents a contraction violation."""
    line_num: int
    priority: str
    full_form: str
    contracted: str
    context: str
    in_dialogue: bool

def find_violations(content: str) -> Tuple[List[Violation], Dict]:
    """Find all contraction violations in content."""
    violations = []
    stats = {
        'critical': 0,
        'high_priority': 0,
        'standard': 0,
        'perfect_tense': 0,
        'total_contracted': 0,
        'total_opportunities': 0,
    }
    
    lines = content.split('\n')
    dialogue_pattern = r'"([^"]+)"'
    
    for line_num, line in enumerate(lines, 1):
        # Check if line contains dialogue
        dialogues = re.findall(dialogue_pattern, line)
        in_dialogue = bool(dialogues)
        
        # Check critical violations
        for pattern, contracted, full_form in CRITICAL_CONTRACTIONS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                violations.append(Violation(
                    line_num=line_num,
                    priority='CRITICAL',
                    full_form=full_form,
                    contracted=contracted,
                    context=line.strip()[:80],
                    in_dialogue=in_dialogue
                ))
                stats['critical'] += 1
                stats['total_opportunities'] += 1
        
        # Check high priority violations
        for pattern, contracted, full_form in HIGH_PRIORITY_CONTRACTIONS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                violations.append(Violation(
                    line_num=line_num,
                    priority='HIGH',
                    full_form=full_form,
                    contracted=contracted,
                    context=line.strip()[:80],
                    in_dialogue=in_dialogue
                ))
                stats['high_priority'] += 1
                stats['total_opportunities'] += 1
        
        # Check standard violations
        for pattern, contracted, full_form in STANDARD_CONTRACTIONS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                violations.append(Violation(
                    line_num=line_num,
                    priority='STANDARD',
                    full_form=full_form,
                    contracted=contracted,
                    context=line.strip()[:80],
                    in_dialogue=in_dialogue
                ))
                stats['standard'] += 1
                stats['total_opportunities'] += 1
        
        # Check perfect tense violations
        for pattern, contracted, full_form in PERFECT_TENSE_CONTRACTIONS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                violations.append(Violation(
                    line_num=line_num,
                    priority='PERFECT_TENSE',
                    full_form=full_form,
                    contracted=contracted,
                    context=line.strip()[:80],
                    in_dialogue=in_dialogue
                ))
                stats['perfect_tense'] += 1
                stats['total_opportunities'] += 1
        
        # Count existing contractions
        contraction_pattern = r"'(m|ll|ve|d|re|t|s)\b"
        stats['total_contracted'] += len(re.findall(contraction_pattern, line))
    
    return violations, stats

def calculate_rate(stats: Dict) -> float:
    """Calculate contraction rate."""
    total = stats['total_contracted'] + stats['total_opportunities']
    if total == 0:
        return 1.0
    return stats['total_contracted'] / total

def auto_fix(content: str) -> str:
    """Auto-fix all contraction violations."""
    fixed = content
    
    # Apply fixes in order of priority
    all_contractions = (
        CRITICAL_CONTRACTIONS + 
        HIGH_PRIORITY_CONTRACTIONS + 
        STANDARD_CONTRACTIONS + 
        PERFECT_TENSE_CONTRACTIONS
    )
    
    for pattern, contracted, _ in all_contractions:
        # Preserve case for first letter
        def replace_preserve_case(match):
            original = match.group(0)
            if original[0].isupper():
                return contracted[0].upper() + contracted[1:]
            return contracted
        
        fixed = re.sub(pattern, replace_preserve_case, fixed, flags=re.IGNORECASE)
    
    return fixed

def print_report(violations: List[Violation], stats: Dict, filepath: str):
    """Print detailed QC report."""
    rate = calculate_rate(stats)
    
    print("\n" + "=" * 70)
    print(f"CONTRACTION QC REPORT - Yen Press/J-Novel Club Gold Standard")
    print("=" * 70)
    print(f"File: {filepath}")
    print(f"Current Rate: {rate:.2%}")
    print(f"Gold Standard: 99%+")
    print(f"Gap: {max(0, 0.99 - rate):.2%}")
    print("-" * 70)
    
    # Summary
    total_violations = stats['critical'] + stats['high_priority'] + stats['standard'] + stats['perfect_tense']
    print(f"\n📊 SUMMARY")
    print(f"  Total contractions found: {stats['total_contracted']}")
    print(f"  Total violations found: {total_violations}")
    print(f"    - Critical (MUST fix): {stats['critical']}")
    print(f"    - High priority: {stats['high_priority']}")
    print(f"    - Standard: {stats['standard']}")
    print(f"    - Perfect tense: {stats['perfect_tense']}")
    
    # Grade
    if rate >= 0.99:
        grade = "A+ (Gold Standard)"
    elif rate >= 0.95:
        grade = "A (Professional)"
    elif rate >= 0.90:
        grade = "B (Good)"
    elif rate >= 0.80:
        grade = "C (Acceptable)"
    else:
        grade = "D (Needs Work)"
    
    print(f"\n📈 GRADE: {grade}")
    
    # Projected improvement
    if total_violations > 0:
        projected_contracted = stats['total_contracted'] + total_violations
        projected_rate = projected_contracted / (projected_contracted)
        print(f"\n🎯 PROJECTED RATE AFTER FIXES: 100% (all opportunities contracted)")
    
    # Detailed violations
    if violations:
        print("\n" + "-" * 70)
        print("VIOLATIONS BY PRIORITY")
        print("-" * 70)
        
        # Critical
        critical = [v for v in violations if v.priority == 'CRITICAL']
        if critical:
            print(f"\n🔴 CRITICAL ({len(critical)}) - MUST CONTRACT:")
            for v in critical[:10]:
                dialogue_marker = "[dialogue]" if v.in_dialogue else "[narration]"
                print(f"  Line {v.line_num} {dialogue_marker}: \"{v.full_form}\" → \"{v.contracted}\"")
                print(f"    Context: {v.context}")
        
        # High priority
        high = [v for v in violations if v.priority == 'HIGH']
        if high:
            print(f"\n🟠 HIGH PRIORITY ({len(high)}) - SHOULD CONTRACT:")
            for v in high[:10]:
                dialogue_marker = "[dialogue]" if v.in_dialogue else "[narration]"
                print(f"  Line {v.line_num} {dialogue_marker}: \"{v.full_form}\" → \"{v.contracted}\"")
                print(f"    Context: {v.context}")
        
        # Standard
        standard = [v for v in violations if v.priority == 'STANDARD']
        if standard:
            print(f"\n🟡 STANDARD ({len(standard)}):")
            for v in standard[:5]:
                print(f"  Line {v.line_num}: \"{v.full_form}\" → \"{v.contracted}\"")
        
        # Perfect tense
        perfect = [v for v in violations if v.priority == 'PERFECT_TENSE']
        if perfect:
            print(f"\n🔵 PERFECT TENSE ({len(perfect)}) - J-Novel Club Style:")
            for v in perfect[:5]:
                print(f"  Line {v.line_num}: \"{v.full_form}\" → \"{v.contracted}\"")
    
    print("\n" + "=" * 70)
    
    # Quick fix command
    if violations:
        print("\n💡 To auto-fix, run:")
        print(f"   python contraction_qc.py --fix \"{filepath}\"")

def main():
    parser = argparse.ArgumentParser(
        description="Contraction Rate QC Tool - Yen Press/J-Novel Club Gold Standard"
    )
    parser.add_argument('path', help='File or directory to scan')
    parser.add_argument('--fix', action='store_true', help='Auto-fix violations (creates .bak backup)')
    parser.add_argument('--quiet', action='store_true', help='Only show summary')
    
    args = parser.parse_args()
    path = Path(args.path)
    
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = list(path.glob('**/*.md'))
    else:
        print(f"Error: {path} not found")
        sys.exit(1)
    
    total_violations = 0
    
    for filepath in files:
        content = filepath.read_text(encoding='utf-8')
        violations, stats = find_violations(content)
        total_violations += len(violations)
        
        if args.fix:
            # Create backup
            backup_path = filepath.with_suffix(filepath.suffix + '.bak')
            backup_path.write_text(content, encoding='utf-8')
            
            # Apply fixes
            fixed_content = auto_fix(content)
            filepath.write_text(fixed_content, encoding='utf-8')
            
            # Report
            _, new_stats = find_violations(fixed_content)
            new_rate = calculate_rate(new_stats)
            print(f"✅ Fixed {filepath.name}: {calculate_rate(stats):.2%} → {new_rate:.2%}")
        else:
            if not args.quiet or violations:
                print_report(violations, stats, str(filepath))
    
    if args.fix:
        print(f"\n✅ Fixed {len(files)} files. Backups created with .bak extension.")
    
    sys.exit(0 if total_violations == 0 else 1)

if __name__ == '__main__':
    main()
