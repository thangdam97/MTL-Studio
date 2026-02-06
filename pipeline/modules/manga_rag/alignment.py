"""
LN ↔ Manga Chapter Alignment Engine.

Maps Light Novel chapters to their corresponding manga chapter/page ranges.
This is the "coarse alignment" layer that scopes retrieval queries to the
correct manga pages for each LN chapter.

Methods:
  1. Manual — YAML alignment file (reliable, initial implementation)
  2. Dialogue Match — Fuzzy match LN dialogue with manga OCR (future)
  3. Embedding — Semantic similarity between LN segments and panels (future)

🧪 EXPERIMENTAL — Phase 1.8b
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ChapterAlignment:
    """
    Manages LN ↔ Manga chapter alignment.

    Loads alignment data from:
      1. manga_alignment.yaml (manual or auto-generated)
      2. manifest.json manga_rag section (embedded alignment)

    Provides scoping for retrieval queries — ensures manga panels from
    Chapter 5 aren't retrieved when translating LN Chapter 1.
    """

    def __init__(self, volume_path: Path, alignment_file: str = "manga_alignment.yaml"):
        self.volume_path = volume_path
        self.alignment_file = volume_path / alignment_file
        self.alignment: Dict[str, Any] = {}
        self.chapter_map: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> bool:
        """
        Load alignment data from YAML file or manifest.

        Returns:
            True if alignment was loaded successfully
        """
        # Try YAML file first
        if self.alignment_file.exists():
            return self._load_from_yaml()

        # Fallback: try manifest.json
        manifest_path = self.volume_path / "manifest.json"
        if manifest_path.exists():
            return self._load_from_manifest(manifest_path)

        logger.warning(
            f"[MANGA] No alignment file found at {self.alignment_file}. "
            "Create one or run manga-align --auto."
        )
        return False

    def _load_from_yaml(self) -> bool:
        """Load from manga_alignment.yaml."""
        if not YAML_AVAILABLE:
            logger.error("[MANGA] PyYAML required for alignment: pip install pyyaml")
            return False

        try:
            with open(self.alignment_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            self.alignment = data
            self.chapter_map = data.get("alignment", {})
            self._loaded = True

            logger.info(
                f"[MANGA] Loaded alignment: {len(self.chapter_map)} chapters mapped "
                f"(method: {data.get('alignment_method', 'manual')})"
            )
            return True

        except Exception as e:
            logger.error(f"[MANGA] Failed to load alignment YAML: {e}")
            return False

    def _load_from_manifest(self, manifest_path: Path) -> bool:
        """Load alignment from manifest.json manga_rag section."""
        try:
            import json

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            manga_rag = manifest.get("manga_rag", {})
            if not manga_rag:
                return False

            self.alignment = manga_rag
            self.chapter_map = manga_rag.get("chapter_map", {})
            self._loaded = True

            logger.info(
                f"[MANGA] Loaded alignment from manifest: {len(self.chapter_map)} chapters"
            )
            return True

        except Exception as e:
            logger.error(f"[MANGA] Failed to load alignment from manifest: {e}")
            return False

    # ─── Query ───────────────────────────────────────────────────────

    def get_manga_scope(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the manga page scope for an LN chapter.

        Args:
            chapter_id: LN chapter identifier (e.g., "CHAPTER_01", "chapter_01")

        Returns:
            Dict with manga_chapters, manga_pages range, notes.
            None if no alignment exists for this chapter.
        """
        if not self._loaded:
            self.load()

        # Try exact match first, then case-insensitive
        scope = self.chapter_map.get(chapter_id)
        if scope:
            return scope

        # Try common key variants
        for variant in [
            chapter_id.upper(),
            chapter_id.lower(),
            chapter_id.replace("chapter_", "CHAPTER_"),
            chapter_id.replace("CHAPTER_", "chapter_"),
        ]:
            scope = self.chapter_map.get(variant)
            if scope:
                return scope

        return None

    def get_page_range(self, chapter_id: str) -> Optional[Tuple[int, int]]:
        """
        Get the manga page range for an LN chapter.

        Returns:
            (start_page, end_page) tuple, or None
        """
        scope = self.get_manga_scope(chapter_id)
        if not scope:
            return None

        pages = scope.get("manga_pages", [])
        if len(pages) >= 2:
            return (pages[0], pages[1])

        return None

    def get_manga_chapters(self, chapter_id: str) -> List[int]:
        """Get the manga chapter numbers that correspond to an LN chapter."""
        scope = self.get_manga_scope(chapter_id)
        if not scope:
            return []
        return scope.get("manga_chapters", [])

    def get_canon_divergence_notes(self) -> List[str]:
        """Get any canon divergence notes from the alignment."""
        return self.alignment.get("canon_divergence_notes", [])

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def mapped_chapters(self) -> List[str]:
        """List all LN chapters that have manga alignment."""
        return list(self.chapter_map.keys())

    def summary(self) -> str:
        """Human-readable alignment summary."""
        if not self._loaded:
            return "Alignment: not loaded"

        total_pages = 0
        for scope in self.chapter_map.values():
            pages = scope.get("manga_pages", [])
            if len(pages) >= 2:
                total_pages += pages[1] - pages[0] + 1

        method = self.alignment.get("alignment_method", "manual")
        return (
            f"Alignment: {len(self.chapter_map)} chapters, "
            f"~{total_pages} manga pages (method: {method})"
        )


# ─── Alignment File Generator ───────────────────────────────────────────

def generate_alignment_template(
    volume_path: Path,
    volume_id: str,
    ln_chapters: List[str],
    output_file: str = "manga_alignment.yaml",
) -> Path:
    """
    Generate a blank manga_alignment.yaml template for manual editing.

    Args:
        volume_path: Path to the volume directory
        volume_id: Volume identifier
        ln_chapters: List of LN chapter identifiers
        output_file: Output filename

    Returns:
        Path to the generated YAML file
    """
    template_lines = [
        f"# Manga Alignment for Volume {volume_id}",
        f"# Generated template — fill in manga chapter/page ranges manually",
        f"#",
        f"# Instructions:",
        f"#   manga_chapters: [start_ch, end_ch] — which manga chapters cover this LN chapter",
        f"#   manga_pages: [start_page, end_page] — page range in the manga (inclusive)",
        f"#   notes: description of the alignment",
        f"",
        f"volume_id: \"{volume_id}\"",
        f"manga_source: \"\"  # e.g., \"Series Name Manga Vol.1-3\"",
        f"alignment_method: manual",
        f"",
        f"alignment:",
    ]

    for i, chapter_id in enumerate(ln_chapters, 1):
        template_lines.extend(
            [
                f"  {chapter_id}:",
                f"    manga_chapters: []  # e.g., [{i * 2 - 1}, {i * 2}]",
                f"    manga_pages: []     # e.g., [{(i-1)*24+1}, {i*24}]",
                f'    notes: ""',
            ]
        )

    template_lines.extend(
        [
            "",
            "canon_divergence_notes:",
            '  # - "Manga Ch.X: Description of divergence from LN"',
        ]
    )

    output_path = volume_path / output_file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(template_lines) + "\n")

    logger.info(f"[MANGA] Generated alignment template: {output_path}")
    return output_path
