"""
Visual Speaker Resolver (Speaker Diarization).

Uses manga panel evidence to resolve subject-omitted Japanese dialogue.
When the LN has 「バカ……」 with no explicit subject, this module checks
the manga panel's speech bubble tail to identify the speaker.

This is the "Speaker Diarization Breakthrough" from Phase 1.8:
  Without manga: 「バカ……」 → "Idiot..." (who says this?)
  With manga:    Panel shows bubble tail → Nagi, blushing, averted gaze
                 → "Idiot..." she muttered, Nagi's cheeks flushed.

🧪 EXPERIMENTAL — Phase 1.8c
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from modules.manga_rag.retriever import MangaRetriever, MangaQueryType, SpeakerAttribution

logger = logging.getLogger(__name__)


@dataclass
class SpeakerResolution:
    """Complete speaker resolution result for a dialogue line."""

    dialogue_jp: str
    speaker: Optional[str]
    confidence: float
    method: str  # "manga_bubble", "context_inference", "unresolved"
    panel_evidence: Optional[str] = None
    expression: Optional[str] = None
    body_language: Optional[str] = None


class SpeakerResolver:
    """
    Visual Speaker Diarization using manga panel evidence.

    For each dialogue line in a segment, attempts to identify the speaker by:
    1. Checking if the text already names the speaker (highest priority)
    2. Querying manga panels for speech bubble attribution
    3. Falling back to contextual inference

    Speaker attributions are logged with confidence levels:
      HIGH (≥0.85): Inject into translation prompt
      MEDIUM (0.70-0.84): Log for review
      LOW (<0.70): Discard
    """

    def __init__(
        self,
        retriever: MangaRetriever,
        confidence_threshold: float = 0.85,
        character_names: Optional[List[str]] = None,
    ):
        self.retriever = retriever
        self.confidence_threshold = confidence_threshold
        self.character_names = character_names or []

    def resolve_segment_speakers(
        self,
        segment_text: str,
        chapter_id: str,
    ) -> List[SpeakerResolution]:
        """
        Resolve speakers for all dialogue lines in a segment.

        Args:
            segment_text: The LN text segment with dialogue
            chapter_id: Current LN chapter

        Returns:
            List of SpeakerResolution for each dialogue line found
        """
        dialogue_lines = self._extract_dialogue_lines(segment_text)
        if not dialogue_lines:
            return []

        resolutions = []
        for line_data in dialogue_lines:
            resolution = self._resolve_single(
                line_data["dialogue"],
                line_data["context_before"],
                chapter_id,
            )
            resolutions.append(resolution)

        resolved_count = sum(1 for r in resolutions if r.speaker is not None)
        logger.debug(
            f"[MANGA] Speaker resolution: {resolved_count}/{len(resolutions)} "
            f"lines resolved for {chapter_id}"
        )

        return resolutions

    def _resolve_single(
        self,
        dialogue: str,
        context_before: str,
        chapter_id: str,
    ) -> SpeakerResolution:
        """Resolve speaker for a single dialogue line."""

        # Method 1: Check if context already names the speaker
        text_speaker = self._extract_speaker_from_context(context_before)
        if text_speaker:
            return SpeakerResolution(
                dialogue_jp=dialogue,
                speaker=text_speaker,
                confidence=1.0,
                method="text_explicit",
            )

        # Method 2: Query manga panels for speech bubble evidence
        attribution = self.retriever.resolve_speaker(
            dialogue, chapter_id, candidates=self.character_names
        )

        if attribution and attribution.confidence >= self.confidence_threshold:
            return SpeakerResolution(
                dialogue_jp=dialogue,
                speaker=attribution.speaker,
                confidence=attribution.confidence,
                method="manga_bubble",
                panel_evidence=attribution.evidence,
            )

        # Method 3: Low-confidence or no result
        if attribution:
            return SpeakerResolution(
                dialogue_jp=dialogue,
                speaker=attribution.speaker,
                confidence=attribution.confidence,
                method="manga_bubble_low_confidence",
                panel_evidence=attribution.evidence,
            )

        return SpeakerResolution(
            dialogue_jp=dialogue,
            speaker=None,
            confidence=0.0,
            method="unresolved",
        )

    # ─── Text Analysis Helpers ───────────────────────────────────────

    def _extract_dialogue_lines(self, text: str) -> List[Dict[str, str]]:
        """
        Extract dialogue lines with surrounding context.

        Returns list of {dialogue, context_before, context_after}.
        """
        results = []
        # Match 「...」 with up to 50 chars before
        pattern = re.compile(r"(.{0,50})「([^」]+)」")

        for match in pattern.finditer(text):
            results.append(
                {
                    "context_before": match.group(1).strip(),
                    "dialogue": match.group(2),
                }
            )

        return results

    def _extract_speaker_from_context(self, context: str) -> Optional[str]:
        """
        Try to identify the speaker from narration before the dialogue.

        Looks for patterns like:
          「〇〇は言った」→ 〇〇
          「〇〇が呟いた」→ 〇〇
        """
        if not context:
            return None

        # Check if any known character name appears right before the dialogue
        for name in self.character_names:
            # Pattern: name + speech verb (は言った, が言う, と呟いた, etc.)
            if name in context[-30:]:
                return name

        # Look for common speech verb patterns with subject
        speech_patterns = [
            r"(\S+)[はが](?:言|云|呟|叫|囁|尋|答|返|告|語)",
            r"(\S+)の(?:声|言葉|返事)",
        ]

        for pattern in speech_patterns:
            match = re.search(pattern, context)
            if match:
                candidate = match.group(1)
                # Validate: must be in character list (if available)
                if self.character_names:
                    if candidate in self.character_names:
                        return candidate
                else:
                    # No character list: return raw match if it looks like a name
                    if len(candidate) >= 2 and not candidate.startswith("「"):
                        return candidate

        return None

    def build_speaker_guidance(
        self,
        resolutions: List[SpeakerResolution],
    ) -> str:
        """
        Build speaker guidance text for injection into translation prompt.

        Only includes HIGH confidence resolutions (≥ threshold).
        """
        high_confidence = [
            r for r in resolutions
            if r.speaker and r.confidence >= self.confidence_threshold
        ]

        if not high_confidence:
            return ""

        lines = ["--- SPEAKER ATTRIBUTION (Manga Evidence) ---"]
        for r in high_confidence:
            short_dialogue = r.dialogue_jp[:30] + ("..." if len(r.dialogue_jp) > 30 else "")
            lines.append(
                f"  「{short_dialogue}」→ {r.speaker} "
                f"(confidence: {r.confidence:.0%}, method: {r.method})"
            )
            if r.expression:
                lines.append(f"    Expression: {r.expression}")
            if r.body_language:
                lines.append(f"    Body language: {r.body_language}")

        lines.append("--- END SPEAKER ATTRIBUTION ---")
        return "\n".join(lines)
