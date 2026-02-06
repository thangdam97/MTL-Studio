"""
FINAL AUDITOR: Report Aggregator
==================================
Mission: Aggregate all 3 subagent reports into a final audit summary
with weighted scoring and actionable recommendations.

Input: 
  - fidelity_audit_report.json (Subagent 1)
  - integrity_audit_report.json (Subagent 2)
  - prose_audit_report.json (Subagent 3)

Output:
  - FINAL_AUDIT_REPORT.md (Human-readable)
  - audit_summary.json (Machine-readable)
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class SubagentReport:
    """Container for a subagent report."""
    name: str
    weight: float
    loaded: bool
    score: float
    verdict: str
    issue_count: int
    critical_issues: int
    key_findings: List[str]


class FinalAuditor:
    """
    Final Auditor - Report Aggregator
    
    Combines results from all 3 subagent auditors into a
    final weighted assessment with grade and recommendations.
    """
    
    # Scoring weights
    WEIGHTS = {
        "fidelity": 0.40,   # Most important - content preservation
        "integrity": 0.30,  # Names, terms, formatting
        "prose": 0.30       # English quality
    }
    
    # Grade thresholds
    GRADE_THRESHOLDS = {
        "A+": 95,
        "A": 90,
        "B+": 85,
        "B": 80,
        "C+": 75,
        "C": 70,
        "D": 60,
        "F": 0
    }
    
    def __init__(self, audit_dir: Path, work_dir: Optional[Path] = None):
        self.audit_dir = Path(audit_dir)
        self.work_dir = Path(work_dir) if work_dir else self.audit_dir.parent
        
        self.fidelity_report: Optional[Dict] = None
        self.integrity_report: Optional[Dict] = None
        self.prose_report: Optional[Dict] = None
        
        self.subagent_results: List[SubagentReport] = []
    
    def load_reports(self) -> Tuple[bool, List[str]]:
        """Load all subagent reports."""
        errors = []
        
        # Load Fidelity Report (Subagent 1)
        fidelity_path = self.audit_dir / "fidelity_audit_report.json"
        if fidelity_path.exists():
            try:
                with open(fidelity_path, 'r', encoding='utf-8') as f:
                    self.fidelity_report = json.load(f)
                print(f"✅ Loaded: {fidelity_path.name}")
            except Exception as e:
                errors.append(f"Failed to load fidelity report: {e}")
        else:
            errors.append(f"Missing: {fidelity_path}")
        
        # Load Integrity Report (Subagent 2)
        integrity_path = self.audit_dir / "integrity_audit_report.json"
        if integrity_path.exists():
            try:
                with open(integrity_path, 'r', encoding='utf-8') as f:
                    self.integrity_report = json.load(f)
                print(f"✅ Loaded: {integrity_path.name}")
            except Exception as e:
                errors.append(f"Failed to load integrity report: {e}")
        else:
            errors.append(f"Missing: {integrity_path}")
        
        # Load Prose Report (Subagent 3)
        prose_path = self.audit_dir / "prose_audit_report.json"
        if prose_path.exists():
            try:
                with open(prose_path, 'r', encoding='utf-8') as f:
                    self.prose_report = json.load(f)
                print(f"✅ Loaded: {prose_path.name}")
            except Exception as e:
                errors.append(f"Failed to load prose report: {e}")
        else:
            errors.append(f"Missing: {prose_path}")
        
        success = len(errors) == 0
        return success, errors
    
    def aggregate(self) -> Dict:
        """Aggregate all reports into final assessment."""
        
        print("=" * 60)
        print("FINAL AUDITOR: REPORT AGGREGATION")
        print("=" * 60)
        
        # Load reports
        success, errors = self.load_reports()
        
        if not success:
            print("\n⚠️ Missing reports:")
            for error in errors:
                print(f"  - {error}")
        
        # Extract scores from each report
        fidelity_score = self._extract_fidelity_score()
        integrity_score = self._extract_integrity_score()
        prose_score = self._extract_prose_score()
        
        # Build subagent results
        self._build_subagent_results(fidelity_score, integrity_score, prose_score)
        
        # Calculate weighted final score
        final_score = self._calculate_final_score(fidelity_score, integrity_score, prose_score)
        final_grade = self._score_to_grade(final_score)
        
        # Determine blocking issues
        blocking_issues = self._get_blocking_issues()
        
        # Determine overall verdict
        verdict = self._determine_verdict(final_score, blocking_issues)
        
        # Get volume info
        volume_id = self._get_volume_id()
        
        # Compile summary
        summary = {
            "audit_type": "final_aggregated",
            "volume_id": volume_id,
            "timestamp": datetime.now().isoformat(),
            "auditor_version": "2.0",
            
            "reports_loaded": {
                "fidelity": self.fidelity_report is not None,
                "integrity": self.integrity_report is not None,
                "prose": self.prose_report is not None
            },
            
            "scores": {
                "fidelity": {
                    "raw_score": round(fidelity_score, 1),
                    "weight": self.WEIGHTS["fidelity"],
                    "weighted_score": round(fidelity_score * self.WEIGHTS["fidelity"], 1)
                },
                "integrity": {
                    "raw_score": round(integrity_score, 1),
                    "weight": self.WEIGHTS["integrity"],
                    "weighted_score": round(integrity_score * self.WEIGHTS["integrity"], 1)
                },
                "prose": {
                    "raw_score": round(prose_score, 1),
                    "weight": self.WEIGHTS["prose"],
                    "weighted_score": round(prose_score * self.WEIGHTS["prose"], 1)
                },
                "final": round(final_score, 1)
            },
            
            "grade": final_grade,
            "verdict": verdict,
            
            "subagent_summaries": [asdict(r) for r in self.subagent_results],
            
            "blocking_issues": blocking_issues,
            
            "issue_counts": {
                "fidelity_issues": self._get_issue_count(self.fidelity_report),
                "integrity_issues": self._get_issue_count(self.integrity_report),
                "prose_issues": self._get_issue_count(self.prose_report),
                "total": (self._get_issue_count(self.fidelity_report) +
                          self._get_issue_count(self.integrity_report) +
                          self._get_issue_count(self.prose_report))
            },
            
            "recommendations": self._generate_recommendations(
                fidelity_score, integrity_score, prose_score, blocking_issues
            ),
            
            "action_items": self._generate_action_items(blocking_issues),
            
            "certification": {
                "status": "CERTIFIED" if verdict == "PASS" else "NOT_CERTIFIED",
                "certified_by": "MTL Studio Audit System v2.0",
                "timestamp": datetime.now().isoformat()
            }
        }
        
        print(f"\n{'=' * 60}")
        print(f"FINAL SCORE: {final_score:.1f}/100")
        print(f"GRADE: {final_grade}")
        print(f"VERDICT: {verdict}")
        print(f"{'=' * 60}")
        
        return summary
    
    def _extract_fidelity_score(self) -> float:
        """Extract score from fidelity report."""
        if not self.fidelity_report:
            return 0.0
        
        # Get from summary
        summary = self.fidelity_report.get("summary", {})
        
        # Check validation checks
        validation = self.fidelity_report.get("validation_checks", {})
        
        # Calculate score based on pass rate
        checks = [
            validation.get("truncation_check", {}).get("status") == "PASS",
            validation.get("censorship_check", {}).get("status") == "PASS",
            validation.get("summarization_check", {}).get("status") == "PASS",
        ]
        
        pass_count = sum(checks)
        base_score = (pass_count / len(checks)) * 100
        
        # Deduct for issues
        issues = summary.get("total_issues", 0)
        critical = summary.get("critical_issues", 0)
        
        penalty = min(30, critical * 15 + issues * 2)
        
        return max(0, base_score - penalty)
    
    def _extract_integrity_score(self) -> float:
        """Extract score from integrity report."""
        if not self.integrity_report:
            return 0.0
        
        summary = self.integrity_report.get("summary", {})
        
        # Use pass rate if available
        pass_rate = summary.get("pass_rate", 0)
        
        if pass_rate:
            return pass_rate
        
        # Calculate from issue counts
        issues = summary.get("total_issues", 0)
        critical = len([i for i in self.integrity_report.get("all_issues", []) 
                        if i.get("severity") == "HIGH"])
        
        base_score = 100
        penalty = min(50, critical * 10 + issues * 2)
        
        return max(0, base_score - penalty)
    
    def _extract_prose_score(self) -> float:
        """Extract score from prose report."""
        if not self.prose_report:
            return 0.0
        
        summary = self.prose_report.get("summary", {})
        
        # Direct prose score if available
        return summary.get("prose_score", 0)
    
    def _build_subagent_results(self, fidelity_score: float, integrity_score: float,
                                 prose_score: float):
        """Build subagent result summaries."""
        self.subagent_results = []
        
        # Fidelity
        if self.fidelity_report:
            summary = self.fidelity_report.get("summary", {})
            self.subagent_results.append(SubagentReport(
                name="Content Fidelity (Subagent 1)",
                weight=self.WEIGHTS["fidelity"],
                loaded=True,
                score=fidelity_score,
                verdict=summary.get("verdict", "UNKNOWN"),
                issue_count=summary.get("total_issues", 0),
                critical_issues=summary.get("critical_issues", 0),
                key_findings=self._get_fidelity_findings()
            ))
        else:
            self.subagent_results.append(SubagentReport(
                name="Content Fidelity (Subagent 1)",
                weight=self.WEIGHTS["fidelity"],
                loaded=False,
                score=0,
                verdict="NOT_LOADED",
                issue_count=0,
                critical_issues=0,
                key_findings=["Report not available"]
            ))
        
        # Integrity
        if self.integrity_report:
            summary = self.integrity_report.get("summary", {})
            self.subagent_results.append(SubagentReport(
                name="Content Integrity (Subagent 2)",
                weight=self.WEIGHTS["integrity"],
                loaded=True,
                score=integrity_score,
                verdict=summary.get("verdict", "UNKNOWN"),
                issue_count=summary.get("total_issues", 0),
                critical_issues=0,  # Integrity usually doesn't have critical
                key_findings=self._get_integrity_findings()
            ))
        else:
            self.subagent_results.append(SubagentReport(
                name="Content Integrity (Subagent 2)",
                weight=self.WEIGHTS["integrity"],
                loaded=False,
                score=0,
                verdict="NOT_LOADED",
                issue_count=0,
                critical_issues=0,
                key_findings=["Report not available"]
            ))
        
        # Prose
        if self.prose_report:
            summary = self.prose_report.get("summary", {})
            self.subagent_results.append(SubagentReport(
                name="Prose Quality (Subagent 3)",
                weight=self.WEIGHTS["prose"],
                loaded=True,
                score=prose_score,
                verdict=summary.get("verdict", "UNKNOWN"),
                issue_count=summary.get("ai_ism_count", 0),
                critical_issues=0,
                key_findings=self._get_prose_findings()
            ))
        else:
            self.subagent_results.append(SubagentReport(
                name="Prose Quality (Subagent 3)",
                weight=self.WEIGHTS["prose"],
                loaded=False,
                score=0,
                verdict="NOT_LOADED",
                issue_count=0,
                critical_issues=0,
                key_findings=["Report not available"]
            ))
    
    def _get_fidelity_findings(self) -> List[str]:
        """Get key findings from fidelity report."""
        if not self.fidelity_report:
            return []
        
        findings = []
        
        validation = self.fidelity_report.get("validation_checks", {})
        
        truncation = validation.get("truncation_check", {})
        if truncation.get("status") != "PASS":
            findings.append(f"Truncation detected: {truncation.get('deviation', 0):.1f}% deviation")
        
        censorship = validation.get("censorship_check", {})
        if censorship.get("status") != "PASS":
            findings.append(f"Censorship detected: {censorship.get('issue_count', 0)} issues")
        
        if not findings:
            findings.append("All fidelity checks passed")
        
        return findings
    
    def _get_integrity_findings(self) -> List[str]:
        """Get key findings from integrity report."""
        if not self.integrity_report:
            return []
        
        findings = []
        summary = self.integrity_report.get("summary", {})
        
        if summary.get("name_typos", 0) > 0:
            findings.append(f"Name typos: {summary.get('name_typos', 0)}")
        
        if summary.get("format_issues", 0) > 0:
            findings.append(f"Formatting issues: {summary.get('format_issues', 0)}")
        
        if summary.get("auto_fixable", 0) > 0:
            findings.append(f"Auto-fixable issues: {summary.get('auto_fixable', 0)}")
        
        if not findings:
            findings.append("All integrity checks passed")
        
        return findings
    
    def _get_prose_findings(self) -> List[str]:
        """Get key findings from prose report."""
        if not self.prose_report:
            return []
        
        findings = []
        summary = self.prose_report.get("summary", {})
        
        ai_ism_count = summary.get("ai_ism_count", 0)
        if ai_ism_count > 0:
            findings.append(f"AI-isms: {ai_ism_count} ({summary.get('ai_ism_density', 0):.2f}/1k words)")
        
        contraction_rate = summary.get("contraction_rate", 100)
        if contraction_rate < 90:
            findings.append(f"Contraction rate: {contraction_rate:.1f}%")
        
        if summary.get("missed_transcreations", 0) > 0:
            findings.append(f"Missed transcreations: {summary.get('missed_transcreations', 0)}")
        
        if not findings:
            findings.append("Excellent prose quality")
        
        return findings
    
    def _calculate_final_score(self, fidelity: float, integrity: float, prose: float) -> float:
        """Calculate weighted final score."""
        return (fidelity * self.WEIGHTS["fidelity"] +
                integrity * self.WEIGHTS["integrity"] +
                prose * self.WEIGHTS["prose"])
    
    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"
    
    def _get_blocking_issues(self) -> List[Dict]:
        """Get all blocking issues from reports."""
        blocking = []
        
        # Fidelity blockers (truncation, censorship)
        if self.fidelity_report:
            for issue in self.fidelity_report.get("critical_issues", []):
                blocking.append({
                    "source": "fidelity",
                    "type": issue.get("issue_type", "UNKNOWN"),
                    "description": issue.get("description", ""),
                    "chapter": issue.get("chapter", "")
                })
        
        # Integrity blockers (severe name errors)
        if self.integrity_report:
            for issue in self.integrity_report.get("all_issues", []):
                if issue.get("severity") == "HIGH":
                    blocking.append({
                        "source": "integrity",
                        "type": issue.get("issue_type", "UNKNOWN"),
                        "description": issue.get("description", ""),
                        "chapter": issue.get("chapter", "")
                    })
        
        return blocking
    
    def _get_issue_count(self, report: Optional[Dict]) -> int:
        """Get total issue count from a report."""
        if not report:
            return 0
        
        summary = report.get("summary", {})
        
        # Try different keys
        return (summary.get("total_issues", 0) or
                summary.get("ai_ism_count", 0) or
                len(report.get("all_issues", [])))
    
    def _determine_verdict(self, score: float, blocking_issues: List[Dict]) -> str:
        """Determine final verdict."""
        if blocking_issues:
            return "BLOCKED"
        
        if score >= 90:
            return "PASS"
        elif score >= 80:
            return "PASS_WITH_NOTES"
        elif score >= 70:
            return "NEEDS_IMPROVEMENT"
        else:
            return "FAIL"
    
    def _generate_recommendations(self, fidelity: float, integrity: float,
                                   prose: float, blocking: List[Dict]) -> List[str]:
        """Generate recommendations based on scores."""
        recs = []
        
        if blocking:
            recs.append(f"🚨 {len(blocking)} blocking issues must be resolved before publication")
        
        if fidelity < 90:
            recs.append("📖 Review fidelity issues - content may be truncated or censored")
        
        if integrity < 90:
            recs.append("✍️ Fix integrity issues - check name spellings and formatting")
        
        if prose < 90:
            recs.append("💬 Improve prose quality - address AI-isms and contraction usage")
        
        if not recs:
            recs.append("✅ All checks passed - ready for final review")
        
        return recs
    
    def _generate_action_items(self, blocking: List[Dict]) -> List[Dict]:
        """Generate action items from blocking issues."""
        actions = []
        
        for issue in blocking[:10]:  # Limit to top 10
            actions.append({
                "priority": "HIGH",
                "source": issue.get("source", "unknown").upper(),
                "action": f"Review and fix: {issue.get('type', '')}",
                "details": issue.get("description", ""),
                "chapter": issue.get("chapter", "all")
            })
        
        return actions
    
    def _get_volume_id(self) -> str:
        """Get volume ID from reports."""
        for report in [self.fidelity_report, self.integrity_report, self.prose_report]:
            if report and report.get("volume_id"):
                return report.get("volume_id")
        
        return self.work_dir.name.split('_')[-1][:4] if '_' in self.work_dir.name else "unknown"
    
    def generate_markdown_report(self, summary: Dict) -> str:
        """Generate human-readable markdown report."""
        md = []
        
        # Header
        md.append("# FINAL AUDIT REPORT")
        md.append("")
        md.append(f"**Volume:** {summary.get('volume_id', 'Unknown')}")
        md.append(f"**Generated:** {summary.get('timestamp', '')[:10]}")
        md.append(f"**Auditor Version:** {summary.get('auditor_version', '2.0')}")
        md.append("")
        
        # Grade Box
        grade = summary.get("grade", "?")
        score = summary.get("scores", {}).get("final", 0)
        verdict = summary.get("verdict", "UNKNOWN")
        
        md.append("## 📊 Final Assessment")
        md.append("")
        md.append("| Metric | Value |")
        md.append("|--------|-------|")
        md.append(f"| **Final Score** | {score:.1f}/100 |")
        md.append(f"| **Grade** | {grade} |")
        md.append(f"| **Verdict** | {verdict} |")
        md.append("")
        
        # Score Breakdown
        md.append("## 📈 Score Breakdown")
        md.append("")
        md.append("| Category | Weight | Raw Score | Weighted |")
        md.append("|----------|--------|-----------|----------|")
        
        scores = summary.get("scores", {})
        for cat in ["fidelity", "integrity", "prose"]:
            cat_data = scores.get(cat, {})
            md.append(f"| {cat.title()} | {cat_data.get('weight', 0)*100:.0f}% | "
                     f"{cat_data.get('raw_score', 0):.1f} | {cat_data.get('weighted_score', 0):.1f} |")
        
        md.append(f"| **TOTAL** | 100% | - | **{score:.1f}** |")
        md.append("")
        
        # Subagent Summaries
        md.append("## 🤖 Subagent Reports")
        md.append("")
        
        for sub in summary.get("subagent_summaries", []):
            status = "✅" if sub.get("loaded") else "❌"
            md.append(f"### {status} {sub.get('name', 'Unknown')}")
            md.append("")
            md.append(f"- **Score:** {sub.get('score', 0):.1f}")
            md.append(f"- **Verdict:** {sub.get('verdict', 'UNKNOWN')}")
            md.append(f"- **Issues:** {sub.get('issue_count', 0)}")
            md.append("")
            md.append("**Key Findings:**")
            for finding in sub.get("key_findings", []):
                md.append(f"- {finding}")
            md.append("")
        
        # Blocking Issues
        blocking = summary.get("blocking_issues", [])
        if blocking:
            md.append("## 🚨 Blocking Issues")
            md.append("")
            md.append("These issues must be resolved before publication:")
            md.append("")
            for issue in blocking[:10]:
                md.append(f"- **[{issue.get('source', '').upper()}]** "
                         f"{issue.get('type', '')}: {issue.get('description', '')}")
            md.append("")
        
        # Recommendations
        md.append("## 💡 Recommendations")
        md.append("")
        for rec in summary.get("recommendations", []):
            md.append(f"- {rec}")
        md.append("")
        
        # Action Items
        actions = summary.get("action_items", [])
        if actions:
            md.append("## ✅ Action Items")
            md.append("")
            for i, action in enumerate(actions, 1):
                md.append(f"{i}. **[{action.get('priority', '')}]** {action.get('action', '')}")
                if action.get("details"):
                    md.append(f"   - {action.get('details', '')}")
            md.append("")
        
        # Certification
        cert = summary.get("certification", {})
        md.append("## 🏆 Certification")
        md.append("")
        if cert.get("status") == "CERTIFIED":
            md.append(f"✅ **CERTIFIED** by {cert.get('certified_by', 'MTL Studio')}")
            md.append("")
            md.append("This volume meets quality standards and is approved for publication.")
        else:
            md.append(f"❌ **NOT CERTIFIED**")
            md.append("")
            md.append("This volume requires additional work before certification.")
        md.append("")
        
        md.append("---")
        md.append(f"*Report generated by MTL Studio Audit System v2.0*")
        
        return "\n".join(md)
    
    def save_reports(self, output_dir: Optional[Path] = None) -> Tuple[Path, Path]:
        """Run aggregation and save both JSON and Markdown reports."""
        
        if output_dir is None:
            output_dir = self.audit_dir
        
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Run aggregation
        summary = self.aggregate()
        
        # Save JSON
        json_path = output_dir / "audit_summary.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n✅ JSON summary saved to: {json_path}")
        
        # Save Markdown
        md_content = self.generate_markdown_report(summary)
        md_path = output_dir / "FINAL_AUDIT_REPORT.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"✅ Markdown report saved to: {md_path}")
        
        return json_path, md_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python final_auditor.py <audit_dir> [output_dir]")
        print("       audit_dir should contain the 3 subagent JSON reports")
        sys.exit(1)
    
    audit_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else audit_dir
    
    auditor = FinalAuditor(audit_dir)
    auditor.save_reports(output_dir)
