"""
Manga Panel Retriever.

Scene-level semantic retrieval of manga panels during Phase 2 translation.
Uses chapter alignment to scope queries, then ChromaDB for semantic search.

Supports multiple query types:
  - SCENE_MATCH: Find panels depicting a scene described in LN text
  - SPEAKER_ATTRIBUTION: Identify who speaks a line from speech bubble tails
  - EXPRESSION_LOOKUP: Find a character's facial expression for a dialogue line
  - BODY_LANGUAGE: Get physical context for a scene

🧪 EXPERIMENTAL — Phase 1.8c
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from modules.manga_rag.vector_store import MangaVectorStore, PanelSearchResult
from modules.manga_rag.alignment import ChapterAlignment

logger = logging.getLogger(__name__)


class MangaQueryType(Enum):
    """Types of manga panel retrieval queries."""

    SCENE_MATCH = "scene_match"
    SPEAKER_ATTRIBUTION = "speaker_attribution"
    EXPRESSION_LOOKUP = "expression_lookup"
    BODY_LANGUAGE = "body_language"
    ATMOSPHERE = "atmosphere"


@dataclass
class SpeakerAttribution:
    """Result of Visual Speaker Diarization."""

    speaker: str
    confidence: float
    source_panel: str
    evidence: str


class MangaRetriever:
    """
    Retrieves relevant manga panels for a given translation segment.

    Uses chapter alignment to scope retrieval to the correct
    manga page range, then semantic search within that range.
    """

    def __init__(
        self,
        vector_store: MangaVectorStore,
        alignment: ChapterAlignment,
        max_panels_per_segment: int = 4,
        min_similarity: float = 0.75,
        inject_threshold: float = 0.80,
        log_threshold: float = 0.65,
    ):
        self.vector_store = vector_store
        self.alignment = alignment
        self.max_panels = max_panels_per_segment
        self.min_similarity = min_similarity
        self.inject_threshold = inject_threshold
        self.log_threshold = log_threshold

    def retrieve_for_segment(
        self,
        segment_text: str,
        chapter_id: str,
        query_type: MangaQueryType = MangaQueryType.SCENE_MATCH,
        max_panels: Optional[int] = None,
        min_similarity: Optional[float] = None,
    ) -> List[PanelSearchResult]:
        """
        Retrieve manga panels relevant to a translation segment.

        1. Get chapter alignment → manga page range
        2. Build query based on query type
        3. Semantic search within filtered page range
        4. Return top-k panels above threshold

        Args:
            segment_text: The LN text segment being translated
            chapter_id: Current LN chapter (e.g., "CHAPTER_01")
            query_type: Type of retrieval query
            max_panels: Override max results
            min_similarity: Override minimum similarity

        Returns:
            List of PanelSearchResult sorted by similarity (descending)
        """
        max_panels = max_panels or self.max_panels
        min_similarity = min_similarity or self.min_similarity

        # Get manga page scope for this chapter
        page_range = self.alignment.get_page_range(chapter_id)
        if not page_range:
            logger.debug(
                f"[MANGA] No alignment for {chapter_id}, skipping manga retrieval"
            )
            return []

        # Build query
        query = self._build_query(segment_text, query_type)

        # Build metadata filter for page range
        where_filter = {
            "$and": [
                {"page_number": {"$gte": page_range[0]}},
                {"page_number": {"$lte": page_range[1]}},
            ]
        }

        # Execute search
        results = self.vector_store.query(
            query_text=query,
            n_results=max_panels,
            where=where_filter,
            min_similarity=min_similarity,
        )

        if results:
            logger.debug(
                f"[MANGA] Retrieved {len(results)} panels for {chapter_id} "
                f"(pages {page_range[0]}-{page_range[1]}, "
                f"top similarity: {results[0].similarity:.3f})"
            )

        return results

    def retrieve_injectable(
        self,
        segment_text: str,
        chapter_id: str,
        query_type: MangaQueryType = MangaQueryType.SCENE_MATCH,
    ) -> List[PanelSearchResult]:
        """
        Retrieve panels above the injection threshold.

        Only returns panels confident enough to inject into the translation prompt.
        """
        results = self.retrieve_for_segment(
            segment_text, chapter_id, query_type,
            min_similarity=self.inject_threshold,
        )
        return results

    def retrieve_loggable(
        self,
        segment_text: str,
        chapter_id: str,
        query_type: MangaQueryType = MangaQueryType.SCENE_MATCH,
    ) -> List[PanelSearchResult]:
        """
        Retrieve panels above the log threshold (but possibly below inject).

        Returns panels worth logging for review but not confident enough to inject.
        """
        results = self.retrieve_for_segment(
            segment_text, chapter_id, query_type,
            min_similarity=self.log_threshold,
        )
        return results

    def resolve_speaker(
        self,
        dialogue_text: str,
        chapter_id: str,
        candidates: Optional[List[str]] = None,
    ) -> Optional[SpeakerAttribution]:
        """
        Visual Speaker Diarization.

        Given a line of dialogue, find the manga panel where this
        dialogue appears and identify the speaker from the speech
        bubble tail direction.

        Args:
            dialogue_text: The Japanese dialogue (「...」 content)
            chapter_id: Current LN chapter
            candidates: Optional list of character names to choose from

        Returns:
            SpeakerAttribution with character name and confidence, or None
        """
        panels = self.retrieve_for_segment(
            dialogue_text,
            chapter_id,
            query_type=MangaQueryType.SPEAKER_ATTRIBUTION,
            max_panels=2,
            min_similarity=0.80,  # High threshold for speaker attribution
        )

        if not panels:
            return None

        top = panels[0]
        if top.speaker and (not candidates or top.speaker in candidates):
            return SpeakerAttribution(
                speaker=top.speaker,
                confidence=top.similarity,
                source_panel=top.panel_id,
                evidence=f"Speech bubble tail → {top.speaker} (similarity: {top.similarity:.3f})",
            )

        return None

    # ─── Query Builders ──────────────────────────────────────────────

    def _build_query(self, segment_text: str, query_type: MangaQueryType) -> str:
        """
        Build a search query optimized for the query type.

        Different query types emphasize different aspects of the segment.
        """
        if query_type == MangaQueryType.SPEAKER_ATTRIBUTION:
            # Focus on dialogue content for speaker matching
            return self._extract_dialogue(segment_text)

        elif query_type == MangaQueryType.EXPRESSION_LOOKUP:
            # Focus on character + dialogue for expression matching
            dialogue = self._extract_dialogue(segment_text)
            return f"Expression: {dialogue}" if dialogue else segment_text

        elif query_type == MangaQueryType.BODY_LANGUAGE:
            # Focus on action/physical descriptions
            return f"Body language: {segment_text[:300]}"

        elif query_type == MangaQueryType.ATMOSPHERE:
            # Focus on scene/location descriptions
            return f"Atmosphere: {segment_text[:300]}"

        else:
            # SCENE_MATCH: use the full segment
            return segment_text[:500]  # Truncate for embedding quality

    def _extract_dialogue(self, text: str) -> str:
        """Extract Japanese dialogue from text (content within 「」 brackets)."""
        import re

        dialogues = re.findall(r"「([^」]+)」", text)
        if dialogues:
            return " ".join(dialogues)
        return text[:200]  # Fallback to raw text
