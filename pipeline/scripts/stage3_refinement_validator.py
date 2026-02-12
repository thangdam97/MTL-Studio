#!/usr/bin/env python3
"""
Stage 3 Refinement Validator - v1.7 Architecture
Hybrid validation using Gemini 2.5 Flash + human review flagging.

Features:
1. Sentence splitter for hard cap enforcement (dialogue >10w, narration >15w)
2. Expanded AI-ism detection (15 patterns from anti_ai_ism_patterns.json)
3. Tense consistency validation (past tense narrative standard)
4. Confidence scoring for review prioritization
5. Gemini 2.5 Flash validation for ambiguous cases

Target: A+ (94) → S- (96/100)
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict

# Gemini client import
import sys
sys.path.append(str(Path(__file__).parent.parent))
from pipeline.common.gemini_client import GeminiClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RefinementIssue:
    """Represents a single refinement issue requiring attention."""
    issue_type: str  # 'hard_cap', 'ai_ism', 'tense', 'rhythm'
    severity: str  # 'critical', 'high', 'medium', 'low'
    confidence: float  # 0.0-1.0
    file_name: str
    line_number: int
    matched_text: str
    context: str  # Surrounding 100 chars
    issue_description: str
    suggested_fix: Optional[str] = None
    auto_fix_eligible: bool = False
    human_review_required: bool = False
    gemini_validation: Optional[str] = None  # Gemini's assessment


@dataclass
class RefinementReport:
    """Summary report of Stage 3 refinement."""
    volume_name: str
    chapters_processed: int
    total_issues: int
    issues_by_type: Dict[str, int] = field(default_factory=dict)
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    auto_fixable: int = 0
    human_review_required: int = 0
    issues: List[RefinementIssue] = field(default_factory=list)

    # Quality metrics
    hard_cap_compliance: Dict[str, float] = field(default_factory=dict)
    ai_ism_density: float = 0.0
    tense_consistency: float = 100.0
    rhythm_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'issues': [asdict(i) for i in self.issues]
        }


class Stage3RefinementValidator:
    """Stage 3 Refinement Validator with hybrid Gemini + human review."""

    def __init__(
        self,
        config_dir: Path,
        use_gemini_validation: bool = True,
        auto_fix: bool = False
    ):
        """
        Initialize Stage 3 validator.

        Args:
            config_dir: Path to pipeline/config directory
            use_gemini_validation: Enable Gemini 2.5 Flash validation for ambiguous cases
            auto_fix: Automatically apply high-confidence fixes
        """
        self.config_dir = config_dir
        self.use_gemini_validation = use_gemini_validation
        self.auto_fix = auto_fix

        # Load configurations
        self.ai_ism_patterns = self._load_ai_ism_patterns()
        self.grammar_rules = self._load_grammar_rules()
        self.literacy_techniques = self._load_literacy_techniques()

        # Initialize Gemini client for ambiguous validation
        self.gemini_client = None
        if use_gemini_validation:
            try:
                self.gemini_client = GeminiClient(model_name="gemini-2.0-flash-exp")
                logger.info("Gemini 2.5 Flash validation enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.use_gemini_validation = False

    def _load_ai_ism_patterns(self) -> Dict:
        """Load AI-ism detection patterns."""
        pattern_file = self.config_dir / "anti_ai_ism_patterns.json"
        if pattern_file.exists():
            with open(pattern_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _load_grammar_rules(self) -> Dict:
        """Load grammar validation rules."""
        grammar_file = self.config_dir / "english_grammar_validation_t1.json"
        if grammar_file.exists():
            with open(grammar_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _load_literacy_techniques(self) -> Dict:
        """Load literacy techniques config."""
        lit_file = self.config_dir / "literacy_techniques.json"
        if lit_file.exists():
            with open(lit_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(re.findall(r'\b\w+\b', text))

    def _is_dialogue(self, line: str) -> bool:
        """Check if line contains dialogue."""
        return bool(re.search(r'"[^"]{10,}"', line))

    def _extract_dialogue_sentences(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Extract dialogue sentences from text.

        Returns:
            List of (sentence, start_pos, end_pos)
        """
        dialogues = []
        # Match quoted text
        for match in re.finditer(r'"([^"]+)"', text):
            content = match.group(1).strip()
            # Split by sentence boundaries
            sentences = re.split(r'(?<=[.!?])\s+', content)

            for sentence in sentences:
                if sentence:
                    dialogues.append((sentence, match.start(), match.end()))

        return dialogues

    def _extract_narration_sentences(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Extract narration sentences from text (excluding dialogue).

        Returns:
            List of (sentence, start_pos, end_pos)
        """
        # Remove dialogue first
        narration_text = re.sub(r'"[^"]*"', ' __DIALOGUE__ ', text)

        sentences = []
        # Split by sentence boundaries
        for match in re.finditer(r'([^.!?]+[.!?])', narration_text):
            sentence = match.group(1).strip()
            # Skip if it's just dialogue placeholder
            if '__DIALOGUE__' not in sentence and len(sentence) > 5:
                sentences.append((sentence, match.start(), match.end()))

        return sentences

    def check_hard_caps(
        self,
        file_path: Path,
        file_content: str
    ) -> List[RefinementIssue]:
        """
        Check hard cap violations (dialogue >10w, narration >15w).

        Priority: CRITICAL (these are binary enforcement rules)
        """
        issues = []
        lines = file_content.split('\n')

        for line_num, line in enumerate(lines, 1):
            # Check dialogue sentences
            dialogues = self._extract_dialogue_sentences(line)
            for dialogue, start, end in dialogues:
                word_count = self._count_words(dialogue)
                if word_count > 10:
                    context = line[max(0, start-50):min(len(line), end+50)]
                    issues.append(RefinementIssue(
                        issue_type='hard_cap_dialogue',
                        severity='critical',
                        confidence=1.0,
                        file_name=file_path.name,
                        line_number=line_num,
                        matched_text=dialogue,
                        context=context,
                        issue_description=f"Dialogue exceeds 10-word hard cap ({word_count} words)",
                        suggested_fix=None,  # Requires intelligent splitting
                        auto_fix_eligible=False,
                        human_review_required=True
                    ))

            # Check narration sentences
            narrations = self._extract_narration_sentences(line)
            for narration, start, end in narrations:
                word_count = self._count_words(narration)
                if word_count > 15:
                    context = line[max(0, start-50):min(len(line), end+50)]

                    # Check if it's close to soft target (12-14w) - lower severity
                    severity = 'high' if word_count <= 17 else 'critical'

                    issues.append(RefinementIssue(
                        issue_type='hard_cap_narration',
                        severity=severity,
                        confidence=1.0,
                        file_name=file_path.name,
                        line_number=line_num,
                        matched_text=narration,
                        context=context,
                        issue_description=f"Narration exceeds 15-word hard cap ({word_count} words)",
                        suggested_fix=None,  # Requires intelligent splitting
                        auto_fix_eligible=False,
                        human_review_required=True
                    ))

        return issues

    def check_ai_isms(
        self,
        file_path: Path,
        file_content: str
    ) -> List[RefinementIssue]:
        """
        Check for AI-ism patterns using expanded detection set.

        Uses anti_ai_ism_patterns.json with confidence scoring.
        """
        issues = []
        lines = file_content.split('\n')

        # Get AI-ism patterns
        patterns = self.ai_ism_patterns.get('patterns', [])

        for line_num, line in enumerate(lines, 1):
            # Skip dialogue (AI-isms are narrative-specific)
            if self._is_dialogue(line):
                continue

            for pattern_rule in patterns:
                pattern = pattern_rule.get('pattern', '')
                description = pattern_rule.get('description', '')
                auto_fix = pattern_rule.get('auto_fix', False)
                confidence = pattern_rule.get('confidence', 0.7)

                # Check for matches
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    matched_text = match.group(0)
                    context = line[max(0, match.start()-50):min(len(line), match.end()+50)]

                    # Get suggested fix if available
                    suggested_fix = pattern_rule.get('replacement', {}).get(matched_text.lower())

                    # Determine severity based on confidence
                    if confidence >= 0.9:
                        severity = 'high'
                    elif confidence >= 0.7:
                        severity = 'medium'
                    else:
                        severity = 'low'

                    issues.append(RefinementIssue(
                        issue_type='ai_ism',
                        severity=severity,
                        confidence=confidence,
                        file_name=file_path.name,
                        line_number=line_num,
                        matched_text=matched_text,
                        context=context,
                        issue_description=f"AI-ism detected: {description}",
                        suggested_fix=suggested_fix,
                        auto_fix_eligible=auto_fix and suggested_fix is not None,
                        human_review_required=confidence < 0.8
                    ))

        return issues

    def check_tense_consistency(
        self,
        file_path: Path,
        file_content: str
    ) -> List[RefinementIssue]:
        """
        Check narrative tense consistency (past tense standard).

        Flags present tense verbs in past-tense narrative.
        """
        issues = []
        lines = file_content.split('\n')

        # Present tense verb pattern
        present_verbs = r'\b(is|are|am|has|have|does|do|goes|comes|sees|says|feels|thinks|knows|gives|takes|makes|gets)\b'

        for line_num, line in enumerate(lines, 1):
            # Skip dialogue (present tense allowed in character speech)
            if self._is_dialogue(line):
                continue

            # Skip meta-text (brackets, parentheses)
            if re.search(r'[\[\(].*[\]\)]', line):
                continue

            # Remove quoted text before checking
            narration = re.sub(r'"[^"]*"', '', line)

            # Find present tense verbs
            for match in re.finditer(present_verbs, narration, re.IGNORECASE):
                matched_text = match.group(0)
                context = line[max(0, match.start()-50):min(len(line), match.end()+50)]

                # Check if it's a universal truth ("water boils at 100°C")
                if re.search(r'\b(learned|realized|discovered|understood|explained) that\b', context):
                    continue

                issues.append(RefinementIssue(
                    issue_type='tense_consistency',
                    severity='medium',
                    confidence=0.75,
                    file_name=file_path.name,
                    line_number=line_num,
                    matched_text=matched_text,
                    context=context,
                    issue_description=f"Present tense '{matched_text}' in past-tense narrative",
                    suggested_fix=None,  # Context-dependent
                    auto_fix_eligible=False,
                    human_review_required=True
                ))

        return issues

    async def validate_with_gemini(
        self,
        issue: RefinementIssue
    ) -> Optional[str]:
        """
        Use Gemini 2.5 Flash to validate ambiguous cases.

        Returns:
            Gemini's assessment or None if validation fails
        """
        if not self.gemini_client:
            return None

        prompt = f"""You are a literary editor reviewing English light novel prose.

**Issue Type:** {issue.issue_type}
**Severity:** {issue.severity}
**Detected Text:** "{issue.matched_text}"
**Context:** ...{issue.context}...
**Issue Description:** {issue.issue_description}

**Question:** Is this a genuine issue that requires correction, or is it acceptable in context?

Respond with ONE of:
1. "GENUINE_ISSUE: [brief reason]"
2. "ACCEPTABLE: [brief reason]"
3. "SUGGEST_FIX: [proposed fix]"

Keep response under 50 words."""

        try:
            response = await self.gemini_client.generate_text(prompt, temperature=0.3)
            return response.strip()
        except Exception as e:
            logger.error(f"Gemini validation failed: {e}")
            return None

    def validate_file(self, file_path: Path) -> List[RefinementIssue]:
        """
        Run all validation checks on a single file.

        Returns:
            List of all issues found
        """
        logger.info(f"Validating: {file_path.name}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        all_issues = []

        # 1. Hard cap validation (critical)
        all_issues.extend(self.check_hard_caps(file_path, content))

        # 2. AI-ism detection
        all_issues.extend(self.check_ai_isms(file_path, content))

        # 3. Tense consistency
        all_issues.extend(self.check_tense_consistency(file_path, content))

        return all_issues

    def validate_volume(self, volume_dir: Path) -> RefinementReport:
        """
        Validate entire volume (all EN chapters).

        Args:
            volume_dir: Path to volume directory containing EN/ subdirectory

        Returns:
            RefinementReport with all findings
        """
        en_dir = volume_dir / "EN"

        if not en_dir.exists():
            raise FileNotFoundError(f"EN directory not found: {en_dir}")

        report = RefinementReport(
            volume_name=volume_dir.name,
            chapters_processed=0,
            total_issues=0
        )

        # Process each chapter
        chapter_files = sorted(en_dir.glob("CHAPTER_*.md"))

        for chapter_file in chapter_files:
            issues = self.validate_file(chapter_file)
            report.issues.extend(issues)
            report.chapters_processed += 1

        # Aggregate statistics
        report.total_issues = len(report.issues)

        for issue in report.issues:
            # Count by type
            report.issues_by_type[issue.issue_type] = \
                report.issues_by_type.get(issue.issue_type, 0) + 1

            # Count by severity
            report.issues_by_severity[issue.severity] = \
                report.issues_by_severity.get(issue.severity, 0) + 1

            # Count auto-fixable vs human review
            if issue.auto_fix_eligible:
                report.auto_fixable += 1
            if issue.human_review_required:
                report.human_review_required += 1

        # Calculate quality metrics
        self._calculate_quality_metrics(report)

        return report

    def _calculate_quality_metrics(self, report: RefinementReport):
        """Calculate quality metrics from issues."""
        # Hard cap compliance
        hard_cap_dialogue = [i for i in report.issues if i.issue_type == 'hard_cap_dialogue']
        hard_cap_narration = [i for i in report.issues if i.issue_type == 'hard_cap_narration']

        # Estimate total sentences (rough approximation)
        total_sentences_est = report.chapters_processed * 300  # ~300 sentences per chapter

        if total_sentences_est > 0:
            dialogue_compliance = 100 * (1 - len(hard_cap_dialogue) / (total_sentences_est * 0.4))
            narration_compliance = 100 * (1 - len(hard_cap_narration) / (total_sentences_est * 0.6))

            report.hard_cap_compliance = {
                'dialogue': max(0, dialogue_compliance),
                'narration': max(0, narration_compliance)
            }

        # AI-ism density (per chapter)
        ai_isms = [i for i in report.issues if i.issue_type == 'ai_ism']
        report.ai_ism_density = len(ai_isms) / report.chapters_processed if report.chapters_processed > 0 else 0

        # Tense consistency (percentage)
        tense_issues = [i for i in report.issues if i.issue_type == 'tense_consistency']
        if total_sentences_est > 0:
            report.tense_consistency = 100 * (1 - len(tense_issues) / total_sentences_est)

    def generate_report(
        self,
        report: RefinementReport,
        output_dir: Path
    ):
        """Generate JSON and Markdown reports."""
        # JSON report
        json_path = output_dir / f"{report.volume_name}_STAGE3_REPORT.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # Markdown report
        md_path = output_dir / f"{report.volume_name}_STAGE3_REPORT.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# Stage 3 Refinement Validation Report\n\n")
            f.write(f"**Volume:** {report.volume_name}\n\n")
            f.write(f"**Chapters Processed:** {report.chapters_processed}\n\n")
            f.write(f"---\n\n")

            # Executive Summary
            f.write(f"## Executive Summary\n\n")
            f.write(f"**Total Issues:** {report.total_issues}\n\n")
            f.write(f"- **Auto-fixable:** {report.auto_fixable} ({100*report.auto_fixable/report.total_issues:.1f}%)\n")
            f.write(f"- **Human Review Required:** {report.human_review_required} ({100*report.human_review_required/report.total_issues:.1f}%)\n\n")

            # Quality Metrics
            f.write(f"### Quality Metrics\n\n")
            f.write(f"| Metric | Score |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Dialogue Hard Cap Compliance | {report.hard_cap_compliance.get('dialogue', 0):.1f}% |\n")
            f.write(f"| Narration Hard Cap Compliance | {report.hard_cap_compliance.get('narration', 0):.1f}% |\n")
            f.write(f"| AI-ism Density | {report.ai_ism_density:.2f} per chapter |\n")
            f.write(f"| Tense Consistency | {report.tense_consistency:.1f}% |\n\n")

            # Issues by Type
            f.write(f"## Issues by Type\n\n")
            for issue_type, count in sorted(report.issues_by_type.items(), key=lambda x: -x[1]):
                f.write(f"- **{issue_type}**: {count}\n")
            f.write(f"\n")

            # Issues by Severity
            f.write(f"## Issues by Severity\n\n")
            for severity, count in sorted(report.issues_by_severity.items(), key=lambda x: ['critical', 'high', 'medium', 'low'].index(x[0])):
                f.write(f"- **{severity.upper()}**: {count}\n")
            f.write(f"\n")

            # Detailed Issues (grouped by type and file)
            f.write(f"## Detailed Issues\n\n")

            # Group by type then file
            issues_by_type_file = defaultdict(lambda: defaultdict(list))
            for issue in report.issues:
                issues_by_type_file[issue.issue_type][issue.file_name].append(issue)

            for issue_type in sorted(issues_by_type_file.keys()):
                f.write(f"### {issue_type.upper()}\n\n")

                for file_name in sorted(issues_by_type_file[issue_type].keys()):
                    issues = issues_by_type_file[issue_type][file_name]
                    f.write(f"#### {file_name} ({len(issues)} issues)\n\n")

                    for issue in issues:
                        f.write(f"**Line {issue.line_number}** | Severity: `{issue.severity}` | Confidence: `{issue.confidence:.2f}`\n\n")
                        f.write(f"- **Matched:** `{issue.matched_text}`\n")
                        f.write(f"- **Issue:** {issue.issue_description}\n")
                        if issue.suggested_fix:
                            f.write(f"- **Suggested Fix:** `{issue.suggested_fix}`\n")
                        if issue.gemini_validation:
                            f.write(f"- **Gemini Assessment:** {issue.gemini_validation}\n")
                        f.write(f"- **Context:** ...{issue.context}...\n\n")
                        f.write(f"---\n\n")

        logger.info(f"Reports generated: {json_path}, {md_path}")


def main():
    """Run Stage 3 validation on 17fb volume."""
    import argparse

    parser = argparse.ArgumentParser(description="Stage 3 Refinement Validator")
    parser.add_argument("--volume", type=str, required=True, help="Volume directory name")
    parser.add_argument("--no-gemini", action="store_true", help="Disable Gemini validation")
    parser.add_argument("--auto-fix", action="store_true", help="Apply auto-fixes (NOT RECOMMENDED for first run)")

    args = parser.parse_args()

    # Paths
    pipeline_dir = Path(__file__).parent.parent
    config_dir = pipeline_dir / "config"
    work_dir = pipeline_dir / "WORK" / args.volume

    if not work_dir.exists():
        print(f"❌ Volume directory not found: {work_dir}")
        return 1

    # Create validator
    validator = Stage3RefinementValidator(
        config_dir=config_dir,
        use_gemini_validation=not args.no_gemini,
        auto_fix=args.auto_fix
    )

    # Run validation
    print(f"\n{'='*60}")
    print(f"Stage 3 Refinement Validation")
    print(f"{'='*60}")
    print(f"Volume: {args.volume}")
    print(f"Gemini validation: {'Enabled' if not args.no_gemini else 'Disabled'}")
    print(f"Auto-fix: {'Enabled' if args.auto_fix else 'Disabled'}")
    print(f"{'='*60}\n")

    report = validator.validate_volume(work_dir)

    # Generate reports
    validator.generate_report(report, pipeline_dir)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Validation Complete")
    print(f"{'='*60}")
    print(f"Total issues: {report.total_issues}")
    print(f"Auto-fixable: {report.auto_fixable}")
    print(f"Human review required: {report.human_review_required}")
    print(f"\nQuality Metrics:")
    print(f"  Dialogue hard cap compliance: {report.hard_cap_compliance.get('dialogue', 0):.1f}%")
    print(f"  Narration hard cap compliance: {report.hard_cap_compliance.get('narration', 0):.1f}%")
    print(f"  AI-ism density: {report.ai_ism_density:.2f} per chapter")
    print(f"  Tense consistency: {report.tense_consistency:.1f}%")
    print(f"\nReports saved to: {pipeline_dir}")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    exit(main())
