"""
Markdown to XHTML Converter - Industry Standard OEBPS Format.

Converts translated markdown content to XHTML paragraphs with proper
XML escaping, illustration handling, and formatting.

Path convention: Uses OEBPS standard paths (../Images/)
"""

import re
from typing import List
from html import escape

try:
    from smartypants import smartypants, Attr
    SMARTYPANTS_AVAILABLE = True
except ImportError:
    SMARTYPANTS_AVAILABLE = False
    Attr = None

from ..config import SCENE_BREAK_MARKER, ILLUSTRATION_PLACEHOLDER_PATTERN, MARKDOWN_IMAGE_PATTERN
from .config import COLLAPSE_BLANK_LINES, BLANK_LINE_FREQUENCY

# Industry-standard image path (OEBPS format)
IMAGES_PATH = "../Images"


class MarkdownToXHTML:
    """Converts markdown content to XHTML paragraph format."""

    @staticmethod
    def convert_paragraphs(paragraphs: List[str]) -> List[str]:
        """
        Convert a list of paragraphs to XHTML <p> tags.

        Args:
            paragraphs: List of paragraph strings (including "<blank>" markers)

        Returns:
            List of XHTML paragraph strings
        """
        xhtml_paragraphs = []

        for para in paragraphs:
            xhtml_para = MarkdownToXHTML._convert_single_paragraph(para)
            if xhtml_para:
                xhtml_paragraphs.append(xhtml_para)

        return xhtml_paragraphs

    @staticmethod
    def _convert_single_paragraph(para: str, skip_illustrations: bool = False) -> str:
        """
        Convert a single paragraph to XHTML.

        Args:
            para: Single paragraph string
            skip_illustrations: If True, skip illustration placeholders

        Returns:
            XHTML paragraph tag or empty string
        """
        if para == "<blank>":
            return '<p><br/></p>'

        # Check for standalone illustration placeholder (block-level)
        stripped = para.strip()
        if MarkdownToXHTML._is_illustration_placeholder(stripped):
            if skip_illustrations:
                return ""
            else:
                return MarkdownToXHTML._convert_illustration_placeholder(stripped)

        # Check for scene break marker
        if stripped == SCENE_BREAK_MARKER:
            return '<p class="section-break">◆</p>'

        # Check if paragraph contains inline image tags (normalize and preserve them)
        if '<img' in para and 'src=' in para:
            para = MarkdownToXHTML._normalize_inline_images(para)
            # Wrap in paragraph if not already wrapped
            if para.startswith('<img'):
                return f'<p class="illustration">{para}</p>'
            return para

        # Check for inline gaiji images within text (markdown format)
        # These need to be converted but kept inline with surrounding text
        content = para
        if re.search(r'!\[gaiji\]\([^)]+\)', content):
            content = MarkdownToXHTML._convert_inline_gaiji(content)

        # Apply smart quotes/dashes/ellipses FIRST (before XML escaping)
        # This ensures 100% typographic compliance even if AI agents output straight quotes
        if SMARTYPANTS_AVAILABLE:
            # STEP 1: Protect stacked dialogue (3+ consecutive quotes for multi-speaker chorus)
            stacked_quotes = []
            STACKED_PATTERN = re.compile(r'"{3,}([^"]+)"{3,}')
            
            def protect_stacked(match):
                stacked_quotes.append(match.group(0))
                return f"__STACKED_{len(stacked_quotes)-1}__"
            
            content = STACKED_PATTERN.sub(protect_stacked, content)
            
            # STEP 2: Apply curly quotes to normal dialogue
            # Use Attr flags: q=quotes, D=em-dashes, e=ellipses
            # smartypants converts: " → &#8220; (left curly quote), ' → &#8216;, etc.
            content = smartypants(content, Attr.q | Attr.D | Attr.e)
            
            # STEP 3: Restore stacked dialogue with original straight quotes
            for idx, original in enumerate(stacked_quotes):
                content = content.replace(f"__STACKED_{idx}__", original)
        
        # Escape XML special characters (< > &) BUT preserve HTML entities from smartypants
        # We can't use escape() directly as it would double-escape &#8220; → &amp;#8220;
        # Instead, manually escape only the dangerous characters not in entities
        escaped_content = content.replace('&', '&amp;')  # Escape & first
        escaped_content = escaped_content.replace('&amp;#', '&#')  # Restore &#XXXX; entities
        escaped_content = escaped_content.replace('<', '&lt;')
        escaped_content = escaped_content.replace('>', '&gt;')

        # Finally convert markdown formatting
        escaped_content = MarkdownToXHTML._convert_markdown_formatting(escaped_content)

        return f'<p>{escaped_content}</p>'

    @staticmethod
    def _normalize_inline_images(para: str) -> str:
        """
        Normalize existing img tags to OEBPS standard paths.
        
        Converts EN translation inline images to proper EPUB format:
        - Updates path from ../image/ to ../Images/
        - Updates class from 'fit' to 'insert'
        
        Args:
            para: Paragraph text containing img tags
            
        Returns:
            Normalized paragraph text
        """
        # Update path from ../image/ to ../Images/
        para = re.sub(
            r'src="\.\./image/([^"]+)"',
            r'src="../Images/\1"',
            para
        )
        # Update class from 'fit' to 'insert'
        para = re.sub(
            r'class="fit"',
            r'class="insert"',
            para
        )
        return para

    @staticmethod
    def _convert_markdown_formatting(text: str) -> str:
        """
        Convert markdown formatting to HTML tags.

        Converts:
        - **bold** to <strong>bold</strong>
        - *italic* to <em>italic</em>

        Args:
            text: Text with markdown formatting

        Returns:
            Text with HTML tags
        """
        # Convert **bold** to <strong>bold</strong>
        text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)

        # Convert *italic* to <em>italic</em>
        text = re.sub(r'(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)

        return text

    @staticmethod
    def _is_illustration_placeholder(text: str) -> bool:
        """Check if text contains an illustration placeholder (legacy or markdown format)."""
        # Legacy format: [ILLUSTRATION: filename]
        if re.search(ILLUSTRATION_PLACEHOLDER_PATTERN, text):
            return True
        # Markdown format: ![illustration](filename) or ![gaiji](filename)
        if re.search(MARKDOWN_IMAGE_PATTERN, text):
            return True
        return False

    @staticmethod
    def _convert_illustration_placeholder(text: str) -> str:
        """Convert illustration placeholder to XHTML img tag."""
        # Try legacy format first: [ILLUSTRATION: filename]
        match = re.search(ILLUSTRATION_PLACEHOLDER_PATTERN, text)
        if match:
            filename = match.group(1)
            return f'<p class="illustration"><img class="insert" src="{IMAGES_PATH}/{filename}" alt=""/></p>'
        
        # Try markdown format: ![alt](filename)
        match = re.search(MARKDOWN_IMAGE_PATTERN, text)
        if match:
            alt_type = match.group(1)  # 'illustration', 'gaiji', or ''
            filename = match.group(2)
            
            if alt_type == 'gaiji':
                # Gaiji: inline character - no wrapper paragraph, just the img
                # Will be embedded inline within surrounding text
                return f'<img class="gaiji" src="{IMAGES_PATH}/{filename}" alt=""/>'
            else:
                # Regular illustration - full block with wrapper
                return f'<p class="illustration"><img class="insert" src="{IMAGES_PATH}/{filename}" alt=""/></p>'
        
        return ""

    @staticmethod
    def convert_to_xhtml_string(paragraphs: List[str]) -> str:
        """
        Convert paragraphs to a single XHTML content string.

        Args:
            paragraphs: List of paragraph strings

        Returns:
            Concatenated XHTML paragraphs as string
        """
        filtered_paragraphs = MarkdownToXHTML._collapse_blank_lines(paragraphs)
        xhtml_paragraphs = MarkdownToXHTML.convert_paragraphs(filtered_paragraphs)
        return '\n      '.join(xhtml_paragraphs)

    @staticmethod
    def _collapse_blank_lines(paragraphs: List[str]) -> List[str]:
        """
        Collapse consecutive <blank> markers to reduce visual breaks.
        Swallows the first blank line (standard paragraph separator) 
        but keeps subsequent ones as explicit breaks.

        Args:
            paragraphs: List of paragraph strings

        Returns:
            Filtered list with fewer <blank> markers
        """
        if not COLLAPSE_BLANK_LINES:
            return paragraphs

        filtered = []
        blank_run = 0

        for para in paragraphs:
            if para == "<blank>":
                blank_run += 1
                # Swallow the first blank line in any run
                # Keep any subsequent ones
                if blank_run > 1:
                    filtered.append(para)
            else:
                blank_run = 0
                filtered.append(para)

        return filtered

    @staticmethod
    def escape_xml_content(text: str) -> str:
        """Escape XML special characters in text content."""
        return escape(text)


def convert_paragraphs_to_xhtml(paragraphs: List[str], skip_illustrations: bool = False) -> str:
    """
    Main function to convert markdown paragraphs to XHTML.

    Args:
        paragraphs: List of paragraph strings
        skip_illustrations: If True, skip illustration placeholders

    Returns:
        XHTML content string
    """
    if skip_illustrations:
        xhtml_paragraphs = []
        for para in paragraphs:
            if para == "<blank>":
                xhtml_paragraphs.append('<p><br/></p>')
            elif not MarkdownToXHTML._is_illustration_placeholder(para):
                xhtml_para = MarkdownToXHTML._convert_single_paragraph(para, skip_illustrations=True)
                if xhtml_para:
                    xhtml_paragraphs.append(xhtml_para)
        return '\n      '.join(xhtml_paragraphs)
    else:
        return MarkdownToXHTML.convert_to_xhtml_string(paragraphs)


def extract_illustrations_from_paragraphs(paragraphs: List[str]) -> List[str]:
    """
    Extract illustration filenames from paragraph list.

    Args:
        paragraphs: List of paragraph strings

    Returns:
        List of illustration filenames
    """
    illustrations = []

    for para in paragraphs:
        match = re.search(ILLUSTRATION_PLACEHOLDER_PATTERN, para)
        if match:
            filename = match.group(1)
            illustrations.append(filename)

    return illustrations
