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
                book_title = metadata_translated.get(title_key) or metadata_translated.get('title_en') or metadata_jp.get('title', 'Unknown')
            print(f"     Title: {book_title}")
            print(f"     Target Language: {actual_language_name}")
            print(f"     Chapters: {len(chapters)}")

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
            all_items = nav_items + css_items + frontmatter_items + chapter_items + image_items

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
        book_title = metadata_translated.get(title_key) or metadata_translated.get('title_en') or metadata_jp.get('title', '')
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

        for i, chapter in enumerate(chapters):
            chapter_id = chapter.get('id', f'chapter_{i+1:02d}')
            source_file = chapter.get('source_file', '')
            # Prioritize language-specific chapter title
            chapter_title_key = f'title_{target_language}'
            # v3.7 uses title_english, older versions use title_en
            title = chapter.get(chapter_title_key) or chapter.get('title_english') or chapter.get('title_en') or chapter.get('title', f'Chapter {i+1}')

            # Skip chapters without source files (e.g., cover, kuchie)
            if not source_file:
                continue

            # Look for translated file in language-specific dir first, then fallback
            # Use the target_language parameter (from manifest), not self.target_language (from config)
            lang_file_key = f'{target_language}_file'
            translated_filename = chapter.get(lang_file_key) or chapter.get('translated_file', source_file)
            translated_file = translated_dir / translated_filename
            jp_file = jp_dir / source_file

            if translated_file.exists():
                md_path = translated_file
            elif jp_file.exists():
                md_path = jp_file
                print(f"     [WARNING] Using JP source for: {source_file}")
            else:
                # Fallback: try to map filename
                mapped_id = self._map_filename_to_chapter_id(source_file)
                if mapped_id != source_file:
                    # Try mapped filename
                    translated_file_mapped = translated_dir / f"{mapped_id}.md"
                    if translated_file_mapped.exists():
                        md_path = translated_file_mapped
                        print(f"     [INFO] Mapped {source_file} -> {mapped_id}.md")
                    else:
                        print(f"     [SKIP] File not found: {source_file}")
                        continue
                else:
                    print(f"     [SKIP] File not found: {source_file}")
                    continue

            # Read markdown
            md_content = md_path.read_text(encoding='utf-8')

            # Convert to XHTML paragraphs
            paragraphs = self._markdown_to_paragraphs(md_content)
            xhtml_content = MarkdownToXHTML.convert_to_xhtml_string(paragraphs)

            # Build XHTML
            xhtml_filename = f"chapter{i+1:03d}.xhtml"
            xhtml_path = paths.text_dir / xhtml_filename

            # Pre-TOC content: suppress title header to match original formatting
            chapter_title_for_xhtml = title
            if chapter.get('is_pre_toc_content', False):
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
            if not chapter.get('is_pre_toc_content', False):
                chapter_info.append({
                    'id': chapter_id,
                    'title': title,
                    'xhtml_filename': xhtml_filename,
                    'href': f"Text/{xhtml_filename}"
                })

            print(f"     [OK] {source_file} -> {xhtml_filename}")

        return manifest_items, chapter_info

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
        title = metadata_translated.get(title_key) or metadata_translated.get('title_en') or metadata_jp.get('title', '')
        
        # Get UI strings from language config
        ui_strings = lang_config.get('ui_strings', {})
        toc_title = ui_strings.get('toc_title', 'Table of Contents')

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
        for i, kuchie in enumerate(kuchie_list):
            kuchie_id = f"kuchie-{i+1:03d}"
            kuchie_xhtml = f"kuchie{i+1:03d}.xhtml"
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
        for ch in chapter_info:
            toc_entries.append({
                'href': ch['xhtml_filename'],
                'label': ch['title']
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
        title = metadata_translated.get(title_key) or metadata_translated.get('title_en') or metadata_jp.get('title', '')
        identifier = manifest.get('volume_id', '')
        
        # Get UI strings from language config
        ui_strings = lang_config.get('ui_strings', {})
        toc_title = ui_strings.get('toc_title', 'Table of Contents')
        cover_title = ui_strings.get('cover_title', 'Cover')
        start_content = ui_strings.get('start_content', 'Start of Content')

        manifest_items = []

        # Build TOC entries for nav.xhtml
        toc_entries = [TOCEntry(label=cover_title, href="cover.xhtml")]
        toc_entries.append(TOCEntry(label=toc_title, href="toc.xhtml"))

        for ch in chapter_info:
            toc_entries.append(TOCEntry(
                label=ch['title'],
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
                label=ch['title'],
                src=f"Text/{ch['xhtml_filename']}",
                play_order=play_order
            ))
            play_order += 1

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
            title=metadata_translated.get(title_key) or metadata_translated.get('title_en') or jp_title,
            author=metadata_translated.get(author_key) or metadata_translated.get('author_en') or jp_author,
            language=language_code,
            publisher=metadata_translated.get(publisher_key) or metadata_translated.get('publisher_en') or jp_publisher,
            series=series_value,
            series_index=series_index,
            identifier=manifest.get('volume_id', '')
        )

        # Build spine - order matters!
        spine_items = []

        # Cover first
        spine_items.append(SpineItem(idref="cover", linear="no"))

        # Kuchi-e pages (frontmatter position)
        kuchie_list = self._detect_kuchie_images(
            manifest.get('assets', {}), 
            manifest, 
            manifest.get('structure', {})
        )
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
