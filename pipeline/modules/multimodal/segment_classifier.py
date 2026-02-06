"""
Segment Classifier for Multimodal Translation.

Classifies chapter segments to determine which require visual context injection.
Supports lookahead buffer to pre-load visual context for upcoming illustrations.

Detects ALL illustration tag formats produced by the Librarian (Phase 1):
  - Legacy bracket:    [ILLUSTRATION: illust-001.jpg]    (block-level)
  - Markdown image:    ![illustration](p162.jpg)          (block-level)
  - Gaiji inline:      ![gaiji](gaiji-001.png)            (inline glyph)
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class SegmentType(Enum):
    STANDARD = "standard"
    MULTIMODAL = "multimodal"
    MULTIMODAL_LOOKAHEAD = "multimodal_lookahead"


class IllustrationLevel(Enum):
    """Whether the illustration marker is block-level or inline."""
    BLOCK = "block"       # Full illustrations (page/panel art)
    INLINE = "inline"     # Gaiji (character glyph replacements)


@dataclass
class IllustrationMatch:
    """A single illustration reference found in text."""
    illustration_id: str       # e.g. 'illust-001', 'p162', 'gaiji-001'
    raw_match: str             # The full matched string
    level: IllustrationLevel   # BLOCK or INLINE
    format_type: str           # 'legacy_bracket', 'markdown_image', 'gaiji'


@dataclass
class ClassifiedSegment:
    """A text segment with its classification and associated illustration info."""
    text: str
    segment_type: SegmentType
    illustration_id: Optional[str] = None
    lookahead_illustration_id: Optional[str] = None
    illustration_level: Optional[IllustrationLevel] = None
    all_illustrations: List[IllustrationMatch] = field(default_factory=list)


# ============================================================================
# ILLUSTRATION PATTERNS — aligned with pipeline/config.py canonical patterns
# ============================================================================

# 1) Legacy bracket format: [ILLUSTRATION: filename.jpg]
#    Produced by: librarian/agent.py, librarian/content_splitter.py
#    Canonical pattern from config.py: r'\[ILLUSTRATION:?\s*"?([^"\]]+)"?\]'
LEGACY_BRACKET_PATTERN = re.compile(
    r'\[ILLUSTRATION:?\s*"?([^"\]]+)"?\]', re.IGNORECASE
)

# 2) Markdown image format: ![illustration](filename.jpg) or ![](filename.jpg)
#    Produced by: librarian/xhtml_to_markdown.py for block-level illustrations
#    Canonical pattern from config.py: r'!\[(illustration|gaiji|)\]\(([^)]+)\)'
#    NOTE: We split this into two patterns to distinguish block vs inline
MARKDOWN_ILLUSTRATION_PATTERN = re.compile(
    r'!\[(illustration|)\]\(([^)]+)\)', re.IGNORECASE
)

# 3) Gaiji inline format: ![gaiji](gaiji-001.png)
#    Produced by: librarian/xhtml_to_markdown.py for inline character glyphs
#    These are NOT real illustrations — they replace CJK characters
GAIJI_PATTERN = re.compile(
    r'!\[gaiji\]\(([^)]+)\)', re.IGNORECASE
)

# Combined pattern for quick "does this contain ANY illustration?" checks
_ANY_ILLUSTRATION_PATTERN = re.compile(
    r'(?:\[ILLUSTRATION:?\s*"?[^"\]]+?"?\])|(?:!\[(?:illustration|gaiji|)\]\([^)]+\))',
    re.IGNORECASE
)


# ============================================================================
# UTILITY: Strip file extensions from illustration IDs
# ============================================================================

_EXTENSION_PATTERN = re.compile(r'\.(jpg|jpeg|png|gif|webp|svg)$', re.IGNORECASE)


def _strip_extension(raw_id: str) -> str:
    """Remove image file extension from an illustration ID."""
    return _EXTENSION_PATTERN.sub('', raw_id.strip())


# ============================================================================
# CORE DETECTION FUNCTIONS
# ============================================================================

def find_all_illustrations(text: str) -> List[IllustrationMatch]:
    """
    Find ALL illustration references in a text segment.

    Scans for all three Librarian output formats and returns structured
    matches with their type and level classification.

    Args:
        text: Text to scan (a segment or full chapter).

    Returns:
        List of IllustrationMatch objects, in order of appearance.
    """
    matches: List[IllustrationMatch] = []
    seen_positions: set = set()  # Avoid double-counting overlapping patterns

    # 1) Legacy bracket format: [ILLUSTRATION: filename]
    for m in LEGACY_BRACKET_PATTERN.finditer(text):
        if m.start() not in seen_positions:
            seen_positions.add(m.start())
            raw_filename = m.group(1).strip()
            illust_id = _strip_extension(raw_filename)

            # Gaiji detection within legacy format (rare but possible)
            if illust_id.startswith('gaiji-') or illust_id.startswith('gaiji_'):
                level = IllustrationLevel.INLINE
                fmt = 'gaiji'
            else:
                level = IllustrationLevel.BLOCK
                fmt = 'legacy_bracket'

            matches.append(IllustrationMatch(
                illustration_id=illust_id,
                raw_match=m.group(0),
                level=level,
                format_type=fmt
            ))

    # 2) Gaiji inline: ![gaiji](filename)
    for m in GAIJI_PATTERN.finditer(text):
        if m.start() not in seen_positions:
            seen_positions.add(m.start())
            raw_filename = m.group(1).strip()
            illust_id = _strip_extension(raw_filename)
            matches.append(IllustrationMatch(
                illustration_id=illust_id,
                raw_match=m.group(0),
                level=IllustrationLevel.INLINE,
                format_type='gaiji'
            ))

    # 3) Markdown illustration: ![illustration](filename) or ![](filename)
    for m in MARKDOWN_ILLUSTRATION_PATTERN.finditer(text):
        if m.start() not in seen_positions:
            seen_positions.add(m.start())
            raw_filename = m.group(2).strip()
            illust_id = _strip_extension(raw_filename)
            matches.append(IllustrationMatch(
                illustration_id=illust_id,
                raw_match=m.group(0),
                level=IllustrationLevel.BLOCK,
                format_type='markdown_image'
            ))

    # Sort by position in text
    matches.sort(key=lambda x: text.index(x.raw_match))
    return matches


def has_illustration(text: str) -> bool:
    """Quick check: does this text contain ANY illustration marker?"""
    return bool(_ANY_ILLUSTRATION_PATTERN.search(text))


def has_block_illustration(text: str) -> bool:
    """Check if text contains a block-level illustration (not gaiji)."""
    illustrations = find_all_illustrations(text)
    return any(m.level == IllustrationLevel.BLOCK for m in illustrations)


# ============================================================================
# CLASSIFICATION FUNCTIONS (backward-compatible API)
# ============================================================================

def classify_segment(text: str) -> SegmentType:
    """
    Classify a single text segment based on illustration markers.

    A segment is MULTIMODAL if it contains any block-level illustration.
    Gaiji-only segments remain STANDARD (gaiji are character glyphs,
    not visual illustrations requiring context injection).
    """
    if has_block_illustration(text):
        return SegmentType.MULTIMODAL
    return SegmentType.STANDARD


def extract_illustration_id(text: str) -> Optional[str]:
    """
    Extract the first block-level illustration ID from text.

    Returns:
        Illustration ID without extension (e.g., 'illust-001') or None.
        Skips gaiji (inline character glyphs).
    """
    illustrations = find_all_illustrations(text)
    for m in illustrations:
        if m.level == IllustrationLevel.BLOCK:
            return m.illustration_id
    return None


def extract_all_illustration_ids(text: str) -> List[str]:
    """
    Extract ALL unique block-level illustration IDs from text.

    Returns:
        List of unique illustration IDs (without extensions).
        Excludes gaiji markers.
    """
    illustrations = find_all_illustrations(text)
    seen = set()
    ids = []
    for m in illustrations:
        if m.level == IllustrationLevel.BLOCK and m.illustration_id not in seen:
            seen.add(m.illustration_id)
            ids.append(m.illustration_id)
    return ids


def extract_all_gaiji_ids(text: str) -> List[str]:
    """
    Extract ALL unique gaiji IDs from text.

    Returns:
        List of unique gaiji IDs (without extensions).
    """
    illustrations = find_all_illustrations(text)
    seen = set()
    ids = []
    for m in illustrations:
        if m.level == IllustrationLevel.INLINE and m.illustration_id not in seen:
            seen.add(m.illustration_id)
            ids.append(m.illustration_id)
    return ids


def extract_all_ids_with_level(text: str) -> List[Tuple[str, IllustrationLevel]]:
    """
    Extract ALL illustration IDs with their level classification.

    Returns:
        List of (illustration_id, level) tuples in order of appearance.
    """
    illustrations = find_all_illustrations(text)
    seen = set()
    result = []
    for m in illustrations:
        if m.illustration_id not in seen:
            seen.add(m.illustration_id)
            result.append((m.illustration_id, m.level))
    return result


# ============================================================================
# LOOKAHEAD CLASSIFIER
# ============================================================================

def classify_segments_with_lookahead(
    segments: List[str],
    lookahead_buffer_size: int = 3
) -> List[ClassifiedSegment]:
    """
    Classify all segments in a chapter with lookahead buffer.

    The lookahead buffer allows pre-loading visual context for segments
    that appear BEFORE an illustration, enabling emotional momentum buildup.

    Only block-level illustrations trigger MULTIMODAL/LOOKAHEAD classification.
    Gaiji markers are tracked in all_illustrations but don't affect classification.

    Args:
        segments: List of text segments (typically paragraphs).
        lookahead_buffer_size: How many segments ahead to check.

    Returns:
        List of ClassifiedSegment with type and illustration references.
    """
    classified = []

    for i, text in enumerate(segments):
        all_illusts = find_all_illustrations(text)
        illust_id = extract_illustration_id(text)

        if illust_id:
            # This segment contains a block-level illustration
            classified.append(ClassifiedSegment(
                text=text,
                segment_type=SegmentType.MULTIMODAL,
                illustration_id=illust_id,
                illustration_level=IllustrationLevel.BLOCK,
                all_illustrations=all_illusts
            ))
        else:
            # Lookahead: check next N segments for upcoming block illustration
            lookahead_id = None
            for j in range(1, lookahead_buffer_size + 1):
                if i + j < len(segments):
                    future_id = extract_illustration_id(segments[i + j])
                    if future_id:
                        lookahead_id = future_id
                        break

            if lookahead_id:
                classified.append(ClassifiedSegment(
                    text=text,
                    segment_type=SegmentType.MULTIMODAL_LOOKAHEAD,
                    lookahead_illustration_id=lookahead_id,
                    all_illustrations=all_illusts
                ))
            else:
                classified.append(ClassifiedSegment(
                    text=text,
                    segment_type=SegmentType.STANDARD,
                    all_illustrations=all_illusts
                ))

    return classified
