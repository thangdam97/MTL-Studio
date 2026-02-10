"""
Image Extractor - Catalogs images from source EPUB.

Language-agnostic extraction of cover images, illustrations,
and kuchie (color plates) from EPUB content.

Now uses PublisherProfileManager for pattern matching instead of
hardcoded regex patterns.
"""

import re
import struct
import imghdr
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .config import IMAGE_EXTENSIONS
from .publisher_profiles.manager import PublisherProfileManager, get_profile_manager


def get_jpeg_dimensions(image_path: Path) -> Tuple[int, int]:
    """
    Extract dimensions from JPEG image.

    Args:
        image_path: Path to JPEG image

    Returns:
        Tuple of (width, height)
    """
    try:
        with open(image_path, 'rb') as f:
            head = f.read(24)
            if len(head) != 24:
                return (0, 0)

            if imghdr.what(image_path) == 'jpeg':
                f.seek(0)
                size = 2
                ftype = 0
                while not 0xc0 <= ftype <= 0xcf:
                    f.seek(size, 1)
                    byte = f.read(1)
                    while ord(byte) == 0xff:
                        byte = f.read(1)
                    ftype = ord(byte)
                    size = struct.unpack('>H', f.read(2))[0] - 2
                f.seek(1, 1)
                height, width = struct.unpack('>HH', f.read(4))
                return (width, height)
    except Exception:
        pass

    return (0, 0)


def detect_orientation(image_path: Path) -> str:
    """
    Detect if image is portrait or landscape.

    Args:
        image_path: Path to image file

    Returns:
        'portrait' or 'landscape'
    """
    try:
        width, height = get_jpeg_dimensions(image_path)
        if width > 0 and height > 0:
            return 'landscape' if width > height else 'portrait'
    except Exception:
        pass

    return 'portrait'


@dataclass
class ImageInfo:
    """Information about an extracted image."""
    filename: str
    filepath: Path
    image_type: str  # cover, kuchie, illustration, insert
    width: int = 0
    height: int = 0
    orientation: str = "portrait"
    source_chapter: Optional[str] = None


class ImageExtractor:
    """
    Extracts and catalogs images from EPUB content.

    Uses PublisherProfileManager for publisher-specific pattern matching
    instead of hardcoded patterns.
    """

    # Legacy patterns kept for backwards compatibility
    # These are now loaded from publisher_database.json via ProfileManager
    GAIJI_PATTERN = re.compile(r'^gaiji[-_].*\.(jpe?g|png)$', re.IGNORECASE)
    KUCHIE_PATTERN = re.compile(r'^(o_)?(?:kuchie[-_]\d+|k\d+|p00[1-9])(-\d+)?\.jpe?g$', re.IGNORECASE)
    
    # Double-spread illustration pattern (e.g., p016-p017.jpg, p001-p002.jpg)
    DOUBLE_SPREAD_PATTERN = re.compile(
        r'^(o_)?p\d{3,4}-p\d{3,4}\.jpe?g$',
        re.IGNORECASE
    )
    
    ILLUSTRATION_PATTERN = re.compile(
        r'^(o_)?(?:i[-_]\d+|img[-_]p\d+|p\d+)\.jpe?g$',
        re.IGNORECASE
    )
    COVER_PATTERN = re.compile(
        r'^(o_|i[-_])?'
        r'(?:cover|hyoushi|hyousi|frontcover|front[-_]cover|h1)'
        r'\.(jpe?g|png)$',
        re.IGNORECASE
    )

    @staticmethod
    def normalize_filename(image_type: str, index: int, original_ext: str = ".jpg") -> str:
        """
        Generate standardized filename based on image type.

        Args:
            image_type: 'cover', 'kuchie', or 'illustration'
            index: Sequential index (0-based)
            original_ext: Original file extension (default: .jpg)

        Returns:
            Normalized filename (e.g., 'kuchie-001.jpg', 'illust-023.jpg').
            Illustration normalization is legacy-only; extraction now preserves
            original illustration filenames.
        """
        if image_type == "cover":
            return f"cover{original_ext}"
        elif image_type == "kuchie":
            return f"kuchie-{index+1:03d}{original_ext}"
        elif image_type == "illustration":
            return f"illust-{index+1:03d}{original_ext}"
        return f"unknown-{index+1:03d}{original_ext}"

    def __init__(self, content_dir: Path, publisher: str = None):
        """
        Initialize image extractor.

        Args:
            content_dir: EPUB content directory (contains image/ folder)
            publisher: Publisher name for pattern matching (optional)
        """
        self.content_dir = Path(content_dir)
        self.image_dir = self._find_image_dir()
        self.publisher = publisher

        # Get profile manager for pattern matching
        self._profile_manager = get_profile_manager()

    def _find_image_dir(self) -> Optional[Path]:
        """Find the image directory in content."""
        candidates = ["image", "images", "Images", "img", "OEBPS/image"]
        for candidate in candidates:
            img_dir = self.content_dir / candidate
            if img_dir.is_dir():
                return img_dir
        return None

    def catalog_all(self) -> Dict[str, List[ImageInfo]]:
        """
        Catalog all images by type.

        Returns:
            Dictionary with keys: cover, kuchie, illustrations
        """
        catalog = {
            "cover": [],
            "kuchie": [],
            "illustrations": [],
        }

        if not self.image_dir:
            return catalog

        for img_path in self.image_dir.iterdir():
            if img_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            info = self._classify_image(img_path)
            if info:
                if info.image_type == "cover":
                    catalog["cover"].append(info)
                elif info.image_type == "kuchie":
                    catalog["kuchie"].append(info)
                elif info.image_type == "illustration":
                    catalog["illustrations"].append(info)

        # Sort by filename
        catalog["kuchie"].sort(key=lambda x: x.filename)
        catalog["illustrations"].sort(key=lambda x: x.filename)

        return catalog

    def _classify_image(self, img_path: Path) -> Optional[ImageInfo]:
        """
        Classify an image by its filename using publisher profile patterns.

        Uses PublisherProfileManager for pattern matching, falling back
        to legacy patterns if no match found.

        Returns None for:
        - Gaiji (special character) images
        - Unrecognized patterns
        """
        filename = img_path.name

        # Use profile manager for pattern matching
        match = self._profile_manager.match_image(filename, self.publisher)

        if match.matched:
            if match.image_type == "exclude":
                # Excluded images (gaiji, etc.)
                return None

            width, height = get_jpeg_dimensions(img_path)
            return ImageInfo(
                filename=filename,
                filepath=img_path,
                image_type=match.image_type,
                width=width,
                height=height,
                orientation=detect_orientation(img_path)
            )

        # No match found - image will be skipped but mismatch is tracked
        # by the profile manager for later review
        return None

    def _classify_image_legacy(self, img_path: Path) -> Optional[ImageInfo]:
        """
        Legacy classification using hardcoded patterns.
        Kept for backwards compatibility.
        """
        filename = img_path.name

        # Skip gaiji images
        if self.GAIJI_PATTERN.match(filename):
            return None

        # Check cover
        if self.COVER_PATTERN.match(filename):
            width, height = get_jpeg_dimensions(img_path)
            return ImageInfo(
                filename=filename,
                filepath=img_path,
                image_type="cover",
                width=width,
                height=height,
                orientation=detect_orientation(img_path)
            )

        # Check kuchie
        if self.KUCHIE_PATTERN.match(filename):
            width, height = get_jpeg_dimensions(img_path)
            return ImageInfo(
                filename=filename,
                filepath=img_path,
                image_type="kuchie",
                width=width,
                height=height,
                orientation=detect_orientation(img_path)
            )

        # Check double-spread illustration (e.g., p016-p017.jpg)
        if self.DOUBLE_SPREAD_PATTERN.match(filename):
            width, height = get_jpeg_dimensions(img_path)
            return ImageInfo(
                filename=filename,
                filepath=img_path,
                image_type="illustration",
                width=width,
                height=height,
                orientation="landscape"  # Double-spreads are always landscape
            )

        # Check illustration
        if self.ILLUSTRATION_PATTERN.match(filename):
            width, height = get_jpeg_dimensions(img_path)
            return ImageInfo(
                filename=filename,
                filepath=img_path,
                image_type="illustration",
                width=width,
                height=height,
                orientation=detect_orientation(img_path)
            )

        return None

    def copy_to_assets(self, output_dir: Path, exclude_files: set = None) -> Tuple[Dict[str, Path], Dict[str, str]]:
        """
        Copy cataloged images to assets directory.

        Args:
            output_dir: Base assets directory
            exclude_files: Set of filenames to exclude from copying (e.g., spine-extracted kuchie)

        Returns:
            Tuple of:
            - Dictionary mapping image type to output directory
            - Dictionary mapping original filename to output filename
        """
        if exclude_files is None:
            exclude_files = set()
        
        catalog = self.catalog_all()
        
        # Filter out excluded files from all categories
        if exclude_files:
            catalog["cover"] = [img for img in catalog["cover"] if img.filename not in exclude_files]
            catalog["kuchie"] = [img for img in catalog["kuchie"] if img.filename not in exclude_files]
            catalog["illustrations"] = [img for img in catalog["illustrations"] if img.filename not in exclude_files]
        output_paths = {}
        filename_mapping = {}  # original -> normalized

        # Copy cover
        if catalog["cover"]:
            cover_dir = output_dir
            cover_dir.mkdir(parents=True, exist_ok=True)
            for img in catalog["cover"]:
                # Preserve original extension for non-JPG covers
                original_ext = Path(img.filename).suffix.lower()
                dest_filename = f"cover{original_ext if original_ext in ['.jpg', '.jpeg', '.png'] else '.jpg'}"
                dest = cover_dir / dest_filename
                shutil.copy2(img.filepath, dest)
                output_paths["cover"] = dest
                filename_mapping[img.filename] = dest_filename
                print(f"[OK] Copied cover: {img.filename} -> {dest_filename}")
        else:
            # Fallback: Check if OPF metadata points to a cover we missed
            print("[WARNING] No cover detected by pattern matching. Check OPF metadata for cover reference.")

        # Copy kuchie - SKIP if spine-based extraction is being used (exclude_files provided)
        # The spine-based system handles kuchie extraction and copying directly
        if catalog["kuchie"] and not exclude_files:
            kuchie_dir = output_dir / "kuchie"
            kuchie_dir.mkdir(parents=True, exist_ok=True)
            for i, img in enumerate(catalog["kuchie"]):
                # Store original filename before normalization
                original_filename = img.filename
                original_ext = Path(img.filename).suffix
                
                # Check if filename already matches our naming pattern (kuchie-NNN.jpg or kuchie-NNN-NNN.jpg)
                # Pattern: kuchie-001.jpg, kuchie-002-003.jpg, etc.
                if re.match(r'^kuchie-\d{3}(?:-\d{3})?\.jpe?g$', original_filename, re.IGNORECASE):
                    # Already matches our convention - preserve as-is
                    normalized_name = original_filename
                else:
                    # Normalize filename
                    normalized_name = self.normalize_filename("kuchie", i, original_ext)
                
                dest = kuchie_dir / normalized_name
                shutil.copy2(img.filepath, dest)
                # Track mapping
                filename_mapping[original_filename] = normalized_name
                # Update ImageInfo with normalized filename
                img.filename = normalized_name
                print(f"[OK] Copied kuchie: {original_filename} -> {normalized_name}")
            output_paths["kuchie"] = kuchie_dir

        # Copy illustrations with ORIGINAL filenames.
        # Markdown placeholders now use original filenames, so do not normalize
        # to illust-XXX anymore.
        if catalog["illustrations"]:
            illust_dir = output_dir / "illustrations"
            illust_dir.mkdir(parents=True, exist_ok=True)
            print(f"[INFO] Processing {len(catalog['illustrations'])} illustrations...")
            for img in catalog["illustrations"]:
                original_filename = img.filename
                dest = illust_dir / original_filename
                shutil.copy2(img.filepath, dest)
                # Identity mapping keeps placeholders intact and avoids removals.
                filename_mapping[original_filename] = original_filename
            print(f"[OK] Copied {len(catalog['illustrations'])} illustrations")
            output_paths["illustrations"] = illust_dir
        else:
            print(f"[WARNING] No illustrations detected. Check if image filenames match expected patterns.")

        # Report any mismatches
        if self._profile_manager.has_mismatches():
            mismatches = self._profile_manager.get_session_mismatches()
            print(f"\n[WARNING] {len(mismatches)} images did not match any known pattern:")
            for m in mismatches[:5]:
                print(f"  - {m.filename}")
                if m.suggested_type:
                    print(f"    Suggested: {m.suggested_type}")
            if len(mismatches) > 5:
                print(f"  ... and {len(mismatches) - 5} more")

        return output_paths, filename_mapping

    def get_mismatches(self) -> List:
        """Get any unmatched images from this session."""
        return self._profile_manager.get_session_mismatches()

    def save_mismatches(self, epub_name: str, publisher_text: str) -> None:
        """Save mismatches for later review."""
        self._profile_manager.save_unconfirmed_patterns(
            epub_name, publisher_text, self.publisher
        )


def catalog_images(content_dir: Path, publisher: str = None) -> Dict[str, List[ImageInfo]]:
    """
    Main function to catalog images from EPUB.

    Args:
        content_dir: EPUB content directory
        publisher: Publisher name for pattern matching (optional)

    Returns:
        Dictionary of images by type
    """
    extractor = ImageExtractor(content_dir, publisher)
    return extractor.catalog_all()


def extract_images_to_assets(
    content_dir: Path,
    assets_dir: Path,
    publisher: str = None
) -> Tuple[Dict[str, Path], Dict[str, str]]:
    """
    Extract images from EPUB to assets directory.

    Args:
        content_dir: EPUB content directory
        assets_dir: Destination assets directory
        publisher: Publisher name for pattern matching (optional)

    Returns:
        Tuple of:
        - Dictionary mapping image type to output path
        - Dictionary mapping original filename to normalized filename
    """
    extractor = ImageExtractor(content_dir, publisher)
    return extractor.copy_to_assets(assets_dir)
