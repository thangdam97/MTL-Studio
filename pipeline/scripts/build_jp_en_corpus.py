#!/usr/bin/env python3
"""
Build JP→EN Narrative Technique Corpus from Paired Translations.

Extracts real-world examples by comparing:
- Japanese source (JP/ markdown files)
- English transcreation (EN/ markdown files)

Identifies:
1. Free Indirect Discourse applications
2. Filter word elimination
3. Show Don't Tell transformations
4. Psychic distance adaptations
5. Emotional vocabulary choices

Author: MTL Studio
Date: 2026-02-03
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class JPENCorpusBuilder:
    def __init__(self, work_dir: Path, output_json: Path):
        self.work_dir = work_dir
        self.output_json = output_json

        # Corpus storage
        self.fid_examples = []
        self.filter_eliminations = []
        self.show_dont_tell = []
        self.emotional_vocabulary = []
        self.psychic_distance_shifts = []

        # Pattern detection
        self.filter_words = r'\b(felt|thought|saw|heard|noticed|wondered|sensed|realized)\b'
        self.emotional_physical = {
            'heart': r'\b(heart|pulse)\s+(pounded|raced|skipped|fluttered|tightened|ached)\b',
            'breath': r'\b(breath|breathing)\s+(caught|hitched|quickened|stopped|shallow)\b',
            'throat': r'\b(throat|voice)\s+(tightened|closed|choked|thick|constricted)\b',
            'hands': r'\b(hands|fingers|palms)\s+(trembled|shook|clenched|sweating|cold)\b',
            'eyes': r'\b(eyes|gaze)\s+(stinging|burning|widened|narrowed|darted)\b',
        }

    def find_volume_directories(self) -> List[Path]:
        """Find all volume work directories with JP and EN folders."""
        volume_dirs = []

        for item in self.work_dir.iterdir():
            if not item.is_dir():
                continue

            jp_dir = item / 'JP'
            en_dir = item / 'EN'

            if jp_dir.exists() and en_dir.exists():
                # Check if EN has content (not just empty/skeleton)
                en_files = list(en_dir.glob('CHAPTER_*.md'))
                if len(en_files) > 0:
                    volume_dirs.append(item)
                    logger.info(f"Found volume: {item.name} ({len(en_files)} chapters)")

        return volume_dirs

    def extract_chapter_pairs(self, volume_dir: Path) -> List[Tuple[Path, Path]]:
        """Extract JP-EN chapter pairs."""
        jp_dir = volume_dir / 'JP'
        en_dir = volume_dir / 'EN'

        pairs = []

        for jp_file in sorted(jp_dir.glob('CHAPTER_*.md')):
            chapter_id = jp_file.stem  # e.g., CHAPTER_01
            en_file = en_dir / f"{chapter_id}_EN.md"

            if en_file.exists():
                pairs.append((jp_file, en_file))

        return pairs

    def read_markdown_content(self, md_file: Path) -> List[str]:
        """Read markdown file and extract paragraphs."""
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Remove title/header
            content = re.sub(r'^#.*\n', '', content, flags=re.MULTILINE)

            # Split by double newlines (paragraphs)
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

            # Remove empty lines and markdown artifacts
            paragraphs = [
                p for p in paragraphs
                if p and not p.startswith('---') and len(p) > 10
            ]

            return paragraphs

        except Exception as e:
            logger.warning(f"Failed to read {md_file.name}: {e}")
            return []

    def align_paragraphs(self, jp_paras: List[str], en_paras: List[str]) -> List[Tuple[str, str]]:
        """
        Simple paragraph alignment (1:1 mapping).

        Note: This assumes translations maintain paragraph structure.
        For more complex alignment, would need sentence-level matching.
        """
        # Use minimum length to avoid index errors
        min_len = min(len(jp_paras), len(en_paras))

        aligned = []
        for i in range(min_len):
            jp_para = jp_paras[i]
            en_para = en_paras[i]

            # Filter out very short or very long mismatches
            jp_len = len(jp_para)
            en_len = len(en_para)

            # Reasonable length ratio (JP is typically 40-60% of EN length)
            ratio = en_len / jp_len if jp_len > 0 else 0

            if 0.3 <= ratio <= 3.0:  # Allow some flexibility
                aligned.append((jp_para, en_para))

        return aligned

    def detect_filter_elimination(self, en_para: str) -> Optional[Dict]:
        """
        Detect if EN paragraph successfully eliminates filter words.

        Returns pattern if paragraph shows direct perception without filters.
        """
        # Check if paragraph has emotional/perceptual content without filter words
        has_filter = bool(re.search(self.filter_words, en_para, re.IGNORECASE))

        # Check for emotional content
        has_emotional = any(
            re.search(pattern, en_para, re.IGNORECASE)
            for pattern in self.emotional_physical.values()
        )

        # Check for third-person narration
        has_third_person = bool(re.search(r'\b(she|he|her|his|him)\b', en_para, re.IGNORECASE))

        # Success: Emotional content WITHOUT filter words
        if has_emotional and not has_filter and has_third_person:
            return {
                'en_text': en_para,
                'has_emotional_content': True,
                'filter_words_eliminated': True,
                'technique': 'free_indirect_discourse'
            }

        return None

    def detect_show_dont_tell(self, jp_para: str, en_para: str) -> Optional[Dict]:
        """
        Detect Show Don't Tell transformations.

        Look for emotional descriptors in JP that become physical actions in EN.
        """
        # Japanese emotion markers (common patterns)
        jp_emotion_markers = {
            'angry': r'怒[りって]|腹.*立[つった]|ムカ',
            'sad': r'悲し[いかっ]|哀れ|憂鬱',
            'happy': r'嬉し[いかっ]|楽し[いかっ]|喜[びんで]',
            'nervous': r'緊張|不安|ドキドキ',
            'embarrassed': r'恥ずかし[いかっ]|照れ',
        }

        for emotion, jp_pattern in jp_emotion_markers.items():
            if re.search(jp_pattern, jp_para):
                # Check if EN shows physical manifestation instead of telling
                physical_pattern = self.emotional_physical.get(emotion.split('_')[0])

                # Look for physical descriptions in EN
                en_has_physical = any(
                    re.search(pattern, en_para, re.IGNORECASE)
                    for pattern in self.emotional_physical.values()
                )

                # Check if EN avoids direct emotion label
                emotion_labels = r'\b(angry|sad|happy|nervous|embarrassed|scared)\b'
                en_has_label = bool(re.search(emotion_labels, en_para, re.IGNORECASE))

                if en_has_physical and not en_has_label:
                    return {
                        'jp_text': jp_para,
                        'en_text': en_para,
                        'emotion_in_jp': emotion,
                        'physical_show_in_en': True,
                        'emotion_label_avoided': True,
                    }

        return None

    def detect_emotional_vocabulary_upgrade(self, jp_para: str, en_para: str) -> Optional[Dict]:
        """
        Detect when simple JP words become richer EN emotional vocabulary.

        Example: 綺麗 (kirei - pretty) → "breathtakingly beautiful"
        """
        # Common JP descriptors that often get upgraded
        jp_simple_descriptors = {
            '綺麗|美し[いかっ]': 'beautiful/pretty',
            '可愛[いかっ]': 'cute',
            '怖[いかっ]': 'scary',
            '嬉し[いかっ]': 'happy',
            '悲し[いかっ]': 'sad',
        }

        # EN poetic/literary vocabulary (indicates upgrade)
        en_literary_vocab = [
            r'\b(breathtaking|stunning|radiant|luminous|ethereal)\b',
            r'\b(melancholy|wistful|yearning|aching)\b',
            r'\b(enchanting|captivating|mesmerizing)\b',
            r'\b(tremulous|fragile|delicate)\b',
        ]

        for jp_pattern, jp_meaning in jp_simple_descriptors.items():
            if re.search(jp_pattern, jp_para):
                # Check if EN uses literary vocabulary
                for en_pattern in en_literary_vocab:
                    if re.search(en_pattern, en_para, re.IGNORECASE):
                        return {
                            'jp_text': jp_para,
                            'en_text': en_para,
                            'jp_simple': jp_meaning,
                            'en_literary': True,
                            'vocabulary_upgraded': True,
                        }

        return None

    def detect_psychic_distance_shift(self, jp_para: str, en_para: str) -> Optional[Dict]:
        """
        Detect changes in psychic distance between JP and EN.

        Often JP uses more distant narration, EN brings it closer.
        """
        # JP often uses という/と思う (quotative/thought markers) = more distant
        jp_has_quotative = bool(re.search(r'という|と思[うった]|のだ', jp_para))

        # EN close psychic distance: direct perception, no filters
        en_has_filter = bool(re.search(self.filter_words, en_para, re.IGNORECASE))
        en_has_emotional = any(
            re.search(pattern, en_para, re.IGNORECASE)
            for pattern in self.emotional_physical.values()
        )

        # Shift from distant (JP) to close (EN)
        if jp_has_quotative and en_has_emotional and not en_has_filter:
            return {
                'jp_text': jp_para,
                'en_text': en_para,
                'jp_distance': 'distant (quotative markers)',
                'en_distance': 'very_close (direct perception)',
                'shift_direction': 'jp_distant_to_en_close',
            }

        return None

    def process_chapter_pair(self, jp_file: Path, en_file: Path, volume_name: str):
        """Process a single JP-EN chapter pair."""
        logger.info(f"  Processing: {jp_file.name} → {en_file.name}")

        jp_paras = self.read_markdown_content(jp_file)
        en_paras = self.read_markdown_content(en_file)

        if not jp_paras or not en_paras:
            logger.warning(f"  Empty chapter: {jp_file.name}")
            return

        # Align paragraphs
        aligned = self.align_paragraphs(jp_paras, en_paras)
        logger.info(f"  Aligned {len(aligned)} paragraph pairs")

        chapter_id = jp_file.stem

        for jp_para, en_para in aligned:
            # Detect filter elimination
            filter_result = self.detect_filter_elimination(en_para)
            if filter_result:
                filter_result['source'] = f"{volume_name}/{chapter_id}"
                self.filter_eliminations.append(filter_result)

            # Detect show don't tell
            show_result = self.detect_show_dont_tell(jp_para, en_para)
            if show_result:
                show_result['source'] = f"{volume_name}/{chapter_id}"
                self.show_dont_tell.append(show_result)

            # Detect emotional vocabulary upgrade
            vocab_result = self.detect_emotional_vocabulary_upgrade(jp_para, en_para)
            if vocab_result:
                vocab_result['source'] = f"{volume_name}/{chapter_id}"
                self.emotional_vocabulary.append(vocab_result)

            # Detect psychic distance shift
            distance_result = self.detect_psychic_distance_shift(jp_para, en_para)
            if distance_result:
                distance_result['source'] = f"{volume_name}/{chapter_id}"
                self.psychic_distance_shifts.append(distance_result)

    def process_all_volumes(self):
        """Process all volume directories."""
        volume_dirs = self.find_volume_directories()

        if not volume_dirs:
            logger.warning("No volume directories found with both JP and EN content")
            return

        logger.info(f"Processing {len(volume_dirs)} volumes...")

        for volume_dir in volume_dirs:
            volume_name = volume_dir.name
            logger.info(f"\n=== {volume_name} ===")

            pairs = self.extract_chapter_pairs(volume_dir)
            logger.info(f"Found {len(pairs)} chapter pairs")

            for jp_file, en_file in pairs:
                self.process_chapter_pair(jp_file, en_file, volume_name)

    def build_corpus(self) -> Dict:
        """Build final corpus JSON."""
        # Deduplicate by text content
        fid_unique = self._deduplicate(self.filter_eliminations, 'en_text')
        show_unique = self._deduplicate(self.show_dont_tell, 'en_text')
        vocab_unique = self._deduplicate(self.emotional_vocabulary, 'en_text')
        distance_unique = self._deduplicate(self.psychic_distance_shifts, 'en_text')

        corpus = {
            'metadata': {
                'version': '1.0',
                'generated': '2026-02-03',
                'source': 'MTL Studio JP→EN paired translations',
                'description': 'Real-world examples of literary techniques applied in translation',
                'total_volumes_processed': len(self.find_volume_directories()),
            },

            'free_indirect_discourse': {
                'description': 'EN paragraphs showing direct perception without filter words (felt/saw/thought)',
                'instruction': 'Use character emotional vocabulary to describe reality directly, without mediation',
                'examples': fid_unique[:30],
            },

            'show_dont_tell_transformations': {
                'description': 'JP emotion labels transformed into EN physical manifestations',
                'instruction': 'When JP uses emotion words, translate as physical sensations/actions',
                'examples': show_unique[:30],
            },

            'emotional_vocabulary_upgrades': {
                'description': 'Simple JP descriptors becoming rich EN literary vocabulary',
                'instruction': 'Elevate simple adjectives to create atmosphere and emotional depth',
                'examples': vocab_unique[:30],
            },

            'psychic_distance_shifts': {
                'description': 'JP distant narration brought closer in EN (Free Indirect Discourse)',
                'instruction': 'Remove quotative markers and thought-reporting to create intimacy',
                'examples': distance_unique[:30],
            },
        }

        return corpus

    def _deduplicate(self, items: List[Dict], key: str) -> List[Dict]:
        """Remove duplicates based on text content."""
        seen = set()
        unique = []

        for item in items:
            text = item.get(key, '')
            # Use first 100 chars as fingerprint
            fingerprint = text[:100] if text else ''

            if fingerprint and fingerprint not in seen:
                seen.add(fingerprint)
                unique.append(item)

        return unique

    def save_corpus(self):
        """Save corpus to JSON."""
        corpus = self.build_corpus()

        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(corpus, f, indent=2, ensure_ascii=False)

        logger.info(f"\n✅ Corpus saved: {self.output_json}")
        logger.info(f"  - Free Indirect Discourse examples: {len(corpus['free_indirect_discourse']['examples'])}")
        logger.info(f"  - Show Don't Tell examples: {len(corpus['show_dont_tell_transformations']['examples'])}")
        logger.info(f"  - Vocabulary upgrades: {len(corpus['emotional_vocabulary_upgrades']['examples'])}")
        logger.info(f"  - Psychic distance shifts: {len(corpus['psychic_distance_shifts']['examples'])}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Build JP→EN narrative technique corpus from paired translations'
    )
    parser.add_argument(
        '--work-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'WORK',
        help='WORK directory containing volume folders (default: pipeline/WORK)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).parent.parent / 'config' / 'jp_en_narrative_corpus.json',
        help='Output corpus JSON (default: config/jp_en_narrative_corpus.json)'
    )

    args = parser.parse_args()

    if not args.work_dir.exists():
        logger.error(f"WORK directory not found: {args.work_dir}")
        return

    builder = JPENCorpusBuilder(args.work_dir, args.output)
    builder.process_all_volumes()
    builder.save_corpus()


if __name__ == '__main__':
    main()
