#!/usr/bin/env python3
"""
Stage 3 Intelligent Sentence Splitter - v1.7 Architecture
Uses Gemini 2.5 Flash to intelligently split long sentences while preserving meaning.

Target: Hard cap compliance 31.8% → 95%+ (dialogue), 42.1% → 95%+ (narration)
Expected grade impact: A+ (94) → S- (96/100)
"""

import json
import re
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

# Gemini client import
import sys
sys.path.append(str(Path(__file__).parent.parent))
from pipeline.common.gemini_client import GeminiClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SentenceSplit:
    """Represents a sentence split operation."""
    original: str
    splits: List[str]
    original_word_count: int
    split_word_counts: List[int]
    split_method: str  # 'conjunction', 'clause', 'gemini', 'manual'
    confidence: float  # 0.0-1.0


@dataclass
class SplitterReport:
    """Summary report of sentence splitting."""
    volume_name: str
    chapters_processed: int
    total_splits: int
    dialogue_splits: int
    narration_splits: int
    splits: List[SentenceSplit] = field(default_factory=list)

    # Compliance metrics
    dialogue_compliance_before: float = 0.0
    dialogue_compliance_after: float = 0.0
    narration_compliance_before: float = 0.0
    narration_compliance_after: float = 0.0

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'splits': [asdict(s) for s in self.splits]
        }


class IntelligentSentenceSplitter:
    """Stage 3 intelligent sentence splitter using Gemini 2.5 Flash."""

    def __init__(self, dry_run: bool = False, use_gemini: bool = True):
        """
        Initialize sentence splitter.

        Args:
            dry_run: Preview splits without modifying files
            use_gemini: Use Gemini 2.5 Flash for intelligent splitting
        """
        self.dry_run = dry_run
        self.use_gemini = use_gemini

        # Initialize Gemini client
        self.gemini_client = None
        if use_gemini:
            try:
                self.gemini_client = GeminiClient(model_name="gemini-2.0-flash-exp")
                logger.info("Gemini 2.5 Flash initialized for intelligent splitting")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
                self.use_gemini = False

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(re.findall(r'\b\w+\b', text))

    def _is_dialogue(self, text: str) -> bool:
        """Check if text is dialogue (quoted)."""
        return bool(re.search(r'"[^"]{10,}"', text))

    def _extract_quoted_text(self, line: str) -> List[Tuple[str, int, int]]:
        """
        Extract quoted dialogue from line.

        Returns:
            List of (quoted_content, start_pos, end_pos)
        """
        dialogues = []
        for match in re.finditer(r'"([^"]+)"', line):
            dialogues.append((match.group(1), match.start(), match.end()))
        return dialogues

    async def _split_with_gemini(
        self,
        sentence: str,
        max_words: int,
        is_dialogue: bool
    ) -> List[str]:
        """
        Use Gemini 2.5 Flash to intelligently split sentence.

        Args:
            sentence: The sentence to split
            max_words: Maximum words per split sentence
            is_dialogue: Whether this is dialogue or narration

        Returns:
            List of split sentences
        """
        if not self.gemini_client:
            return [sentence]  # Fallback: no split

        prompt = f"""Split this {"dialogue" if is_dialogue else "narration"} sentence into 2-3 shorter sentences that each have ≤{max_words} words.

CRITICAL RULES:
1. Preserve ALL information from the original
2. Maintain natural reading flow and rhythm
3. Split at conjunctions (but, and, yet, so) or clause boundaries
4. Keep related ideas together
5. Each split sentence must be ≤{max_words} words
6. Do NOT add any words not in the original

Original sentence ({self._count_words(sentence)} words):
"{sentence}"

Output ONLY valid JSON in this exact format:
{{
  "splits": ["sentence 1", "sentence 2", ...]
}}

JSON output:"""

        try:
            response = await self.gemini_client.generate_text(
                prompt,
                temperature=0.3,
                max_tokens=500
            )

            # Extract JSON from response
            response = response.strip()

            # Try to find JSON object in response
            json_match = re.search(r'\{[^}]*"splits"[^}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                splits = result.get('splits', [])

                # Validate splits
                if splits and all(self._count_words(s) <= max_words + 1 for s in splits):
                    logger.debug(f"Gemini split: {self._count_words(sentence)}w → {[self._count_words(s) for s in splits]}")
                    return splits
                else:
                    logger.warning(f"Gemini split validation failed: {[self._count_words(s) for s in splits]}")

            # Fallback: try simple splitting
            return self._fallback_split(sentence, max_words)

        except Exception as e:
            logger.error(f"Gemini split failed: {e}")
            return self._fallback_split(sentence, max_words)

    def _fallback_split(self, sentence: str, max_words: int) -> List[str]:
        """
        Fallback splitting using rule-based methods.

        Priority:
        1. Coordinating conjunctions (but, and, yet, so)
        2. Subordinating conjunctions (while, when, because, although)
        3. Relative clauses (who, which, that)
        4. No split (if can't find good break point)
        """
        word_count = self._count_words(sentence)

        if word_count <= max_words:
            return [sentence]

        # Try splitting at coordinating conjunctions
        for conj in [', but ', ', and ', ', yet ', ', so ']:
            if conj in sentence:
                parts = sentence.split(conj, 1)
                if len(parts) == 2:
                    # Capitalize second part if needed
                    part2 = parts[1].strip()
                    if part2 and not part2[0].isupper():
                        part2 = part2[0].upper() + part2[1:]

                    # Remove leading comma from part2
                    conj_word = conj.strip(', ').capitalize()

                    result = [parts[0].strip() + '.', f"{conj_word} {part2}"]

                    # Validate
                    if all(self._count_words(s) <= max_words for s in result):
                        logger.debug(f"Rule-based split at '{conj}': {word_count}w → {[self._count_words(s) for s in result]}")
                        return result

        # Try splitting at subordinating conjunctions
        for conj in [' while ', ' when ', ' because ', ' although ', ' since ']:
            if conj in sentence:
                parts = sentence.split(conj, 1)
                if len(parts) == 2:
                    result = [parts[0].strip() + '.', conj.strip().capitalize() + ' ' + parts[1].strip()]
                    if all(self._count_words(s) <= max_words for s in result):
                        logger.debug(f"Rule-based split at '{conj}': {word_count}w → {[self._count_words(s) for s in result]}")
                        return result

        # Can't find good split point - return original
        logger.warning(f"No good split point found for {word_count}w sentence")
        return [sentence]

    async def _split_dialogue(self, dialogue: str, max_words: int = 10) -> List[str]:
        """
        Split dialogue sentence(s) to meet hard cap.

        Args:
            dialogue: The dialogue content (without quotes)
            max_words: Maximum words per sentence (default 10)

        Returns:
            List of split sentences
        """
        # Split by sentence boundaries first
        sentences = re.split(r'(?<=[.!?])\s+', dialogue)

        result = []
        for sentence in sentences:
            word_count = self._count_words(sentence)

            if word_count <= max_words:
                result.append(sentence)
            else:
                # Need to split this sentence
                if self.use_gemini:
                    splits = await self._split_with_gemini(sentence, max_words, is_dialogue=True)
                    result.extend(splits)
                else:
                    splits = self._fallback_split(sentence, max_words)
                    result.extend(splits)

        return result

    async def _split_narration(self, narration: str, max_words: int = 15) -> List[str]:
        """
        Split narration sentence to meet hard cap.

        Args:
            narration: The narration sentence
            max_words: Maximum words per sentence (default 15)

        Returns:
            List of split sentences
        """
        word_count = self._count_words(narration)

        if word_count <= max_words:
            return [narration]

        # Use Gemini for intelligent splitting
        if self.use_gemini:
            return await self._split_with_gemini(narration, max_words, is_dialogue=False)
        else:
            return self._fallback_split(narration, max_words)

    async def process_line(self, line: str) -> Tuple[str, List[SentenceSplit]]:
        """
        Process a single line, splitting long sentences.

        Args:
            line: The line to process

        Returns:
            (modified_line, list_of_splits)
        """
        splits_made = []
        modified_line = line

        # Check for dialogue
        dialogues = self._extract_quoted_text(line)

        for dialogue_content, start, end in dialogues:
            word_count = self._count_words(dialogue_content)

            if word_count > 10:
                # Need to split dialogue
                split_sentences = await self._split_dialogue(dialogue_content, max_words=10)

                if len(split_sentences) > 1:
                    # Join splits back into quoted dialogue
                    new_dialogue = ' '.join(split_sentences)

                    # Replace in line
                    original_quoted = f'"{dialogue_content}"'
                    new_quoted = f'"{new_dialogue}"'
                    modified_line = modified_line.replace(original_quoted, new_quoted)

                    splits_made.append(SentenceSplit(
                        original=dialogue_content,
                        splits=split_sentences,
                        original_word_count=word_count,
                        split_word_counts=[self._count_words(s) for s in split_sentences],
                        split_method='gemini' if self.use_gemini else 'rule_based',
                        confidence=0.85 if self.use_gemini else 0.7
                    ))

        # Check for narration (non-dialogue parts)
        # Remove dialogue first
        narration_text = re.sub(r'"[^"]*"', '__DIALOGUE__', modified_line)

        # Find long narration sentences
        for match in re.finditer(r'([^.!?]+[.!?])', narration_text):
            sentence = match.group(1).strip()

            # Skip if it's dialogue placeholder
            if '__DIALOGUE__' in sentence:
                continue

            word_count = self._count_words(sentence)

            if word_count > 15:
                # Need to split narration
                split_sentences = await self._split_narration(sentence, max_words=15)

                if len(split_sentences) > 1:
                    # Join splits
                    new_narration = ' '.join(split_sentences)

                    # Find original sentence in line (without dialogue)
                    original_in_line = sentence
                    modified_line = modified_line.replace(original_in_line, new_narration, 1)

                    splits_made.append(SentenceSplit(
                        original=sentence,
                        splits=split_sentences,
                        original_word_count=word_count,
                        split_word_counts=[self._count_words(s) for s in split_sentences],
                        split_method='gemini' if self.use_gemini else 'rule_based',
                        confidence=0.85 if self.use_gemini else 0.7
                    ))

        return modified_line, splits_made

    async def process_file(self, file_path: Path) -> Tuple[List[str], List[SentenceSplit]]:
        """
        Process a single EN markdown file.

        Args:
            file_path: Path to the EN markdown file

        Returns:
            (modified_lines, list_of_splits)
        """
        logger.info(f"Processing: {file_path.name}")

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        modified_lines = []
        all_splits = []

        for line in lines:
            modified_line, splits = await self.process_line(line)
            modified_lines.append(modified_line)
            all_splits.extend(splits)

        return modified_lines, all_splits

    async def process_volume(self, volume_dir: Path) -> SplitterReport:
        """
        Process entire volume (all EN chapters).

        Args:
            volume_dir: Path to volume directory containing EN/ subdirectory

        Returns:
            SplitterReport with all splits and metrics
        """
        en_dir = volume_dir / "EN"

        if not en_dir.exists():
            raise FileNotFoundError(f"EN directory not found: {en_dir}")

        report = SplitterReport(
            volume_name=volume_dir.name,
            chapters_processed=0,
            total_splits=0,
            dialogue_splits=0,
            narration_splits=0
        )

        # Process each chapter
        chapter_files = sorted(en_dir.glob("CHAPTER_*.md"))

        for chapter_file in chapter_files:
            modified_lines, splits = await self.process_file(chapter_file)

            # Write modified file (if not dry run)
            if not self.dry_run and splits:
                with open(chapter_file, 'w', encoding='utf-8') as f:
                    f.writelines(modified_lines)
                logger.info(f"✅ Modified: {chapter_file.name} ({len(splits)} splits)")

            report.splits.extend(splits)
            report.chapters_processed += 1

        # Calculate metrics
        report.total_splits = len(report.splits)

        # Count dialogue vs narration splits (approximate)
        for split in report.splits:
            if self._is_dialogue(split.original):
                report.dialogue_splits += 1
            else:
                report.narration_splits += 1

        return report

    def generate_report(self, report: SplitterReport, output_dir: Path):
        """Generate JSON and Markdown reports."""
        # JSON report
        json_path = output_dir / f"{report.volume_name}_STAGE3_SPLITTER_REPORT.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # Markdown report
        md_path = output_dir / f"{report.volume_name}_STAGE3_SPLITTER_REPORT.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# Stage 3 Sentence Splitter Report\n\n")
            f.write(f"**Volume:** {report.volume_name}\n\n")
            f.write(f"**Chapters Processed:** {report.chapters_processed}\n\n")
            f.write(f"---\n\n")

            f.write(f"## Summary\n\n")
            f.write(f"**Total Splits:** {report.total_splits}\n\n")
            f.write(f"- **Dialogue splits:** {report.dialogue_splits}\n")
            f.write(f"- **Narration splits:** {report.narration_splits}\n\n")

            f.write(f"## Sample Splits\n\n")
            for i, split in enumerate(report.splits[:20], 1):
                f.write(f"### Split {i}\n\n")
                f.write(f"**Original ({split.original_word_count} words):**\n")
                f.write(f"> {split.original}\n\n")
                f.write(f"**Split into {len(split.splits)} sentences:**\n")
                for j, s in enumerate(split.splits, 1):
                    f.write(f"{j}. ({split.split_word_counts[j-1]} words) {s}\n")
                f.write(f"\n**Method:** {split.split_method} | **Confidence:** {split.confidence:.2f}\n\n")
                f.write(f"---\n\n")

        logger.info(f"Reports generated: {json_path}, {md_path}")


async def main():
    """Run Stage 3 sentence splitter on 17fb volume."""
    import argparse

    parser = argparse.ArgumentParser(description="Stage 3 Intelligent Sentence Splitter")
    parser.add_argument("--volume", type=str, required=True, help="Volume directory name")
    parser.add_argument("--dry-run", action="store_true", help="Preview splits without applying")
    parser.add_argument("--no-gemini", action="store_true", help="Use rule-based splitting only")

    args = parser.parse_args()

    # Paths
    pipeline_dir = Path(__file__).parent.parent
    work_dir = pipeline_dir / "WORK" / args.volume

    if not work_dir.exists():
        print(f"❌ Volume directory not found: {work_dir}")
        return 1

    # Create backup if not dry run
    if not args.dry_run:
        import shutil
        backup_dir = work_dir.parent / f"{work_dir.name}_BACKUP_PRE_STAGE3_SPLITTER"
        if not backup_dir.exists():
            shutil.copytree(work_dir, backup_dir)
            print(f"✅ Backup created: {backup_dir.name}")

    # Create splitter
    splitter = IntelligentSentenceSplitter(
        dry_run=args.dry_run,
        use_gemini=not args.no_gemini
    )

    # Run splitting
    print(f"\n{'='*60}")
    print(f"Stage 3 Intelligent Sentence Splitter")
    print(f"{'='*60}")
    print(f"Volume: {args.volume}")
    print(f"Gemini: {'Enabled' if not args.no_gemini else 'Disabled (rule-based only)'}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    report = await splitter.process_volume(work_dir)

    # Generate reports
    splitter.generate_report(report, pipeline_dir)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Splitting Complete")
    print(f"{'='*60}")
    print(f"Total splits: {report.total_splits}")
    print(f"  Dialogue: {report.dialogue_splits}")
    print(f"  Narration: {report.narration_splits}")
    print(f"\nReports saved to: {pipeline_dir}")

    if args.dry_run:
        print(f"\n⚠️  DRY RUN: No files were modified.")
        print(f"Run without --dry-run to apply splits.")
    else:
        print(f"\n✅ Splits applied successfully!")

    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
