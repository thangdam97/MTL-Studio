"""
Manga Storyboard Prompt Injector.

Builds "Storyboard Notes" blocks from manga panel retrieval results
and merges them with Phase 1.6 "Art Director's Notes" for Binocular Vision.

This is the final integration layer:
  Left Eye:  Art Director's Notes  (Phase 1.6 — LN illustrations)
  Right Eye: Storyboard Notes      (Phase 1.8 — manga panels)

Both eyes feed into Gemini 2.5 Pro's translation prompt.

🧪 EXPERIMENTAL — Phase 1.8c
"""

import logging
from typing import Dict, List, Optional, Any

from modules.manga_rag.vector_store import PanelSearchResult

logger = logging.getLogger(__name__)


# ─── Canon Divergence Directive ──────────────────────────────────────────

MANGA_CANON_DIVERGENCE_DIRECTIVE = """
=== MANGA REFERENCE PROTOCOL ===

The Storyboard Notes below are from the MANGA ADAPTATION of this light novel.
They provide VISUAL REFERENCE for expressions, body language, and atmosphere.

**STRICT RULES:**
1. The LN TEXT is SCRIPTURE — never contradict it based on manga panels
2. The MANGA is VISUAL REFERENCE — borrow emotion, expression, atmosphere
3. If text says "she stood" but manga shows her sitting: follow TEXT, borrow EMOTION
4. Use manga body language to enrich prose ONLY where the text is vague
5. Speaker attributions from manga panels have HIGH confidence but verify against text context

**WHAT TO USE:**
✓ Facial micro-expressions for emotional vocabulary
✓ Body language details to disambiguate vague descriptions
✓ Speaker attribution from speech bubble evidence
✓ Atmosphere and lighting for scene-setting vocabulary
✗ Adding actions not in the text (even if manga shows them)
✗ Changing scene choreography based on manga composition
✗ Assuming manga-original scenes exist in the LN

=== END MANGA REFERENCE PROTOCOL ===
"""


# ─── Storyboard Note Formatting ─────────────────────────────────────────

STORYBOARD_NOTE_TEMPLATE = """--- STORYBOARD [{panel_id}] (Manga Reference, similarity: {similarity:.0%}) ---
{content_lines}
--- END STORYBOARD ---"""


def format_storyboard_note(panel: PanelSearchResult) -> str:
    """
    Format a single manga panel result as a Storyboard Note.

    Only includes non-empty fields to keep prompt tokens lean.
    """
    lines = []

    if panel.speaker:
        lines.append(f"Speaker: {panel.speaker}")

    if panel.characters:
        lines.append(f"Characters: {', '.join(panel.characters)}")

    if panel.expression:
        lines.append(f"Expression: {panel.expression}")

    if panel.body_language:
        lines.append(f"Body Language: {panel.body_language}")

    if panel.dialogue_context:
        lines.append(f"Scene: {panel.dialogue_context}")

    if panel.atmosphere:
        lines.append(f"Atmosphere: {panel.atmosphere}")

    if panel.emotional_intensity > 0:
        lines.append(f"Emotional Intensity: {panel.emotional_intensity:.1f}/1.0")

    if panel.narrative_beat:
        lines.append(f"Beat: {panel.narrative_beat}")

    content = "\n".join(lines) if lines else "Visual reference (see panel)"

    return STORYBOARD_NOTE_TEMPLATE.format(
        panel_id=panel.panel_id,
        similarity=panel.similarity,
        content_lines=content,
    )


# ─── Binocular Vision Merger ────────────────────────────────────────────

def build_storyboard_context(
    manga_panels: List[PanelSearchResult],
    include_directive: bool = True,
) -> str:
    """
    Build the Storyboard Notes block for prompt injection.

    Args:
        manga_panels: Retrieved manga panel results
        include_directive: Whether to include the Canon Divergence directive

    Returns:
        Formatted storyboard context string
    """
    if not manga_panels:
        return ""

    blocks = []

    if include_directive:
        blocks.append(MANGA_CANON_DIVERGENCE_DIRECTIVE)

    blocks.append(f"\n=== STORYBOARD CONTEXT (Manga Reference) ===")
    blocks.append(f"Panels retrieved: {len(manga_panels)}")
    blocks.append("")

    for panel in manga_panels:
        blocks.append(format_storyboard_note(panel))
        blocks.append("")

    blocks.append("=== END STORYBOARD CONTEXT ===")

    return "\n".join(blocks)


def build_binocular_context(
    art_director_notes: Optional[str],
    manga_panels: List[PanelSearchResult],
    speaker_guidance: Optional[str] = None,
) -> str:
    """
    Build combined visual context from LN illustrations + manga panels.

    This is the "Binocular Vision" merger:
      Left Eye:  Art Director's Notes (Phase 1.6 LN illustrations)
      Right Eye: Storyboard Notes (Phase 1.8 manga panels)

    The two sources complement each other:
      - LN illustrations provide high-res keyframe context
      - Manga panels fill the gaps with scene-level detail

    Args:
        art_director_notes: Existing Phase 1.6 visual context (or None)
        manga_panels: Retrieved manga panels for this segment
        speaker_guidance: Optional speaker attribution block

    Returns:
        Combined visual context string for prompt injection
    """
    sections = []

    # Left Eye: Art Director's Notes (existing Phase 1.6)
    if art_director_notes:
        sections.append(art_director_notes)

    # Right Eye: Storyboard Notes (new Phase 1.8)
    storyboard = build_storyboard_context(manga_panels, include_directive=True)
    if storyboard:
        sections.append(storyboard)

    # Speaker attribution evidence
    if speaker_guidance:
        sections.append(speaker_guidance)

    if not sections:
        return ""

    return "\n\n".join(sections)


# ─── Segment-Level Integration ──────────────────────────────────────────

def should_inject_storyboard(
    panels: List[PanelSearchResult],
    inject_threshold: float = 0.80,
) -> bool:
    """
    Determine if retrieved panels are confident enough to inject.

    At least one panel must exceed the injection threshold.
    """
    if not panels:
        return False
    return any(p.similarity >= inject_threshold for p in panels)


def build_segment_visual_context(
    art_director_notes: Optional[str],
    manga_panels: List[PanelSearchResult],
    speaker_guidance: Optional[str] = None,
    inject_threshold: float = 0.80,
) -> Optional[str]:
    """
    Build visual context for a single translation segment.

    Only injects manga panels if at least one exceeds the threshold.
    Art Director's Notes are always included if available.

    This is the function called from the main Phase 2 translation loop.

    Returns:
        Visual context string, or None if nothing to inject
    """
    # Filter to injectable panels only
    injectable_panels = [
        p for p in manga_panels if p.similarity >= inject_threshold
    ]

    # Always include Art Director's Notes if available
    if not art_director_notes and not injectable_panels:
        return None

    return build_binocular_context(
        art_director_notes=art_director_notes,
        manga_panels=injectable_panels,
        speaker_guidance=speaker_guidance,
    )
