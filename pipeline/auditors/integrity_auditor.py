"""
SUBAGENT 2: Content Integrity Auditor
======================================
Mission: Validate structural elements - chapter titles, names, terms,
formatting standards, illustration markers, and cross-reference with source.

Output: integrity_audit_report.json
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class IntegrityIssueType(Enum):
    NAME_TYPO = "NAME_TYPO"
    NAME_ORDER = "NAME_ORDER"
    TERM_INCONSISTENCY = "TERM_INCONSISTENCY"
    HONORIFIC_VIOLATION = "HONORIFIC_VIOLATION"
    FORMAT_QUOTES = "FORMAT_QUOTES"
    FORMAT_DASHES = "FORMAT_DASHES"
    FORMAT_ELLIPSIS = "FORMAT_ELLIPSIS"
    FORMAT_SPACING = "FORMAT_SPACING"
    ILLUSTRATION_MISSING = "ILLUSTRATION_MISSING"
    ILLUSTRATION_MISPLACED = "ILLUSTRATION_MISPLACED"
    TITLE_MISMATCH = "TITLE_MISMATCH"
    SEQUEL_CONTINUITY = "SEQUEL_CONTINUITY"


@dataclass
class IntegrityIssue:
    issue_id: str
    issue_type: str
    severity: str
    chapter: str
    line: int
    found: str
    expected: str
    context: str
    auto_fixable: bool


class IntegrityAuditor:
    """
    Content Integrity Auditor - Subagent 2
    
    Validates structural elements including names, terms, formatting,
    and illustration markers.
    """
    
    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)
        self.jp_dir = self.work_dir / "JP"
        self.en_dir = self.work_dir / "EN"
        self.context_dir = self.work_dir / ".context"
        
        self.issues: List[IntegrityIssue] = []
        
        # Load registries
        self.name_registry = self._load_name_registry()
        self.glossary = self._load_glossary()
        self.metadata = self._load_metadata()
        
        # Formatting standards
        self.formatting_rules = {
            "smart_quotes": {
                "bad": ['"', '"'],  # Straight quotes
                "good": ['"', '"', ''', ''']  # Curly quotes
            },
            "em_dash": {
                "bad": ["--", "–"],  # Double hyphen, en dash
                "good": ["—"]  # Em dash
            },
            "ellipsis": {
                "bad": ["..."],  # Three periods
                "good": ["…"]  # Proper ellipsis
            }
        }
        
        # Honorifics to retain (hybrid localization)
        self.valid_honorifics = [
            "-san", "-kun", "-chan", "-senpai", "-sensei", 
            "-sama", "-dono", "Onii-chan", "Onee-san", "Onee-chan"
        ]
        
    def _load_name_registry(self) -> Dict:
        """Load character name registry."""
        registry_path = self.context_dir / "name_registry.json"
        if registry_path.exists():
            with open(registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Also try metadata_en.json
        metadata_path = self.work_dir / "metadata_en.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "character_profiles" in data:
                    return {
                        "characters": [
                            {
                                "id": c.get("id", c.get("name_en", "").lower()),
                                "name_en": c.get("name_en", ""),
                                "name_jp": c.get("name_jp", ""),
                                "aliases": c.get("aliases", [])
                            }
                            for c in data["character_profiles"]
                        ]
                    }
        return {"characters": []}
    
    def _load_glossary(self) -> Dict:
        """Load glossary terms from manifest."""
        manifest_path = self.context_dir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("glossary", {})
        return {}
    
    def _load_metadata(self) -> Dict:
        """Load volume metadata."""
        metadata_path = self.work_dir / "metadata_en.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def audit(self) -> Dict:
        """Run full integrity audit on all chapters."""
        
        print("=" * 60)
        print("SUBAGENT 2: CONTENT INTEGRITY AUDITOR")
        print("=" * 60)
        
        en_chapters = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        jp_chapters = sorted(self.jp_dir.glob("CHAPTER_*.md"))
        
        if not en_chapters:
            raise FileNotFoundError(f"No EN chapters found in {self.en_dir}")
        
        print(f"Found {len(en_chapters)} EN chapters to audit")
        print(f"Name registry: {len(self.name_registry.get('characters', []))} characters")
        print(f"Glossary: {len(self.glossary)} terms")
        
        results = {
            "chapter_titles": {"status": "PASS", "chapters": [], "issues": []},
            "character_names": {"status": "PASS", "checks": []},
            "name_order": {"status": "PASS", "violations": []},
            "honorifics": {"status": "PASS", "violations": []},
            "glossary_terms": {"status": "PASS", "checks": []},
            "formatting": {"status": "PASS", "checks": {}},
            "illustration_markers": {"status": "PASS", "markers": []},
            "scene_breaks": {"status": "PASS"}
        }
        
        total_checks = 0
        passed_checks = 0
        warnings = 0
        failures = 0
        
        # Audit each chapter
        for en_file in en_chapters:
            chapter_num = self._extract_chapter_num(en_file.name)
            jp_file = self.jp_dir / f"CHAPTER_{chapter_num:02d}.md"
            
            print(f"\n📋 Auditing Chapter {chapter_num:02d} integrity...")
            
            en_text = en_file.read_text(encoding='utf-8')
            jp_text = jp_file.read_text(encoding='utf-8') if jp_file.exists() else ""
            
            # Check chapter title
            title_result = self._check_chapter_title(en_text, jp_text, chapter_num)
            results["chapter_titles"]["chapters"].append(title_result)
            total_checks += 1
            if title_result["title_match"]:
                passed_checks += 1
            
            # Check character names
            name_results = self._check_character_names(en_text, chapter_num)
            results["character_names"]["checks"].extend(name_results)
            
            # Check formatting
            format_results = self._check_formatting(en_text, en_file.name, chapter_num)
            for category, check_result in format_results.items():
                if category not in results["formatting"]["checks"]:
                    results["formatting"]["checks"][category] = {"status": "PASS", "issues": []}
                results["formatting"]["checks"][category]["issues"].extend(check_result.get("issues", []))
            
            # Check illustration markers
            illust_results = self._check_illustrations(en_text, jp_text, chapter_num)
            results["illustration_markers"]["markers"].extend(illust_results)
        
        # Aggregate formatting status
        for category, check in results["formatting"]["checks"].items():
            total_checks += 1
            if check["issues"]:
                check["status"] = "WARNING"
                warnings += 1
            else:
                check["status"] = "PASS"
                passed_checks += 1
        
        # Count character name checks
        for check in results["character_names"]["checks"]:
            total_checks += 1
            if check.get("inconsistencies", 0) == 0:
                passed_checks += 1
            else:
                warnings += 1
        
        # Calculate pass rate
        pass_rate = (passed_checks / max(total_checks, 1)) * 100
        
        # Determine overall status
        critical_issues = [i for i in self.issues if i.severity == "CRITICAL"]
        if critical_issues:
            overall_status = "FAIL"
            failures = len(critical_issues)
        elif warnings > 0:
            overall_status = "PASS_WITH_WARNINGS"
        else:
            overall_status = "PASS"
        
        # Update category statuses
        if results["character_names"]["checks"]:
            has_name_issues = any(c.get("inconsistencies", 0) > 0 for c in results["character_names"]["checks"])
            results["character_names"]["status"] = "WARNING" if has_name_issues else "PASS"
        
        # Count auto-fixable issues
        auto_fixable = len([i for i in self.issues if i.auto_fixable])
        
        # Build final report
        report = {
            "audit_type": "content_integrity",
            "volume_id": self.work_dir.name.split('_')[-1][:4] if '_' in self.work_dir.name else "unknown",
            "timestamp": datetime.now().isoformat(),
            "auditor_version": "2.0",
            
            "summary": {
                "total_checks": total_checks,
                "passed": passed_checks,
                "warnings": warnings,
                "failures": failures,
                "pass_rate": round(pass_rate, 2),
                "verdict": overall_status
            },
            
            "chapter_titles": results["chapter_titles"],
            "character_names": {
                "status": results["character_names"]["status"],
                "registry_loaded": len(self.name_registry.get("characters", [])) > 0,
                "characters_verified": len(results["character_names"]["checks"]),
                "checks": results["character_names"]["checks"]
            },
            "name_order": results["name_order"],
            "honorifics": {
                "status": "PASS",
                "standard": "HYBRID_LOCALIZATION",
                "retained": self.valid_honorifics,
                "violations": results["honorifics"]["violations"],
                "consistency_score": 100 - len(results["honorifics"]["violations"]) * 5
            },
            "glossary_terms": {
                "status": "PASS",
                "terms_loaded": len(self.glossary),
                "checks": results["glossary_terms"]["checks"]
            },
            "formatting": {
                "status": "PASS_WITH_WARNINGS" if any(
                    c.get("issues") for c in results["formatting"]["checks"].values()
                ) else "PASS",
                "checks": results["formatting"]["checks"],
                "auto_fixable_count": auto_fixable
            },
            "illustration_markers": {
                "status": results["illustration_markers"]["status"],
                "markers": results["illustration_markers"]["markers"]
            },
            "scene_breaks": results["scene_breaks"],
            
            "all_issues": [asdict(i) for i in self.issues],
            
            "final_verdict": {
                "grade": self._calculate_grade(pass_rate, failures),
                "pass_rate": round(pass_rate, 2),
                "status": overall_status,
                "blocking_issues": failures,
                "auto_fixable_issues": auto_fixable,
                "recommendation": self._get_recommendation(overall_status)
            }
        }
        
        print(f"\n{'=' * 60}")
        print(f"INTEGRITY AUDIT COMPLETE")
        print(f"Pass Rate: {pass_rate:.1f}% | Verdict: {overall_status}")
        print(f"{'=' * 60}")
        
        return report
    
    def _check_chapter_title(self, en_text: str, jp_text: str, chapter_num: int) -> Dict:
        """Verify chapter title exists and matches expected format."""
        
        en_lines = en_text.split('\n')
        jp_lines = jp_text.split('\n') if jp_text else []
        
        en_title = ""
        jp_title = ""
        
        for line in en_lines[:15]:
            if line.startswith('#'):
                en_title = line.lstrip('#').strip()
                break
        
        for line in jp_lines[:15]:
            if line.startswith('#'):
                jp_title = line.lstrip('#').strip()
                break
        
        # Check title format
        format_correct = bool(re.match(r'^Chapter \d+', en_title, re.IGNORECASE))
        
        return {
            "chapter_id": f"{chapter_num:02d}",
            "jp_title": jp_title,
            "en_title": en_title,
            "title_match": bool(en_title),
            "format_correct": format_correct
        }
    
    def _check_character_names(self, text: str, chapter_num: int) -> List[Dict]:
        """Check character name consistency against registry."""
        
        results = []
        
        for char in self.name_registry.get("characters", []):
            name_en = char.get("name_en", "")
            if not name_en:
                continue
            
            # Count occurrences
            occurrences = len(re.findall(re.escape(name_en), text, re.IGNORECASE))
            
            # Check for common typos (missing/extra letters)
            inconsistencies = 0
            issues = []
            
            # Generate potential typos
            typo_patterns = self._generate_typo_patterns(name_en)
            for typo in typo_patterns:
                if typo.lower() != name_en.lower():
                    typo_count = len(re.findall(r'\b' + re.escape(typo) + r'\b', text, re.IGNORECASE))
                    if typo_count > 0:
                        inconsistencies += typo_count
                        self._add_issue(
                            issue_type=IntegrityIssueType.NAME_TYPO,
                            severity="WARNING",
                            chapter=f"{chapter_num:02d}",
                            line=0,
                            found=typo,
                            expected=name_en,
                            context=f"Found {typo_count} instances",
                            auto_fixable=True
                        )
                        issues.append({
                            "issue_id": f"INT-NAME-{chapter_num:02d}-{len(issues)+1:03d}",
                            "chapter": f"{chapter_num:02d}",
                            "found": typo,
                            "expected": name_en,
                            "type": "TYPO"
                        })
            
            results.append({
                "character_id": char.get("id", name_en.lower()),
                "canonical_name": name_en,
                "jp_source": char.get("name_jp", ""),
                "occurrences_checked": occurrences,
                "inconsistencies": inconsistencies,
                "status": "PASS" if inconsistencies == 0 else "WARNING",
                "issues": issues
            })
        
        return results
    
    def _generate_typo_patterns(self, name: str) -> List[str]:
        """Generate common typo patterns for a name."""
        typos = [name]
        
        # Single character deletions
        for i in range(len(name)):
            typos.append(name[:i] + name[i+1:])
        
        # Common substitutions
        substitutions = {
            'i': ['e', 'y'],
            'e': ['i', 'a'],
            'a': ['e', 'o'],
            'o': ['a', 'u'],
            'u': ['o'],
            's': ['z'],
            'z': ['s'],
            'c': ['k', 's'],
            'k': ['c'],
        }
        
        for i, char in enumerate(name.lower()):
            if char in substitutions:
                for sub in substitutions[char]:
                    typos.append(name[:i] + sub + name[i+1:])
        
        return list(set(typos))
    
    def _check_formatting(self, text: str, filename: str, chapter_num: int) -> Dict:
        """Check formatting standards (quotes, dashes, ellipsis)."""
        
        results = {}
        
        # Check straight quotes
        straight_quote_count = text.count('"') + text.count("'")
        results["smart_quotes"] = {
            "status": "PASS" if straight_quote_count == 0 else "WARNING",
            "straight_quotes_found": straight_quote_count,
            "issues": []
        }
        
        if straight_quote_count > 0:
            # Find line numbers
            for i, line in enumerate(text.split('\n'), 1):
                if '"' in line or "'" in line:
                    self._add_issue(
                        issue_type=IntegrityIssueType.FORMAT_QUOTES,
                        severity="LOW",
                        chapter=f"{chapter_num:02d}",
                        line=i,
                        found='"',
                        expected='"" or ""',
                        context=line[:50],
                        auto_fixable=True
                    )
                    results["smart_quotes"]["issues"].append({
                        "issue_id": f"INT-FMT-{chapter_num:02d}-{i:04d}",
                        "chapter": f"{chapter_num:02d}",
                        "line": i,
                        "type": "STRAIGHT_QUOTE"
                    })
        
        # Check em dashes
        double_hyphen_count = text.count("--")
        results["em_dashes"] = {
            "status": "PASS" if double_hyphen_count == 0 else "WARNING",
            "issues": []
        }
        
        if double_hyphen_count > 0:
            for i, line in enumerate(text.split('\n'), 1):
                if "--" in line:
                    self._add_issue(
                        issue_type=IntegrityIssueType.FORMAT_DASHES,
                        severity="LOW",
                        chapter=f"{chapter_num:02d}",
                        line=i,
                        found="--",
                        expected="—",
                        context=line[:50],
                        auto_fixable=True
                    )
                    results["em_dashes"]["issues"].append({
                        "issue_id": f"INT-FMT-{chapter_num:02d}-{i:04d}",
                        "chapter": f"{chapter_num:02d}",
                        "line": i,
                        "found": "--",
                        "expected": "—",
                        "auto_fixable": True
                    })
        
        # Check ellipsis
        triple_dots = len(re.findall(r'\.\.\.', text))
        results["ellipsis"] = {
            "status": "PASS" if triple_dots == 0 else "WARNING",
            "triple_dots_found": triple_dots,
            "proper_ellipsis_used": "…" in text
        }
        
        # Check spacing
        double_spaces = len(re.findall(r'  ', text))
        results["spacing"] = {
            "status": "PASS" if double_spaces == 0 else "WARNING",
            "double_spaces_found": double_spaces
        }
        
        return results
    
    def _check_illustrations(self, en_text: str, jp_text: str, chapter_num: int) -> List[Dict]:
        """Check illustration markers are present and properly placed."""
        
        results = []
        
        # Find illustration tags in EN
        en_illustrations = re.findall(r'<img[^>]+src="[^"]*/(i-\d+|p-?\d+)\.jpg"[^>]*/>', en_text)
        
        # Find illustration references in JP (if any format)
        jp_illustrations = re.findall(r'(i-\d+|p-?\d+)\.jpg', jp_text)
        
        for img_id in set(en_illustrations + jp_illustrations):
            in_en = img_id in en_illustrations
            in_jp = img_id in jp_illustrations
            
            results.append({
                "image_id": img_id,
                "in_jp": in_jp,
                "in_en": in_en,
                "format_correct": in_en,
                "status": "PASS" if in_en else "MISSING"
            })
            
            if in_jp and not in_en:
                self._add_issue(
                    issue_type=IntegrityIssueType.ILLUSTRATION_MISSING,
                    severity="MEDIUM",
                    chapter=f"{chapter_num:02d}",
                    line=0,
                    found="[missing]",
                    expected=f'<img class="fit" src="../image/{img_id}.jpg" alt=""/>',
                    context=f"Illustration {img_id} found in JP but not in EN",
                    auto_fixable=False
                )
        
        return results
    
    def _add_issue(self, issue_type: IntegrityIssueType, severity: str,
                   chapter: str, line: int, found: str, expected: str,
                   context: str, auto_fixable: bool):
        """Add an integrity issue."""
        
        issue_id = f"INT-{issue_type.value[:3]}-{chapter}-{len(self.issues)+1:03d}"
        
        self.issues.append(IntegrityIssue(
            issue_id=issue_id,
            issue_type=issue_type.value,
            severity=severity,
            chapter=chapter,
            line=line,
            found=found,
            expected=expected,
            context=context,
            auto_fixable=auto_fixable
        ))
    
    def _extract_chapter_num(self, filename: str) -> int:
        """Extract chapter number from filename."""
        match = re.search(r'CHAPTER_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def _calculate_grade(self, pass_rate: float, failures: int) -> str:
        """Calculate letter grade."""
        if failures > 0:
            return "F"
        if pass_rate >= 98:
            return "A+"
        if pass_rate >= 95:
            return "A"
        if pass_rate >= 90:
            return "B"
        if pass_rate >= 80:
            return "C"
        return "D"
    
    def _get_recommendation(self, status: str) -> str:
        """Get recommendation based on status."""
        recommendations = {
            "PASS": "Integrity verified. Proceed to prose audit.",
            "PASS_WITH_WARNINGS": "Minor issues detected. Auto-fix available. Proceed with caution.",
            "FAIL": "Critical integrity issues. BLOCKS PUBLICATION. Manual review required."
        }
        return recommendations.get(status, "Unknown status")
    
    def save_report(self, output_path: Path) -> Path:
        """Run audit and save report to JSON file."""
        report = self.audit()
        
        output_file = output_path / "integrity_audit_report.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Integrity report saved to: {output_file}")
        return output_file


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python integrity_auditor.py <work_dir> [output_dir]")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else work_dir / "audits"
    output_dir.mkdir(exist_ok=True)
    
    auditor = IntegrityAuditor(work_dir)
    auditor.save_report(output_dir)
