"""
Truncation validator for translated chapter outputs.   V2.0

Detects likely incomplete lines such as:
- Missing terminal punctuation at paragraph end followed by blank line
  (PRIMARY truncation signal from chunk-boundary failures)
- Mid-word truncation (e.g., line ending with "Tig")
- Dangling conjunctions that indicate unfinished sentences

V2.0 changes (post-25d9 audit):
- Paragraph-context-aware: checks line + next-line to distinguish real
  truncations from run-on prose
- followed_by_blank flag on every issue for callers to triage
- has_paragraph_truncations() for quick caller checks
- Expanded SHORT_WORD_ALLOWLIST so common function words don't false-positive
- Metadata-line skip list for publisher info
- Strict mode support: callers can check should_block() to decide retry
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class TruncationIssue:
    line_number: int
    truncated_text: str
    severity: str  # CRITICAL, HIGH, MEDIUM
    broken_word: Optional[str] = None
    followed_by_blank: bool = False


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
    def paragraph_end_truncations(self) -> List[TruncationIssue]:
        """Issues where line is followed by blank line - strongest truncation signal."""
        return [issue for issue in self.issues if issue.followed_by_blank]

    @property
    def all_issues(self) -> List[TruncationIssue]:
        return list(self.issues)

    def has_critical(self) -> bool:
        return bool(self.critical)

    def has_paragraph_truncations(self) -> bool:
        return bool(self.paragraph_end_truncations)

    def has_any(self) -> bool:
        return bool(self.issues)

    def should_block(self) -> bool:
        """Return True if the report warrants blocking chapter completion.

        Policy: block on 3+ CRITICAL or any paragraph-end CRITICAL.
        """
        if any(i.severity == "CRITICAL" and i.followed_by_blank for i in self.issues):
            return True
        return len(self.critical) >= 3


class TruncationValidator:
    TERMINAL_PUNCTUATION: Set[str] = {
        ".",
        "!",
        "?",
        '"',
        "'",
        "…",  # ellipsis
        "。",  # JP period
        "！",  # JP !
        "？",  # JP ?
        "”",  # right double quote
        "’",  # right single quote
        ")",
        "]",
        "*",       # markdown emphasis close
        "—",  # em dash (legitimate sentence terminator in fiction)
    }
    COLON_TERMINATORS: Set[str] = {":", ";"}
    DANGLING_CONJUNCTIONS: Set[str] = {
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
    _SHORT_WORD_ALLOWLIST: Set[str] = {
        "a", "an", "the", "to", "of", "in", "on", "at", "by", "for",
        "it", "he", "she", "we", "you", "they", "i",
        "is", "up", "so", "no", "do", "be", "us", "me", "or", "as", "if",
    }
    _METADATA_KEYWORDS: Set[str] = {
        "Dash X", "Kawaguchi", "DIGITAL", "Bunko", "Publisher",
        "Shueisha", "Chiyoda", "Hitotsubashi", "TSUKASA", "Published", "Author",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_chapter(self, chapter_path: Path) -> TruncationReport:
        text = chapter_path.read_text(encoding="utf-8")
        report = self.validate_text(text)
        report.chapter_path = chapter_path
        return report

    def validate_text(self, text: str) -> TruncationReport:
        lines = text.splitlines()
        issues: List[TruncationIssue] = []
        for idx, line in enumerate(lines):
            line_num = idx + 1
            next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            issue = self._validate_line_in_context(line, line_num, next_line)
            if issue:
                issues.append(issue)
        return TruncationReport(chapter_path=None, issues=issues)

    # Backwards-compat: line-only validation (no paragraph context)
    def validate_line(self, line: str, line_num: int) -> Optional[TruncationIssue]:
        """Legacy single-line validation (no paragraph context)."""
        return self._validate_line_in_context(line, line_num, next_line="")

    # ------------------------------------------------------------------
    # Core detection (paragraph-context-aware)
    # ------------------------------------------------------------------

    def _validate_line_in_context(
        self, line: str, line_num: int, next_line: str
    ) -> Optional[TruncationIssue]:
        stripped = line.strip()
        if not stripped:
            return None

        # Skip markdown metadata/format lines
        if (
            stripped.startswith("#")
            or stripped.startswith("![")
            or stripped.startswith("```")
            or stripped.startswith("---")
            or stripped == "◆"
            or stripped == "* * *"
            or stripped.startswith("> ")
        ):
            return None

        # Skip metadata lines (publisher info, etc.)
        if any(kw in stripped for kw in self._METADATA_KEYWORDS):
            return None

        # Very short lines are often deliberate (dialogue fragments, titles)
        if len(stripped) < 20:
            return None

        last_char = stripped[-1]

        # Properly terminated - no issue
        if last_char in self.TERMINAL_PUNCTUATION:
            return None

        # Determine if this line is followed by a blank line (paragraph end)
        followed_by_blank = next_line == ""

        # --- CRITICAL: explicit broken-word (trailing hyphen) ---
        if stripped.endswith("-"):
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="CRITICAL",
                broken_word=stripped.split()[-1] if stripped.split() else "-",
                followed_by_blank=followed_by_blank,
            )

        # --- Lines ending in comma/semicolon/colon ---
        if last_char in self.COLON_TERMINATORS or last_char == ",":
            # Colon mid-paragraph is usually fine
            if last_char == ":" and not followed_by_blank:
                return None
            severity = "HIGH" if followed_by_blank else "MEDIUM"
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity=severity,
                broken_word=None,
                followed_by_blank=followed_by_blank,
            )

        words = re.findall(r"[A-Za-z]+(?:[\'-][A-Za-z]+)?", stripped)
        if not words:
            return None

        last_word = words[-1].lower()

        # --- Dangling conjunction ---
        if last_word in self.DANGLING_CONJUNCTIONS:
            severity = "CRITICAL" if followed_by_blank else "HIGH"
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity=severity,
                broken_word=last_word,
                followed_by_blank=followed_by_blank,
            )

        # --- Paragraph-end heuristic (strongest truncation signal) ---
        # A line without terminal punctuation followed by a blank line is
        # the primary signature of a chunk-boundary truncation.
        if followed_by_blank:
            # Mid-word cut: short final token that is not a common word
            if len(last_word) <= 4 and last_word not in self._SHORT_WORD_ALLOWLIST:
                return TruncationIssue(
                    line_number=line_num,
                    truncated_text=stripped[-120:],
                    severity="CRITICAL",
                    broken_word=last_word,
                    followed_by_blank=True,
                )
            # Long paragraph ending without punctuation
            if len(stripped) >= 40:
                return TruncationIssue(
                    line_number=line_num,
                    truncated_text=stripped[-120:],
                    severity="HIGH",
                    broken_word=None,
                    followed_by_blank=True,
                )
            return None

        # --- Mid-paragraph: only flag very obvious cases ---
        # Short final token on a long line (mid-word cut)
        if len(stripped) >= 40 and len(last_word) <= 4 and last_word not in self._SHORT_WORD_ALLOWLIST:
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="CRITICAL",
                broken_word=last_word,
                followed_by_blank=False,
            )

        # Very long mid-paragraph line without punctuation
        if len(stripped) >= 120:
            return TruncationIssue(
                line_number=line_num,
                truncated_text=stripped[-120:],
                severity="MEDIUM",
                broken_word=None,
                followed_by_blank=False,
            )

        return None
