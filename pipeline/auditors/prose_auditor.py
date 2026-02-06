"""
SUBAGENT 3: Prose Quality Auditor
==================================
Mission: Ensure English translation adheres to natural prose standards
using the Grammar RAG pattern database. Detect AI-isms, Victorian patterns,
contraction issues, and missed transcreation opportunities.

Output: prose_audit_report.json
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from modules.english_grammar_rag import EnglishGrammarRAG
except ImportError:
    EnglishGrammarRAG = None


class ProseIssueType(Enum):
    AI_ISM = "AI_ISM"
    CONTRACTION = "CONTRACTION"
    VICTORIAN = "VICTORIAN"
    TRANSCREATION = "TRANSCREATION"
    PASSIVE_VOICE = "PASSIVE_VOICE"
    NOMINALIZATION = "NOMINALIZATION"


@dataclass
class ProseIssue:
    issue_id: str
    issue_type: str
    severity: str
    chapter: str
    line: int
    found: str
    suggestion: str
    context: str
    pattern_id: Optional[str] = None


class ProseAuditor:
    """
    Prose Quality Auditor - Subagent 3
    
    Validates English prose quality using Grammar RAG patterns,
    AI-ism detection, and contraction analysis.
    """
    
    def __init__(self, work_dir: Path, config_dir: Optional[Path] = None):
        self.work_dir = Path(work_dir)
        self.jp_dir = self.work_dir / "JP"
        self.en_dir = self.work_dir / "EN"
        
        # Config directory for RAG patterns
        if config_dir is None:
            config_dir = self.work_dir.parent / "config"
        self.config_dir = Path(config_dir)
        
        self.issues: List[ProseIssue] = []
        
        # Initialize Grammar RAG
        self.rag = None
        if EnglishGrammarRAG:
            try:
                # Pass the specific JSON file path, not the directory
                rag_file = self.config_dir / "english_grammar_rag.json"
                if rag_file.exists():
                    self.rag = EnglishGrammarRAG(str(rag_file))
                else:
                    print(f"Warning: Grammar RAG file not found at {rag_file}")
            except Exception as e:
                print(f"Warning: Could not load Grammar RAG: {e}")
        
        # Load AI-ism patterns
        self.ai_ism_patterns = self._load_ai_ism_patterns()
        
        # Victorian patterns
        self.victorian_patterns = {
            "I shall": {"fix": "I'll / I will", "exception": "oath/decree"},
            "can you not": {"fix": "can't you", "exception": None},
            "do you not": {"fix": "don't you", "exception": None},
            "If you will excuse me": {"fix": "Excuse me", "exception": None},
            "I must confess": {"fix": "I have to say", "exception": "formal"},
            "It would appear": {"fix": "It seems / looks like", "exception": None},
            "I dare say": {"fix": "I'd say", "exception": "period piece"},
        }
        
        # Contraction rules
        self.contraction_pairs = {
            "I am": "I'm",
            "you are": "you're",
            "he is": "he's",
            "she is": "she's",
            "it is": "it's",
            "we are": "we're",
            "they are": "they're",
            "do not": "don't",
            "does not": "doesn't",
            "did not": "didn't",
            "will not": "won't",
            "would not": "wouldn't",
            "could not": "couldn't",
            "should not": "shouldn't",
            "can not": "can't",
            "cannot": "can't",
            "is not": "isn't",
            "are not": "aren't",
            "was not": "wasn't",
            "were not": "weren't",
            "have not": "haven't",
            "has not": "hasn't",
            "had not": "hadn't",
            "I have": "I've",
            "you have": "you've",
            "we have": "we've",
            "they have": "they've",
            "I will": "I'll",
            "you will": "you'll",
            "he will": "he'll",
            "she will": "she'll",
            "we will": "we'll",
            "they will": "they'll",
            "I would": "I'd",
            "you would": "you'd",
            "he would": "he'd",
            "she would": "she'd",
            "we would": "we'd",
            "they would": "they'd",
            "that is": "that's",
            "there is": "there's",
            "what is": "what's",
            "who is": "who's",
            "let us": "let's",
        }
        
        # Literal translation markers to detect missed transcreation
        self.literal_markers = {
            "yappari_transcreation": ["as expected,", "as i expected"],
            "sasuga_transcreation": ["as expected of"],
            "shikata_nai_transcreation": ["it can't be helped", "it cannot be helped", "there's no helping it"],
            "maa_transcreation": [],  # Hard to detect literal
            "betsu_ni_transcreation": ["not particularly", "it's not particularly"],
            "zettai_transcreation": ["absolutely"],
            "mattaku_transcreation": ["completely", "totally"],
            "masaka_transcreation": ["no way that", "could it be that"],
            "naruhodo_transcreation": ["i see,", "i understand,"],
            "tashika_ni_transcreation": ["certainly,", "certainly it is"],
        }
        
    def _load_ai_ism_patterns(self) -> Dict:
        """Load AI-ism patterns from config."""
        patterns_path = self.config_dir / "anti_ai_ism_patterns.json"
        
        if patterns_path.exists():
            with open(patterns_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Default patterns if config not found
        return {
            "critical": [
                {"pattern": "couldn't help but", "fix": "naturally / simply", "severity": "MAJOR"},
                {"pattern": "a sense of", "fix": "remove or rephrase", "severity": "MINOR"},
                {"pattern": "the familiar", "fix": "the [specific noun]", "severity": "MINOR"},
                {"pattern": "the comfortable", "fix": "specific description", "severity": "MINOR"},
                {"pattern": "voice tinged with", "fix": "show emotion via action", "severity": "MAJOR"},
                {"pattern": "voice laced with", "fix": "show emotion via action", "severity": "MAJOR"},
                {"pattern": "couldn't help feeling", "fix": "felt / was", "severity": "MAJOR"},
                {"pattern": "found myself", "fix": "I [verb]", "severity": "MINOR"},
                {"pattern": "I couldn't deny", "fix": "I had to admit", "severity": "MINOR"},
                {"pattern": "a mixture of", "fix": "specific emotions", "severity": "MINOR"},
                {"pattern": "a wave of", "fix": "specific sensation", "severity": "MINOR"},
                {"pattern": "a pang of", "fix": "specific emotion", "severity": "MINOR"},
                {"pattern": "welled up", "fix": "specific action", "severity": "MINOR"},
            ]
        }
    
    def audit(self) -> Dict:
        """Run full prose quality audit."""
        
        print("=" * 60)
        print("SUBAGENT 3: PROSE QUALITY AUDITOR")
        print("=" * 60)
        
        en_chapters = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        jp_chapters = sorted(self.jp_dir.glob("CHAPTER_*.md"))
        
        if not en_chapters:
            raise FileNotFoundError(f"No EN chapters found in {self.en_dir}")
        
        rag_loaded = self.rag is not None
        pattern_count = len(self.rag.patterns) if self.rag else 0
        
        print(f"Found {len(en_chapters)} EN chapters to audit")
        print(f"Grammar RAG: {'Loaded' if rag_loaded else 'Not available'} ({pattern_count} patterns)")
        
        # Aggregate stats
        total_words = 0
        total_sentences = 0
        total_ai_isms = 0
        total_contracted = 0
        total_expanded = 0
        total_victorian = 0
        total_transcreation_detected = 0
        total_transcreation_missed = 0
        
        ai_ism_details = []
        contraction_violations = []
        victorian_issues = []
        transcreation_issues = []
        
        chapter_results = []
        
        # Audit each chapter
        for en_file in en_chapters:
            chapter_num = self._extract_chapter_num(en_file.name)
            jp_file = self.jp_dir / f"CHAPTER_{chapter_num:02d}.md"
            
            print(f"\n✍️ Auditing Chapter {chapter_num:02d} prose...")
            
            en_text = en_file.read_text(encoding='utf-8')
            jp_text = jp_file.read_text(encoding='utf-8') if jp_file.exists() else ""
            
            # Count words and sentences
            words = len(en_text.split())
            sentences = len(re.findall(r'[.!?]+', en_text))
            total_words += words
            total_sentences += sentences
            
            # Check AI-isms
            ai_issues = self._check_ai_isms(en_text, chapter_num)
            total_ai_isms += len(ai_issues)
            ai_ism_details.extend(ai_issues)
            
            # Check contractions
            contracted, expanded, violations = self._check_contractions(en_text, chapter_num)
            total_contracted += contracted
            total_expanded += expanded
            contraction_violations.extend(violations)
            
            # Check Victorian patterns
            victorian = self._check_victorian(en_text, chapter_num)
            total_victorian += len(victorian)
            victorian_issues.extend(victorian)
            
            # Check transcreation (if RAG available and JP exists)
            if self.rag and jp_text:
                detected, missed, issues = self._check_transcreation(jp_text, en_text, chapter_num)
                total_transcreation_detected += detected
                total_transcreation_missed += missed
                transcreation_issues.extend(issues)
            
            chapter_results.append({
                "chapter_id": f"{chapter_num:02d}",
                "words": words,
                "sentences": sentences,
                "ai_isms": len(ai_issues),
                "contraction_violations": len(violations),
                "victorian_patterns": len(victorian),
                "transcreation_missed": len([i for i in transcreation_issues if i.get("chapter") == f"{chapter_num:02d}"])
            })
        
        # Calculate metrics
        ai_ism_density = (total_ai_isms / max(total_words, 1)) * 1000
        contraction_rate = (total_contracted / max(total_contracted + total_expanded, 1)) * 100
        transcreation_rate = ((total_transcreation_detected - total_transcreation_missed) / max(total_transcreation_detected, 1)) * 100
        
        # Calculate prose score
        prose_score = self._calculate_prose_score(
            ai_ism_density=ai_ism_density,
            contraction_rate=contraction_rate,
            victorian_count=total_victorian,
            transcreation_rate=transcreation_rate
        )
        
        # Determine verdict
        verdict = self._calculate_verdict(prose_score, ai_ism_density, contraction_rate)
        
        # Categorize AI-isms
        ai_ism_categories = {}
        for issue in ai_ism_details:
            cat = issue.get("category", "UNKNOWN")
            if cat not in ai_ism_categories:
                ai_ism_categories[cat] = 0
            ai_ism_categories[cat] += 1
        
        # Build report
        report = {
            "audit_type": "prose_quality",
            "volume_id": self.work_dir.name.split('_')[-1][:4] if '_' in self.work_dir.name else "unknown",
            "timestamp": datetime.now().isoformat(),
            "auditor_version": "2.0",
            "grammar_rag_version": "1.0" if self.rag else "N/A",
            "patterns_loaded": pattern_count,
            
            "summary": {
                "total_words": total_words,
                "total_sentences": total_sentences,
                "ai_ism_count": total_ai_isms,
                "ai_ism_density": round(ai_ism_density, 2),
                "contraction_rate": round(contraction_rate, 1),
                "victorian_patterns": total_victorian,
                "missed_transcreations": total_transcreation_missed,
                "prose_score": round(prose_score, 1),
                "verdict": verdict
            },
            
            "thresholds": {
                "ai_ism_density": {
                    "excellent": "<0.1 per 1k words",
                    "good": "0.1-0.5 per 1k words",
                    "acceptable": "0.5-1.0 per 1k words",
                    "poor": ">1.0 per 1k words"
                },
                "contraction_rate": {
                    "ffxvi_tier": "99%+",
                    "excellent": "95%+",
                    "good": "90%+",
                    "acceptable": "80%+",
                    "poor": "<80%"
                }
            },
            
            "ai_isms": {
                "status": self._get_ai_ism_status(ai_ism_density),
                "count": total_ai_isms,
                "density_per_1k": round(ai_ism_density, 2),
                "by_severity": {
                    "critical": len([i for i in ai_ism_details if i.get("severity") == "CRITICAL"]),
                    "major": len([i for i in ai_ism_details if i.get("severity") == "MAJOR"]),
                    "minor": len([i for i in ai_ism_details if i.get("severity") == "MINOR"])
                },
                "issues": ai_ism_details[:50],  # Limit to first 50
                "categories": ai_ism_categories
            },
            
            "contractions": {
                "status": self._get_contraction_status(contraction_rate),
                "rate": round(contraction_rate, 1),
                "total_opportunities": total_contracted + total_expanded,
                "contracted": total_contracted,
                "expanded": total_expanded,
                "violations": contraction_violations[:30]  # Limit
            },
            
            "victorian_patterns": {
                "status": "PASS" if total_victorian <= 3 else "WARNING",
                "count": total_victorian,
                "exempted": 0,  # Would need character archetype detection
                "flagged": total_victorian,
                "issues": victorian_issues[:20]
            },
            
            "transcreation_opportunities": {
                "status": "GOOD" if transcreation_rate >= 80 else "NEEDS_IMPROVEMENT",
                "patterns_detected": total_transcreation_detected,
                "well_handled": total_transcreation_detected - total_transcreation_missed,
                "missed": total_transcreation_missed,
                "improvement_suggestions": transcreation_issues[:20]
            },
            
            "chapter_breakdown": chapter_results,
            
            "all_issues": [asdict(i) for i in self.issues],
            
            "final_verdict": {
                "grade": self._prose_score_to_grade(prose_score),
                "prose_score": round(prose_score, 1),
                "status": verdict,
                "blocking_issues": len([i for i in self.issues if i.severity == "CRITICAL"]),
                "improvement_areas": self._get_improvement_areas(
                    ai_ism_density, contraction_rate, total_victorian, transcreation_rate
                ),
                "recommendation": self._get_recommendation(verdict)
            }
        }
        
        print(f"\n{'=' * 60}")
        print(f"PROSE AUDIT COMPLETE")
        print(f"Score: {prose_score:.1f}/100 | Verdict: {verdict}")
        print(f"{'=' * 60}")
        
        return report
    
    def _check_ai_isms(self, text: str, chapter_num: int) -> List[Dict]:
        """Check for AI-ism patterns."""
        issues = []
        text_lower = text.lower()
        lines = text.split('\n')
        
        # Check each pattern
        all_patterns = self.ai_ism_patterns.get("critical", [])
        
        for pattern_info in all_patterns:
            pattern = pattern_info.get("pattern", "").lower()
            if not pattern:
                continue
            
            # Find all occurrences
            for i, line in enumerate(lines, 1):
                if pattern in line.lower():
                    issue_id = f"PRO-AI-{chapter_num:02d}-{len(issues)+1:03d}"
                    issues.append({
                        "issue_id": issue_id,
                        "chapter": f"{chapter_num:02d}",
                        "line": i,
                        "severity": pattern_info.get("severity", "MINOR"),
                        "pattern": pattern,
                        "context": line.strip()[:80],
                        "suggestion": pattern_info.get("fix", "Rephrase"),
                        "category": self._categorize_ai_ism(pattern)
                    })
                    
                    self._add_issue(
                        issue_type=ProseIssueType.AI_ISM,
                        severity=pattern_info.get("severity", "MINOR"),
                        chapter=f"{chapter_num:02d}",
                        line=i,
                        found=pattern,
                        suggestion=pattern_info.get("fix", "Rephrase"),
                        context=line.strip()[:80]
                    )
        
        return issues
    
    def _categorize_ai_ism(self, pattern: str) -> str:
        """Categorize AI-ism pattern."""
        if "couldn't help" in pattern or "found myself" in pattern:
            return "VERBOSE_CONSTRUCTION"
        if "a sense of" in pattern or "a wave of" in pattern or "a pang of" in pattern:
            return "FILLER_PHRASE"
        if "voice" in pattern and ("tinged" in pattern or "laced" in pattern):
            return "EMOTIONAL_TELLING"
        if "the familiar" in pattern or "the comfortable" in pattern:
            return "STIFF_PHRASING"
        return "OTHER"
    
    def _check_contractions(self, text: str, chapter_num: int) -> Tuple[int, int, List[Dict]]:
        """Check contraction usage."""
        contracted = 0
        expanded = 0
        violations = []
        
        lines = text.split('\n')
        
        # Count contractions used
        for contraction in self.contraction_pairs.values():
            contracted += len(re.findall(r'\b' + re.escape(contraction) + r'\b', text, re.IGNORECASE))
        
        # Count expanded forms that should be contracted
        for expanded_form, contraction in self.contraction_pairs.items():
            pattern = r'\b' + re.escape(expanded_form) + r'\b'
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            
            for match in matches:
                # Find line number
                pos = match.start()
                line_num = text[:pos].count('\n') + 1
                line_text = lines[line_num - 1] if line_num <= len(lines) else ""
                
                # Check if it's in dialogue (should be contracted)
                # Simple heuristic: if there are quotes on the same line
                if '"' in line_text or '"' in line_text or "'" in line_text:
                    expanded += 1
                    violations.append({
                        "issue_id": f"PRO-CON-{chapter_num:02d}-{len(violations)+1:03d}",
                        "chapter": f"{chapter_num:02d}",
                        "line": line_num,
                        "found": expanded_form,
                        "expected": contraction,
                        "context": line_text.strip()[:60],
                        "exception_applies": False
                    })
                    
                    self._add_issue(
                        issue_type=ProseIssueType.CONTRACTION,
                        severity="LOW",
                        chapter=f"{chapter_num:02d}",
                        line=line_num,
                        found=expanded_form,
                        suggestion=contraction,
                        context=line_text.strip()[:60]
                    )
        
        return contracted, expanded, violations
    
    def _check_victorian(self, text: str, chapter_num: int) -> List[Dict]:
        """Check for Victorian/archaic patterns."""
        issues = []
        lines = text.split('\n')
        
        for pattern, info in self.victorian_patterns.items():
            for i, line in enumerate(lines, 1):
                if pattern.lower() in line.lower():
                    issues.append({
                        "issue_id": f"PRO-VIC-{chapter_num:02d}-{len(issues)+1:03d}",
                        "chapter": f"{chapter_num:02d}",
                        "line": i,
                        "pattern": pattern,
                        "context": line.strip()[:60],
                        "suggestion": info["fix"],
                        "exception": info.get("exception")
                    })
                    
                    self._add_issue(
                        issue_type=ProseIssueType.VICTORIAN,
                        severity="LOW",
                        chapter=f"{chapter_num:02d}",
                        line=i,
                        found=pattern,
                        suggestion=info["fix"],
                        context=line.strip()[:60]
                    )
        
        return issues
    
    def _check_transcreation(self, jp_text: str, en_text: str, chapter_num: int) -> Tuple[int, int, List[Dict]]:
        """Check for missed transcreation opportunities using Grammar RAG."""
        detected = 0
        missed = 0
        issues = []
        
        if not self.rag:
            return detected, missed, issues
        
        # Detect patterns that should be applied
        detected_patterns = self.rag.detect_patterns(jp_text)
        detected = len(detected_patterns)
        
        en_lower = en_text.lower()
        
        # Check if literal translations were used
        for pattern in detected_patterns:
            pattern_id = pattern.get("id", "")
            literal_markers = self.literal_markers.get(pattern_id, [])
            
            for marker in literal_markers:
                if marker in en_lower:
                    missed += 1
                    
                    # Get natural alternative from RAG
                    natural_alt = self._get_natural_alternative(pattern_id)
                    
                    issues.append({
                        "issue_id": f"PRO-TRC-{chapter_num:02d}-{len(issues)+1:03d}",
                        "chapter": f"{chapter_num:02d}",
                        "jp_pattern": pattern.get("matched_indicator", ""),
                        "current_en": marker,
                        "suggested_en": natural_alt,
                        "pattern_id": pattern_id,
                        "priority": pattern.get("priority", "medium")
                    })
                    
                    self._add_issue(
                        issue_type=ProseIssueType.TRANSCREATION,
                        severity="MEDIUM",
                        chapter=f"{chapter_num:02d}",
                        line=0,
                        found=marker,
                        suggestion=natural_alt,
                        context=f"Pattern: {pattern_id}",
                        pattern_id=pattern_id
                    )
                    break  # Only count once per pattern
        
        return detected, missed, issues
    
    def _get_natural_alternative(self, pattern_id: str) -> str:
        """Get natural alternative for a pattern."""
        alternatives = {
            "yappari_transcreation": "Sure enough / Just as I thought / Yeah, definitely",
            "sasuga_transcreation": "That's [name] for you / Classic [name]",
            "shikata_nai_transcreation": "Oh well / What can you do",
            "betsu_ni_transcreation": "It's not like I... / Whatever",
            "zettai_transcreation": "No way / For sure / I swear",
            "mattaku_transcreation": "Good grief / Honestly / Jeez",
            "masaka_transcreation": "Wait, you... / Don't tell me...",
            "naruhodo_transcreation": "Ah, that makes sense / I get it",
            "tashika_ni_transcreation": "Fair point / You're right / If I remember correctly",
        }
        return alternatives.get(pattern_id, "Rephrase naturally")
    
    def _add_issue(self, issue_type: ProseIssueType, severity: str,
                   chapter: str, line: int, found: str, suggestion: str,
                   context: str, pattern_id: Optional[str] = None):
        """Add a prose issue."""
        issue_id = f"PRO-{issue_type.value[:3]}-{chapter}-{len(self.issues)+1:03d}"
        
        self.issues.append(ProseIssue(
            issue_id=issue_id,
            issue_type=issue_type.value,
            severity=severity,
            chapter=chapter,
            line=line,
            found=found,
            suggestion=suggestion,
            context=context,
            pattern_id=pattern_id
        ))
    
    def _calculate_prose_score(self, ai_ism_density: float, contraction_rate: float,
                                victorian_count: int, transcreation_rate: float) -> float:
        """Calculate overall prose score (0-100)."""
        
        # AI-ism score (0-30 points)
        if ai_ism_density < 0.1:
            ai_score = 30
        elif ai_ism_density < 0.5:
            ai_score = 25
        elif ai_ism_density < 1.0:
            ai_score = 20
        else:
            ai_score = max(0, 30 - ai_ism_density * 10)
        
        # Contraction score (0-30 points)
        contraction_score = min(30, contraction_rate * 0.3)
        
        # Victorian score (0-20 points)
        victorian_score = max(0, 20 - victorian_count * 2)
        
        # Transcreation score (0-20 points)
        transcreation_score = transcreation_rate * 0.2
        
        return ai_score + contraction_score + victorian_score + transcreation_score
    
    def _calculate_verdict(self, prose_score: float, ai_ism_density: float, 
                           contraction_rate: float) -> str:
        """Calculate verdict based on scores."""
        if prose_score >= 90 and ai_ism_density < 0.5 and contraction_rate >= 90:
            return "PASS"
        elif prose_score >= 80 and contraction_rate >= 80:
            return "PASS_WITH_SUGGESTIONS"
        elif prose_score >= 70:
            return "NEEDS_IMPROVEMENT"
        else:
            return "FAIL"
    
    def _get_ai_ism_status(self, density: float) -> str:
        """Get AI-ism status label."""
        if density < 0.1:
            return "EXCELLENT"
        elif density < 0.5:
            return "GOOD"
        elif density < 1.0:
            return "ACCEPTABLE"
        return "POOR"
    
    def _get_contraction_status(self, rate: float) -> str:
        """Get contraction rate status label."""
        if rate >= 99:
            return "FFXVI_TIER"
        elif rate >= 95:
            return "EXCELLENT"
        elif rate >= 90:
            return "GOOD"
        elif rate >= 80:
            return "ACCEPTABLE"
        return "POOR"
    
    def _prose_score_to_grade(self, score: float) -> str:
        """Convert prose score to letter grade."""
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 85:
            return "B+"
        elif score >= 80:
            return "B"
        elif score >= 75:
            return "C+"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"
    
    def _get_improvement_areas(self, ai_ism_density: float, contraction_rate: float,
                                victorian_count: int, transcreation_rate: float) -> List[str]:
        """Get list of improvement areas."""
        areas = []
        
        if ai_ism_density >= 0.5:
            areas.append(f"AI-isms: {ai_ism_density:.2f}/1k words (target: <0.5)")
        
        if contraction_rate < 90:
            areas.append(f"Contraction rate: {contraction_rate:.1f}% (target: >90%)")
        
        if victorian_count > 3:
            areas.append(f"Victorian patterns: {victorian_count} instances")
        
        if transcreation_rate < 80:
            areas.append(f"Transcreation: {transcreation_rate:.1f}% well-handled (target: >80%)")
        
        return areas
    
    def _get_recommendation(self, verdict: str) -> str:
        """Get recommendation based on verdict."""
        recommendations = {
            "PASS": "High-quality prose. Ready for final audit.",
            "PASS_WITH_SUGGESTIONS": "Good prose with minor improvements available. Proceed to final audit.",
            "NEEDS_IMPROVEMENT": "Several prose quality issues. Review and revise before publication.",
            "FAIL": "Significant prose quality issues. Requires major revision."
        }
        return recommendations.get(verdict, "Unknown verdict")
    
    def _extract_chapter_num(self, filename: str) -> int:
        """Extract chapter number from filename."""
        match = re.search(r'CHAPTER_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def save_report(self, output_path: Path) -> Path:
        """Run audit and save report to JSON file."""
        report = self.audit()
        
        output_file = output_path / "prose_audit_report.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Prose report saved to: {output_file}")
        return output_file


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python prose_auditor.py <work_dir> [output_dir] [config_dir]")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else work_dir / "audits"
    config_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    
    output_dir.mkdir(exist_ok=True)
    
    auditor = ProseAuditor(work_dir, config_dir)
    auditor.save_report(output_dir)
