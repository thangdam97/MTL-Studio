"""
XHTML to Markdown Converter - Convert EPUB chapters to clean markdown.

Language-agnostic conversion that handles:
- Ruby tags (furigana) for CJK languages
- Inline illustrations with position markers
- Scene breaks and formatting
- Paragraph structure preservation
"""

import re
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Callable
from dataclasses import dataclass, field
from bs4 import BeautifulSoup, NavigableString, Tag

from .config import REMOVE_RUBY_TAGS, SCENE_BREAK_MARKER


@dataclass
class ConvertedChapter:
    """Container for converted chapter content."""
    filename: str
    title: str
    content: str
    illustrations: List[str]
    word_count: int
    paragraph_count: int
    is_pre_toc_content: bool = False  # True if unlisted opening hook
    source_files: List[str] = field(default_factory=list)  # Original source XHTML files merged into this chapter
    raw_group_index: Optional[int] = None  # Original unsplit spine group index (for Builder re-merge)
    raw_group_title: Optional[str] = None  # Original unsplit spine group title
    split_strategy: Optional[str] = None  # e.g., "text_page_boundary"


class XHTMLToMarkdownConverter:
    """Converts EPUB XHTML chapters to clean markdown."""

    # Elements to skip entirely
    SKIP_ELEMENTS = {'script', 'style', 'head', 'meta', 'link'}

    # Block elements that should have paragraph breaks
    BLOCK_ELEMENTS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'li'}

    # Heading elements
    HEADING_ELEMENTS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    # Image element patterns
    IMAGE_PATTERNS = {
        'img': 'src',
        'image': 'href',
        'svg': None,
    }

    def __init__(
        self,
        remove_ruby: bool = True,
        scene_break: str = "* * *",
        content_dir: Path = None,
        exclude_image_matcher: Optional[Callable[[str], bool]] = None,
    ):
        """
        Initialize converter.

        Args:
            remove_ruby: Whether to strip ruby tags (keep base text only)
            scene_break: Marker for scene breaks in output
            content_dir: Path to EPUB content directory (for image analysis)
            exclude_image_matcher: Optional callback to skip inline images by filename
        """
        self.remove_ruby = remove_ruby
        self.scene_break = scene_break
        self.content_dir = content_dir
        self.exclude_image_matcher = exclude_image_matcher
        # Per-file exclusions populated by raw XHTML header scan.
        self._runtime_excluded_images = set()

    def _is_excluded_image(self, image_filename: str) -> bool:
        """Check whether an image should be excluded from markdown output."""
        if image_filename.lower() in self._runtime_excluded_images:
            return True
        if not self.exclude_image_matcher:
            return False
        try:
            return bool(self.exclude_image_matcher(image_filename))
        except Exception:
            return False

    def _extract_image_filename(self, element: Tag) -> Optional[str]:
        """Extract image filename from img/image/svg tags."""
        if not isinstance(element, Tag):
            return None

        tag_name = (element.name or "").lower()
        if tag_name == 'img':
            src = element.get('src', element.get('xlink:href', ''))
            return Path(src).name if src else None
        if tag_name == 'image':
            href = element.get('href', element.get('{http://www.w3.org/1999/xlink}href', ''))
            return Path(href).name if href else None
        if tag_name == 'svg':
            nested = element.find('image')
            if nested:
                return self._extract_image_filename(nested)
        return None

    def _resolve_header_scan_root(self, body: Tag) -> Tag:
        """
        Unwrap generic container wrappers so top-of-file header scan sees real flow nodes.
        """
        root = body
        wrapper_tags = {'div', 'section', 'article', 'main'}

        while True:
            child_tags = [
                child for child in root.children
                if isinstance(child, Tag) and (child.name or "").lower() not in self.SKIP_ELEMENTS
            ]
            has_direct_text = any(
                isinstance(child, NavigableString) and child.strip() for child in root.children
            )
            if len(child_tags) == 1 and not has_direct_text and (child_tags[0].name or "").lower() in wrapper_tags:
                root = child_tags[0]
                continue
            return root

    def _detect_stylized_header_images(self, body: Tag) -> set:
        """
        Detect top-of-file decorative/chapter-header images from raw JP XHTML.

        Heuristic:
        - Scan top flow elements in order.
        - Collect image tags seen before the first substantial text block.
        - Apply only when substantial text exists later in the same file.
          (prevents excluding full-page illustration wrappers)
        """
        if not isinstance(body, Tag):
            return set()

        scan_root = self._resolve_header_scan_root(body)
        header_images = []
        saw_story_text = False
        story_text_threshold = 24

        for child in scan_root.children:
            if not isinstance(child, Tag):
                continue

            tag_name = (child.name or "").lower()
            if tag_name in self.SKIP_ELEMENTS:
                continue

            text = re.sub(r'\s+', '', child.get_text(separator='', strip=True))
            if len(text) >= story_text_threshold:
                saw_story_text = True
                break

            # Treat only image-only top blocks as stylized headers.
            # If short text already exists, this is likely real content.
            if text:
                continue

            for image_tag in child.find_all(['img', 'image', 'svg']):
                img_name = self._extract_image_filename(image_tag)
                if img_name:
                    header_images.append(img_name.lower())

        if not saw_story_text:
            return set()
        return set(header_images)

    def convert_file(self, xhtml_path: Path, chapter_title: str = "") -> ConvertedChapter:
        """
        Convert XHTML file to markdown.

        Args:
            xhtml_path: Path to XHTML file
            chapter_title: Optional title override

        Returns:
            ConvertedChapter with markdown content
        """
        if not xhtml_path.exists():
            raise ValueError(f"XHTML file not found: {xhtml_path}")

        with open(xhtml_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        return self.convert_html(html_content, xhtml_path.name, chapter_title)

    def convert_html(self, html_content: str, filename: str = "", chapter_title: str = "") -> ConvertedChapter:
        """
        Convert HTML/XHTML string to markdown.

        Args:
            html_content: HTML/XHTML content string
            filename: Source filename for reference
            chapter_title: Optional title override

        Returns:
            ConvertedChapter with markdown content
        """
        soup = BeautifulSoup(html_content, 'xml')

        # Extract title if not provided
        if not chapter_title:
            chapter_title = self._extract_title(soup)

        # Find body or main content
        body = soup.find('body')
        if body is None:
            body = soup

        # Track illustrations found
        illustrations = []

        # Convert content
        markdown_lines = []
        self._runtime_excluded_images = self._detect_stylized_header_images(body)
        try:
            self._convert_element(body, markdown_lines, illustrations)
        finally:
            self._runtime_excluded_images = set()

        # Clean up and format
        markdown = self._clean_markdown(markdown_lines)

        # Add title as heading if found
        if chapter_title:
            markdown = f"# {chapter_title}\n\n{markdown}"

        # Count words (approximate, works for most languages)
        word_count = len(re.findall(r'\S+', markdown))

        # Count paragraphs (non-empty lines that aren't markers)
        paragraphs = [line for line in markdown.split('\n\n') if line.strip() and not line.startswith('#')]
        paragraph_count = len(paragraphs)

        return ConvertedChapter(
            filename=filename,
            title=chapter_title,
            content=markdown,
            illustrations=illustrations,
            word_count=word_count,
            paragraph_count=paragraph_count,
        )

    def _is_scene_break_icon(self, image_filename: str) -> bool:
        """
        Detect if an image is likely a scene break icon.
        
        Scene break icons are small decorative images used as dividers.
        They should be converted to text scene breaks (***) instead of
        preserved as image placeholders.
        
        Args:
            image_filename: Name of the image file
        
        Returns:
            True if image appears to be a scene break icon
        """
        if not self.content_dir:
            return False
        
        # Gaiji files (inline text glyphs) are NOT scene breaks
        if image_filename.startswith('gaiji-'):
            return False
        
        # Try to locate the image file (check both /image/ and /images/ paths)
        for images_folder in ['image', 'images', 'Images', 'IMAGES']:
            image_path = self.content_dir / images_folder / image_filename
            if image_path.exists():
                break
        else:
            return False
        
        try:
            # Check file size (scene breaks are typically tiny)
            file_size = image_path.stat().st_size
            if file_size < 10240:  # Less than 10KB
                # Note: We don't have image dimension checking here
                # (that's in builder), but small file size is a strong indicator
                return True
        except Exception:
            pass
        
        return False

    def _classify_inline_image(self, image_filename: str, css_class: list = None) -> str:
        """
        Classify inline images to determine how they should be handled.
        
        Image types:
        - 'gaiji': Inline character/symbol replacement (e.g., ○, numbers, symbols)
        - 'scene_break': Small decorative divider
        - 'illustration': Regular illustration to preserve
        
        Args:
            image_filename: Name of the image file
            css_class: CSS classes from the img element
        
        Returns:
            'gaiji', 'scene_break', or 'illustration'
        """
        # Check CSS class first (most reliable)
        if css_class:
            if isinstance(css_class, str):
                css_class = css_class.split()
            if any(c in css_class for c in ['gaiji', 'glyph', 'inline-char', 'symbol']):
                return 'gaiji'
        
        # Named gaiji files
        if image_filename.startswith('gaiji-') or image_filename.startswith('glyph-'):
            return 'gaiji'
        
        if not self.content_dir:
            return 'illustration'
        
        # Try to locate the image file
        image_path = None
        for images_folder in ['image', 'images', 'Images', 'IMAGES']:
            candidate = self.content_dir / images_folder / image_filename
            if candidate.exists():
                image_path = candidate
                break
        
        if not image_path:
            return 'illustration'
        
        try:
            file_size = image_path.stat().st_size
            
            # Very small images (< 6KB) are likely gaiji characters
            # These are used for inline symbols/numbers that aren't in standard fonts
            if file_size < 6000:
                return 'gaiji'
            
            # Small images (6-15KB) are likely scene breaks or chapter decorations
            # But only if they're standalone, not within text paragraphs
            if file_size < 15000:
                return 'scene_break'
            
        except Exception:
            pass
        
        return 'illustration'

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract chapter title from HTML."""
        # Try h1, h2, h3 in order
        for tag_name in ['h1', 'h2', 'h3']:
            heading = soup.find(tag_name)
            if heading:
                return self._get_text(heading).strip()

        # Try title element
        title = soup.find('title')
        if title and title.string:
            return title.string.strip()

        return ""

    def _convert_element(
        self,
        element,
        lines: List[str],
        illustrations: List[str],
        in_paragraph: bool = False
    ):
        """
        Recursively convert HTML element to markdown.

        Args:
            element: BeautifulSoup element
            lines: Output lines list
            illustrations: List to collect illustration references
            in_paragraph: Whether we're inside a paragraph
        """
        if isinstance(element, NavigableString):
            text = str(element)
            if text.strip():
                lines.append(text)
            return

        if not isinstance(element, Tag):
            return

        tag_name = element.name.lower() if element.name else ""

        # Skip certain elements
        if tag_name in self.SKIP_ELEMENTS:
            return

        # Handle ruby tags (furigana)
        if tag_name == 'ruby':
            if self.remove_ruby:
                lines.append(self._get_text(element))
                return

            # Preserve ruby in {reading} format
            # Collect ALL base characters and ALL readings, then output as Base{CombinedReading}
            # This handles patterns like: <ruby><span>真</span><rt>ま</rt><span>白</span><rt>しろ</rt></ruby>
            # Which should become: 真白{ましろ}
            all_base_chars = []
            all_readings = []

            for child in element.children:
                if isinstance(child, NavigableString):
                    text = str(child).strip()
                    if text:
                        all_base_chars.append(text)
                elif isinstance(child, Tag):
                    child_name = child.name.lower()
                    if child_name == 'rt':
                        # Collect reading
                        reading = child.get_text().strip()
                        if reading:
                            all_readings.append(reading)
                    elif child_name == 'rp':
                        # Ignore rp tags (parentheses for fallback)
                        pass
                    elif child_name == 'rb':
                        # Explicit base container
                        text = self._get_text(child).strip()
                        if text:
                            all_base_chars.append(text)
                    elif child_name == 'rtc':
                        # Complex ruby container, rare. Skip for now.
                        pass
                    else:
                        # Other formatting tags (em, strong, span) inside ruby
                        # Treat as part of the base text
                        text = self._get_text(child).strip()
                        if text:
                            all_base_chars.append(text)

            # Output combined base with combined reading
            combined_base = "".join(all_base_chars)
            combined_reading = "".join(all_readings)

            if combined_base and combined_reading:
                lines.append(f"{combined_base}{{{combined_reading}}}")
            elif combined_base:
                # Base text without reading (shouldn't happen often)
                lines.append(combined_base)
            return

        # Handle images
        if tag_name == 'img':
            src = element.get('src', element.get('xlink:href', ''))
            if src:
                img_name = Path(src).name
                if self._is_excluded_image(img_name):
                    return
                css_class = element.get('class', [])
                
                # Classify the image type
                img_type = self._classify_inline_image(img_name, css_class)
                
                if img_type == 'gaiji':
                    # Hard-filter gaiji inline glyph assets.
                    return
                
                if img_type == 'scene_break':
                    # Scene break icon - convert to text marker
                    lines.append(f'\n{self.scene_break}\n')
                    return
                
                # Regular illustration - use block markdown image format
                illustrations.append(img_name)
                lines.append(f'\n![illustration]({img_name})\n')
            return

        if tag_name == 'image':
            href = element.get('href', element.get('{http://www.w3.org/1999/xlink}href', ''))
            if href:
                img_name = Path(href).name
                if self._is_excluded_image(img_name):
                    return
                css_class = element.get('class', [])
                
                # Classify the image type
                img_type = self._classify_inline_image(img_name, css_class)
                
                if img_type == 'gaiji':
                    # Hard-filter gaiji inline glyph assets.
                    return
                
                if img_type == 'scene_break':
                    # Scene break icon
                    lines.append(f'\n{self.scene_break}\n')
                    return
                
                # Regular illustration - use block markdown image format
                illustrations.append(img_name)
                lines.append(f'\n![illustration]({img_name})\n')
            return

        # Handle SVG with embedded image
        if tag_name == 'svg':
            img = element.find('image')
            if img:
                href = img.get('href', img.get('{http://www.w3.org/1999/xlink}href', ''))
                if href:
                    img_name = Path(href).name
                    if self._is_excluded_image(img_name):
                        return
                    css_class = img.get('class', [])
                    
                    # Classify the image type
                    img_type = self._classify_inline_image(img_name, css_class)
                    
                    if img_type == 'gaiji':
                        # Hard-filter gaiji inline glyph assets.
                        return
                    
                    if img_type == 'scene_break':
                        lines.append(f'\n{self.scene_break}\n')
                        return
                    
                    illustrations.append(img_name)
                    lines.append(f'\n![illustration]({img_name})\n')
            return

        # Handle headings (skip h1 since we add title separately)
        if tag_name in self.HEADING_ELEMENTS:
            level = int(tag_name[1])
            text = self._get_text(element).strip()
            if text:
                # Use level + 1 since h1 is reserved for chapter title
                lines.append(f"\n{'#' * (level + 1)} {text}\n")
            return

        # Handle paragraphs
        if tag_name == 'p':
            # Check for scene break patterns
            text = self._get_text(element).strip()
            sb_marker = self._is_scene_break(element, text)
            if sb_marker:
                lines.append(f"\n{sb_marker}\n")
                return

            # Regular paragraph
            para_lines = []
            for child in element.children:
                self._convert_element(child, para_lines, illustrations, True)

            para_text = ''.join(para_lines).strip()
            if para_text:
                lines.append(f"\n{para_text}\n")
            return

        # Handle line breaks
        if tag_name == 'br':
            lines.append('\n')
            return

        # Handle emphasis
        if tag_name in ('em', 'i'):
            text = self._get_text(element).strip()
            if text:
                lines.append(f"*{text}*")
            return

        # Handle strong
        if tag_name in ('strong', 'b'):
            text = self._get_text(element).strip()
            if text:
                lines.append(f"**{text}**")
            return

        # Handle spans (check for specific classes)
        if tag_name == 'span':
            css_class = element.get('class', [])
            if isinstance(css_class, str):
                css_class = css_class.split()

            # Check for emphasis classes
            if any(c in css_class for c in ['em', 'emphasis', 'italic']):
                text = self._get_text(element).strip()
                if text:
                    lines.append(f"*{text}*")
                return

            # Check for bold classes
            if any(c in css_class for c in ['strong', 'bold']):
                text = self._get_text(element).strip()
                if text:
                    lines.append(f"**{text}**")
                return

        # Handle blockquotes
        if tag_name == 'blockquote':
            text = self._get_text(element).strip()
            if text:
                # Prefix each line with >
                quoted_lines = [f"> {line}" for line in text.split('\n')]
                lines.append('\n' + '\n'.join(quoted_lines) + '\n')
            return

        # Handle horizontal rules
        if tag_name == 'hr':
            lines.append(f"\n{self.scene_break}\n")
            return

        # Handle divs (check for scene break classes)
        if tag_name == 'div':
            css_class = element.get('class', [])
            if isinstance(css_class, str):
                css_class = css_class.split()

            # Scene break classes
            if any(c in css_class for c in ['scene-break', 'break', 'separator', 'asterism']):
                text = self._get_text(element).strip()
                sb_marker = self._is_scene_break(element, text) or self.scene_break
                lines.append(f"\n{sb_marker}\n")
                return

            # Image container
            if any(c in css_class for c in ['image', 'illustration', 'fig', 'figure']):
                img = element.find('img')
                if img:
                    self._convert_element(img, lines, illustrations)
                return

        # Default: recursively process children
        for child in element.children:
            self._convert_element(child, lines, illustrations, in_paragraph)

    def _get_text(self, element) -> str:
        """Get text content, handling ruby tags."""
        if self.remove_ruby:
            # Build text excluding rt (ruby text) elements
            texts = []
            for descendant in element.descendants:
                if isinstance(descendant, NavigableString):
                    parent = descendant.parent
                    if parent and parent.name not in ('rt', 'rp'):
                        texts.append(str(descendant))
            return ''.join(texts)
        else:
            return element.get_text()

    def _is_scene_break(self, element: Tag, text: str) -> Optional[str]:
        """
        Check if element represents a scene break.
        Returns the original text if it's a decorative marker, or self.scene_break otherwise.
        
        Supported proprietary patterns (discovered from OUTPUT analysis):
        - Asterisks: *, **, ***, * * *
        - Diamonds: ◆, ◇, ◆◇◆, ◆　◇　◆　◇
        - Stars: ★, ☆, ★ ★ ★, ☆ ☆ ☆
        - Triangles: ▼▽
        - Circles: ●, ○
        - Others: ※※※, §
        """
        # Check CSS class
        css_class = element.get('class', [])
        if isinstance(css_class, str):
            css_class = css_class.split()

        is_break_class = any(c in css_class for c in ['scene-break', 'break', 'separator', 'asterism', 'ornament'])

        # Comprehensive decorative pattern list (preserve original markers)
        decorative_patterns = [
            # Single ornaments
            r'^\s*[◇◆★☆●○◎□■△▲▽▼❖◈⬥✦§]\s*$',
            
            # Diamond patterns
            r'^\s*◆◇◆\s*$',
            r'^\s*◇◆◇\s*$',
            r'^\s*◆[\s　]*◇[\s　]*◆[\s　]*◇?\s*$',  # ◆　◇　◆　◇
            r'^\s*◇[\s　]*◆[\s　]*◇[\s　]*◆?\s*$',  # ◇　◆　◇　◆
            r'^\s*◆[\s　]+◆\s*$',                   # ◆　　　　　　◆
            r'^\s*◇[\s　]+◇[\s　]+◇\s*$',           # ◇　　　◇　　　◇
            r'^\s*◇\s+◇\s+◇\s*$',                   # ◇ ◇ ◇
            
            # Star patterns
            r'^\s*★\s+★\s+★\s*$',                   # ★ ★ ★
            r'^\s*☆\s+☆\s+☆\s*$',                   # ☆ ☆ ☆
            r'^\s*☆☆+\s*$',                         # ☆☆
            r'^\s*★★+\s*$',                         # ★★
            
            # Triangle patterns
            r'^\s*▼▽\s*$',
            r'^\s*▽▼\s*$',
            r'^\s*[▼▽△▲]{2,}\s*$',
            
            # Circle patterns
            r'^\s*[●○]{2,}\s*$',
            
            # Other patterns
            r'^\s*※※※\s*$',
            r'^\s*※[\s　]*※[\s　]*※\s*$',
            r'^\s*§§+\s*$',
            r'^\s*⁂\s*$',                           # Asterism
            
            # Japanese-style triple ornament (with full-width spaces)
            r'^\s*[◇◆★☆●○◎□■△▲▽▼][　 ]+[◇◆★☆●○◎□■△▲▽▼][　 ]+[◇◆★☆●○◎□■△▲▽▼]\s*$',
        ]
        
        for pattern in decorative_patterns:
            if re.match(pattern, text):
                return text.strip()

        # Generic break patterns (normalize to standard scene break)
        generic_patterns = [
            r'^\s*\*\s*\*\s*\*\s*$',   # * * *
            r'^\s*\*{1,5}\s*$',        # *, **, ***, ****, *****
            r'^\s*[-_]{3,}\s*$',       # --- or ___
            r'^\s*[=~]{3,}\s*$',       # === or ~~~
        ]
        for pattern in generic_patterns:
            if re.match(pattern, text):
                return self.scene_break

        return self.scene_break if is_break_class else None

    def _clean_markdown(self, lines: List[str]) -> str:
        """Clean and format the final markdown output."""
        # Join all lines
        text = ''.join(lines)

        # Normalize whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines
        text = re.sub(r' +', ' ', text)          # Single spaces
        text = re.sub(r'\n +', '\n', text)       # Remove leading spaces

        # Clean up around markdown images (![](...))
        text = re.sub(r'\n{2,}(!\[)', r'\n\n\1', text)
        text = re.sub(r'(\))\n{2,}', r'\1\n\n', text)

        # Clean up around scene breaks
        text = re.sub(rf'\n{{2,}}({re.escape(self.scene_break)})', rf'\n\n\1', text)
        text = re.sub(rf'({re.escape(self.scene_break)})\n{{2,}}', rf'\1\n\n', text)

        return text.strip()


def convert_xhtml_to_markdown(
    xhtml_path: Path,
    chapter_title: str = "",
    remove_ruby: bool = True,
    scene_break: str = "* * *"
) -> ConvertedChapter:
    """
    Main function to convert XHTML file to markdown.

    Args:
        xhtml_path: Path to XHTML file
        chapter_title: Optional title override
        remove_ruby: Whether to strip ruby tags
        scene_break: Scene break marker

    Returns:
        ConvertedChapter object
    """
    converter = XHTMLToMarkdownConverter(remove_ruby, scene_break)
    return converter.convert_file(xhtml_path, chapter_title)


def convert_all_chapters(
    content_dir: Path,
    output_dir: Path,
    chapter_order: Optional[List[str]] = None,
    remove_ruby: bool = True
) -> List[ConvertedChapter]:
    """
    Convert all XHTML chapters to markdown files.

    Args:
        content_dir: Directory containing XHTML files
        output_dir: Directory to write markdown files
        chapter_order: Optional ordered list of chapter files
        remove_ruby: Whether to strip ruby tags

    Returns:
        List of ConvertedChapter objects
    """
    converter = XHTMLToMarkdownConverter(remove_ruby)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get files to process
    if chapter_order:
        xhtml_files = []
        for ref in chapter_order:
            # Handle fragment references (file.xhtml#id)
            filename = ref.split('#')[0]
            filepath = content_dir / filename
            if filepath.exists() and filepath not in xhtml_files:
                xhtml_files.append(filepath)
    else:
        xhtml_files = sorted(content_dir.glob("*.xhtml"))

    results = []
    for xhtml_path in xhtml_files:
        try:
            chapter = converter.convert_file(xhtml_path)

            # Write markdown file
            md_filename = xhtml_path.stem + ".md"
            md_path = output_dir / md_filename

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(chapter.content)

            print(f"[OK] Converted {xhtml_path.name} -> {md_filename}")
            results.append(chapter)

        except Exception as e:
            print(f"[FAIL] Error converting {xhtml_path.name}: {e}")

    return results
