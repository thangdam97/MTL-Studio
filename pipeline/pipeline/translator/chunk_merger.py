"""
Chunk merger for massive chapter translation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.post_processor.truncation_validator import TruncationIssue, TruncationValidator

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    chapter_id: str
    chunks_merged: int
    output_path: Path
    truncation_issues: List[TruncationIssue]


class ChunkMerger:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.temp_dir = work_dir / "temp" / "chunks"
        self.en_dir = work_dir / "EN"
        self.validator = TruncationValidator()

    def merge_chapter(self, chapter_id: str, output_filename: Optional[str] = None) -> MergeResult:
        chunk_files = sorted(self.temp_dir.glob(f"{chapter_id}_chunk_*.json"))
        if not chunk_files:
            raise ValueError(f"No chunk JSON files found for {chapter_id}")

        chunks = [self._load_chunk(path) for path in chunk_files]
        self._validate_chunk_sequence(chunks, chapter_id)

        merged_text = self._merge_chunks(chunks)
        merged_text = self._dedupe_scene_breaks(merged_text)

        report = self.validator.validate_text(merged_text)
        if report.has_critical():
            logger.warning(
                f"[MERGE] {chapter_id} merged with {len(report.critical)} critical truncation issue(s)"
            )

        self.en_dir.mkdir(parents=True, exist_ok=True)
        target_name = output_filename or f"{chapter_id.upper()}.md"
        output_path = self.en_dir / target_name
        output_path.write_text(merged_text, encoding="utf-8")

        return MergeResult(
            chapter_id=chapter_id,
            chunks_merged=len(chunks),
            output_path=output_path,
            truncation_issues=report.all_issues,
        )

    def _load_chunk(self, path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "content" not in data:
            raise ValueError(f"Chunk JSON missing content: {path}")
        return data

    def _validate_chunk_sequence(self, chunks: List[Dict[str, Any]], chapter_id: str) -> None:
        expected_index = 1
        expected_total = chunks[0].get("total_chunks")
        for chunk in chunks:
            idx = chunk.get("chunk_index")
            chunk_chapter = chunk.get("chapter_id")
            if chunk_chapter != chapter_id:
                raise ValueError(f"Chunk chapter mismatch: expected {chapter_id}, got {chunk_chapter}")
            if idx != expected_index:
                raise ValueError(f"Chunk index mismatch: expected {expected_index}, got {idx}")
            if expected_total and chunk.get("total_chunks") != expected_total:
                raise ValueError(
                    f"Total chunk count mismatch in chunk {idx}: expected {expected_total}, "
                    f"got {chunk.get('total_chunks')}"
                )
            expected_index += 1

    def _merge_chunks(self, chunks: List[Dict[str, Any]]) -> str:
        merged_parts: List[str] = []
        last_sentence: str = ""

        for chunk in chunks:
            content = str(chunk.get("content", "")).strip()
            if not content:
                continue

            content = self._strip_duplicate_prefix(content, last_sentence)
            merged_parts.append(content)
            last_sentence = str(chunk.get("last_sentence", "")).strip()

        return "\n\n".join(part for part in merged_parts if part).strip()

    def _dedupe_scene_breaks(self, text: str) -> str:
        # Collapse repeated scene-break runs into a single separator.
        deduped = re.sub(r"(?:\n\s*◆\s*\n\s*){2,}", "\n\n◆\n\n", text)
        # Normalize excess blank lines.
        deduped = re.sub(r"\n{4,}", "\n\n\n", deduped)
        return deduped.strip()

    def _strip_duplicate_prefix(self, next_text: str, previous_last_sentence: str) -> str:
        if not previous_last_sentence:
            return next_text

        candidate = previous_last_sentence.strip()
        if len(candidate) < 10:
            return next_text

        # Exact duplicate sentence at boundary.
        if next_text.startswith(candidate):
            return next_text[len(candidate):].lstrip()

        # Loose match on first line to handle spacing differences.
        first_line = next_text.splitlines()[0].strip() if next_text.splitlines() else next_text.strip()
        normalized_candidate = re.sub(r"\s+", " ", candidate).lower()
        normalized_first_line = re.sub(r"\s+", " ", first_line).lower()
        if normalized_candidate and normalized_first_line == normalized_candidate:
            offset = next_text.find(first_line)
            if offset >= 0:
                return next_text[offset + len(first_line):].lstrip()

        return next_text
