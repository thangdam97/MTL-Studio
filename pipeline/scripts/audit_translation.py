#!/usr/bin/env python3
"""
Comprehensive Translation Audit per AUDIT_AGENT.md standards.
Analyzes 165c translation for Victorian patterns, contractions, AI-isms, and character consistency.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from collections import Counter


@dataclass
class AuditResult:
    """Audit results for a single chapter."""
    chapter_id: str
    word_count: int
    
    # Victorian patterns
    victorian_patterns: List[Tuple[str, str]] = field(default_factory=list)
    
    # Contractions
    contractions_found: int = 0
    expansion_opportunities: int = 0
    contraction_rate: float = 0.0
    expansion_violations: List[Tuple[str, str]] = field(default_factory=list)
    
    # AI-isms
    ai_isms: List[Tuple[str, str]] = field(default_factory=list)
    
    # Character consistency
    character_names_found: Dict[str, int] = field(default_factory=dict)
    
    def calculate_grade(self) -> str:
        """Calculate overall grade based on audit criteria."""
        issues = 0
        
        # Victorian patterns (1 point per instance)
        issues += len(self.victorian_patterns)
        
        # Contraction rate penalties
        if self.contraction_rate < 80:
            issues += 10  # Critical penalty
        elif self.contraction_rate < 90:
            issues += 5
        elif self.contraction_rate < 95:
            issues += 2
        
        # AI-isms (2 points per instance)
        issues += len(self.ai_isms) * 2
        
        # Grade calculation
        if issues == 0:
            return "A+"
        elif issues <= 2:
            return "A"
        elif issues <= 5:
            return "B+"
        elif issues <= 10:
            return "B"
        elif issues <= 15:
            return "C+"
        elif issues <= 25:
            return "C"
        else:
            return "D"


class TranslationAuditor:
    """Audits translation quality per AUDIT_AGENT.md standards."""
    
    # Victorian patterns to detect
    VICTORIAN_PATTERNS = [
        (r'\bI shall\b', "I shall"),
        (r'\bcan you not\b', "can you not"),
        (r'\bdo you not\b', "do you not"),
        (r'\bIf you will excuse me\b', "If you will excuse me"),
        (r'\bIt can vary\b', "It can vary"),
        (r'\bmay I inquire\b', "may I inquire"),
        (r'\bthus\b(?! far)', "thus (not thus far)"),
    ]
    
    # Standard contractions we should find
    STANDARD_CONTRACTIONS = [
        r"\bI'm\b", r"\byou're\b", r"\bhe's\b", r"\bshe's\b", r"\bit's\b",
        r"\bwe're\b", r"\bthey're\b",
        r"\bI'll\b", r"\byou'll\b", r"\bhe'll\b", r"\bshe'll\b", r"\bwe'll\b",
        r"\bthey'll\b",
        r"\bI've\b", r"\byou've\b", r"\bwe've\b", r"\bthey've\b",
        r"\bI'd\b", r"\byou'd\b", r"\bhe'd\b", r"\bshe'd\b", r"\bwe'd\b",
        r"\bthey'd\b",
        r"\bdon't\b", r"\bdoesn't\b", r"\bdidn't\b",
        r"\bwon't\b", r"\bwouldn't\b",
        r"\bcan't\b", r"\bcouldn't\b",
        r"\bisn't\b", r"\baren't\b", r"\bwasn't\b", r"\bweren't\b",
        r"\bhasn't\b", r"\bhaven't\b", r"\bhadn't\b",
        r"\bshouldn't\b", r"\bmustn't\b",
        r"\bthere's\b", r"\bthat's\b", r"\bwhat's\b", r"\bwho's\b",
        r"\bwhere's\b", r"\bwhen's\b", r"\bwhy's\b", r"\bhow's\b",
        r"\bcould've\b", r"\bshould've\b", r"\bwould've\b", r"\bmight've\b",
    ]
    
    # Expansion violations (should be contracted)
    EXPANSION_VIOLATIONS = [
        (r'\bI am\b(?! serious| being| the)', "I am → I'm"),
        (r'\byou are\b', "you are → you're"),
        (r'\bhe is\b', "he is → he's"),
        (r'\bshe is\b', "she is → she's"),
        (r'\bdo not\b', "do not → don't"),
        (r'\bdoes not\b', "does not → doesn't"),
        (r'\bdid not\b', "did not → didn't"),
        (r'\bwill not\b', "will not → won't"),
        (r'\bcannot\b', "cannot → can't"),
        (r'\bthere is\b', "there is → there's"),
        (r'\bthat is\b', "that is → that's"),
        (r'\bwhat is\b', "what is → what's"),
    ]
    
    # AI-ism patterns
    AI_ISMS = [
        (r'\bto be honest\b', "to be honest (AI crutch)"),
        (r'\bI couldn\'t help but\b', "I couldn't help but (AI pattern)"),
        (r'\bI found myself\b', "I found myself (AI pattern)"),
        (r'\ba mix of\b', "a mix of (AI pattern)"),
        (r'\ba sense of\b', "a sense of (overused)"),
        (r'\bseemed to\b', "seemed to (wishy-washy)"),
        (r'\bappeared to\b', "appeared to (wishy-washy)"),
    ]
    
    def __init__(self, en_dir: Path, manifest_path: Path):
        self.en_dir = Path(en_dir)
        self.manifest_path = Path(manifest_path)
        self.manifest = self._load_manifest()
        
    def _load_manifest(self) -> Dict:
        """Load manifest.json for character verification."""
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def audit_chapter(self, file_path: Path) -> AuditResult:
        """Audit a single chapter file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove markdown headers and metadata
        lines = content.split('\n')
        text_lines = [l for l in lines if not l.strip().startswith('#') and not l.strip().startswith('[ILLUSTRATION')]
        text = ' '.join(text_lines)
        
        result = AuditResult(
            chapter_id=file_path.stem,
            word_count=len(text.split())
        )
        
        # Check Victorian patterns
        for pattern, name in self.VICTORIAN_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                context = self._get_context(content, match.start(), match.end())
                result.victorian_patterns.append((name, context))
        
        # Check contractions
        for pattern in self.STANDARD_CONTRACTIONS:
            result.contractions_found += len(re.findall(pattern, content, re.IGNORECASE))
        
        # Check expansion violations
        for pattern, name in self.EXPANSION_VIOLATIONS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                context = self._get_context(content, match.start(), match.end())
                result.expansion_violations.append((name, context))
                result.expansion_opportunities += 1
        
        # Calculate contraction rate
        total = result.contractions_found + result.expansion_opportunities
        if total > 0:
            result.contraction_rate = (result.contractions_found / total) * 100
        
        # Check AI-isms
        for pattern, name in self.AI_ISMS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                context = self._get_context(content, match.start(), match.end())
                result.ai_isms.append((name, context))
        
        # Check character names
        if 'metadata_en' in self.manifest and 'character_profiles' in self.manifest['metadata_en']:
            for char_key, char_data in self.manifest['metadata_en']['character_profiles'].items():
                full_name = char_data.get('full_name', '')
                if full_name:
                    # Extract English name from "name_jp (name_reading)"
                    eng_names = []
                    if 'nickname' in char_data:
                        eng_names.append(char_data['nickname'])
                    
                    for name in eng_names:
                        if name and name in content:
                            result.character_names_found[name] = content.count(name)
        
        return result
    
    def _get_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        """Extract context around a match."""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        context = text[context_start:context_end].strip()
        return f"...{context}..."
    
    def audit_all(self) -> List[AuditResult]:
        """Audit all chapter files."""
        results = []
        
        chapter_files = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        
        for file_path in chapter_files:
            print(f"📖 Auditing {file_path.name}...")
            result = self.audit_chapter(file_path)
            results.append(result)
        
        return results
    
    def generate_report(self, results: List[AuditResult], output_path: Path):
        """Generate comprehensive audit report."""
        # Calculate aggregate statistics
        total_words = sum(r.word_count for r in results)
        total_victorian = sum(len(r.victorian_patterns) for r in results)
        total_contractions = sum(r.contractions_found for r in results)
        total_expansions = sum(r.expansion_opportunities for r in results)
        avg_contraction_rate = sum(r.contraction_rate for r in results) / len(results)
        total_ai_isms = sum(len(r.ai_isms) for r in results)
        
        # Generate markdown report
        report = f"""# Translation Audit Report: 165c
**Date**: 2026-01-29
**Auditor**: Automated per AUDIT_AGENT.md standards
**Volume**: 弓道部の美人な先輩が、俺の部屋でお腹出して寝てる (165c)
**Chapters Audited**: {len(results)}
**Total Words**: {total_words:,}

---

## Executive Summary

### Overall Quality Metrics

| Metric | Result | Standard | Status |
|--------|--------|----------|--------|
| **Contraction Rate** | {avg_contraction_rate:.1f}% | 80% (Pass), 95% (A+) | {'✅ PASS' if avg_contraction_rate >= 80 else '❌ FAIL'} |
| **Victorian Patterns** | {total_victorian} instances | 0 ideal | {'✅ GOOD' if total_victorian < 5 else '⚠️ NEEDS REVIEW'} |
| **AI-isms** | {total_ai_isms} instances | <5 ideal | {'✅ GOOD' if total_ai_isms < 5 else '⚠️ NEEDS REVIEW'} |
| **Expansion Violations** | {total_expansions} | 0 ideal | {'✅ GOOD' if total_expansions < 20 else '⚠️ NEEDS REVIEW'} |

### Aggregate Grade: **{self._calculate_aggregate_grade(results)}**

---

## Chapter-by-Chapter Breakdown

"""
        
        for result in results:
            grade = result.calculate_grade()
            report += f"""### {result.chapter_id} - Grade: {grade}

**Metrics**:
- Words: {result.word_count:,}
- Contraction Rate: {result.contraction_rate:.1f}%
- Victorian Patterns: {len(result.victorian_patterns)}
- AI-isms: {len(result.ai_isms)}
- Expansion Violations: {result.expansion_opportunities}

"""
            
            # Show issues if any
            if result.victorian_patterns:
                report += "**Victorian Patterns Found**:\n"
                for name, context in result.victorian_patterns[:3]:  # Show first 3
                    report += f"- {name}: `{context}`\n"
                if len(result.victorian_patterns) > 3:
                    report += f"- ... and {len(result.victorian_patterns) - 3} more\n"
                report += "\n"
            
            if result.ai_isms:
                report += "**AI-isms Found**:\n"
                for name, context in result.ai_isms[:3]:
                    report += f"- {name}: `{context}`\n"
                if len(result.ai_isms) > 3:
                    report += f"- ... and {len(result.ai_isms) - 3} more\n"
                report += "\n"
            
            if result.expansion_violations:
                report += "**Expansion Violations** (should be contracted):\n"
                for name, context in result.expansion_violations[:3]:
                    report += f"- {name}: `{context}`\n"
                if len(result.expansion_violations) > 3:
                    report += f"- ... and {len(result.expansion_violations) - 3} more\n"
                report += "\n"
            
            report += "---\n\n"
        
        # Write report
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n✅ Audit report saved to: {output_path}")
        
        return report
    
    def _calculate_aggregate_grade(self, results: List[AuditResult]) -> str:
        """Calculate aggregate grade across all chapters."""
        grades = [r.calculate_grade() for r in results]
        grade_values = {'A+': 4, 'A': 3.7, 'B+': 3.3, 'B': 3.0, 'C+': 2.7, 'C': 2.3, 'D': 1.0}
        
        avg_value = sum(grade_values.get(g, 2.0) for g in grades) / len(grades)
        
        if avg_value >= 4.0:
            return "A+"
        elif avg_value >= 3.7:
            return "A"
        elif avg_value >= 3.3:
            return "B+"
        elif avg_value >= 3.0:
            return "B"
        elif avg_value >= 2.7:
            return "C+"
        elif avg_value >= 2.3:
            return "C"
        else:
            return "D"


def main():
    """Main entry point."""
    workspace = Path(__file__).parent.parent
    
    en_dir = workspace / "WORK/弓道部の美人な先輩が、俺の部屋でお腹出して寝てる_20260129_165c/EN"
    manifest_path = workspace / "WORK/弓道部の美人な先輩が、俺の部屋でお腹出して寝てる_20260129_165c/manifest.json"
    output_path = workspace / "WORK/弓道部の美人な先輩が、俺の部屋でお腹出して寝てる_20260129_165c/QC/AUDIT_REPORT_165c.md"
    
    print("🔍 Translation Audit: 165c")
    print("=" * 60)
    print(f"EN Directory: {en_dir}")
    print(f"Manifest: {manifest_path}")
    print("=" * 60)
    
    auditor = TranslationAuditor(en_dir, manifest_path)
    results = auditor.audit_all()
    auditor.generate_report(results, output_path)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 AUDIT SUMMARY")
    print("=" * 60)
    avg_rate = sum(r.contraction_rate for r in results) / len(results)
    total_vic = sum(len(r.victorian_patterns) for r in results)
    total_ai = sum(len(r.ai_isms) for r in results)
    
    print(f"Average Contraction Rate: {avg_rate:.1f}%")
    print(f"Total Victorian Patterns: {total_vic}")
    print(f"Total AI-isms: {total_ai}")
    print(f"Overall Grade: {auditor._calculate_aggregate_grade(results)}")


if __name__ == "__main__":
    main()
