#!/usr/bin/env python3
"""Scan translation output folders for common EN grammar/error patterns.

Scope (default): pipeline/WORK/*/EN/*.md
Output: JSON + Markdown report
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Pattern, Tuple


@dataclass
class MatchRecord:
    category: str
    severity: str
    file_path: str
    volume_id: str
    line_number: int
    matched_text: str
    context: str


@dataclass
class Rule:
    rule_id: str
    category: str
    severity: str
    pattern: Pattern[str]
    matcher: Optional[Callable[[re.Match[str], str], Optional[str]]] = None


def _extract_volume_id(path: Path) -> str:
    parts = path.parts
    if "WORK" in parts:
        i = parts.index("WORK")
        if i + 1 < len(parts):
            return parts[i + 1]
    return "unknown"


def _line_context(line: str, max_len: int = 180) -> str:
    line = line.strip().replace("\t", " ")
    if len(line) <= max_len:
        return line
    return line[: max_len - 3] + "..."


def _name_possessive_filter(match: re.Match[str], line: str) -> Optional[str]:
    name = match.group(1)
    noun = match.group(2)

    excluded = {
        "Her", "His", "My", "Your", "Our", "Their", "Its",
        "The", "This", "That", "These", "Those", "A", "An",
        "In", "On", "At", "To", "From", "For", "By", "With", "Without",
        "And", "But", "Or", "Nor", "Yet", "So", "If", "When", "While", "Though",
        "Because", "Since", "As", "After", "Before", "Until", "Unless",
        "Then", "Now", "Today", "Tomorrow", "Yesterday",
        "Once", "Each", "Every", "Many", "Few", "Some", "Any", "All", "Both",
        "First", "Last", "Next", "Previous", "New", "Old", "Other",
        "Japanese", "English", "Chinese", "Korean",
        "Welcome", "Good", "Bad", "Big", "Small",
        "Soft", "Long", "Short", "Slender", "Sulking", "Bright", "Dark",
        "Gentle", "Warm", "Cold", "Sharp", "Thick", "Thin", "Wide", "Narrow",
        "Heavy", "Light", "Quiet", "Loud",
        "Black", "White", "Red", "Blue", "Green", "Golden", "Silver",
    }
    if name in excluded:
        return None

    stripped = line.strip()
    if stripped.startswith(('"', "'", "*", "“", "”", "‘", "’")):
        return None

    # Skip clear verb usages frequently misdetected by simple regex.
    if noun.lower() in {"thought", "response", "question", "answer"}:
        return None

    # If already possessive (e.g., "Bennett family's"), do not flag.
    after = line[match.end():]
    if after.startswith("'"):
        return None

    return f"{name}'s {noun}"


def _there_was_plural_filter(match: re.Match[str], line: str) -> Optional[str]:
    noun = match.group(1)
    noun_l = noun.lower()
    singular_like = {
        "news", "series", "species", "means", "headquarters",
        "physics", "mathematics", "economics", "politics", "athletics",
    }
    if noun_l in singular_like:
        return None
    # Typical singular nouns ending in -is/-us/-ss can be false positives (e.g., basis, glass).
    if noun_l.endswith(("is", "us", "ss")):
        return None
    return f"There were no {noun}"


def _a_vs_an_filter(match: re.Match[str], line: str) -> Optional[str]:
    word = match.group(1)
    lowered = word.lower()
    # Common consonant-sound exceptions after "a"
    if lowered.startswith((
        "user", "use", "util", "usual", "uni", "unanim", "one", "once",
        "euro", "ewe", "ufo", "uk", "u-sh", "usb", "usage",
    )):
        return None
    return f"an {word}"


def _always(match: re.Match[str], line: str) -> Optional[str]:
    return match.group(0)


def build_rules() -> List[Rule]:
    # Keep this list intentionally narrow to reduce false positives.
    possessive_nouns = (
        "eyes|face|hand|voice|expression|smile|heart|mind|body|hair|skin|lips|"
        "arms|legs|feet|shoulders|gaze|cheeks|jaw|fingers|wrist|posture|breath"
    )

    cjk_ranges = "\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF"

    return [
        Rule(
            rule_id="missing_possessive_noun",
            category="Possessive Apostrophe",
            severity="high",
            pattern=re.compile(rf"\b([A-Z][a-z]+)\s+({possessive_nouns})\b"),
            matcher=_name_possessive_filter,
        ),
        Rule(
            rule_id="there_was_no_plural",
            category="Existential Agreement",
            severity="high",
            pattern=re.compile(
                r"\bThere\s+was\s+no\s+(people|children|men|women|teeth|feet|mice|geese|[A-Za-z][A-Za-z'-]*s)\b"
            ),
            matcher=_there_was_plural_filter,
        ),
        Rule(
            rule_id="a_vs_an_vowel_sound",
            category="Article Usage",
            severity="medium",
            pattern=re.compile(r"\ba\s+([aeiouAEIOU][A-Za-z'-]*)\b"),
            matcher=_a_vs_an_filter,
        ),
        Rule(
            rule_id="malformed_modal_of",
            category="Contraction Form",
            severity="medium",
            pattern=re.compile(r"\b(could|would|should|must)\s+of\b", re.IGNORECASE),
            matcher=_always,
        ),
        Rule(
            rule_id="singular_subject_plural_verb",
            category="Subject-Verb Agreement",
            severity="high",
            pattern=re.compile(r"\b(He|She|It)\s+(are|were|have|do)\b"),
            matcher=_always,
        ),
        Rule(
            rule_id="plural_subject_singular_verb",
            category="Subject-Verb Agreement",
            severity="high",
            pattern=re.compile(r"\b(They|We|These|Those)\s+(is|was|has|does)\b"),
            matcher=_always,
        ),
        Rule(
            rule_id="literal_words_surprise_my_heart",
            category="Literal JP->EN Phrasing",
            severity="medium",
            pattern=re.compile(r"\b([Hh]er|[Hh]is|[Tt]heir|[Mm]y|[Yy]our)\s+words\s+surprise\s+my\s+heart\b"),
            matcher=_always,
        ),
        Rule(
            rule_id="cjk_leak",
            category="CJK Character Leak",
            severity="high",
            pattern=re.compile(rf"[{cjk_ranges}]+"),
            matcher=_always,
        ),
    ]


def iter_target_files(work_root: Path) -> Iterable[Path]:
    # Treat EN folders inside WORK as translation output folders.
    for path in sorted(work_root.glob("*/EN/*.md")):
        if path.is_file():
            yield path


def scan_files(files: Iterable[Path], rules: List[Rule]) -> Tuple[List[MatchRecord], Dict[str, int]]:
    matches: List[MatchRecord] = []
    file_count = 0

    for file_path in files:
        file_count += 1
        volume_id = _extract_volume_id(file_path)

        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="replace")

        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            for rule in rules:
                for m in rule.pattern.finditer(line):
                    if rule.matcher:
                        hint = rule.matcher(m, line)
                        if hint is None:
                            continue
                    matches.append(
                        MatchRecord(
                            category=rule.category,
                            severity=rule.severity,
                            file_path=str(file_path),
                            volume_id=volume_id,
                            line_number=line_no,
                            matched_text=m.group(0),
                            context=_line_context(line),
                        )
                    )

    meta = {"files_scanned": file_count}
    return matches, meta


def build_report(matches: List[MatchRecord], files_scanned: int) -> Dict:
    by_category = Counter(m.category for m in matches)
    by_severity = Counter(m.severity for m in matches)
    by_volume = Counter(m.volume_id for m in matches)
    by_file = Counter(m.file_path for m in matches)

    # Keep representative examples per category
    examples: Dict[str, List[Dict]] = defaultdict(list)
    seen = set()
    for m in matches:
        key = (m.category, m.file_path, m.line_number, m.matched_text)
        if key in seen:
            continue
        seen.add(key)
        if len(examples[m.category]) < 10:
            examples[m.category].append(
                {
                    "file": m.file_path,
                    "line": m.line_number,
                    "match": m.matched_text,
                    "context": m.context,
                }
            )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "target": "pipeline/WORK/*/EN/*.md",
            "files_scanned": files_scanned,
            "total_findings": len(matches),
        },
        "summary": {
            "by_category": dict(by_category.most_common()),
            "by_severity": dict(by_severity),
        },
        "hotspots": {
            "top_volumes": [{"volume_id": k, "findings": v} for k, v in by_volume.most_common(15)],
            "top_files": [{"file": k, "findings": v} for k, v in by_file.most_common(20)],
        },
        "examples": examples,
    }


def write_markdown(report: Dict, out_path: Path) -> None:
    lines: List[str] = []
    lines.append("# Gemini Output Grammar Error Scan Report")
    lines.append("")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- Target: `{report['scope']['target']}`")
    lines.append(f"- Files scanned: **{report['scope']['files_scanned']}**")
    lines.append(f"- Total findings: **{report['scope']['total_findings']}**")
    lines.append("")

    lines.append("## Common Error Categories")
    for category, count in report["summary"]["by_category"].items():
        lines.append(f"- {category}: **{count}**")
    lines.append("")

    lines.append("## Severity Mix")
    for severity, count in report["summary"]["by_severity"].items():
        lines.append(f"- {severity}: **{count}**")
    lines.append("")

    lines.append("## Hotspot Volumes")
    for item in report["hotspots"]["top_volumes"]:
        lines.append(f"- `{item['volume_id']}`: {item['findings']} findings")
    lines.append("")

    lines.append("## Hotspot Files")
    for item in report["hotspots"]["top_files"]:
        lines.append(f"- `{item['file']}`: {item['findings']} findings")
    lines.append("")

    lines.append("## Example Findings")
    for category, ex_list in report["examples"].items():
        lines.append("")
        lines.append(f"### {category}")
        for ex in ex_list[:8]:
            lines.append(f"- `{ex['file']}:{ex['line']}` — `{ex['match']}`")
            lines.append(f"  - {ex['context']}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan EN output files for common grammar errors.")
    parser.add_argument(
        "--work-root",
        default="pipeline/WORK",
        help="Root of volume work directories (default: pipeline/WORK)",
    )
    parser.add_argument(
        "--json-out",
        default="pipeline/OUTPUT_GRAMMAR_SCAN_REPORT.json",
        help="Path to JSON report",
    )
    parser.add_argument(
        "--md-out",
        default="pipeline/OUTPUT_GRAMMAR_SCAN_REPORT.md",
        help="Path to markdown report",
    )
    args = parser.parse_args()

    work_root = Path(args.work_root)
    files = list(iter_target_files(work_root))
    rules = build_rules()

    matches, meta = scan_files(files, rules)
    report = build_report(matches, files_scanned=meta["files_scanned"])

    json_out = Path(args.json_out)
    md_out = Path(args.md_out)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, md_out)

    print(f"Scanned files: {report['scope']['files_scanned']}")
    print(f"Total findings: {report['scope']['total_findings']}")
    print(f"JSON report: {json_out}")
    print(f"Markdown report: {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
