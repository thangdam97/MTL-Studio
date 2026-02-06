#!/usr/bin/env python3
"""
Gap Preservation Auditor - Phase 4 of MTL Studio Audit System V2.0
==================================================================

Mission: Validate semantic gaps preserved from JP to EN

Gap Types:
- Gap A: Emotion + Action (simultaneous emotion + physical action)
- Gap B: Ruby Text (furigana/wordplay preservation)
- Gap C: Subtext (hidden meanings, sarcasm, performative speech)

Target preservation rate: >85%
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class GapIssue:
    """A gap preservation issue found during audit."""
    issue_id: str
    issue_type: str  # GAP_A, GAP_B, GAP_C
    severity: str  # HIGH, MEDIUM, LOW
    chapter_id: str
    jp_line: int
    jp_content: str
    en_line: int
    en_content: str
    analysis: str
    recommendation: str


@dataclass
class ChapterGapAudit:
    """Gap preservation audit for a single chapter."""
    chapter_id: str
    jp_title: str
    en_title: str
    gap_a_detected: int = 0
    gap_a_preserved: int = 0
    gap_b_detected: int = 0
    gap_b_preserved: int = 0
    gap_c_detected: int = 0
    gap_c_preserved: int = 0
    issues: List[GapIssue] = field(default_factory=list)


class GapPreservationAuditor:
    """
    Phase 4: Gap Preservation Auditor
    Validates semantic gaps preserved from JP to EN.
    """
    
    # Gap A: Emotion + Action patterns (Japanese)
    GAP_A_PATTERNS = [
        r'(驚|慌|焦|困|恥|照|怒|悲|喜|嬉|楽|笑|泣|叫|怯|震|息|溜息|苦笑|微笑|頷|首を振|目を見開|目を瞑|目を逸|顔を赤|顔を背|額を押|頬を撫|手を握|肩を竦|腕を組)',
        r'(ドキッ|ビクッ|ハッ|ゾクッ|フワッ|キュン|ギュッ)',
        r'てから|つつ|ながら',  # Simultaneous action markers
    ]
    
    # Gap B: Ruby text patterns (furigana detection)
    GAP_B_PATTERNS = [
        r'{(.+?)}',  # {ruby} markers
        r'\[(.+?)\]',  # [ruby] markers
        r'《(.+?)》',  # 《ruby》 markers
        r'<ruby>(.+?)</ruby>',  # HTML ruby tags
    ]
    
    # Gap C: Subtext markers (sarcasm, tsundere, hidden meaning)
    GAP_C_PATTERNS = [
        r'(別に|べつに|ベツニ)',  # "It's not like..." (tsundere)
        r'(やっぱり|さすが)',  # Context-dependent phrases
        r'(まあ|さあ|ねえ)',  # Filler words with subtext
        r'～(だ|です)(よね|ね|わ)',  # Sentence-ending particles
        r'(はぁ|ふぅ|へぇ|ほぉ)',  # Sighs/reactions
    ]
    
    def __init__(self, work_dir: Path):
        """Initialize auditor with work directory."""
        self.work_dir = Path(work_dir)
        self.jp_dir = self.work_dir / "JP"
        self.en_dir = self.work_dir / "EN"
        self.metadata_path = self.work_dir / "metadata_en.json"
        
        # Load metadata
        self.metadata = self._load_metadata()
        
        # Initialize audit results
        self.chapters: List[ChapterGapAudit] = []
        self.summary: Dict[str, Any] = {}
        
        # Run audit
        self._run_audit()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata_en.json for context."""
        if self.metadata_path.exists():
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _run_audit(self):
        """Run gap preservation audit on all chapters."""
        # Get list of JP chapters
        jp_files = sorted(self.jp_dir.glob("CHAPTER_*.md"))
        
        print(f"Found {len(jp_files)} JP chapters to audit")
        
        for jp_file in jp_files:
            chapter_num = re.search(r'CHAPTER_(\d+)', jp_file.name)
            if not chapter_num:
                continue
            
            chapter_id = chapter_num.group(1)
            en_file = self.en_dir / f"CHAPTER_{chapter_id}_EN.md"
            
            if not en_file.exists():
                print(f"⚠️ Chapter {chapter_id}: EN file not found - skipping")
                continue
            
            print(f"\n🔍 Auditing Chapter {chapter_id} gap preservation...")
            
            # Audit this chapter
            chapter_audit = self._audit_chapter(chapter_id, jp_file, en_file)
            self.chapters.append(chapter_audit)
        
        # Generate summary
        self._generate_summary()
        
        # Print results
        self._print_results()
    
    def _audit_chapter(
        self,
        chapter_id: str,
        jp_file: Path,
        en_file: Path
    ) -> ChapterGapAudit:
        """Audit gap preservation for a single chapter."""
        # Read files
        jp_lines = jp_file.read_text(encoding='utf-8').split('\n')
        en_lines = en_file.read_text(encoding='utf-8').split('\n')
        
        # Get chapter titles from metadata
        jp_title = ""
        en_title = ""
        for ch in self.metadata.get("chapters", []):
            if ch.get("id") == f"chapter_{int(chapter_id):02d}":
                jp_title = ch.get("title_jp", "")
                en_title = ch.get("title_en", "")
                break
        
        audit = ChapterGapAudit(
            chapter_id=chapter_id,
            jp_title=jp_title,
            en_title=en_title
        )
        
        # Check Gap A: Emotion + Action
        self._check_gap_a(audit, jp_lines, en_lines)
        
        # Check Gap B: Ruby Text
        self._check_gap_b(audit, jp_lines, en_lines)
        
        # Check Gap C: Subtext
        self._check_gap_c(audit, jp_lines, en_lines)
        
        return audit
    
    def _check_gap_a(
        self,
        audit: ChapterGapAudit,
        jp_lines: List[str],
        en_lines: List[str]
    ):
        """Check Gap A: Emotion + Action preservation."""
        for i, jp_line in enumerate(jp_lines):
            # Check for emotion+action patterns
            emotion_action_found = False
            for pattern in self.GAP_A_PATTERNS:
                if re.search(pattern, jp_line):
                    emotion_action_found = True
                    break
            
            if emotion_action_found:
                audit.gap_a_detected += 1
                
                # Check if EN preserves the simultaneity
                # Look for corresponding EN line
                if i < len(en_lines):
                    en_line = en_lines[i]
                    
                    # Simple heuristic: check if EN has both emotion and action words
                    emotion_words = r'(blush|gasp|sigh|smile|frown|grimace|wince|shudder|tremble|laugh|cry|yell|scream)'
                    action_words = r'(while|as|turning|looking|walking|holding|gripping|clenching|opening|closing)'
                    
                    has_emotion = bool(re.search(emotion_words, en_line, re.IGNORECASE))
                    has_action = bool(re.search(action_words, en_line, re.IGNORECASE))
                    has_gerund = bool(re.search(r'\b\w+ing\b', en_line))
                    
                    if (has_emotion and has_action) or (has_emotion and has_gerund):
                        audit.gap_a_preserved += 1
                    else:
                        # Create issue
                        issue = GapIssue(
                            issue_id=f"GAP-A-{audit.chapter_id}-{len(audit.issues)+1:03d}",
                            issue_type="GAP_A",
                            severity="MEDIUM",
                            chapter_id=audit.chapter_id,
                            jp_line=i + 1,
                            jp_content=jp_line[:100],
                            en_line=i + 1,
                            en_content=en_line[:100],
                            analysis="Emotion+Action simultaneity may not be preserved",
                            recommendation="Consider restructuring to show simultaneous emotion and action"
                        )
                        audit.issues.append(issue)
    
    def _check_gap_b(
        self,
        audit: ChapterGapAudit,
        jp_lines: List[str],
        en_lines: List[str]
    ):
        """Check Gap B: Ruby text preservation."""
        for i, jp_line in enumerate(jp_lines):
            # Check for ruby text markers
            ruby_found = False
            for pattern in self.GAP_B_PATTERNS:
                matches = re.findall(pattern, jp_line)
                if matches:
                    ruby_found = True
                    audit.gap_b_detected += len(matches)
                    
                    # Check if EN has TL notes or preserved the wordplay
                    if i < len(en_lines):
                        en_line = en_lines[i]
                        
                        # Check for TL notes
                        has_tl_note = bool(re.search(r'\[TL Note|TN:|Note:|※', en_line))
                        
                        # Check for capitalization tricks (common ruby preservation)
                        has_caps_trick = bool(re.search(r'[A-Z]{2,}', en_line))
                        
                        # Check for parenthetical explanations
                        has_explanation = bool(re.search(r'\([^)]{5,}\)', en_line))
                        
                        if has_tl_note or has_caps_trick or has_explanation:
                            audit.gap_b_preserved += len(matches)
                        else:
                            # Create issue for each ruby instance
                            issue = GapIssue(
                                issue_id=f"GAP-B-{audit.chapter_id}-{len(audit.issues)+1:03d}",
                                issue_type="GAP_B",
                                severity="HIGH",
                                chapter_id=audit.chapter_id,
                                jp_line=i + 1,
                                jp_content=jp_line[:100],
                                en_line=i + 1,
                                en_content=en_line[:100],
                                analysis=f"Ruby text detected but preservation unclear: {matches}",
                                recommendation="Add TL note or find creative English equivalent"
                            )
                            audit.issues.append(issue)
    
    def _check_gap_c(
        self,
        audit: ChapterGapAudit,
        jp_lines: List[str],
        en_lines: List[str]
    ):
        """Check Gap C: Subtext preservation."""
        genre = self.metadata.get("analysis", {}).get("genre", "")
        is_tsundere = "tsundere" in genre.lower()
        
        for i, jp_line in enumerate(jp_lines):
            # Check for subtext markers
            subtext_found = False
            marker_type = ""
            
            for pattern in self.GAP_C_PATTERNS:
                if re.search(pattern, jp_line):
                    subtext_found = True
                    marker_type = pattern
                    break
            
            if subtext_found:
                audit.gap_c_detected += 1
                
                # Check if EN preserves the subtext
                if i < len(en_lines):
                    en_line = en_lines[i]
                    
                    # For tsundere works, check for defensive language
                    if is_tsundere and '別に' in jp_line:
                        # Should have "It's not like" or "not that" or defensive tone
                        has_defensive = bool(re.search(
                            r"(not like|not that|wasn't|didn't|don't)",
                            en_line,
                            re.IGNORECASE
                        ))
                        
                        if has_defensive:
                            audit.gap_c_preserved += 1
                        else:
                            issue = GapIssue(
                                issue_id=f"GAP-C-{audit.chapter_id}-{len(audit.issues)+1:03d}",
                                issue_type="GAP_C",
                                severity="HIGH",
                                chapter_id=audit.chapter_id,
                                jp_line=i + 1,
                                jp_content=jp_line[:100],
                                en_line=i + 1,
                                en_content=en_line[:100],
                                analysis="Tsundere defensive pattern not preserved",
                                recommendation="Add defensive phrasing like 'It's not like...'"
                            )
                            audit.issues.append(issue)
                    else:
                        # Generic subtext check - harder to validate
                        # Assume preserved if line exists and is similar length
                        if len(en_line) > len(jp_line) * 0.5:
                            audit.gap_c_preserved += 1
    
    def _generate_summary(self):
        """Generate summary statistics."""
        total_gap_a_detected = sum(ch.gap_a_detected for ch in self.chapters)
        total_gap_a_preserved = sum(ch.gap_a_preserved for ch in self.chapters)
        
        total_gap_b_detected = sum(ch.gap_b_detected for ch in self.chapters)
        total_gap_b_preserved = sum(ch.gap_b_preserved for ch in self.chapters)
        
        total_gap_c_detected = sum(ch.gap_c_detected for ch in self.chapters)
        total_gap_c_preserved = sum(ch.gap_c_preserved for ch in self.chapters)
        
        total_detected = total_gap_a_detected + total_gap_b_detected + total_gap_c_detected
        total_preserved = total_gap_a_preserved + total_gap_b_preserved + total_gap_c_preserved
        
        preservation_rate = (total_preserved / total_detected * 100) if total_detected > 0 else 0.0
        
        # Calculate score (0-100)
        score = min(100.0, preservation_rate)
        
        # Determine verdict
        if preservation_rate >= 85:
            verdict = "PASS"
        elif preservation_rate >= 70:
            verdict = "PASS_WITH_WARNINGS"
        else:
            verdict = "FAIL"
        
        self.summary = {
            "total_chapters": len(self.chapters),
            "total_gaps_detected": total_detected,
            "total_gaps_preserved": total_preserved,
            "preservation_rate": round(preservation_rate, 2),
            "gap_a": {
                "detected": total_gap_a_detected,
                "preserved": total_gap_a_preserved,
                "rate": round((total_gap_a_preserved / total_gap_a_detected * 100) if total_gap_a_detected > 0 else 0.0, 2)
            },
            "gap_b": {
                "detected": total_gap_b_detected,
                "preserved": total_gap_b_preserved,
                "rate": round((total_gap_b_preserved / total_gap_b_detected * 100) if total_gap_b_detected > 0 else 0.0, 2)
            },
            "gap_c": {
                "detected": total_gap_c_detected,
                "preserved": total_gap_c_preserved,
                "rate": round((total_gap_c_preserved / total_gap_c_detected * 100) if total_gap_c_detected > 0 else 0.0, 2)
            },
            "score": round(score, 1),
            "verdict": verdict,
            "total_issues": sum(len(ch.issues) for ch in self.chapters)
        }
    
    def _print_results(self):
        """Print audit results to console."""
        print("\n" + "=" * 60)
        print("GAP PRESERVATION AUDIT COMPLETE")
        print(f"Preservation Rate: {self.summary['preservation_rate']:.1f}%")
        print(f"Score: {self.summary['score']:.1f}/100")
        print(f"Verdict: {self.summary['verdict']}")
        print("=" * 60)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit to dictionary for JSON serialization."""
        return {
            "audit_type": "gap_preservation",
            "volume_id": self.work_dir.name.split('_')[-1] if '_' in self.work_dir.name else "unknown",
            "timestamp": datetime.now().isoformat(),
            "auditor_version": "2.0",
            "summary": self.summary,
            "chapters": [
                {
                    "chapter_id": ch.chapter_id,
                    "jp_title": ch.jp_title,
                    "en_title": ch.en_title,
                    "gap_a_detected": ch.gap_a_detected,
                    "gap_a_preserved": ch.gap_a_preserved,
                    "gap_b_detected": ch.gap_b_detected,
                    "gap_b_preserved": ch.gap_b_preserved,
                    "gap_c_detected": ch.gap_c_detected,
                    "gap_c_preserved": ch.gap_c_preserved,
                    "issues": [
                        {
                            "issue_id": issue.issue_id,
                            "issue_type": issue.issue_type,
                            "severity": issue.severity,
                            "chapter_id": issue.chapter_id,
                            "jp_line": issue.jp_line,
                            "jp_content": issue.jp_content,
                            "en_line": issue.en_line,
                            "en_content": issue.en_content,
                            "analysis": issue.analysis,
                            "recommendation": issue.recommendation
                        }
                        for issue in ch.issues
                    ]
                }
                for ch in self.chapters
            ]
        }
    
    def save_report(self, output_dir: Path) -> Path:
        """Save audit report to JSON file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
        
        report_path = output_dir / "gap_preservation_audit_report.json"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"✅ Gap preservation report saved to: {report_path}")
        
        return report_path


def main():
    """Test the auditor standalone."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python gap_preservation_auditor.py <work_dir>")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    auditor = GapPreservationAuditor(work_dir)
    
    output_dir = work_dir / "audits"
    auditor.save_report(output_dir)


if __name__ == "__main__":
    main()
