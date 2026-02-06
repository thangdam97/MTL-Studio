"""
Analysis Leak Detector.

Detects when Gemini outputs analysis/planning text instead of translated prose.
This is a known issue with multimodal prompts where the model sometimes
outputs its reasoning process instead of the translation.

Used as a post-translation QA check when multimodal mode is active.
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Patterns that indicate analysis/planning output instead of translation
ANALYSIS_MARKERS = [
    r"^(?:First|Second|Third|Next|Finally),?\s+I",
    r"^Let me\s+",
    r"^I (?:will|need to|should|'ll)\s+",
    r"^My (?:approach|strategy|plan)\s+",
    r"^(?:Okay|Alright),?\s+(?:so|let)",
    r"^Here's (?:what|how|my)\s+",
    r"^\*\*(?:Translation|My|Analysis)\*\*",
    r"^Step \d+:",
    r"translation (?:process|approach|strategy)",
    r"^(?:Looking at|Analyzing|Examining) the (?:illustration|image|text)",
    r"^The illustration (?:shows|depicts|features)",
    r"^Based on (?:the|my) (?:visual|analysis)",
]


def detect_analysis_leak(text: str) -> Tuple[bool, List[str]]:
    """
    Detect if translation output contains analysis instead of translation.

    Args:
        text: The translated output text to check.

    Returns:
        Tuple of (leak_detected: bool, issues: List[str]).
    """
    lines = text.strip().split('\n')
    first_lines = lines[:5]

    issues = []
    for line in first_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        for pattern in ANALYSIS_MARKERS:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                preview = line_stripped[:60] + "..." if len(line_stripped) > 60 else line_stripped
                issues.append(f"Analysis marker detected: '{preview}'")
                break

    # Also check for absence of narrative indicators in first 10 lines
    if len(lines) > 3:
        narrative_indicators = ['"', '\u201c', '\u201d', '*', '\u2014', '...', '\u2026']
        non_empty_lines = [l.strip() for l in lines[:10] if l.strip()]
        has_narrative = any(
            any(ind in line for ind in narrative_indicators)
            for line in non_empty_lines
        )
        if not has_narrative and len(non_empty_lines) > 3:
            issues.append("No narrative indicators (quotes, italics, em-dashes) in first 10 lines")

    leak_detected = len(issues) > 0

    if leak_detected:
        logger.warning(f"[MULTIMODAL] Analysis leak detected ({len(issues)} issues):")
        for issue in issues:
            logger.warning(f"  - {issue}")

    return leak_detected, issues
