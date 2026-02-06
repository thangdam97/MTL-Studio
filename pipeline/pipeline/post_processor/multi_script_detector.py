"""
Comprehensive Multi-Script Detector
====================================

Detects ALL non-Japanese scripts that may appear in text due to:
- LLM hallucination (Gemini generating wrong scripts)
- Encoding errors during EPUB extraction
- OCR mistakes in source material

Detects:
- CJK (Chinese) - All 14 Unicode blocks
- Cyrillic (Russian, Ukrainian, etc.)
- Arabic (Arabic, Persian, Urdu)
- Hebrew
- Thai
- Devanagari (Hindi, Sanskrit)
- Bengali
- Tamil
- Telugu
- Korean Hangul (when in Japanese text)
- Greek
- Armenian
- Georgian
- And more...

Valid in Japanese text:
- Hiragana (U+3040–U+309F)
- Katakana (U+30A0–U+30FF)
- CJK Unified Ideographs (subset - Japanese kanji)
- Latin alphabet (romaji)
- Numbers (Arabic numerals)
- Punctuation
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Set, Dict
from enum import Enum
import sys
from pathlib import Path

# Import CJK detector
sys.path.insert(0, str(Path(__file__).parent))
try:
    from cjk_unicode_detector import ComprehensiveCJKDetector, CJKBlock
except ImportError:
    ComprehensiveCJKDetector = None
    CJKBlock = None


class ScriptFamily(Enum):
    """Unicode script families that may appear in text."""

    # Valid Japanese scripts
    HIRAGANA = ("Hiragana", 0x3040, 0x309F, "Japanese", False)
    KATAKANA = ("Katakana", 0x30A0, 0x30FF, "Japanese", False)
    KATAKANA_PHONETIC = ("Katakana Phonetic Extensions", 0x31F0, 0x31FF, "Japanese", False)
    HALFWIDTH_KATAKANA = ("Halfwidth Katakana", 0xFF65, 0xFF9F, "Japanese", False)

    # CJK (handled separately by ComprehensiveCJKDetector)
    # Included here for completeness
    CJK_UNIFIED = ("CJK Unified Ideographs", 0x4E00, 0x9FFF, "CJK", True)

    # Cyrillic (Russian, Ukrainian, Belarusian, Serbian, etc.)
    CYRILLIC = ("Cyrillic", 0x0400, 0x04FF, "Cyrillic", True)
    CYRILLIC_SUPPLEMENT = ("Cyrillic Supplement", 0x0500, 0x052F, "Cyrillic", True)
    CYRILLIC_EXTENDED_A = ("Cyrillic Extended-A", 0x2DE0, 0x2DFF, "Cyrillic", True)
    CYRILLIC_EXTENDED_B = ("Cyrillic Extended-B", 0xA640, 0xA69F, "Cyrillic", True)
    CYRILLIC_EXTENDED_C = ("Cyrillic Extended-C", 0x1C80, 0x1C8F, "Cyrillic", True)

    # Arabic (Arabic, Persian, Urdu, Pashto, etc.)
    ARABIC = ("Arabic", 0x0600, 0x06FF, "Arabic", True)
    ARABIC_SUPPLEMENT = ("Arabic Supplement", 0x0750, 0x077F, "Arabic", True)
    ARABIC_EXTENDED_A = ("Arabic Extended-A", 0x08A0, 0x08FF, "Arabic", True)
    ARABIC_PRESENTATION_A = ("Arabic Presentation Forms-A", 0xFB50, 0xFDFF, "Arabic", True)
    ARABIC_PRESENTATION_B = ("Arabic Presentation Forms-B", 0xFE70, 0xFEFF, "Arabic", True)

    # Hebrew
    HEBREW = ("Hebrew", 0x0590, 0x05FF, "Hebrew", True)

    # Greek
    GREEK = ("Greek", 0x0370, 0x03FF, "Greek", True)
    GREEK_EXTENDED = ("Greek Extended", 0x1F00, 0x1FFF, "Greek", True)

    # Korean Hangul (suspicious in Japanese text)
    HANGUL_JAMO = ("Hangul Jamo", 0x1100, 0x11FF, "Korean", True)
    HANGUL_COMPATIBILITY = ("Hangul Compatibility Jamo", 0x3130, 0x318F, "Korean", True)
    HANGUL_SYLLABLES = ("Hangul Syllables", 0xAC00, 0xD7AF, "Korean", True)

    # Thai
    THAI = ("Thai", 0x0E00, 0x0E7F, "Thai", True)

    # Devanagari (Hindi, Sanskrit, Marathi, Nepali)
    DEVANAGARI = ("Devanagari", 0x0900, 0x097F, "Devanagari", True)
    DEVANAGARI_EXTENDED = ("Devanagari Extended", 0xA8E0, 0xA8FF, "Devanagari", True)

    # Bengali
    BENGALI = ("Bengali", 0x0980, 0x09FF, "Bengali", True)

    # Tamil
    TAMIL = ("Tamil", 0x0B80, 0x0BFF, "Tamil", True)

    # Telugu
    TELUGU = ("Telugu", 0x0C00, 0x0C7F, "Telugu", True)

    # Armenian
    ARMENIAN = ("Armenian", 0x0530, 0x058F, "Armenian", True)

    # Georgian
    GEORGIAN = ("Georgian", 0x10A0, 0x10FF, "Georgian", True)

    # Ethiopic
    ETHIOPIC = ("Ethiopic", 0x1200, 0x137F, "Ethiopic", True)

    # Myanmar
    MYANMAR = ("Myanmar", 0x1000, 0x109F, "Myanmar", True)

    # Khmer
    KHMER = ("Khmer", 0x1780, 0x17FF, "Khmer", True)

    # Lao
    LAO = ("Lao", 0x0E80, 0x0EFF, "Lao", True)

    # Tibetan
    TIBETAN = ("Tibetan", 0x0F00, 0x0FFF, "Tibetan", True)

    # Mongolian
    MONGOLIAN = ("Mongolian", 0x1800, 0x18AF, "Mongolian", True)

    def __init__(self, name: str, start: int, end: int, family: str, suspicious: bool):
        self.script_name = name
        self.start = start
        self.end = end
        self.family = family
        self.suspicious_in_japanese = suspicious

    def contains(self, codepoint: int) -> bool:
        """Check if codepoint is in this script."""
        return self.start <= codepoint <= self.end

    @classmethod
    def identify_script(cls, char: str) -> Optional['ScriptFamily']:
        """Identify which script a character belongs to."""
        if not char:
            return None

        codepoint = ord(char)
        for script in cls:
            if script.contains(codepoint):
                return script
        return None


@dataclass
class ScriptArtifact:
    """Foreign script character found in text."""
    char: str
    codepoint: int
    unicode_name: str
    script: ScriptFamily
    line_number: int
    sentence: str
    position_in_sentence: int
    suspicion_score: float
    reason: str
    llm_hallucination_likely: bool  # If True, likely from LLM output


class MultiScriptDetector:
    """
    Comprehensive multi-script detector for non-Japanese characters.

    Detects:
    - Chinese characters (via ComprehensiveCJKDetector)
    - Cyrillic, Arabic, Hebrew, Greek
    - Korean Hangul, Thai, Devanagari
    - All other non-Japanese Unicode scripts
    """

    # Characters that are OK in Japanese text
    VALID_JAPANESE_RANGES = [
        (0x3040, 0x309F),  # Hiragana
        (0x30A0, 0x30FF),  # Katakana
        (0x31F0, 0x31FF),  # Katakana Phonetic Extensions
        (0xFF65, 0xFF9F),  # Halfwidth Katakana
        (0x4E00, 0x9FFF),  # CJK Unified Ideographs (Japanese kanji subset)
        (0x0020, 0x007E),  # Basic Latin (ASCII)
        (0x00A0, 0x00FF),  # Latin-1 Supplement
        (0xFF01, 0xFF5E),  # Fullwidth Latin
        (0x3000, 0x303F),  # CJK Symbols and Punctuation
        (0x2000, 0x206F),  # General Punctuation
    ]

    # Scripts most likely from LLM hallucination
    LLM_HALLUCINATION_SCRIPTS = {
        'Cyrillic', 'Arabic', 'Hebrew', 'Greek',
        'Korean', 'Thai', 'Devanagari', 'Bengali'
    }

    def __init__(self, use_cjk_detector: bool = True):
        """
        Initialize multi-script detector.

        Args:
            use_cjk_detector: Whether to use comprehensive CJK detector
        """
        self.use_cjk_detector = use_cjk_detector

        # Initialize CJK detector
        if use_cjk_detector and ComprehensiveCJKDetector:
            self.cjk_detector = ComprehensiveCJKDetector(strict_mode=False)
        else:
            self.cjk_detector = None

    def is_valid_japanese(self, char: str) -> bool:
        """
        Check if character is valid in Japanese text.

        Args:
            char: Character to check

        Returns:
            True if valid in Japanese, False otherwise
        """
        codepoint = ord(char)

        # Check valid Japanese ranges
        for start, end in self.VALID_JAPANESE_RANGES:
            if start <= codepoint <= end:
                return True

        return False

    def detect_all_foreign_scripts(self, text: str) -> List[ScriptArtifact]:
        """
        Detect ALL foreign (non-Japanese) scripts in text.

        Args:
            text: Text to analyze

        Returns:
            List of foreign script artifacts
        """
        artifacts = []

        # Process each character
        for idx, char in enumerate(text):
            # Skip valid Japanese characters
            if self.is_valid_japanese(char):
                continue

            # Skip whitespace and control characters
            if char.isspace() or ord(char) < 0x20:
                continue

            # Identify script
            script = ScriptFamily.identify_script(char)
            if not script:
                continue  # Unknown/private use

            # Skip if not suspicious
            if not script.suspicious_in_japanese:
                continue

            # Calculate suspicion
            suspicion, reason = self._calculate_suspicion(char, text, idx, script)

            # Find line number
            line_num = text[:idx].count('\n') + 1

            # Extract sentence
            sentence, pos_in_sent = self._extract_sentence(text, idx)

            # Check if likely LLM hallucination
            is_llm_hallucination = script.family in self.LLM_HALLUCINATION_SCRIPTS

            artifact = ScriptArtifact(
                char=char,
                codepoint=ord(char),
                unicode_name=self._get_unicode_name(char),
                script=script,
                line_number=line_num,
                sentence=sentence,
                position_in_sentence=pos_in_sent,
                suspicion_score=suspicion,
                reason=reason,
                llm_hallucination_likely=is_llm_hallucination
            )

            artifacts.append(artifact)

        return artifacts

    def _calculate_suspicion(
        self,
        char: str,
        text: str,
        position: int,
        script: ScriptFamily
    ) -> Tuple[float, str]:
        """
        Calculate suspicion score for a foreign character.

        Args:
            char: Character to evaluate
            text: Full text
            position: Position in text
            script: Identified script

        Returns:
            Tuple of (suspicion_score 0-1, reason)
        """
        score = 0.0
        reasons = []

        # Factor 1: Script family (50% weight)
        if script.family == "Cyrillic":
            score += 0.50
            reasons.append("Cyrillic script (likely LLM hallucination)")
        elif script.family == "Arabic":
            score += 0.50
            reasons.append("Arabic script (likely LLM hallucination)")
        elif script.family == "Hebrew":
            score += 0.50
            reasons.append("Hebrew script (likely encoding error)")
        elif script.family == "Greek":
            score += 0.45
            reasons.append("Greek script (possible scientific notation or hallucination)")
        elif script.family == "Korean":
            score += 0.40
            reasons.append("Korean Hangul (wrong language)")
        elif script.family in ["Thai", "Devanagari", "Bengali"]:
            score += 0.50
            reasons.append(f"{script.family} script (likely LLM hallucination)")
        elif script.family == "CJK":
            score += 0.30
            reasons.append("Chinese character (may be valid Japanese kanji)")
        else:
            score += 0.35
            reasons.append(f"{script.family} script (foreign)")

        # Factor 2: Multiple foreign characters in sequence (30% weight)
        consecutive_foreign = self._count_consecutive_foreign(text, position)
        if consecutive_foreign >= 3:
            score += 0.30
            reasons.append(f"{consecutive_foreign} consecutive foreign chars")
        elif consecutive_foreign >= 2:
            score += 0.15
            reasons.append(f"{consecutive_foreign} consecutive foreign chars")

        # Factor 3: No Japanese context nearby (20% weight)
        left_context = text[max(0, position - 10):position]
        right_context = text[position + 1:min(len(text), position + 11)]

        has_japanese_left = any(self.is_valid_japanese(c) for c in left_context)
        has_japanese_right = any(self.is_valid_japanese(c) for c in right_context)

        if not has_japanese_left and not has_japanese_right:
            score += 0.20
            reasons.append("No Japanese context nearby")
        elif not has_japanese_left or not has_japanese_right:
            score += 0.10
            reasons.append("Japanese context on one side only")

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        reason = "; ".join(reasons) if reasons else "Foreign script"
        return score, reason

    def _count_consecutive_foreign(self, text: str, position: int) -> int:
        """Count consecutive foreign characters around position."""
        count = 1  # Current character

        # Count left
        idx = position - 1
        while idx >= 0 and not self.is_valid_japanese(text[idx]):
            count += 1
            idx -= 1

        # Count right
        idx = position + 1
        while idx < len(text) and not self.is_valid_japanese(text[idx]):
            count += 1
            idx += 1

        return count

    def _extract_sentence(self, text: str, position: int) -> Tuple[str, int]:
        """Extract sentence containing the character."""
        sentence_delimiters = '。！？\n'

        # Find start
        start = position
        while start > 0 and text[start - 1] not in sentence_delimiters:
            start -= 1

        # Find end
        end = position
        while end < len(text) and text[end] not in sentence_delimiters:
            end += 1

        if end < len(text) and text[end] in sentence_delimiters:
            end += 1

        sentence = text[start:end].strip()
        pos_in_sent = position - start

        return sentence, pos_in_sent

    def _get_unicode_name(self, char: str) -> str:
        """Get Unicode character name."""
        try:
            import unicodedata
            return unicodedata.name(char, f"U+{ord(char):04X}")
        except (ValueError, ImportError):
            return f"U+{ord(char):04X}"

    def generate_report(self, text: str) -> Dict:
        """
        Generate comprehensive multi-script detection report.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with detection statistics
        """
        artifacts = self.detect_all_foreign_scripts(text)

        # Group by script family
        by_family = {}
        for artifact in artifacts:
            family = artifact.script.family
            if family not in by_family:
                by_family[family] = []
            by_family[family].append(artifact)

        # LLM hallucination detection
        hallucination_artifacts = [a for a in artifacts if a.llm_hallucination_likely]

        return {
            "total_foreign_chars": len(artifacts),
            "unique_chars": len(set(a.char for a in artifacts)),
            "by_family": {
                family: {
                    "count": len(chars),
                    "characters": list(set(a.char for a in chars)),
                    "avg_suspicion": sum(a.suspicion_score for a in chars) / len(chars)
                }
                for family, chars in by_family.items()
            },
            "llm_hallucinations": {
                "count": len(hallucination_artifacts),
                "families": list(set(a.script.family for a in hallucination_artifacts))
            },
            "high_suspicion_count": len([a for a in artifacts if a.suspicion_score >= 0.7])
        }


def main():
    """CLI test harness."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python multi_script_detector.py <text>")
        print("\nExample:")
        print("  python multi_script_detector.py '日本語テスト with Привет and مرحبا'")
        sys.exit(1)

    text = sys.argv[1]
    detector = MultiScriptDetector()

    print("="*70)
    print("Multi-Script Foreign Character Detection")
    print("="*70)
    print(f"\nAnalyzing: {text}")
    print()

    artifacts = detector.detect_all_foreign_scripts(text)

    if not artifacts:
        print("✓ No foreign scripts detected")
        return

    print(f"Found {len(artifacts)} foreign characters:\n")

    for artifact in artifacts:
        hallucination_marker = " [LLM HALLUCINATION]" if artifact.llm_hallucination_likely else ""
        print(f"  '{artifact.char}' (U+{artifact.codepoint:04X}){hallucination_marker}")
        print(f"    Script: {artifact.script.script_name} ({artifact.script.family})")
        print(f"    Line: {artifact.line_number}")
        print(f"    Suspicion: {artifact.suspicion_score:.2f} - {artifact.reason}")
        print(f"    Sentence: {artifact.sentence[:60]}...")
        print()

    # Generate report
    report = detector.generate_report(text)

    print("="*70)
    print("Detection Report")
    print("="*70)
    print(f"Total Foreign: {report['total_foreign_chars']}")
    print(f"Unique: {report['unique_chars']}")
    print(f"High Suspicion (≥0.7): {report['high_suspicion_count']}")
    print(f"LLM Hallucinations: {report['llm_hallucinations']['count']}")
    print(f"  Families: {', '.join(report['llm_hallucinations']['families'])}")
    print()

    print("By Script Family:")
    for family, data in report['by_family'].items():
        chars_preview = ''.join(data['characters'][:5])
        if len(data['characters']) > 5:
            chars_preview += "..."
        print(f"  {family}: {data['count']} chars ({chars_preview}) - Avg suspicion: {data['avg_suspicion']:.2f}")


if __name__ == "__main__":
    main()
