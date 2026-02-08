"""
Librarian Agent - EPUB Extraction and Cataloging Orchestrator.

Main entry point for Phase 1 of the MT Publishing Pipeline.
Extracts source EPUBs, parses metadata, converts chapters to markdown,
and generates manifest.json for downstream agents.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

from .epub_extractor import EPUBExtractor, ExtractionResult
from .metadata_parser import MetadataParser, BookMetadata
from .toc_parser import TOCParser, TableOfContents
from .spine_parser import SpineParser, Spine, SpineItem
from .xhtml_to_markdown import XHTMLToMarkdownConverter, ConvertedChapter
from .image_extractor import ImageExtractor, catalog_images
from .ruby_extractor import extract_ruby_from_directory
from .content_splitter import ContentSplitter, KodanshaSplitter
from .config import get_volume_structure, get_work_dir, get_pre_toc_detection_config
from .publisher_profiles.manager import get_profile_manager, PublisherProfile


@dataclass
class ChapterEntry:
    """Chapter entry for manifest."""
    id: str
    source_file: str
    translated_file: str
    title: str
    word_count: int
    toc_order: int = 0  # Position in canonical TOC order
    toc_level: int = 0  # Nesting level (0=main, 1=sub-chapter, etc.)
    illustrations: List[str] = field(default_factory=list)
    translation_status: str = "pending"
    qc_status: str = "pending"
    is_pre_toc_content: bool = False  # True if unlisted opening hook

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineState:
    """State tracking for pipeline stages."""
    status: str = "pending"
    timestamp: Optional[str] = None
    chapters_completed: int = 0
    chapters_total: int = 0
    current_chapter: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Manifest:
    """Complete manifest for pipeline communication."""
    version: str = "1.0"
    volume_id: str = ""
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    metadata_en: Dict[str, Any] = field(default_factory=dict)  # Semantic metadata for translator
    pipeline_state: Dict[str, Any] = field(default_factory=dict)
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    assets: Dict[str, Any] = field(default_factory=dict)
    toc: Dict[str, Any] = field(default_factory=dict)
    ruby_names: List[Dict[str, Any]] = field(default_factory=list)  # Ruby-extracted character names
    volume_structure: Dict[str, Any] = field(default_factory=dict)  # Multi-act/merged volume structure

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: Path):
        """Save manifest to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> 'Manifest':
        """Load manifest from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)


class LibrarianAgent:
    """
    Orchestrates EPUB extraction and content cataloging.

    Workflow:
    1. Extract EPUB to working directory
    2. Parse OPF metadata (title, author, etc.)
    3. Parse TOC for chapter ordering
    4. Convert XHTML chapters to markdown
    5. Catalog images by type
    6. Generate manifest.json
    """

    def __init__(self, work_base: Optional[Path] = None):
        """
        Initialize Librarian agent.

        Args:
            work_base: Base working directory (defaults to WORK/)
        """
        self.work_base = Path(work_base) if work_base else get_work_dir()
        self.work_base.mkdir(parents=True, exist_ok=True)
    
    def _create_metadata_en_template(
        self,
        chapters: List['ConvertedChapter'],
        ruby_names: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create metadata_en template with enhanced schema structure.
        
        This generates the V3-style semantic metadata schema with:
        - character_profiles (with keigo_switch placeholders)
        - localization_notes (with forbidden patterns)
        - chapters (with title_en placeholders)
        
        Args:
            chapters: List of converted chapters
            ruby_names: List of ruby-extracted character names
        
        Returns:
            metadata_en dict with proper schema structure
        """
        # Character profile template with keigo_switch
        def create_character_profile(name_data: Dict[str, Any]) -> Dict[str, Any]:
            """Create a character profile from ruby name data."""
            return {
                "full_name": name_data.get("reading", ""),
                "nickname": "",
                "age": "",
                "pronouns": "they/them",
                "origin": "Japanese" if not any(c.isalpha() and ord(c) > 127 for c in name_data.get("reading", "")) else "Unknown",
                "relationship_to_protagonist": "",
                "relationship_to_others": "",
                "personality_traits": "",
                "speech_pattern": "[TO BE FILLED - describe character's speaking style]",
                "keigo_switch": {
                    "narration": "casual",
                    "internal_thoughts": "casual",
                    "speaking_to": {},
                    "emotional_shifts": {},
                    "notes": "[TO BE FILLED - context-dependent register notes]"
                },
                "key_traits": "",
                "appearance": "",
                "character_arc": "",
                "ruby_base": name_data.get("base", ""),
                "ruby_reading": name_data.get("reading", ""),
                "occurrences": name_data.get("count", 0)
            }
        
        # Build character profiles from ruby names
        character_profiles = {}
        for name_data in ruby_names:
            # Use reading as key (e.g., "Charlotte Bennett")
            name_key = name_data.get("reading", name_data.get("base", "Unknown"))
            if name_key and name_key not in character_profiles:
                character_profiles[name_key] = create_character_profile(name_data)
        
        # Build chapter metadata
        chapters_meta = {}
        for i, ch in enumerate(chapters):
            chapter_id = f"chapter_{i+1:02d}"
            chapters_meta[chapter_id] = {
                "title_jp": ch.title or f"Chapter {i+1}",
                "title_en": ["[TO BE FILLED]"],
                "pov_tracking": [
                    {
                        "character": "[TO BE DETERMINED]",
                        "start_line": 1,
                        "end_line": None,
                        "context": "Full chapter - update if POV shifts occur"
                    }
                ],
                "setting": "",
                "themes": [],
                "key_events": [],
                "notes": ""
            }
        
        # Localization notes template
        localization_notes = {
            "british_speech_exception": {
                "character": "[IDENTIFY BRITISH CHARACTER IF ANY]",
                "allowed_patterns": [
                    "do not", "cannot", "will not", "I am", "it is",
                    "I have", "one must", "shall"
                ],
                "rationale": "British characters maintain formal register as authentic voice",
                "examples": []
            },
            "all_other_characters": {
                "priority": "SHORT, CONCISE, CONTEMPORARY GRAMMAR",
                "narrator_voice": "[PROTAGONIST NAME] - Contemporary teen voice",
                "forbidden_patterns": [
                    "cannot", "do not", "does not", "will not", "would not",
                    "I am", "it is", "there is"
                ],
                "preferred_alternatives": {
                    "cannot": "can't",
                    "do not": "don't",
                    "does not": "doesn't",
                    "will not": "won't",
                    "would not": "wouldn't",
                    "I am": "I'm",
                    "it is": "it's",
                    "there is": "there's",
                    "that is": "that's",
                    "I have": "I've",
                    "I will": "I'll",
                    "I would": "I'd",
                    "we are": "we're",
                    "they are": "they're",
                    "he is": "he's",
                    "she is": "she's"
                },
                "target_metrics": {
                    "contraction_rate": ">95%",
                    "ai_ism_density": "<0.3 per 1000 words",
                    "sentence_length": "Short and punchy for dialogue",
                    "vocabulary": "Contemporary American teen"
                }
            },
            "name_order": {
                "western_characters": {
                    "order": "First name first (Western order)",
                    "characters": [],
                    "examples": []
                },
                "japanese_characters": {
                    "order": "Family name first (Japanese order)",
                    "characters": [],
                    "examples": []
                }
            },
            "dialogue_guidelines": {
                "internal_monologue": "Use contractions, casual tone",
                "formal_speech": "Reserve for British/formal characters only",
                "casual_speech": "Natural American teen dialogue"
            },
            "volume_specific_notes": {}
        }
        
        return {
            "character_profiles": character_profiles,
            "localization_notes": localization_notes,
            "chapters": chapters_meta,
            "schema_version": "v3_enhanced",
            "schema_note": "Auto-generated by Librarian. Fill in [TO BE FILLED] placeholders before translation."
        }

    def process_epub(
        self,
        epub_path: Path,
        volume_id: Optional[str] = None,
        source_lang: str = "ja",
        target_lang: str = "en"
    ) -> Manifest:
        """
        Process source EPUB through full extraction pipeline.

        Args:
            epub_path: Path to source EPUB file
            volume_id: Optional custom volume ID
            source_lang: Source language code (default: ja)
            target_lang: Target language code (default: en)

        Returns:
            Manifest object with extraction results
        """
        epub_path = Path(epub_path)
        print(f"\n{'='*60}")
        print(f"LIBRARIAN AGENT - Processing: {epub_path.name}")
        print(f"{'='*60}\n")

        # Step 1: Extract EPUB
        print("[STEP 1/5] Extracting EPUB...")
        extractor = EPUBExtractor(self.work_base)
        extraction = extractor.extract(epub_path, volume_id)

        if not extraction.success:
            raise RuntimeError(f"EPUB extraction failed: {extraction.error}")

        volume_id = extraction.volume_id
        work_dir = extraction.work_dir
        structure = get_volume_structure()

        # Step 2: Parse metadata
        print("\n[STEP 2/5] Parsing metadata...")
        metadata_parser = MetadataParser()
        metadata = metadata_parser.parse_opf(extraction.opf_path)
        print(f"     Title: {metadata.title}")
        print(f"     Author: {metadata.author}")
        print(f"     Language: {metadata.language}")

        # Step 3: Parse TOC and Spine
        print("\n[STEP 3/5] Parsing table of contents and spine...")
        toc_parser = TOCParser(extraction.epub_root)
        toc = toc_parser.parse()
        print(f"     Found {len(toc.get_flat_list())} navigation entries")
        print(f"     Format: {toc.format.upper()}")

        # Parse spine for actual reading order
        spine_parser = SpineParser(extraction.opf_path)
        spine = spine_parser.parse()
        spine_parser.detect_illustration_pages(spine)
        print(f"     Spine: {len(spine.items)} items ({len([i for i in spine.items if i.is_illustration])} illustration pages)")

        # Detect multi-act/multi-volume structure (e.g., merged Shueisha publications)
        volume_acts = self._detect_volume_acts(spine, toc, extraction.content_dir)
        if volume_acts:
            print(f"     [MULTI-ACT] Detected {len(volume_acts)} acts in merged volume")
            for act in volume_acts:
                print(f"       Act {act['act_number']}: {act['title']} ({len(act['kuchie_spine_indices'])} kuchie pages)")

        # Get publisher profile for content handling configuration
        profile_manager = get_profile_manager()
        publisher_name = extraction.publisher_canonical
        publisher_profile = extraction.publisher_profile

        # Hybrid spine fallback detection (Solution 3)
        toc_entry_count = len(toc.get_flat_list())
        UNIVERSAL_TOC_THRESHOLD = 3
        
        # Check 1: Is TOC suspiciously minimal?
        is_minimal_toc = toc_entry_count <= UNIVERSAL_TOC_THRESHOLD
        
        # Check 2: Does TOC cover spine content files?
        toc_coverage, missing_files = self._validate_toc_completeness(toc, spine)
        is_incomplete_toc = toc_coverage < 0.5
        
        # Check 3: Publisher-specific config
        is_publisher_minimal = profile_manager.should_use_spine_fallback(publisher_name, toc_entry_count)
        
        # Use spine fallback if ANY condition met
        use_spine_fallback = is_minimal_toc or is_incomplete_toc or is_publisher_minimal
        
        # Track recovery reason for diagnostics
        recovery_reasons = []
        if is_minimal_toc:
            recovery_reasons.append("minimal_toc")
            print(f"     [WARNING] TOC has only {toc_entry_count} entries - likely corrupted")
        if is_incomplete_toc:
            recovery_reasons.append(f"incomplete_coverage_{int(toc_coverage*100)}%")
            print(f"     [WARNING] TOC only covers {toc_coverage:.0%} of spine content ({len(missing_files)} files missing)")
            if len(missing_files) <= 5:
                print(f"     [WARNING] Missing from TOC: {sorted(missing_files)}")
            else:
                print(f"     [WARNING] Missing from TOC: {sorted(list(missing_files)[:5])} ... and {len(missing_files)-5} more")
        if is_publisher_minimal:
            recovery_reasons.append("publisher_config")
            print(f"     [INFO] Publisher {publisher_name} uses minimal TOC pattern")
        
        if use_spine_fallback:
            print(f"     [INFO] Using spine-based chapter detection")

        # Step 4: Convert chapters to markdown (with content merging)
        print("\n[STEP 4/5] Converting chapters to markdown...")
        source_dir = work_dir / structure["source_chapters"]
        source_dir.mkdir(parents=True, exist_ok=True)

        # Preserve ruby readings for translator (format: 愛歌{まなか})
        # Pass content_dir for scene break icon detection
        converter = XHTMLToMarkdownConverter(remove_ruby=False, content_dir=extraction.content_dir)

        if use_spine_fallback:
            # Use spine-based chapter detection (for minimal-TOC publishers like Hifumi Shobo)
            chapters = self._convert_chapters_from_spine(
                extraction.content_dir,
                source_dir,
                spine,
                converter,
                publisher_name,
                volume_acts=volume_acts
            )
        else:
            # Use standard TOC-based chapter detection
            chapters = self._convert_chapters_with_spine(
                extraction.content_dir,
                source_dir,
                toc,
                spine,
                converter
            )
        print(f"     Converted {len(chapters)} chapters")
        
        # Post-process: Check for Kodansha heading-based splitting
        heading_split_config = profile_manager.get_heading_split_config(publisher_name)
        if heading_split_config and heading_split_config.get("split_on_heading", False):
            chapters = self._apply_heading_split(
                chapters,
                source_dir,
                heading_split_config.get("heading_patterns", [])
            )
            print(f"     [KODANSHA] Re-split into {len(chapters)} chapters using heading markers")
        
        # Collect all inline illustrations referenced in chapters
        chapter_illustrations = set()
        for ch in chapters:
            if hasattr(ch, 'illustrations') and ch.illustrations:
                for img in ch.illustrations:
                    chapter_illustrations.add(img)
        if chapter_illustrations:
            print(f"     Found {len(chapter_illustrations)} inline illustrations in chapters")

        # Step 4.5: Extract kuchie from spine (AUTHORITATIVE ORDER)
        print("\n[STEP 4.5/6] Extracting kuchie from spine...")
        spine_kuchie = self._extract_kuchie_from_spine(
            spine,
            extraction.content_dir,
            publisher_profile,
            volume_acts=volume_acts
        )
        print(f"     Found {len(spine_kuchie)} kuchie pages in spine order")
        if spine_kuchie:
            print(f"     Spine order: {' → '.join([k['original'] for k in spine_kuchie])}")

        # Step 5: Catalog images (cover + illustrations, kuchie already extracted)
        print("\n[STEP 5/6] Cataloging images...")
        image_extractor = ImageExtractor(extraction.content_dir, publisher=publisher_name)
        
        # Get kuchie filenames to exclude from pattern-based detection
        spine_kuchie_originals = {k['original'] for k in spine_kuchie}
        
        # Catalog remaining images (excluding spine-extracted kuchie)
        image_catalog = image_extractor.catalog_all()
        
        # Filter out spine-extracted kuchie from pattern-based results
        if spine_kuchie_originals:
            image_catalog["kuchie"] = [
                img for img in image_catalog["kuchie"]
                if img.filename not in spine_kuchie_originals
            ]

        # Copy images to assets
        assets_dir = work_dir / structure["assets"]
        
        # First, copy spine-based kuchie with proper sequential naming
        kuchie_output_paths = []
        kuchie_filename_mapping = {}
        for kuchie_meta in spine_kuchie:
            # Source: resolve image_path relative to content_dir
            src_image = extraction.content_dir / kuchie_meta['image_path']
            
            # Destination: assets/kuchie-NNN.ext
            dst_image = assets_dir / kuchie_meta['file']
            dst_image.parent.mkdir(parents=True, exist_ok=True)
            
            if src_image.exists():
                import shutil
                shutil.copy2(src_image, dst_image)
                kuchie_output_paths.append(dst_image)
                kuchie_filename_mapping[kuchie_meta['original']] = kuchie_meta['file']
        
        # Then copy remaining images (cover + illustrations)
        # Exclude spine-extracted kuchie from being copied again
        output_paths, filename_mapping = image_extractor.copy_to_assets(
            assets_dir, 
            exclude_files=spine_kuchie_originals
        )
        
        # Merge filename mappings
        filename_mapping.update(kuchie_filename_mapping)
        
        # Copy chapter-referenced inline illustrations (gaiji + illustrations from content)
        # These may not be detected by pattern-based image extractor (e.g., Gagaga Bunko uses numbered filenames)
        import shutil
        illust_dir = assets_dir / "illustrations"
        illust_dir.mkdir(parents=True, exist_ok=True)
        
        # Exclude kuchie images from inline illustrations
        chapter_illustrations_to_copy = chapter_illustrations - spine_kuchie_originals
        copied_illustrations = []
        
        for img_filename in chapter_illustrations_to_copy:
            # Try to find the image in content_dir
            for images_folder in ['images', 'image', 'Images', 'IMAGES']:
                src_path = extraction.content_dir / images_folder / img_filename
                if src_path.exists():
                    dst_path = illust_dir / img_filename
                    if not dst_path.exists():  # Avoid overwriting
                        shutil.copy2(src_path, dst_path)
                        copied_illustrations.append(img_filename)
                    break
        
        if copied_illustrations:
            print(f"     Copied {len(copied_illustrations)} inline illustrations to assets")
            # Add to image catalog for manifest
            image_catalog["illustrations"].extend([
                type('obj', (object,), {'filename': f})() for f in copied_illustrations
            ])

        # Update illustration references in markdown files
        if filename_mapping:
            print(f"\n[POST-PROCESS] Updating illustration references...")
            self._update_markdown_illustrations(source_dir, filename_mapping)
            print(f"     Updated {len(filename_mapping)} illustration references")

        # Count images
        cover_count = len(image_catalog["cover"])
        kuchie_count = len(spine_kuchie)  # Use spine-based count
        illust_count = len(image_catalog["illustrations"])
        print(f"     Cover: {cover_count}, Kuchie: {kuchie_count}, Illustrations: {illust_count}")
        
        # Step 6: Extract ruby annotations (character names only)
        print("\n[STEP 6/6] Extracting ruby annotations...")
        ruby_data = extract_ruby_from_directory(extraction.content_dir)
        names_count = len(ruby_data["names"])
        print(f"     Character Names: {names_count}")

        # Build manifest
        print("\n[FINALIZING] Building manifest...")
        manifest = self._build_manifest(
            volume_id=volume_id,
            epub_path=epub_path,
            metadata=metadata,
            toc=toc,
            spine=spine,
            chapters=chapters,
            image_catalog=image_catalog,
            spine_kuchie=spine_kuchie,  # Add spine-based kuchie metadata
            ruby_data=ruby_data,
            source_lang=source_lang,
            target_lang=target_lang,
            recovery_info={
                "used_spine_fallback": use_spine_fallback,
                "recovery_reasons": recovery_reasons,
                "toc_entries": toc_entry_count,
                "spine_content_files": len([i for i in spine.items if i.linear and not i.is_illustration]),
                "toc_coverage": toc_coverage,
                "missing_from_toc": sorted(list(missing_files)) if missing_files else []
            },
            volume_acts=volume_acts
        )

        # Sync manifest filenames with normalized names
        if filename_mapping:
            print("[POST-PROCESS] Syncing manifest filenames...")
            self._sync_manifest_filenames(manifest, filename_mapping)
            print(f"     Synced {len(filename_mapping)} filename mappings")

        # Save manifest
        manifest_path = work_dir / "manifest.json"
        manifest.save(manifest_path)
        print(f"     Saved: {manifest_path}")

        # Save TOC separately
        toc_path = work_dir / "toc.json"
        with open(toc_path, 'w', encoding='utf-8') as f:
            json.dump(toc.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"     Saved: {toc_path}")

        # Verify JP directory and chapter files exist
        jp_dir = work_dir / structure["source_chapters"]
        if not jp_dir.exists():
            raise RuntimeError(f"CRITICAL ERROR: JP directory not created at {jp_dir}")
        
        jp_files = list(jp_dir.glob("CHAPTER_*.md"))
        if len(jp_files) != len(chapters):
            raise RuntimeError(
                f"CRITICAL ERROR: Chapter count mismatch - Expected {len(chapters)} files in JP/, "
                f"found {len(jp_files)}. Files: {[f.name for f in jp_files]}"
            )
        print(f"\n[VERIFICATION] ✓ JP directory verified: {len(jp_files)} chapter files present")

        # Summary
        print(f"\n{'='*60}")
        print("LIBRARIAN COMPLETE")
        print(f"{'='*60}")
        print(f"Volume ID: {volume_id}")
        print(f"Work Dir:  {work_dir}")
        print(f"Chapters:  {len(chapters)}")
        
        # Show metadata_en summary
        char_count = len(manifest.metadata_en.get('character_profiles', {}))
        chapter_meta_count = len(manifest.metadata_en.get('chapters', {}))
        print(f"Metadata:  {char_count} character profiles, {chapter_meta_count} chapter templates")
        print(f"Schema:    V3 Enhanced (with keigo_switch)")
        
        print(f"Status:    Ready for TRANSLATOR")
        print(f"{'='*60}\n")

        return manifest

    def _convert_chapters(
        self,
        content_dir: Path,
        output_dir: Path,
        chapter_order: List[str],
        toc: TableOfContents,
        converter: XHTMLToMarkdownConverter
    ) -> List[ConvertedChapter]:
        """Convert XHTML chapters to markdown files."""
        chapters = []
        titles = {np.content_src: np.label for np in toc.get_flat_list()}

        # Track processed files to avoid duplicates
        processed = set()

        for ref in chapter_order:
            # Handle fragment references (file.xhtml#id)
            filename = ref.split('#')[0]
            if filename in processed:
                continue

            xhtml_path = content_dir / filename
            if not xhtml_path.exists():
                # Try in subdirectories
                for sub in ['text', 'Text', 'xhtml', 'XHTML']:
                    alt_path = content_dir / sub / filename
                    if alt_path.exists():
                        xhtml_path = alt_path
                        break

            if not xhtml_path.exists():
                print(f"     [SKIP] Not found: {filename}")
                continue

            # Skip navigation, cover, and toc files
            lower_name = filename.lower()
            if any(skip in lower_name for skip in ['nav', 'toc', 'cover', 'copyright']):
                print(f"     [SKIP] Navigation/cover: {filename}")
                continue

            try:
                # Get title from TOC
                title = titles.get(ref, titles.get(filename, ""))

                # Convert
                chapter = converter.convert_file(xhtml_path, title)

                # Save markdown
                md_filename = self._make_markdown_filename(filename, len(chapters) + 1)
                md_path = output_dir / md_filename

                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(chapter.content)

                # Update chapter info
                chapter.filename = md_filename
                chapters.append(chapter)
                processed.add(filename)

                print(f"     [OK] {filename} -> {md_filename}")

            except Exception as e:
                print(f"     [FAIL] {filename}: {e}")

        return chapters

    def _convert_chapters_with_spine(
        self,
        content_dir: Path,
        output_dir: Path,
        toc: TableOfContents,
        spine: Spine,
        converter: XHTMLToMarkdownConverter
    ) -> List[ConvertedChapter]:
        """
        Convert XHTML chapters to markdown, merging content between TOC entries.

        This handles EPUBs where:
        - Illustrations are standalone XHTML files between content files
        - Chapter content is split across multiple XHTML files
        - The spine order differs from the TOC navigation order

        Args:
            content_dir: Directory containing XHTML files
            output_dir: Directory to write markdown files
            toc: Parsed table of contents
            spine: Parsed spine with reading order
            converter: XHTML to Markdown converter

        Returns:
            List of ConvertedChapter objects
        """
        import re
        chapters = []

        # Build TOC entry map: normalized filename -> (title, TOC entry)
        toc_entries = {}
        for np in toc.get_flat_list():
            # Normalize: xhtml/p-007.xhtml#toc-001 -> p-007.xhtml
            filename = np.content_src.split('#')[0]
            if '/' in filename:
                filename = filename.split('/')[-1]
            toc_entries[filename] = np

        # Build spine item map: normalized filename -> SpineItem
        spine_map = {}
        spine_order = []  # Ordered list of normalized filenames
        for item in spine.items:
            filename = item.href.split('/')[-1] if '/' in item.href else item.href
            spine_map[filename] = item
            spine_order.append(filename)

        # Identify chapter boundaries from TOC
        # A chapter starts at a TOC entry and ends at the next TOC entry
        toc_filenames = list(toc_entries.keys())

        # Skip navigation, cover, colophon entries
        skip_patterns = ['cover', 'toc', 'nav', 'titlepage', 'caution', 'colophon', '998', '999']

        # Load pre-TOC detection config
        pre_toc_config = get_pre_toc_detection_config()
        
        # Detect pre-TOC content (opening hooks before prologue)
        pre_toc_content = []
        if pre_toc_config["enabled"]:
            pre_toc_content = self._detect_pre_toc_content(
                spine_order, toc_filenames, content_dir, skip_patterns, pre_toc_config
            )
        
        # Group spine items into chapters
        chapter_groups = []  # List of (title, [spine_files], is_pre_toc)
        
        # Add pre-TOC content as first chapter if found
        if pre_toc_content:
            chapter_title = pre_toc_config["chapter_title"]
            chapter_groups.append((chapter_title, pre_toc_content, True))  # Mark as pre-TOC
            print(f"     [INFO] Found pre-prologue content: {len(pre_toc_content)} files")
        
        current_chapter = None
        current_files = []

        for filename in spine_order:
            lower_name = filename.lower()

            # Skip navigation/special files
            if any(skip in lower_name for skip in skip_patterns):
                continue
            
            # Skip if already processed as pre-TOC content
            if filename in pre_toc_content:
                continue

            # Check if this file starts a new chapter (is in TOC)
            if filename in toc_entries:
                # Save previous chapter if exists
                if current_chapter is not None and current_files:
                    chapter_groups.append((current_chapter, current_files, False))  # Regular TOC chapter

                # Start new chapter
                current_chapter = toc_entries[filename].label
                current_files = [filename]
            elif current_chapter is not None:
                # Continue current chapter
                current_files.append(filename)

        # Don't forget the last chapter
        if current_chapter is not None and current_files:
            chapter_groups.append((current_chapter, current_files, False))  # Regular TOC chapter

        # Process each chapter group
        for chapter_title, file_list, *is_pre_toc_flag in chapter_groups:
            is_pre_toc_chapter = is_pre_toc_flag[0] if is_pre_toc_flag else False
            try:
                merged_content = []
                all_illustrations = []

                for filename in file_list:
                    spine_item = spine_map.get(filename)
                    xhtml_path = self._find_xhtml_file(content_dir, filename)

                    if xhtml_path is None:
                        print(f"     [SKIP] Not found: {filename}")
                        continue

                    # Check if this is an illustration-only page
                    if spine_item and spine_item.is_illustration:
                        # Extract illustration reference from the file
                        illust_ref = self._extract_illustration_from_file(xhtml_path)
                        if illust_ref:
                            merged_content.append(f"\n[ILLUSTRATION: {illust_ref}]\n")
                            all_illustrations.append(illust_ref)
                        continue

                    # Convert regular content file
                    # Don't include title for continuation files
                    is_first = (filename == file_list[0])
                    chapter = converter.convert_file(
                        xhtml_path,
                        chapter_title if is_first else ""
                    )

                    # For continuation files, strip the auto-detected title
                    content = chapter.content
                    if not is_first and content.startswith('# '):
                        # Remove the first heading line
                        lines = content.split('\n', 1)
                        if len(lines) > 1:
                            content = lines[1].lstrip('\n')

                    merged_content.append(content)
                    all_illustrations.extend(chapter.illustrations)

                # Combine all content
                full_content = '\n\n'.join(merged_content)

                # Clean up excessive newlines
                full_content = re.sub(r'\n{3,}', '\n\n', full_content)

                # Create merged chapter
                word_count = len(re.findall(r'\S+', full_content))
                paragraphs = [p for p in full_content.split('\n\n') if p.strip() and not p.startswith('#')]

                merged_chapter = ConvertedChapter(
                    filename="",  # Will be set below
                    title=chapter_title,
                    content=full_content,
                    illustrations=all_illustrations,
                    word_count=word_count,
                    paragraph_count=len(paragraphs),
                    is_pre_toc_content=is_pre_toc_chapter,
                )

                # Generate filename and save
                first_file = file_list[0]
                md_filename = self._make_markdown_filename(first_file, len(chapters) + 1)
                md_path = output_dir / md_filename

                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(full_content)

                merged_chapter.filename = md_filename
                chapters.append(merged_chapter)

                files_str = f"{len(file_list)} files" if len(file_list) > 1 else "1 file"
                print(f"     [OK] {chapter_title[:40]}... ({files_str}) -> {md_filename}")

            except Exception as e:
                print(f"     [FAIL] {chapter_title}: {e}")

        return chapters

    def _convert_chapters_from_spine(
        self,
        content_dir: Path,
        output_dir: Path,
        spine: Spine,
        converter: XHTMLToMarkdownConverter,
        publisher: str = None,
        volume_acts: Optional[List[Dict[str, Any]]] = None
    ) -> List[ConvertedChapter]:
        """
        Convert XHTML chapters to markdown using spine order when TOC is minimal/broken.

        This is used for publishers like Hifumi Shobo that have intentionally minimal
        TOCs (only cover + colophon). Instead of relying on TOC entries, this method:
        1. Scans each spine item for content
        2. Detects chapter boundaries by looking for chapter titles in the content
        3. Groups consecutive content files into chapters

        Args:
            content_dir: Directory containing XHTML files
            output_dir: Directory to write markdown files
            spine: Parsed spine with reading order
            converter: XHTML to Markdown converter
            publisher: Publisher name for profile-specific patterns

        Returns:
            List of ConvertedChapter objects
        """
        import re
        from bs4 import BeautifulSoup

        chapters = []
        profile_manager = get_profile_manager()
        title_patterns = profile_manager.get_chapter_title_patterns(publisher)
        content_config = profile_manager.get_content_config(publisher)

        # Build spine order list
        spine_order = []
        spine_map = {}
        for item in spine.items:
            filename = item.href.split('/')[-1] if '/' in item.href else item.href
            spine_map[filename] = item
            spine_order.append(filename)

        # Skip patterns for non-content files
        skip_patterns = ['cover', 'toc', 'nav', 'titlepage', 'caution', 'colophon', '998', '999']

        # In multi-act books, keep act>=2 frontmatter image pages inline with
        # the FIRST chapter of that act (not the previous chapter).
        act_boundary_files = set()
        if volume_acts:
            for act in volume_acts:
                act_num = act.get('act_number', 1)
                if act_num < 2:
                    continue
                boundary_indices = act.get('tobira_spine_indices', []) + act.get('kuchie_spine_indices', [])
                for idx in boundary_indices:
                    if 0 <= idx < len(spine.items):
                        boundary_file = spine.items[idx].href.split('/')[-1] if '/' in spine.items[idx].href else spine.items[idx].href
                        act_boundary_files.add(boundary_file)

        # Group files into chapters based on content scanning
        chapter_groups = []  # List of (title, [files])
        current_title = None
        current_files = []
        chapter_counter = 0
        pending_next_chapter_files = []  # Deferred act-boundary pages

        for filename in spine_order:
            lower_name = filename.lower()

            # Skip navigation/special files
            if any(skip in lower_name for skip in skip_patterns):
                continue

            # Multi-act boundary images (e.g., act tobira + fmatter) should be
            # attached to the next chapter, not to the previous one.
            if filename in act_boundary_files:
                pending_next_chapter_files.append(filename)
                continue

            xhtml_path = self._find_xhtml_file(content_dir, filename)
            if xhtml_path is None:
                continue

            spine_item = spine_map.get(filename)

            # Check if this is an illustration-only page
            if spine_item and spine_item.is_illustration:
                # Add to current chapter if we have one
                if current_title is not None:
                    current_files.append(filename)
                continue

            # Check if this file has a chapter title
            detected_title = self._detect_chapter_title_in_file(xhtml_path, title_patterns)

            # Also check if file has meaningful text content
            has_content = self._file_has_text_content(xhtml_path)

            if not has_content:
                # Skip files without text content (image pages, etc.)
                # But still track illustration references
                if current_title is not None:
                    current_files.append(filename)
                continue

            if detected_title:
                # Save previous chapter if exists
                if current_title is not None and current_files:
                    chapter_groups.append((current_title, current_files))

                # Start new chapter with detected title
                current_title = detected_title
                current_files = pending_next_chapter_files + [filename]
                pending_next_chapter_files = []
                chapter_counter += 1
            elif current_title is None:
                # First content file without explicit title - use fallback
                chapter_counter += 1
                fallback_title = content_config.fallback_chapter_title.format(n=chapter_counter)
                current_title = fallback_title
                current_files = pending_next_chapter_files + [filename]
                pending_next_chapter_files = []
            else:
                # Continue current chapter
                current_files.append(filename)

        # Don't forget the last chapter
        if current_title is not None and current_files:
            chapter_groups.append((current_title, current_files))

        # Convert each chapter group to markdown
        for idx, (chapter_title, file_list) in enumerate(chapter_groups):
            try:
                merged_content = []
                all_illustrations = []

                for filename in file_list:
                    spine_item = spine_map.get(filename)
                    xhtml_path = self._find_xhtml_file(content_dir, filename)

                    if xhtml_path is None:
                        continue

                    # Check if this is an illustration-only page
                    if spine_item and spine_item.is_illustration:
                        illust_ref = self._extract_illustration_from_file(xhtml_path)
                        if illust_ref:
                            merged_content.append(f"\n[ILLUSTRATION: {illust_ref}]\n")
                            all_illustrations.append(illust_ref)
                        continue

                    # Convert regular content file
                    is_first = (filename == file_list[0])
                    chapter = converter.convert_file(
                        xhtml_path,
                        chapter_title if is_first else ""
                    )

                    content = chapter.content
                    if not is_first and content.startswith('# '):
                        lines = content.split('\n', 1)
                        if len(lines) > 1:
                            content = lines[1].lstrip('\n')

                    merged_content.append(content)
                    all_illustrations.extend(chapter.illustrations)

                # Combine all content
                full_content = '\n\n'.join(merged_content)
                full_content = re.sub(r'\n{3,}', '\n\n', full_content)

                # Check if chapter splitting is needed (for publishers like Hifumi)
                profile_manager = get_profile_manager()
                split_config = profile_manager.get_chapter_split_config(publisher)
                
                if split_config and split_config.get("enabled", False):
                    # Check if this chapter exceeds token limit
                    splitter = ContentSplitter(
                        max_tokens=split_config.get("max_tokens_per_chapter", 2000),
                        min_tokens=split_config.get("min_part_tokens", 800),
                        scene_break_patterns=split_config.get("scene_break_patterns")
                    )
                    
                    estimated_tokens = splitter.estimate_tokens(full_content)
                    
                    if estimated_tokens > split_config.get("max_tokens_per_chapter", 2000):
                        # Split chapter into parts
                        parts = splitter.split_chapter(full_content)
                        print(f"     [SPLIT] Chapter exceeds {split_config['max_tokens_per_chapter']} tokens, splitting into {len(parts)} parts")
                        
                        for part in parts:
                            part_title = f"{chapter_title} - Part {part.part_number}"
                            part_filename = self._make_markdown_filename(
                                file_list[0], 
                                idx + 1,
                                part_suffix=f"_PART_{part.part_number:02d}"
                            )
                            part_path = output_dir / part_filename
                            
                            with open(part_path, 'w', encoding='utf-8') as f:
                                f.write(part.content)
                            
                            part_chapter = ConvertedChapter(
                                filename=part_filename,
                                title=part_title,
                                content=part.content,
                                illustrations=part.illustrations,
                                word_count=part.word_count,
                                paragraph_count=len([p for p in part.content.split('\n\n') if p.strip()]),
                                is_pre_toc_content=False,
                            )
                            chapters.append(part_chapter)
                            
                            print(f"     [OK] {part_title} ({part.estimated_tokens} tokens) -> {part_filename}")
                        
                        continue  # Skip single chapter creation

                # Create single chapter (default behavior)
                word_count = len(re.findall(r'\S+', full_content))
                paragraphs = [p for p in full_content.split('\n\n') if p.strip() and not p.startswith('#')]

                merged_chapter = ConvertedChapter(
                    filename="",
                    title=chapter_title,
                    content=full_content,
                    illustrations=all_illustrations,
                    word_count=word_count,
                    paragraph_count=len(paragraphs),
                    is_pre_toc_content=False,
                )

                # Generate filename and save
                md_filename = self._make_markdown_filename(file_list[0], idx + 1)
                md_path = output_dir / md_filename

                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(full_content)

                merged_chapter.filename = md_filename
                chapters.append(merged_chapter)

                files_str = f"{len(file_list)} files" if len(file_list) > 1 else "1 file"
                print(f"     [OK] {chapter_title[:40]}... ({files_str}) -> {md_filename}")

            except Exception as e:
                print(f"     [FAIL] {chapter_title}: {e}")

        return chapters

    def _detect_chapter_title_in_file(
        self,
        xhtml_path: Path,
        title_patterns: List
    ) -> Optional[str]:
        """
        Detect chapter title from XHTML file content.

        Looks for headings or text matching chapter title patterns.

        Args:
            xhtml_path: Path to XHTML file
            title_patterns: List of compiled regex patterns for chapter titles

        Returns:
            Detected chapter title or None
        """
        from bs4 import BeautifulSoup

        try:
            with open(xhtml_path, 'r', encoding='utf-8') as f:
                content = f.read()

            soup = BeautifulSoup(content, 'xml')
            body = soup.find('body')

            if not body:
                return None

            # Check headings first (h1, h2, h3)
            for tag in ['h1', 'h2', 'h3']:
                heading = body.find(tag)
                if heading:
                    text = heading.get_text(strip=True)
                    if text and len(text) > 0 and len(text) < 100:
                        # Check if it matches a chapter pattern
                        for pattern in title_patterns:
                            if pattern.search(text):
                                return text
                        # Also check if it looks like a title (not just a number)
                        if len(text) > 2:
                            return text

            # Check first few paragraphs for chapter markers
            paragraphs = body.find_all('p', limit=5)
            for p in paragraphs:
                text = p.get_text(strip=True)
                if not text:
                    continue

                for pattern in title_patterns:
                    match = pattern.search(text)
                    if match:
                        # Return just the matched portion if it's a clear title
                        matched_text = match.group(0)
                        # If the match is at the start, use the full paragraph as title
                        if text.startswith(matched_text):
                            return text if len(text) < 50 else matched_text
                        return matched_text

            return None

        except Exception:
            return None

    def _file_has_text_content(self, xhtml_path: Path) -> bool:
        """
        Check if XHTML file has meaningful text content (not just images).

        Args:
            xhtml_path: Path to XHTML file

        Returns:
            True if file has text content
        """
        from bs4 import BeautifulSoup

        try:
            with open(xhtml_path, 'r', encoding='utf-8') as f:
                content = f.read()

            soup = BeautifulSoup(content, 'xml')
            body = soup.find('body')

            if not body:
                return False

            # Check if body is just an SVG/image wrapper
            if body.find('svg') and not body.get_text(strip=True):
                return False

            # Get text content
            text = body.get_text(strip=True)

            # Need at least some text
            return len(text) > 20

        except Exception:
            return False

    def _apply_heading_split(
        self,
        chapters: List[ConvertedChapter],
        output_dir: Path,
        heading_patterns: List[str]
    ) -> List[ConvertedChapter]:
        """
        Apply Kodansha-style heading-based chapter splitting.
        
        When Kodansha EPUBs merge all content into one/few files with ### N markers,
        this method splits them into proper chapters.
        
        Args:
            chapters: List of converted chapters (may have merged content)
            output_dir: Directory containing markdown files
            heading_patterns: Regex patterns for heading detection
            
        Returns:
            New list of ConvertedChapter objects after splitting
        """
        import re
        
        # Create splitter with publisher-specific patterns
        splitter = KodanshaSplitter(heading_patterns=heading_patterns)
        
        # First pass: identify which chapters need splitting and calculate offsets
        split_info = []  # List of (chapter_index, num_split_chapters)
        total_offset = 0
        
        for idx, chapter in enumerate(chapters):
            chapter_path = output_dir / chapter.filename
            
            if not chapter_path.exists():
                continue
            
            content = chapter_path.read_text(encoding='utf-8')
            
            if splitter.should_split(content, min_chapters=2):
                num_chapters = splitter.detect_chapters(content)
                split_info.append((idx, num_chapters))
                # Offset is (new chapters - 1) because we're replacing 1 chapter with N
                total_offset += num_chapters - 1
        
        if not split_info:
            return chapters  # Nothing to split
        
        # Second pass: renumber subsequent chapters to make room
        # We need to rename files from the end to avoid conflicts
        for split_idx, num_new in reversed(split_info):
            # Chapters after split_idx need to be renumbered
            chapters_to_rename = []
            for i in range(len(chapters) - 1, split_idx, -1):
                old_path = output_dir / chapters[i].filename
                if old_path.exists():
                    # Calculate new chapter number
                    old_num = i + 1  # 1-indexed
                    # Add offset for all splits before this point
                    offset = sum(n - 1 for idx, n in split_info if idx < i)
                    new_num = old_num + offset + (num_new - 1)
                    
                    new_filename = f"CHAPTER_{new_num:02d}.md"
                    new_path = output_dir / new_filename
                    
                    chapters_to_rename.append((old_path, new_path, chapters[i], new_filename))
            
            # Rename from highest to lowest to avoid conflicts
            for old_path, new_path, chapter_obj, new_filename in chapters_to_rename:
                if old_path != new_path:
                    old_path.rename(new_path)
                    chapter_obj.filename = new_filename
        
        # Third pass: perform the actual splits
        new_chapters = []
        current_chapter_num = 1
        
        for idx, chapter in enumerate(chapters):
            chapter_path = output_dir / chapter.filename
            
            if not chapter_path.exists():
                new_chapters.append(chapter)
                current_chapter_num += 1
                continue
            
            content = chapter_path.read_text(encoding='utf-8')
            
            # Check if this chapter needs splitting
            if not splitter.should_split(content, min_chapters=2):
                # Update filename to current number (may have shifted)
                new_filename = f"CHAPTER_{current_chapter_num:02d}.md"
                if chapter.filename != new_filename:
                    old_path = output_dir / chapter.filename
                    new_path = output_dir / new_filename
                    if old_path.exists() and old_path != new_path:
                        old_path.rename(new_path)
                    chapter.filename = new_filename
                new_chapters.append(chapter)
                current_chapter_num += 1
                continue
            
            # Split the chapter
            print(f"     [KODANSHA SPLIT] {chapter.filename} has multiple chapter markers")
            split_chapters = splitter.split_chapters(content, base_chapter_num=current_chapter_num)
            
            if not split_chapters:
                new_chapters.append(chapter)
                current_chapter_num += 1
                continue
            
            # Backup original file BEFORE creating new files (to avoid overwrite)
            backup_path = chapter_path.with_suffix('.md.backup')
            chapter_path.rename(backup_path)
            print(f"     [BACKUP] {chapter.filename} -> {backup_path.name}")
            
            # Create new chapter files
            for split_ch in split_chapters:
                new_filename = f"CHAPTER_{current_chapter_num:02d}.md"
                new_path = output_dir / new_filename
                
                # Write content with proper header
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write(split_ch.content)
                
                # Create ConvertedChapter object
                new_chapter = ConvertedChapter(
                    filename=new_filename,
                    title=split_ch.title,
                    content=split_ch.content,
                    illustrations=split_ch.illustrations,
                    word_count=split_ch.word_count,
                    paragraph_count=len([p for p in split_ch.content.split('\n\n') if p.strip()]),
                    is_pre_toc_content=False
                )
                new_chapters.append(new_chapter)
                print(f"       -> {new_filename}: '{split_ch.title}' ({split_ch.word_count} words)")
                current_chapter_num += 1
        
        return new_chapters

    def _detect_pre_toc_content(
        self,
        spine_order: List[str],
        toc_filenames: List[str],
        content_dir: Path,
        skip_patterns: List[str],
        config: Dict[str, Any]
    ) -> List[str]:
        """
        Detect content files that appear before the first TOC entry.
        
        These are often opening hooks or narrative setup that don't appear
        in the table of contents but are crucial to the story.
        
        This is EXCEPTIONALLY RARE - see config.py for settings.
        
        Args:
            spine_order: Ordered list of spine filenames
            toc_filenames: List of filenames that are in TOC
            content_dir: Directory containing XHTML files
            skip_patterns: Patterns for files to skip
            config: Pre-TOC detection configuration
            
        Returns:
            List of filenames for pre-TOC content
        """
        from bs4 import BeautifulSoup
        
        if not toc_filenames:
            return []
        
        # Find first TOC entry in spine order
        first_toc_index = None
        for idx, filename in enumerate(spine_order):
            if filename in toc_filenames:
                first_toc_index = idx
                break
        
        if first_toc_index is None or first_toc_index == 0:
            return []
        
        # Get exclude patterns from config
        exclude_patterns = config["exclude_patterns"]
        
        # Check files before first TOC entry
        pre_toc_content = []
        for filename in spine_order[:first_toc_index]:
            lower_name = filename.lower()
            
            # Skip navigation/special files
            if any(skip in lower_name for skip in skip_patterns):
                continue
            
            # Skip patterns from config (fmatter, kuchie, etc.)
            if any(pattern in lower_name for pattern in exclude_patterns):
                continue
            
            # Check if file has actual text content
            xhtml_path = self._find_xhtml_file(content_dir, filename)
            if xhtml_path and self._has_story_content(xhtml_path, config):
                pre_toc_content.append(filename)
        
        return pre_toc_content
    
    def _has_story_content(self, xhtml_path: Path, config: Dict[str, Any]) -> bool:
        """
        Check if XHTML file contains story text (not just images/credits).
        
        Args:
            xhtml_path: Path to XHTML file
            config: Pre-TOC detection configuration
            
        Returns:
            True if file has meaningful story content
        """
        from bs4 import BeautifulSoup
        
        try:
            with open(xhtml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'xml')
            body = soup.find('body')
            
            if not body:
                return False
            
            # Check if it's just an SVG image wrapper
            if body.find('svg'):
                text = body.get_text(strip=True)
                if not text:
                    return False  # Image-only page
            
            # Get text content
            text = body.get_text(strip=True)

            # Check if this is a TOC page (目次 = Table of Contents in Japanese)
            # TOC pages have "目次" and multiple internal chapter links
            if '目次' in text or 'Contents' in text or 'Table of Contents' in text:
                # Count internal chapter links (href to other xhtml files)
                anchors = body.find_all('a')
                internal_links = [a for a in anchors if a.get('href', '').endswith('.xhtml') or '#' in a.get('href', '')]

                # If we have 3+ internal chapter links, it's almost certainly a TOC
                if len(internal_links) >= 3:
                    return False  # This is a TOC page, not story content

            # Get markers from config
            credit_markers = config["credit_markers"]
            min_sentences = config["min_sentences_after_credits"]
            min_length = config["min_text_length"]
            dialog_markers = config["story_markers"]["dialog"]
            pronouns = config["story_markers"]["pronouns"]

            # Filter out credit lines and short metadata
            if any(marker in text for marker in credit_markers):
                # Check if there's substantial text beyond credits
                sentences = [s for s in text.split('。') if len(s) > 10]
                return len(sentences) >= min_sentences
            
            # Check for dialog or narrative
            has_dialog = any(marker in text for marker in dialog_markers)
            has_narrative = any(pronoun in text for pronoun in pronouns)
            
            # If has dialog or narrative, it's story content
            if has_dialog or has_narrative:
                return True
            
            # Otherwise, check length
            return len(text) >= min_length
            
        except Exception as e:
            return False
    
    def _find_xhtml_file(self, content_dir: Path, filename: str) -> Optional[Path]:
        """Find XHTML file in content directory or subdirectories."""
        # Direct path
        direct = content_dir / filename
        if direct.exists():
            return direct

        # Try common subdirectories
        for sub in ['xhtml', 'XHTML', 'text', 'Text', 'OEBPS', 'OPS']:
            path = content_dir / sub / filename
            if path.exists():
                return path

        # Search recursively
        for path in content_dir.rglob(filename):
            return path

        return None

    def _extract_illustration_from_file(self, xhtml_path: Path) -> Optional[str]:
        """Extract illustration filename from an illustration-only XHTML file."""
        try:
            from bs4 import BeautifulSoup

            with open(xhtml_path, 'r', encoding='utf-8') as f:
                content = f.read()

            soup = BeautifulSoup(content, 'xml')

            # Check for SVG with image
            svg = soup.find('svg')
            if svg:
                image = svg.find('image')
                if image:
                    # BeautifulSoup stores xlink:href as literal 'xlink:href' key
                    href = (
                        image.get('href') or
                        image.get('xlink:href') or  # BeautifulSoup literal key
                        image.get('{http://www.w3.org/1999/xlink}href', '')
                    )
                    if href:
                        return Path(href).name

            # Check for img tag
            img = soup.find('img')
            if img:
                src = img.get('src', '')
                if src:
                    return Path(src).name

        except Exception:
            pass

        return None

    def _make_markdown_filename(self, xhtml_filename: str, index: int, part_suffix: str = "") -> str:
        """
        Generate clean markdown filename using sequential chapter index.
        
        IMPORTANT: Uses `index` parameter (sequential chapter count) instead of
        EPUB page numbers to avoid off-by-N errors when EPUBs have pre-content
        pages (credits, kuchie, etc.) that aren't chapters.
        
        Args:
            xhtml_filename: Original XHTML filename (e.g., p-003.xhtml)
            index: Sequential chapter number (1-based)
            part_suffix: Optional suffix for chapter parts (e.g., "_PART_01")
            
        Returns:
            Markdown filename (e.g., CHAPTER_01.md or CHAPTER_01_PART_01.md)
        """
        # Always use sequential index for consistent chapter numbering
        # This avoids issues where p-003.xhtml is the first chapter but
        # would incorrectly become CHAPTER_03.md instead of CHAPTER_01.md
        return f"CHAPTER_{index:02d}{part_suffix}.md"

    def _generate_chapter_id(self, title: str, index: int, filename: str = "") -> str:
        """
        Generate semantic chapter ID from title.
        
        Detects chapter type (interlude, epilogue, etc.) and generates
        appropriate ID for manifest consistency.
        
        Args:
            title: Chapter title from TOC
            index: Sequential index (fallback)
            filename: Source filename (optional)
            
        Returns:
            Semantic chapter ID (e.g., 'interlude_01', 'epilogue', 'chapter_05')
        """
        import re
        
        # Priority: Filename-based ID (to ensure stability)
        if filename:
            # Matches: CHAPTER_01.md, 01_chapter.md
            match = re.search(r'CHAPTER_(\d+)', filename, re.IGNORECASE)
            if match:
                return f"chapter_{int(match.group(1)):02d}"

        title_lower = title.lower()
        
        # Detect interludes
        if 'interlude' in title_lower or '間章' in title:
            match = re.search(r'(\d+)', title)
            num = int(match.group(1)) if match else 1
            return f"interlude_{num:02d}"
        
        # Detect epilogue (English, katakana, kanji 終章)
        if 'epilogue' in title_lower or 'エピローグ' in title or '終章' in title:
            return "epilogue"

        # Detect prologue (English, katakana, kanji 序章)
        if 'prologue' in title_lower or 'プロローグ' in title or '序章' in title:
            return "prologue"
        
        # Detect afterword
        if 'afterword' in title_lower or 'あとがき' in title or '後書き' in title:
            return "afterword"
        
        # Detect colophon
        if 'colophon' in title_lower or '奥付' in title:
            return "colophon"
        
        # Extract chapter number from title
        # Matches: "Chapter 5", "第5章", "5", etc.
        match = re.search(r'chapter\s*(\d+)', title_lower)
        if match:
            num = int(match.group(1))
            return f"chapter_{num:02d}"
        
        # Japanese chapter pattern: 第N章
        match = re.search(r'第(\d+)章', title)
        if match:
            num = int(match.group(1))
            return f"chapter_{num:02d}"
        
        # Numeric pattern at start
        match = re.match(r'^(\d+)', title)
        if match:
            num = int(match.group(1))
            return f"chapter_{num:02d}"
        
        # Fallback: sequential numbering
        return f"chapter_{index+1:02d}"

    def _update_markdown_illustrations(self, jp_dir: Path, filename_mapping: Dict[str, str]):
        """
        Update illustration references in markdown files with normalized filenames.
        
        Replaces [ILLUSTRATION: p011.jpg] with [ILLUSTRATION: illust-001.jpg]
        based on the mapping from original to normalized filenames.
        
        Also removes illustration placeholders for filtered files (e.g., m*.jpg stylized titles)
        that were excluded by the image pattern filter.
        
        Args:
            jp_dir: Directory containing Japanese markdown files
            filename_mapping: Dict mapping original filename -> normalized filename
        """
        import re
        from ..config import ILLUSTRATION_PLACEHOLDER_PATTERN
        
        updated_count = 0
        removed_count = 0
        
        for md_file in jp_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
                original_content = content
                
                # Find all illustration placeholders
                for match in re.finditer(ILLUSTRATION_PLACEHOLDER_PATTERN, content):
                    original_filename = match.group(1)
                    old_placeholder = match.group(0)
                    
                    # Check if we have a mapping for this filename
                    if original_filename in filename_mapping:
                        # File was processed - replace with normalized name
                        normalized_filename = filename_mapping[original_filename]
                        new_placeholder = f"[ILLUSTRATION: {normalized_filename}]"
                        content = content.replace(old_placeholder, new_placeholder)
                        updated_count += 1
                    else:
                        # File was filtered out (e.g., m*.jpg stylized titles) - remove placeholder
                        # Remove the placeholder and any surrounding blank lines
                        content = content.replace(f"\n{old_placeholder}\n", "\n")
                        content = content.replace(old_placeholder, "")
                        removed_count += 1
                
                # Write back if changed
                if content != original_content:
                    md_file.write_text(content, encoding='utf-8')
                    
            except Exception as e:
                print(f"     [WARN] Failed to update illustrations in {md_file.name}: {e}")

        if removed_count > 0:
            print(f"     Removed {removed_count} filtered illustration placeholders (stylized titles, etc.)")
        
        return updated_count

    def _sync_manifest_filenames(self, manifest: Manifest, filename_mapping: Dict[str, str]):
        """
        Sync manifest asset filenames with normalized names.

        Updates both the global assets section and per-chapter illustration lists
        to use normalized filenames instead of original EPUB filenames.

        Args:
            manifest: Manifest object to update (modified in-place)
            filename_mapping: Dict mapping original filename -> normalized filename
        """
        if not filename_mapping:
            return

        # Update cover filename if mapped
        if "cover" in manifest.assets and manifest.assets["cover"]:
            manifest.assets["cover"] = filename_mapping.get(
                manifest.assets["cover"], 
                manifest.assets["cover"]
            )

        # Update global assets
        # Kuchie now contains metadata dicts, so update the 'file' field
        if "kuchie" in manifest.assets and isinstance(manifest.assets["kuchie"], list):
            # Check if kuchie is list of dicts (new format) or strings (old format)
            if manifest.assets["kuchie"] and isinstance(manifest.assets["kuchie"][0], dict):
                # New format: list of dicts with metadata
                for kuchie_meta in manifest.assets["kuchie"]:
                    if "file" in kuchie_meta:
                        # Already normalized during extraction, no mapping needed
                        pass
            else:
                # Old format: list of strings (fallback for compatibility)
                manifest.assets["kuchie"] = [
                    filename_mapping.get(f, f) for f in manifest.assets["kuchie"]
                ]

        if "illustrations" in manifest.assets:
            manifest.assets["illustrations"] = [
                filename_mapping.get(f, f) for f in manifest.assets["illustrations"]
            ]

        # Update per-chapter illustration lists
        for chapter in manifest.chapters:
            if "illustrations" in chapter:
                chapter["illustrations"] = [
                    filename_mapping.get(f, f) for f in chapter["illustrations"]
                ]

    def _extract_kuchie_from_spine(
        self,
        spine: Spine,
        content_dir: Path,
        publisher_profile: Optional[PublisherProfile],
        volume_acts: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract kuchie (color plates) from spine order - THE AUTHORITATIVE SOURCE.
        
        This replaces pattern-based kuchie detection with spine-based extraction.
        The OPF spine defines the canonical reading order, which we preserve here.
        
        Supports multi-act EPUBs: when volume_acts is provided, extracts kuchie
        for ALL acts (front matter of each act), not just the initial front matter.
        
        Why spine-based?
        - OPF spine is the authoritative source of reading order
        - Pattern matching breaks on non-sequential filenames (P000a→P003)
        - Publisher-agnostic: works for any EPUB structure
        - Preserves traceability: original filename + spine position
        
        Args:
            spine: Parsed spine with reading order
            content_dir: Extracted EPUB content directory
            publisher_profile: Optional publisher profile for validation
            volume_acts: Optional list of act metadata from _detect_volume_acts.
                        If provided, extracts kuchie for all acts.
            
        Returns:
            List of kuchie dicts with metadata: 
            [{"file": "kuchie-001.jpg", "original": "P000a.jpg", "spine_index": 2, "act": 1}, ...]
        """
        # Multi-act dispatch: extract kuchie for each act's front matter region
        if volume_acts:
            return self._extract_kuchie_multi_act(spine, content_dir, volume_acts)
        
        from lxml import etree
        
        kuchie_list = []
        chapter_started = False
        
        print(f"     Scanning {len(spine.items)} spine items for kuchie pages (front matter only)...")
        
        # Iterate through spine in reading order
        for idx, spine_item in enumerate(spine.items):
            # Stop kuchie extraction once we hit chapter content
            # Kuchi-e are ONLY in the front matter (before chapters start)
            if chapter_started:
                break
            
            # Skip non-linear items
            if not spine_item.linear:
                continue
                
            # Only process XHTML files
            if not spine_item.href.endswith(('.xhtml', '.html', '.htm')):
                continue
                
            xhtml_path = content_dir / spine_item.href
            if not xhtml_path.exists():
                continue
            
            # Quick size check: kuchie pages are typically small (< 5KB XHTML wrapper)
            # Chapter content files are much larger (10KB+)
            file_size = xhtml_path.stat().st_size
            if file_size > 10000:  # 10KB threshold
                # This is likely chapter content - stop extracting kuchie
                chapter_started = True
                break
            
            # Check if this is an image-only page (kuchie candidate)
            try:
                tree = etree.parse(str(xhtml_path))
                root = tree.getroot()
                
                # Find body element
                body = root.find(".//{http://www.w3.org/1999/xhtml}body")
                if body is None:
                    body = root.find(".//body")
                
                if body is None:
                    continue
                
                # Extract text content (excluding <img> alt text)
                # Optimized: only get first 200 chars worth of text to check
                text_parts = []
                char_count = 0
                for element in body.iter():
                    if char_count > 200:  # Stop early if we already have enough text
                        break
                    if element.tag.endswith(('img', 'image')):
                        continue
                    if element.text:
                        text_parts.append(element.text.strip())
                        char_count += len(element.text.strip())
                    if element.tail:
                        text_parts.append(element.tail.strip())
                        char_count += len(element.tail.strip())
                
                text_content = ' '.join(text_parts).strip()
                
                # Check if this is substantial chapter content (not kuchie)
                # If we encounter a page with >200 chars of text, chapters have started
                if len(text_content) > 200:
                    chapter_started = True
                    break
                
                # Find image references
                img_elements = body.findall(".//{http://www.w3.org/1999/xhtml}img")
                if not img_elements:
                    img_elements = body.findall(".//img")
                
                # Also check for SVG images
                svg_images = body.findall(".//{http://www.w3.org/2000/svg}image")
                if svg_images:
                    img_elements.extend(svg_images)
                
                # Kuchie detection: image-only page (minimal/no text)
                # Allow up to 50 chars for titles/labels/whitespace
                if img_elements and len(text_content) < 50:
                    # Extract image filename
                    img_src = None
                    for img in img_elements:
                        src = img.get('src') or img.get('{http://www.w3.org/1999/xlink}href')
                        if src:
                            # Resolve relative path from XHTML location
                            xhtml_dir = Path(spine_item.href).parent
                            img_path = (xhtml_dir / src).as_posix()
                            
                            # Normalize path (remove ../)
                            img_path_parts = []
                            for part in img_path.split('/'):
                                if part == '..':
                                    if img_path_parts:
                                        img_path_parts.pop()
                                elif part and part != '.':
                                    img_path_parts.append(part)
                            img_src = '/'.join(img_path_parts)
                            break
                    
                    if img_src:
                        # Extract original image filename (without path)
                        original_filename = Path(img_src).name
                        
                        # Skip known non-kuchie patterns
                        # - white.jpg: blank separator pages
                        # - logo.png/publisher logo: title page logos
                        # - Small images (< 20KB): likely icons/logos, not color plates
                        skip_patterns = ['white', 'logo', 'blank', 'separator']
                        if any(pattern in original_filename.lower() for pattern in skip_patterns):
                            continue
                        
                        # Check actual image file size
                        # Note: Some publishers (e.g., Gagaga Bunko) use small decorative images
                        # as chapter headers/ornaments that should be included as kuchie
                        img_file_path = content_dir / img_src
                        if img_file_path.exists():
                            img_size = img_file_path.stat().st_size
                            # Lowered threshold to 5KB to capture decorative chapter images
                            # Very small images (< 5KB) are usually gaiji or icons
                            if img_size < 5000:  # < 5KB, likely gaiji/icon
                                continue
                        
                        # Generate sequential kuchie filename
                        kuchie_number = len(kuchie_list) + 1
                        extension = Path(original_filename).suffix
                        normalized_filename = f"kuchie-{kuchie_number:03d}{extension}"
                        
                        # KUCHIE SCHEMA (v3.5) - CANONICAL FIELDS
                        # ========================================
                        # "file": normalized destination filename (Builder uses this)
                        # "original": source filename from EPUB
                        # "image_path": full relative path to source image
                        # "spine_index": position in OPF spine
                        # "spine_href": XHTML file reference in spine
                        # 
                        # NOTE: Builder expects "file" field. Legacy manifests may have
                        # only "image_path" - Builder has fallback for this.
                        kuchie_list.append({
                            "file": normalized_filename,
                            "original": original_filename,
                            "spine_index": idx,
                            "spine_href": spine_item.href,
                            "image_path": img_src,
                        })
                        
            except Exception as e:
                # Silently continue on parse errors
                continue
        
        return kuchie_list

    def _validate_toc_completeness(self, toc: TableOfContents, spine: Spine) -> tuple[float, set]:
        """
        Validate if TOC covers all content files in spine.
        
        Args:
            toc: Parsed table of contents
            spine: Parsed spine with reading order
            
        Returns:
            Tuple of (coverage_ratio, missing_files_set)
            - coverage_ratio: 0.0 to 1.0 indicating percentage of spine files in TOC
            - missing_files: Set of filenames in spine but not in TOC
        """
        # Get normalized filenames from TOC
        toc_files = set()
        for np in toc.get_flat_list():
            # Normalize: xhtml/p-007.xhtml#toc-001 -> p-007.xhtml
            filename = np.content_src.split('#')[0]
            if '/' in filename:
                filename = filename.split('/')[-1]
            toc_files.add(filename)
        
        # Get content files from spine (exclude special files)
        skip_patterns = ['cover', 'nav', 'toc', 'colophon', 'copyright', 'titlepage']
        spine_content = set()
        for item in spine.items:
            if not item.linear or item.is_illustration:
                continue
            filename = item.href.split('/')[-1] if '/' in item.href else item.href
            lower_name = filename.lower()
            if any(skip in lower_name for skip in skip_patterns):
                continue
            spine_content.add(filename)
        
        # Calculate coverage
        if not spine_content:
            return 1.0, set()  # No content files to check
        
        covered_files = toc_files & spine_content
        missing_files = spine_content - toc_files
        coverage = len(covered_files) / len(spine_content)
        
        return coverage, missing_files

    def _detect_volume_acts(
        self,
        spine: Spine,
        toc: TableOfContents,
        content_dir: Path
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Detect multi-act/multi-volume structure from spine analysis.
        
        Identifies act boundaries by detecting tobira (title page) patterns
        that appear mid-spine after chapter content has begun. This is
        characteristic of merged multi-volume Japanese light novel EPUBs
        (e.g., Shueisha Dash X Bunko "Act 1 + Act 2" releases).
        
        Detection signals:
        - Spine idrefs containing 'tobira' keyword (most reliable)
        - Multiple tobira groups separated by content pages
        - TOC entries matching act naming patterns (幕, Act, Part)
        
        Reference: 25d9 (魔弾の王と戦姫) spine structure:
        - p-tobira-001/001-2 → Act 1 header
        - p-fmatter-001..006 → Act 1 kuchie (6 plates)
        - p-001..p-028 → Act 1 content
        - p-tobira-002 → Act 2 header (mid-spine boundary!)
        - p-fmatter-007..008 → Act 2 kuchie (2 plates)
        - p-029..p-054 → Act 2 content
        
        Args:
            spine: Parsed spine with reading order
            toc: Parsed table of contents
            content_dir: Extracted EPUB content directory
            
        Returns:
            List of act dicts, or None if single-volume.
            Each dict contains:
            {
                "act_number": int,
                "title": str,
                "tobira_spine_indices": [int],
                "kuchie_spine_indices": [int],
                "first_content_spine_index": int,
                "toc_index": int,  # Index into TOC flat list
            }
        """
        # Phase 1: Find tobira pages in spine by idref pattern
        tobira_entries = []
        for idx, item in enumerate(spine.items):
            if 'tobira' in item.idref.lower():
                tobira_entries.append((idx, item))
        
        if len(tobira_entries) < 2:
            return None  # Need at least 2 tobira references for multi-act
        
        # Phase 2: Group consecutive tobira pages into act boundaries
        # Consecutive tobira pages (e.g., tobira-001, tobira-001-2) = same act header
        # Tobira separated by content pages = different act boundary
        tobira_groups = []
        current_group = [tobira_entries[0]]
        skip_idrefs = {'cover', 'caution', 'titlepage', 'colophon'}
        
        for i in range(1, len(tobira_entries)):
            prev_idx = tobira_entries[i - 1][0]
            curr_idx = tobira_entries[i][0]
            
            # Check if content pages exist between consecutive tobira entries
            has_content_between = False
            for j in range(prev_idx + 1, curr_idx):
                item = spine.items[j]
                idref_lower = item.idref.lower()
                if (item.linear
                        and 'fmatter' not in idref_lower
                        and 'tobira' not in idref_lower
                        and not any(s in idref_lower for s in skip_idrefs)):
                    has_content_between = True
                    break
            
            if has_content_between:
                tobira_groups.append(current_group)
                current_group = [tobira_entries[i]]
            else:
                current_group.append(tobira_entries[i])
        
        tobira_groups.append(current_group)
        
        if len(tobira_groups) < 2:
            return None  # All tobira pages in same group = single volume
        
        # Phase 3: Build act metadata
        # Cross-reference TOC entries with tobira spine items for act titles
        toc_flat = toc.get_flat_list()
        toc_map = {}  # filename -> (label, toc_index)
        for np_idx, np in enumerate(toc_flat):
            filename = np.content_src.split('#')[0]
            if '/' in filename:
                filename = filename.split('/')[-1]
            toc_map[filename] = (np.label, np_idx)
        
        acts = []
        for act_num, group in enumerate(tobira_groups, 1):
            last_tobira_idx = group[-1][0]
            tobira_indices = [idx for idx, _ in group]
            
            # Find act title and TOC index from TOC by matching tobira href
            act_title = ""
            act_toc_index = -1
            for _, tobira_item in group:
                filename = tobira_item.href.split('/')[-1] if '/' in tobira_item.href else tobira_item.href
                if filename in toc_map:
                    act_title, act_toc_index = toc_map[filename]
                    break
            
            if not act_title:
                act_title = f"Act {act_num}"
            
            # Find fmatter (kuchie) pages following this tobira group
            kuchie_indices = []
            scan_idx = last_tobira_idx + 1
            while scan_idx < len(spine.items):
                item = spine.items[scan_idx]
                if 'fmatter' in item.idref.lower() or item.is_illustration:
                    kuchie_indices.append(scan_idx)
                    scan_idx += 1
                else:
                    break
            
            # First content page after kuchie
            first_content_idx = scan_idx
            
            acts.append({
                "act_number": act_num,
                "title": act_title,
                "tobira_spine_indices": tobira_indices,
                "kuchie_spine_indices": kuchie_indices,
                "first_content_spine_index": first_content_idx,
                "toc_index": act_toc_index,
            })
        
        return acts

    def _extract_kuchie_multi_act(
        self,
        spine: Spine,
        content_dir: Path,
        volume_acts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract normalized frontmatter kuchie for ACT 1 only in a multi-act EPUB.
        
        Rationale:
        - Act 1 kuchie should remain regular frontmatter color plates.
        - Act 2+ tobira/fmatter images should stay inline in chapter flow to avoid
          duplicate insertion later in Builder (seen in dual-volume 25d9).
        
        Args:
            spine: Parsed spine with reading order
            content_dir: Extracted EPUB content directory
            volume_acts: Act boundary metadata from _detect_volume_acts
            
        Returns:
            List of Act 1 kuchie dicts with act tags:
            [{"file": "kuchie-001.jpg", ..., "act": 1}, ...]
        """
        from lxml import etree
        
        kuchie_list = []
        
        for act in volume_acts:
            act_num = act['act_number']
            if act_num != 1:
                continue
            # Scan both tobira pages (may contain title card images) and fmatter pages
            scan_indices = act['tobira_spine_indices'] + act['kuchie_spine_indices']
            
            for spine_idx in scan_indices:
                if spine_idx >= len(spine.items):
                    continue
                
                spine_item = spine.items[spine_idx]
                xhtml_path = content_dir / spine_item.href
                if not xhtml_path.exists():
                    continue
                
                try:
                    tree = etree.parse(str(xhtml_path))
                    root = tree.getroot()
                    
                    body = root.find(".//{http://www.w3.org/1999/xhtml}body")
                    if body is None:
                        body = root.find(".//body")
                    if body is None:
                        continue
                    
                    # Check text content - skip pages with substantial text (chapter pages)
                    text_parts = []
                    char_count = 0
                    for elem in body.iter():
                        if char_count > 200:
                            break
                        tag_name = elem.tag.split('}')[-1] if '}' in str(elem.tag) else str(elem.tag)
                        if tag_name in ('img', 'image', 'svg'):
                            continue
                        if elem.text:
                            text_parts.append(elem.text.strip())
                            char_count += len(elem.text.strip())
                        if elem.tail:
                            text_parts.append(elem.tail.strip())
                            char_count += len(elem.tail.strip())
                    
                    text_content = ' '.join(text_parts).strip()
                    if len(text_content) > 200:
                        continue  # Too much text, likely a chapter page
                    
                    # Find image references
                    img_src = None
                    
                    # Check <img> elements
                    for ns_prefix in ['{http://www.w3.org/1999/xhtml}', '']:
                        for img in body.findall(f".//{ns_prefix}img"):
                            src = img.get('src')
                            if src:
                                img_src = self._resolve_image_path(spine_item.href, src)
                                break
                        if img_src:
                            break
                    
                    # Check SVG <image> elements
                    if not img_src:
                        for img in body.findall(".//{http://www.w3.org/2000/svg}image"):
                            src = img.get('{http://www.w3.org/1999/xlink}href') or img.get('href')
                            if src:
                                img_src = self._resolve_image_path(spine_item.href, src)
                                break
                    
                    if not img_src:
                        continue
                    
                    original_filename = Path(img_src).name
                    
                    # Skip known non-kuchie patterns
                    skip_patterns = ['white', 'logo', 'blank', 'separator']
                    if any(p in original_filename.lower() for p in skip_patterns):
                        continue
                    
                    # Check image file size (skip tiny icons < 5KB)
                    img_file_path = content_dir / img_src
                    if img_file_path.exists() and img_file_path.stat().st_size < 5000:
                        continue
                    
                    # Generate sequential kuchie filename
                    kuchie_number = len(kuchie_list) + 1
                    extension = Path(original_filename).suffix
                    normalized_filename = f"kuchie-{kuchie_number:03d}{extension}"
                    
                    # Determine type based on spine idref
                    is_tobira = spine_idx in act['tobira_spine_indices']
                    kuchie_type = "tobira" if is_tobira else "color_plate"
                    
                    kuchie_list.append({
                        "file": normalized_filename,
                        "original": original_filename,
                        "spine_index": spine_idx,
                        "spine_href": spine_item.href,
                        "image_path": img_src,
                        "act": act_num,
                        "type": kuchie_type,
                    })
                    
                except Exception:
                    continue
        
        return kuchie_list

    def _resolve_image_path(self, xhtml_href: str, img_src: str) -> str:
        """Resolve relative image path from XHTML location to content-dir-relative path."""
        from pathlib import PurePosixPath
        xhtml_dir = PurePosixPath(xhtml_href).parent
        resolved = []
        for part in (xhtml_dir / img_src).parts:
            if part == '..':
                if resolved:
                    resolved.pop()
            elif part != '.':
                resolved.append(part)
        return '/'.join(resolved)

    def _build_manifest(
        self,
        volume_id: str,
        epub_path: Path,
        metadata: BookMetadata,
        toc: TableOfContents,
        spine: Spine,
        chapters: List[ConvertedChapter],
        image_catalog: Dict[str, List],
        spine_kuchie: List[Dict[str, Any]],  # Add spine-based kuchie metadata
        ruby_data: Dict[str, List],
        source_lang: str,
        target_lang: str,
        recovery_info: Optional[Dict[str, Any]] = None,
        volume_acts: Optional[List[Dict[str, Any]]] = None
    ) -> Manifest:
        """Build complete manifest from extraction results."""
        now = datetime.now().isoformat()

        # Get TOC entries for metadata
        toc_entries = toc.get_flat_list()

        # Build chapter entries with semantic IDs and TOC order
        chapter_entries = []
        used_ids = set()  # Track used IDs to prevent duplicates
        for i, ch in enumerate(chapters):
            # Get corresponding TOC entry for level info
            toc_entry = toc_entries[i] if i < len(toc_entries) else None

            # Generate semantic ID from title
            chapter_id = self._generate_chapter_id(ch.title, i, ch.filename)

            # Ensure ID is unique by adding suffix if needed
            if chapter_id in used_ids:
                # Find unique suffix
                suffix = 2
                while f"{chapter_id}_{suffix}" in used_ids:
                    suffix += 1
                chapter_id = f"{chapter_id}_{suffix}"
            used_ids.add(chapter_id)
            
            entry = ChapterEntry(
                id=chapter_id,
                source_file=ch.filename,
                translated_file=ch.filename.replace('.md', f'_{target_lang.upper()}.md'),
                title=ch.title or ch.filename,
                word_count=ch.word_count,
                toc_order=i,  # Explicit canonical order
                toc_level=toc_entry.level if toc_entry else 0,  # Nesting level
                illustrations=ch.illustrations,
                is_pre_toc_content=ch.is_pre_toc_content,
            )
            chapter_entries.append(entry.to_dict())

        # Build asset references with spine-based kuchie metadata
        assets = {
            "cover": image_catalog["cover"][0].filename if image_catalog["cover"] else None,
            "kuchie": spine_kuchie,  # Use spine-based kuchie with full metadata
            "illustrations": [img.filename for img in image_catalog["illustrations"]],
        }

        # Build pipeline state with recovery information
        librarian_state = PipelineState(
            status="completed",
            timestamp=now,
            chapters_completed=len(chapters),
            chapters_total=len(chapters),
        ).to_dict()
        
        # Add recovery diagnostics if spine fallback was used
        if recovery_info and recovery_info.get("used_spine_fallback"):
            librarian_state["recovery_method"] = "spine_fallback"
            librarian_state["recovery_reasons"] = recovery_info["recovery_reasons"]
            librarian_state["toc_entries"] = recovery_info["toc_entries"]
            librarian_state["spine_content_files"] = recovery_info["spine_content_files"]
            librarian_state["toc_coverage"] = round(recovery_info["toc_coverage"], 2)
            if recovery_info["missing_from_toc"]:
                librarian_state["missing_from_toc"] = recovery_info["missing_from_toc"][:10]  # Limit to 10 for brevity
        
        pipeline_state = {
            "librarian": librarian_state,
            "translator": PipelineState(
                status="pending",
                chapters_total=len(chapters),
            ).to_dict(),
            "critics": PipelineState(status="pending").to_dict(),
            "builder": PipelineState(status="pending").to_dict(),
        }

        # Build metadata_en with enhanced schema structure
        metadata_en = self._create_metadata_en_template(chapters, ruby_data["names"])

        # Build volume_structure for multi-act EPUBs
        volume_structure_data = {}
        if volume_acts and len(volume_acts) >= 2:
            # Map acts to chapter ranges using TOC indices
            toc_flat = toc.get_flat_list()
            act_details = []
            for i, act in enumerate(volume_acts):
                toc_idx = act.get('toc_index', 0)
                # Next act's toc_index is the boundary, or end of chapters
                if i + 1 < len(volume_acts):
                    next_toc_idx = volume_acts[i + 1].get('toc_index', len(chapters))
                else:
                    next_toc_idx = len(chapters)
                
                # Get chapter IDs for this act
                first_ch_id = chapter_entries[toc_idx]['id'] if toc_idx < len(chapter_entries) else ''
                last_ch_idx = min(next_toc_idx - 1, len(chapter_entries) - 1)
                last_ch_id = chapter_entries[last_ch_idx]['id'] if last_ch_idx >= 0 else ''
                
                # Get kuchie files for this act
                act_kuchie = [k['file'] for k in spine_kuchie if k.get('act') == act['act_number']]
                
                act_details.append({
                    "act_number": act['act_number'],
                    "title": act['title'],
                    "title_en": "",  # Placeholder for translator
                    "first_chapter_id": first_ch_id,
                    "last_chapter_id": last_ch_id,
                    "first_chapter_index": toc_idx,
                    "last_chapter_index": last_ch_idx,
                    "chapter_count": next_toc_idx - toc_idx,
                    "kuchie_files": act_kuchie,
                })
            
            volume_structure_data = {
                "is_multi_act": True,
                "act_count": len(volume_acts),
                "acts": act_details,
            }

        return Manifest(
            version="1.0",
            volume_id=volume_id,
            created_at=now,
            metadata={
                "title": metadata.title,
                "title_sort": metadata.title_sort,
                "author": metadata.author,
                "author_sort": metadata.author_sort,
                "publisher": metadata.publisher,
                "source_language": source_lang,
                "target_language": target_lang,
                "page_progression_direction": spine.page_progression,
                "isbn": metadata.isbn,
                "series": metadata.series,
                "series_index": metadata.series_index,
                "source_epub": str(epub_path.absolute()),
            },
            metadata_en=metadata_en,  # Enhanced semantic metadata for translator
            pipeline_state=pipeline_state,
            chapters=chapter_entries,
            assets=assets,
            toc=toc.to_dict(),
            ruby_names=ruby_data["names"],  # Character names from ruby annotations
            volume_structure=volume_structure_data,
        )


def run_librarian(
    epub_path: Path,
    volume_id: Optional[str] = None,
    work_base: Optional[Path] = None,
    source_lang: str = "ja",
    target_lang: str = "en"
) -> Manifest:
    """
    Main entry point for Librarian agent.

    Args:
        epub_path: Path to source EPUB file
        volume_id: Optional custom volume ID
        work_base: Optional custom working directory
        source_lang: Source language code
        target_lang: Target language code

    Returns:
        Manifest object with extraction results
    """
    agent = LibrarianAgent(work_base)
    return agent.process_epub(epub_path, volume_id, source_lang, target_lang)


# CLI interface
if __name__ == "__main__":
    import argparse
    from .config import get_target_language

    # Get default target language from config.yaml
    default_target = get_target_language()

    parser = argparse.ArgumentParser(
        description="Librarian Agent - Extract and catalog EPUB content"
    )
    parser.add_argument("epub", type=Path, help="Path to source EPUB file")
    parser.add_argument("--volume-id", "-v", type=str, help="Custom volume ID")
    parser.add_argument("--work-dir", "-w", type=Path, help="Working directory")
    parser.add_argument("--source-lang", "-s", type=str, default="ja", help="Source language code")
    parser.add_argument("--target-lang", "-t", type=str, default=default_target, 
                        help=f"Target language code (default: {default_target} from config.yaml)")

    args = parser.parse_args()

    manifest = run_librarian(
        epub_path=args.epub,
        volume_id=args.volume_id,
        work_base=args.work_dir,
        source_lang=args.source_lang,
        target_lang=args.target_lang
    )

    print(f"\nManifest saved to: {manifest.volume_id}/manifest.json")
