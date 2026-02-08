"""
Comprehensive CJK Unicode Detector
===================================

Detects CJK characters from ALL Unicode blocks, not just the basic CJK Unified Ideographs.

Covers:
- CJK Unified Ideographs (U+4E00–U+9FFF)
- CJK Extension A (U+3400–U+4DBF)
- CJK Extension B (U+20000–U+2A6DF)
- CJK Extension C (U+2A700–U+2B73F)
- CJK Extension D (U+2B740–U+2B81F)
- CJK Extension E (U+2B820–U+2CEAF)
- CJK Extension F (U+2CEB0–U+2EBEF)
- CJK Extension G (U+30000–U+3134F)
- CJK Compatibility Ideographs (U+F900–U+FAFF)
- CJK Compatibility Ideographs Supplement (U+2F800–U+2FA1F)
- CJK Radicals Supplement (U+2E80–U+2EFF)
- Kangxi Radicals (U+2F00–U+2FDF)

This ensures we catch Chinese characters that may appear in:
- Traditional Chinese (Big5, GB)
- Simplified Chinese (GB2312, GBK, GB18030)
- Japanese (Shift-JIS, EUC-JP)
- Korean (EUC-KR, ISO-2022-KR)
- Vietnamese (legacy CJK characters)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Set
from enum import Enum


class CJKBlock(Enum):
    """Unicode CJK block definitions."""

    # Main ideographs
    UNIFIED_IDEOGRAPHS = ("CJK Unified Ideographs", 0x4E00, 0x9FFF, "Common")

    # Extensions (rare/historical characters)
    EXTENSION_A = ("CJK Extension A", 0x3400, 0x4DBF, "Rare")
    EXTENSION_B = ("CJK Extension B", 0x20000, 0x2A6DF, "Very Rare")
    EXTENSION_C = ("CJK Extension C", 0x2A700, 0x2B73F, "Very Rare")
    EXTENSION_D = ("CJK Extension D", 0x2B740, 0x2B81F, "Very Rare")
    EXTENSION_E = ("CJK Extension E", 0x2B820, 0x2CEAF, "Very Rare")
    EXTENSION_F = ("CJK Extension F", 0x2CEB0, 0x2EBEF, "Very Rare")
    EXTENSION_G = ("CJK Extension G", 0x30000, 0x3134F, "Very Rare")

    # Compatibility (variants/ligatures)
    COMPATIBILITY = ("CJK Compatibility", 0xF900, 0xFAFF, "Variants")
    COMPATIBILITY_SUPPLEMENT = ("CJK Compatibility Supplement", 0x2F800, 0x2FA1F, "Variants")

    # Radicals
    RADICALS_SUPPLEMENT = ("CJK Radicals Supplement", 0x2E80, 0x2EFF, "Components")
    KANGXI_RADICALS = ("Kangxi Radicals", 0x2F00, 0x2FDF, "Components")

    # Symbols and Punctuation
    CJK_SYMBOLS = ("CJK Symbols and Punctuation", 0x3000, 0x303F, "Punctuation")
    IDEOGRAPHIC_DESCRIPTION = ("Ideographic Description Characters", 0x2FF0, 0x2FFF, "Structure")

    # Strokes
    CJK_STROKES = ("CJK Strokes", 0x31C0, 0x31EF, "Components")
    
    # Japanese Kana (ADDED - these should be detected as CJK leaks in English text!)
    HIRAGANA = ("Hiragana", 0x3040, 0x309F, "Japanese Kana")
    KATAKANA = ("Katakana", 0x30A0, 0x30FF, "Japanese Kana")
    KATAKANA_PHONETIC_EXT = ("Katakana Phonetic Extensions", 0x31F0, 0x31FF, "Japanese Kana")
    HALFWIDTH_KATAKANA = ("Halfwidth Katakana", 0xFF65, 0xFF9F, "Japanese Kana")


    def __init__(self, name: str, start: int, end: int, rarity: str):
        self.block_name = name
        self.start = start
        self.end = end
        self.rarity = rarity

    def contains(self, codepoint: int) -> bool:
        """Check if codepoint is in this block."""
        return self.start <= codepoint <= self.end

    @classmethod
    def identify_block(cls, char: str) -> Optional['CJKBlock']:
        """Identify which CJK block a character belongs to."""
        if not char:
            return None

        codepoint = ord(char)
        for block in cls:
            if block.contains(codepoint):
                return block
        return None


@dataclass
class CJKCharInfo:
    """Detailed information about a CJK character."""
    char: str
    codepoint: int
    unicode_name: str
    block: CJKBlock
    is_common: bool
    is_japanese_compatible: bool
    encoding_hints: List[str]


class ComprehensiveCJKDetector:
    """
    Comprehensive CJK character detector using full Unicode coverage.

    Features:
    - Detects ALL CJK Unicode blocks (not just U+4E00–U+9FFF)
    - Identifies character origins (Chinese-only, Japanese-compatible, etc.)
    - Provides encoding hints (GB, Big5, Shift-JIS, etc.)
    - Calculates suspicion scores based on context and rarity
    """

    # Japanese kana blocks (for context detection)
    HIRAGANA_RANGE = (0x3040, 0x309F)
    KATAKANA_RANGE = (0x30A0, 0x30FF)
    KATAKANA_PHONETIC_EXTENSIONS = (0x31F0, 0x31FF)
    HALFWIDTH_KATAKANA = (0xFF65, 0xFF9F)

    # Known Chinese-only characters (high suspicion in Japanese text)
    # These appear in Chinese but rarely/never in Japanese
    CHINESE_ONLY_CHARS = {
        # Simplified Chinese specific
        '为', '们', '这', '那', '您', '吗', '呢', '啊', '吧', '哦', '唄', '咧',
        '啦', '哪', '谁', '啥', '咋', '俺', '咱', '阮', '伲',

        # Traditional Chinese specific (not used in Japanese)
        '係', '喺', '啲', '嘅', '嗰', '噉', '乜', '咁', '點', '樣', '邊', '冇',

        # Chinese-specific radicals/components
        '爲', '個', '們',

        # Vietnamese Chu Nom (legacy CJK)
        '𡨸', '𢆥', '𣎃', '𤅷', '𥄮'
    }

    # Characters common in Japanese (reduce suspicion)
    COMMON_JAPANESE_KANJI = {
        # JLPT N5-N4 level
        '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
        '百', '千', '万', '円', '年', '月', '日', '時', '分', '秒',
        '人', '大', '小', '中', '学', '生', '先', '校', '本', '書',
        '店', '国', '会', '社', '名', '語', '文', '字', '目', '手',
        '足', '口', '耳', '心', '体', '話', '言', '読', '書', '見',
        '聞', '食', '飲', '行', '来', '帰', '入', '出', '上', '下',
        '左', '右', '前', '後', '東', '西', '南', '北', '内', '外',

        # Common verbs/adjectives
        '好', '悪', '新', '古', '高', '安', '多', '少', '長', '短',
        '明', '暗', '早', '遅', '速', '遅', '強', '弱', '軽', '重',

        # Common nouns
        '家', '父', '母', '兄', '弟', '姉', '妹', '友', '達', '私',
        '僕', '君', '彼', '彼女', '男', '女', '子', '親', '学校',
        '会社', '仕事', '勉強', '買', '売', '開', '始', '終', '教',
        '室', '駅', '車', '電', '道', '橋', '町', '市', '県', '都'
    }

    def __init__(self, strict_mode: bool = False):
        """
        Initialize comprehensive CJK detector.

        Args:
            strict_mode: If True, flags even common CJK if context is suspicious
        """
        self.strict_mode = strict_mode

    def detect_all_cjk(self, text: str) -> List[CJKCharInfo]:
        """
        Detect ALL CJK characters in text, regardless of block.

        Args:
            text: Text to analyze

        Returns:
            List of detected CJK characters with detailed info
        """
        cjk_chars = []

        for char in text:
            block = CJKBlock.identify_block(char)
            if block:
                codepoint = ord(char)
                info = CJKCharInfo(
                    char=char,
                    codepoint=codepoint,
                    unicode_name=self._get_unicode_name(char),
                    block=block,
                    is_common=char in self.COMMON_JAPANESE_KANJI,
                    is_japanese_compatible=self._is_japanese_compatible(char, block),
                    encoding_hints=self._get_encoding_hints(char, block)
                )
                cjk_chars.append(info)

        return cjk_chars

    def calculate_suspicion(
        self,
        char: str,
        left_context: str,
        right_context: str,
        block: Optional[CJKBlock] = None
    ) -> Tuple[float, str]:
        """
        Calculate suspicion score for a CJK character.

        Args:
            char: Character to evaluate
            left_context: Left surrounding text
            right_context: Right surrounding text
            block: Unicode block (auto-detected if None)

        Returns:
            Tuple of (suspicion_score 0-1, reason)
        """
        if block is None:
            block = CJKBlock.identify_block(char)

        if not block:
            return 0.0, "Not CJK"

        score = 0.0
        reasons = []

        # Factor 1: Block rarity (40% weight)
        if block.rarity == "Very Rare":
            score += 0.40
            reasons.append(f"Very rare block: {block.block_name}")
        elif block.rarity == "Rare":
            score += 0.25
            reasons.append(f"Rare block: {block.block_name}")
        elif block.rarity == "Variants":
            score += 0.15
            reasons.append(f"Variant form: {block.block_name}")

        # Factor 2: Chinese-only character (30% weight)
        if char in self.CHINESE_ONLY_CHARS:
            score += 0.30
            reasons.append("Chinese-only character")

        # Factor 3: No kana neighbors (20% weight)
        has_left_kana = self._has_kana(left_context)
        has_right_kana = self._has_kana(right_context)

        if not has_left_kana and not has_right_kana:
            score += 0.20
            reasons.append("No kana neighbors")
        elif not has_left_kana or not has_right_kana:
            score += 0.10
            reasons.append("Kana on one side only")

        # Factor 4: Common Japanese kanji (negative weight)
        if char in self.COMMON_JAPANESE_KANJI:
            score -= 0.30
            reasons.append("Common Japanese kanji (reduced suspicion)")

        # Factor 5: Encoding hints suggest Chinese origin (10% weight)
        encoding_hints = self._get_encoding_hints(char, block)
        if "GB2312" in encoding_hints or "GBK" in encoding_hints:
            score += 0.10
            reasons.append(f"Chinese encoding: {', '.join(encoding_hints)}")

        # Clamp score to [0, 1]
        score = max(0.0, min(1.0, score))

        reason = "; ".join(reasons) if reasons else "Low suspicion"
        return score, reason

    def _has_kana(self, text: str) -> bool:
        """Check if text contains Japanese kana."""
        if not text:
            return False

        for char in text:
            cp = ord(char)
            if (self.HIRAGANA_RANGE[0] <= cp <= self.HIRAGANA_RANGE[1] or
                self.KATAKANA_RANGE[0] <= cp <= self.KATAKANA_RANGE[1] or
                self.KATAKANA_PHONETIC_EXTENSIONS[0] <= cp <= self.KATAKANA_PHONETIC_EXTENSIONS[1] or
                self.HALFWIDTH_KATAKANA[0] <= cp <= self.HALFWIDTH_KATAKANA[1]):
                return True

        return False

    def _is_japanese_compatible(self, char: str, block: CJKBlock) -> bool:
        """
        Check if character is compatible with Japanese.

        Japanese uses:
        - CJK Unified Ideographs (common subset)
        - Some CJK Compatibility characters
        - Rarely Extension A/B
        """
        if char in self.CHINESE_ONLY_CHARS:
            return False

        if char in self.COMMON_JAPANESE_KANJI:
            return True

        # CJK Unified Ideographs are generally Japanese-compatible
        if block == CJKBlock.UNIFIED_IDEOGRAPHS:
            return True

        # Extensions B-G are almost always Chinese-only
        if block in [CJKBlock.EXTENSION_B, CJKBlock.EXTENSION_C,
                     CJKBlock.EXTENSION_D, CJKBlock.EXTENSION_E,
                     CJKBlock.EXTENSION_F, CJKBlock.EXTENSION_G]:
            return False

        # Extension A has some Japanese characters (rare names)
        if block == CJKBlock.EXTENSION_A:
            return True  # Possible but rare

        return False  # Conservative default

    def _get_encoding_hints(self, char: str, block: CJKBlock) -> List[str]:
        """
        Get encoding hints for a character.

        Returns:
            List of likely encodings (e.g., ["GB2312", "Big5"])
        """
        codepoint = ord(char)
        hints = []

        # Simplified Chinese encodings
        if codepoint <= 0x9FFF:  # Within BMP
            hints.append("GB2312/GBK")

        # Traditional Chinese
        if 0x4E00 <= codepoint <= 0x9FFF:
            hints.append("Big5")

        # Japanese
        if self._is_japanese_compatible(char, block):
            hints.append("Shift-JIS/EUC-JP")

        # Extensions require GB18030 or UTF-8/UTF-16
        if block in [CJKBlock.EXTENSION_A, CJKBlock.EXTENSION_B,
                     CJKBlock.EXTENSION_C, CJKBlock.EXTENSION_D,
                     CJKBlock.EXTENSION_E, CJKBlock.EXTENSION_F,
                     CJKBlock.EXTENSION_G]:
            hints.append("GB18030/UTF-8 only")

        return hints if hints else ["UTF-8"]

    def _get_unicode_name(self, char: str) -> str:
        """Get Unicode character name."""
        try:
            import unicodedata
            return unicodedata.name(char, f"U+{ord(char):04X}")
        except (ValueError, ImportError):
            return f"U+{ord(char):04X}"

    def generate_coverage_report(self, text: str) -> dict:
        """
        Generate comprehensive CJK coverage report.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with block-level statistics
        """
        all_cjk = self.detect_all_cjk(text)

        # Count by block
        block_counts = {}
        for info in all_cjk:
            block_name = info.block.block_name
            if block_name not in block_counts:
                block_counts[block_name] = {
                    "count": 0,
                    "characters": [],
                    "rarity": info.block.rarity
                }
            block_counts[block_name]["count"] += 1
            if info.char not in block_counts[block_name]["characters"]:
                block_counts[block_name]["characters"].append(info.char)

        # Calculate suspicion distribution
        suspicion_scores = []
        for info in all_cjk:
            # Find character in text for context
            idx = text.find(info.char)
            if idx >= 0:
                left = text[max(0, idx-5):idx]
                right = text[idx+1:min(len(text), idx+6)]
                score, _ = self.calculate_suspicion(info.char, left, right, info.block)
                suspicion_scores.append(score)

        avg_suspicion = sum(suspicion_scores) / len(suspicion_scores) if suspicion_scores else 0

        return {
            "total_cjk_chars": len(all_cjk),
            "unique_chars": len(set(info.char for info in all_cjk)),
            "blocks_used": block_counts,
            "average_suspicion": round(avg_suspicion, 3),
            "high_suspicion_count": len([s for s in suspicion_scores if s >= 0.7]),
            "encoding_compatibility": self._check_encoding_compatibility(all_cjk)
        }

    def _check_encoding_compatibility(self, cjk_chars: List[CJKCharInfo]) -> dict:
        """Check which encodings can represent all detected characters."""
        requires_utf8 = False
        requires_gb18030 = False
        fits_in_bmp = True

        for info in cjk_chars:
            if info.codepoint > 0xFFFF:
                fits_in_bmp = False
                requires_utf8 = True

            if info.block in [CJKBlock.EXTENSION_B, CJKBlock.EXTENSION_C,
                             CJKBlock.EXTENSION_D, CJKBlock.EXTENSION_E,
                             CJKBlock.EXTENSION_F, CJKBlock.EXTENSION_G]:
                requires_gb18030 = True
                requires_utf8 = True

        return {
            "utf8_required": requires_utf8,
            "gb18030_required": requires_gb18030,
            "fits_in_bmp": fits_in_bmp,
            "safe_for_shift_jis": not requires_utf8,
            "recommendation": "UTF-8" if requires_utf8 else "UTF-8/Shift-JIS/GB2312"
        }


def main():
    """CLI test harness."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cjk_unicode_detector.py <text>")
        print("\nExample:")
        print("  python cjk_unicode_detector.py '日本語テスト'")
        sys.exit(1)

    text = sys.argv[1]
    detector = ComprehensiveCJKDetector()

    print("="*70)
    print("Comprehensive CJK Unicode Detection")
    print("="*70)
    print(f"\nAnalyzing: {text}")
    print()

    # Detect all CJK
    all_cjk = detector.detect_all_cjk(text)

    if not all_cjk:
        print("✓ No CJK characters detected")
        return

    print(f"Found {len(all_cjk)} CJK characters:\n")

    for info in all_cjk:
        # Get context for suspicion calculation
        idx = text.find(info.char)
        left = text[max(0, idx-5):idx] if idx >= 0 else ""
        right = text[idx+1:min(len(text), idx+6)] if idx >= 0 else ""

        score, reason = detector.calculate_suspicion(info.char, left, right, info.block)

        print(f"  '{info.char}' (U+{info.codepoint:04X})")
        print(f"    Block: {info.block.block_name}")
        print(f"    Rarity: {info.block.rarity}")
        print(f"    Japanese Compatible: {'Yes' if info.is_japanese_compatible else 'No'}")
        print(f"    Encodings: {', '.join(info.encoding_hints)}")
        print(f"    Suspicion: {score:.2f} - {reason}")
        print()

    # Generate coverage report
    report = detector.generate_coverage_report(text)

    print("="*70)
    print("Coverage Report")
    print("="*70)
    print(f"Total CJK: {report['total_cjk_chars']}")
    print(f"Unique: {report['unique_chars']}")
    print(f"Average Suspicion: {report['average_suspicion']}")
    print(f"High Suspicion (≥0.7): {report['high_suspicion_count']}")
    print(f"\nEncoding: {report['encoding_compatibility']['recommendation']}")
    print()

    print("Blocks Used:")
    for block_name, data in report['blocks_used'].items():
        chars_preview = ''.join(data['characters'][:10])
        if len(data['characters']) > 10:
            chars_preview += "..."
        print(f"  {block_name}: {data['count']} chars ({chars_preview})")


if __name__ == "__main__":
    main()
