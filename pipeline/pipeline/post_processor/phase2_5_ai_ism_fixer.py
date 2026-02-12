"""
Phase 2.5: Technical Quick-Fix - AI-ism Purple Prose Removal
=============================================================

Lightweight post-processing phase inserted between Phase 2 (Translation) and Phase 3 (QC).

Purpose:
- Auto-fix high-confidence AI-ism patterns (≥0.95 confidence)
- Flag medium-confidence patterns for Phase 3 review (0.7-0.9 confidence)
- Minimal latency impact (<1s per chapter)

Integration Point:
- Runs after chapter translation completes
- Before rich metadata cache
- Operates on EN markdown files in-place

Configuration:
- Uses english_grammar_validation_t1.json v1.3 Phase 2 blocklist
- Auto-fix threshold: 0.95
- Review threshold: 0.7-0.9
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AIismFix:
    """Record of a single AI-ism fix."""
    pattern_id: str
    line_number: int
    original: str
    fixed: str
    confidence: float
    auto_applied: bool


@dataclass
class Phase25Report:
    """Phase 2.5 processing report."""
    chapter_id: str
    fixes_applied: int = 0
    fixes_flagged: int = 0
    patterns_detected: Dict[str, int] = field(default_factory=dict)
    fixes: List[AIismFix] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'chapter_id': self.chapter_id,
            'fixes_applied': self.fixes_applied,
            'fixes_flagged': self.fixes_flagged,
            'patterns_detected': self.patterns_detected,
            'fixes': [
                {
                    'pattern_id': f.pattern_id,
                    'line_number': f.line_number,
                    'original': f.original,
                    'fixed': f.fixed,
                    'confidence': f.confidence,
                    'auto_applied': f.auto_applied
                }
                for f in self.fixes
            ]
        }


class Phase25AIismFixer:
    """
    Phase 2.5: Lightweight AI-ism technical fix agent.

    Operates on completed EN chapter files with minimal latency.
    """

    def __init__(self, config_path: Optional[Path] = None, dry_run: bool = False):
        """
        Initialize Phase 2.5 AI-ism fixer.

        Args:
            config_path: Path to english_grammar_validation_t1.json
            dry_run: If True, detect but don't apply fixes
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "english_grammar_validation_t1.json"

        self.config_path = config_path
        self.dry_run = dry_run

        # Load AI-ism patterns
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.patterns = config['validation_categories']['ai_ism_purple_prose']['patterns']

        # Separate high-confidence (auto-fix) from medium-confidence (flag)
        self.auto_fix_patterns = [p for p in self.patterns if p.get('confidence_threshold', 0) >= 0.95]
        self.review_patterns = [p for p in self.patterns if 0.7 <= p.get('confidence_threshold', 0) < 0.95]

        logger.info(
            f"Phase 2.5 initialized: {len(self.auto_fix_patterns)} auto-fix, "
            f"{len(self.review_patterns)} review patterns"
        )

    def process_chapter(self, chapter_path: Path) -> Phase25Report:
        """
        Process a single chapter EN markdown file.

        Args:
            chapter_path: Path to CHAPTER_XX_EN.md

        Returns:
            Phase25Report with fixes applied and/or flagged
        """
        chapter_id = chapter_path.stem.replace('_EN', '')

        logger.info(f"Phase 2.5: Processing {chapter_id}")

        # Read chapter
        with open(chapter_path, 'r', encoding='utf-8') as f:
            original_text = f.read()

        report = Phase25Report(chapter_id=chapter_id)
        fixed_text = original_text

        # Step 1: Apply high-confidence auto-fixes
        for pattern_def in self.auto_fix_patterns:
            fixed_text, fixes = self._apply_pattern_fix(
                text=fixed_text,
                pattern_def=pattern_def,
                auto_apply=True
            )

            if fixes:
                report.fixes.extend(fixes)
                report.fixes_applied += len(fixes)
                report.patterns_detected[pattern_def['id']] = len(fixes)

                logger.info(
                    f"  Auto-fixed {len(fixes)} instances of '{pattern_def['id']}'"
                )

        # Step 2: Flag medium-confidence patterns for review
        for pattern_def in self.review_patterns:
            _, flags = self._apply_pattern_fix(
                text=fixed_text,
                pattern_def=pattern_def,
                auto_apply=False
            )

            if flags:
                report.fixes.extend(flags)
                report.fixes_flagged += len(flags)
                report.patterns_detected[pattern_def['id']] = len(flags)

                logger.info(
                    f"  Flagged {len(flags)} instances of '{pattern_def['id']}' for review"
                )

        # Write fixed text (if not dry run and changes made)
        if not self.dry_run and fixed_text != original_text:
            # Create backup
            backup_path = chapter_path.with_suffix('.md.phase2_backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_text)

            # Write fixed version
            with open(chapter_path, 'w', encoding='utf-8') as f:
                f.write(fixed_text)

            logger.info(
                f"  Applied {report.fixes_applied} fixes to {chapter_id} "
                f"(backup: {backup_path.name})"
            )

        return report

    def _apply_pattern_fix(
        self,
        text: str,
        pattern_def: Dict,
        auto_apply: bool
    ) -> Tuple[str, List[AIismFix]]:
        """
        Apply or flag a single AI-ism pattern.

        Args:
            text: Input text
            pattern_def: Pattern definition from config
            auto_apply: If True, apply fixes; if False, only flag

        Returns:
            (fixed_text, list_of_fixes)
        """
        pattern_id = pattern_def['id']
        pattern = pattern_def['pattern']
        confidence = pattern_def.get('confidence_threshold', 0.7)
        fix_suggestions = pattern_def.get('fix_suggestions', {})

        fixes: List[AIismFix] = []
        fixed_text = text

        # Find all matches
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(0)
            position = match.start()

            # Calculate line number
            line_number = text[:position].count('\n') + 1

            # Get fix suggestion
            suggested_fix = fix_suggestions.get(matched_text.lower())

            if auto_apply and suggested_fix:
                # Apply fix via regex substitution
                fixed_text = fixed_text.replace(matched_text, suggested_fix, 1)

                fixes.append(AIismFix(
                    pattern_id=pattern_id,
                    line_number=line_number,
                    original=matched_text,
                    fixed=suggested_fix,
                    confidence=confidence,
                    auto_applied=True
                ))
            else:
                # Flag for review
                fixes.append(AIismFix(
                    pattern_id=pattern_id,
                    line_number=line_number,
                    original=matched_text,
                    fixed=suggested_fix or "(manual review required)",
                    confidence=confidence,
                    auto_applied=False
                ))

        return fixed_text, fixes

    def process_batch(self, chapter_paths: List[Path]) -> Dict[str, Phase25Report]:
        """
        Process multiple chapters in batch.

        Args:
            chapter_paths: List of paths to EN chapter files

        Returns:
            Dict mapping chapter_id to Phase25Report
        """
        reports = {}

        for chapter_path in chapter_paths:
            try:
                report = self.process_chapter(chapter_path)
                reports[report.chapter_id] = report
            except Exception as e:
                logger.error(f"Failed to process {chapter_path.name}: {e}")

        return reports

    def generate_summary_report(
        self,
        reports: Dict[str, Phase25Report],
        output_path: Path
    ):
        """Generate consolidated JSON report."""
        summary = {
            'phase': '2.5_ai_ism_technical_fix',
            'chapters_processed': len(reports),
            'total_fixes_applied': sum(r.fixes_applied for r in reports.values()),
            'total_flags_for_review': sum(r.fixes_flagged for r in reports.values()),
            'chapters': {
                chapter_id: report.to_dict()
                for chapter_id, report in reports.items()
            }
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Phase 2.5 summary report written to {output_path}")


# Integration hook for pipeline
def integrate_phase25(en_output_dir: Path, dry_run: bool = False) -> Dict[str, Phase25Report]:
    """
    Integration point for main pipeline.

    Call this after Phase 2 (Translation) completes, before Phase 3 (QC).

    Args:
        en_output_dir: Directory containing CHAPTER_*_EN.md files
        dry_run: If True, detect but don't apply fixes

    Returns:
        Dict of chapter_id -> Phase25Report
    """
    logger.info("=" * 60)
    logger.info("Phase 2.5: AI-ism Technical Quick-Fix")
    logger.info("=" * 60)

    # Initialize fixer
    fixer = Phase25AIismFixer(dry_run=dry_run)

    # Find all EN chapter files
    chapter_paths = sorted(en_output_dir.glob('CHAPTER_*_EN.md'))

    if not chapter_paths:
        logger.warning(f"No EN chapters found in {en_output_dir}")
        return {}

    # Process all chapters
    reports = fixer.process_batch(chapter_paths)

    # Generate summary report
    report_path = en_output_dir.parent / 'phase2_5_ai_ism_report.json'
    fixer.generate_summary_report(reports, report_path)

    # Log summary
    total_applied = sum(r.fixes_applied for r in reports.values())
    total_flagged = sum(r.fixes_flagged for r in reports.values())

    logger.info(f"Phase 2.5 complete: {total_applied} fixes applied, {total_flagged} flagged for review")
    logger.info("=" * 60)

    return reports


if __name__ == '__main__':
    # CLI entry point for standalone execution
    import argparse

    parser = argparse.ArgumentParser(description='Phase 2.5: AI-ism Technical Quick-Fix')
    parser.add_argument('--input-dir', type=Path, required=True, help='Directory with EN chapter files')
    parser.add_argument('--dry-run', action='store_true', help='Detect but do not apply fixes')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    integrate_phase25(args.input_dir, dry_run=args.dry_run)
