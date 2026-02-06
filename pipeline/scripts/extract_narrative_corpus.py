#!/usr/bin/env python3
"""
Extract narrative technique patterns from professional JP→EN translations (EPUB corpus).

Scans ~130 EPUBs from INPUT folder to build a corpus of:
1. Free Indirect Discourse examples
2. Filter word elimination patterns
3. Psychic distance level examples
4. Show Don't Tell transformations
5. Genre-specific narrative voice samples

Author: MTL Studio
Date: 2026-02-03
"""

import os
import re
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict, Counter
from ebooklib import epub
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class NarrativeCorpusExtractor:
    def __init__(self, input_dir: Path, output_json: Path):
        self.input_dir = input_dir
        self.output_json = output_json

        # Pattern databases
        self.fid_patterns = []  # Free Indirect Discourse examples
        self.filter_eliminations = []  # Before/after filter word removal
        self.psychic_distance_samples = defaultdict(list)  # Level → examples
        self.show_dont_tell = []  # Tell → Show transformations
        self.genre_voice_samples = defaultdict(list)  # Genre → voice examples

        # Detection patterns
        self.filter_words = [
            r'\b(she|he|they)\s+(saw|heard|felt|noticed|wondered|thought|sensed|realized)\b',
            r'\b(seemed to|appeared to|looked like)\b',
        ]

        self.emotion_tells = {
            'angry': r'\b(angry|furious|enraged|irate)\b',
            'sad': r'\b(sad|miserable|depressed|gloomy)\b',
            'happy': r'\b(happy|joyful|delighted|cheerful)\b',
            'nervous': r'\b(nervous|anxious|worried|uneasy)\b',
            'scared': r'\b(scared|frightened|terrified|afraid)\b',
        }

        # Genre detection (based on publisher/series patterns)
        self.genre_keywords = {
            'shoujo_romance': ['romance', 'love', 'heart', 'confession', 'dating'],
            'action_fantasy': ['sword', 'magic', 'battle', 'dungeon', 'skill'],
            'slice_of_life': ['daily', 'school', 'club', 'friends', 'ordinary'],
            'isekai': ['another world', 'reincarnated', 'transported', 'game world'],
        }

    def extract_text_from_epub(self, epub_path: Path) -> List[Tuple[str, str]]:
        """Extract text content from EPUB chapters."""
        chapters = []

        try:
            book = epub.read_epub(str(epub_path))

            for item in book.get_items():
                if item.get_type() == 9:  # XHTML content
                    content = item.get_content().decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(content, 'html.parser')

                    # Extract text, preserving paragraph structure
                    paragraphs = soup.find_all(['p', 'div'])
                    text = '\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])

                    if text:
                        # Get chapter title if available
                        title_tag = soup.find(['h1', 'h2', 'h3'])
                        title = title_tag.get_text().strip() if title_tag else "Unknown Chapter"
                        chapters.append((title, text))

        except Exception as e:
            logger.warning(f"Failed to extract from {epub_path.name}: {e}")

        return chapters

    def detect_free_indirect_discourse(self, text: str) -> List[Dict]:
        """
        Detect Free Indirect Discourse patterns.

        FID characteristics:
        - Third-person pronouns (she/he)
        - Character's emotional vocabulary without quotation marks
        - No filter words (felt/thought/saw)
        - Emotional immediacy
        """
        fid_samples = []

        # Split into sentences
        sentences = re.split(r'[.!?]+', text)

        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 200:
                continue

            # Check for third-person pronouns
            has_third_person = bool(re.search(r'\b(she|he|her|his|him)\b', sentence, re.IGNORECASE))

            # Check for absence of filter words
            has_filter = bool(re.search(r'\b(felt|thought|saw|heard|noticed|wondered)\b', sentence, re.IGNORECASE))

            # Check for emotional/internal vocabulary
            has_emotional = bool(re.search(
                r'\b(heart|pulse|breath|throat|chest|eyes|hands|stomach|mind)\b.*'
                r'\b(pounded|raced|tightened|clenched|skipped|fluttered|trembled|ached)\b',
                sentence, re.IGNORECASE
            ))

            # Check for internal questions (characteristic of FID)
            has_internal_question = bool(re.search(r'(What|How|Why|Could)\s+\w+.*\?', sentence))

            # FID score
            fid_score = sum([
                has_third_person * 1,
                (not has_filter) * 2,  # Absence of filter = strong FID indicator
                has_emotional * 2,
                has_internal_question * 1,
            ])

            if fid_score >= 4:
                # Get surrounding context
                context_before = sentences[i-1].strip() if i > 0 else ""
                context_after = sentences[i+1].strip() if i < len(sentences) - 1 else ""

                fid_samples.append({
                    'sentence': sentence,
                    'context_before': context_before,
                    'context_after': context_after,
                    'fid_score': fid_score,
                    'has_third_person': has_third_person,
                    'no_filter_words': not has_filter,
                    'has_emotional_vocabulary': has_emotional,
                    'has_internal_question': has_internal_question,
                })

        return fid_samples

    def detect_filter_word_usage(self, text: str) -> List[Dict]:
        """
        Detect sentences with filter words to build before/after corpus.

        Goal: Find professional translations that successfully eliminate filters.
        """
        filter_samples = []

        sentences = re.split(r'[.!?]+', text)

        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue

            # Check for filter words
            filter_match = re.search(
                r'\b(she|he|they)\s+(saw|heard|felt|noticed|wondered|thought|sensed|realized)\b',
                sentence, re.IGNORECASE
            )

            if filter_match:
                # Get context to see if next sentence shows direct perception
                context_after = sentences[i+1].strip() if i < len(sentences) - 1 else ""

                filter_samples.append({
                    'with_filter': sentence,
                    'filter_word': filter_match.group(2).lower(),
                    'context_after': context_after,
                })

        return filter_samples

    def detect_show_dont_tell(self, text: str) -> List[Dict]:
        """
        Detect show-don't-tell patterns.

        Look for emotional descriptions using physical actions/sensations
        instead of emotion labels.
        """
        show_samples = []

        sentences = re.split(r'[.!?]+', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 200:
                continue

            # Check for physical manifestations of emotion (SHOW)
            physical_patterns = [
                (r'jaw.*clenched|teeth.*ground', 'anger'),
                (r'throat.*tight|eyes.*stinging', 'sadness'),
                (r'heart.*leapt|heart.*soared', 'happiness'),
                (r'palms.*sweating|hands.*trembling', 'nervousness'),
                (r'blood.*cold|spine.*tingling', 'fear'),
                (r'cheeks.*flushed|face.*burning', 'embarrassment'),
            ]

            for pattern, emotion in physical_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    # Make sure it doesn't ALSO tell (e.g., "She was angry, her jaw clenched")
                    emotion_tell_pattern = self.emotion_tells.get(emotion, '')
                    has_tell = bool(re.search(emotion_tell_pattern, sentence, re.IGNORECASE)) if emotion_tell_pattern else False

                    if not has_tell:
                        show_samples.append({
                            'sentence': sentence,
                            'emotion': emotion,
                            'physical_indicator': pattern,
                            'pure_show': not has_tell,
                        })
                    break

        return show_samples

    def classify_psychic_distance(self, text: str) -> Dict[str, List[str]]:
        """
        Classify sentences by psychic distance level.

        Levels:
        1. Maximum distance (geographic/historical framing)
        2. Distant (external description)
        3. Close (with filter words)
        4. Very close (no filters, character vocabulary)
        5. First person
        """
        distance_samples = {
            'level_1_maximum': [],
            'level_2_distant': [],
            'level_3_close': [],
            'level_4_very_close': [],
            'level_5_first_person': [],
        }

        sentences = re.split(r'[.!?]+', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 200:
                continue

            # Level 5: First person
            if re.search(r'\b(I|my|me|we|our)\b', sentence, re.IGNORECASE):
                distance_samples['level_5_first_person'].append(sentence)
                continue

            # Level 1: Maximum distance (geographic/temporal framing)
            if re.search(r'\b(in the (city|kingdom|land|world) of|it was the (year|age|era)|once upon a time)\b', sentence, re.IGNORECASE):
                distance_samples['level_1_maximum'].append(sentence)
                continue

            # Level 4: Very close (third person + emotional vocabulary + no filters)
            has_third_person = bool(re.search(r'\b(she|he|her|his)\b', sentence, re.IGNORECASE))
            has_filter = bool(re.search(r'\b(felt|thought|saw|noticed)\b', sentence, re.IGNORECASE))
            has_emotional = bool(re.search(r'\b(heart|pulse|breath|chest)\b.*\b(pounded|raced|tightened|skipped)\b', sentence, re.IGNORECASE))

            if has_third_person and not has_filter and has_emotional:
                distance_samples['level_4_very_close'].append(sentence)
                continue

            # Level 3: Close (with filter words)
            if has_third_person and has_filter:
                distance_samples['level_3_close'].append(sentence)
                continue

            # Level 2: Distant (external description)
            if has_third_person:
                distance_samples['level_2_distant'].append(sentence)

        # Limit samples per level
        for level in distance_samples:
            distance_samples[level] = distance_samples[level][:10]

        return distance_samples

    def detect_genre(self, text: str, title: str) -> str:
        """Detect genre based on keyword frequency."""
        text_lower = text.lower()
        title_lower = title.lower()

        genre_scores = defaultdict(int)

        for genre, keywords in self.genre_keywords.items():
            for keyword in keywords:
                genre_scores[genre] += text_lower.count(keyword)
                genre_scores[genre] += title_lower.count(keyword) * 3  # Title has higher weight

        if not genre_scores:
            return 'unknown'

        return max(genre_scores, key=genre_scores.get)

    def process_epub(self, epub_path: Path) -> Dict:
        """Process a single EPUB file."""
        logger.info(f"Processing: {epub_path.name}")

        chapters = self.extract_text_from_epub(epub_path)

        if not chapters:
            return {}

        # Combine all chapter text for analysis
        full_text = '\n\n'.join([text for title, text in chapters])
        first_chapter_title = chapters[0][0] if chapters else "Unknown"

        # Detect genre
        genre = self.detect_genre(full_text, first_chapter_title)

        # Extract patterns
        fid_samples = self.detect_free_indirect_discourse(full_text)
        filter_samples = self.detect_filter_word_usage(full_text)
        show_samples = self.detect_show_dont_tell(full_text)
        distance_samples = self.classify_psychic_distance(full_text)

        return {
            'title': first_chapter_title,
            'genre': genre,
            'fid_count': len(fid_samples),
            'filter_count': len(filter_samples),
            'show_count': len(show_samples),
            'fid_samples': fid_samples[:5],  # Top 5
            'filter_samples': filter_samples[:3],  # Top 3
            'show_samples': show_samples[:5],  # Top 5
            'distance_samples': distance_samples,
        }

    def process_all_epubs(self, limit: int = None):
        """Process all EPUBs in INPUT directory."""
        epub_files = sorted(self.input_dir.glob("*.epub"))

        if limit:
            epub_files = epub_files[:limit]

        total = len(epub_files)
        logger.info(f"Found {total} EPUB files to process")

        processed_count = 0

        for i, epub_path in enumerate(epub_files, 1):
            logger.info(f"[{i}/{total}] {epub_path.name}")

            try:
                result = self.process_epub(epub_path)

                if result:
                    # Aggregate results
                    self.fid_patterns.extend(result.get('fid_samples', []))
                    self.filter_eliminations.extend(result.get('filter_samples', []))
                    self.show_dont_tell.extend(result.get('show_samples', []))

                    genre = result.get('genre', 'unknown')
                    for level, samples in result.get('distance_samples', {}).items():
                        self.psychic_distance_samples[level].extend(samples)

                    processed_count += 1

            except Exception as e:
                logger.error(f"Error processing {epub_path.name}: {e}")

        logger.info(f"Successfully processed {processed_count}/{total} EPUBs")

    def build_corpus_json(self) -> Dict:
        """Build final corpus JSON structure."""
        # Deduplicate and sort by quality
        fid_patterns_unique = self._deduplicate_samples(self.fid_patterns, key='sentence')
        fid_patterns_sorted = sorted(fid_patterns_unique, key=lambda x: x.get('fid_score', 0), reverse=True)

        show_patterns_unique = self._deduplicate_samples(self.show_dont_tell, key='sentence')

        corpus = {
            'metadata': {
                'version': '1.0',
                'generated': '2026-02-03',
                'source': 'Professional JP→EN EPUB translations (~130 volumes)',
                'total_fid_patterns': len(fid_patterns_sorted),
                'total_show_patterns': len(show_patterns_unique),
                'total_filter_samples': len(self.filter_eliminations),
            },

            'free_indirect_discourse_corpus': {
                'description': 'Real-world examples of Free Indirect Discourse in professional translations',
                'examples': fid_patterns_sorted[:50],  # Top 50 highest-scoring FID examples
            },

            'show_dont_tell_corpus': {
                'description': 'Physical manifestations of emotions (Show) instead of emotion labels (Tell)',
                'by_emotion': self._group_by_emotion(show_patterns_unique),
            },

            'filter_word_elimination_corpus': {
                'description': 'Examples of sentences with/without filter words for comparison',
                'samples': self.filter_eliminations[:30],
            },

            'psychic_distance_corpus': {
                'description': 'Sentences classified by psychic distance level (John Gardner scale)',
                'levels': {
                    level: samples[:15]  # Top 15 per level
                    for level, samples in self.psychic_distance_samples.items()
                },
            },
        }

        return corpus

    def _deduplicate_samples(self, samples: List[Dict], key: str) -> List[Dict]:
        """Remove duplicate samples based on key."""
        seen = set()
        unique = []

        for sample in samples:
            text = sample.get(key, '')
            if text and text not in seen:
                seen.add(text)
                unique.append(sample)

        return unique

    def _group_by_emotion(self, show_samples: List[Dict]) -> Dict:
        """Group Show samples by emotion type."""
        grouped = defaultdict(list)

        for sample in show_samples:
            emotion = sample.get('emotion', 'unknown')
            grouped[emotion].append({
                'sentence': sample.get('sentence'),
                'physical_indicator': sample.get('physical_indicator'),
            })

        # Limit per emotion
        return {emotion: samples[:10] for emotion, samples in grouped.items()}

    def save_corpus(self):
        """Save extracted corpus to JSON file."""
        corpus = self.build_corpus_json()

        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(corpus, f, indent=2, ensure_ascii=False)

        logger.info(f"Corpus saved to: {self.output_json}")
        logger.info(f"  - FID patterns: {corpus['metadata']['total_fid_patterns']}")
        logger.info(f"  - Show patterns: {corpus['metadata']['total_show_patterns']}")
        logger.info(f"  - Filter samples: {corpus['metadata']['total_filter_samples']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract narrative technique patterns from professional EPUB translations'
    )
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'INPUT',
        help='Directory containing EPUB files (default: pipeline/INPUT)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).parent.parent / 'config' / 'narrative_corpus_extracted.json',
        help='Output JSON file (default: config/narrative_corpus_extracted.json)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of EPUBs to process (for testing)'
    )

    args = parser.parse_args()

    if not args.input_dir.exists():
        logger.error(f"Input directory not found: {args.input_dir}")
        return

    extractor = NarrativeCorpusExtractor(args.input_dir, args.output)
    extractor.process_all_epubs(limit=args.limit)
    extractor.save_corpus()

    logger.info("✅ Corpus extraction complete!")


if __name__ == '__main__':
    main()
