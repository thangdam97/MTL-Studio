"""
Chapter Summarization Agent.

Generates lightweight per-chapter summaries for volume-level continuity context.
Output schema is aligned with `VolumeContextAggregator.ChapterSummary`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.common.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


@dataclass
class ChapterSummaryResult:
    """Result payload for chapter summarization."""
    success: bool
    chapter_num: int
    summary_path: Optional[Path]
    summary_data: Dict[str, Any]
    model: str
    used_fallback: bool = False
    error: Optional[str] = None


class ChapterSummarizationAgent:
    """
    Build chapter summaries from translated chapter text.

    Saved file format (per chapter):
      .context/CHAPTER_XX_SUMMARY.json
    """

    _CHAPTER_NUM_RE = re.compile(r"chapter[_\-\s]*(\d+)", re.IGNORECASE)
    _SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")

    def __init__(
        self,
        gemini_client: GeminiClient,
        work_dir: Path,
        target_language: str = "en",
        model: str = "gemini-2.5-flash",
    ):
        self.client = gemini_client
        self.work_dir = work_dir
        self.target_language = target_language
        self.model = model
        self.context_dir = work_dir / ".context"
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def summarize_chapter(
        self,
        chapter_id: str,
        translation_text: str,
        chapter_num: Optional[int] = None,
        chapter_title: Optional[str] = None,
    ) -> ChapterSummaryResult:
        """
        Summarize chapter text and persist structured summary JSON.
        """
        resolved_chapter_num = chapter_num or self._extract_chapter_number(chapter_id)
        if not resolved_chapter_num:
            return ChapterSummaryResult(
                success=False,
                chapter_num=0,
                summary_path=None,
                summary_data={},
                model=self.model,
                error=f"Unable to resolve chapter number from chapter_id='{chapter_id}'",
            )

        resolved_title = (chapter_title or f"Chapter {resolved_chapter_num}").strip()
        summary_path = self.context_dir / f"CHAPTER_{resolved_chapter_num:02d}_SUMMARY.json"

        if not translation_text or not translation_text.strip():
            fallback = self._build_fallback_summary(
                chapter_num=resolved_chapter_num,
                chapter_title=resolved_title,
                translation_text=translation_text or "",
            )
            self._write_summary(summary_path, fallback)
            return ChapterSummaryResult(
                success=True,
                chapter_num=resolved_chapter_num,
                summary_path=summary_path,
                summary_data=fallback,
                model=self.model,
                used_fallback=True,
                error="Empty translation text; used fallback summary.",
            )

        prompt = self._build_summary_prompt(
            chapter_num=resolved_chapter_num,
            chapter_title=resolved_title,
            translation_text=translation_text,
        )

        try:
            response = self.client.generate(
                prompt=prompt,
                system_instruction=None,
                temperature=0.2,
                max_output_tokens=2048,
                model=self.model,
                force_new_session=True,
            )
            parsed = self._parse_summary_json(response.content or "")
            if not parsed:
                raise ValueError("Model returned non-JSON or invalid summary payload")

            normalized = self._normalize_summary_payload(
                parsed=parsed,
                chapter_num=resolved_chapter_num,
                chapter_title=resolved_title,
                fallback_text=translation_text,
            )
            self._write_summary(summary_path, normalized)
            return ChapterSummaryResult(
                success=True,
                chapter_num=resolved_chapter_num,
                summary_path=summary_path,
                summary_data=normalized,
                model=self.model,
                used_fallback=False,
            )
        except Exception as exc:
            logger.warning(
                f"[CH-SUMMARY] Gemini summary failed for {chapter_id}: {exc}. "
                "Falling back to heuristic summary."
            )
            fallback = self._build_fallback_summary(
                chapter_num=resolved_chapter_num,
                chapter_title=resolved_title,
                translation_text=translation_text,
            )
            self._write_summary(summary_path, fallback)
            return ChapterSummaryResult(
                success=True,
                chapter_num=resolved_chapter_num,
                summary_path=summary_path,
                summary_data=fallback,
                model=self.model,
                used_fallback=True,
                error=str(exc),
            )

    def _extract_chapter_number(self, chapter_id: str) -> Optional[int]:
        """Extract chapter number from chapter_id-like strings."""
        match = self._CHAPTER_NUM_RE.search(str(chapter_id or ""))
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    def _build_summary_prompt(
        self,
        chapter_num: int,
        chapter_title: str,
        translation_text: str,
    ) -> str:
        """Build strict JSON-only summary prompt."""
        return (
            "You are a chapter summarization assistant for light novel translation continuity.\n"
            "Summarize the chapter into concise continuity signals.\n"
            "Return ONLY valid JSON. No markdown fences. No extra text.\n\n"
            "Required JSON schema:\n"
            "{\n"
            '  "chapter_num": <int>,\n'
            '  "title": <string>,\n'
            '  "plot_points": <array of 3-6 short strings>,\n'
            '  "emotional_tone": <string>,\n'
            '  "new_characters": <array of character names introduced in this chapter>,\n'
            '  "running_jokes": <array of recurring joke motifs appearing in this chapter>,\n'
            '  "tone_shifts": <array of notable tone changes in chapter order>\n'
            "}\n\n"
            f"Language of summary fields should match chapter language: {self.target_language}.\n"
            "Keep each array item short and concrete.\n\n"
            f"CHAPTER NUMBER: {chapter_num}\n"
            f"CHAPTER TITLE: {chapter_title}\n\n"
            "CHAPTER TEXT:\n"
            f"{translation_text.strip()}\n"
        )

    def _parse_summary_json(self, raw: str) -> Optional[Dict[str, Any]]:
        """Parse JSON payload with tolerant extraction."""
        text = (raw or "").strip()
        if not text:
            return None

        # Strip markdown fences if present.
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            snippet = text[start : end + 1]
            try:
                payload = json.loads(snippet)
                return payload if isinstance(payload, dict) else None
            except Exception:
                return None

    def _normalize_summary_payload(
        self,
        parsed: Dict[str, Any],
        chapter_num: int,
        chapter_title: str,
        fallback_text: str,
    ) -> Dict[str, Any]:
        """Normalize to strict ChapterSummary schema."""
        payload = {
            "chapter_num": chapter_num,
            "title": str(parsed.get("title") or chapter_title).strip() or chapter_title,
            "plot_points": self._clean_string_list(parsed.get("plot_points"), limit=6),
            "emotional_tone": str(parsed.get("emotional_tone") or "").strip(),
            "new_characters": self._clean_string_list(parsed.get("new_characters"), limit=12),
            "running_jokes": self._clean_string_list(parsed.get("running_jokes"), limit=8),
            "tone_shifts": self._clean_string_list(parsed.get("tone_shifts"), limit=8),
        }

        if not payload["plot_points"]:
            fallback = self._build_fallback_summary(chapter_num, chapter_title, fallback_text)
            payload["plot_points"] = fallback["plot_points"]

        if not payload["emotional_tone"]:
            payload["emotional_tone"] = "neutral"

        return payload

    def _build_fallback_summary(
        self,
        chapter_num: int,
        chapter_title: str,
        translation_text: str,
    ) -> Dict[str, Any]:
        """Heuristic summary when LLM output is unavailable."""
        sentences = self._extract_sentences(translation_text)
        plot_points = [s for s in sentences[:3] if s]
        if not plot_points:
            plot_points = [f"Chapter {chapter_num} translated successfully."]

        return {
            "chapter_num": chapter_num,
            "title": chapter_title,
            "plot_points": plot_points,
            "emotional_tone": "neutral",
            "new_characters": [],
            "running_jokes": [],
            "tone_shifts": [],
        }

    def _extract_sentences(self, text: str) -> List[str]:
        """Extract compact sentence candidates from chapter text."""
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        condensed = " ".join(lines)
        if not condensed:
            return []

        parts = self._SENTENCE_SPLIT_RE.split(condensed)
        cleaned: List[str] = []
        for part in parts:
            sentence = re.sub(r"\s+", " ", part).strip()
            if len(sentence) < 20:
                continue
            cleaned.append(sentence[:220])
            if len(cleaned) >= 6:
                break
        return cleaned

    def _clean_string_list(self, value: Any, limit: int) -> List[str]:
        """Normalize list values to unique non-empty strings."""
        if not isinstance(value, list):
            return []
        out: List[str] = []
        seen = set()
        for item in value:
            text = str(item).strip() if item is not None else ""
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text[:220])
            if len(out) >= limit:
                break
        return out

    def _write_summary(self, path: Path, payload: Dict[str, Any]) -> None:
        """Persist summary file to .context."""
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.info(f"[CH-SUMMARY] Wrote chapter summary: {path.name}")
