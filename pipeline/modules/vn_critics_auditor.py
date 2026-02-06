"""
VN Critics Auditor - Vietnamese Translation Quality Audit System
Based on AUDIT_AGENT.md architecture, adapted for Vietnamese JSON grammar rules

Subagents:
1. Content Fidelity - Line count variance, content completeness
2. Content Integrity - Character names, formatting, structure
3. Prose Quality - Vietnamese AI-ism detection, naturalness scoring

Author: MTL Studio
Version: 1.0
"""

import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field, asdict
from collections import Counter


@dataclass
class AuditIssue:
    """Single audit issue"""
    issue_id: str
    chapter: str
    line: int
    severity: str  # CRITICAL, MAJOR, MINOR
    category: str
    pattern: str
    context: str
    suggestion: str = ""


@dataclass 
class FidelityReport:
    """Subagent 1: Content Fidelity Report"""
    status: str = "NOT_RUN"
    jp_total_lines: int = 0
    vn_total_lines: int = 0
    line_variance_percent: float = 0.0
    chapters_analyzed: int = 0
    issues: List[AuditIssue] = field(default_factory=list)
    chapter_breakdown: Dict = field(default_factory=dict)


@dataclass
class IntegrityReport:
    """Subagent 2: Content Integrity Report"""
    status: str = "NOT_RUN"
    name_consistency: float = 100.0
    formatting_issues: int = 0
    illustration_markers_ok: bool = True
    scene_breaks_ok: bool = True
    issues: List[AuditIssue] = field(default_factory=list)
    character_names: Dict = field(default_factory=dict)


@dataclass
class ProseReport:
    """Subagent 3: Prose Quality Report (Vietnamese-specific)"""
    status: str = "NOT_RUN"
    total_words: int = 0
    ai_ism_count: int = 0
    ai_ism_density: float = 0.0
    issues: List[AuditIssue] = field(default_factory=list)
    categories: Dict[str, int] = field(default_factory=dict)
    prose_score: float = 0.0


class VNCriticsAuditor:
    """
    Main auditor class for Vietnamese translations
    Implements 3-subagent architecture from AUDIT_AGENT.md
    """
    
    def __init__(self, volume_path: str, reference_volume_path: Optional[str] = None):
        """
        Initialize auditor
        
        Args:
            volume_path: Path to the volume being audited (2218)
            reference_volume_path: Path to reference volume for comparison (094e)
        """
        self.volume_path = Path(volume_path)
        self.reference_path = Path(reference_volume_path) if reference_volume_path else None
        
        self.volume_id = self._extract_volume_id(volume_path)
        self.reference_id = self._extract_volume_id(reference_volume_path) if reference_volume_path else None
        
        # Load Vietnamese AI-ism patterns
        self.vn_ai_ism_patterns = self._load_vn_ai_ism_patterns()
        
        # Reports
        self.fidelity_report = FidelityReport()
        self.integrity_report = IntegrityReport()
        self.prose_report = ProseReport()
        
    def _extract_volume_id(self, path: str) -> str:
        """Extract volume ID from path"""
        if not path:
            return ""
        # Pattern: *_YYYYMMDD_XXXX where XXXX is the volume ID
        match = re.search(r'_(\d{8})_([a-f0-9]{4})/?$', str(path))
        if match:
            return match.group(2)
        return Path(path).name[-4:]
    
    def _load_vn_ai_ism_patterns(self) -> Dict:
        """Load Vietnamese AI-ism detection patterns"""
        patterns = {
            "critical": [],
            "major": [],
            "minor": []
        }
        
        # Critical Vietnamese AI-isms (from vietnamese_grammar_rag.json)
        patterns["critical"] = [
            # "một cảm giác" wrapper - most common AI-ism
            {
                "id": "mot-cam-giac",
                "regex": r"(?:một )?cảm giác (?:như |là |bất an|nhẹ nhõm|căng thẳng|hoài niệm|tội lỗi)",
                "display": "một cảm giác [emotion]",
                "fix": "Remove wrapper - show emotion directly"
            },
            # "một cách" adverbial wrapper
            {
                "id": "mot-cach",
                "regex": r"một cách [a-zA-ZÀ-ỹ]+",
                "display": "một cách [adj]",
                "fix": "Use direct adverb or vivid verb"
            },
            # "việc" as unnecessary subject
            {
                "id": "viec-subject",
                "regex": r"^Việc [a-zA-ZÀ-ỹ]+ (?:là|rất|khiến)",
                "display": "Việc [subject] là/rất/khiến",
                "fix": "Remove 'Việc' - use verb directly"
            },
            # Passive voice with bởi
            {
                "id": "passive-boi",
                "regex": r"(?:bị|được) [a-zA-ZÀ-ỹ]+ bởi",
                "display": "[bị/được] X bởi Y",
                "fix": "Convert to active voice"
            }
        ]
        
        # Major Vietnamese AI-isms
        patterns["major"] = [
            # "điều" overuse
            {
                "id": "dieu-overuse",
                "regex": r"Điều (?:quan trọng|duy nhất|đó) (?:là|mà)",
                "display": "Điều [adj] là",
                "fix": "Often unnecessary - simplify"
            },
            # "sự" nominalization overuse
            {
                "id": "su-nominalization",
                "regex": r"[Ss]ự (?:xuất hiện|ra đi|thay đổi|hiện diện|vắng mặt) của",
                "display": "sự [noun] của",
                "fix": "Use verb instead of nominalization"
            },
            # Literal Japanese calques
            {
                "id": "shikata-nai-literal",
                "regex": r"(?:không thể |chẳng thể )làm gì được",
                "display": "không thể làm gì được",
                "fix": "Use: 'Thôi vậy' / 'Biết làm sao'"
            },
            # Formal register in casual dialogue
            {
                "id": "formal-in-casual",
                "regex": r"Tôi cảm thấy (?:rất |vô cùng )",
                "display": "Tôi cảm thấy rất/vô cùng",
                "fix": "Too formal for casual dialogue"
            },
            # Missing sentence-final particles
            {
                "id": "missing-particles",
                "regex": r"(?:Tôi hiểu|Cảm ơn|Được rồi)\.$",
                "display": "Sentence without particle",
                "fix": "Add particles: nha/nè/đi/mà/à/nhé"
            }
        ]
        
        # Minor Vietnamese AI-isms
        patterns["minor"] = [
            # Repetitive "rằng"
            {
                "id": "rang-overuse",
                "regex": r"rằng .+ rằng",
                "display": "rằng ... rằng",
                "fix": "Rephrase to avoid double 'rằng'"
            },
            # "đã" in context where tense is clear
            {
                "id": "da-redundant",
                "regex": r"(?:hôm qua|tuần trước|năm ngoái) .* đã",
                "display": "[past time] + đã",
                "fix": "'đã' often redundant with time markers"
            },
            # Long noun chains
            {
                "id": "noun-chain",
                "regex": r"của [a-zA-ZÀ-ỹ]+ của [a-zA-ZÀ-ỹ]+",
                "display": "của X của Y",
                "fix": "Break up noun chains"
            }
        ]
        
        return patterns
    
    # ========== SUBAGENT 1: CONTENT FIDELITY ==========
    
    def run_fidelity_audit(self) -> FidelityReport:
        """
        Subagent 1: Content Fidelity
        Compares JP source with VN output for completeness
        """
        jp_dir = self.volume_path / "JP"
        vn_dir = self.volume_path / "VN"
        
        if not jp_dir.exists() or not vn_dir.exists():
            self.fidelity_report.status = "ERROR_MISSING_DIR"
            return self.fidelity_report
        
        jp_chapters = sorted(jp_dir.glob("CHAPTER_*_JP.md"))
        vn_chapters = sorted(vn_dir.glob("CHAPTER_*_VN.md"))
        
        total_jp_lines = 0
        total_vn_lines = 0
        chapter_breakdown = {}
        issues = []
        
        for jp_file in jp_chapters:
            chapter_num = re.search(r'CHAPTER_(\d+)', jp_file.name)
            if not chapter_num:
                continue
            chapter_id = chapter_num.group(1)
            
            vn_file = vn_dir / f"CHAPTER_{chapter_id}_VN.md"
            if not vn_file.exists():
                issues.append(AuditIssue(
                    issue_id=f"FID-MISS-{chapter_id}",
                    chapter=chapter_id,
                    line=0,
                    severity="CRITICAL",
                    category="MISSING_CHAPTER",
                    pattern="Missing VN chapter",
                    context=f"Chapter {chapter_id} exists in JP but not in VN"
                ))
                continue
            
            # Count meaningful lines (non-empty, non-whitespace)
            jp_content = jp_file.read_text(encoding='utf-8')
            vn_content = vn_file.read_text(encoding='utf-8')
            
            jp_lines = [l for l in jp_content.split('\n') if l.strip()]
            vn_lines = [l for l in vn_content.split('\n') if l.strip()]
            
            total_jp_lines += len(jp_lines)
            total_vn_lines += len(vn_lines)
            
            variance = abs(len(jp_lines) - len(vn_lines)) / max(len(jp_lines), 1) * 100
            
            chapter_breakdown[chapter_id] = {
                "jp_lines": len(jp_lines),
                "vn_lines": len(vn_lines),
                "variance_percent": round(variance, 2)
            }
            
            # Flag high variance chapters
            if variance > 10:
                issues.append(AuditIssue(
                    issue_id=f"FID-VAR-{chapter_id}",
                    chapter=chapter_id,
                    line=0,
                    severity="MAJOR" if variance <= 20 else "CRITICAL",
                    category="HIGH_VARIANCE",
                    pattern=f"{variance:.1f}% line variance",
                    context=f"JP: {len(jp_lines)} lines, VN: {len(vn_lines)} lines"
                ))
        
        # Calculate overall variance
        overall_variance = abs(total_jp_lines - total_vn_lines) / max(total_jp_lines, 1) * 100
        
        self.fidelity_report.jp_total_lines = total_jp_lines
        self.fidelity_report.vn_total_lines = total_vn_lines
        self.fidelity_report.line_variance_percent = round(overall_variance, 2)
        self.fidelity_report.chapters_analyzed = len(jp_chapters)
        self.fidelity_report.chapter_breakdown = chapter_breakdown
        self.fidelity_report.issues = issues
        
        # Determine status
        if len([i for i in issues if i.severity == "CRITICAL"]) > 0:
            self.fidelity_report.status = "FAIL"
        elif len(issues) > 0:
            self.fidelity_report.status = "PASS_WITH_WARNINGS"
        else:
            self.fidelity_report.status = "PASS"
        
        return self.fidelity_report
    
    # ========== SUBAGENT 2: CONTENT INTEGRITY ==========
    
    def run_integrity_audit(self) -> IntegrityReport:
        """
        Subagent 2: Content Integrity
        Checks names, formatting, structure
        """
        vn_dir = self.volume_path / "VN"
        context_dir = self.volume_path / ".context"
        
        issues = []
        character_names = {}
        
        # Load name registry if available
        name_registry_path = context_dir / "name_registry.json"
        if name_registry_path.exists():
            name_registry = json.loads(name_registry_path.read_text(encoding='utf-8'))
            character_names = name_registry.get("characters", {})
        
        # Check formatting in each chapter
        vn_chapters = sorted(vn_dir.glob("CHAPTER_*_VN.md"))
        
        formatting_issues = 0
        illustration_count = 0
        scene_break_count = 0
        
        for vn_file in vn_chapters:
            chapter_id = re.search(r'CHAPTER_(\d+)', vn_file.name).group(1)
            content = vn_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                # Check for straight quotes (should be curly)
                if '"' in line and ('"' not in line and '"' not in line):
                    issues.append(AuditIssue(
                        issue_id=f"INT-FMT-{chapter_id}-{line_num}",
                        chapter=chapter_id,
                        line=line_num,
                        severity="MINOR",
                        category="STRAIGHT_QUOTES",
                        pattern='"',
                        context=line[:80],
                        suggestion="Use curly quotes: " ""
                    ))
                    formatting_issues += 1
                
                # Check for double hyphens (should be em dash)
                if '--' in line and '—' not in line:
                    issues.append(AuditIssue(
                        issue_id=f"INT-DASH-{chapter_id}-{line_num}",
                        chapter=chapter_id,
                        line=line_num,
                        severity="MINOR",
                        category="DOUBLE_HYPHEN",
                        pattern='--',
                        context=line[:80],
                        suggestion="Use em dash: —"
                    ))
                    formatting_issues += 1
                
                # Count illustration markers
                if '<img' in line:
                    illustration_count += 1
                
                # Count scene breaks
                if line.strip() == '* * *' or line.strip() == '***':
                    scene_break_count += 1
        
        self.integrity_report.formatting_issues = formatting_issues
        self.integrity_report.issues = issues
        self.integrity_report.character_names = character_names
        
        # Determine status
        critical_count = len([i for i in issues if i.severity == "CRITICAL"])
        if critical_count > 0:
            self.integrity_report.status = "FAIL"
        elif len(issues) > 0:
            self.integrity_report.status = "PASS_WITH_WARNINGS"
        else:
            self.integrity_report.status = "PASS"
        
        return self.integrity_report
    
    # ========== SUBAGENT 3: PROSE QUALITY (VIETNAMESE) ==========
    
    def run_prose_audit(self) -> ProseReport:
        """
        Subagent 3: Prose Quality for Vietnamese
        Detects AI-isms using Vietnamese-specific patterns
        """
        vn_dir = self.volume_path / "VN"
        
        total_words = 0
        all_issues = []
        category_counts = Counter()
        
        vn_chapters = sorted(vn_dir.glob("CHAPTER_*_VN.md"))
        
        for vn_file in vn_chapters:
            chapter_id = re.search(r'CHAPTER_(\d+)', vn_file.name).group(1)
            content = vn_file.read_text(encoding='utf-8')
            
            # Count words (Vietnamese words are space-separated)
            words = len(content.split())
            total_words += words
            
            # Run pattern detection
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                # Check critical patterns
                for pattern in self.vn_ai_ism_patterns["critical"]:
                    matches = re.findall(pattern["regex"], line, re.IGNORECASE)
                    for match in matches:
                        all_issues.append(AuditIssue(
                            issue_id=f"PRO-CRI-{chapter_id}-{line_num}",
                            chapter=chapter_id,
                            line=line_num,
                            severity="CRITICAL",
                            category=pattern["id"],
                            pattern=pattern["display"],
                            context=line[:100],
                            suggestion=pattern["fix"]
                        ))
                        category_counts[pattern["id"]] += 1
                
                # Check major patterns
                for pattern in self.vn_ai_ism_patterns["major"]:
                    matches = re.findall(pattern["regex"], line, re.IGNORECASE)
                    for match in matches:
                        all_issues.append(AuditIssue(
                            issue_id=f"PRO-MAJ-{chapter_id}-{line_num}",
                            chapter=chapter_id,
                            line=line_num,
                            severity="MAJOR",
                            category=pattern["id"],
                            pattern=pattern["display"],
                            context=line[:100],
                            suggestion=pattern["fix"]
                        ))
                        category_counts[pattern["id"]] += 1
                
                # Check minor patterns
                for pattern in self.vn_ai_ism_patterns["minor"]:
                    matches = re.findall(pattern["regex"], line, re.IGNORECASE)
                    for match in matches:
                        all_issues.append(AuditIssue(
                            issue_id=f"PRO-MIN-{chapter_id}-{line_num}",
                            chapter=chapter_id,
                            line=line_num,
                            severity="MINOR",
                            category=pattern["id"],
                            pattern=pattern["display"],
                            context=line[:100],
                            suggestion=pattern["fix"]
                        ))
                        category_counts[pattern["id"]] += 1
        
        # Calculate metrics
        ai_ism_count = len(all_issues)
        ai_ism_density = (ai_ism_count / max(total_words, 1)) * 1000  # per 1k words
        
        # Calculate prose score (density-based for long texts)
        # Base: 100, scale based on AI-ism density
        # Target density: <0.5/1k = 100, 0.5-1.0/1k = 85-95, 1.0-2.0/1k = 70-85, >2.0/1k = <70
        if ai_ism_density <= 0.2:
            prose_score = 100.0
        elif ai_ism_density <= 0.5:
            prose_score = 100.0 - ((ai_ism_density - 0.2) / 0.3) * 10  # 90-100
        elif ai_ism_density <= 1.0:
            prose_score = 90.0 - ((ai_ism_density - 0.5) / 0.5) * 15  # 75-90
        elif ai_ism_density <= 2.0:
            prose_score = 75.0 - ((ai_ism_density - 1.0) / 1.0) * 25  # 50-75
        else:
            prose_score = max(0, 50.0 - (ai_ism_density - 2.0) * 10)
        
        # Additional penalty for critical issues (max -10 points)
        critical_count = len([i for i in all_issues if i.severity == "CRITICAL"])
        critical_penalty = min(10, critical_count * 0.2)  # 0.2 per critical, max 10
        prose_score = max(0, prose_score - critical_penalty)
        
        self.prose_report.total_words = total_words
        self.prose_report.ai_ism_count = ai_ism_count
        self.prose_report.ai_ism_density = round(ai_ism_density, 2)
        self.prose_report.issues = all_issues
        self.prose_report.categories = dict(category_counts)
        self.prose_report.prose_score = round(prose_score, 1)
        
        # Determine status
        if ai_ism_density > 1.0 or prose_score < 70:
            self.prose_report.status = "FAIL"
        elif ai_ism_density > 0.5 or prose_score < 85:
            self.prose_report.status = "PASS_WITH_WARNINGS"
        else:
            self.prose_report.status = "PASS"
        
        return self.prose_report
    
    # ========== COMPARISON WITH REFERENCE ==========
    
    def compare_with_reference(self) -> Dict:
        """
        Compare current volume (2218) with reference volume (094e)
        Generates side-by-side quality comparison
        """
        if not self.reference_path:
            return {"error": "No reference volume specified"}
        
        # Create a reference auditor
        ref_auditor = VNCriticsAuditor(str(self.reference_path))
        
        # Run all audits on reference
        ref_auditor.run_fidelity_audit()
        ref_auditor.run_integrity_audit()
        ref_auditor.run_prose_audit()
        
        comparison = {
            "volumes": {
                "new": self.volume_id,
                "reference": self.reference_id
            },
            "fidelity": {
                "new": {
                    "status": self.fidelity_report.status,
                    "variance": self.fidelity_report.line_variance_percent,
                    "issues": len(self.fidelity_report.issues)
                },
                "reference": {
                    "status": ref_auditor.fidelity_report.status,
                    "variance": ref_auditor.fidelity_report.line_variance_percent,
                    "issues": len(ref_auditor.fidelity_report.issues)
                }
            },
            "integrity": {
                "new": {
                    "status": self.integrity_report.status,
                    "formatting_issues": self.integrity_report.formatting_issues,
                    "issues": len(self.integrity_report.issues)
                },
                "reference": {
                    "status": ref_auditor.integrity_report.status,
                    "formatting_issues": ref_auditor.integrity_report.formatting_issues,
                    "issues": len(ref_auditor.integrity_report.issues)
                }
            },
            "prose": {
                "new": {
                    "status": self.prose_report.status,
                    "ai_ism_count": self.prose_report.ai_ism_count,
                    "ai_ism_density": self.prose_report.ai_ism_density,
                    "prose_score": self.prose_report.prose_score,
                    "total_words": self.prose_report.total_words
                },
                "reference": {
                    "status": ref_auditor.prose_report.status,
                    "ai_ism_count": ref_auditor.prose_report.ai_ism_count,
                    "ai_ism_density": ref_auditor.prose_report.ai_ism_density,
                    "prose_score": ref_auditor.prose_report.prose_score,
                    "total_words": ref_auditor.prose_report.total_words
                }
            },
            "verdict": {
                "improvement": {},
                "regression": {}
            }
        }
        
        # Calculate improvements/regressions
        # Prose score
        prose_diff = self.prose_report.prose_score - ref_auditor.prose_report.prose_score
        if prose_diff > 0:
            comparison["verdict"]["improvement"]["prose_score"] = f"+{prose_diff:.1f}"
        elif prose_diff < 0:
            comparison["verdict"]["regression"]["prose_score"] = f"{prose_diff:.1f}"
        
        # AI-ism density
        density_diff = ref_auditor.prose_report.ai_ism_density - self.prose_report.ai_ism_density
        if density_diff > 0:
            comparison["verdict"]["improvement"]["ai_ism_density"] = f"-{density_diff:.2f}/1k (better)"
        elif density_diff < 0:
            comparison["verdict"]["regression"]["ai_ism_density"] = f"+{abs(density_diff):.2f}/1k (worse)"
        
        return comparison
    
    # ========== FINAL REPORT GENERATION ==========
    
    def generate_final_report(self) -> str:
        """Generate comprehensive markdown report"""
        
        # Calculate overall grade
        fidelity_score = 100 if self.fidelity_report.status == "PASS" else 85 if self.fidelity_report.status == "PASS_WITH_WARNINGS" else 60
        integrity_score = 100 if self.integrity_report.status == "PASS" else 85 if self.integrity_report.status == "PASS_WITH_WARNINGS" else 60
        prose_score = self.prose_report.prose_score
        
        # Weighted final score
        final_score = (fidelity_score * 0.4) + (integrity_score * 0.3) + (prose_score * 0.3)
        
        # Determine grade
        if final_score >= 95:
            grade = "A+"
        elif final_score >= 90:
            grade = "A"
        elif final_score >= 85:
            grade = "B"
        elif final_score >= 80:
            grade = "C"
        elif final_score >= 70:
            grade = "D"
        else:
            grade = "F"
        
        # Generate report
        report = f"""# VN CRITICS AUDIT REPORT

## Volume Information
- **Volume ID:** {self.volume_id}
- **Path:** {self.volume_path.name}
- **Audit Date:** {datetime.now().isoformat()}
- **Auditor:** VN Critics Auditor v1.0

---

## OVERALL VERDICT

### Grade: {grade}
### Final Score: {final_score:.1f}/100
### Status: {"PUBLISH_READY" if grade in ["A+", "A", "B"] else "NEEDS_REVISION" if grade in ["C", "D"] else "BLOCKED"}

---

## SUBAGENT RESULTS

### 1. Content Fidelity (Weight: 40%)
| Metric | Value | Status |
|--------|-------|--------|
| JP Lines | {self.fidelity_report.jp_total_lines} | - |
| VN Lines | {self.fidelity_report.vn_total_lines} | - |
| Variance | {self.fidelity_report.line_variance_percent}% | {"✅" if self.fidelity_report.line_variance_percent < 5 else "⚠️"} |
| Issues | {len(self.fidelity_report.issues)} | {"✅" if len(self.fidelity_report.issues) == 0 else "⚠️"} |

**Status:** {self.fidelity_report.status}

### 2. Content Integrity (Weight: 30%)
| Metric | Value | Status |
|--------|-------|--------|
| Formatting Issues | {self.integrity_report.formatting_issues} | {"✅" if self.integrity_report.formatting_issues == 0 else "⚠️"} |
| Total Issues | {len(self.integrity_report.issues)} | {"✅" if len(self.integrity_report.issues) == 0 else "⚠️"} |

**Status:** {self.integrity_report.status}

### 3. Prose Quality (Weight: 30%) - Vietnamese Specific
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Total Words | {self.prose_report.total_words} | - | - |
| AI-ism Count | {self.prose_report.ai_ism_count} | <50 | {"✅" if self.prose_report.ai_ism_count < 50 else "⚠️"} |
| AI-ism Density | {self.prose_report.ai_ism_density}/1k | <0.5/1k | {"✅" if self.prose_report.ai_ism_density < 0.5 else "⚠️"} |
| Prose Score | {self.prose_report.prose_score} | >85 | {"✅" if self.prose_report.prose_score > 85 else "⚠️"} |

**Status:** {self.prose_report.status}

---

## AI-ISM BREAKDOWN

"""
        # Add category breakdown
        if self.prose_report.categories:
            report += "| Category | Count |\n|----------|-------|\n"
            for cat, count in sorted(self.prose_report.categories.items(), key=lambda x: -x[1]):
                report += f"| {cat} | {count} |\n"
        else:
            report += "No AI-isms detected! 🎉\n"
        
        report += """
---

## DETAILED ISSUES

"""
        # Add critical issues
        critical_issues = [i for i in self.prose_report.issues if i.severity == "CRITICAL"]
        if critical_issues:
            report += "### Critical Issues\n"
            for issue in critical_issues[:10]:  # Limit to 10
                report += f"- **{issue.chapter}:{issue.line}** - `{issue.pattern}` - {issue.suggestion}\n"
                report += f"  - Context: _{issue.context[:60]}..._\n"
        
        # Add major issues
        major_issues = [i for i in self.prose_report.issues if i.severity == "MAJOR"]
        if major_issues:
            report += "\n### Major Issues\n"
            for issue in major_issues[:10]:  # Limit to 10
                report += f"- **{issue.chapter}:{issue.line}** - `{issue.pattern}` - {issue.suggestion}\n"
        
        report += """
---

## RECOMMENDATIONS

"""
        if grade in ["A+", "A"]:
            report += "✅ **READY FOR PUBLICATION** - High-quality Vietnamese prose detected.\n"
        elif grade in ["B", "C"]:
            report += "⚠️ **MINOR REVISIONS RECOMMENDED** - Address AI-isms before final publication.\n"
        else:
            report += "❌ **MAJOR REVISIONS REQUIRED** - Significant prose quality issues detected.\n"
        
        return report
    
    def run_full_audit(self) -> Dict:
        """Run all three subagent audits and return summary"""
        print(f"🔍 Running VN Critics Audit on volume {self.volume_id}...")
        
        print("  📊 Subagent 1: Content Fidelity...")
        self.run_fidelity_audit()
        
        print("  📋 Subagent 2: Content Integrity...")
        self.run_integrity_audit()
        
        print("  📝 Subagent 3: Prose Quality (Vietnamese)...")
        self.run_prose_audit()
        
        # Generate summary
        summary = {
            "volume_id": self.volume_id,
            "timestamp": datetime.now().isoformat(),
            "fidelity": {
                "status": self.fidelity_report.status,
                "variance": self.fidelity_report.line_variance_percent,
                "issues": len(self.fidelity_report.issues)
            },
            "integrity": {
                "status": self.integrity_report.status,
                "formatting_issues": self.integrity_report.formatting_issues,
                "issues": len(self.integrity_report.issues)
            },
            "prose": {
                "status": self.prose_report.status,
                "ai_ism_count": self.prose_report.ai_ism_count,
                "ai_ism_density": self.prose_report.ai_ism_density,
                "prose_score": self.prose_report.prose_score,
                "categories": self.prose_report.categories
            }
        }
        
        print(f"✅ Audit complete!")
        return summary


def run_vn_critics_audit(volume_id: str, reference_id: Optional[str] = None):
    """
    CLI entry point for VN Critics Audit
    
    Args:
        volume_id: Volume to audit (e.g., "2218")
        reference_id: Reference volume for comparison (e.g., "094e")
    """
    # Find volume path
    work_dir = Path(__file__).parent.parent / "WORK"
    
    volume_path = None
    reference_path = None
    
    for folder in work_dir.iterdir():
        if folder.is_dir():
            if volume_id in folder.name:
                volume_path = folder
            if reference_id and reference_id in folder.name:
                reference_path = folder
    
    if not volume_path:
        print(f"❌ Volume {volume_id} not found in WORK directory")
        return
    
    # Create auditor
    auditor = VNCriticsAuditor(str(volume_path), str(reference_path) if reference_path else None)
    
    # Run full audit
    summary = auditor.run_full_audit()
    
    # Print summary
    print("\n" + "="*60)
    print("AUDIT SUMMARY")
    print("="*60)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    # Generate comparison if reference available
    if reference_path:
        print("\n" + "="*60)
        print(f"COMPARISON: {volume_id} vs {reference_id}")
        print("="*60)
        comparison = auditor.compare_with_reference()
        print(json.dumps(comparison, indent=2, ensure_ascii=False))
    
    # Generate and save report
    report = auditor.generate_final_report()
    report_path = volume_path / "audits" / "VN_CRITICS_REPORT.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report, encoding='utf-8')
    print(f"\n📄 Report saved to: {report_path}")
    
    # Save JSON summary
    json_path = volume_path / "audits" / "vn_critics_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    
    return auditor


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vn_critics_auditor.py <volume_id> [reference_id]")
        print("Example: python vn_critics_auditor.py 2218 094e")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    reference_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    run_vn_critics_audit(volume_id, reference_id)
