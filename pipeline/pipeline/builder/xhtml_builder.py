"""
XHTML Builder - Industry Standard OEBPS Format.

Builds XHTML files following Yen Press / J-Novel Club EPUB presentation standards.
Supports both EPUB2 (legacy) and EPUB3 (modern) formats.

Path convention: Uses OEBPS standard paths (../Styles/)
"""

import re
from pathlib import Path
from html import escape
from typing import Any

from .config import get_epub_version

# Industry-standard CSS path (OEBPS format)
CSS_PATH = "../Styles/stylesheet.css"


class XHTMLBuilder:
    """Builds XHTML files with content following industry standards."""

    @staticmethod
    def _coerce_text(value: Any, fallback: str = "") -> str:
        """
        Convert mixed manifest values (str/dict/list/etc.) into safe text.
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
                    candidate = XHTMLBuilder._coerce_text(value.get(key), "")
                    if candidate:
                        return candidate
            for candidate in value.values():
                normalized = XHTMLBuilder._coerce_text(candidate, "")
                if normalized:
                    return normalized
            return fallback
        if isinstance(value, (list, tuple)):
            parts = [XHTMLBuilder._coerce_text(v, "") for v in value]
            parts = [p for p in parts if p]
            return " / ".join(parts) if parts else fallback
        text = str(value).strip()
        return text if text else fallback

    @staticmethod
    def build_chapter_xhtml(
        content: str,
        chapter_title: str = "",
        chapter_id: str = "",
        lang_code: str = "en",
        book_title: str = ""
    ) -> str:
        """
        Build industry-standard XHTML structure for a chapter.

        Args:
            content: XHTML content paragraphs
            chapter_title: Chapter title for <h1> element
            chapter_id: Chapter identifier for section/div id attribute
            lang_code: ISO 639-1 language code
            book_title: Book title for <title> element

        Returns:
            Complete XHTML document string
        """
        chapter_title_text = XHTMLBuilder._coerce_text(chapter_title, "")
        escaped_title = escape(chapter_title_text) if chapter_title_text else ""
        section_id = XHTMLBuilder._coerce_text(chapter_id, "chapter") or "chapter"
        book_title_text = XHTMLBuilder._coerce_text(book_title, "")
        page_title = escape(book_title_text) if book_title_text else escaped_title or "Chapter"
        epub_version = get_epub_version()

        # Build chapter title if provided
        title_html = ""
        if chapter_title_text:
            title_html = f'      <h1>{escaped_title}</h1>\n\n'

        if epub_version == "EPUB3":
            return XHTMLBuilder._build_epub3_chapter(content, title_html, section_id, lang_code, page_title)
        else:
            return XHTMLBuilder._build_epub2_chapter(content, title_html, section_id, lang_code, page_title)

    @staticmethod
    def _build_epub3_chapter(content: str, title_html: str, section_id: str, lang_code: str, page_title: str) -> str:
        """Build EPUB3 format chapter."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta charset="UTF-8"/>
  <title>{page_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<section epub:type="bodymatter chapter" id="{section_id}">
  <div class="main">
{title_html}{content}
  </div>
</section>
</body>
</html>
'''

    @staticmethod
    def _build_epub2_chapter(content: str, title_html: str, section_id: str, lang_code: str, page_title: str) -> str:
        """Build EPUB2 format chapter."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8"/>
  <title>{page_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<div id="{section_id}" class="chapter">
  <div class="main">
{title_html}{content}
  </div>
</div>
</body>
</html>
'''

    @staticmethod
    def remove_ruby_tags(content: str) -> str:
        """
        Remove ruby and rt tags (furigana) from content.

        Args:
            content: XHTML content

        Returns:
            Content with ruby tags removed
        """
        # Pattern: <ruby>base<rt>ruby</rt></ruby> → base
        content = re.sub(r'<ruby>([^<]*)<rt>[^<]*</rt></ruby>', r'\1', content)

        # Remove any remaining orphaned ruby/rt tags
        content = re.sub(r'</?ruby>', '', content)
        content = re.sub(r'</?rt>', '', content)

        return content

    @staticmethod
    def remove_vertical_text_class(content: str) -> str:
        """Remove class='vrtl' from html tag."""
        content = re.sub(r'<html\s+([^>]*)class="vrtl"\s*([^>]*)>', r'<html \1\2>', content)
        content = re.sub(r'<html\s+class="vrtl"\s*>', '<html>', content)
        return content

    @staticmethod
    def update_language_attribute(content: str, old_lang: str, new_lang: str) -> str:
        """
        Update xml:lang attribute from source to target language.

        Args:
            content: XHTML content
            old_lang: Source language code
            new_lang: Target language code

        Returns:
            Modified XHTML content
        """
        content = re.sub(rf'xml:lang="{old_lang}"', f'xml:lang="{new_lang}"', content)
        content = re.sub(rf"xml:lang='{old_lang}'", f"xml:lang='{new_lang}'", content)
        content = re.sub(rf'lang="{old_lang}"', f'lang="{new_lang}"', content)
        return content


def build_chapter_file(
    content: str,
    output_path: Path,
    chapter_title: str = "",
    chapter_id: str = "",
    lang_code: str = "en"
) -> None:
    """
    Build and write a chapter XHTML file.

    Args:
        content: XHTML content paragraphs
        output_path: Path to write XHTML file
        chapter_title: Chapter title
        chapter_id: Chapter identifier
        lang_code: Target language code
    """
    xhtml = XHTMLBuilder.build_chapter_xhtml(
        content=content,
        chapter_title=chapter_title,
        chapter_id=chapter_id,
        lang_code=lang_code
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xhtml, encoding='utf-8')
