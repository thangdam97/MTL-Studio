"""
Enhanced CJK Artifact Cleaner v2.0 - LLM-powered sentence-level correction.

Major improvements over v1:
1. Full sentence extraction for better context
2. KanjiAPI integration for character validation
3. Gemini 2.5 Flash LLM-based correction
4. Smarter detection with semantic understanding

Use this when Japanese text contains stray Chinese characters from EPUB extraction.
"""

import re
import json
import requests
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from pipeline.common.gemini_client import GeminiClient
except ImportError:
    GeminiClient = None

try:
    from pipeline.post_processor.cjk_unicode_detector import (
        ComprehensiveCJKDetector, CJKBlock, CJKCharInfo
    )
except ImportError:
    ComprehensiveCJKDetector = None
    CJKBlock = None
    CJKCharInfo = None

try:
    from pipeline.post_processor.multi_script_detector import (
        MultiScriptDetector, ScriptArtifact, ScriptFamily
    )
except ImportError:
    MultiScriptDetector = None
    ScriptArtifact = None
    ScriptFamily = None


@dataclass
class CJKArtifactV2:
    """Enhanced artifact for foreign characters (CJK, Cyrillic, Arabic, etc.)."""
    line_number: int
    char: str
    char_unicode: str
    unicode_block: Optional[str] = None  # Unicode block/script name
    block_rarity: Optional[str] = None   # Common/Rare/Very Rare
    script_family: Optional[str] = None  # NEW: CJK/Cyrillic/Arabic/etc.
    llm_hallucination: bool = False      # NEW: Likely from LLM hallucination
    sentence: str = ""
    position_in_sentence: int = 0
    confidence: float = 0.0
    reason: str = ""
    kanji_api_data: Optional[Dict] = None
    suggested_correction: Optional[str] = None
    encoding_hints: Optional[List[str]] = None


class KanjiValidator:
    """Validates CJK characters using KanjiAPI (https://kanjiapi.dev)."""

    BASE_URL = "https://kanjiapi.dev/v1"

    @classmethod
    def lookup_kanji(cls, char: str) -> Optional[Dict]:
        """
        Look up kanji information from KanjiAPI.

        Args:
            char: Single kanji character

        Returns:
            Dictionary with kanji info or None if not found
        """
        try:
            url = f"{cls.BASE_URL}/kanji/{char}"
            response = requests.get(url, timeout=3)

            if response.status_code == 200:
                data = response.json()
                return {
                    "kanji": data.get("kanji"),
                    "meanings": data.get("meanings", []),
                    "kun_readings": data.get("kun_readings", []),
                    "on_readings": data.get("on_readings", []),
                    "jlpt_level": data.get("jlpt"),
                    "grade": data.get("grade"),
                    "is_common": data.get("jlpt") is not None or data.get("grade") is not None
                }
            return None
        except Exception:
            return None


class EnhancedCJKCleaner:
    """
    Enhanced CJK artifact cleaner with LLM-powered correction.

    Features:
    - Full sentence extraction for context
    - KanjiAPI validation for character legitimacy
    - Gemini 2.5 Flash for intelligent correction
    - Preserves sentence structure and meaning
    """

    # Inherited from v1 - Known Chinese-only characters
    CHINESE_ONLY_CHARS = set("""
        爲這個們嗎呢啊吧喔哦唄咧啦哪誰係喺啲嘅嗰噉乜咁點樣邊
        冇未曾經緊住咗過喇啩囉啫嚟佢哋你妳您俺咱阮伲偌倆仨
    """.replace('\n', '').replace(' ', ''))

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        min_confidence: float = 0.70,
        use_kanji_api: bool = True,
        use_llm_correction: bool = True,
        use_comprehensive_unicode: bool = True,
        detect_all_scripts: bool = True
    ):
        """
        Initialize enhanced foreign script cleaner.

        Args:
            gemini_client: Gemini client for LLM correction (if None, creates new)
            min_confidence: Minimum confidence threshold for flagging (0.0-1.0)
            use_kanji_api: Whether to validate with KanjiAPI
            use_llm_correction: Whether to use LLM for correction suggestions
            use_comprehensive_unicode: Use comprehensive Unicode detector (all CJK blocks)
            detect_all_scripts: Detect ALL foreign scripts (Cyrillic, Arabic, etc.)
        """
        self.min_confidence = min_confidence
        self.use_kanji_api = use_kanji_api
        self.use_llm_correction = use_llm_correction
        self.use_comprehensive_unicode = use_comprehensive_unicode
        self.detect_all_scripts = detect_all_scripts

        # Initialize Gemini client for corrections
        if use_llm_correction and GeminiClient:
            self.gemini_client = gemini_client or GeminiClient()
        else:
            self.gemini_client = None

        # Initialize comprehensive Unicode detector
        if use_comprehensive_unicode and ComprehensiveCJKDetector:
            self.unicode_detector = ComprehensiveCJKDetector(strict_mode=False)
        else:
            self.unicode_detector = None

        # Initialize multi-script detector
        if detect_all_scripts and MultiScriptDetector:
            self.multi_script_detector = MultiScriptDetector(use_cjk_detector=False)
        else:
            self.multi_script_detector = None

    def extract_sentence(self, text: str, char_position: int) -> Tuple[str, int]:
        """
        Extract the full sentence containing the character at given position.

        Sentence boundaries:
        - Japanese: 。！？
        - Newlines

        Args:
            text: Full text
            char_position: Position of the suspicious character

        Returns:
            Tuple of (sentence, position_in_sentence)
        """
        # Japanese sentence delimiters
        sentence_delimiters = '。！？\n'

        # Find start of sentence
        start = char_position
        while start > 0 and text[start - 1] not in sentence_delimiters:
            start -= 1

        # Find end of sentence
        end = char_position
        while end < len(text) and text[end] not in sentence_delimiters:
            end += 1

        # Include the ending delimiter if present
        if end < len(text) and text[end] in sentence_delimiters:
            end += 1

        sentence = text[start:end].strip()
        position_in_sentence = char_position - start

        return sentence, position_in_sentence

    def detect_artifacts(self, text: str) -> List[CJKArtifactV2]:
        """
        Detect ALL foreign script artifacts (CJK, Cyrillic, Arabic, etc.).

        Uses:
        1. Comprehensive Unicode detection for ALL CJK blocks
        2. Multi-script detection for Cyrillic, Arabic, Hebrew, etc.

        Args:
            text: Text to analyze

        Returns:
            List of detected artifacts (CJK + all other foreign scripts)
        """
        # Strip THINKING logs before detection
        text = self._strip_thinking_logs(text)

        artifacts = []

        # Detect CJK artifacts
        if self.use_comprehensive_unicode and self.unicode_detector:
            artifacts.extend(self._detect_with_comprehensive_unicode(text))
        else:
            artifacts.extend(self._detect_legacy(text))

        # Detect other foreign scripts (Cyrillic, Arabic, etc.)
        if self.detect_all_scripts and self.multi_script_detector:
            artifacts.extend(self._detect_other_scripts(text))

        # Sort by line number
        artifacts.sort(key=lambda a: (a.line_number, a.position_in_sentence))

        # Generate LLM corrections for all artifacts
        if self.use_llm_correction and artifacts and self.gemini_client:
            self._generate_llm_corrections(artifacts)

        return artifacts

    def _detect_other_scripts(self, text: str) -> List[CJKArtifactV2]:
        """Detect non-CJK foreign scripts (Cyrillic, Arabic, etc.)."""
        artifacts = []

        # Use multi-script detector
        script_artifacts = self.multi_script_detector.detect_all_foreign_scripts(text)

        for script_artifact in script_artifacts:
            # Skip CJK (already handled)
            if script_artifact.script.family == "CJK":
                continue

            # Convert to CJKArtifactV2 format
            artifact = CJKArtifactV2(
                line_number=script_artifact.line_number,
                char=script_artifact.char,
                char_unicode=f"U+{script_artifact.codepoint:04X}",
                unicode_block=script_artifact.script.script_name,
                block_rarity="Foreign Script",
                script_family=script_artifact.script.family,
                llm_hallucination=script_artifact.llm_hallucination_likely,
                sentence=script_artifact.sentence,
                position_in_sentence=script_artifact.position_in_sentence,
                confidence=script_artifact.suspicion_score,
                reason=script_artifact.reason,
                kanji_api_data=None,
                encoding_hints=[script_artifact.script.family]
            )

            artifacts.append(artifact)

        return artifacts

    def _detect_with_comprehensive_unicode(self, text: str) -> List[CJKArtifactV2]:
        """Detect artifacts using comprehensive Unicode detector."""
        artifacts = []
        lines = text.split('\n')
        cumulative_pos = 0

        # Get all CJK characters in text
        all_cjk = self.unicode_detector.detect_all_cjk(text)

        for cjk_info in all_cjk:
            # Find position in text
            char_pos = text.find(cjk_info.char, cumulative_pos)
            if char_pos == -1:
                continue

            # Find line number
            line_num = text[:char_pos].count('\n') + 1
            pos_in_line = char_pos - text[:char_pos].rfind('\n') - 1

            # Get context
            left = text[max(0, char_pos - 5):char_pos]
            right = text[char_pos + 1:min(len(text), char_pos + 6)]

            # Calculate suspicion using comprehensive detector
            suspicion, reason = self.unicode_detector.calculate_suspicion(
                cjk_info.char, left, right, cjk_info.block
            )

            if suspicion < self.min_confidence:
                continue

            # Extract full sentence
            sentence, pos_in_sent = self.extract_sentence(text, char_pos)

            # KanjiAPI validation (optional enhancement)
            kanji_data = None
            if self.use_kanji_api:
                kanji_data = KanjiValidator.lookup_kanji(cjk_info.char)
                if kanji_data and kanji_data.get("is_common"):
                    # Reduce suspicion for common Japanese kanji
                    suspicion *= 0.5
                    reason += " (but is common Japanese kanji)"
                    if suspicion < self.min_confidence:
                        continue

            # Create enhanced artifact with Unicode block info
            artifact = CJKArtifactV2(
                line_number=line_num,
                char=cjk_info.char,
                char_unicode=f"U+{cjk_info.codepoint:04X}",
                unicode_block=cjk_info.block.block_name,
                block_rarity=cjk_info.block.rarity,
                script_family="CJK",
                llm_hallucination=False,  # CJK usually from source text, not LLM
                sentence=sentence,
                position_in_sentence=pos_in_sent,
                confidence=suspicion,
                reason=reason,
                kanji_api_data=kanji_data,
                encoding_hints=cjk_info.encoding_hints
            )

            artifacts.append(artifact)

        # Generate LLM corrections
        if self.use_llm_correction and artifacts and self.gemini_client:
            self._generate_llm_corrections(artifacts)

        return artifacts

    def _detect_legacy(self, text: str) -> List[CJKArtifactV2]:
        """Legacy detection method (U+4E00-U+9FFF only)."""
        artifacts = []
        lines = text.split('\n')
        cumulative_pos = 0

        for line_num, line in enumerate(lines, 1):
            # Find all CJK Unified Ideographs (basic range only)
            for match in re.finditer(r'[\u4E00-\u9FFF]', line):
                char = match.group()
                pos_in_line = match.start()
                pos_in_text = cumulative_pos + pos_in_line

                # Quick filter
                if char in '一二三四五六七八九十日月年時分人大小中学生':
                    continue

                # Check Chinese-only
                if char not in self.CHINESE_ONLY_CHARS:
                    left = line[max(0, pos_in_line - 2):pos_in_line]
                    right = line[pos_in_line + 1:min(len(line), pos_in_line + 3)]
                    if self._has_kana(left) or self._has_kana(right):
                        continue

                sentence, pos_in_sent = self.extract_sentence(text, pos_in_text)
                confidence, reason = self._calculate_confidence(char, line, pos_in_line)

                if confidence < self.min_confidence:
                    continue

                # KanjiAPI validation
                kanji_data = None
                if self.use_kanji_api:
                    kanji_data = KanjiValidator.lookup_kanji(char)
                    if kanji_data and kanji_data.get("is_common"):
                        confidence *= 0.5
                        reason += " (but is common Japanese kanji)"
                        if confidence < self.min_confidence:
                            continue

                artifact = CJKArtifactV2(
                    line_number=line_num,
                    char=char,
                    char_unicode=f"U+{ord(char):04X}",
                    unicode_block="CJK Unified Ideographs",
                    block_rarity="Common",
                    script_family="CJK",
                    llm_hallucination=False,
                    sentence=sentence,
                    position_in_sentence=pos_in_sent,
                    confidence=confidence,
                    reason=reason,
                    kanji_api_data=kanji_data
                )

                artifacts.append(artifact)

            cumulative_pos += len(line) + 1

        if self.use_llm_correction and artifacts and self.gemini_client:
            self._generate_llm_corrections(artifacts)

        return artifacts

    def _has_kana(self, text: str) -> bool:
        """Check if text contains hiragana or katakana."""
        if not text:
            return False
        for char in text:
            code = ord(char)
            if (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF):
                return True
        return False

    def _strip_thinking_logs(self, text: str) -> str:
        """
        Remove THINKING log blocks from text before CJK detection.

        THINKING logs contain foreign scripts for analysis purposes
        and should not be flagged as artifacts in the translation output.

        Args:
            text: Input text potentially containing THINKING blocks

        Returns:
            Text with all THINKING blocks removed
        """
        import re

        # Pattern to match THINKING blocks:
        # <THINKING>...</THINKING> or <thinking>...</thinking>
        thinking_pattern = r'<THINKING>.*?</THINKING>'

        # Remove all THINKING blocks (case-insensitive, multiline)
        cleaned_text = re.sub(thinking_pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

        return cleaned_text

    def _calculate_confidence(self, char: str, line: str, pos: int) -> Tuple[float, str]:
        """
        Calculate confidence that this is a Chinese artifact.

        Args:
            char: The character
            line: The full line
            pos: Position in line

        Returns:
            Tuple of (confidence, reason)
        """
        score = 0.0
        reasons = []

        # Factor 1: Known Chinese-only character
        if char in self.CHINESE_ONLY_CHARS:
            score += 0.6
            reasons.append("Chinese-only char")

        # Factor 2: No kana neighbors
        left = line[max(0, pos - 3):pos]
        right = line[pos + 1:min(len(line), pos + 4)]

        if not self._has_kana(left) and not self._has_kana(right):
            score += 0.3
            reasons.append("No kana neighbors")

        # Factor 3: Surrounded by punctuation or spaces
        if left and left[-1] in ' \t,.:;!?「」『』（）':
            score += 0.1
            reasons.append("Preceded by punctuation")

        if right and right[0] in ' \t,.:;!?「」『』（）':
            score += 0.1
            reasons.append("Followed by punctuation")

        reason = "; ".join(reasons) if reasons else "Suspicious context"
        return min(score, 1.0), reason

    def _generate_llm_corrections(self, artifacts: List[CJKArtifactV2]) -> None:
        """
        Use Gemini 2.5 Flash to suggest corrections for artifacts.

        Args:
            artifacts: List of artifacts to correct (modified in-place)
        """
        if not self.gemini_client:
            return

        # Batch correction for efficiency
        batch_size = 10
        for i in range(0, len(artifacts), batch_size):
            batch = artifacts[i:i + batch_size]

            # Build prompt
            prompt = self._build_correction_prompt(batch)

            try:
                # Use Gemini 2.5 Flash for fast correction
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-exp",
                    contents=prompt
                )

                # Parse corrections
                corrections = self._parse_corrections(response.text, batch)

                # Apply corrections
                for artifact, correction in zip(batch, corrections):
                    artifact.suggested_correction = correction

            except Exception as e:
                # If LLM fails, skip corrections
                for artifact in batch:
                    artifact.suggested_correction = f"[LLM correction failed: {e}]"

    def _build_correction_prompt(self, artifacts: List[CJKArtifactV2]) -> str:
        """Build prompt for LLM correction."""
        prompt_parts = [
            "You are a Japanese text correction specialist. The following sentences contain stray Chinese characters that leaked into Japanese text during EPUB extraction.",
            "",
            "For each sentence, provide a corrected version by:",
            "1. Removing the Chinese character entirely if it's clearly noise",
            "2. Replacing it with the correct Japanese kanji if identifiable from context",
            "3. Keeping it if it's actually valid Japanese (but mark as [KEEP])",
            "",
            "Format: Return ONLY the corrected sentences, one per line, in order.",
            "",
            "=== Artifacts to Correct ===",
            ""
        ]

        for idx, artifact in enumerate(artifacts, 1):
            prompt_parts.append(f"{idx}. Line {artifact.line_number}:")
            prompt_parts.append(f"   Sentence: {artifact.sentence}")
            prompt_parts.append(f"   Suspicious char: '{artifact.char}' ({artifact.char_unicode})")
            if artifact.kanji_api_data:
                meanings = artifact.kanji_api_data.get("meanings", [])
                if meanings:
                    prompt_parts.append(f"   Meanings (if Japanese): {', '.join(meanings[:3])}")
            prompt_parts.append("")

        prompt_parts.append("=== Corrected Sentences (one per line) ===")

        return "\n".join(prompt_parts)

    def _parse_corrections(self, llm_response: str, artifacts: List[CJKArtifactV2]) -> List[str]:
        """
        Parse LLM response into corrections.

        Args:
            llm_response: Raw LLM output
            artifacts: Original artifacts

        Returns:
            List of correction strings
        """
        # Extract lines from response
        lines = []
        for line in llm_response.strip().split('\n'):
            line = line.strip()
            # Skip empty lines and headers
            if line and not line.startswith('===') and not line.startswith('#'):
                # Remove numbering if present
                line = re.sub(r'^\d+\.\s*', '', line)
                lines.append(line)

        # If we don't have enough corrections, pad with original sentences
        while len(lines) < len(artifacts):
            lines.append(artifacts[len(lines)].sentence)

        return lines[:len(artifacts)]

    def generate_report(self, artifacts: List[CJKArtifactV2], output_path: Path) -> None:
        """
        Generate detailed HTML/JSON report of artifacts and corrections.

        Args:
            artifacts: List of detected artifacts
            output_path: Path to save report
        """
        report_data = {
            "total_artifacts": len(artifacts),
            "timestamp": str(Path(__file__).stat().st_mtime),
            "artifacts": [asdict(a) for a in artifacts]
        }

        # Save JSON
        json_path = output_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        # Categorize artifacts
        by_script = {}
        llm_hallucinations = []
        for artifact in artifacts:
            family = artifact.script_family or "Unknown"
            if family not in by_script:
                by_script[family] = []
            by_script[family].append(artifact)

            if artifact.llm_hallucination:
                llm_hallucinations.append(artifact)

        # Generate readable text report
        text_path = output_path.with_suffix('.txt')
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("Multi-Script Foreign Character Detection Report v2.1\n")
            f.write("="*80 + "\n\n")
            f.write(f"Total artifacts found: {len(artifacts)}\n")
            f.write(f"LLM hallucinations: {len(llm_hallucinations)}\n")
            f.write(f"\nBy Script Family:\n")
            for family, artifs in by_script.items():
                f.write(f"  {family}: {len(artifs)} characters\n")
            f.write("\n")

            for idx, artifact in enumerate(artifacts, 1):
                hallucination_marker = " [LLM HALLUCINATION]" if artifact.llm_hallucination else ""
                f.write(f"\nArtifact #{idx}{hallucination_marker}\n")
                f.write(f"{'='*40}\n")
                f.write(f"Line: {artifact.line_number}\n")
                f.write(f"Character: '{artifact.char}' ({artifact.char_unicode})\n")
                f.write(f"Script: {artifact.unicode_block} ({artifact.script_family})\n")
                f.write(f"Rarity: {artifact.block_rarity}\n")
                f.write(f"Confidence: {artifact.confidence:.2f}\n")
                f.write(f"Reason: {artifact.reason}\n")

                if artifact.encoding_hints:
                    f.write(f"Encodings: {', '.join(artifact.encoding_hints)}\n")

                f.write(f"\nOriginal sentence:\n  {artifact.sentence}\n")

                if artifact.kanji_api_data:
                    f.write(f"\nKanjiAPI data:\n")
                    meanings = artifact.kanji_api_data.get("meanings", [])
                    if meanings:
                        f.write(f"  Meanings: {', '.join(meanings)}\n")
                    f.write(f"  JLPT: {artifact.kanji_api_data.get('jlpt_level', 'N/A')}\n")
                    f.write(f"  Grade: {artifact.kanji_api_data.get('grade', 'N/A')}\n")

                if artifact.suggested_correction:
                    f.write(f"\nSuggested correction:\n  {artifact.suggested_correction}\n")

                f.write("\n")


def main():
    """CLI entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Enhanced CJK Artifact Cleaner v2.0")
    parser.add_argument("input_file", type=Path, help="File to analyze")
    parser.add_argument("--output", "-o", type=Path, help="Output report path (default: input_file_cjk_report)")
    parser.add_argument("--no-kanji-api", action="store_true", help="Disable KanjiAPI validation")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM correction")
    parser.add_argument("--confidence", "-c", type=float, default=0.70, help="Minimum confidence threshold")

    args = parser.parse_args()

    # Read input
    with open(args.input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Initialize cleaner
    cleaner = EnhancedCJKCleaner(
        min_confidence=args.confidence,
        use_kanji_api=not args.no_kanji_api,
        use_llm_correction=not args.no_llm
    )

    print(f"Analyzing {args.input_file}...")
    artifacts = cleaner.detect_artifacts(text)

    print(f"\n✓ Found {len(artifacts)} artifacts")

    # Generate report
    if artifacts:
        output_path = args.output or args.input_file.with_name(f"{args.input_file.stem}_cjk_report")
        cleaner.generate_report(artifacts, output_path)
        print(f"✓ Report saved to {output_path}.txt and {output_path}.json")
    else:
        print("✓ No artifacts detected")


if __name__ == "__main__":
    main()
