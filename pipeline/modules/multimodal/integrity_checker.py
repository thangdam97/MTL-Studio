"""
Illustration Integrity Checker (Pre-flight for Phase 1.6).

Validates that all illustration references in JP source markdown are
consistent with the assets on disk and the manifest ID mapping before
the Multimodal Processor spends API credits on Gemini Vision calls.

Checks performed:
  1. TAG→FILE:   Every [ILLUSTRATION: X] tag in JP/*.md has a matching
                 file in assets/illustrations/ (via epub_id_to_cache_id mapping)
  2. FILE→TAG:   Every illust-NNN.jpg in assets/illustrations/ is referenced
                 by at least one JP tag (orphan detection)
  3. KUCHIE:     Every kuchie-NNN.jpg in assets/kuchie/ exists on disk
  4. COVER:      assets/cover.jpg (or .png) exists
  5. MAPPING:    epub_id_to_cache_id in manifest.json covers every JP tag ID

Usage:
    from modules.multimodal.integrity_checker import check_illustration_integrity

    report = check_illustration_integrity(volume_path)
    if not report.passed:
        # Block Phase 1.6
        for error in report.errors:
            print(f"  ✗ {error}")
"""

import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any

logger = logging.getLogger(__name__)


# Reuse the same patterns as segment_classifier.py
_LEGACY_BRACKET = re.compile(
    r'\[ILLUSTRATION:?\s*"?([^"\]]+)"?\]', re.IGNORECASE
)
_MARKDOWN_IMAGE = re.compile(
    r'!\[(illustration|)\]\(([^)]+)\)', re.IGNORECASE
)
_EXTENSION = re.compile(r'\.(jpg|jpeg|png|gif|webp|svg)$', re.IGNORECASE)


def _strip_ext(name: str) -> str:
    """Remove image file extension from an ID."""
    return _EXTENSION.sub('', name.strip())


@dataclass
class TagReference:
    """A single illustration tag found in a JP source file."""
    file: str           # e.g. "CHAPTER_01.md"
    line: int           # 1-based line number
    raw_tag: str        # Full matched string, e.g. "[ILLUSTRATION: i-019.jpg]"
    epub_id: str        # Bare ID without extension, e.g. "i-019"
    format: str         # "legacy_bracket" or "markdown_image"


@dataclass
class IntegrityReport:
    """Result of the pre-flight illustration integrity check."""
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Detailed inventories
    tags_found: List[TagReference] = field(default_factory=list)
    asset_illustrations: List[str] = field(default_factory=list)   # illust-NNN
    asset_kuchie: List[str] = field(default_factory=list)          # kuchie-NNN
    asset_cover: Optional[str] = None

    # Mapping state
    mapping: Dict[str, str] = field(default_factory=dict)  # epub_id → cache_id
    unmapped_tags: List[TagReference] = field(default_factory=list)
    orphan_assets: List[str] = field(default_factory=list)
    missing_assets: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def total_checks(self) -> int:
        return len(self.errors) + len(self.warnings)

    def summary(self) -> str:
        """One-line summary for log output."""
        tag_count = len(self.tags_found)
        asset_count = len(self.asset_illustrations) + len(self.asset_kuchie)
        if self.asset_cover:
            asset_count += 1
        status = "PASS ✅" if self.passed else "FAIL ❌"
        return (
            f"Integrity {status}: {tag_count} tags, {asset_count} assets, "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )


# ============================================================================
# STEP 1: Scan JP source files for all illustration tags
# ============================================================================

def _scan_jp_tags(jp_dir: Path) -> List[TagReference]:
    """Scan all JP/*.md files for illustration marker tags."""
    tags: List[TagReference] = []

    if not jp_dir.exists():
        return tags

    for md_file in sorted(jp_dir.glob("*.md")):
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except (IOError, UnicodeDecodeError) as e:
            logger.warning(f"[INTEGRITY] Cannot read {md_file.name}: {e}")
            continue

        for line_num, line in enumerate(lines, start=1):
            # Legacy bracket: [ILLUSTRATION: i-019.jpg]
            for m in _LEGACY_BRACKET.finditer(line):
                raw_id = m.group(1).strip()
                tags.append(TagReference(
                    file=md_file.name,
                    line=line_num,
                    raw_tag=m.group(0),
                    epub_id=_strip_ext(raw_id),
                    format="legacy_bracket",
                ))

            # Markdown image: ![illustration](filename.jpg)
            for m in _MARKDOWN_IMAGE.finditer(line):
                raw_id = m.group(2).strip()
                # Skip gaiji — they are inline glyph replacements, not illustrations
                if "gaiji" in raw_id.lower():
                    continue
                tags.append(TagReference(
                    file=md_file.name,
                    line=line_num,
                    raw_tag=m.group(0),
                    epub_id=_strip_ext(raw_id),
                    format="markdown_image",
                ))

    return tags


# ============================================================================
# STEP 2: Inventory assets on disk
# ============================================================================

def _inventory_assets(volume_path: Path) -> tuple:
    """
    Inventory illustration assets on disk.
    
    Recognizes ALL common EPUB illustration naming patterns:
    - Standard: illust-NNN, p###, m###, k###, kuchie-NNN
    - Special: profile, tokuten, ok, oku, allcover, allcover-NNN
    - Legacy: image#, image_rsrc*
    - Publisher: i-bookwalker, *_title
    - Gaiji: gaiji-NNNN (excluded from illustrations)

    Returns:
        (illustrations: list[str], kuchie: list[str], cover: str|None, assets_dir: Path|None)
    """
    # Same fallback logic as asset_processor.py
    assets_dir = volume_path / "_assets"
    if not assets_dir.exists():
        assets_dir = volume_path / "assets"
    if not assets_dir.exists():
        return [], [], None, None

    illustrations: List[str] = []
    kuchie: List[str] = []
    cover: Optional[str] = None

    # Patterns to EXCLUDE from illustration inventory
    EXCLUDE_PATTERNS = {
        'cover', 'gaiji-', 'i-bookwalker', '_title'
    }
    
    # Patterns that identify KUCHIE (color plates)
    KUCHIE_PATTERNS = {
        'kuchie-', 'k001', 'k002', 'k003', 'k004', 'k005', 'k006', 'k007', 'k008'
    }

    # Inline illustrations
    illust_dir = assets_dir / "illustrations"
    for search_dir in [illust_dir, assets_dir]:
        if search_dir.exists():
            for f in sorted(search_dir.glob("*.*")):
                if f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue
                    
                stem = f.stem.lower()
                
                # Check exclusions
                if any(stem.startswith(pattern) for pattern in EXCLUDE_PATTERNS):
                    continue
                
                # Classify as kuchie or illustration
                if any(stem.startswith(pattern) for pattern in KUCHIE_PATTERNS):
                    kuchie.append(f.stem)
                else:
                    # Accept as illustration:
                    # illust-*, p###, m###, image*, tokuten, profile, ok, oku, allcover-NNN, etc.
                    illustrations.append(f.stem)
                    
            if illustrations or kuchie:
                break

    # Kuchie color plates from dedicated directory
    kuchie_dir = assets_dir / "kuchie"
    if kuchie_dir.exists():
        for f in sorted(kuchie_dir.glob("*.*")):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                if f.stem not in kuchie:  # Avoid duplicates
                    kuchie.append(f.stem)

    # Cover art
    for f in assets_dir.glob("cover.*"):
        if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
            cover = f.name
            break

    return illustrations, kuchie, cover, assets_dir


# ============================================================================
# STEP 3: Load epub_id_to_cache_id mapping from manifest
# ============================================================================

def _load_id_mapping(volume_path: Path) -> Dict[str, str]:
    """Load epub_id → cache_id mapping from manifest.json multimodal section."""
    manifest_path = volume_path / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest.get("multimodal", {}).get("epub_id_to_cache_id", {})
    except (json.JSONDecodeError, IOError):
        return {}


# ============================================================================
# MAIN: Run all integrity checks
# ============================================================================

def check_illustration_integrity(volume_path: Path) -> IntegrityReport:
    """
    Run pre-flight illustration integrity checks for a volume.

    This should be called BEFORE Phase 1.6 (Multimodal Processor) to catch
    mismatches between JP source tags, asset files, and the manifest mapping.

    Args:
        volume_path: Path to the volume working directory.

    Returns:
        IntegrityReport with pass/fail status and detailed findings.
    """
    report = IntegrityReport()
    jp_dir = volume_path / "JP"

    # ── Step 1: Scan JP tags ──────────────────────────────────────────────
    report.tags_found = _scan_jp_tags(jp_dir)
    if not report.tags_found:
        report.add_warning("No illustration tags found in JP/*.md — nothing to validate")
        return report

    logger.info(f"[INTEGRITY] Found {len(report.tags_found)} illustration tag(s) in JP source")
    for tag in report.tags_found:
        logger.debug(f"  {tag.file}:{tag.line}  {tag.raw_tag}  → epub_id={tag.epub_id}")

    # ── Step 2: Inventory assets ──────────────────────────────────────────
    illustrations, kuchie, cover, assets_dir = _inventory_assets(volume_path)
    report.asset_illustrations = illustrations
    report.asset_kuchie = kuchie
    report.asset_cover = cover

    if assets_dir is None:
        report.add_error(
            "No assets directory found (checked _assets/ and assets/). "
            "Cannot verify illustration files."
        )
        return report

    logger.info(
        f"[INTEGRITY] Assets on disk: {len(illustrations)} illustrations, "
        f"{len(kuchie)} kuchie, cover={'yes' if cover else 'no'}"
    )

    # ── Step 3: Load ID mapping ───────────────────────────────────────────
    report.mapping = _load_id_mapping(volume_path)
    if not report.mapping:
        report.add_warning(
            "No epub_id_to_cache_id mapping in manifest.json. "
            "Tags will be matched by direct filename only."
        )

    # ── Check A: Every JP tag maps to an asset on disk ────────────────────
    asset_set = set(illustrations) | set(kuchie)
    mapped_assets: Set[str] = set()

    for tag in report.tags_found:
        # Resolve epub_id → cache_id (or direct match)
        cache_id = report.mapping.get(tag.epub_id)

        if cache_id is None:
            # Try direct match (tag epub_id IS the cache_id)
            if tag.epub_id in asset_set:
                cache_id = tag.epub_id
            else:
                report.unmapped_tags.append(tag)
                report.add_error(
                    f"TAG→FILE mismatch: {tag.file}:{tag.line} tag [{tag.epub_id}] "
                    f"has no mapping in manifest and no matching asset file"
                )
                continue

        if cache_id not in asset_set:
            report.missing_assets.append(cache_id)
            report.add_error(
                f"Missing asset: {tag.file}:{tag.line} tag [{tag.epub_id}] "
                f"maps to [{cache_id}] but {cache_id}.jpg not found in {assets_dir}"
            )
        else:
            mapped_assets.add(cache_id)

    # ── Check B: Every asset file is referenced by at least one tag ───────
    epub_id_targets = set(report.mapping.values()) if report.mapping else set()
    tag_epub_ids = {tag.epub_id for tag in report.tags_found}

    for asset_id in illustrations:
        # Check: Is this asset referenced directly or via mapping?
        is_mapped = asset_id in epub_id_targets or asset_id in mapped_assets
        is_direct = asset_id in tag_epub_ids

        if not is_mapped and not is_direct:
            report.orphan_assets.append(asset_id)
            report.add_warning(
                f"Orphan asset: {asset_id}.jpg exists in assets/illustrations/ "
                f"but no JP tag references it"
            )

    # ── Check C: All kuchie files exist ───────────────────────────────────
    kuchie_dir = assets_dir / "kuchie"
    if kuchie_dir and kuchie_dir.exists():
        for kid in kuchie:
            # Kuchie don't need JP tags — verify known image extensions.
            # NOTE: keep .jpeg support in sync with _inventory_assets().
            kuchie_exists = any(
                (kuchie_dir / f"{kid}{ext}").exists()
                for ext in (".jpg", ".jpeg", ".png")
            )
            if not kuchie_exists:
                report.add_error(f"Kuchie file missing: {kid} not found in {kuchie_dir}")

    # ── Check D: Cover art exists ─────────────────────────────────────────
    if not cover:
        report.add_warning("No cover art found in assets/ (cover.jpg or cover.png)")

    # ── Check E: Tag count vs asset count sanity ──────────────────────────
    unique_tag_ids = {tag.epub_id for tag in report.tags_found}
    if len(unique_tag_ids) != len(illustrations):
        report.add_warning(
            f"Count mismatch: {len(unique_tag_ids)} unique JP tags vs "
            f"{len(illustrations)} illustration assets — verify mapping is complete"
        )

    return report
