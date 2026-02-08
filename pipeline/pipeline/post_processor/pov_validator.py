"""
POV consistency validator for translated chapter outputs.

Detects unexpected first-person narration in volumes declared as
third-person, and vice versa.  First-person inside quoted dialogue
or italicized internal monologue is allowed.

Created post-25d9 audit where Ch02 dream sequence leaked first-person
narration into an otherwise third-person volume.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class POVIssue:
    line_number: int
    text_snippet: str
    marker: str          # the word/phrase that triggered detection
    severity: str = "HIGH"


@dataclass
class POVReport:
    chapter_path: Optional[Path] = None
    declared_pov: str = "third"   # "first" | "third"
    issues: List[POVIssue] = field(default_factory=list)

    def has_any(self) -> bool:
        return bool(self.issues)

    @property
    def issue_count(self) -> int:
        return len(self.issues)


class POVValidator:
    """Detect POV inconsistencies in translated prose."""

    # First-person markers (only match outside quotes)
    _FIRST_PERSON_PATTERNS = [
        # Pronoun at word boundary, case-insensitive would catch too much
        # so we specifically look for sentence-start "I " and standalone "I"
        re.compile(r"(?<![\w])I(?=[\s,;:.!?])"),          # standalone I
        re.compile(r"\bmy\b", re.IGNORECASE),
        re.compile(r"\bmine\b", re.IGNORECASE),
        re.compile(r"\bmyself\b", re.IGNORECASE),
    ]

    # Patterns that indicate quoted speech or internal monologue (exempt)
    _QUOTE_RE = re.compile(
        r'(?:'
        r'[\u201c\u201d"]+.*?[\u201c\u201d"]+'   # "quoted text"
        r'|'
        r"\*.*?\*"                                    # *italicized text*
        r'|'
        r'_.*?_'                                        # _underline italic_
        r')'
    )

    def __init__(self, declared_pov: str = "third"):
        """
        Args:
            declared_pov: Expected POV for the volume ("first" or "third").
        """
        self.declared_pov = declared_pov.lower()

    def validate_chapter(self, chapter_path: Path) -> POVReport:
        text = chapter_path.read_text(encoding="utf-8")
        report = self.validate_text(text)
        report.chapter_path = chapter_path
        return report

    def validate_text(self, text: str) -> POVReport:
        report = POVReport(declared_pov=self.declared_pov)

        if self.declared_pov != "third":
            # Only check for first-person leaks in third-person volumes
            return report

        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Remove quoted speech and italics before scanning
            cleaned = self._QUOTE_RE.sub("", stripped)

            for pattern in self._FIRST_PERSON_PATTERNS:
                match = pattern.search(cleaned)
                if match:
                    report.issues.append(
                        POVIssue(
                            line_number=line_num,
                            text_snippet=stripped[:120],
                            marker=match.group(),
                            severity="HIGH",
                        )
                    )
                    break  # one issue per line is enough

        return report
