"""
English Grammar Validator (Tier 1)
Mechanical grammar validation for translated English output.
Detects possessive errors, article issues, subject-verb agreement, etc.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class GrammarViolation:
    """Represents a single grammar violation found."""
    rule_id: str
    category: str
    severity: str  # 'high', 'medium', 'low'
    line_number: int
    matched_text: str
    issue_description: str
    suggested_fix: Optional[str] = None
    confidence: float = 1.0
    context: str = ""  # Surrounding text for review


@dataclass
class GrammarReport:
    """Summary report of grammar validation."""
    file_path: str
    total_lines: int
    total_violations: int
    violations_by_severity: Dict[str, int] = field(default_factory=dict)
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    violations: List[GrammarViolation] = field(default_factory=list)
    auto_fixed: int = 0
    flagged_for_review: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'violations': [asdict(v) for v in self.violations]
        }


class GrammarValidator:
    """Validates English grammar using tier-1 validation rules."""

    def __init__(self, config_path: Optional[Path] = None, auto_fix: bool = False):
        """
        Initialize Grammar Validator.

        Args:
            config_path: Path to english_grammar_validation_t1.json
            auto_fix: Whether to automatically fix high-confidence errors
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "english_grammar_validation_t1.json"

        self.config_path = config_path
        self.auto_fix = auto_fix
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        """Load validation rules from JSON config."""
        if not self.config_path.exists():
            logger.warning(f"Grammar validation config not found: {self.config_path}")
            return {}

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def validate_file(self, file_path: Path) -> GrammarReport:
        """
        Validate a single markdown file.

        Args:
            file_path: Path to the EN markdown file

        Returns:
            GrammarReport with all violations found
        """
        logger.info(f"Validating grammar: {file_path.name}")

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        report = GrammarReport(
            file_path=str(file_path),
            total_lines=len(lines),
            total_violations=0,
            violations_by_severity={'high': 0, 'medium': 0, 'low': 0},
            violations_by_category={}
        )

        # Run all validation categories
        violations = []
        violations.extend(self._check_possessive_errors(lines))
        violations.extend(self._check_article_errors(lines))
        violations.extend(self._check_subject_verb_agreement(lines))
        violations.extend(self._check_pronoun_errors(lines))
        violations.extend(self._check_contraction_errors(lines))
        violations.extend(self._check_double_negatives(lines))

        # Aggregate results
        for violation in violations:
            report.violations.append(violation)
            report.total_violations += 1
            report.violations_by_severity[violation.severity] += 1
            report.violations_by_category[violation.category] = \
                report.violations_by_category.get(violation.category, 0) + 1

        # Auto-fix eligible violations if enabled
        if self.auto_fix and report.total_violations > 0:
            report.auto_fixed = self._apply_auto_fixes(file_path, violations)

        # Count flagged for review
        report.flagged_for_review = sum(
            1 for v in violations if v.confidence < 0.9
        )

        logger.info(f"  Found {report.total_violations} violations "
                   f"(high: {report.violations_by_severity['high']}, "
                   f"medium: {report.violations_by_severity['medium']}, "
                   f"low: {report.violations_by_severity['low']})")

        if self.auto_fix and report.auto_fixed > 0:
            logger.info(f"  Auto-fixed: {report.auto_fixed} violations")

        return report

    def _check_possessive_errors(self, lines: List[str]) -> List[GrammarViolation]:
        """Check for missing possessive apostrophes."""
        violations = []
        rules = self.rules.get('validation_categories', {}).get('possessive_errors', {})
        if not rules:
            return violations

        # Pattern: Name + space + body part/possession (missing 's)
        pattern = re.compile(
            r'\b([A-Z][a-z]+)\s+(eyes|face|hand|voice|expression|smile|heart|mind|'
            r'mother|father|brother|sister|friend|family|home|room|book|bag|phone|'
            r'car|body|hair|skin|lips|arms|legs|feet|words|question|answer|response|'
            r'reaction|gesture|movement|action|decision|choice|thought|memory|dream|'
            r'hope|wish|fear|anger|sadness|happiness|joy|pain|suffering|death|life|'
            r'love|hate|wide)\b'
        )

        for line_num, line in enumerate(lines, start=1):
            # Skip dialogue and italics markers
            if line.strip().startswith('"') or line.strip().startswith('*'):
                continue

            matches = pattern.finditer(line)
            for match in matches:
                name, possession = match.groups()

                # Exclude pronouns, articles, and determiners that should NEVER have possessive 's
                excluded_words = ['Her', 'His', 'My', 'Your', 'Their', 'Our', 'Its', 'The',
                                  'This', 'That', 'These', 'Those', 'Some', 'Any', 'Each',
                                  'Every', 'Many', 'Much', 'Few', 'Several', 'All', 'Both',
                                  'No', 'None', 'Another', 'Other', 'Such', 'What', 'Which',
                                  'Whose', 'Black', 'White', 'Red', 'Blue', 'Green', 'Golden',
                                  'Silver', 'To', 'From', 'With', 'Without', 'For', 'Against']
                if name in excluded_words:
                    continue

                # Avoid false positives: "Maria said" vs "Maria voice"
                if possession in ['said', 'asked', 'replied', 'answered', 'whispered', 'shouted']:
                    continue

                violations.append(GrammarViolation(
                    rule_id='missing_possessive_noun',
                    category='possessive_errors',
                    severity='high',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description=f"Missing possessive: should be '{name}'s {possession}'",
                    suggested_fix=f"{name}'s {possession}",
                    confidence=0.9,
                    context=line.strip()[:100]
                ))

        return violations

    def _check_article_errors(self, lines: List[str]) -> List[GrammarViolation]:
        """Check for a/an usage errors."""
        violations = []

        # Pattern: "a" before vowel sound
        pattern = re.compile(r'\ba\s+([aeiou]\w+)', re.IGNORECASE)

        for line_num, line in enumerate(lines, start=1):
            matches = pattern.finditer(line)
            for match in matches:
                word = match.group(1)

                # Exceptions: "a user" (yoo sound), "a one-time" (w sound), "a European" (yoo sound)
                if word.lower().startswith(('user', 'one', 'europ', 'univers', 'uniform')):
                    continue

                violations.append(GrammarViolation(
                    rule_id='a_vs_an_vowel_sound',
                    category='article_errors',
                    severity='medium',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description=f"Should use 'an' before '{word}'",
                    suggested_fix=f"an {word}",
                    confidence=0.85,
                    context=line.strip()[:100]
                ))

        return violations

    def _check_subject_verb_agreement(self, lines: List[str]) -> List[GrammarViolation]:
        """Check for subject-verb agreement errors."""
        violations = []

        # Singular subject + plural verb
        pattern1 = re.compile(r'\b(He|She|It|[A-Z][a-z]+)\s+(are|were|have|do)\b')

        # Plural subject + singular verb
        pattern2 = re.compile(r'\b(They|We)\s+(is|was|has|does)\b')

        for line_num, line in enumerate(lines, start=1):
            # Skip dialogue (may intentionally use non-standard grammar)
            if line.strip().startswith('"'):
                continue

            matches1 = pattern1.finditer(line)
            for match in matches1:
                subject, verb = match.groups()
                fix_map = {'are': 'is', 'were': 'was', 'have': 'has', 'do': 'does'}

                violations.append(GrammarViolation(
                    rule_id='singular_subject_plural_verb',
                    category='subject_verb_agreement',
                    severity='high',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description=f"Singular subject '{subject}' requires singular verb",
                    suggested_fix=f"{subject} {fix_map[verb]}",
                    confidence=0.95,
                    context=line.strip()[:100]
                ))

            matches2 = pattern2.finditer(line)
            for match in matches2:
                subject, verb = match.groups()
                fix_map = {'is': 'are', 'was': 'were', 'has': 'have', 'does': 'do'}

                violations.append(GrammarViolation(
                    rule_id='plural_subject_singular_verb',
                    category='subject_verb_agreement',
                    severity='high',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description=f"Plural subject '{subject}' requires plural verb",
                    suggested_fix=f"{subject} {fix_map[verb]}",
                    confidence=0.95,
                    context=line.strip()[:100]
                ))

        return violations

    def _check_pronoun_errors(self, lines: List[str]) -> List[GrammarViolation]:
        """Check for pronoun case errors."""
        violations = []

        # Object pronoun as subject: "me is" / "him are"
        pattern = re.compile(r'\b(me|him|her|us|them)\s+(is|are|was|were|am|can|will|would|should|could|have|has|had)\b', re.IGNORECASE)

        for line_num, line in enumerate(lines, start=1):
            matches = pattern.finditer(line)
            for match in matches:
                pronoun, verb = match.groups()
                fix_map = {'me': 'I', 'him': 'he', 'her': 'she', 'us': 'we', 'them': 'they'}

                violations.append(GrammarViolation(
                    rule_id='object_pronoun_as_subject',
                    category='pronoun_errors',
                    severity='medium',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description=f"Object pronoun '{pronoun}' used as subject",
                    suggested_fix=f"{fix_map[pronoun.lower()]} {verb}",
                    confidence=0.85,
                    context=line.strip()[:100]
                ))

        return violations

    def _check_contraction_errors(self, lines: List[str]) -> List[GrammarViolation]:
        """Check for malformed contractions."""
        violations = []

        # Pattern: "could of" instead of "could have"
        pattern = re.compile(r'\b(could|would|should|must|might|may)\s+of\b', re.IGNORECASE)

        for line_num, line in enumerate(lines, start=1):
            matches = pattern.finditer(line)
            for match in matches:
                modal = match.group(1)

                violations.append(GrammarViolation(
                    rule_id='malformed_contraction',
                    category='contraction_errors',
                    severity='medium',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description=f"Incorrect '{modal} of' - should be '{modal} have'",
                    suggested_fix=f"{modal} have",
                    confidence=0.95,
                    context=line.strip()[:100]
                ))

        return violations

    def _check_double_negatives(self, lines: List[str]) -> List[GrammarViolation]:
        """Check for unintentional double negatives."""
        violations = []

        pattern = re.compile(
            r'\b(don\'t|doesn\'t|didn\'t|can\'t|couldn\'t|won\'t|wouldn\'t|shouldn\'t|'
            r'isn\'t|aren\'t|wasn\'t|weren\'t)\s+\w+\s+(nothing|nobody|nowhere|never|no one|none)\b',
            re.IGNORECASE
        )

        for line_num, line in enumerate(lines, start=1):
            # Double negatives more likely in dialogue (character voice)
            in_dialogue = line.strip().startswith('"')

            matches = pattern.finditer(line)
            for match in matches:
                violations.append(GrammarViolation(
                    rule_id='double_negative_standard',
                    category='double_negatives',
                    severity='low' if in_dialogue else 'medium',
                    line_number=line_num,
                    matched_text=match.group(0),
                    issue_description="Double negative creates unintended positive meaning",
                    suggested_fix="Replace second negative with 'any-' form (anything, anybody, etc.)",
                    confidence=0.7 if in_dialogue else 0.85,
                    context=line.strip()[:100]
                ))

        return violations

    def _apply_auto_fixes(self, file_path: Path, violations: List[GrammarViolation]) -> int:
        """
        Apply automatic fixes for high-confidence violations.

        Returns:
            Number of fixes applied
        """
        # Only fix violations with confidence >= 0.9
        fixable = [v for v in violations if v.confidence >= 0.9 and v.suggested_fix]

        if not fixable:
            return 0

        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        fixes_applied = 0

        # Group fixes by line number and apply in reverse order to preserve line numbers
        fixes_by_line: Dict[int, List[Tuple[str, str]]] = {}
        for violation in fixable:
            if violation.line_number not in fixes_by_line:
                fixes_by_line[violation.line_number] = []
            fixes_by_line[violation.line_number].append((violation.matched_text, violation.suggested_fix))

        # Apply fixes
        for line_num in sorted(fixes_by_line.keys(), reverse=True):
            line_idx = line_num - 1
            if 0 <= line_idx < len(lines):
                for old_text, new_text in fixes_by_line[line_num]:
                    if old_text in lines[line_idx]:
                        lines[line_idx] = lines[line_idx].replace(old_text, new_text, 1)
                        fixes_applied += 1

        # Write back
        if fixes_applied > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            logger.info(f"  Applied {fixes_applied} automatic grammar fixes")

        return fixes_applied

    def validate_volume(self, work_dir: Path) -> Dict[str, GrammarReport]:
        """
        Validate all EN chapter files in a volume.

        Args:
            work_dir: Path to volume working directory

        Returns:
            Dict mapping file names to GrammarReport objects
        """
        en_dir = work_dir / "EN"
        if not en_dir.exists():
            logger.warning(f"EN directory not found: {en_dir}")
            return {}

        results = {}
        chapter_files = sorted(en_dir.glob("CHAPTER_*_EN.md"))

        for chapter_file in chapter_files:
            report = self.validate_file(chapter_file)
            results[chapter_file.name] = report

        # Save aggregate report
        self._save_aggregate_report(work_dir, results)

        return results

    def _save_aggregate_report(self, work_dir: Path, results: Dict[str, GrammarReport]) -> None:
        """Save aggregate grammar validation report to JSON."""
        report_path = work_dir / "audits" / "grammar_validation_report.json"
        report_path.parent.mkdir(exist_ok=True)

        aggregate = {
            "validation_timestamp": str(Path(__file__).stat().st_mtime),
            "total_files": len(results),
            "total_violations": sum(r.total_violations for r in results.values()),
            "auto_fixed": sum(r.auto_fixed for r in results.values()),
            "files": {name: report.to_dict() for name, report in results.items()}
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(aggregate, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved grammar validation report: {report_path}")
