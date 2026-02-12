#!/usr/bin/env python3
"""
Stage 3 Refinement Validator Agent (Hybrid Approach)
=====================================================

Auto-fixes AI-isms via Gemini re-injection with targeted context.
Flags narration length violations for human review (no auto-fix).

Architecture:
- AI-ism Removal: Gemini Flash with focused prompt (high confidence patterns)
- Length Flagging: Regex-based detection, JSON report generation
- Output: Fixed EN markdown + comprehensive JSON report

Usage:
    python refinement_validator.py --input CHAPTER_01_EN.md --output CHAPTER_01_EN_REFINED.md
    python refinement_validator.py --batch EN/ --output-dir EN_REFINED/
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import google.generativeai as genai
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.common.gemini_client import GeminiClient


@dataclass
class AIismViolation:
    """Detected AI-ism purple prose pattern."""
    pattern_id: str
    line_number: int
    original_text: str
    context_before: str
    context_after: str
    severity: str
    confidence: float
    suggested_fix: Optional[str] = None
    auto_fixed: bool = False


@dataclass
class LengthViolation:
    """Narration sentence length violation (flagged for review)."""
    line_number: int
    sentence: str
    word_count: int
    violation_type: str  # 'soft_target' (12-14w) or 'hard_cap' (>15w)
    severity: str
    suggested_action: str


@dataclass
class RefinementReport:
    """Complete refinement validation report."""
    file_path: str
    timestamp: str
    total_lines: int

    # AI-ism stats
    ai_isms_detected: int
    ai_isms_auto_fixed: int
    ai_isms_remaining: int
    ai_ism_violations: List[AIismViolation] = field(default_factory=list)

    # Length stats
    length_violations_detected: int
    length_soft_target_violations: int
    length_hard_cap_violations: int
    length_violations: List[LengthViolation] = field(default_factory=list)

    # Summary
    overall_grade: str = ""
    improvements_made: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'ai_ism_violations': [asdict(v) for v in self.ai_ism_violations],
            'length_violations': [asdict(v) for v in self.length_violations]
        }


class RefinementValidator:
    """
    Stage 3 Refinement Validator Agent.

    Hybrid approach:
    1. Auto-fix AI-isms via Gemini re-injection (intelligent context-aware)
    2. Flag length violations for human review (no auto-fix)
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        gemini_model: str = "gemini-2.5-flash-preview",
        dry_run: bool = False
    ):
        """
        Initialize Refinement Validator.

        Args:
            config_path: Path to english_grammar_validation_t1.json
            gemini_model: Model for AI-ism auto-fixing
            dry_run: If True, report violations but don't apply fixes
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "english_grammar_validation_t1.json"

        self.config_path = config_path
        self.gemini_model = gemini_model
        self.dry_run = dry_run

        # Load grammar validation config
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Extract AI-ism patterns
        self.ai_ism_patterns = self.config['validation_categories']['ai_ism_purple_prose']['patterns']

        # Initialize Gemini client for auto-fixing
        self.gemini_client = GeminiClient(model_name=gemini_model)

        print(f"✓ Refinement Validator initialized")
        print(f"  - Config: {config_path.name} v{self.config['version']}")
        print(f"  - Model: {gemini_model}")
        print(f"  - Mode: {'DRY RUN' if dry_run else 'LIVE'}")

    def validate_file(self, input_path: Path, output_path: Optional[Path] = None) -> RefinementReport:
        """
        Validate and refine a single EN markdown file.

        Args:
            input_path: Path to EN markdown file
            output_path: Path for refined output (if None, use input_path with _REFINED suffix)

        Returns:
            RefinementReport with all violations and fixes applied
        """
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_REFINED{input_path.suffix}"

        print(f"\n{'='*60}")
        print(f"Refining: {input_path.name}")
        print(f"{'='*60}")

        # Read input
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        # Initialize report
        report = RefinementReport(
            file_path=str(input_path),
            timestamp=datetime.now().isoformat(),
            total_lines=len(lines)
        )

        # Step 1: Detect AI-isms
        print("\n[Step 1/3] Detecting AI-ism purple prose patterns...")
        ai_ism_violations = self._detect_ai_isms(content, lines)
        report.ai_ism_violations = ai_ism_violations
        report.ai_isms_detected = len(ai_ism_violations)

        print(f"  → Found {len(ai_ism_violations)} AI-ism violations")
        for v in ai_ism_violations:
            print(f"    - {v.pattern_id}: '{v.original_text}' (confidence: {v.confidence})")

        # Step 2: Auto-fix AI-isms via Gemini
        refined_content = content
        if ai_ism_violations and not self.dry_run:
            print("\n[Step 2/3] Auto-fixing AI-isms via Gemini re-injection...")
            refined_content = self._auto_fix_ai_isms(content, ai_ism_violations, report)
            print(f"  → Applied {report.ai_isms_auto_fixed} auto-fixes")
        elif self.dry_run:
            print("\n[Step 2/3] Skipping auto-fixes (DRY RUN mode)")
            report.ai_isms_auto_fixed = 0
        else:
            print("\n[Step 2/3] No AI-isms to fix")
            report.ai_isms_auto_fixed = 0

        report.ai_isms_remaining = report.ai_isms_detected - report.ai_isms_auto_fixed

        # Step 3: Flag length violations (no auto-fix)
        print("\n[Step 3/3] Flagging narration length violations...")
        length_violations = self._detect_length_violations(refined_content)
        report.length_violations = length_violations
        report.length_violations_detected = len(length_violations)
        report.length_hard_cap_violations = sum(1 for v in length_violations if v.violation_type == 'hard_cap')
        report.length_soft_target_violations = sum(1 for v in length_violations if v.violation_type == 'soft_target')

        print(f"  → Found {len(length_violations)} length violations")
        print(f"    - Hard cap (>15w): {report.length_hard_cap_violations}")
        print(f"    - Soft target (12-14w): {report.length_soft_target_violations}")

        # Generate summary
        self._generate_summary(report)

        # Write refined output
        if not self.dry_run:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(refined_content)
            print(f"\n✓ Refined output written to: {output_path.name}")

        return report

    def _detect_ai_isms(self, content: str, lines: List[str]) -> List[AIismViolation]:
        """Detect AI-ism purple prose patterns using regex."""
        violations = []

        for pattern_def in self.ai_ism_patterns:
            pattern_id = pattern_def['id']
            pattern = pattern_def['pattern']
            severity = pattern_def['severity']
            confidence = pattern_def.get('confidence_threshold', 0.7)

            # Find all matches
            for match in re.finditer(pattern, content, re.IGNORECASE):
                matched_text = match.group(0)
                position = match.start()

                # Find line number
                line_num = content[:position].count('\n') + 1

                # Extract context (±100 chars)
                context_start = max(0, position - 100)
                context_end = min(len(content), match.end() + 100)
                context_before = content[context_start:position].replace('\n', ' ').strip()
                context_after = content[match.end():context_end].replace('\n', ' ').strip()

                # Get suggested fix
                fix_suggestions = pattern_def.get('fix_suggestions', {})
                suggested_fix = fix_suggestions.get(matched_text.lower())

                violation = AIismViolation(
                    pattern_id=pattern_id,
                    line_number=line_num,
                    original_text=matched_text,
                    context_before=context_before,
                    context_after=context_after,
                    severity=severity,
                    confidence=confidence,
                    suggested_fix=suggested_fix
                )

                violations.append(violation)

        return violations

    def _auto_fix_ai_isms(
        self,
        content: str,
        violations: List[AIismViolation],
        report: RefinementReport
    ) -> str:
        """
        Auto-fix AI-isms via Gemini re-injection with focused context.

        Strategy:
        - Send each violation with ±200 char context to Gemini
        - Gemini rewrites the sentence to remove AI-ism
        - Replace in-place with fixed version
        """
        refined_content = content
        fixes_applied = 0

        # Build focused prompt for Gemini
        system_prompt = """You are a professional prose editor specializing in removing AI-generated purple prose patterns.

Your task: Rewrite the given sentence to remove the AI-ism while preserving meaning and tone.

CRITICAL RULES:
1. Only fix the specific AI-ism pattern indicated
2. Preserve the surrounding context exactly
3. Maintain the sentence's core meaning and emotional weight
4. Keep dialogue tags and character names unchanged
5. Return ONLY the fixed sentence, nothing else

AI-ism Patterns to Remove:
- "I couldn't help but [verb]" → "[verb]" (remove unnecessary filter)
- "a sense of [emotion]" → "felt [emotion]" or direct emotion noun
- "heavy with [descriptor]" → direct adjective
- "welled up" → "spread" / "rose" / direct action
- Purple prose metaphors → simpler, direct language

Examples:
INPUT: "I couldn't help but flinch at the sudden sound."
OUTPUT: "I flinched at the sudden sound."

INPUT: "Warmth welled up in my chest as she spoke."
OUTPUT: "Warmth spread through my chest as she spoke."

INPUT: "Her voice, heavy with a sultry charm, made my heart race."
OUTPUT: "Her sultry voice made my heart race."
"""

        for violation in violations:
            # Only auto-fix high-confidence patterns
            if violation.confidence < 0.9:
                continue

            # Build focused context window
            context = f"{violation.context_before} **{violation.original_text}** {violation.context_after}"

            user_prompt = f"""Fix this AI-ism:

Pattern: {violation.pattern_id}
Confidence: {violation.confidence}
Original: "{violation.original_text}"

Context:
{context}

Return ONLY the fixed version of the text, maintaining all surrounding context."""

            try:
                # Call Gemini for intelligent rewrite
                response = self.gemini_client.generate(
                    system_instruction=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3,  # Low temp for consistent fixes
                    max_tokens=200
                )

                if response and response.strip():
                    fixed_text = response.strip()

                    # Replace in content (find exact match with context)
                    # Use context window to ensure correct replacement
                    search_pattern = re.escape(violation.original_text)
                    refined_content = re.sub(
                        search_pattern,
                        fixed_text.replace(violation.original_text, '').strip() or fixed_text,
                        refined_content,
                        count=1,
                        flags=re.IGNORECASE
                    )

                    violation.auto_fixed = True
                    violation.suggested_fix = fixed_text
                    fixes_applied += 1

                    print(f"  ✓ Fixed: '{violation.original_text}' → '{fixed_text[:50]}...'")

            except Exception as e:
                print(f"  ✗ Failed to fix '{violation.original_text}': {e}")
                violation.auto_fixed = False

        report.ai_isms_auto_fixed = fixes_applied
        report.improvements_made.append(f"Auto-fixed {fixes_applied} AI-ism purple prose patterns")

        return refined_content

    def _detect_length_violations(self, content: str) -> List[LengthViolation]:
        """
        Detect narration sentence length violations.

        Flag only, no auto-fix (human review required for sentence splitting).
        """
        violations = []

        # Split into sentences (exclude dialogue)
        sentences = re.split(r'[.!?]+(?=\s+[A-Z"]|\s*$)', content)

        current_line = 1
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or sentence.startswith('#'):
                continue

            # Skip dialogue (contains quotes)
            if '"' in sentence:
                # Only check narration parts (text outside quotes)
                narration_text = re.sub(r'"[^"]*"', '', sentence).strip()
                if not narration_text:
                    continue
                sentence_to_check = narration_text
            else:
                sentence_to_check = sentence

            # Count words
            words = sentence_to_check.split()
            word_count = len(words)

            # Check violations
            if word_count > 15:
                # Hard cap violation
                violations.append(LengthViolation(
                    line_number=current_line,
                    sentence=sentence_to_check[:100] + '...' if len(sentence_to_check) > 100 else sentence_to_check,
                    word_count=word_count,
                    violation_type='hard_cap',
                    severity='high',
                    suggested_action=f"Split into 2-3 sentences (current: {word_count}w, target: ≤15w)"
                ))
            elif word_count > 14:
                # Soft target violation (12-14w ideal)
                violations.append(LengthViolation(
                    line_number=current_line,
                    sentence=sentence_to_check[:100] + '...' if len(sentence_to_check) > 100 else sentence_to_check,
                    word_count=word_count,
                    violation_type='soft_target',
                    severity='medium',
                    suggested_action=f"Consider tightening (current: {word_count}w, target: 12-14w)"
                ))

            current_line += sentence.count('\n') + 1

        return violations

    def _generate_summary(self, report: RefinementReport):
        """Generate overall grade and recommendations."""
        # Calculate grade
        ai_ism_score = 100 - (report.ai_isms_remaining * 10)  # -10 per remaining AI-ism
        length_score = max(0, 100 - (report.length_hard_cap_violations * 2))  # -2 per violation

        overall_score = (ai_ism_score * 0.6) + (length_score * 0.4)

        if overall_score >= 95:
            report.overall_grade = "A+"
        elif overall_score >= 90:
            report.overall_grade = "A"
        elif overall_score >= 85:
            report.overall_grade = "A-"
        elif overall_score >= 80:
            report.overall_grade = "B+"
        else:
            report.overall_grade = "B"

        # Generate recommendations
        if report.ai_isms_remaining > 0:
            report.recommendations.append(
                f"Review {report.ai_isms_remaining} remaining AI-ism(s) - may require manual rewrite"
            )

        if report.length_hard_cap_violations > 10:
            report.recommendations.append(
                f"High priority: Split {report.length_hard_cap_violations} narration sentences exceeding 15 words"
            )

        if report.length_soft_target_violations > 20:
            report.recommendations.append(
                f"Consider tightening {report.length_soft_target_violations} sentences to 12-14 word range"
            )

        if not report.recommendations:
            report.recommendations.append("No critical issues - output is production-ready")


def main():
    parser = argparse.ArgumentParser(
        description="Stage 3 Refinement Validator - Auto-fix AI-isms, flag length violations"
    )
    parser.add_argument(
        '--input',
        type=Path,
        help='Input EN markdown file'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output refined markdown file (default: INPUT_REFINED.md)'
    )
    parser.add_argument(
        '--batch',
        type=Path,
        help='Batch process all EN markdown files in directory'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory for batch processing'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report violations without applying fixes'
    )
    parser.add_argument(
        '--model',
        default='gemini-2.5-flash-preview',
        help='Gemini model for AI-ism auto-fixing (default: gemini-2.5-flash-preview)'
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to english_grammar_validation_t1.json'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.input and not args.batch:
        parser.error("Either --input or --batch must be specified")

    # Initialize validator
    validator = RefinementValidator(
        config_path=args.config,
        gemini_model=args.model,
        dry_run=args.dry_run
    )

    # Process files
    reports = []

    if args.batch:
        # Batch processing
        input_files = sorted(args.batch.glob('CHAPTER_*_EN.md'))
        output_dir = args.output_dir or args.batch / 'REFINED'
        output_dir.mkdir(exist_ok=True)

        print(f"\nBatch processing {len(input_files)} files...")

        for input_file in input_files:
            output_file = output_dir / input_file.name
            report = validator.validate_file(input_file, output_file)
            reports.append(report)

    else:
        # Single file processing
        report = validator.validate_file(args.input, args.output)
        reports.append(report)

    # Generate aggregate report
    print(f"\n{'='*60}")
    print("REFINEMENT SUMMARY")
    print(f"{'='*60}")

    total_ai_isms_detected = sum(r.ai_isms_detected for r in reports)
    total_ai_isms_fixed = sum(r.ai_isms_auto_fixed for r in reports)
    total_length_violations = sum(r.length_violations_detected for r in reports)

    print(f"\nProcessed: {len(reports)} file(s)")
    print(f"\nAI-ism Purple Prose:")
    print(f"  - Detected: {total_ai_isms_detected}")
    print(f"  - Auto-fixed: {total_ai_isms_fixed}")
    print(f"  - Remaining: {total_ai_isms_detected - total_ai_isms_fixed}")
    print(f"\nLength Violations:")
    print(f"  - Total flagged: {total_length_violations}")
    print(f"  - Hard cap (>15w): {sum(r.length_hard_cap_violations for r in reports)}")
    print(f"  - Soft target: {sum(r.length_soft_target_violations for r in reports)}")

    # Save JSON reports
    for i, report in enumerate(reports):
        json_path = Path(report.file_path).parent / f"{Path(report.file_path).stem}_REFINEMENT_REPORT.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"\n✓ Report saved: {json_path.name}")

    print(f"\n{'='*60}")
    print("Refinement complete!")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
