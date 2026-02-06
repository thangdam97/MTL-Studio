"""
SUBAGENT 1: Content Fidelity Auditor
=====================================
Mission: ZERO TOLERANCE for truncation, censorship, or lazy summarization.
Every Japanese source line must have corresponding English translation.

Output: fidelity_audit_report.json
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class IssueSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IssueType(Enum):
    TRUNCATION = "TRUNCATION"
    CENSORSHIP = "CENSORSHIP"
    SUMMARIZATION = "SUMMARIZATION"
    OMISSION = "OMISSION"
    ADDITION = "ADDITION"


@dataclass
class FidelityIssue:
    issue_id: str
    issue_type: str
    severity: str
    chapter_id: str
    jp_line: int
    jp_content: str
    en_line: Optional[int]
    en_content: Optional[str]
    analysis: str
    content_loss: str
    recommendation: str


@dataclass
class ChapterFidelityResult:
    chapter_id: str
    jp_title: str
    en_title: str
    jp_lines: int
    en_lines: int
    jp_content_units: int
    jp_dialogues: int
    en_dialogues: int
    jp_paragraphs: int
    en_paragraphs: int
    issues: List[Dict]


class FidelityAuditor:
    """
    Content Fidelity Auditor - Subagent 1
    
    Validates that translated content preserves all source material
    without truncation, censorship, or lazy summarization.
    """
    
    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)
        self.jp_dir = self.work_dir / "JP"
        self.en_dir = self.work_dir / "EN"
        self.issues: List[FidelityIssue] = []
        self.chapter_results: List[ChapterFidelityResult] = []
        
        # Thresholds
        self.thresholds = {
            "pass": 5.0,          # <5% deviation
            "review": 10.0,       # 5-10% deviation
            "fail": 15.0,         # >10% but <15%
            "critical_fail": 15.0  # >15% blocks publication
        }
        
        # Censorship detection keywords
        self.intimate_keywords_jp = [
            "キス", "抱き", "胸", "触", "唇", "ドキドキ", 
            "恥ずかし", "頬", "赤く", "近づ", "囁"
        ]
        
    def audit(self) -> Dict:
        """Run full fidelity audit on all chapters."""
        
        print("=" * 60)
        print("SUBAGENT 1: CONTENT FIDELITY AUDITOR")
        print("=" * 60)
        
        # Get chapter files
        jp_chapters = sorted(self.jp_dir.glob("CHAPTER_*.md"))
        en_chapters = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        
        if not jp_chapters:
            raise FileNotFoundError(f"No JP chapters found in {self.jp_dir}")
        if not en_chapters:
            raise FileNotFoundError(f"No EN chapters found in {self.en_dir}")
            
        print(f"Found {len(jp_chapters)} JP chapters, {len(en_chapters)} EN chapters")
        
        total_jp_lines = 0
        total_en_lines = 0
        total_jp_units = 0
        total_missing_units = 0
        total_altered_units = 0
        
        # Audit each chapter
        for jp_file in jp_chapters:
            chapter_num = self._extract_chapter_num(jp_file.name)
            en_file = self.en_dir / f"CHAPTER_{chapter_num:02d}_EN.md"
            
            if not en_file.exists():
                self._add_issue(
                    issue_type=IssueType.OMISSION,
                    severity=IssueSeverity.CRITICAL,
                    chapter_id=f"{chapter_num:02d}",
                    jp_line=0,
                    jp_content=f"Entire chapter {chapter_num}",
                    en_line=None,
                    en_content=None,
                    analysis=f"Chapter {chapter_num} EN translation missing entirely",
                    content_loss="Entire chapter",
                    recommendation=f"Translate CHAPTER_{chapter_num:02d}.md"
                )
                continue
            
            print(f"\n📖 Auditing Chapter {chapter_num:02d}...")
            result = self._audit_chapter(jp_file, en_file, chapter_num)
            self.chapter_results.append(result)
            
            total_jp_lines += result.jp_lines
            total_en_lines += result.en_lines
            total_jp_units += result.jp_content_units
            
        # Calculate totals
        for issue in self.issues:
            if issue.issue_type in [IssueType.TRUNCATION.value, IssueType.OMISSION.value]:
                total_missing_units += 1
            elif issue.issue_type in [IssueType.CENSORSHIP.value, IssueType.SUMMARIZATION.value]:
                total_altered_units += 1
        
        # Calculate deviation
        deviation_percent = ((total_missing_units + total_altered_units) / max(total_jp_units, 1)) * 100
        
        # Determine verdict
        verdict = self._calculate_verdict(deviation_percent)
        
        # Build report
        report = self._build_report(
            total_jp_lines=total_jp_lines,
            total_en_lines=total_en_lines,
            total_jp_units=total_jp_units,
            total_missing=total_missing_units,
            total_altered=total_altered_units,
            deviation_percent=deviation_percent,
            verdict=verdict
        )
        
        print(f"\n{'=' * 60}")
        print(f"FIDELITY AUDIT COMPLETE")
        print(f"Deviation: {deviation_percent:.2f}% | Verdict: {verdict}")
        print(f"{'=' * 60}")
        
        return report
    
    def _audit_chapter(self, jp_file: Path, en_file: Path, chapter_num: int) -> ChapterFidelityResult:
        """Audit a single chapter for content fidelity."""
        
        jp_text = jp_file.read_text(encoding='utf-8')
        en_text = en_file.read_text(encoding='utf-8')
        
        jp_lines = jp_text.strip().split('\n')
        en_lines = en_text.strip().split('\n')
        
        # Extract titles
        jp_title = self._extract_title(jp_lines)
        en_title = self._extract_title(en_lines)
        
        # Count content units
        jp_dialogues = self._count_dialogues(jp_text)
        en_dialogues = self._count_dialogues(en_text)
        
        jp_paragraphs = self._count_paragraphs(jp_text)
        en_paragraphs = self._count_paragraphs(en_text)
        
        jp_content_units = jp_dialogues + jp_paragraphs
        
        # Check for truncation
        self._check_truncation(jp_lines, en_lines, chapter_num)
        
        # Check for censorship
        self._check_censorship(jp_text, en_text, chapter_num)
        
        # Check for summarization
        self._check_summarization(jp_paragraphs, en_paragraphs, chapter_num)
        
        # Check dialogue count
        if abs(jp_dialogues - en_dialogues) > jp_dialogues * 0.1:
            self._add_issue(
                issue_type=IssueType.OMISSION,
                severity=IssueSeverity.HIGH,
                chapter_id=f"{chapter_num:02d}",
                jp_line=0,
                jp_content=f"JP has {jp_dialogues} dialogues",
                en_line=0,
                en_content=f"EN has {en_dialogues} dialogues",
                analysis=f"Dialogue count mismatch: {jp_dialogues} JP vs {en_dialogues} EN",
                content_loss=f"{abs(jp_dialogues - en_dialogues)} dialogue lines",
                recommendation="Review and restore missing dialogue"
            )
        
        chapter_issues = [
            asdict(i) for i in self.issues 
            if i.chapter_id == f"{chapter_num:02d}"
        ]
        
        return ChapterFidelityResult(
            chapter_id=f"{chapter_num:02d}",
            jp_title=jp_title,
            en_title=en_title,
            jp_lines=len(jp_lines),
            en_lines=len(en_lines),
            jp_content_units=jp_content_units,
            jp_dialogues=jp_dialogues,
            en_dialogues=en_dialogues,
            jp_paragraphs=jp_paragraphs,
            en_paragraphs=en_paragraphs,
            issues=chapter_issues
        )
    
    def _check_truncation(self, jp_lines: List[str], en_lines: List[str], chapter_num: int):
        """Check for truncated content by comparing line lengths."""
        
        # Simple heuristic: if JP has significantly more content lines
        jp_content_lines = [l for l in jp_lines if l.strip() and not l.startswith('#')]
        en_content_lines = [l for l in en_lines if l.strip() and not l.startswith('#')]
        
        # Check for very short EN lines that should be longer
        for i, jp_line in enumerate(jp_content_lines[:min(len(jp_content_lines), len(en_content_lines))]):
            if len(jp_line) > 50:  # Long JP line
                if i < len(en_content_lines):
                    en_line = en_content_lines[i]
                    # JP has 50+ chars but EN has <20 words - potential truncation
                    en_words = len(en_line.split())
                    if en_words < 10 and len(jp_line) > 80:
                        self._add_issue(
                            issue_type=IssueType.TRUNCATION,
                            severity=IssueSeverity.HIGH,
                            chapter_id=f"{chapter_num:02d}",
                            jp_line=i + 1,
                            jp_content=jp_line[:100] + "..." if len(jp_line) > 100 else jp_line,
                            en_line=i + 1,
                            en_content=en_line,
                            analysis=f"JP line has {len(jp_line)} chars but EN has only {en_words} words",
                            content_loss="Descriptive content potentially lost",
                            recommendation="Review and expand translation to match source detail"
                        )
    
    def _check_censorship(self, jp_text: str, en_text: str, chapter_num: int):
        """Check for potential censorship of intimate content."""
        
        # Check if JP has intimate keywords
        intimate_count = sum(1 for kw in self.intimate_keywords_jp if kw in jp_text)
        
        if intimate_count > 0:
            # Check EN for corresponding intimate content
            intimate_en_markers = [
                "kiss", "embrace", "chest", "touch", "lips", 
                "heart pound", "blush", "cheek", "lean", "whisper"
            ]
            en_intimate_count = sum(1 for m in intimate_en_markers if m.lower() in en_text.lower())
            
            # If JP has intimate content but EN is significantly lacking
            if intimate_count > 3 and en_intimate_count < intimate_count * 0.5:
                self._add_issue(
                    issue_type=IssueType.CENSORSHIP,
                    severity=IssueSeverity.CRITICAL,
                    chapter_id=f"{chapter_num:02d}",
                    jp_line=0,
                    jp_content=f"JP has {intimate_count} intimate markers",
                    en_line=0,
                    en_content=f"EN has only {en_intimate_count} intimate markers",
                    analysis="Potential censorship: intimate content may have been softened",
                    content_loss="Romantic/intimate atmosphere",
                    recommendation="Review intimate scenes for content preservation"
                )
    
    def _check_summarization(self, jp_paragraphs: int, en_paragraphs: int, chapter_num: int):
        """Check for lazy summarization (multiple JP paragraphs merged into one)."""
        
        if jp_paragraphs > en_paragraphs * 1.2:  # JP has 20%+ more paragraphs
            self._add_issue(
                issue_type=IssueType.SUMMARIZATION,
                severity=IssueSeverity.MEDIUM,
                chapter_id=f"{chapter_num:02d}",
                jp_line=0,
                jp_content=f"JP has {jp_paragraphs} paragraphs",
                en_line=0,
                en_content=f"EN has {en_paragraphs} paragraphs",
                analysis=f"Paragraph count mismatch suggests content condensation",
                content_loss="Narrative pacing and detail",
                recommendation="Review for merged/summarized paragraphs"
            )
    
    def _add_issue(self, issue_type: IssueType, severity: IssueSeverity, 
                   chapter_id: str, jp_line: int, jp_content: str,
                   en_line: Optional[int], en_content: Optional[str],
                   analysis: str, content_loss: str, recommendation: str):
        """Add a fidelity issue to the list."""
        
        issue_id = f"FID-{chapter_id}-{len(self.issues) + 1:03d}"
        
        self.issues.append(FidelityIssue(
            issue_id=issue_id,
            issue_type=issue_type.value,
            severity=severity.value,
            chapter_id=chapter_id,
            jp_line=jp_line,
            jp_content=jp_content,
            en_line=en_line,
            en_content=en_content,
            analysis=analysis,
            content_loss=content_loss,
            recommendation=recommendation
        ))
    
    def _extract_chapter_num(self, filename: str) -> int:
        """Extract chapter number from filename."""
        match = re.search(r'CHAPTER_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def _extract_title(self, lines: List[str]) -> str:
        """Extract chapter title from first heading."""
        for line in lines[:10]:
            if line.startswith('#'):
                return line.lstrip('#').strip()
        return "Unknown"
    
    def _count_dialogues(self, text: str) -> int:
        """Count dialogue lines (lines with quotes)."""
        # Match Japanese quotes「」or English quotes ""
        jp_dialogues = len(re.findall(r'「[^」]+」', text))
        en_dialogues = len(re.findall(r'"[^"]+"|"[^"]+"', text))
        return max(jp_dialogues, en_dialogues)
    
    def _count_paragraphs(self, text: str) -> int:
        """Count paragraphs (blocks separated by blank lines)."""
        paragraphs = re.split(r'\n\s*\n', text.strip())
        return len([p for p in paragraphs if p.strip()])
    
    def _calculate_verdict(self, deviation_percent: float) -> str:
        """Calculate verdict based on deviation percentage."""
        if deviation_percent < self.thresholds["pass"]:
            return "PASS"
        elif deviation_percent < self.thresholds["review"]:
            return "REVIEW"
        elif deviation_percent < self.thresholds["critical_fail"]:
            return "FAIL"
        else:
            return "CRITICAL_FAIL"
    
    def _build_report(self, total_jp_lines: int, total_en_lines: int,
                      total_jp_units: int, total_missing: int, 
                      total_altered: int, deviation_percent: float,
                      verdict: str) -> Dict:
        """Build the final fidelity audit report."""
        
        # Categorize issues
        issue_categories = {}
        for issue_type in IssueType:
            type_issues = [i for i in self.issues if i.issue_type == issue_type.value]
            issue_categories[issue_type.value] = {
                "description": self._get_issue_description(issue_type),
                "count": len(type_issues),
                "severity": self._get_issue_severity(issue_type),
                "examples": [i.issue_id for i in type_issues[:3]]
            }
        
        # Calculate dialogue and paragraph totals
        total_jp_dialogues = sum(c.jp_dialogues for c in self.chapter_results)
        total_en_dialogues = sum(c.en_dialogues for c in self.chapter_results)
        total_jp_paragraphs = sum(c.jp_paragraphs for c in self.chapter_results)
        total_en_paragraphs = sum(c.en_paragraphs for c in self.chapter_results)
        
        line_variance = abs(total_jp_lines - total_en_lines) / max(total_jp_lines, 1) * 100
        
        report = {
            "audit_type": "content_fidelity",
            "volume_id": self.work_dir.name.split('_')[-1][:4] if '_' in self.work_dir.name else "unknown",
            "timestamp": datetime.now().isoformat(),
            "auditor_version": "2.0",
            
            "summary": {
                "total_jp_lines": total_jp_lines,
                "total_en_lines": total_en_lines,
                "line_variance_percent": round(line_variance, 2),
                "total_jp_content_units": total_jp_units,
                "missing_content_units": total_missing,
                "altered_content_units": total_altered,
                "deviation_percent": round(deviation_percent, 2),
                "verdict": verdict
            },
            
            "thresholds": {
                "pass": "<5% deviation",
                "review": "5-10% deviation",
                "fail": ">10% deviation",
                "critical_fail": ">15% deviation (blocks publication)"
            },
            
            "chapters": [asdict(c) for c in self.chapter_results],
            
            "issue_categories": issue_categories,
            
            "validation_checks": {
                "dialogue_count_match": {
                    "jp_dialogue_lines": total_jp_dialogues,
                    "en_dialogue_lines": total_en_dialogues,
                    "variance": abs(total_jp_dialogues - total_en_dialogues),
                    "status": "PASS" if abs(total_jp_dialogues - total_en_dialogues) < total_jp_dialogues * 0.1 else "FAIL"
                },
                "paragraph_count_match": {
                    "jp_paragraphs": total_jp_paragraphs,
                    "en_paragraphs": total_en_paragraphs,
                    "variance": abs(total_jp_paragraphs - total_en_paragraphs),
                    "status": "PASS" if abs(total_jp_paragraphs - total_en_paragraphs) < total_jp_paragraphs * 0.15 else "FAIL"
                }
            },
            
            "all_issues": [asdict(i) for i in self.issues],
            
            "final_verdict": {
                "grade": self._verdict_to_grade(verdict),
                "deviation_percent": round(deviation_percent, 2),
                "status": verdict,
                "blocking_issues": len([i for i in self.issues if i.severity == "CRITICAL"]),
                "recommendation": self._get_recommendation(verdict)
            }
        }
        
        return report
    
    def _get_issue_description(self, issue_type: IssueType) -> str:
        """Get description for issue type."""
        descriptions = {
            IssueType.TRUNCATION: "Content removed or shortened without justification",
            IssueType.CENSORSHIP: "Content altered due to perceived sensitivity",
            IssueType.SUMMARIZATION: "Multiple sentences lazily combined into one",
            IssueType.OMISSION: "Entire paragraph or dialogue exchange missing",
            IssueType.ADDITION: "Content added not present in source"
        }
        return descriptions.get(issue_type, "Unknown issue type")
    
    def _get_issue_severity(self, issue_type: IssueType) -> str:
        """Get default severity for issue type."""
        severities = {
            IssueType.TRUNCATION: "HIGH",
            IssueType.CENSORSHIP: "CRITICAL",
            IssueType.SUMMARIZATION: "MEDIUM",
            IssueType.OMISSION: "CRITICAL",
            IssueType.ADDITION: "MEDIUM"
        }
        return severities.get(issue_type, "MEDIUM")
    
    def _verdict_to_grade(self, verdict: str) -> str:
        """Convert verdict to letter grade."""
        grades = {
            "PASS": "A",
            "REVIEW": "B",
            "FAIL": "D",
            "CRITICAL_FAIL": "F"
        }
        return grades.get(verdict, "F")
    
    def _get_recommendation(self, verdict: str) -> str:
        """Get recommendation based on verdict."""
        recommendations = {
            "PASS": "Content fidelity verified. Proceed to integrity audit.",
            "REVIEW": "Minor fidelity issues detected. Manual review recommended before proceeding.",
            "FAIL": "Significant content deviation. Revision required before publication.",
            "CRITICAL_FAIL": "Critical content loss. BLOCKS PUBLICATION. Retranslation required."
        }
        return recommendations.get(verdict, "Unknown verdict")
    
    def save_report(self, output_path: Path) -> Path:
        """Run audit and save report to JSON file."""
        report = self.audit()
        
        output_file = output_path / "fidelity_audit_report.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Fidelity report saved to: {output_file}")
        return output_file


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python fidelity_auditor.py <work_dir> [output_dir]")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else work_dir / "audits"
    output_dir.mkdir(exist_ok=True)
    
    auditor = FidelityAuditor(work_dir)
    auditor.save_report(output_dir)
