"""
Translation Ambiguity Detector.

Scores LN text segments for translation ambiguity to decide whether
manga panel retrieval is worthwhile. High-ambiguity segments trigger
Manga RAG; low-ambiguity segments skip it (saving API calls).

Key ambiguity triggers:
  - Subject omission (no explicit subject in Japanese)
  - Emotional scenes (emotion words without clear visual)
  - Multiple speakers (dialogue between 3+ characters)
  - Physical descriptions (body language / gesture references)
  - Scene transitions (location or time changes)

🧪 EXPERIMENTAL — Phase 1.8c
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Japanese Language Markers ───────────────────────────────────────────

# Subject pronouns (if present, subject is explicit → less ambiguity)
SUBJECT_PRONOUNS_JP = {
    "私", "僕", "俺", "あたし", "わたし", "ぼく", "おれ",  # First person
    "あなた", "君", "お前", "てめえ", "きみ", "あんた",     # Second person
    "彼", "彼女", "あの人", "あいつ", "やつ", "こいつ",     # Third person
}

# Emotion markers (scenes with these need visual context)
EMOTION_MARKERS_JP = {
    "泣", "涙", "笑", "怒", "照", "恥", "驚", "震", "赤面",
    "ドキドキ", "キュン", "ゾクゾク", "ハラハラ", "ワクワク",
    "びっくり", "がっかり", "うんざり", "ほっと",
    "溜め息", "ため息", "吐息",
}

# Physical action markers (body language in text → need visual reference)
PHYSICAL_MARKERS_JP = {
    "手", "腕", "肩", "首", "頭", "目", "顔", "唇", "指",
    "握", "掴", "触", "抱", "押", "引", "叩", "振",
    "立", "座", "歩", "走", "止", "向", "背",
    "うつむ", "そっぽ", "にらみ", "睨", "見つめ",
}

# Scene transition markers
TRANSITION_MARKERS_JP = {
    "翌日", "翌朝", "次の日", "放課後", "昼休み", "夕方",
    "場所を移", "移動", "到着", "着い",
    "――", "＊＊＊", "♦", "◇",  # Section break patterns
}


@dataclass
class AmbiguityScore:
    """Detailed ambiguity analysis result."""

    total_score: float
    triggers: Dict[str, float] = field(default_factory=dict)
    should_retrieve: bool = False
    explanation: str = ""


class AmbiguityDetector:
    """
    Scores LN text segments for translation ambiguity.

    High-ambiguity segments trigger Manga RAG retrieval.
    Low-ambiguity segments skip it (saves API calls and prompt tokens).
    """

    # Trigger weights
    AMBIGUITY_TRIGGERS = {
        "subject_omission": 0.40,
        "emotional_scene": 0.30,
        "multiple_speakers": 0.50,
        "physical_description": 0.25,
        "scene_transition": 0.30,
        "dense_dialogue": 0.35,
    }

    def __init__(self, retrieval_threshold: float = 0.6):
        self.retrieval_threshold = retrieval_threshold

    def score_ambiguity(
        self,
        segment: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AmbiguityScore:
        """
        Score a segment's translation ambiguity (0.0 → 1.0).

        Args:
            segment: The LN text segment to analyze
            context: Optional context (chapter_id, characters, prev_segment)

        Returns:
            AmbiguityScore with breakdown of triggers
        """
        context = context or {}
        triggers = {}
        explanations = []

        # 1. Subject omission: no explicit subject pronoun
        if not self._has_explicit_subject(segment):
            triggers["subject_omission"] = self.AMBIGUITY_TRIGGERS["subject_omission"]
            explanations.append("No explicit subject pronoun detected")

        # 2. Emotional scene: contains emotion markers
        emotion_count = self._count_markers(segment, EMOTION_MARKERS_JP)
        if emotion_count > 0:
            weight = min(
                self.AMBIGUITY_TRIGGERS["emotional_scene"] * emotion_count,
                self.AMBIGUITY_TRIGGERS["emotional_scene"],
            )
            triggers["emotional_scene"] = weight
            explanations.append(f"{emotion_count} emotion marker(s)")

        # 3. Multiple speakers: 3+ dialogue blocks
        dialogue_count = segment.count("「")
        if dialogue_count >= 3:
            triggers["multiple_speakers"] = self.AMBIGUITY_TRIGGERS["multiple_speakers"]
            explanations.append(f"{dialogue_count} dialogue blocks (multi-speaker)")

        # 4. Physical description: body language words
        physical_count = self._count_markers(segment, PHYSICAL_MARKERS_JP)
        if physical_count >= 2:
            triggers["physical_description"] = self.AMBIGUITY_TRIGGERS[
                "physical_description"
            ]
            explanations.append(f"{physical_count} physical markers")

        # 5. Scene transition
        if self._has_transition(segment):
            triggers["scene_transition"] = self.AMBIGUITY_TRIGGERS["scene_transition"]
            explanations.append("Scene transition detected")

        # 6. Dense dialogue without narration
        if dialogue_count >= 2 and self._dialogue_ratio(segment) > 0.7:
            triggers["dense_dialogue"] = self.AMBIGUITY_TRIGGERS["dense_dialogue"]
            explanations.append("Dense dialogue (>70% of segment)")

        total = min(sum(triggers.values()), 1.0)
        should_retrieve = total >= self.retrieval_threshold

        return AmbiguityScore(
            total_score=round(total, 3),
            triggers=triggers,
            should_retrieve=should_retrieve,
            explanation="; ".join(explanations) if explanations else "Low ambiguity",
        )

    def should_retrieve(
        self,
        segment: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Quick check: should this segment trigger manga retrieval?"""
        return self.score_ambiguity(segment, context).should_retrieve

    # ─── Language Analysis Helpers ────────────────────────────────────

    def _has_explicit_subject(self, text: str) -> bool:
        """Check if text contains an explicit subject pronoun."""
        for pronoun in SUBJECT_PRONOUNS_JP:
            if pronoun in text:
                return True
        return False

    def _count_markers(self, text: str, markers: set) -> int:
        """Count how many markers appear in text."""
        count = 0
        for marker in markers:
            if marker in text:
                count += 1
        return count

    def _has_transition(self, text: str) -> bool:
        """Check if text contains a scene transition marker."""
        for marker in TRANSITION_MARKERS_JP:
            if marker in text:
                return True
        # Also check for section break patterns (multiple newlines)
        if "\n\n\n" in text or "---" in text:
            return True
        return False

    def _dialogue_ratio(self, text: str) -> float:
        """Calculate the ratio of dialogue to total text."""
        dialogue_chars = 0
        in_dialogue = False
        for ch in text:
            if ch == "「":
                in_dialogue = True
            elif ch == "」":
                in_dialogue = False
            elif in_dialogue:
                dialogue_chars += 1

        total = len(text.strip())
        if total == 0:
            return 0.0
        return dialogue_chars / total
