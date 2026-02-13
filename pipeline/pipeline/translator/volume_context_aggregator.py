"""
Volume Context Aggregator - Builds comprehensive context from previous chapters.
Leverages Gemini's 1M token window for volume-level translation consistency.

Based on official Gemini Full Long Context specifications:
- Context window: 1 million tokens
- Best practice: Put query at END after all context
- Optimization: Use context caching for 4x cost reduction
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import json
import logging
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class CharacterEntry:
    """Character information extracted from previous chapters."""
    name_en: str
    name_jp: str
    first_appearance_chapter: int
    personality_traits: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    dialogue_style: str = ""
    honorifics_used: List[str] = field(default_factory=list)


@dataclass
class ChapterSummary:
    """Summary of a single chapter for context building."""
    chapter_num: int
    title: str
    plot_points: List[str] = field(default_factory=list)
    emotional_tone: str = ""
    new_characters: List[str] = field(default_factory=list)
    running_jokes: List[str] = field(default_factory=list)
    tone_shifts: List[str] = field(default_factory=list)


@dataclass
class VolumeContext:
    """Complete volume-level context for translation."""
    volume_title: str
    total_chapters_processed: int
    character_registry: Dict[str, CharacterEntry] = field(default_factory=dict)
    chapter_summaries: List[ChapterSummary] = field(default_factory=list)
    established_terminology: Dict[str, str] = field(default_factory=dict)
    recurring_patterns: Dict[str, Any] = field(default_factory=dict)
    overall_tone: str = ""

    def to_prompt_section(self) -> str:
        """
        Convert volume context to structured prompt section.
        Format optimized for Gemini's long context processing.
        """
        sections = []

        # Section 1: Volume Overview
        sections.append("# VOLUME-LEVEL CONTEXT")
        sections.append(f"**Title:** {self.volume_title}")
        sections.append(f"**Chapters Processed:** {self.total_chapters_processed}")
        sections.append(f"**Overall Tone:** {self.overall_tone}")
        sections.append("")

        # Section 2: Character Registry
        if self.character_registry:
            sections.append("## CHARACTER REGISTRY")
            sections.append("Established characters from previous chapters:")
            sections.append("")
            for name, char in self.character_registry.items():
                sections.append(f"### {char.name_en} ({char.name_jp})")
                sections.append(f"- **First appearance:** Chapter {char.first_appearance_chapter}")
                if char.personality_traits:
                    sections.append(f"- **Personality:** {', '.join(char.personality_traits)}")
                if char.dialogue_style:
                    sections.append(f"- **Dialogue style:** {char.dialogue_style}")
                if char.relationships:
                    sections.append(f"- **Relationships:** {', '.join(f'{k}: {v}' for k, v in char.relationships.items())}")
                if char.honorifics_used:
                    sections.append(f"- **Honorifics:** {', '.join(char.honorifics_used)}")
                sections.append("")

        # Section 3: Chapter Progression
        if self.chapter_summaries:
            sections.append("## CHAPTER PROGRESSION")
            for summary in self.chapter_summaries[-5:]:  # Last 5 chapters for relevance
                sections.append(f"### Chapter {summary.chapter_num}: {summary.title}")
                if summary.plot_points:
                    sections.append(f"**Plot:** {'; '.join(summary.plot_points[:3])}")  # Top 3 points
                if summary.emotional_tone:
                    sections.append(f"**Tone:** {summary.emotional_tone}")
                if summary.new_characters:
                    sections.append(f"**New characters:** {', '.join(summary.new_characters)}")
                sections.append("")

        # Section 4: Established Patterns
        if self.recurring_patterns:
            sections.append("## RECURRING PATTERNS")
            for pattern_type, pattern_data in self.recurring_patterns.items():
                sections.append(f"**{pattern_type}:** {pattern_data}")
            sections.append("")

        # Section 5: Terminology Consistency
        if self.established_terminology:
            sections.append("## ESTABLISHED TERMINOLOGY")
            for jp_term, en_translation in self.established_terminology.items():
                sections.append(f"- {jp_term} → {en_translation}")
            sections.append("")

        return "\n".join(sections)


class VolumeContextAggregator:
    """
    Aggregates context from all previous chapters for volume-aware translation.

    Builds context structure:
    1. Character registry (all characters from previous chapters)
    2. Previous chapters summary (plot, tone, style)
    3. Established patterns (dialogue rhythm, running jokes, tone shifts)
    4. Translation consistency rules (names, honorifics, terminology)

    Total size: 10-20 KB per volume (well under 1M token limit)
    """

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.bible_path = work_dir / '.bible.json'
        self.context_path = work_dir / '.context'
        self.context_cache = {}

        # Ensure context directory exists
        self.context_path.mkdir(exist_ok=True)

    def aggregate_volume_context(
        self,
        current_chapter_num: int,
        source_dir: Path,
        en_dir: Path
    ) -> VolumeContext:
        """
        Aggregate context from chapters 1 to (current_chapter_num - 1).

        Args:
            current_chapter_num: The chapter being translated (1-indexed)
            source_dir: Directory containing JP source chapters
            en_dir: Directory containing EN translated chapters

        Returns:
            VolumeContext with all previous chapter information
        """
        logger.info(f"Aggregating volume context for Chapter {current_chapter_num}")

        # Initialize volume context
        volume_context = VolumeContext(
            volume_title=self._get_volume_title(),
            total_chapters_processed=current_chapter_num - 1
        )

        # If this is Chapter 1, return empty context
        if current_chapter_num <= 1:
            logger.info("Chapter 1: No previous context available")
            return volume_context

        # Load bible for character registry baseline
        bible_data = self._load_bible()
        if bible_data:
            volume_context.character_registry = self._extract_characters_from_bible(bible_data)

        # Process each previous chapter
        for chapter_num in range(1, current_chapter_num):
            chapter_summary = self._process_chapter(chapter_num, source_dir, en_dir)
            if chapter_summary:
                volume_context.chapter_summaries.append(chapter_summary)

                # Update character registry with new characters
                for char_name in chapter_summary.new_characters:
                    if char_name not in volume_context.character_registry:
                        # Create new character entry (will be enriched by subsequent chapters)
                        volume_context.character_registry[char_name] = CharacterEntry(
                            name_en=char_name,
                            name_jp="",  # To be filled from bible or context
                            first_appearance_chapter=chapter_num
                        )

        # Extract recurring patterns from chapter summaries
        volume_context.recurring_patterns = self._extract_recurring_patterns(
            volume_context.chapter_summaries
        )

        # Determine overall tone from chapter progression
        volume_context.overall_tone = self._determine_overall_tone(
            volume_context.chapter_summaries
        )

        # Extract established terminology from bible and chapters
        volume_context.established_terminology = self._extract_terminology(bible_data)

        # Cache the context for this chapter
        self._save_context_cache(current_chapter_num, volume_context)

        logger.info(
            f"Volume context aggregated: {len(volume_context.character_registry)} characters, "
            f"{len(volume_context.chapter_summaries)} chapters, "
            f"{len(volume_context.established_terminology)} terminology entries"
        )

        return volume_context

    def _get_volume_title(self) -> str:
        """Extract volume title from work directory name."""
        # Format: "Title_20260213_1234"
        dir_name = self.work_dir.name
        # Remove date and ID suffix
        title = dir_name.split('_')[0] if '_' in dir_name else dir_name
        return title

    def _load_bible(self) -> Optional[Dict[str, Any]]:
        """Load bible.json if exists."""
        if not self.bible_path.exists():
            logger.warning(f"Bible not found: {self.bible_path}")
            return None

        try:
            with open(self.bible_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load bible: {e}")
            return None

    def _extract_characters_from_bible(self, bible_data: Dict[str, Any]) -> Dict[str, CharacterEntry]:
        """Extract character registry from bible.json."""
        characters = {}

        # Bible structure: {"characters": {"CharName": {...}}}
        bible_characters = bible_data.get('characters', {})

        for char_name, char_data in bible_characters.items():
            characters[char_name] = CharacterEntry(
                name_en=char_data.get('name_en', char_name),
                name_jp=char_data.get('name_jp', ''),
                first_appearance_chapter=char_data.get('first_appearance', 1),
                personality_traits=char_data.get('personality', []),
                dialogue_style=char_data.get('dialogue_style', ''),
                honorifics_used=char_data.get('honorifics', [])
            )

        return characters

    def _process_chapter(
        self,
        chapter_num: int,
        source_dir: Path,
        en_dir: Path
    ) -> Optional[ChapterSummary]:
        """
        Process a single chapter to extract summary information.

        Reads from .context/{chapter}_SUMMARY.json if exists, otherwise creates lightweight summary.
        """
        # Check for existing summary in .context
        summary_file = self.context_path / f"CHAPTER_{chapter_num:02d}_SUMMARY.json"

        if summary_file.exists():
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                    return ChapterSummary(**summary_data)
            except Exception as e:
                logger.warning(f"Failed to load summary for Chapter {chapter_num}: {e}")

        # If no summary exists, create basic summary from chapter file
        chapter_file = en_dir / f"CHAPTER_{chapter_num:02d}_EN.md"

        if not chapter_file.exists():
            logger.warning(f"Chapter file not found: {chapter_file}")
            return None

        # Create lightweight summary (title only for now)
        # Full summarization would be done by a separate Gemini call in production
        return ChapterSummary(
            chapter_num=chapter_num,
            title=f"Chapter {chapter_num}",
            plot_points=[],  # To be filled by summarization agent
            emotional_tone="",  # To be filled by summarization agent
            new_characters=[],  # To be filled by character detection
            running_jokes=[],
            tone_shifts=[]
        )

    def _extract_recurring_patterns(self, chapter_summaries: List[ChapterSummary]) -> Dict[str, Any]:
        """Extract recurring patterns from chapter summaries."""
        patterns = {}

        # Collect all running jokes
        all_jokes = []
        for summary in chapter_summaries:
            all_jokes.extend(summary.running_jokes)

        if all_jokes:
            # Count frequency of each joke
            joke_counts = defaultdict(int)
            for joke in all_jokes:
                joke_counts[joke] += 1

            # Keep jokes that appear in multiple chapters
            recurring_jokes = [joke for joke, count in joke_counts.items() if count >= 2]
            if recurring_jokes:
                patterns['running_jokes'] = recurring_jokes

        # Detect tone progression
        tones = [s.emotional_tone for s in chapter_summaries if s.emotional_tone]
        if len(tones) >= 3:
            patterns['tone_progression'] = " → ".join(tones[-3:])  # Last 3 chapters

        return patterns

    def _determine_overall_tone(self, chapter_summaries: List[ChapterSummary]) -> str:
        """Determine overall volume tone from chapter progression."""
        if not chapter_summaries:
            return "Unknown"

        # Collect all emotional tones
        tones = [s.emotional_tone for s in chapter_summaries if s.emotional_tone]

        if not tones:
            return "Neutral"

        # Simple majority vote (in production, use Gemini to synthesize)
        from collections import Counter
        tone_counts = Counter(tones)
        most_common_tone = tone_counts.most_common(1)[0][0]

        return most_common_tone

    def _extract_terminology(self, bible_data: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """Extract established terminology from bible."""
        if not bible_data:
            return {}

        terminology = {}

        # Bible structure: {"terminology": {"JP_term": "EN_translation"}}
        bible_terms = bible_data.get('terminology', {})

        for jp_term, en_translation in bible_terms.items():
            terminology[jp_term] = en_translation

        return terminology

    def _save_context_cache(self, chapter_num: int, context: VolumeContext):
        """Save aggregated context to cache for inspection/debugging."""
        cache_file = self.context_path / f"CHAPTER_{chapter_num:02d}_VOLUME_CONTEXT.json"

        try:
            # Convert to dict for JSON serialization
            context_dict = {
                'volume_title': context.volume_title,
                'total_chapters_processed': context.total_chapters_processed,
                'character_registry': {
                    name: {
                        'name_en': char.name_en,
                        'name_jp': char.name_jp,
                        'first_appearance_chapter': char.first_appearance_chapter,
                        'personality_traits': char.personality_traits,
                        'relationships': char.relationships,
                        'dialogue_style': char.dialogue_style,
                        'honorifics_used': char.honorifics_used
                    }
                    for name, char in context.character_registry.items()
                },
                'chapter_summaries': [
                    {
                        'chapter_num': s.chapter_num,
                        'title': s.title,
                        'plot_points': s.plot_points,
                        'emotional_tone': s.emotional_tone,
                        'new_characters': s.new_characters,
                        'running_jokes': s.running_jokes,
                        'tone_shifts': s.tone_shifts
                    }
                    for s in context.chapter_summaries
                ],
                'established_terminology': context.established_terminology,
                'recurring_patterns': context.recurring_patterns,
                'overall_tone': context.overall_tone
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(context_dict, f, indent=2, ensure_ascii=False)

            logger.info(f"Context cache saved: {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save context cache: {e}")

    def load_cached_context(self, chapter_num: int) -> Optional[VolumeContext]:
        """Load previously cached context for a chapter."""
        cache_file = self.context_path / f"CHAPTER_{chapter_num:02d}_VOLUME_CONTEXT.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                context_dict = json.load(f)

            # Reconstruct VolumeContext from dict
            context = VolumeContext(
                volume_title=context_dict['volume_title'],
                total_chapters_processed=context_dict['total_chapters_processed'],
                overall_tone=context_dict.get('overall_tone', '')
            )

            # Reconstruct character registry
            for name, char_data in context_dict.get('character_registry', {}).items():
                context.character_registry[name] = CharacterEntry(**char_data)

            # Reconstruct chapter summaries
            for summary_data in context_dict.get('chapter_summaries', []):
                context.chapter_summaries.append(ChapterSummary(**summary_data))

            context.established_terminology = context_dict.get('established_terminology', {})
            context.recurring_patterns = context_dict.get('recurring_patterns', {})

            logger.info(f"Loaded cached context for Chapter {chapter_num}")
            return context
        except Exception as e:
            logger.error(f"Failed to load cached context: {e}")
            return None
