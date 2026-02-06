"""
Manga Ingest Pipeline.

Extracts page images from manga archives (CBZ/CBR/PDF/ZIP)
and directories for feeding into the visual analyzer.

🧪 EXPERIMENTAL — Phase 1.8a

Supported formats:
  .cbz  → ZIP archive of images
  .cbr  → RAR archive of images (requires unrar)
  .pdf  → PDF with embedded images (requires pymupdf)
  .zip  → Generic ZIP of images
  dir/  → Directory of images (already extracted)
"""

import zipfile
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_ARCHIVE_EXTENSIONS = {".cbz", ".cbr", ".pdf", ".zip"}


def ingest_manga(
    source: Path,
    output_dir: Path,
    volume_id: str,
) -> Tuple[List[Path], dict]:
    """
    Ingest manga from archive or directory into page images.
    
    Args:
        source: Path to CBZ/PDF/directory
        output_dir: Where to extract images (volume_path / _manga_extracted/)
        volume_id: Volume identifier for logging
        
    Returns:
        (list of page image paths sorted by page number, metadata dict)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if source.is_dir():
        pages = _ingest_from_directory(source, output_dir)
    elif source.suffix.lower() in (".cbz", ".zip"):
        pages = _ingest_from_cbz(source, output_dir)
    elif source.suffix.lower() == ".cbr":
        pages = _ingest_from_cbr(source, output_dir)
    elif source.suffix.lower() == ".pdf":
        pages = _ingest_from_pdf(source, output_dir)
    else:
        raise ValueError(f"Unsupported manga format: {source.suffix}")
    
    metadata = {
        "source": str(source),
        "format": source.suffix.lower() if source.is_file() else "directory",
        "total_pages": len(pages),
        "output_dir": str(output_dir),
    }
    
    logger.info(f"[MANGA] Ingested {len(pages)} pages from {source.name}")
    return pages, metadata


def _ingest_from_directory(source: Path, output_dir: Path) -> List[Path]:
    """Ingest from a directory of images."""
    pages = []
    for img_file in sorted(source.glob("*")):
        if img_file.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            dest = output_dir / img_file.name
            if not dest.exists():
                shutil.copy2(img_file, dest)
            pages.append(dest)
    return pages


def _ingest_from_cbz(source: Path, output_dir: Path) -> List[Path]:
    """Ingest from CBZ (ZIP) archive."""
    pages = []
    with zipfile.ZipFile(source, 'r') as zf:
        for name in sorted(zf.namelist()):
            ext = Path(name).suffix.lower()
            if ext in SUPPORTED_IMAGE_EXTENSIONS:
                # Flatten directory structure
                page_name = Path(name).name
                dest = output_dir / page_name
                if not dest.exists():
                    with zf.open(name) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
                pages.append(dest)
    return pages


def _ingest_from_cbr(source: Path, output_dir: Path) -> List[Path]:
    """Ingest from CBR (RAR) archive. Requires unrar."""
    raise NotImplementedError(
        "CBR support requires 'unrar' package. "
        "Install with: pip install unrar\n"
        "Alternative: Convert CBR to CBZ first."
    )


def _ingest_from_pdf(source: Path, output_dir: Path) -> List[Path]:
    """Ingest from PDF with embedded images. Requires pymupdf."""
    raise NotImplementedError(
        "PDF support requires 'pymupdf' package. "
        "Install with: pip install pymupdf\n"
        "Alternative: Convert PDF to CBZ first."
    )
