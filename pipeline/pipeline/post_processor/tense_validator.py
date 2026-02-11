"""
Tense Consistency Validator
Detects and corrects narrative tense inconsistencies in English translations.
Follows international literary prose conventions with comprehensive whitelist system.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class TenseViolation:
    """Represents a single tense consistency violation."""
    rule_id: str
    line_number: int
    matched_text: str
    paragraph_context: str
    issue_description: str
    suggested_fix: Optional[str] = None
    confidence: float = 1.0
    severity: str = "medium"  # 'high', 'medium', 'low'
    auto_fix_eligible: bool = False


@dataclass
class TenseReport:
    """Summary report of tense validation."""
    file_path: str
    total_lines: int
    total_violations: int
    violations_by_severity: Dict[str, int] = field(default_factory=dict)
    violations_by_rule: Dict[str, int] = field(default_factory=dict)
    violations: List[TenseViolation] = field(default_factory=list)
    auto_fixed: int = 0
    paragraph_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'violations': [asdict(v) for v in self.violations]
        }


class TenseConsistencyValidator:
    """Validates narrative tense consistency using international prose standards."""

    def __init__(self, config_path: Optional[Path] = None, auto_fix: bool = False):
        """
        Initialize Tense Consistency Validator.

        Args:
            config_path: Path to english_grammar_validation_t1.json
            auto_fix: Whether to automatically fix high-confidence violations
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "english_grammar_validation_t1.json"

        self.config_path = config_path
        self.auto_fix = auto_fix
        self.rules = self._load_tense_rules()

    def _load_tense_rules(self) -> Dict[str, Any]:
        """Load tense consistency rules from config."""
        if not self.config_path.exists():
            logger.warning(f"Config not found: {self.config_path}")
            return {}

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Check if rules are nested under validation_categories
            if 'validation_categories' in config:
                return config['validation_categories'].get('tense_consistency', {})
            else:
                return config.get('tense_consistency', {})

    def _extract_verbs(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Extract past and present tense verbs from text.

        Returns:
            (past_verbs, present_verbs)
        """
        # Simplified verb extraction (could use spaCy/NLTK for better accuracy)

        # Common past tense patterns
        past_patterns = [
            r'\b\w+ed\b',  # walked, talked
            r'\b(was|were|had|did|went|came|saw|said|felt|thought|knew|gave|took|made|got)\b'
        ]

        # Common present tense patterns
        present_patterns = [
            r'\b\w+s\b(?!\')',  # walks, talks (3rd person singular)
            r'\b(is|are|am|has|have|do|does|go|come|see|say|feel|think|know|give|take|make|get)\b'
        ]

        past_verbs = []
        for pattern in past_patterns:
            past_verbs.extend(re.findall(pattern, text, re.IGNORECASE))

        present_verbs = []
        for pattern in present_patterns:
            present_verbs.extend(re.findall(pattern, text, re.IGNORECASE))

        return past_verbs, present_verbs

    def _is_whitelisted(self, text: str, match_position: int, matched_text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a present tense match is in a whitelisted context.

        Returns:
            (is_whitelisted, whitelist_type)
        """
        # Priority 1: Structural exemptions

        # Check if in dialogue
        if self._is_in_dialogue(text, match_position):
            return (True, "dialogue")

        # Check if in italics/thoughts
        if self._is_in_italics(text, match_position):
            return (True, "italicized_thought")

        # Check if in meta-narrative (brackets/parentheses)
        if self._is_in_meta_text(text, match_position):
            return (True, "meta_narrative")

        # Priority 2: Semantic exemptions via regex patterns

        exception_rules = self.rules.get('exception_rules', {})

        # Universal truths
        if 'universal_truths' in exception_rules:
            pattern = exception_rules['universal_truths'].get('pattern', '')
            if pattern and re.search(pattern, text, re.IGNORECASE):
                # Check if our match is within this pattern's span
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    if match.start() <= match_position <= match.end():
                        return (True, "universal_truth")

        # Definitions
        if 'definitions' in exception_rules:
            pattern = exception_rules['definitions'].get('pattern', '')
            if pattern:
                # Check if matched_text is part of a definition phrase
                context_window = text[max(0, match_position-20):match_position+len(matched_text)+20]
                if re.search(pattern, context_window, re.IGNORECASE):
                    return (True, "definition")

        # Conditionals
        if 'conditionals' in exception_rules:
            pattern = exception_rules['conditionals'].get('pattern', '')
            if pattern and re.search(pattern, text, re.IGNORECASE):
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    if match.start() <= match_position <= match.end():
                        return (True, "conditional")

        # Cultural notes
        if 'cultural_notes' in exception_rules:
            pattern = exception_rules['cultural_notes'].get('pattern', '')
            if pattern and re.search(pattern, text, re.IGNORECASE):
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    if match.start() <= match_position <= match.end():
                        return (True, "cultural_note")

        # Performative verbs
        if 'performative_verbs' in exception_rules:
            pattern = exception_rules['performative_verbs'].get('pattern', '')
            if pattern:
                context_window = text[max(0, match_position-50):match_position+len(matched_text)+50]
                if re.search(pattern, context_window, re.IGNORECASE):
                    return (True, "performative_verb")

        # Modal perfects (must have, would have, etc.)
        if 'modal_perfects' in exception_rules:
            pattern = exception_rules['modal_perfects'].get('pattern', '')
            if pattern:
                context_window = text[max(0, match_position-15):match_position+len(matched_text)+5]
                if re.search(pattern, context_window, re.IGNORECASE):
                    return (True, "modal_perfect")

        # Infinitive constructions (to do, to have, etc.)
        if 'infinitive_constructions' in exception_rules:
            pattern = exception_rules['infinitive_constructions'].get('pattern', '')
            if pattern:
                context_window = text[max(0, match_position-5):match_position+len(matched_text)+5]
                if re.search(pattern, context_window, re.IGNORECASE):
                    return (True, "infinitive")

        # Quoted internal monologue with ellipsis
        if 'quoted_internal_monologue' in exception_rules:
            pattern = exception_rules['quoted_internal_monologue'].get('pattern', '')
            if pattern:
                context_window = text[max(0, match_position-50):match_position+len(matched_text)+50]
                if re.search(pattern, context_window, re.IGNORECASE):
                    return (True, "internal_monologue")

        # Timeless character traits (gives off vibes, etc.)
        if 'timeless_character_traits' in exception_rules:
            pattern = exception_rules['timeless_character_traits'].get('pattern', '')
            if pattern:
                context_window = text[max(0, match_position-5):match_position+len(matched_text)+20]
                if re.search(pattern, context_window, re.IGNORECASE):
                    return (True, "timeless_trait")

        return (False, None)

    def _is_in_dialogue(self, text: str, position: int) -> bool:
        """Check if position is inside quotation marks."""
        # Count quotes before position
        before = text[:position]
        quote_count = before.count('"')
        return quote_count % 2 == 1

    def _is_in_italics(self, text: str, position: int) -> bool:
        """Check if position is inside italic markers."""
        before = text[:position]
        asterisk_count = before.count('*')
        underscore_count = before.count('_')
        return (asterisk_count % 2 == 1) or (underscore_count % 2 == 1)

    def _is_in_meta_text(self, text: str, position: int) -> bool:
        """Check if position is inside brackets [] or parentheses ()."""
        before = text[:position]
        bracket_count = before.count('[') - before.count(']')
        paren_count = before.count('(') - before.count(')')
        return bracket_count > 0 or paren_count > 0

    def validate_file(self, file_path: Path) -> TenseReport:
        """
        Validate a single markdown file for tense consistency.

        Args:
            file_path: Path to the EN markdown file

        Returns:
            TenseReport with all violations found
        """
        logger.info(f"Validating tense consistency: {file_path.name}")

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        report = TenseReport(
            file_path=str(file_path),
            total_lines=len(lines),
            total_violations=0,
            violations_by_severity={'high': 0, 'medium': 0, 'low': 0},
            violations_by_rule={}
        )

        # Process by paragraph
        current_paragraph = []
        para_start_line = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped:
                # End of paragraph
                if current_paragraph:
                    violations = self._validate_paragraph(
                        '\n'.join(current_paragraph),
                        para_start_line
                    )
                    report.violations.extend(violations)
                    current_paragraph = []
            else:
                if not current_paragraph:
                    para_start_line = line_num
                current_paragraph.append(line)

        # Handle last paragraph
        if current_paragraph:
            violations = self._validate_paragraph(
                '\n'.join(current_paragraph),
                para_start_line
            )
            report.violations.extend(violations)

        # Aggregate statistics
        report.total_violations = len(report.violations)
        for v in report.violations:
            report.violations_by_severity[v.severity] = \
                report.violations_by_severity.get(v.severity, 0) + 1
            report.violations_by_rule[v.rule_id] = \
                report.violations_by_rule.get(v.rule_id, 0) + 1

        return report

    def _validate_paragraph(self, paragraph: str, start_line: int) -> List[TenseViolation]:
        """Validate a single paragraph for tense consistency."""
        violations = []

        # Skip empty or very short paragraphs
        if len(paragraph.strip()) < 20:
            return violations

        # Extract narrative text (exclude dialogue)
        narrative_text = re.sub(r'"[^"]*"', '', paragraph)

        # Analyze verb tense distribution
        past_verbs, present_verbs = self._extract_verbs(narrative_text)
        total_verbs = len(past_verbs) + len(present_verbs)

        if total_verbs == 0:
            return violations

        past_ratio = len(past_verbs) / total_verbs if total_verbs > 0 else 0

        # If predominantly past tense (>70%), flag present tense violations
        if past_ratio > 0.7:
            violations.extend(self._check_present_in_past(
                paragraph, start_line, past_ratio
            ))

        # Run pattern-based checks
        patterns = self.rules.get('patterns', [])
        for rule in patterns:
            violations.extend(self._check_pattern_rule(
                paragraph, start_line, rule
            ))

        return violations

    def _check_present_in_past(
        self, paragraph: str, start_line: int, past_ratio: float
    ) -> List[TenseViolation]:
        """Check for present tense verbs in predominantly past-tense paragraph."""
        violations = []

        # Find present tense verbs
        present_pattern = r'\b(is|are|am|has|have|does|do|goes|comes|sees|says|feels|thinks|knows|gives|takes|makes|gets)\b'

        for match in re.finditer(present_pattern, paragraph, re.IGNORECASE):
            position = match.start()
            matched_text = match.group(0)

            # Check whitelist
            is_whitelisted, whitelist_type = self._is_whitelisted(paragraph, position, matched_text)
            if is_whitelisted:
                logger.debug(f"Skipping '{matched_text}' at position {position}: whitelisted as {whitelist_type}")
                continue

            context = paragraph[max(0, position-50):min(len(paragraph), position+50)]

            violations.append(TenseViolation(
                rule_id="present_in_past_narrative",
                line_number=start_line,
                matched_text=matched_text,
                paragraph_context=context,
                issue_description=f"Present tense '{matched_text}' in past-tense paragraph (past_ratio={past_ratio:.2f})",
                confidence=past_ratio,
                severity="high" if past_ratio > 0.85 else "medium",
                auto_fix_eligible=False
            ))

        return violations

    def _check_pattern_rule(
        self, paragraph: str, start_line: int, rule: Dict
    ) -> List[TenseViolation]:
        """Check a specific pattern rule against the paragraph."""
        violations = []
        rule_id = rule.get('id', 'unknown')
        patterns = rule.get('patterns', [])
        fixes = rule.get('fixes', {})
        severity = rule.get('severity', 'medium')
        auto_fix = rule.get('auto_fix_eligible', False)
        confidence = rule.get('confidence_threshold', 0.7)

        for pattern in patterns:
            try:
                for match in re.finditer(pattern, paragraph, re.IGNORECASE):
                    matched_text = match.group(0)
                    position = match.start()

                    # Check whitelist before flagging
                    is_whitelisted, whitelist_type = self._is_whitelisted(paragraph, position, matched_text)
                    if is_whitelisted:
                        logger.debug(f"Skipping '{matched_text}' for rule {rule_id}: whitelisted as {whitelist_type}")
                        continue

                    suggested_fix = fixes.get(matched_text.lower()) if isinstance(fixes, dict) else None

                    violations.append(TenseViolation(
                        rule_id=rule_id,
                        line_number=start_line,
                        matched_text=matched_text,
                        paragraph_context=paragraph[:200],  # Limit context to 200 chars
                        issue_description=rule.get('description', 'Tense inconsistency'),
                        suggested_fix=suggested_fix,
                        confidence=confidence,
                        severity=severity,
                        auto_fix_eligible=auto_fix and suggested_fix is not None
                    ))
            except re.error as e:
                logger.warning(f"Invalid regex pattern in rule {rule_id}: {pattern} - {e}")
                continue

        return violations

    def generate_report(self, report: TenseReport, output_path: Path):
        """Generate JSON and Markdown reports."""
        # JSON report
        json_path = output_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # Markdown report
        md_path = output_path.with_suffix('.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# Tense Consistency Validation Report\n\n")
            f.write(f"**File:** `{report.file_path}`\n\n")
            f.write(f"**Total Violations:** {report.total_violations}\n\n")

            f.write("## Violations by Severity\n\n")
            for severity, count in sorted(report.violations_by_severity.items()):
                f.write(f"- **{severity.upper()}**: {count}\n")

            f.write("\n## Violations by Rule\n\n")
            for rule, count in sorted(report.violations_by_rule.items(), key=lambda x: -x[1]):
                f.write(f"- `{rule}`: {count}\n")

            f.write("\n## Detailed Violations\n\n")
            for v in report.violations:
                f.write(f"### Line {v.line_number}: {v.rule_id}\n\n")
                f.write(f"**Matched:** `{v.matched_text}`\n\n")
                f.write(f"**Issue:** {v.issue_description}\n\n")
                if v.suggested_fix:
                    f.write(f"**Suggested Fix:** `{v.suggested_fix}`\n\n")
                f.write(f"**Confidence:** {v.confidence:.2f} | **Severity:** {v.severity}\n\n")
                f.write("---\n\n")

        logger.info(f"Reports generated: {json_path}, {md_path}")

    def validate_volume(self, volume_dir: Path, output_dir: Optional[Path] = None) -> Dict[str, TenseReport]:
        """
        Validate all chapter files in a volume directory.

        Args:
            volume_dir: Directory containing EN chapter files
            output_dir: Directory to save reports (defaults to volume_dir)

        Returns:
            Dict mapping file names to their TenseReports
        """
        if output_dir is None:
            output_dir = volume_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        reports = {}
        chapter_files = sorted(volume_dir.glob("CHAPTER_*.md"))

        logger.info(f"Validating {len(chapter_files)} chapters in {volume_dir.name}")

        for chapter_file in chapter_files:
            report = self.validate_file(chapter_file)
            reports[chapter_file.name] = report

            # Generate individual report
            report_path = output_dir / f"TENSE_REPORT_{chapter_file.stem}"
            self.generate_report(report, report_path)

        # Generate aggregate report
        self._generate_aggregate_report(reports, output_dir / "TENSE_REPORT_AGGREGATE")

        return reports

    def _generate_aggregate_report(self, reports: Dict[str, TenseReport], output_path: Path):
        """Generate an aggregate report for all chapters."""
        total_violations = sum(r.total_violations for r in reports.values())
        total_lines = sum(r.total_lines for r in reports.values())

        # Aggregate by severity
        agg_severity = {'high': 0, 'medium': 0, 'low': 0}
        for report in reports.values():
            for severity, count in report.violations_by_severity.items():
                agg_severity[severity] = agg_severity.get(severity, 0) + count

        # Aggregate by rule
        agg_rules = {}
        for report in reports.values():
            for rule, count in report.violations_by_rule.items():
                agg_rules[rule] = agg_rules.get(rule, 0) + count

        # Markdown report
        md_path = output_path.with_suffix('.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write("# Aggregate Tense Consistency Report\n\n")
            f.write(f"**Total Chapters:** {len(reports)}\n")
            f.write(f"**Total Lines:** {total_lines}\n")
            f.write(f"**Total Violations:** {total_violations}\n")
            f.write(f"**Violations per 1000 lines:** {total_violations / total_lines * 1000:.2f}\n\n")

            f.write("## Violations by Severity\n\n")
            for severity, count in sorted(agg_severity.items()):
                f.write(f"- **{severity.upper()}**: {count}\n")

            f.write("\n## Violations by Rule\n\n")
            for rule, count in sorted(agg_rules.items(), key=lambda x: -x[1]):
                f.write(f"- `{rule}`: {count}\n")

            f.write("\n## Per-Chapter Breakdown\n\n")
            for filename, report in sorted(reports.items()):
                f.write(f"### {filename}\n\n")
                f.write(f"- Total Violations: {report.total_violations}\n")
                f.write(f"- By Severity: {report.violations_by_severity}\n")
                f.write(f"- Top Rules: {dict(sorted(report.violations_by_rule.items(), key=lambda x: -x[1])[:3])}\n\n")

        logger.info(f"Aggregate report generated: {md_path}")
