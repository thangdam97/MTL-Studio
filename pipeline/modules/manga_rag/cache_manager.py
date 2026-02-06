"""
Manga Cache Manager.

Handles loading, saving, and querying manga_cache.json
that stores pre-baked manga panel analysis from Gemini 3 Pro Vision.

Mirrors modules/multimodal/cache_manager.py but stores manga-specific
panel-level data (characters, expressions, body language, dialogue).

🧪 EXPERIMENTAL — Phase 1.8a
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


class MangaCacheManager:
    """Manage manga panel analysis cache (manga_cache.json)."""

    def __init__(
        self,
        volume_path: Path,
        cache_filename: str = "manga_cache.json",
    ):
        self.volume_path = volume_path
        self.cache_path = volume_path / cache_filename
        self.cache: Dict[str, Any] = self._load_cache()

    # ─── Load / Save ─────────────────────────────────────────────────

    def _load_cache(self) -> Dict[str, Any]:
        """Load existing manga cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                page_count = len(cache.get("pages", {}))
                logger.info(f"[MANGA] Loaded manga cache: {page_count} pages")
                return cache
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[MANGA] Failed to load manga cache: {e}")
        return self._empty_cache()

    def _empty_cache(self) -> Dict[str, Any]:
        """Return empty cache structure."""
        return {
            "schema_version": "1.0_experimental",
            "manga_source": None,
            "total_pages_analyzed": 0,
            "total_panels_indexed": 0,
            "analysis_model": None,
            "analysis_date": None,
            "pages": {},
        }

    def save_cache(self) -> None:
        """Persist manga cache to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Update summary fields
            pages = self.cache.get("pages", {})
            self.cache["total_pages_analyzed"] = len(pages)
            self.cache["total_panels_indexed"] = sum(
                p.get("panel_count", 0) for p in pages.values()
            )
            self.cache["analysis_date"] = datetime.now().isoformat()

            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)

            size_kb = self.cache_path.stat().st_size / 1024
            logger.info(
                f"[MANGA] ✓ Cache saved: {len(pages)} pages, "
                f"{self.cache['total_panels_indexed']} panels ({size_kb:.1f} KB)"
            )
        except Exception as e:
            logger.error(f"[MANGA] ✗ Failed to save manga cache: {e}")
            raise

    # ─── Page Operations ─────────────────────────────────────────────

    def has_page(self, page_number: int) -> bool:
        """Check if a page has been analyzed."""
        return str(page_number) in self.cache.get("pages", {})

    def get_page(self, page_number: int) -> Optional[Dict[str, Any]]:
        """Get analysis for a specific page."""
        return self.cache.get("pages", {}).get(str(page_number))

    def store_page(self, page_number: int, analysis: Dict[str, Any]) -> None:
        """Store analysis for a page."""
        if "pages" not in self.cache:
            self.cache["pages"] = {}

        # Generate content hash for change detection
        content_str = json.dumps(analysis, sort_keys=True)
        cache_key = hashlib.sha256(content_str.encode()).hexdigest()[:16]
        analysis["cache_key"] = f"sha256:{cache_key}"

        self.cache["pages"][str(page_number)] = analysis

    def get_all_panels(self) -> List[Dict[str, Any]]:
        """Get all panels from all pages, flattened."""
        panels = []
        for page_num, page_data in self.cache.get("pages", {}).items():
            for panel in page_data.get("panels", []):
                panel_copy = dict(panel)
                panel_copy["page_number"] = int(page_num)
                panel_copy["chapter_number"] = page_data.get("chapter_number")
                panels.append(panel_copy)
        return panels

    def get_panels_for_chapter(self, chapter_number: int) -> List[Dict[str, Any]]:
        """Get all panels from a specific manga chapter."""
        panels = []
        for page_num, page_data in self.cache.get("pages", {}).items():
            if page_data.get("chapter_number") == chapter_number:
                for panel in page_data.get("panels", []):
                    panel_copy = dict(panel)
                    panel_copy["page_number"] = int(page_num)
                    panels.append(panel_copy)
        return panels

    def get_panels_for_page_range(
        self, start_page: int, end_page: int
    ) -> List[Dict[str, Any]]:
        """Get all panels within a page range (inclusive)."""
        panels = []
        for page_num_str, page_data in self.cache.get("pages", {}).items():
            page_num = int(page_num_str)
            if start_page <= page_num <= end_page:
                for panel in page_data.get("panels", []):
                    panel_copy = dict(panel)
                    panel_copy["page_number"] = page_num
                    panels.append(panel_copy)
        return panels

    # ─── Metadata ────────────────────────────────────────────────────

    def set_source_metadata(
        self,
        manga_source: str,
        model: str,
    ) -> None:
        """Set manga source metadata."""
        self.cache["manga_source"] = manga_source
        self.cache["analysis_model"] = model

    def has_cache(self) -> bool:
        """Check if any pages have been analyzed."""
        return len(self.cache.get("pages", {})) > 0

    @property
    def page_count(self) -> int:
        return len(self.cache.get("pages", {}))

    @property
    def panel_count(self) -> int:
        return sum(
            p.get("panel_count", 0)
            for p in self.cache.get("pages", {}).values()
        )

    def summary(self) -> str:
        """Return human-readable cache summary."""
        return (
            f"Manga Cache: {self.page_count} pages, "
            f"{self.panel_count} panels | "
            f"Source: {self.cache.get('manga_source', 'unknown')} | "
            f"Model: {self.cache.get('analysis_model', 'unknown')}"
        )
