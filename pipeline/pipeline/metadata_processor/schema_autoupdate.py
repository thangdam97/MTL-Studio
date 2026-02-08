"""
Schema auto-update step for Phase 1.5.

This module fills Librarian-generated metadata_en schema placeholders
through a dedicated Gemini API call, then merges the patch into manifest.json.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from google.genai import types

from pipeline.common.gemini_client import GeminiClient
from pipeline.config import PIPELINE_ROOT

logger = logging.getLogger("SchemaAutoUpdate")


class SchemaAutoUpdater:
    """Auto-fill metadata_en schema fields using Gemini."""

    MODEL_NAME = "gemini-2.5-flash"
    TEMPERATURE = 0.5
    MAX_OUTPUT_TOKENS = 32768

    # Keep context bounded for very large books.
    MAX_CONTEXT_CHAPTERS = 20
    MAX_CONTEXT_CHARS = 120000
    PER_CHAPTER_EXCERPT_CHARS = 6500
    EXCERPT_HEAD_CHARS = 4300
    EXCERPT_TAIL_CHARS = 1900

    # Translation fields are handled later by metadata processor.
    PROTECTED_TOP_LEVEL_FIELDS = {
        "title_en",
        "author_en",
        "illustrator_en",
        "publisher_en",
        "series_en",
        "character_names",
        "target_language",
        "language_code",
    }
    PROTECTED_CHAPTER_FIELDS = {"title_en", "title_vn"}

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.manifest_path = work_dir / "manifest.json"
        self.schema_spec_path = PIPELINE_ROOT / "SCHEMA_V3.9_AGENT.md"
        self.client = GeminiClient(model=self.MODEL_NAME, enable_caching=False)

    def apply(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply schema auto-update patch to manifest in-memory.

        Returns:
            Dict with metadata about update process.
        """
        metadata = manifest.get("metadata", {})
        metadata_en = manifest.get("metadata_en", {})
        search_hint = self._detect_localized_series_hint(metadata)
        prompt = self._build_prompt(manifest, search_hint)
        system_instruction = self._build_system_instruction()
        tools = None
        if search_hint.get("use_online_search"):
            tools = [types.Tool(google_search=types.GoogleSearch())]
            logger.info(
                "Localized series hint detected (%s). Enabling online search grounding for official metadata.",
                search_hint.get("localized_series_name", ""),
            )

        response = self.client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=self.TEMPERATURE,
            max_output_tokens=self.MAX_OUTPUT_TOKENS,
            model=self.MODEL_NAME,
            tools=tools,
        )
        payload = self._parse_json_response(response.content)
        patch = payload.get("metadata_en_patch", payload)

        if not isinstance(patch, dict):
            raise ValueError("Schema auto-update response did not include a valid metadata_en patch object")

        patch = self._sanitize_patch(patch)
        manifest["metadata_en"] = self._deep_merge_dict(metadata_en, patch)
        self._mark_pipeline_state(
            manifest=manifest,
            status="completed",
            updated_keys=sorted(patch.keys()),
            output_tokens=response.output_tokens,
            online_search_used=bool(tools),
            localized_series_name=search_hint.get("localized_series_name"),
        )
        return {
            "status": "completed",
            "updated_keys": sorted(patch.keys()),
            "output_tokens": response.output_tokens,
            "online_search_used": bool(tools),
        }

    def mark_failed(self, manifest: Dict[str, Any], error: Exception) -> None:
        """Record failed schema update state without throwing away phase 1.5."""
        self._mark_pipeline_state(
            manifest=manifest,
            status="failed",
            error=str(error)[:500],
        )

    def _build_system_instruction(self) -> str:
        base = (
            "You are the Schema v3.9 Metadata Agent for an MTL light novel pipeline.\n"
            "Your job is to enrich metadata_en fields using extracted source data.\n"
            "Return JSON only. Do not output markdown or commentary.\n"
            "Use this output shape:\n"
            "{\n"
            '  "metadata_en_patch": {\n'
            '    "character_profiles": {...},\n'
            '    "localization_notes": {...},\n'
            '    "chapters": {...},\n'
            '    "schema_version": "v3.9",\n'
            '    "official_localization": {\n'
            '      "should_use_official": true,\n'
            '      "series_title_en": "string",\n'
            '      "volume_title_en": "string",\n'
            '      "author_en": "string",\n'
            '      "publisher_en": "string",\n'
            '      "confidence": "high|medium|low",\n'
            '      "sources": [{"title": "string", "url": "https://..."}]\n'
            "    }\n"
            "  }\n"
            "}\n"
            "Do not write translation fields such as title_en, author_en, chapter title_en, or character_names.\n"
            "Respect existing chapter ids and character profile keys when patching.\n"
            "Directive: when a localized series name is detected, perform online search and prioritize official localization metadata."
        )
        if not self.schema_spec_path.exists():
            return base

        try:
            schema_spec = self.schema_spec_path.read_text(encoding="utf-8")
            return f"{base}\n\nReference spec:\n{schema_spec}"
        except Exception as e:
            logger.warning(f"Could not read schema spec file: {e}")
            return base

    def _build_prompt(self, manifest: Dict[str, Any], search_hint: Dict[str, Any]) -> str:
        metadata = manifest.get("metadata", {})
        metadata_en = manifest.get("metadata_en", {})
        chapter_entries = manifest.get("chapters", [])

        chapter_outline = [
            {
                "id": ch.get("id", ""),
                "title": ch.get("title", ""),
                "source_file": ch.get("source_file", ""),
                "word_count": ch.get("word_count", 0),
            }
            for ch in chapter_entries
        ]

        snippets = self._collect_chapter_snippets(chapter_entries)
        payload = {
            "metadata": metadata,
            "metadata_en_seed": metadata_en,
            "ruby_names": manifest.get("ruby_names", []),
            "chapter_outline": chapter_outline,
            "chapter_snippets": snippets,
            "localized_series_hint": search_hint,
        }

        prompt = (
            "Generate metadata_en_patch for schema auto-update.\n"
            "Requirements:\n"
            "- Fill [TO BE FILLED] and weak placeholder values with concrete data where possible.\n"
            "- Add RTAS-compatible relationship structures when inferable.\n"
            "- Keep unknown values empty rather than hallucinating.\n"
            "- Keep chapter ids unchanged.\n"
            "- If localized_series_hint.use_online_search=true, use online search and adopt official localization metadata.\n"
            "- Output valid JSON only.\n\n"
            f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        if search_hint.get("use_online_search"):
            query = search_hint.get("search_query", "")
            prompt += (
                "\n\nOfficial localization directive:\n"
                f"- Execute web search for this query: {query}\n"
                "- Prefer publisher listing, official English license pages, and major distributor pages.\n"
                "- Populate metadata_en_patch.official_localization from official sources.\n"
                "- Set should_use_official=true when confidence is medium/high.\n"
            )
        return prompt

    def _detect_localized_series_hint(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect whether metadata indicates an existing localized series name.

        Examples:
        - "Madan no Ou to Vanadis (Lord Marksman and Vanadis)"
        - Series/title fields containing both JP and Latin-script aliases.
        """
        series = str(metadata.get("series", "") or "").strip()
        title = str(metadata.get("title", "") or "").strip()
        author = str(metadata.get("author", "") or "").strip()

        candidates = [series, title]
        localized = ""
        for candidate in candidates:
            if not candidate:
                continue
            m = re.search(r"\(([^)]*[A-Za-z][^)]*)\)", candidate)
            if m:
                localized = m.group(1).strip()
                break
            # Fallback: any Latin-script heavy segment without parentheses.
            latin_chunks = re.findall(r"[A-Za-z][A-Za-z0-9 '&:,-]{3,}", candidate)
            if latin_chunks:
                localized = max(latin_chunks, key=len).strip()
                break

        use_online_search = bool(localized)
        search_title = localized or series or title
        query = " ".join(part for part in [search_title, author, "official English localization"] if part).strip()

        return {
            "use_online_search": use_online_search,
            "localized_series_name": localized,
            "search_query": query,
        }

    def _collect_chapter_snippets(self, chapter_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        snippets: List[Dict[str, Any]] = []
        if not chapter_entries:
            return snippets

        total_chars = 0
        for idx in self._select_spread_indices(len(chapter_entries), self.MAX_CONTEXT_CHAPTERS):
            chapter = chapter_entries[idx]
            source_file = chapter.get("source_file", "")
            if not source_file:
                continue

            chapter_path = self.work_dir / "JP" / source_file
            if not chapter_path.exists():
                continue

            try:
                text = chapter_path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                continue

            excerpt = self._make_excerpt(text)
            if not excerpt:
                continue

            remaining = self.MAX_CONTEXT_CHARS - total_chars
            if remaining <= 512:
                break
            if len(excerpt) > remaining:
                excerpt = excerpt[: max(0, remaining - 24)] + "\n[...truncated...]"

            snippets.append(
                {
                    "id": chapter.get("id", ""),
                    "title": chapter.get("title", ""),
                    "source_file": source_file,
                    "excerpt": excerpt,
                    "full_length_chars": len(text),
                }
            )
            total_chars += len(excerpt)

        return snippets

    def _make_excerpt(self, text: str) -> str:
        if len(text) <= self.PER_CHAPTER_EXCERPT_CHARS:
            return text
        head = text[: self.EXCERPT_HEAD_CHARS]
        tail = text[-self.EXCERPT_TAIL_CHARS :]
        omitted = max(0, len(text) - len(head) - len(tail))
        return f"{head}\n\n[... {omitted} chars omitted ...]\n\n{tail}"

    def _select_spread_indices(self, total: int, limit: int) -> List[int]:
        if total <= limit:
            return list(range(total))
        if limit <= 1:
            return [0]
        return sorted({round(i * (total - 1) / (limit - 1)) for i in range(limit)})

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _sanitize_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(patch)
        for field in self.PROTECTED_TOP_LEVEL_FIELDS:
            cleaned.pop(field, None)

        chapters = cleaned.get("chapters")
        if isinstance(chapters, dict):
            for chapter_id, chapter_data in chapters.items():
                if not isinstance(chapter_data, dict):
                    continue
                for protected in self.PROTECTED_CHAPTER_FIELDS:
                    chapter_data.pop(protected, None)
                chapters[chapter_id] = chapter_data

        return cleaned

    def _deep_merge_dict(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, patch_value in patch.items():
            base_value = merged.get(key)
            if isinstance(base_value, dict) and isinstance(patch_value, dict):
                merged[key] = self._deep_merge_dict(base_value, patch_value)
            else:
                merged[key] = patch_value
        return merged

    def _mark_pipeline_state(
        self,
        manifest: Dict[str, Any],
        status: str,
        updated_keys: List[str] | None = None,
        output_tokens: int | None = None,
        error: str | None = None,
        online_search_used: bool = False,
        localized_series_name: str | None = None,
    ) -> None:
        pipeline_state = manifest.setdefault("pipeline_state", {})
        schema_state: Dict[str, Any] = {
            "status": status,
            "timestamp": datetime.datetime.now().isoformat(),
            "model": self.MODEL_NAME,
            "temperature": self.TEMPERATURE,
            "max_output_tokens": self.MAX_OUTPUT_TOKENS,
            "online_search_used": online_search_used,
        }
        if localized_series_name:
            schema_state["localized_series_name"] = localized_series_name
        if updated_keys:
            schema_state["updated_keys"] = updated_keys
        if output_tokens is not None:
            schema_state["output_tokens"] = output_tokens
        if error:
            schema_state["error"] = error
        pipeline_state["schema_agent"] = schema_state
