#!/usr/bin/env python3
"""
Compare tense consistency between baseline and new output after tense enforcement.
Generates a detailed comparison report showing improvements.
"""

import sys
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.post_processor.tense_validator import TenseConsistencyValidator, TenseReport


@dataclass
class ComparisonMetrics:
    """Metrics comparing baseline vs new output."""
    baseline_violations: int
    new_violations: int
    improvement_pct: float
    baseline_violations_per_1k: float
    new_violations_per_1k: float
    severity_improvements: Dict[str, tuple]  # (baseline_count, new_count)
    rule_improvements: Dict[str, tuple]  # (baseline_count, new_count)


def compare_reports(baseline: TenseReport, new: TenseReport) -> ComparisonMetrics:
    """Compare two tense reports and calculate improvement metrics."""

    improvement_pct = 0.0
    if baseline.total_violations > 0:
        improvement_pct = ((baseline.total_violations - new.total_violations) /
                          baseline.total_violations * 100)

    baseline_per_1k = (baseline.total_violations / baseline.total_lines * 1000) if baseline.total_lines > 0 else 0
    new_per_1k = (new.total_violations / new.total_lines * 1000) if new.total_lines > 0 else 0

    # Compare by severity
    severity_improvements = {}
    all_severities = set(list(baseline.violations_by_severity.keys()) +
                        list(new.violations_by_severity.keys()))
    for severity in all_severities:
        baseline_count = baseline.violations_by_severity.get(severity, 0)
        new_count = new.violations_by_severity.get(severity, 0)
        severity_improvements[severity] = (baseline_count, new_count)

    # Compare by rule
    rule_improvements = {}
    all_rules = set(list(baseline.violations_by_rule.keys()) +
                   list(new.violations_by_rule.keys()))
    for rule in all_rules:
        baseline_count = baseline.violations_by_rule.get(rule, 0)
        new_count = new.violations_by_rule.get(rule, 0)
        if baseline_count > 0 or new_count > 0:  # Only include rules with violations
            rule_improvements[rule] = (baseline_count, new_count)

    return ComparisonMetrics(
        baseline_violations=baseline.total_violations,
        new_violations=new.total_violations,
        improvement_pct=improvement_pct,
        baseline_violations_per_1k=baseline_per_1k,
        new_violations_per_1k=new_per_1k,
        severity_improvements=severity_improvements,
        rule_improvements=rule_improvements
    )


def generate_comparison_report(
    chapter_metrics: Dict[str, ComparisonMetrics],
    output_path: Path
):
    """Generate markdown comparison report."""

    with open(output_path.with_suffix('.md'), 'w', encoding='utf-8') as f:
        f.write("# Tense Consistency Enforcement - Before/After Comparison\n\n")
        f.write("## Overview\n\n")
        f.write("Comparison of baseline output vs new output with NARRATIVE_TENSE_CONSISTENCY enforcement.\n\n")

        # Summary table
        f.write("## Summary by Chapter\n\n")
        f.write("| Chapter | Baseline | New | Improvement | Baseline/1k | New/1k |\n")
        f.write("|---------|----------|-----|-------------|-------------|--------|\n")

        total_baseline = 0
        total_new = 0

        for ch_id, metrics in sorted(chapter_metrics.items()):
            total_baseline += metrics.baseline_violations
            total_new += metrics.new_violations

            f.write(f"| {ch_id} | {metrics.baseline_violations} | {metrics.new_violations} | "
                   f"{metrics.improvement_pct:+.1f}% | "
                   f"{metrics.baseline_violations_per_1k:.2f} | "
                   f"{metrics.new_violations_per_1k:.2f} |\n")

        overall_improvement = 0.0
        if total_baseline > 0:
            overall_improvement = ((total_baseline - total_new) / total_baseline * 100)

        f.write(f"| **TOTAL** | **{total_baseline}** | **{total_new}** | "
               f"**{overall_improvement:+.1f}%** | - | - |\n\n")

        # Severity breakdown
        f.write("## Violations by Severity\n\n")

        for ch_id, metrics in sorted(chapter_metrics.items()):
            f.write(f"### {ch_id}\n\n")
            f.write("| Severity | Baseline | New | Change |\n")
            f.write("|----------|----------|-----|--------|\n")

            for severity, (baseline_count, new_count) in sorted(metrics.severity_improvements.items()):
                change = new_count - baseline_count
                f.write(f"| {severity.upper()} | {baseline_count} | {new_count} | {change:+d} |\n")
            f.write("\n")

        # Rule-specific improvements
        f.write("## Violations by Rule Type\n\n")

        for ch_id, metrics in sorted(chapter_metrics.items()):
            f.write(f"### {ch_id}\n\n")
            f.write("| Rule | Baseline | New | Change | Status |\n")
            f.write("|------|----------|-----|--------|--------|\n")

            sorted_rules = sorted(metrics.rule_improvements.items(),
                                 key=lambda x: -(x[1][0] - x[1][1]))  # Sort by improvement

            for rule, (baseline_count, new_count) in sorted_rules:
                change = new_count - baseline_count
                status = "✅ Fixed" if new_count == 0 and baseline_count > 0 else \
                        "✓ Improved" if change < 0 else \
                        "⚠ Same" if change == 0 else \
                        "✗ Regressed"

                f.write(f"| `{rule}` | {baseline_count} | {new_count} | {change:+d} | {status} |\n")
            f.write("\n")

        # Key findings
        f.write("## Key Findings\n\n")

        if overall_improvement > 0:
            f.write(f"✅ **Overall improvement: {overall_improvement:.1f}% reduction in tense violations**\n\n")
        elif overall_improvement < 0:
            f.write(f"⚠️ **Regression: {abs(overall_improvement):.1f}% increase in violations**\n\n")
        else:
            f.write("⚠️ **No change in violation count**\n\n")

        # Most improved rules
        all_rule_changes = []
        for ch_id, metrics in chapter_metrics.items():
            for rule, (baseline_count, new_count) in metrics.rule_improvements.items():
                all_rule_changes.append((rule, baseline_count - new_count, baseline_count, new_count))

        all_rule_changes.sort(key=lambda x: -x[1])

        if all_rule_changes and all_rule_changes[0][1] > 0:
            f.write("### Most Improved Rules\n\n")
            for rule, improvement, baseline, new in all_rule_changes[:5]:
                if improvement > 0:
                    f.write(f"- **{rule}**: {baseline} → {new} ({-improvement} violations fixed)\n")
            f.write("\n")

        # Remaining issues
        if total_new > 0:
            f.write("### Remaining Issues\n\n")
            for ch_id, metrics in sorted(chapter_metrics.items()):
                if metrics.new_violations > 0:
                    f.write(f"- **{ch_id}**: {metrics.new_violations} violations remaining\n")
            f.write("\n")

        f.write("---\n\n")
        f.write("*Generated by TenseConsistencyValidator comparison tool*\n")


def main():
    """Run comparison between baseline and new output."""
    print("=" * 70)
    print("TENSE ENFORCEMENT COMPARISON - BASELINE vs NEW OUTPUT")
    print("=" * 70)
    print()

    volume_path = Path(__file__).parent.parent / "WORK" / "他校の氷姫を助けたら、お友達から始める事になりました３_20260209_1a60"

    baseline_dir = volume_path / "EN_baseline_before_tense_enforcement"
    new_dir = volume_path / "EN"

    if not baseline_dir.exists():
        print(f"✗ Baseline directory not found: {baseline_dir}")
        return 1

    if not new_dir.exists():
        print(f"✗ New output directory not found: {new_dir}")
        return 1

    validator = TenseConsistencyValidator(auto_fix=False)

    chapter_files = [
        ("chapter_01", "CHAPTER_01_EN.md"),
        ("chapter_02", "CHAPTER_02_EN.md"),
        ("chapter_03", "CHAPTER_03_EN.md"),
    ]

    chapter_metrics = {}

    for ch_id, filename in chapter_files:
        baseline_file = baseline_dir / filename
        new_file = new_dir / filename

        if not baseline_file.exists():
            print(f"⚠ Baseline file not found: {baseline_file}")
            continue

        if not new_file.exists():
            print(f"⚠ New file not found: {new_file}")
            continue

        print(f"\nValidating {ch_id}...")
        print(f"  Baseline: {baseline_file}")
        baseline_report = validator.validate_file(baseline_file)

        print(f"  New:      {new_file}")
        new_report = validator.validate_file(new_file)

        metrics = compare_reports(baseline_report, new_report)
        chapter_metrics[ch_id] = metrics

        print(f"  Result:   {baseline_report.total_violations} → {new_report.total_violations} "
              f"({metrics.improvement_pct:+.1f}%)")

    if not chapter_metrics:
        print("\n✗ No chapters could be compared")
        return 1

    # Generate comparison report
    output_path = volume_path / "TENSE_ENFORCEMENT_COMPARISON_REPORT"
    generate_comparison_report(chapter_metrics, output_path)

    print()
    print("=" * 70)
    print(f"✓ Comparison report generated: {output_path.with_suffix('.md')}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
