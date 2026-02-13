"""
Builder Agent - EPUB Assembly Orchestrator.

Main entry point for Phase 4 of the MT Publishing Pipeline.
Assembles final EPUB from translated content following industry standards
(Yen Press / J-Novel Club conventions).
"""

import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import xml.etree.ElementTree as ET

from ..config import WORK_DIR, OUTPUT_DIR, get_target_language, get_language_config
from .epub_structure import create_epub_structure, EPUBPaths
from .opf_generator import OPFGenerator, BookMetadata, ManifestItem, SpineItem
from .ncx_generator import NCXGenerator, NavPoint
from .nav_generator import NavGenerator, TOCEntry, Landmark
from .structure_builder import StructureBuilder
from .xhtml_builder import XHTMLBuilder
from .markdown_to_xhtml import MarkdownToXHTML
from .epub_packager import EPUBPackager
from .image_analyzer import get_image_dimensions, is_horizontal, analyze_kuchie_images
import re


# Industry-standard CSS for EPUB
DEFAULT_CSS = '''/* Industry Standard EPUB Stylesheet */
@charset "UTF-8";

/* Base Styles */
body {
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.6;
  margin: 1em;
  text-align: justify;
}

/* Headings */
h1 {
  text-align: center;
  font-size: 1.5em;
  margin: 2em 0 1em;
  page-break-before: always;
}

h1:first-child {
  page-break-before: avoid;
}

/* Paragraphs */
p {
  text-indent: 1.5em;
  margin: 0;
}

p.noindent, section > div > p:first-of-type {
  text-indent: 0;
}

/* Scene Break - Force center alignment with maximum specificity */
p.section-break,
.section-break,
p[class="section-break"] {
  text-align: center !important;
  text-indent: 0 !important;
  margin: 1.5em auto !important;
  padding: 0 !important;
  display: block !important;
  width: 100%;
  max-width: 100%;
}

/* Emphasis */
em {
  font-style: italic;
}

strong {
  font-weight: bold;
}

/* Cover */
.cover-image {
  text-align: center;
  text-indent: 0;
  margin: 0;
  padding: 0;
}

.cover-image img {
  max-width: 100%;
  max-height: 100vh;
  object-fit: contain;
}

/* Kuchi-e Images */
img.fullpage {
  display: block;
  max-width: 100%;
  max-height: 100vh;
  margin: 0 auto;
  object-fit: contain;
}

img.insert {
  display: block;
  max-width: 100%;
  margin: 1em auto;
  object-fit: contain;
}

p.illustration {
  text-align: center;
  text-indent: 0;
  margin: 1em 0;
}

p.kuchie-image {
  text-align: center;
  text-indent: 0;
  margin: 0;
  padding: 0;
  height: 100vh;
}

/* Horizontal Kuchi-e (SVG-based) */
.horizontal-kuchie {
  text-align: center;
  text-indent: 0;
  margin: 0;
  padding: 0;
  height: 100vh;
}

.horizontal-kuchie svg {
  display: block;
  width: 100%;
  height: 100%;
}

/* Full-page insert images */
.image_full {
  text-align: center;
  margin: 0;
  padding: 0;
  height: 100vh;
}

.image_full img.insert {
  max-width: 100%;
  max-height: 100vh;
  object-fit: contain;
}

/* TOC */
.toc-list {
  list-style: none;
  padding-left: 0;
}

.toc-list li {
  margin: 0.5em 0;
}

.toc-list a {
  text-decoration: none;
  color: inherit;
}

nav#toc ol {
  list-style: none;
  padding-left: 0;
}

nav#toc li {
  margin: 0.5em 0;
}

nav#toc a {
  text-decoration: none;
  color: inherit;
}

/* Main content wrapper */
.main {
  max-width: 100%;
}
'''


@dataclass
class BuildResult:
    """Result of EPUB build operation."""
    success: bool
    output_path: Optional[Path]
    file_size_mb: float = 0.0
    chapter_count: int = 0
    image_count: int = 0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


class BuilderAgent:
    """
    Orchestrates EPUB assembly from translated content.
    Supports multi-language configuration (EN, VN, etc.)

    Workflow:
    1. Load manifest.json
    2. Create EPUB directory structure (OEBPS/)
    3. Convert markdown chapters to XHTML
    4. Copy images to Images/
    5. Generate navigation (nav.xhtml, toc.ncx)
    6. Generate OPF manifest
    7. Copy/create stylesheet
    8. Package as .epub
    9. Validate structure
    """

    def __init__(
        self,
        work_base: Optional[Path] = None,
        output_base: Optional[Path] = None,
        target_language: str = None
    ):
        """
        Initialize Builder agent.

        Args:
            work_base: Base working directory (defaults to WORK/)
            output_base: Output directory (defaults to OUTPUT/)
            target_language: Target language code (e.g., 'en', 'vn').
                            If None, uses current target language from config.
        """
        self.work_base = Path(work_base) if work_base else WORK_DIR
        self.output_base = Path(output_base) if output_base else OUTPUT_DIR
        self.output_base.mkdir(parents=True, exist_ok=True)

        # Language configuration
        self.target_language = target_language if target_language else get_target_language()
        self.lang_config = get_language_config(self.target_language)
        self.language_name = self.lang_config.get('language_name', self.target_language.upper())
        self.language_code = self.lang_config.get('language_code', self.target_language)
        self.output_suffix = self.lang_config.get('output_suffix', f'_{self.target_language.upper()}')

    def _coerce_text(self, value: Any, fallback: str = "") -> str:
        """
        Normalize mixed manifest values (str/dict/list/etc.) to plain text.
        """
        if value is None:
            return fallback
        if isinstance(value, str):
            text = value.strip()
            return text if text else fallback
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            preferred_keys = (
                "title_en", "title_english", "english", "title",
                "name", "label", "text", "value", "romaji",
                "title_jp", "japanese"
            )
            for key in preferred_keys:
                if key in value:
                    candidate = self._coerce_text(value.get(key), "")
                    if candidate:
                        return candidate
            for candidate in value.values():
                normalized = self._coerce_text(candidate, "")
                if normalized:
                    return normalized
            return fallback
        if isinstance(value, (list, tuple)):
            parts = [self._coerce_text(v, "") for v in value]
            parts = [p for p in parts if p]
            return " / ".join(parts) if parts else fallback
        text = str(value).strip()
        return text if text else fallback

    def build_epub(
        self,
        volume_id: str,
        output_filename: Optional[str] = None,
        skip_qc_check: bool = False
    ) -> BuildResult:
        """
        Build complete EPUB from translated volume.

        Args:
            volume_id: Volume identifier (directory name in WORK/)
            output_filename: Optional custom output filename
            skip_qc_check: If True, build even if critics not complete

        Returns:
            BuildResult with status and details
        """
        print(f"\n{'='*60}")
        print(f"BUILDER AGENT - Building: {volume_id}")
        print(f"Target Language: {self.language_name} ({self.target_language.upper()})")
        print(f"{'='*60}\n")

        try:
            # Step 1: Load and validate manifest
            print("[STEP 1/8] Loading manifest...")
            work_dir = self.work_base / volume_id
            manifest = self._load_manifest(work_dir)

            # Determine target language from manifest (overrides global config)
            manifest_target_lang = manifest.get('pipeline_state', {}).get('translator', {}).get('target_language')
            if manifest_target_lang:
                # Use the language from when this volume was translated
                actual_target_lang = manifest_target_lang
                actual_lang_config = get_language_config(actual_target_lang)
                actual_language_name = actual_lang_config.get('language_name', actual_target_lang.upper())
                actual_language_code = actual_lang_config.get('language_code', actual_target_lang)
                actual_output_suffix = actual_lang_config.get('output_suffix', f'_{actual_target_lang.upper()}')
                
                if actual_target_lang != self.target_language:
                    print(f"     [INFO] Volume was translated to {actual_target_lang.upper()}, using that language config")
                    print(f"            (Current global config is {self.target_language.upper()})")
            else:
                # Fallback to global config (backward compatibility for old manifests)
                print(f"     [WARNING] No target_language in manifest, using global config: {self.target_language.upper()}")
                actual_target_lang = self.target_language
                actual_lang_config = self.lang_config
                actual_language_name = self.language_name
                actual_language_code = self.language_code
                actual_output_suffix = self.output_suffix

            if not skip_qc_check:
                self._validate_pipeline_state(manifest)

            metadata_jp = manifest.get('metadata', {})
            # Get language-specific metadata using actual target language
            metadata_key = f'metadata_{actual_target_lang}'
            metadata_translated = manifest.get(metadata_key) or manifest.get('metadata_en', {})
            
            # Support both v3.0 and v3.5 manifest schemas
            chapters = manifest.get('chapters', [])
            if not chapters and 'structure' in manifest:
                # v3.5 schema: chapters are in structure.chapters
                chapters = manifest.get('structure', {}).get('chapters', [])

            # Get title in actual target language
            # Support v3.0, v3.5, v3.6, and v3.7 schemas
            title_key = f'title_{actual_target_lang}'
            series_data = metadata_jp.get('series', {})
            # v3.7 format: check for title_english/title_japanese directly first
            if isinstance(series_data, dict) and 'title_english' in series_data:
                if actual_target_lang == 'en':
                    book_title = series_data.get('title_english') or series_data.get('title_romaji') or 'Unknown'
                else:
                    book_title = series_data.get(f'title_{actual_target_lang}') or series_data.get('title_english') or 'Unknown'
            elif isinstance(series_data, dict) and 'title' in series_data:
                series_title = series_data.get('title', {})
                if isinstance(series_title, dict):
                    # v3.5 schema: title is nested dict (title.english, title.romaji)
                    if actual_target_lang == 'en':
                        book_title = series_title.get('english') or series_title.get('romaji') or 'Unknown'
                    else:
                        book_title = series_title.get(actual_target_lang) or series_title.get('english') or series_title.get('romaji') or 'Unknown'
                else:
                    # v3.6 schema: title is string
                    book_title = series_data.get('title') or 'Unknown'
            else:
                # v3.0 schema or fallback
                # Check metadata_translated first, then top-level title_en, then fall back to Japanese
                book_title = (metadata_translated.get(title_key) or 
                             metadata_translated.get('title_en') or 
                             manifest.get('title_en') or 
                             metadata_jp.get('title', 'Unknown'))
            book_title = self._coerce_text(book_title, "Unknown")
            print(f"     Title: {book_title}")
            print(f"     Target Language: {actual_language_name}")
            print(f"     Chapters: {len(chapters)}")

            # Detect multi-act structure
            volume_structure = manifest.get('volume_structure', {})
            volume_acts = volume_structure.get('acts', [])
            is_multi_act = volume_structure.get('is_multi_act', False) and len(volume_acts) >= 2
            if is_multi_act:
                print(f"     [MULTI-ACT] {len(volume_acts)} acts detected")
                for act in volume_acts:
                    act_label = self._coerce_text(
                        act.get('title_en') or act.get('title', ''),
                        f"Act {act.get('act_number', '')}"
                    )
                    print(f"       Act {act['act_number']}: {act_label}")

            # Step 2: Create build directory
            print("\n[STEP 2/8] Creating EPUB structure...")
            build_dir = Path(tempfile.mkdtemp(prefix='epub_build_'))
            paths = create_epub_structure(build_dir)
            print(f"     Build dir: {build_dir}")

            # Step 3: Convert chapters
            print("\n[STEP 3/8] Converting chapters to XHTML...")
            chapter_items, chapter_info = self._process_chapters(
                manifest, work_dir, paths, actual_target_lang
            )
            print(f"     Converted: {len(chapter_items)} chapters")

            # Step 4: Process images
            print("\n[STEP 4/8] Processing images...")
            image_items, kuchie_metadata = self._process_images(manifest, work_dir, paths)
            print(f"     Copied: {len(image_items)} images")

            # Step 5: Generate frontmatter
            print("\n[STEP 5/8] Generating frontmatter...")
            frontmatter_items = self._generate_frontmatter(manifest, paths, chapter_info, kuchie_metadata, actual_language_code, actual_lang_config, actual_target_lang)
            print(f"     Generated: cover, kuchi-e, TOC pages")

            # Step 5.5: Generate act interstitials (separators + per-act kuchie) for multi-act
            act_items = []
            if is_multi_act:
                print("\n[STEP 5.5/8] Generating act interstitials...")
                act_items = self._generate_act_interstitials(
                    manifest, paths, chapter_info, kuchie_metadata,
                    actual_language_code, actual_lang_config, actual_target_lang
                )
                print(f"     Generated: {len(act_items)} act separator/kuchie pages")

            # Step 6: Generate navigation
            print("\n[STEP 6/8] Generating navigation...")
            nav_items = self._generate_navigation(manifest, paths, chapter_info, actual_language_code, actual_lang_config, actual_target_lang)
            print(f"     Generated: nav.xhtml, toc.ncx")

            # Step 7: Generate CSS
            print("\n[STEP 7/8] Creating stylesheet...")
            css_items = self._create_stylesheet(paths)
            print(f"     Created: stylesheet.css")

            # Step 8: Generate OPF and package
            print("\n[STEP 8/8] Generating OPF and packaging...")
            all_items = nav_items + css_items + frontmatter_items + act_items + chapter_items + image_items

            # Find cover image ID
            # Prioritize exact match for 'cover-image' to avoid matching 'allcover' first
            cover_image_id = None
            for item in image_items:
                if item.id == 'cover-image':
                    cover_image_id = item.id
                    break
            # Fallback: accept any ID containing 'cover' (but not 'allcover')
            if not cover_image_id:
                for item in image_items:
                    if 'cover' in item.id.lower() and 'allcover' not in item.id.lower():
                        cover_image_id = item.id
                        break
            # Second fallback: use first kuchie image as cover if no cover found
            if not cover_image_id:
                for item in image_items:
                    if item.id.startswith('kuchie-img-'):
                        cover_image_id = item.id
                        print(f"     [COVER] Using kuchie as cover: {item.id}")
                        break

            self._generate_opf(manifest, paths, all_items, chapter_info, cover_image_id, actual_language_code, actual_target_lang)

            # Generate output filename
            if output_filename is None:
                # Use translated title for filename if available
                title_for_filename = book_title or metadata_jp.get('title', volume_id)
                # Clean filename
                safe_title = "".join(c for c in title_for_filename if c.isalnum() or c in ' -_').strip()
                safe_title = safe_title[:50]  # Limit length
                output_filename = f"{safe_title}{actual_output_suffix}.epub"

            output_path = self.output_base / output_filename

            # Package EPUB
            EPUBPackager.package_epub(build_dir, output_path)

            # Validate
            EPUBPackager.validate_epub_structure(output_path)

            # Get file size
            file_size_mb = output_path.stat().st_size / (1024 * 1024)

            # Update manifest
            self._update_manifest(work_dir, output_filename, len(chapter_items), len(image_items))

            # Cleanup
            shutil.rmtree(build_dir, ignore_errors=True)

            # Summary
            print(f"\n{'='*60}")
            print("BUILD COMPLETE")
            print(f"{'='*60}")
            print(f"Output: {output_path}")
            print(f"Size:   {file_size_mb:.2f} MB")
            print(f"Chapters: {len(chapter_items)}")
            print(f"Images: {len(image_items)}")
            print(f"{'='*60}\n")

            return BuildResult(
                success=True,
                output_path=output_path,
                file_size_mb=file_size_mb,
                chapter_count=len(chapter_items),
                image_count=len(image_items)
            )

        except Exception as e:
            import traceback
            print(f"\n[ERROR] Build failed: {e}")
            print("\n[DEBUG] Full traceback:")
            traceback.print_exc()
            return BuildResult(
                success=False,
                output_path=None,
                error=str(e)
            )

    def _load_manifest(self, work_dir: Path) -> dict:
        """Load manifest.json from work directory."""
        manifest_path = work_dir / "manifest.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _validate_pipeline_state(self, manifest: dict) -> None:
        """Validate that previous pipeline stages are complete."""
        state = manifest.get('pipeline_state', {})

        # Check librarian
        librarian = state.get('librarian', {})
        if librarian.get('status') != 'completed':
            raise ValueError("Librarian stage not completed")

        # Check translator
        translator = state.get('translator', {})
        if translator.get('status') != 'completed':
            # Allow if at least some chapters translated
            if translator.get('chapters_completed', 0) == 0:
                raise ValueError("No chapters translated yet")
            print("     [WARNING] Translator not fully complete, building available chapters")

    def _process_chapters(
        self,
        manifest: dict,
        work_dir: Path,
        paths: EPUBPaths,
        target_language: str
    ) -> tuple:
        """Convert all translated markdown chapters to XHTML."""
        # Support both v3.0 and v3.5 manifest schemas
        chapters = manifest.get('chapters', [])
        if not chapters and 'structure' in manifest:
            # v3.5 schema: chapters are in structure.chapters
            chapters = manifest.get('structure', {}).get('chapters', [])
        metadata_jp = manifest.get('metadata', {})
        # Get language-specific metadata
        metadata_key = f'metadata_{target_language}'
        metadata_translated = manifest.get(metadata_key) or manifest.get('metadata_en', {})
        title_key = f'title_{target_language}'
        book_title = (metadata_translated.get(title_key) or 
                     metadata_translated.get('title_en') or 
                     manifest.get('title_en') or 
                     metadata_jp.get('title', ''))
        book_title = self._coerce_text(book_title, "Unknown")
        lang_config = get_language_config(target_language)
        lang_code = lang_config.get('language_code', target_language)

        # Sort chapters by toc_order to preserve canonical sequence
        # Fallback to original order if toc_order not present
        chapters = sorted(chapters, key=lambda ch: ch.get('toc_order', 999))

        # Language-specific translated directory (e.g., EN/, VN/)
        translated_dir = work_dir / target_language.upper()
        jp_dir = work_dir / "JP"  # Fallback if translated dir not available

        manifest_items = []
        chapter_info = []  # For navigation

        merge_enabled, merge_diag = self._should_merge_split_chapters_to_raw_structure(
            manifest, work_dir, chapters
        )
        if merge_enabled:
            chapter_batches = self._group_chapters_by_raw_group_index(chapters)
            print(
                "     [INFO] Raw-structure merge enabled: "
                f"{len(chapters)} translated chapters -> {len(chapter_batches)} EPUB chapters"
            )
        else:
            chapter_batches = [[chapter] for chapter in chapters]
            if any(ch.get('split_strategy') == 'text_page_boundary' for ch in chapters):
                reason = self._coerce_text(merge_diag.get("reason"), "raw structure not verified")
                print(
                    "     [INFO] Detected text-page split chapters but raw-structure merge is disabled "
                    f"({reason}); keeping per-chapter EPUB layout."
                )

        for i, batch in enumerate(chapter_batches):
            primary = batch[0]
            chapter_id = self._coerce_text(primary.get('id', f'chapter_{i+1:02d}'), f'chapter_{i+1:02d}')
            source_file = self._coerce_text(primary.get('source_file', ''), '')

            # Prioritize language-specific chapter title
            chapter_title_key = f'title_{target_language}'
            raw_title = (
                primary.get(chapter_title_key)
                or primary.get('title_english')
                or primary.get('title_en')
                or primary.get('title')
                or f'Chapter {i+1}'
            )
            title = self._coerce_text(raw_title, f'Chapter {i+1}')

            # Skip non-content entries (cover/kuchie placeholders)
            if not source_file:
                continue

            merged_markdown_chunks: List[str] = []
            merged_source_files: List[str] = []
            for chapter in batch:
                md_path = self._resolve_chapter_markdown_path(
                    chapter=chapter,
                    translated_dir=translated_dir,
                    jp_dir=jp_dir,
                    target_language=target_language,
                )
                if md_path is None:
                    continue
                merged_markdown_chunks.append(md_path.read_text(encoding='utf-8'))
                merged_source_files.append(self._coerce_text(chapter.get('source_file', ''), ''))

            if not merged_markdown_chunks:
                print(f"     [SKIP] No markdown content resolved for chapter batch {i+1}")
                continue

            md_content = '\n\n'.join(chunk for chunk in merged_markdown_chunks if chunk)

            # Convert to XHTML paragraphs
            paragraphs = self._markdown_to_paragraphs(md_content)
            xhtml_content = MarkdownToXHTML.convert_to_xhtml_string(paragraphs)

            # Build XHTML
            xhtml_filename = f"chapter{i+1:03d}.xhtml"
            xhtml_path = paths.text_dir / xhtml_filename

            # Pre-TOC content: suppress title header to match original formatting
            chapter_title_for_xhtml = title
            if primary.get('is_pre_toc_content', False):
                chapter_title_for_xhtml = ""  # No H1 header for unlisted content
                print(f"     [INFO] Pre-TOC content: suppressing title header")

            xhtml = XHTMLBuilder.build_chapter_xhtml(
                content=xhtml_content,
                chapter_title=chapter_title_for_xhtml,
                chapter_id=chapter_id,
                lang_code=lang_code,
                book_title=book_title
            )
            xhtml_path.write_text(xhtml, encoding='utf-8')

            # Add to manifest
            manifest_items.append(ManifestItem(
                id=chapter_id,
                href=f"Text/{xhtml_filename}",
                media_type="application/xhtml+xml"
            ))

            # Track for navigation (skip pre-TOC content like cover pages)
            if not primary.get('is_pre_toc_content', False):
                chapter_info.append({
                    'id': chapter_id,
                    'title': title,
                    'xhtml_filename': xhtml_filename,
                    'href': f"Text/{xhtml_filename}",
                })

            if len(batch) > 1:
                merged_count = len([f for f in merged_source_files if f])
                print(
                    f"     [OK] merged {merged_count} source chapters "
                    f"(raw_group={primary.get('raw_group_index')}) -> {xhtml_filename}"
                )
            else:
                print(f"     [OK] {source_file} -> {xhtml_filename}")

        return manifest_items, chapter_info

    def _resolve_chapter_markdown_path(
        self,
        chapter: dict,
        translated_dir: Path,
        jp_dir: Path,
        target_language: str
    ) -> Optional[Path]:
        """Resolve translated markdown path for one manifest chapter entry."""
        source_file = self._coerce_text(chapter.get('source_file', ''), '')
        if not source_file:
            return None

        # Look for translated file in language-specific dir first, then fallback.
        lang_file_key = f'{target_language}_file'
        translated_filename_raw = chapter.get(lang_file_key) or chapter.get('translated_file', source_file)
        translated_filename = self._coerce_text(translated_filename_raw, source_file)
        translated_file = translated_dir / translated_filename
        jp_file = jp_dir / source_file

        if translated_file.exists():
            return translated_file
        if jp_file.exists():
            print(f"     [WARNING] Using JP source for: {source_file}")
            return jp_file

        # Fallback: try mapped chapter ID naming.
        mapped_id = self._map_filename_to_chapter_id(source_file)
        if mapped_id != source_file:
            translated_file_mapped = translated_dir / f"{mapped_id}.md"
            if translated_file_mapped.exists():
                print(f"     [INFO] Mapped {source_file} -> {mapped_id}.md")
                return translated_file_mapped

        print(f"     [SKIP] File not found: {source_file}")
        return None

    def _group_chapters_by_raw_group_index(self, chapters: List[dict]) -> List[List[dict]]:
        """
        Group consecutive chapters that originated from the same raw spine group.

        Chapters without raw_group_index remain standalone.
        """
        grouped: List[List[dict]] = []
        current_group: List[dict] = []
        current_raw_group: Optional[int] = None

        for chapter in chapters:
            raw_group = chapter.get('raw_group_index')
            if raw_group is None:
                if current_group:
                    grouped.append(current_group)
                    current_group = []
                    current_raw_group = None
                grouped.append([chapter])
                continue

            if not current_group:
                current_group = [chapter]
                current_raw_group = raw_group
                continue

            if raw_group == current_raw_group:
                current_group.append(chapter)
                continue

            grouped.append(current_group)
            current_group = [chapter]
            current_raw_group = raw_group

        if current_group:
            grouped.append(current_group)

        return grouped

    def _should_merge_split_chapters_to_raw_structure(
        self,
        manifest: dict,
        work_dir: Path,
        chapters: List[dict]
    ) -> tuple:
        """
        Decide whether Builder should re-merge split chapters back to raw structure.

        We only merge when:
        - Librarian used spine fallback split strategy (text page boundary)
        - Raw TOC/spine inspection confirms malformed TOC + single-content structure
        """
        split_chapters = [
            ch for ch in chapters
            if ch.get('split_strategy') == 'text_page_boundary'
            and ch.get('raw_group_index') is not None
        ]
        if not split_chapters:
            return False, {"reason": "no_text_page_boundary_split"}

        raw_group_count = len({ch.get('raw_group_index') for ch in split_chapters})
        if raw_group_count <= 0 or len(chapters) <= raw_group_count:
            return False, {"reason": "nothing_to_merge"}

        inspection = self._inspect_raw_single_content_structure(work_dir)
        librarian_state = manifest.get('pipeline_state', {}).get('librarian', {})
        toc_entries = librarian_state.get('toc_entries')
        malformed_toc = inspection.get('malformed_toc', False)
        if not malformed_toc and isinstance(toc_entries, int):
            malformed_toc = toc_entries <= 3
        one_content_structure = inspection.get('one_content_structure', False)

        if malformed_toc and one_content_structure:
            return True, {
                "reason": "verified_malformed_toc_single_content",
                "raw_group_count": raw_group_count,
                "inspection": inspection,
            }

        return False, {
            "reason": "raw_structure_verification_failed",
            "inspection": inspection,
        }

    def _detect_title_in_body(self, body: Any, title_patterns: List[re.Pattern]) -> Optional[str]:
        """Detect chapter title markers from a parsed XHTML body."""
        for tag in ['h1', 'h2', 'h3']:
            heading = body.find(tag)
            if heading:
                text = heading.get_text(strip=True)
                if text and len(text) > 0 and len(text) < 100:
                    for pattern in title_patterns:
                        if pattern.search(text):
                            return text
                    if len(text) > 2:
                        return text

        paragraphs = body.find_all('p', limit=5)
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text:
                continue
            for pattern in title_patterns:
                match = pattern.search(text)
                if match:
                    matched_text = match.group(0)
                    if text.startswith(matched_text):
                        return text if len(text) < 50 else matched_text
                    return matched_text

        return None

    def _inspect_raw_single_content_structure(self, work_dir: Path) -> Dict[str, Any]:
        """
        Inspect extracted raw EPUB TOC/spine to detect malformed TOC + single-content layout.
        """
        inspection = {
            "toc_entries": 0,
            "spine_items": 0,
            "text_page_count": 0,
            "detected_title_count": 0,
            "malformed_toc": False,
            "one_content_structure": False,
        }

        # TOC diagnostics
        toc_path = work_dir / "toc.json"
        if toc_path.exists():
            try:
                toc_data = json.loads(toc_path.read_text(encoding='utf-8'))
                nav_points = toc_data.get("nav_points", [])
                if isinstance(nav_points, list):
                    inspection["toc_entries"] = len(nav_points)
            except Exception:
                pass
        inspection["malformed_toc"] = inspection["toc_entries"] <= 3

        # Locate OPF
        opf_path = work_dir / "_epub_extracted" / "item" / "standard.opf"
        if not opf_path.exists():
            candidates = sorted(work_dir.glob("_epub_extracted/**/standard.opf"))
            if candidates:
                opf_path = candidates[0]
        if not opf_path.exists():
            return inspection

        try:
            from bs4 import BeautifulSoup
        except Exception:
            return inspection

        try:
            ns = {'opf': 'http://www.idpf.org/2007/opf'}
            root = ET.parse(opf_path).getroot()
            manifest_items = {
                item.attrib['id']: item.attrib.get('href', '')
                for item in root.findall('.//opf:manifest/opf:item', ns)
                if item.attrib.get('id')
            }
            spine_idrefs = [
                item.attrib.get('idref', '')
                for item in root.findall('.//opf:spine/opf:itemref', ns)
            ]
            inspection["spine_items"] = len(spine_idrefs)

            title_patterns = [
                re.compile(p, re.IGNORECASE)
                for p in [
                    r'^第[一二三四五六七八九十百千]+章',
                    r'^第\d+章',
                    r'^第[一二三四五六七八九十百千]+話',
                    r'^第\d+話',
                    r'^Chapter\s*\d+',
                    r'^プロローグ',
                    r'^エピローグ',
                    r'^幕間',
                    r'^あとがき',
                    r'^Prologue',
                    r'^Epilogue',
                    r'^Interlude',
                ]
            ]
            skip_patterns = ('cover', 'toc', 'nav', 'titlepage', 'caution', 'colophon', '998', '999')

            for idref in spine_idrefs:
                href = manifest_items.get(idref, '')
                if not href:
                    continue
                filename = href.split('/')[-1]
                if any(skip in filename.lower() for skip in skip_patterns):
                    continue

                xhtml_path = opf_path.parent / href
                if not xhtml_path.exists():
                    continue

                content = xhtml_path.read_text(encoding='utf-8', errors='ignore')
                soup = BeautifulSoup(content, 'xml')
                body = soup.find('body')
                if not body:
                    continue

                text = body.get_text(strip=True)
                has_text = not (body.find('svg') and not text) and len(text) > 20
                if not has_text:
                    continue

                inspection["text_page_count"] += 1
                if self._detect_title_in_body(body, title_patterns):
                    inspection["detected_title_count"] += 1

            inspection["one_content_structure"] = (
                inspection["text_page_count"] >= 4
                and inspection["detected_title_count"] <= 1
            )
        except Exception:
            return inspection

        return inspection

    def _markdown_to_paragraphs(self, md_content: str) -> List[str]:
        """Convert markdown content to list of paragraphs."""
        from ..config import ILLUSTRATION_PLACEHOLDER_PATTERN
        
        lines = md_content.split('\n')
        paragraphs = []
        content_started = False  # Track if we've seen actual content yet

        for line in lines:
            line = line.strip()

            # Skip markdown headers (# Title)
            if line.startswith('#'):
                continue

            # Empty line = blank marker
            if not line:
                # Count consecutive blanks to avoid infinite/huge gaps, but allow up to 5
                blank_count = 0
                for p in reversed(paragraphs):
                    if p == "<blank>":
                        blank_count += 1
                    else:
                        break
                
                if blank_count < 5:
                    paragraphs.append("<blank>")
                continue

            # Check if this is a chapter-opening illustration (before any content)
            # These are decorative title cards with Japanese text that should be skipped
            is_illustration = bool(re.search(ILLUSTRATION_PLACEHOLDER_PATTERN, line))
            
            if is_illustration and not content_started:
                # Skip chapter-opening illustrations (stylized titles with Japanese text)
                print(f"     [SKIP] Chapter-opening illustration: {line}")
                continue
            
            # Mark that we've seen actual content (not just blanks)
            if not content_started and line != "<blank>":
                content_started = True

            paragraphs.append(line)

        # Remove trailing blanks
        while paragraphs and paragraphs[-1] == "<blank>":
            paragraphs.pop()

        return paragraphs

    def _map_filename_to_chapter_id(self, filename: str) -> str:
        """
        Map human-readable filename to manifest chapter ID.
        
        Supports flexible file naming by extracting chapter numbers and
        mapping special chapter types (prologue, epilogue, etc.).
        
        Args:
            filename: Human-readable filename (e.g., "Chapter 1_ Title.md")
            
        Returns:
            Manifest chapter ID (e.g., "CHAPTER_01")
        """
        # Extract chapter number from filename
        match = re.match(r'Chapter (\d+)', filename, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            return f"CHAPTER_{num:02d}"
        
        # Handle special chapters
        if filename.lower().startswith('interlude'):
            match = re.match(r'Interlude (\d+)', filename, re.IGNORECASE)
            if match:
                return f"INTERLUDE_{int(match.group(1)):02d}"
        
        if filename.lower().startswith('epilogue'):
            return "EPILOGUE"
        
        if filename.lower().startswith('afterword'):
            return "AFTERWORD"
        
        if filename.lower().startswith('prologue'):
            return "PROLOGUE"
        
        return filename

    def _detect_kuchie_images(self, assets: Dict, manifest: Dict = None, structure: Dict = None) -> List[str]:
        """
        Auto-detect kuchi-e images from manifest assets.

        First checks for explicit kuchie list in assets, then falls back
        to pattern matching on illustration filenames, and finally checks
        the chapters array for kuchie entries (schema v3.6+).
        
        For v3.7 schema, reads from structure.illustrations array.

        For RTL→LTR conversions, automatically reverses the kuchie order
        to maintain correct visual reading flow based on the original EPUB's
        page-progression-direction detected by the Librarian.

        Args:
            assets: Assets dictionary from manifest (v3.0-3.5)
            manifest: Full manifest dictionary (optional, for RTL detection and chapter lookup)
            structure: Structure dictionary from manifest (v3.7+)

        Returns:
            List of kuchi-e image filenames (reversed for RTL→LTR conversions)
        """
        kuchie_list = assets.get('kuchie', [])
        
        # v3.7 schema: check structure.illustrations for frontmatter kuchie (exclude cover)
        if not kuchie_list and structure:
            kuchie_list = [
                ill.get('file', '') 
                for ill in structure.get('illustrations', [])
                if ill.get('location') == 'frontmatter' 
                and ill.get('file')
                and ill.get('id', '').lower() != 'cover'  # Exclude cover image
            ]

        # Handle new format: list of dicts with metadata
        # Schema v3.5 has: {"file": "kuchie-001.jpg", "original": "...", "image_path": "..."}
        # Legacy manifests might have only "image_path" - use that as fallback
        if kuchie_list and isinstance(kuchie_list[0], dict):
            # Extract 'file' field from each metadata dict (preferred)
            # Fallback to 'image_path' basename for legacy manifests
            # Already in correct spine order (1→N)
            kuchie_list = [
                k.get('file') or Path(k.get('image_path', '')).name
                for k in kuchie_list
            ]
            # Filter out empty strings
            kuchie_list = [k for k in kuchie_list if k]

        if not kuchie_list:
            # Fallback: detect from illustrations with naming patterns
            kuchie_patterns = [r'kuchie.*\.jpg', r'frontis.*\.jpg', r'color.*\.jpg']
            kuchie_images = []
            for illust in assets.get('illustrations', []):
                for pattern in kuchie_patterns:
                    if re.match(pattern, illust, re.IGNORECASE):
                        kuchie_images.append(illust)
                        break
            kuchie_list = sorted(kuchie_images)

        # Second fallback: Check chapters array for kuchie entry (schema v3.6+)
        if not kuchie_list and manifest:
            for chapter in manifest.get('chapters', []):
                if chapter.get('id') == 'kuchie':
                    kuchie_list = chapter.get('illustrations', [])
                    break
        
        # DON'T auto-reverse kuchie order - the librarian extraction already
        # provides them in correct visual/narrative order via sequential numbering.
        # Kuchi-e (color plates) don't follow text reading direction; they're
        # presented in a visual sequence independent of RTL/LTR.
        #
        # Historical note: Previous auto-reversal logic caused incorrect order
        # because it double-reversed already-sorted kuchie-001.jpg through kuchie-NNN.jpg
        # filenames from the extraction phase.
        
        return kuchie_list

    def _process_images(
        self,
        manifest: dict,
        work_dir: Path,
        paths: EPUBPaths
    ) -> tuple:
        """
        Copy all images to Images/ directory and analyze kuchi-e dimensions.
        
        Returns:
            Tuple of (manifest_items, kuchie_metadata)
        """
        # Support both v3.0-3.5 (assets key) and v3.7 (structure.illustrations) schemas
        assets = manifest.get('assets', {})
        structure = manifest.get('structure', {})
        
        manifest_items = []

        assets_dir = work_dir / "assets"

        # Cover - Skip allcover images entirely
        cover = assets.get('cover')
        if cover and 'allcover' in cover.lower():
            print(f"     [SKIP] Filtering out allcover image: {cover}")
            # Try to find actual cover.jpg in assets directory
            actual_cover = assets_dir / "cover.jpg"
            if actual_cover.exists():
                cover = "cover.jpg"
                print(f"     [FOUND] Using actual cover.jpg instead")
            else:
                cover = None
                print(f"     [WARNING] No cover.jpg found, skipping cover")
        
        if cover:
            cover_path = assets_dir / cover
            print(f"     [COVER] Filename: {cover}")
            print(f"     [COVER] Source path: {cover_path}")
            print(f"     [COVER] Exists: {cover_path.exists()}")
            if cover_path.exists():
                dest = paths.images_dir / cover
                print(f"     [COVER] Destination: {dest}")
                shutil.copy2(cover_path, dest)
                manifest_items.append(ManifestItem(
                    id="cover-image",
                    href=f"Images/{cover}",
                    media_type=self._get_image_media_type(cover),
                    properties="cover-image"
                ))
                print(f"     [OK] Copied cover: {cover}")
            else:
                print(f"     [WARNING] Cover file not found: {cover_path}")
        else:
            print(f"     [WARNING] No cover specified in manifest")

        # Kuchie - copy and analyze dimensions
        # Use helper to handle both list and dict formats, passing structure for v3.7
        kuchie_list = self._detect_kuchie_images(assets, manifest, structure)
        for i, kuchie in enumerate(kuchie_list):
            # Try subdirectory first (old format), then root assets directory (new format)
            kuchie_path = assets_dir / "kuchie" / kuchie
            if not kuchie_path.exists():
                kuchie_path = assets_dir / kuchie
            
            if kuchie_path.exists():
                dest = paths.images_dir / kuchie
                shutil.copy2(kuchie_path, dest)
                manifest_items.append(ManifestItem(
                    id=f"kuchie-img-{i+1:03d}",  # Use 'kuchie-img' to avoid conflict with XHTML page IDs
                    href=f"Images/{kuchie}",
                    media_type=self._get_image_media_type(kuchie)
                ))

        # Analyze kuchi-e dimensions for orientation detection
        kuchie_metadata = analyze_kuchie_images(assets_dir, kuchie_list)

        # Illustrations - support both v3.0-3.5 (assets.illustrations) and v3.7 (structure.illustrations)
        illust_list = assets.get('illustrations', [])
        
        # v3.7 schema: illustrations are in structure.illustrations array
        if not illust_list and structure.get('illustrations'):
            illust_list = [ill.get('file', '') for ill in structure.get('illustrations', []) if ill.get('file')]

        # Handle new format: list of dicts with metadata (similar to kuchie handling)
        if illust_list and isinstance(illust_list[0], dict):
            # Extract 'file' field from each metadata dict
            illust_list = [
                ill.get('file') or Path(ill.get('image_path', '')).name
                for ill in illust_list
            ]
            # Filter out empty strings
            illust_list = [ill for ill in illust_list if ill]

        # Fallback: Collect illustrations from chapters array (schema v3.6+)
        if not illust_list:
            illust_set = set()  # Use set to avoid duplicates
            for chapter in manifest.get('chapters', []):
                chapter_illusts = chapter.get('illustrations', [])
                illust_set.update(chapter_illusts)
            illust_list = sorted(illust_set)  # Sort for consistent ordering

        # Track copied illustrations to avoid duplicates
        copied_illustrations = set()
        illust_counter = 0
        
        for illust in illust_list:
            # v3.7: images are in root assets directory
            # v3.0-3.5: images are in assets/illustrations subdirectory
            illust_path = assets_dir / illust
            if not illust_path.exists():
                illust_path = assets_dir / "illustrations" / illust
            
            if illust_path.exists():
                dest = paths.images_dir / illust
                shutil.copy2(illust_path, dest)
                illust_counter += 1
                manifest_items.append(ManifestItem(
                    id=f"illust-{illust_counter:03d}",
                    href=f"Images/{illust}",
                    media_type=self._get_image_media_type(illust)
                ))
                copied_illustrations.add(illust)
        
        # Also copy any original-named illustrations from assets/illustrations directory
        # This supports original EPUB filenames from various Japanese publishers
        illustrations_dir = assets_dir / "illustrations"
        if illustrations_dir.exists():
            # Patterns for common original EPUB illustration filenames (from publisher_profiles/)
            # Each pattern group covers specific publisher naming conventions:
            original_patterns = [
                # Page number formats (most common - KADOKAWA, Overlap, Brave Bunko, Kodansha)
                r'^p\d+\.(?:jpg|jpeg|png|gif|webp)$',           # p015.jpg, p267.jpg (lowercase)
                r'^P\d+[a-z]?\.(?:jpg|jpeg|png|gif|webp)$',     # P013.jpg, P020a.jpg (SB Creative uppercase with optional suffix)
                
                # Kindle/AZW conversion format
                r'^image_rsrc\w+\.(?:jpg|jpeg|png|gif|webp)$',  # image_rsrc147.jpg, image_rsrc3ND.jpg
                
                # Manga page format
                r'^m\d+\.(?:jpg|jpeg|png|gif|webp)$',           # m003.jpg, m047.jpg
                
                # Illustration prefix formats (KADOKAWA, Brave Bunko)
                r'^i[-_]\d+\.(?:jpg|jpeg|png|gif|webp)$',       # i-001.jpg, i_023.jpg
                
                # Shueisha embed format
                r'^embed\d+(?:_HD)?\.(?:jpg|jpeg|png|gif|webp)$',  # embed0006.jpg, embed0007_HD.jpg
                
                # Media Factory o_ prefix format
                r'^o_p\d+\.(?:jpg|jpeg|png|gif|webp)$',         # o_p025.jpg, o_p039.jpg
                
                # Special formats
                r'^photo\.(?:jpg|jpeg|png|gif|webp)$',          # photo.jpg (author photos, etc.)
                r'^t\d+\.(?:jpg|jpeg|png|gif|webp)$',           # t002.jpg, t003.jpg (title pages)
            ]
            import re as regex_module
            combined_pattern = '|'.join(f'({p})' for p in original_patterns)
            
            for img_path in sorted(illustrations_dir.iterdir()):
                if not img_path.is_file():
                    continue
                filename = img_path.name
                # Skip if already copied
                if filename in copied_illustrations:
                    continue
                # Skip standard renamed format (illust-###.jpg) - already handled above
                if filename.startswith('illust-'):
                    continue
                # Check if matches original filename patterns
                if regex_module.match(combined_pattern, filename, regex_module.IGNORECASE):
                    dest = paths.images_dir / filename
                    shutil.copy2(img_path, dest)
                    illust_counter += 1
                    manifest_items.append(ManifestItem(
                        id=f"illust-{illust_counter:03d}",
                        href=f"Images/{filename}",
                        media_type=self._get_image_media_type(filename)
                    ))
                    copied_illustrations.add(filename)
                    print(f"     [OK] Copied original illustration: {filename}")

        # Additional images (titlepage, manga headers, etc.)
        additional_list = assets.get('additional', [])
        for i, additional in enumerate(additional_list):
            additional_path = assets_dir / "additional" / additional
            if additional_path.exists():
                dest = paths.images_dir / additional
                shutil.copy2(additional_path, dest)
                manifest_items.append(ManifestItem(
                    id=f"additional-{i+1:03d}",
                    href=f"Images/{additional}",
                    media_type=self._get_image_media_type(additional)
                ))

        return manifest_items, kuchie_metadata

    def _get_image_media_type(self, filename: str) -> str:
        """Get MIME type for image file."""
        ext = Path(filename).suffix.lower()
        types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        return types.get(ext, 'image/jpeg')

    def _generate_frontmatter(
        self,
        manifest: dict,
        paths: EPUBPaths,
        chapter_info: List[dict],
        kuchie_metadata: Dict[str, dict],
        language_code: str,
        lang_config: dict,
        target_language: str
    ) -> List[ManifestItem]:
        """
        Generate cover, kuchi-e, and TOC pages.
        
        Args:
            manifest: Manifest dictionary
            paths: EPUB paths structure
            chapter_info: List of chapter information
            kuchie_metadata: Kuchi-e dimension metadata from _process_images
            language_code: Language code for XHTML (e.g., 'en', 'vi')
            
        Returns:
            List of manifest items for frontmatter
        """
        metadata_jp = manifest.get('metadata', {})
        # Get language-specific metadata
        metadata_key = f'metadata_{target_language}'
        metadata_translated = manifest.get(metadata_key) or manifest.get('metadata_en', {})
        assets = manifest.get('assets', {})
        
        # Get title in target language
        title_key = f'title_{target_language}'
        title = (metadata_translated.get(title_key) or 
                metadata_translated.get('title_en') or 
                manifest.get('title_en') or 
                metadata_jp.get('title', ''))
        title = self._coerce_text(title, "Unknown")
        
        # Get UI strings from language config
        ui_strings = lang_config.get('ui_strings', {})
        toc_title = self._coerce_text(ui_strings.get('toc_title', 'Table of Contents'), 'Table of Contents')

        manifest_items = []

        # 1. Cover page
        # Check if first kuchie is actually the cover (spine-based extraction creates kuchie-001 from cover.jpg)
        cover_image = assets.get('cover', 'cover.jpg')
        kuchie_assets = assets.get('kuchie', [])
        if kuchie_assets:
            # Handle both list and dict formats
            first_kuchie = kuchie_assets[0] if isinstance(kuchie_assets, list) else kuchie_assets[0] if isinstance(kuchie_assets[0], str) else kuchie_assets[0].get('file', '')
            first_kuchie_original = None
            if isinstance(kuchie_assets[0], dict):
                first_kuchie_original = kuchie_assets[0].get('original', '')
            
            # If first kuchie's original is cover.jpg, use kuchie-001.jpg as the actual cover
            if first_kuchie_original and 'cover' in first_kuchie_original.lower():
                cover_image = first_kuchie
                print(f"     [INFO] Using kuchie-001 as cover (spine-extracted from {first_kuchie_original})")
        
        cover_path = paths.text_dir / "cover.xhtml"
        StructureBuilder.create_cover_xhtml(cover_path, title, language_code, cover_image)
        manifest_items.append(ManifestItem(
            id="cover",
            href="Text/cover.xhtml",
            media_type="application/xhtml+xml"
        ))

        # 2. Kuchi-e pages (NEW!)
        kuchie_list = self._detect_kuchie_images(assets, manifest)
        
        # Multi-act: only place Act 1 kuchie in front matter
        volume_structure = manifest.get('volume_structure', {})
        is_multi_act = volume_structure.get('is_multi_act', False) and len(volume_structure.get('acts', [])) >= 2
        
        if is_multi_act:
            # Filter to Act 1 kuchie only (by checking assets.kuchie metadata)
            kuchie_assets = assets.get('kuchie', [])
            act1_kuchie_files = set()
            for k in kuchie_assets:
                if isinstance(k, dict) and k.get('act', 1) == 1:
                    act1_kuchie_files.add(k.get('file', ''))
                elif isinstance(k, str):
                    act1_kuchie_files.add(k)  # Legacy format: assume Act 1
            
            # If no act tags found, use kuchie from volume_structure.acts[0]
            if not act1_kuchie_files and volume_structure.get('acts'):
                act1_kuchie_files = set(volume_structure['acts'][0].get('kuchie_files', []))
            
            frontmatter_kuchie = [k for k in kuchie_list if k in act1_kuchie_files]
            print(f"     [MULTI-ACT] Placing {len(frontmatter_kuchie)} Act 1 kuchie in front matter")
        else:
            frontmatter_kuchie = kuchie_list
        
        for i, kuchie in enumerate(frontmatter_kuchie):
            # Use global kuchie_list index for consistent IDs across acts
            global_idx = kuchie_list.index(kuchie) if kuchie in kuchie_list else i
            kuchie_id = f"kuchie-{global_idx+1:03d}"
            kuchie_xhtml = f"kuchie{global_idx+1:03d}.xhtml"
            kuchie_path = paths.text_dir / kuchie_xhtml

            # Check if horizontal
            meta = kuchie_metadata.get(kuchie, {})
            if meta.get('is_horizontal', False):
                # Use SVG wrapper for horizontal
                StructureBuilder.create_horizontal_kuchie_xhtml(
                    kuchie_path,
                    kuchie,
                    meta['width'],
                    meta['height'],
                    kuchie_id,
                    title,
                    language_code
                )
            else:
                # Standard image page for vertical
                StructureBuilder.create_image_page_xhtml(
                    kuchie_path,
                    kuchie,
                    kuchie_id,
                    title,
                    language_code,
                    "kuchie-image"
                )

            manifest_items.append(ManifestItem(
                id=kuchie_id,
                href=f"Text/{kuchie_xhtml}",
                media_type="application/xhtml+xml"
            ))
            orientation = 'horizontal' if meta.get('is_horizontal') else 'vertical'
            print(f"     [OK] Generated {kuchie_xhtml} ({orientation})")

        # 3. Visual TOC page
        toc_entries = []
        
        # Multi-act: group chapters under act headings
        volume_structure = manifest.get('volume_structure', {})
        vis_acts = volume_structure.get('acts', [])
        is_vis_multi_act = volume_structure.get('is_multi_act', False) and len(vis_acts) >= 2
        
        if is_vis_multi_act:
            # Build chapter-to-act mapping
            chapters_manifest = manifest.get('chapters', [])
            chapters_sorted = sorted(chapters_manifest, key=lambda c: c.get('toc_order', 999))
            ch_id_to_act = {}
            for act in vis_acts:
                first_idx = act.get('first_chapter_index', 0)
                last_idx = act.get('last_chapter_index', len(chapters_sorted) - 1)
                for j in range(first_idx, min(last_idx + 1, len(chapters_sorted))):
                    ch_id_to_act[chapters_sorted[j].get('id', '')] = act
            
            current_act_num = 0
            for ch in chapter_info:
                act = ch_id_to_act.get(ch['id'])
                if act and act['act_number'] != current_act_num:
                    current_act_num = act['act_number']
                    act_label = self._coerce_text(
                        act.get('title_en') or act.get('title', f"Act {current_act_num}"),
                        f"Act {current_act_num}"
                    )
                    separator_href = f"act{current_act_num:03d}_separator.xhtml" if current_act_num >= 2 else ch['xhtml_filename']
                    toc_entries.append({
                        'href': separator_href,
                        'label': f"— {act_label} —"
                    })
                toc_entries.append({
                    'href': ch['xhtml_filename'],
                    'label': self._coerce_text(ch.get('title'), 'Chapter')
                })
        else:
            for ch in chapter_info:
                toc_entries.append({
                    'href': ch['xhtml_filename'],
                    'label': self._coerce_text(ch.get('title'), 'Chapter')
                })

        toc_path = paths.text_dir / "toc.xhtml"
        StructureBuilder.create_toc_xhtml(
            toc_path, toc_entries, toc_title, title, language_code
        )
        manifest_items.append(ManifestItem(
            id="toc-page",
            href="Text/toc.xhtml",
            media_type="application/xhtml+xml"
        ))

        return manifest_items

    def _generate_act_interstitials(
        self,
        manifest: dict,
        paths: EPUBPaths,
        chapter_info: List[dict],
        kuchie_metadata: Dict[str, dict],
        language_code: str,
        lang_config: dict,
        target_language: str
    ) -> List[ManifestItem]:
        """
        Generate act separator pages and per-act kuchie for multi-act EPUBs.
        
        For each act >= 2, generates:
        1. An act separator page (tobira equivalent) with act title
        2. Kuchie pages for that act's color plates
        
        Args:
            manifest: Manifest dictionary
            paths: EPUB paths structure
            chapter_info: List of chapter information
            kuchie_metadata: Kuchi-e dimension metadata
            language_code: Language code for XHTML
            lang_config: Language configuration dict
            target_language: Target language code
            
        Returns:
            List of manifest items for act interstitials
        """
        volume_structure = manifest.get('volume_structure', {})
        volume_acts = volume_structure.get('acts', [])
        assets = manifest.get('assets', {})
        metadata_jp = manifest.get('metadata', {})
        metadata_key = f'metadata_{target_language}'
        metadata_translated = manifest.get(metadata_key) or manifest.get('metadata_en', {})
        title_key = f'title_{target_language}'
        book_title = (metadata_translated.get(title_key) or
                     metadata_translated.get('title_en') or
                     manifest.get('title_en') or
                     metadata_jp.get('title', ''))
        book_title = self._coerce_text(book_title, "Unknown")
        
        # Get full kuchie list for global indexing
        kuchie_list = self._detect_kuchie_images(assets, manifest)
        
        manifest_items = []
        
        for act in volume_acts:
            if act['act_number'] < 2:
                continue  # Act 1 handled in frontmatter
            
            act_num = act['act_number']
            act_title = self._coerce_text(
                act.get('title_en') or act.get('title', f'Act {act_num}'),
                f'Act {act_num}'
            )
            
            # 1. Generate act separator page
            separator_id = f"act-{act_num:03d}-separator"
            separator_xhtml = f"act{act_num:03d}_separator.xhtml"
            separator_path = paths.text_dir / separator_xhtml
            
            StructureBuilder.create_act_separator_xhtml(
                separator_path,
                act_title,
                act_num,
                book_title,
                language_code
            )
            
            manifest_items.append(ManifestItem(
                id=separator_id,
                href=f"Text/{separator_xhtml}",
                media_type="application/xhtml+xml"
            ))
            print(f"     [OK] Generated act separator: {separator_xhtml}")
            
            # 2. Generate kuchie pages for this act
            act_kuchie_files = set(act.get('kuchie_files', []))
            
            # Also check assets.kuchie for act-tagged entries
            kuchie_assets = assets.get('kuchie', [])
            for k in kuchie_assets:
                if isinstance(k, dict) and k.get('act') == act_num:
                    act_kuchie_files.add(k.get('file', ''))
            
            act_kuchie = [k for k in kuchie_list if k in act_kuchie_files]
            
            for kuchie in act_kuchie:
                # Use global kuchie_list index for consistent IDs
                global_idx = kuchie_list.index(kuchie) if kuchie in kuchie_list else 0
                kuchie_id = f"kuchie-{global_idx+1:03d}"
                kuchie_xhtml = f"kuchie{global_idx+1:03d}.xhtml"
                kuchie_path = paths.text_dir / kuchie_xhtml
                
                meta = kuchie_metadata.get(kuchie, {})
                if meta.get('is_horizontal', False):
                    StructureBuilder.create_horizontal_kuchie_xhtml(
                        kuchie_path, kuchie,
                        meta['width'], meta['height'],
                        kuchie_id, book_title, language_code
                    )
                else:
                    StructureBuilder.create_image_page_xhtml(
                        kuchie_path, kuchie, kuchie_id,
                        book_title, language_code, "kuchie-image"
                    )
                
                manifest_items.append(ManifestItem(
                    id=kuchie_id,
                    href=f"Text/{kuchie_xhtml}",
                    media_type="application/xhtml+xml"
                ))
                orientation = 'horizontal' if meta.get('is_horizontal') else 'vertical'
                print(f"     [OK] Generated Act {act_num} kuchie: {kuchie_xhtml} ({orientation})")
        
        return manifest_items

    def _generate_navigation(
        self,
        manifest: dict,
        paths: EPUBPaths,
        chapter_info: List[dict],
        language_code: str,
        lang_config: dict,
        target_language: str
    ) -> List[ManifestItem]:
        """Generate nav.xhtml and toc.ncx."""
        metadata_jp = manifest.get('metadata', {})
        # Get language-specific metadata
        metadata_key = f'metadata_{target_language}'
        metadata_translated = manifest.get(metadata_key) or manifest.get('metadata_en', {})
        
        # Get title in target language
        title_key = f'title_{target_language}'
        title = (metadata_translated.get(title_key) or 
                metadata_translated.get('title_en') or 
                manifest.get('title_en') or 
                metadata_jp.get('title', ''))
        title = self._coerce_text(title, "Unknown")
        identifier = manifest.get('volume_id', '')
        
        # Get UI strings from language config
        ui_strings = lang_config.get('ui_strings', {})
        toc_title = self._coerce_text(ui_strings.get('toc_title', 'Table of Contents'), 'Table of Contents')
        cover_title = self._coerce_text(ui_strings.get('cover_title', 'Cover'), 'Cover')
        start_content = self._coerce_text(ui_strings.get('start_content', 'Start of Content'), 'Start of Content')

        manifest_items = []

        # Build TOC entries for nav.xhtml
        toc_entries = [TOCEntry(label=cover_title, href="cover.xhtml")]
        toc_entries.append(TOCEntry(label=toc_title, href="toc.xhtml"))

        # Check for multi-act structure → nested TOC
        volume_structure = manifest.get('volume_structure', {})
        volume_acts = volume_structure.get('acts', [])
        is_multi_act = volume_structure.get('is_multi_act', False) and len(volume_acts) >= 2

        if is_multi_act:
            # Build nested TOC: act headings with child chapter entries
            # Create a set of chapter IDs per act for lookup
            chapters_manifest = manifest.get('chapters', [])
            chapters_sorted = sorted(chapters_manifest, key=lambda c: c.get('toc_order', 999))
            
            for act in volume_acts:
                act_title = self._coerce_text(
                    act.get('title_en') or act.get('title', f"Act {act['act_number']}"),
                    f"Act {act['act_number']}"
                )
                first_idx = act.get('first_chapter_index', 0)
                last_idx = act.get('last_chapter_index', len(chapters_sorted) - 1)
                
                # Get chapter IDs for this act
                act_chapter_ids = set()
                for j in range(first_idx, min(last_idx + 1, len(chapters_sorted))):
                    act_chapter_ids.add(chapters_sorted[j].get('id', ''))
                
                # Build child entries from chapter_info that match this act
                child_entries = []
                for ch in chapter_info:
                    if ch['id'] in act_chapter_ids:
                        child_entries.append(TOCEntry(
                            label=self._coerce_text(ch.get('title'), 'Chapter'),
                            href=ch['xhtml_filename']
                        ))
                
                # First child's href is the act entry's href (or separator)
                if child_entries:
                    act_href = child_entries[0].href
                else:
                    act_href = f"act{act['act_number']:03d}_separator.xhtml"
                
                act_entry = TOCEntry(
                    label=act_title,
                    href=act_href,
                    children=child_entries
                )
                toc_entries.append(act_entry)
        else:
            # Flat TOC (original behavior)
            for ch in chapter_info:
                toc_entries.append(TOCEntry(
                    label=self._coerce_text(ch.get('title'), 'Chapter'),
                    href=ch['xhtml_filename']
                ))

        # Landmarks
        first_chapter = chapter_info[0]['xhtml_filename'] if chapter_info else "chapter001.xhtml"
        landmarks = [
            Landmark(epub_type="cover", href="cover.xhtml", title=cover_title),
            Landmark(epub_type="toc", href="nav.xhtml", title=toc_title),
            Landmark(epub_type="bodymatter", href=first_chapter, title=start_content),
        ]

        # Generate nav.xhtml
        nav_path = paths.text_dir / "nav.xhtml"
        nav_gen = NavGenerator(language_code)
        nav_gen.generate(nav_path, title, toc_entries, landmarks)
        manifest_items.append(ManifestItem(
            id="nav",
            href="Text/nav.xhtml",
            media_type="application/xhtml+xml",
            properties="nav"
        ))

        # Build NCX nav points
        nav_points = []
        play_order = 1

        nav_points.append(NavPoint(
            id="nav_cover",
            label=cover_title,
            src="Text/cover.xhtml",
            play_order=play_order
        ))
        play_order += 1

        nav_points.append(NavPoint(
            id="nav_toc",
            label=toc_title,
            src="Text/toc.xhtml",
            play_order=play_order
        ))
        play_order += 1

        for ch in chapter_info:
            nav_points.append(NavPoint(
                id=f"nav_{ch['id']}",
                label=self._coerce_text(ch.get('title'), 'Chapter'),
                src=f"Text/{ch['xhtml_filename']}",
                play_order=play_order
            ))
            play_order += 1

        # For multi-act, NCX also uses flat structure (NCX doesn't support nesting well
        # in most readers). The nav.xhtml handles the nested display.

        # Generate toc.ncx
        ncx_gen = NCXGenerator()
        ncx_gen.generate(paths.toc_ncx, title, identifier, nav_points)
        manifest_items.append(ManifestItem(
            id="ncx",
            href="toc.ncx",
            media_type="application/x-dtbncx+xml"
        ))

        return manifest_items

    def _create_stylesheet(self, paths: EPUBPaths) -> List[ManifestItem]:
        """Create CSS stylesheet."""
        css_path = paths.styles_dir / "stylesheet.css"
        css_path.write_text(DEFAULT_CSS, encoding='utf-8')

        return [ManifestItem(
            id="css",
            href="Styles/stylesheet.css",
            media_type="text/css"
        )]

    def _generate_opf(
        self,
        manifest: dict,
        paths: EPUBPaths,
        all_items: List[ManifestItem],
        chapter_info: List[dict],
        cover_image_id: Optional[str],
        language_code: str,
        target_language: str
    ) -> None:
        """Generate package.opf file."""
        metadata_jp = manifest.get('metadata', {})
        # Get language-specific metadata
        metadata_key = f'metadata_{target_language}'
        metadata_translated = manifest.get(metadata_key) or manifest.get('metadata_en', {})

        # Get title and author in target language
        title_key = f'title_{target_language}'
        author_key = f'author_{target_language}'
        publisher_key = f'publisher_{target_language}'
        series_key = f'series_{target_language}'
        
        # Support v3.5/v3.7 nested schema for author/publisher/title
        series_data = metadata_jp.get('series', {})
        if isinstance(series_data, dict) and ('author' in series_data or 'title' in series_data or 'title_english' in series_data):
            # v3.5/v3.7 schema with nested series dict
            
            # Extract author (handle both string and dict formats for v3.7)
            author_data = series_data.get('author', '')
            if isinstance(author_data, dict):
                # v3.7 format: author is a dict with name_english, name_japanese, etc.
                jp_author = author_data.get('name_english') or author_data.get('name_romaji') or author_data.get('name_japanese') or ''
            else:
                # v3.5 format: author is a string
                jp_author = author_data
            
            # Extract publisher (handle both string and dict formats for v3.7)
            publisher_data = series_data.get('publisher', '')
            if isinstance(publisher_data, dict):
                # v3.7 format: publisher is a dict with name_english, etc.
                jp_publisher = publisher_data.get('name_english') or publisher_data.get('name_japanese') or ''
            else:
                # v3.5 format: publisher is a string
                jp_publisher = publisher_data
            
            # Extract title - check v3.7 format first (title_english directly in series)
            if 'title_english' in series_data:
                # v3.7 format: title fields directly in series
                if target_language == 'en':
                    jp_title = series_data.get('title_english') or series_data.get('title_romaji') or 'Unknown'
                else:
                    jp_title = series_data.get(f'title_{target_language}') or series_data.get('title_english') or 'Unknown'
                jp_series = series_data.get('title_japanese', '')
            else:
                # v3.5 nested format or v3.6 string format
                series_title = series_data.get('title', {})
                if isinstance(series_title, dict) and series_title:  # Non-empty dict
                    if target_language == 'en':
                        jp_title = series_title.get('english') or series_title.get('romaji') or 'Unknown'
                    else:
                        jp_title = series_title.get(target_language) or series_title.get('english') or series_title.get('romaji') or 'Unknown'
                    jp_series = series_title.get('japanese', '')
                else:
                    # series_title is a string
                    jp_title = metadata_jp.get('title', '')
                    jp_series = series_data if isinstance(series_data, str) else ''
        else:
            # v3.0 schema or series is a string
            jp_author = metadata_jp.get('author', '')
            jp_publisher = metadata_jp.get('publisher', '')
            jp_title = metadata_jp.get('title', '')
            jp_series = series_data if isinstance(series_data, str) else metadata_jp.get('series', '')
        
        # Build BookMetadata using target language fields
        # Handle series_index from either v3.0 or v3.5 schema
        series_index = metadata_jp.get('series_index')
        if not series_index and isinstance(series_data, dict):
            series_index = series_data.get('volume_number')
        
        # Extract series string from metadata, handling both string and dict formats
        series_value = metadata_translated.get(series_key) or metadata_translated.get('series_en') or jp_series
        # If series is still a dict (from metadata or metadata_en), extract the appropriate language
        if isinstance(series_value, dict):
            if target_language == 'en':
                series_value = series_value.get('title_english') or series_value.get('english') or series_value.get('title_romaji') or series_value.get('romaji') or ''
            else:
                series_value = series_value.get(f'title_{target_language}') or series_value.get(target_language) or series_value.get('title_english') or series_value.get('english') or ''
        
        book_metadata = BookMetadata(
            title=self._coerce_text(
                metadata_translated.get(title_key) or 
                metadata_translated.get('title_en') or 
                manifest.get('title_en') or 
                jp_title,
                'Unknown'
            ),
            author=self._coerce_text(
                metadata_translated.get(author_key) or metadata_translated.get('author_en') or jp_author,
                ''
            ),
            language=language_code,
            publisher=self._coerce_text(
                metadata_translated.get(publisher_key) or metadata_translated.get('publisher_en') or jp_publisher,
                ''
            ),
            series=self._coerce_text(series_value, ''),
            series_index=series_index,
            identifier=self._coerce_text(manifest.get('volume_id', ''), '')
        )

        # Build spine - order matters!
        spine_items = []

        # Cover first
        spine_items.append(SpineItem(idref="cover", linear="no"))

        # Detect multi-act structure for spine ordering
        volume_structure = manifest.get('volume_structure', {})
        volume_acts = volume_structure.get('acts', [])
        is_multi_act = volume_structure.get('is_multi_act', False) and len(volume_acts) >= 2

        # Kuchi-e pages (frontmatter position)
        kuchie_list = self._detect_kuchie_images(
            manifest.get('assets', {}), 
            manifest, 
            manifest.get('structure', {})
        )

        if is_multi_act:
            # === ACT-AWARE SPINE ===
            # Cover → Act 1 kuchie → TOC → Act 1 chapters →
            # Act 2 separator → Act 2 kuchie → Act 2 chapters → ...
            
            # Build chapter-to-act mapping
            chapters_manifest = manifest.get('chapters', [])
            chapters_sorted = sorted(chapters_manifest, key=lambda c: c.get('toc_order', 999))
            
            # Map chapter IDs to their act number
            chapter_act_map = {}  # chapter_id -> act_number
            for act in volume_acts:
                first_idx = act.get('first_chapter_index', 0)
                last_idx = act.get('last_chapter_index', len(chapters_sorted) - 1)
                for j in range(first_idx, min(last_idx + 1, len(chapters_sorted))):
                    ch_id = chapters_sorted[j].get('id', '')
                    chapter_act_map[ch_id] = act['act_number']
            
            # Build per-act kuchie sets
            act_kuchie_map = {}  # act_number -> [kuchie_global_indices]
            kuchie_assets = manifest.get('assets', {}).get('kuchie', [])
            for global_idx, kuchie in enumerate(kuchie_list):
                # Determine act from kuchie metadata
                kuchie_act = 1  # default
                for k in kuchie_assets:
                    if isinstance(k, dict) and k.get('file') == kuchie:
                        kuchie_act = k.get('act', 1)
                        break
                # Also check volume_structure.acts[].kuchie_files
                for act in volume_acts:
                    if kuchie in act.get('kuchie_files', []):
                        kuchie_act = act['act_number']
                        break
                act_kuchie_map.setdefault(kuchie_act, []).append(global_idx)
            
            # Act 1 kuchie
            for idx in act_kuchie_map.get(1, []):
                spine_items.append(SpineItem(idref=f"kuchie-{idx+1:03d}"))
            
            # TOC page
            spine_items.append(SpineItem(idref="toc-page"))
            
            # Interleave chapters with act boundaries
            current_act = 1
            for ch in chapter_info:
                ch_act = chapter_act_map.get(ch['id'], current_act)
                
                # If we've crossed into a new act, insert separator + kuchie
                if ch_act > current_act:
                    for new_act_num in range(current_act + 1, ch_act + 1):
                        # Act separator
                        spine_items.append(SpineItem(idref=f"act-{new_act_num:03d}-separator"))
                        # Act kuchie
                        for idx in act_kuchie_map.get(new_act_num, []):
                            spine_items.append(SpineItem(idref=f"kuchie-{idx+1:03d}"))
                    current_act = ch_act
                
                spine_items.append(SpineItem(idref=ch['id']))
        else:
            # === SINGLE-VOLUME SPINE (original behavior) ===
            for i in range(len(kuchie_list)):
                spine_items.append(SpineItem(idref=f"kuchie-{i+1:03d}"))

            # TOC page
            spine_items.append(SpineItem(idref="toc-page"))

            # Chapters
            for ch in chapter_info:
                spine_items.append(SpineItem(idref=ch['id']))

        # Generate OPF
        opf_gen = OPFGenerator()
        opf_gen.generate(
            paths.package_opf,
            book_metadata,
            all_items,
            spine_items,
            cover_image_id
        )

    def _update_manifest(
        self,
        work_dir: Path,
        output_filename: str,
        chapter_count: int,
        image_count: int
    ) -> None:
        """Update manifest with build status."""
        manifest_path = work_dir / "manifest.json"

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        manifest['pipeline_state']['builder'] = {
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'output_file': output_filename,
            'chapters_built': chapter_count,
            'images_included': image_count
        }

        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)


def run_builder(
    volume_id: str,
    output_filename: Optional[str] = None,
    work_base: Optional[Path] = None,
    output_base: Optional[Path] = None,
    skip_qc_check: bool = False
) -> BuildResult:
    """
    Main entry point for Builder agent.

    Args:
        volume_id: Volume identifier
        output_filename: Optional custom output filename
        work_base: Optional custom working directory
        output_base: Optional custom output directory
        skip_qc_check: Skip critics completion check

    Returns:
        BuildResult with status and details
    """
    agent = BuilderAgent(work_base, output_base)
    return agent.build_epub(volume_id, output_filename, skip_qc_check)


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Builder Agent - Assemble EPUB from translated content"
    )
    parser.add_argument("volume_id", type=str, help="Volume ID (directory name in WORK/)")
    parser.add_argument("--output", "-o", type=str, help="Output filename")
    parser.add_argument("--work-dir", "-w", type=Path, help="Working directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory")
    parser.add_argument("--skip-qc", action="store_true", help="Skip QC check")

    args = parser.parse_args()

    result = run_builder(
        volume_id=args.volume_id,
        output_filename=args.output,
        work_base=args.work_dir,
        output_base=args.output_dir,
        skip_qc_check=args.skip_qc
    )

    if result.success:
        print(f"\nEPUB built successfully: {result.output_path}")
    else:
        print(f"\nBuild failed: {result.error}")
        exit(1)
