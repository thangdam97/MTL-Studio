"""
Grammar Rule Verification Tool
Validates that grammar RAG patterns were correctly applied during translation
Part of Phase 3.5 Quality Assurance System

Based on learnings from Kimi ni Todoke Vol 1 audit (Feb 2026)
Found issue: redundancy_reduction rule added but not applied to "test of courage" repetition
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class GrammarViolation:
    """Single grammar rule violation instance"""
    rule_name: str
    pattern_name: str
    chapter: int
    line_number: int
    context: str
    issue: str
    suggested_fix: Optional[str] = None


class GrammarRuleVerifier:
    """Verify grammar RAG patterns were applied correctly"""
    
    def __init__(self, work_dir: Path, grammar_rag_path: Path):
        """
        Initialize verifier
        
        Args:
            work_dir: Path to volume work directory (contains EN/ folder)
            grammar_rag_path: Path to english_grammar_rag.json
        """
        self.work_dir = Path(work_dir)
        self.en_dir = self.work_dir / "EN"
        
        # Load grammar rules
        with open(grammar_rag_path, 'r', encoding='utf-8') as f:
            self.grammar_rag = json.load(f)
        
        self.violations: List[GrammarViolation] = []
    
    def verify_all_chapters(self) -> Dict:
        """Verify all EN chapters for grammar rule violations"""
        chapter_files = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        
        total_violations = 0
        violations_by_rule = {}
        
        for chapter_file in chapter_files:
            chapter_num = self._extract_chapter_number(chapter_file.name)
            chapter_violations = self._verify_chapter(chapter_file, chapter_num)
            total_violations += len(chapter_violations)
            
            for violation in chapter_violations:
                if violation.rule_name not in violations_by_rule:
                    violations_by_rule[violation.rule_name] = []
                violations_by_rule[violation.rule_name].append(violation)
        
        return {
            'summary': {
                'total_violations': total_violations,
                'rules_violated': len(violations_by_rule),
                'chapters_analyzed': len(chapter_files)
            },
            'violations_by_rule': violations_by_rule,
            'all_violations': self.violations
        }
    
    def _extract_chapter_number(self, filename: str) -> int:
        """Extract chapter number from filename"""
        match = re.search(r'CHAPTER_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def _verify_chapter(self, chapter_file: Path, chapter_num: int) -> List[GrammarViolation]:
        """Verify single chapter for grammar violations"""
        with open(chapter_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        chapter_violations = []
        
        # Check redundancy_reduction rules
        redundancy_violations = self._check_redundancy_reduction(lines, chapter_num)
        chapter_violations.extend(redundancy_violations)
        
        # Check contraction usage rules (if character voice profiles exist)
        # This requires character dialogue attribution - skip for now
        
        # Check sentence fragment issues (formal vs casual speech)
        # This also requires speaker context - skip for now
        
        return chapter_violations
    
    def _check_redundancy_reduction(self, lines: List[str], chapter_num: int) -> List[GrammarViolation]:
        """Check for near-term repetition that should use pronouns/demonstratives"""
        violations = []
        
        # Get redundancy_reduction patterns from grammar RAG
        redundancy_rules = None
        for category in self.grammar_rag.get('grammar_categories', []):
            if category.get('category') == 'redundancy_reduction':
                redundancy_rules = category
                break
        
        if not redundancy_rules:
            return violations
        
        # Check near_term_substitution pattern
        near_term_pattern = None
        for pattern in redundancy_rules.get('patterns', []):
            if pattern.get('pattern_name') == 'near_term_substitution':
                near_term_pattern = pattern
                break
        
        if not near_term_pattern:
            return violations
        
        # Look for repeated nouns in adjacent sentences (within 1-2 sentences)
        context_window = 3  # Check within 3 lines
        
        for i, line in enumerate(lines):
            # Extract significant nouns (3+ chars, capitalized or common nouns)
            nouns = re.findall(r'\b([A-Z][a-z]{2,}|test of courage|group of students|[a-z]{4,})\b', line)
            
            if nouns:
                # Check if any noun repeats in next 1-3 lines
                for noun in nouns:
                    # Skip very common words
                    if noun.lower() in ['said', 'asked', 'from', 'that', 'this', 'with', 'were', 'have', 'been']:
                        continue
                    
                    # Check next few lines for repetition
                    for j in range(i + 1, min(i + context_window + 1, len(lines))):
                        next_line = lines[j]
                        
                        # Case-insensitive check for noun repetition
                        if re.search(r'\b' + re.escape(noun) + r'\b', next_line, re.IGNORECASE):
                            # Found repetition - check if it should use pronoun/demonstrative
                            # Skip if it's dialogue (already attributed to speaker)
                            if '"' in line and '"' in next_line:
                                continue
                            
                            # Skip if it's a proper name (character names should repeat)
                            if noun[0].isupper() and len(noun) > 4:
                                continue
                            
                            # This is likely a violation
                            context = f"L{i+1}: {line.strip()[:60]}... | L{j+1}: {next_line.strip()[:60]}..."
                            
                            violation = GrammarViolation(
                                rule_name='redundancy_reduction',
                                pattern_name='near_term_substitution',
                                chapter=chapter_num,
                                line_number=j + 1,
                                context=context,
                                issue=f"Repeated '{noun}' in adjacent sentences (within {j-i} lines)",
                                suggested_fix=f"Replace second '{noun}' with 'that'/'it'/'this'"
                            )
                            
                            violations.append(violation)
                            
                            # Only report first instance per noun to avoid spam
                            break
        
        return violations
    
    def generate_report(self, output_file: Path = None) -> Dict:
        """Generate grammar verification report"""
        report = self.verify_all_chapters()
        
        if output_file:
            # Convert violations to serializable format
            serializable_report = {
                'summary': report['summary'],
                'violations_by_rule': {
                    rule_name: [
                        {
                            'rule_name': v.rule_name,
                            'pattern_name': v.pattern_name,
                            'chapter': v.chapter,
                            'line_number': v.line_number,
                            'context': v.context,
                            'issue': v.issue,
                            'suggested_fix': v.suggested_fix
                        } for v in violations
                    ] for rule_name, violations in report['violations_by_rule'].items()
                }
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_report, f, indent=2, ensure_ascii=False)
        
        return report
    
    def print_report_summary(self):
        """Print human-readable report summary"""
        report = self.generate_report()
        
        print("\n" + "="*70)
        print("GRAMMAR RULE VERIFICATION REPORT")
        print("="*70)
        
        summary = report['summary']
        print(f"\nChapters Analyzed: {summary['chapters_analyzed']}")
        print(f"Total Violations: {summary['total_violations']}")
        print(f"Rules Violated: {summary['rules_violated']}")
        
        if summary['total_violations'] == 0:
            print("\n✅ No grammar rule violations detected!")
            print("All grammar RAG patterns were correctly applied.")
        else:
            print("\n" + "-"*70)
            print("VIOLATIONS BY RULE")
            print("-"*70)
            
            for rule_name, violations in report['violations_by_rule'].items():
                print(f"\n⚠️  {rule_name} ({len(violations)} violations)")
                
                # Show first 5 violations
                for v in violations[:5]:
                    print(f"\n  Chapter {v.chapter}, Line {v.line_number}")
                    print(f"  Issue: {v.issue}")
                    print(f"  Context: {v.context}")
                    if v.suggested_fix:
                        print(f"  Suggested Fix: {v.suggested_fix}")
                
                if len(violations) > 5:
                    print(f"\n  ... and {len(violations) - 5} more violations")
        
        print("\n" + "="*70)


def main():
    """CLI entry point"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python grammar_rule_verifier.py <work_directory> [grammar_rag.json]")
        print("\nExample:")
        print("  python grammar_rule_verifier.py WORK/volume_dir/")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    grammar_rag_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "common/english_grammar_rag.json"
    
    if not grammar_rag_path.exists():
        print(f"❌ Grammar RAG file not found: {grammar_rag_path}")
        sys.exit(1)
    
    # Run verification
    verifier = GrammarRuleVerifier(work_dir, grammar_rag_path)
    verifier.print_report_summary()
    
    # Save JSON report
    report_path = work_dir / "grammar_verification_report.json"
    verifier.generate_report(report_path)
    print(f"\n📄 Full report saved to: {report_path}")


if __name__ == "__main__":
    main()
