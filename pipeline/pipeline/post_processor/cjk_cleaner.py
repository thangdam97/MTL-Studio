"""
Legacy-compatible CJK artifact cleaner.

This module restores the v1 API expected by translator/agent.py:
- CJKArtifactCleaner(strict_mode, min_confidence, context_window)
- clean_file(), clean_directory(), clean_volume()
- format_results_report(results)

Implementation is intentionally conservative and detection-first so it can run
as a safe post-processing check inside Phase 2.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class CJKArtifact:
    """Detected CJK artifact with context."""

    line_number: int
    char: str
    position: int
    left_context: str
    right_context: str
    confidence: float
    reason: str


class CJKArtifactCleaner:
    """Detects and optionally removes stray CJK characters from text."""

    # High-signal Chinese-only/Cantonese-heavy characters.
    CHINESE_ONLY_CHARS = set(
        """
        爲這個們嗎呢啊吧喔哦唄咧啦哪誰係喺啲嘅嗰噉乜咁點樣邊
        冇未曾經緊住咗過喇啩囉啫嚟佢哋你妳您俺咱阮伲偌倆仨
        """.replace("\n", "").replace(" ", "")
    )

    # Known problematic Chinese compounds observed in corrupted outputs.
    CHINESE_COMPOUNDS = frozenset(
        {
            "有好",
            "爲了",
            "這個",
            "那個",
            "什麼",
            "怎麼",
            "沒有",
            "已經",
            "正在",
            "將要",
            "不能",
            "應該",
            "可以",
            "還是",
            "為什",
            "會不",
        }
    )

    # Keep this short and conservative; scoring logic does the heavy lifting.
    COMMON_JAPANESE_KANJI = set(
        "一二三四五六七八九十百千万年月日時分人大小中学生先校本国会社会名語文字目手足口耳心体話言読書見聞食飲行来帰入出上下左右前後東西南北内外間近遠高安多少長新古明早今毎週次方何私達彼女男子母父兄弟姉妹友達気持思考知分使作勉強仕事休買売開始終教室家族親切元冷暖涼熱好悪楽面白便利必要英語漢字歌音楽映画写真旅行病院薬医者交通電車自動車駅道路橋建林公園海山川空天気雨雪風花春夏秋冬朝昼夜晩色青赤黒白"
    )

    # Basic CJK unified ideographs (legacy v1 behavior).
    _CJK_PATTERN = re.compile(r"[\u4E00-\u9FFF]")

    def __init__(
        self,
        strict_mode: bool = False,
        min_confidence: float = 0.7,
        context_window: int = 5,
    ):
        self.strict_mode = strict_mode
        self.min_confidence = float(min_confidence)
        self.context_window = max(1, int(context_window))

    def detect_artifacts(self, text: str) -> List[CJKArtifact]:
        artifacts: List[CJKArtifact] = []

        for line_number, line in enumerate(text.split("\n"), 1):
            for match in self._CJK_PATTERN.finditer(line):
                char = match.group(0)
                position = match.start()
                left_ctx = line[max(0, position - self.context_window) : position]
                right_ctx = line[position + 1 : position + 1 + self.context_window]

                confidence, reason = self._calculate_suspicion(char, left_ctx, right_ctx)
                if confidence < self.min_confidence:
                    continue

                artifacts.append(
                    CJKArtifact(
                        line_number=line_number,
                        char=char,
                        position=position,
                        left_context=left_ctx,
                        right_context=right_ctx,
                        confidence=confidence,
                        reason=reason,
                    )
                )

        return artifacts

    def _calculate_suspicion(self, char: str, left_ctx: str, right_ctx: str) -> Tuple[float, str]:
        score = 0.0
        reasons: List[str] = []

        left_char = left_ctx[-1] if left_ctx else ""
        right_char = right_ctx[0] if right_ctx else ""

        if char in self.CHINESE_ONLY_CHARS:
            score += 0.7
            reasons.append("Chinese-only char")

        if char not in self.COMMON_JAPANESE_KANJI:
            score += 0.15
            reasons.append("Rare in Japanese")

        left_pair = f"{left_char}{char}" if left_char else ""
        right_pair = f"{char}{right_char}" if right_char else ""
        if left_pair in self.CHINESE_COMPOUNDS:
            score += 0.6
            reasons.append(f"Chinese compound: {left_pair}")
        elif right_pair in self.CHINESE_COMPOUNDS:
            score += 0.6
            reasons.append(f"Chinese compound: {right_pair}")

        if not any(self._is_japanese_kana(c) for c in (left_ctx + right_ctx)):
            score += 0.2
            reasons.append("No kana neighbors")

        if (left_char and self._is_latin_or_vietnamese(left_char)) or (
            right_char and self._is_latin_or_vietnamese(right_char)
        ):
            score += 0.15
            reasons.append("Adjacent to Latin/Vietnamese")

        # If it is common Japanese and no high-signal marker fired, keep conservative.
        if (
            char in self.COMMON_JAPANESE_KANJI
            and "Chinese-only char" not in reasons
            and not any(r.startswith("Chinese compound:") for r in reasons)
        ):
            score = max(0.0, score - 0.15)

        reason = "; ".join(reasons) if reasons else "Suspicious CJK context"
        return min(score, 1.0), reason

    def _is_japanese_kana(self, char: str) -> bool:
        code = ord(char)
        return (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF)

    def _is_latin_or_vietnamese(self, char: str) -> bool:
        if not char or char.isspace():
            return False
        if char.isascii() and char.isalpha():
            return True
        try:
            return "LATIN" in unicodedata.name(char)
        except ValueError:
            return False

    def clean_file(self, filepath: Path) -> Dict[str, any]:
        """
        Clean a single file and return detailed detection results.
        """
        if not filepath.exists():
            return {
                "file": str(filepath),
                "error": "File not found",
                "artifacts": [],
                "modified": False,
            }

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        artifacts = self.detect_artifacts(content)
        result = {
            "file": filepath.name,
            "artifacts": len(artifacts),
            "modified": False,
            "details": [],
        }

        if not artifacts:
            return result

        for artifact in artifacts:
            result["details"].append(
                {
                    "line": artifact.line_number,
                    "char": artifact.char,
                    "code": f"U+{ord(artifact.char):04X}",
                    "confidence": f"{artifact.confidence:.2f}",
                    "context": f"...{artifact.left_context}[{artifact.char}]{artifact.right_context}...",
                    "reason": artifact.reason,
                }
            )

        if self.strict_mode and artifacts:
            cleaned_content = content
            lines = cleaned_content.split("\n")

            # Remove from end to start to keep positions stable.
            for artifact in sorted(artifacts, key=lambda a: (a.line_number, a.position), reverse=True):
                line_idx = artifact.line_number - 1
                if line_idx < len(lines):
                    line = lines[line_idx]
                    lines[line_idx] = line[: artifact.position] + line[artifact.position + 1 :]

            cleaned_content = "\n".join(lines)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(cleaned_content)

            result["modified"] = True

        return result

    def clean_directory(self, directory: Path, pattern: str = "CHAPTER_*.md") -> Dict[str, any]:
        """
        Clean all matching files in a language directory.
        """
        files = sorted(directory.glob(pattern))
        results = {
            "directory": str(directory),
            "files_processed": 0,
            "files_with_artifacts": 0,
            "total_artifacts": 0,
            "files_modified": 0,
            "file_results": [],
        }

        for filepath in files:
            result = self.clean_file(filepath)
            results["files_processed"] += 1

            if result.get("artifacts", 0) > 0:
                results["files_with_artifacts"] += 1
                results["total_artifacts"] += result["artifacts"]
                results["file_results"].append(result)

            if result.get("modified", False):
                results["files_modified"] += 1

        return results

    def clean_volume(self, work_dir: Path) -> Dict[str, any]:
        """
        Clean all language directories in a volume work directory.
        """
        language_dirs = ["JP", "EN", "VN"]
        global_results = {
            "volume": work_dir.name,
            "languages_processed": 0,
            "total_files": 0,
            "total_artifacts": 0,
            "files_modified": 0,
            "language_results": {},
        }

        for lang_dir in language_dirs:
            lang_path = work_dir / lang_dir
            if not lang_path.exists():
                continue

            lang_results = self.clean_directory(lang_path)

            if lang_results["files_processed"] > 0:
                global_results["languages_processed"] += 1
                global_results["total_files"] += lang_results["files_processed"]
                global_results["total_artifacts"] += lang_results["total_artifacts"]
                global_results["files_modified"] += lang_results["files_modified"]
                global_results["language_results"][lang_dir] = lang_results

        return global_results


def format_results_report(results: Dict[str, any]) -> str:
    """
    Format results dictionary into a readable report.

    Args:
        results: Results from clean_volume()

    Returns:
        Formatted string report
    """
    lines: List[str] = []
    lines.append("\n============================================================")
    lines.append("CJK ARTIFACT CLEANUP REPORT")
    lines.append("============================================================")

    lines.append(f"\nVolume: {results.get('volume', 'Unknown')}")
    lines.append(f"Languages processed: {results['languages_processed']}")
    lines.append(f"Total files: {results['total_files']}")
    lines.append(f"Total artifacts found: {results['total_artifacts']}")
    lines.append(f"Files modified: {results['files_modified']}")

    for lang, lang_results in results.get("language_results", {}).items():
        if lang_results["files_with_artifacts"] > 0:
            lines.append(f"\n{lang} Directory:")
            lines.append(f"  Files with artifacts: {lang_results['files_with_artifacts']}")
            lines.append(f"  Total artifacts: {lang_results['total_artifacts']}")

            for file_result in lang_results.get("file_results", []):
                lines.append(f"\n  File: {file_result['file']}")
                lines.append(f"    Artifacts: {file_result['artifacts']}")

                for detail in file_result.get("details", [])[:5]:
                    lines.append(
                        f"    - Line {detail['line']}: '{detail['char']}' ({detail['code']}) confidence={detail['confidence']}"
                    )
                    lines.append(f"      Context: {detail['context']}")
                    lines.append(f"      Reason: {detail['reason']}")

                if len(file_result.get("details", [])) > 5:
                    remaining = len(file_result["details"]) - 5
                    lines.append(f"    ... and {remaining} more artifacts")

    lines.append("\n============================================================\n")
    return "\n".join(lines)

