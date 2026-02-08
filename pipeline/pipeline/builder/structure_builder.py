"""
EPUB Structure Builder - Industry Standard OEBPS Format.

Creates special XHTML files for cover, kuchie images, title page, and TOC.
Following Yen Press / J-Novel Club EPUB presentation standards.
Supports both EPUB2 and EPUB3 formats.

Path convention: Uses OEBPS standard paths (../Styles/, ../Images/)
"""

from pathlib import Path
from typing import List, Dict
from html import escape

from .config import get_epub_version


# Industry-standard paths (OEBPS format)
CSS_PATH = "../Styles/stylesheet.css"
IMAGES_PATH = "../Images"


class StructureBuilder:
    """Builds specialized XHTML files for EPUB structure."""

    @staticmethod
    def create_cover_xhtml(
        output_path: Path,
        title: str,
        lang_code: str = "en",
        cover_image: str = "cover.jpg"
    ) -> None:
        """
        Create cover XHTML file.

        Args:
            output_path: Path where to write cover.xhtml
            title: Book title for metadata
            lang_code: Language code for html attributes
            cover_image: Cover image filename
        """
        escaped_title = escape(title)
        epub_version = get_epub_version()

        if epub_version == "EPUB3":
            cover_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta charset="UTF-8"/>
  <title>{escaped_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<section epub:type="cover" id="cover">
  <div class="main">
    <p class="cover-image"><img class="fullpage" src="{IMAGES_PATH}/{cover_image}" alt="{escaped_title}"/></p>
  </div>
</section>
</body>
</html>
'''
        else:
            cover_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8"/>
  <title>{escaped_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<div id="cover" class="cover">
  <div class="main">
    <p class="cover-image"><img class="fullpage" src="{IMAGES_PATH}/{cover_image}" alt="{escaped_title}"/></p>
  </div>
</div>
</body>
</html>
'''
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(cover_xhtml, encoding='utf-8')

    @staticmethod
    def create_image_page_xhtml(
        output_path: Path,
        image_filename: str,
        page_id: str,
        title: str,
        lang_code: str = "en",
        css_class: str = "insert"
    ) -> None:
        """
        Create a full-page image XHTML file (kuchie, illustration, title page).

        Args:
            output_path: Path where to write the XHTML file
            image_filename: Filename of the image
            page_id: ID for the section/div element
            title: Book title for metadata
            lang_code: Language code for html attributes
            css_class: CSS class for the image container
        """
        escaped_title = escape(title)
        epub_version = get_epub_version()

        if epub_version == "EPUB3":
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta charset="UTF-8"/>
  <title>{escaped_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<section epub:type="bodymatter" id="{page_id}">
  <div class="main">
    <p class="{css_class}"><img class="fullpage" src="{IMAGES_PATH}/{image_filename}" alt=""/></p>
  </div>
</section>
</body>
</html>
'''
        else:
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8"/>
  <title>{escaped_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<div id="{page_id}" class="{css_class}">
  <div class="main">
    <p class="{css_class}"><img class="fullpage" src="{IMAGES_PATH}/{image_filename}" alt=""/></p>
  </div>
</div>
</body>
</html>
'''
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xhtml, encoding='utf-8')

    @staticmethod
    def create_horizontal_kuchie_xhtml(
        output_path: Path,
        image_filename: str,
        width: int,
        height: int,
        page_id: str,
        title: str,
        lang_code: str = "en"
    ) -> None:
        """
        Create horizontal kuchi-e XHTML with SVG wrapper for landscape display.
        
        Uses SVG wrapper with viewport meta tag to enable full-resolution
        landscape display for wide-format double-page spread kuchi-e images.
        Follows the pattern used in official Japanese light novel EPUBs.
        
        Args:
            output_path: Path where to write the XHTML file
            image_filename: Filename of the image
            width: Image width in pixels
            height: Image height in pixels
            page_id: ID for the section/div element
            title: Book title for metadata
            lang_code: Language code for html attributes
        """
        escaped_title = escape(title)
        epub_version = get_epub_version()
        
        if epub_version == "EPUB3":
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta charset="UTF-8"/>
  <title>{escaped_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
  <meta name="viewport" content="width={width}, height={height}"/>
</head>

<body>
<section epub:type="bodymatter" id="{page_id}">
  <div class="main">
    <div class="horizontal-kuchie">
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" 
           version="1.1" width="100%" height="100%" viewBox="0 0 {width} {height}">
        <image width="{width}" height="{height}" xlink:href="{IMAGES_PATH}/{image_filename}"/>
      </svg>
    </div>
  </div>
</section>
</body>
</html>
'''
        else:
            # EPUB2 version with similar structure
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8"/>
  <title>{escaped_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
  <meta name="viewport" content="width={width}, height={height}"/>
</head>

<body>
<div id="{page_id}" class="horizontal-kuchie">
  <div class="main">
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" 
         version="1.1" width="100%" height="100%" viewBox="0 0 {width} {height}">
      <image width="{width}" height="{height}" xlink:href="{IMAGES_PATH}/{image_filename}"/>
    </svg>
  </div>
</div>
</body>
</html>
'''
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xhtml, encoding='utf-8')


    @staticmethod
    def create_act_separator_xhtml(
        output_path: Path,
        act_title: str,
        act_number: int,
        book_title: str,
        lang_code: str = "en"
    ) -> None:
        """
        Create an act separator XHTML page for multi-act EPUBs.
        
        This is the translated equivalent of a tobira (扉) page that
        separates acts in merged multi-volume Japanese light novel EPUBs.
        
        Args:
            output_path: Path where to write the XHTML file
            act_title: Title of the act (e.g., "Act II — The Frozen Snow Princess")
            act_number: Act number (2, 3, ...)
            book_title: Book title for metadata
            lang_code: Language code for html attributes
        """
        escaped_title = escape(act_title)
        escaped_book_title = escape(book_title)
        epub_version = get_epub_version()
        page_id = f"act-{act_number:03d}-separator"

        if epub_version == "EPUB3":
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta charset="UTF-8"/>
  <title>{escaped_book_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<section epub:type="part" id="{page_id}">
  <div class="main">
    <h1 style="text-align: center; margin-top: 40%; font-size: 1.8em;">{escaped_title}</h1>
  </div>
</section>
</body>
</html>
'''
        else:
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8"/>
  <title>{escaped_book_title}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<div id="{page_id}" class="act-separator">
  <div class="main">
    <h1 style="text-align: center; margin-top: 40%; font-size: 1.8em;">{escaped_title}</h1>
  </div>
</div>
</body>
</html>
'''
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(xhtml, encoding='utf-8')

    @staticmethod
    def create_toc_xhtml(
        output_path: Path,
        toc_entries: List[Dict[str, str]],
        toc_title: str,
        book_title: str,
        lang_code: str = "en"
    ) -> None:
        """
        Create visual Table of Contents XHTML file.

        Args:
            output_path: Path where to write toc.xhtml
            toc_entries: List of dicts with 'href' and 'label' keys
            toc_title: Title for the TOC page (e.g., "Table of Contents")
            book_title: Book title for metadata
            lang_code: Language code for html attributes
        """
        # Build TOC entries
        toc_html = ""
        for entry in toc_entries:
            href = entry.get('href', '')
            label = escape(entry.get('label', ''))
            toc_html += f'        <li><a href="{href}">{label}</a></li>\n'

        epub_version = get_epub_version()

        if epub_version == "EPUB3":
            toc_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>

<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta charset="UTF-8"/>
  <title>{escape(toc_title)}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<section epub:type="frontmatter toc" id="toc-page">
  <div class="main">
    <h1>{escape(toc_title)}</h1>
    <ol class="toc-list">
{toc_html}    </ol>
  </div>
</section>
</body>
</html>
'''
        else:
            toc_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml"
      lang="{lang_code}"
      xml:lang="{lang_code}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8"/>
  <title>{escape(toc_title)}</title>
  <link href="{CSS_PATH}" rel="stylesheet" type="text/css"/>
</head>

<body>
<div id="toc-page" class="toc">
  <div class="main">
    <h1>{escape(toc_title)}</h1>
    <ol class="toc-list">
{toc_html}    </ol>
  </div>
</div>
</body>
</html>
'''
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(toc_xhtml, encoding='utf-8')


# Convenience functions
def create_cover_file(output_path: Path, title: str, lang_code: str = "en") -> None:
    """Create cover XHTML file."""
    StructureBuilder.create_cover_xhtml(output_path, title, lang_code)


def create_kuchie_file(
    output_path: Path,
    kuchie_filename: str,
    page_id: str,
    title: str,
    lang_code: str = "en"
) -> None:
    """Create kuchie (illustration) page XHTML file."""
    StructureBuilder.create_image_page_xhtml(
        output_path, kuchie_filename, page_id, title, lang_code, "kuchie-image"
    )


def create_insert_page(
    output_path: Path,
    image_filename: str,
    page_id: str,
    title: str,
    lang_code: str = "en"
) -> None:
    """Create full-page illustration insert XHTML file."""
    StructureBuilder.create_image_page_xhtml(
        output_path, image_filename, page_id, title, lang_code, "insert-page"
    )


def create_toc_file(
    output_path: Path,
    toc_entries: List[Dict[str, str]],
    toc_title: str,
    book_title: str,
    lang_code: str = "en"
) -> None:
    """Create TOC XHTML file."""
    StructureBuilder.create_toc_xhtml(output_path, toc_entries, toc_title, book_title, lang_code)
