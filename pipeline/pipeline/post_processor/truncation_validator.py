"""
Truncation validator for translated chapter outputs.

Detects likely incomplete lines such as:
- Missing terminal punctuation at paragraph end
- Mid-word truncation (e.g., line ending with "Tig")
- Dangling conjunctions that indicate unfinished sentences
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class TruncationIssue:
    line_number: int
    truncated_text: str
    severity: str  # CRITICAL, HIGH, MEDIUM
    broken_word: Optional[str] = None


@dataclass
class TruncationReport:
    chapter_path: Optional[Path]
    issues: List[TruncationIssue] = field(default_factory=list)

    @property
    def critical(self) -> List[TruncationIssue]:
        return [issue for issue in self.issues if issue.severity == "CRITICAL"]

    @property
    def high(self) -> List[TruncationIssue]:
        return [issue for issue in self.issues if issue.severity == "HIGH"]

    @property
    def medium(self) -> List[TruncationIssue]:
        return [issue for issue in self.issues if issue.severity == "MEDIUM"]

    @property
    def all_issues(self) -> List[TruncationIssue]:
        return list(self.issues)

    def has_critical(self) -> bool:
        return bool(self.critical)

    def has_any(self) -> bool:
        return bool(self.issues)


class TruncationValidator:
    TERMINAL_PUNCTUATION = {
        ".",
        "!",
        "?",
        '"',
        "'",
        "…",
        "。",
        "！",
        "？",
        "”",
        "’",
        ")",
        "]",
    }
    DANGLING_CONJUNCTIONS = {
        "and",
        "but",
        "or",
        "that",
        "which",
        "as",
        "when",
        "if",
        "because",
        "while",
        "though",
        "although",
    }
    _SHORT_WORD_ALLOWLIST = {
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "for",
        "it",
        "he",
        "she",
        "we",
        "you",
        "they",
        "i",
    }

    def validate_chapter(self, chapter_path: Path) -> TruncationReport:
        text = chapter_path.read_text(encoding="utf-8")
        report = self.validate_text(text)
        report.chapter_path = chapter_path
        return report

    def validate_text(self, text: str) -> TruncationReport:
        issues: List[TruncationIssue] = []
        for line_num, line in enumerate(text.splitlines(), start=1):
            issue = self.validate_line(line, line_num)
            if issue:
                issues.append(issue)
        return TruncationReport(chapter_path=None, issues=issues)

    def validate_line(self, line: str, line_num: int) -> Optional[TruncationIssue]:
        stripped = line.strip()
        if not stripped:
            return None

        # Skip markdown metadata/format lines.
        if (
            stripped.startswith("#")
            or stripped.startswith("![")
            or stripped.startswith("```")
            or stripped.startswith("---")
            or stripped == "◆"
            or stripped.startswith("> ")
        ):
            return None

        # Very short lines are often deliberate (dialogue fragments, titles).
        if len(stripped) < 20:
            return None

        # Explicit broken ends.
        if stripped.endswith("-"):
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="CRITICAL",
                broken_word=stripped.split()[-1] if stripped.split() else "-",
            )

        last_char = stripped[-1]
        if last_char in self.TERMINAL_PUNCTUATION:
            return None

        # Lines ending in commas/colons/semicolons are usually incomplete thought.
        if last_char in {",", ";", ":"}:
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="HIGH",
                broken_word=None,
            )

        words = re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", stripped)
        if not words:
            return None

        last_word = words[-1].lower()

        if last_word in self.DANGLING_CONJUNCTIONS:
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="HIGH",
                broken_word=last_word,
            )

        # Mid-word cut heuristic: long line + short final token + no punctuation.
        if len(stripped) >= 40 and len(last_word) <= 4 and last_word not in self._SHORT_WORD_ALLOWLIST:
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="CRITICAL",
                broken_word=last_word,
            )

        if len(stripped) >= 80:
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="MEDIUM",
                broken_word=None,
            )

        return None
