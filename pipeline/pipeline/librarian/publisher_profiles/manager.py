"""
Publisher Profile Manager - Runtime pattern loading and matching.

Manages publisher-specific patterns for:
- Image classification (cover, kuchie, illustration)
- Content structure handling (TOC, chapter detection)
- Publisher detection from OPF metadata
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PatternMatch:
    """Result of pattern matching."""
    matched: bool
    image_type: Optional[str] = None  # cover, kuchie, illustration, exclude
    pattern_used: Optional[str] = None
    publisher: Optional[str] = None
    confidence: str = "unmatched"  # confirmed, fallback, unmatched


@dataclass
class MismatchReport:
    """Report for unmatched files."""
    filename: str
    suggested_type: Optional[str] = None
    suggested_pattern: Optional[str] = None
    reason: str = ""


@dataclass
class ContentConfig:
    """Content structure configuration for a publisher."""
    toc_handling: str = "standard"  # standard, spine_fallback, per_file, auto
    toc_min_entries: int = 3  # Minimum TOC entries before falling back
    chapter_merging: bool = False
    filename_pattern: Optional[str] = None

    # Chapter detection settings (for spine_fallback mode)
    chapter_detection_method: str = "content_scan"  # content_scan, filename, none
    chapter_title_patterns: List[str] = field(default_factory=list)
    fallback_chapter_title: str = "Chapter {n}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentConfig':
        """Create ContentConfig from dictionary."""
        chapter_detection = data.get("chapter_detection", {})
        return cls(
            toc_handling=data.get("toc_handling", "standard"),
            toc_min_entries=data.get("toc_min_entries", 3),
            chapter_merging=data.get("chapter_merging", False),
            filename_pattern=data.get("filename_pattern"),
            chapter_detection_method=chapter_detection.get("method", "content_scan"),
            chapter_title_patterns=chapter_detection.get("title_patterns", []),
            fallback_chapter_title=chapter_detection.get("fallback_title", "Chapter {n}"),
        )


@dataclass
class PublisherProfile:
    """Complete profile for a publisher."""
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    country: str = "JP"
    confidence: str = "confirmed"

    # Image patterns by type
    image_patterns: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Content structure config
    content_config: ContentConfig = field(default_factory=ContentConfig)

    # Compiled regex patterns (populated at load time)
    _compiled_patterns: Dict[str, List[re.Pattern]] = field(default_factory=dict, repr=False)

    def compile_patterns(self) -> None:
        """Compile regex patterns for performance."""
        self._compiled_patterns = {}

        for image_type in ["exclude", "cover", "kuchie", "illustration"]:
            self._compiled_patterns[image_type] = []
            for pattern_def in self.image_patterns.get(image_type, []):
                flags = 0
                if "i" in pattern_def.get("flags", ""):
                    flags |= re.IGNORECASE

                try:
                    compiled = re.compile(pattern_def["pattern"], flags)
                    self._compiled_patterns[image_type].append(compiled)
                except re.error as e:
                    print(f"[WARNING] Invalid pattern '{pattern_def['pattern']}': {e}")

    def match_image(self, filename: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Match filename against this publisher's patterns.

        Returns:
            Tuple of (matched, image_type, pattern_used)
        """
        # Check exclusion first
        for pattern in self._compiled_patterns.get("exclude", []):
            if pattern.match(filename):
                return (True, "exclude", pattern.pattern)

        # Check each type in priority order
        for image_type in ["cover", "kuchie", "illustration"]:
            for pattern in self._compiled_patterns.get(image_type, []):
                if pattern.match(filename):
                    return (True, image_type, pattern.pattern)

        return (False, None, None)


class PublisherProfileManager:
    """
    Manages publisher profiles and pattern matching.

    Responsibilities:
    - Load/save publisher database
    - Detect publisher from OPF metadata
    - Match image filenames to types
    - Provide content structure configuration
    - Track and report mismatches
    """

    # Hard exclusions always applied regardless of publisher profile.
    # These assets are non-story noise and must never enter chapter illustrations.
    HARD_EXCLUDE_IMAGE_PATTERNS: Tuple[re.Pattern, ...] = (
        re.compile(r'^gaiji\d*\.(jpe?g|png)$', re.IGNORECASE),
        re.compile(r'^gaiji[-_].*\.(jpe?g|png)$', re.IGNORECASE),
        re.compile(r'^dx_logo\.(jpe?g|png)$', re.IGNORECASE),
        re.compile(r'^fan[-_]?letter\.(jpe?g|png)$', re.IGNORECASE),
        re.compile(r'^(?:i[-_])?bookwalker(?:[-_].*)?\.(jpe?g|png)$', re.IGNORECASE),
        re.compile(r'^m[-_]?\d{2,4}\.(jpe?g|png)$', re.IGNORECASE),
        re.compile(r'^midashi\d+\.(jpe?g|png)$', re.IGNORECASE),
    )

    def __init__(self, profiles_dir: Optional[Path] = None):
        """
        Initialize manager.

        Args:
            profiles_dir: Directory containing JSON profiles.
                         Defaults to this module's directory.
        """
        self.profiles_dir = Path(profiles_dir) if profiles_dir else Path(__file__).parent
        self.db_path = self.profiles_dir / "publisher_database.json"
        self.unconfirmed_path = self.profiles_dir / "unconfirmed_patterns.json"

        self._database: Dict[str, Any] = {}
        self._profiles: Dict[str, PublisherProfile] = {}
        self._fallback_profile: Optional[PublisherProfile] = None
        self._session_mismatches: List[MismatchReport] = []

        self.load_database()

    def load_database(self) -> None:
        """Load publisher database and compile patterns."""
        if self.db_path.exists():
            with open(self.db_path, 'r', encoding='utf-8') as f:
                self._database = json.load(f)
        else:
            print(f"[WARNING] Publisher database not found at {self.db_path}")
            print(f"          Creating default database...")
            self._database = self._create_default_database()
            self.save_database()

        self._load_profiles()

    def save_database(self) -> None:
        """Save publisher database to disk."""
        self._database["last_updated"] = datetime.now().isoformat()
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self._database, f, indent=2, ensure_ascii=False)

    def _load_profiles(self) -> None:
        """
        Load and compile all publisher profiles.
        
        Priority:
        1. Individual JSON files (overlap.json, kadokawa.json, etc.)
        2. Fallback to publisher_database.json entries
        """
        self._profiles = {}

        for pub_name, pub_data in self._database.get("publishers", {}).items():
            # Check for individual publisher JSON file first
            json_filename = pub_name.lower().replace(" ", "_") + ".json"
            individual_json_path = self.profiles_dir / json_filename
            
            if individual_json_path.exists():
                # Load from individual JSON file (PRIORITY)
                try:
                    with open(individual_json_path, 'r', encoding='utf-8') as f:
                        individual_data = json.load(f)
                    
                    # Convert individual JSON format to database format
                    image_patterns_converted = {}
                    for img_type, type_data in individual_data.get("image_patterns", {}).items():
                        raw_type = img_type.lower()
                        # Normalize keys from per-publisher JSON:
                        # - illustrations -> illustration
                        # - special -> exclude (non-story assets)
                        if raw_type in {"special", "exclude", "excludes", "excluded"}:
                            normalized_type = "exclude"
                        elif raw_type.endswith('s') and raw_type != 'kuchie':
                            normalized_type = raw_type.rstrip('s')
                        else:
                            normalized_type = raw_type
                        
                        patterns_list = image_patterns_converted.setdefault(normalized_type, [])
                        start_priority = len(patterns_list)
                        for i, pattern_str in enumerate(type_data.get("patterns", [])):
                            patterns_list.append({
                                "pattern": pattern_str,
                                "flags": "i",
                                "priority": start_priority + i + 1
                            })
                    
                    profile = PublisherProfile(
                        canonical_name=individual_data.get("publisher", pub_name),
                        aliases=[individual_data.get("publisher", pub_name)] + 
                                ([individual_data.get("publisher_ja")] if individual_data.get("publisher_ja") else []),
                        country=individual_data.get("country", "JP"),
                        confidence="confirmed",
                        image_patterns=image_patterns_converted,
                        content_config=ContentConfig.from_dict(individual_data.get("content_structure", {})),
                    )
                    print(f"[OK] Loaded {pub_name} from {json_filename}")
                except Exception as e:
                    print(f"[WARNING] Failed to load {json_filename}: {e}")
                    print(f"          Falling back to publisher_database.json for {pub_name}")
                    # Fall through to database loading
                    profile = PublisherProfile(
                        canonical_name=pub_name,
                        aliases=pub_data.get("aliases", []),
                        country=pub_data.get("country", "JP"),
                        confidence=pub_data.get("confidence", "confirmed"),
                        image_patterns=pub_data.get("image_patterns", {}),
                        content_config=ContentConfig.from_dict(pub_data.get("content_patterns", {})),
                    )
            else:
                # Load from database (FALLBACK)
                profile = PublisherProfile(
                    canonical_name=pub_name,
                    aliases=pub_data.get("aliases", []),
                    country=pub_data.get("country", "JP"),
                    confidence=pub_data.get("confidence", "confirmed"),
                    image_patterns=pub_data.get("image_patterns", {}),
                    content_config=ContentConfig.from_dict(pub_data.get("content_patterns", {})),
                )
            
            profile.compile_patterns()
            self._profiles[pub_name] = profile

        # Load fallback profile
        fallback_data = self._database.get("fallback_patterns", {})
        self._fallback_profile = PublisherProfile(
            canonical_name="__fallback__",
            aliases=[],
            image_patterns=fallback_data.get("image_patterns", {}),
            content_config=ContentConfig.from_dict(fallback_data.get("content_patterns", {})),
        )
        self._fallback_profile.compile_patterns()

        print(f"[OK] Loaded {len(self._profiles)} publisher profiles")

    # =========================================================================
    # PUBLISHER DETECTION
    # =========================================================================

    def detect_publisher(self, opf_publisher_text: str) -> Tuple[str, str, Optional[PublisherProfile]]:
        """
        Detect canonical publisher name from OPF metadata.

        Args:
            opf_publisher_text: Raw publisher text from dc:publisher

        Returns:
            Tuple of (canonical_name, confidence, profile)
            confidence is 'confirmed' or 'unknown'
        """
        if not opf_publisher_text:
            return ("Unknown", "unknown", self._fallback_profile)

        text_lower = opf_publisher_text.lower()

        for pub_name, profile in self._profiles.items():
            for alias in profile.aliases:
                if alias.lower() in text_lower:
                    return (pub_name, "confirmed", profile)

        # No match found
        self._report_unknown_publisher(opf_publisher_text)
        return (opf_publisher_text, "unknown", self._fallback_profile)

    def _report_unknown_publisher(self, publisher_text: str) -> None:
        """Log unknown publisher for potential addition."""
        print(f"[WARNING] Unknown publisher: '{publisher_text}'")
        print(f"          Using fallback patterns. Consider adding to publisher_database.json")

    def get_profile(self, publisher_name: str) -> Optional[PublisherProfile]:
        """Get profile by canonical name."""
        return self._profiles.get(publisher_name, self._fallback_profile)

    # =========================================================================
    # IMAGE PATTERN MATCHING
    # =========================================================================

    def _get_hard_exclude_pattern(self, filename: str) -> Optional[str]:
        """Return matching hard-exclude pattern, if any."""
        for pattern in self.HARD_EXCLUDE_IMAGE_PATTERNS:
            if pattern.match(filename):
                return pattern.pattern
        return None

    def match_image(self, filename: str, publisher: str = None) -> PatternMatch:
        """
        Match image filename to type using publisher patterns.

        Args:
            filename: Image filename (e.g., 'i-003.jpg')
            publisher: Publisher name (uses fallback if None/unknown)

        Returns:
            PatternMatch with classification result
        """
        hard_pattern = self._get_hard_exclude_pattern(filename)
        if hard_pattern:
            return PatternMatch(
                matched=True,
                image_type="exclude",
                pattern_used=hard_pattern,
                publisher="hard_filter",
                confidence="confirmed"
            )

        # Get profile to use
        profile = self._profiles.get(publisher, self._fallback_profile)
        pattern_source = publisher if publisher in self._profiles else "fallback"

        # Match against profile
        matched, image_type, pattern_used = profile.match_image(filename)

        if matched:
            return PatternMatch(
                matched=True,
                image_type=image_type,
                pattern_used=pattern_used,
                publisher=pattern_source,
                confidence="confirmed" if pattern_source != "fallback" else "fallback"
            )

        # No match - report mismatch
        self._track_mismatch(filename, publisher)

        return PatternMatch(
            matched=False,
            image_type=None,
            pattern_used=None,
            publisher=pattern_source,
            confidence="unmatched"
        )

    def is_excluded_image(self, filename: str, publisher: str = None) -> bool:
        """
        Check whether filename matches exclusion patterns for a publisher.

        Unlike match_image(), this method does not track mismatches.
        """
        if self._get_hard_exclude_pattern(filename):
            return True

        profile = self._profiles.get(publisher, self._fallback_profile)
        for pattern in profile._compiled_patterns.get("exclude", []):
            if pattern.match(filename):
                return True
        return False

    def _track_mismatch(self, filename: str, publisher: str) -> None:
        """Track unmatched filename for later review."""
        suggested = self._suggest_type(filename)

        report = MismatchReport(
            filename=filename,
            suggested_type=suggested[0],
            suggested_pattern=suggested[1],
            reason=suggested[2]
        )

        self._session_mismatches.append(report)

    def _suggest_type(self, filename: str) -> Tuple[Optional[str], Optional[str], str]:
        """
        Suggest image type based on heuristics.

        Returns:
            Tuple of (suggested_type, suggested_pattern, reason)
        """
        lower = filename.lower()

        # Cover heuristics
        if "cover" in lower or "hyoushi" in lower:
            return ("cover", f"^.*cover.*$", "Contains 'cover' keyword")

        # Kuchie heuristics
        if "kuchie" in lower or lower.startswith("k0"):
            return ("kuchie", None, "Contains 'kuchie' or 'k0' prefix")

        # Illustration heuristics
        if "illust" in lower or lower.startswith("i-") or lower.startswith("i_"):
            base = filename.rsplit('.', 1)[0]
            if len(base) > 1:
                pattern = f"^{re.escape(base[:-1])}\\d+\\.jpe?g$"
                return ("illustration", pattern, "Contains illustration indicator")

        # Generic numbered pattern
        if re.match(r'^[a-z]?\d+\.jpe?g$', lower, re.IGNORECASE):
            return ("illustration", None, "Numbered filename pattern")

        # Page-number pattern (p###.jpg)
        if re.match(r'^p\d{3}\.jpe?g$', lower, re.IGNORECASE):
            return ("illustration", r"^p\d{3}\.jpe?g$", "Page number pattern")

        return (None, None, "No heuristic match")

    # =========================================================================
    # CONTENT STRUCTURE
    # =========================================================================

    def get_content_config(self, publisher: str = None) -> ContentConfig:
        """
        Get content structure configuration for publisher.

        Args:
            publisher: Publisher name (uses fallback if None/unknown)

        Returns:
            ContentConfig for the publisher
        """
        profile = self._profiles.get(publisher, self._fallback_profile)
        return profile.content_config

    def get_chapter_split_config(self, publisher: str = None) -> dict:
        """
        Get chapter splitting configuration for publisher.
        
        Args:
            publisher: Publisher name (uses fallback if None/unknown)
        
        Returns:
            Chapter splitting config dict (empty if not defined)
        """
        if not publisher or publisher not in self._database.get("publishers", {}):
            return {}
        
        # Access raw publisher data from database
        pub_data = self._database["publishers"].get(publisher, {})
        return pub_data.get("chapter_splitting", {})

    def get_heading_split_config(self, publisher: str = None) -> Optional[dict]:
        """
        Get heading-based chapter splitting config for publishers like Kodansha.
        
        Args:
            publisher: Publisher name (uses fallback if None/unknown)
        
        Returns:
            Dict with 'heading_patterns' and 'split_on_heading' if method is 'heading_split',
            None otherwise
        """
        if not publisher or publisher not in self._database.get("publishers", {}):
            return None
        
        # Access raw publisher data from database
        pub_data = self._database["publishers"].get(publisher, {})
        content_patterns = pub_data.get("content_patterns", {})
        chapter_detection = content_patterns.get("chapter_detection", {})
        
        # Check if this publisher uses heading_split method
        if chapter_detection.get("method") == "heading_split":
            return {
                "heading_patterns": chapter_detection.get("heading_patterns", []),
                "split_on_heading": chapter_detection.get("split_on_heading", True),
                "note": chapter_detection.get("note", "")
            }
        
        return None

    def should_use_spine_fallback(self, publisher: str, toc_entry_count: int) -> bool:
        """
        Determine if spine-based fallback should be used.

        Args:
            publisher: Publisher name
            toc_entry_count: Number of entries in TOC

        Returns:
            True if spine fallback should be used
        """
        config = self.get_content_config(publisher)

        if config.toc_handling == "spine_fallback":
            return toc_entry_count < config.toc_min_entries
        elif config.toc_handling == "auto":
            # Auto-detect: use fallback if TOC seems insufficient
            return toc_entry_count < 3

        return False

    def get_chapter_title_patterns(self, publisher: str = None) -> List[re.Pattern]:
        """
        Get compiled chapter title patterns for content scanning.

        Args:
            publisher: Publisher name

        Returns:
            List of compiled regex patterns for chapter titles
        """
        config = self.get_content_config(publisher)
        patterns = []

        for pattern_str in config.chapter_title_patterns:
            try:
                patterns.append(re.compile(pattern_str, re.IGNORECASE))
            except re.error:
                pass

        # Always include baseline markers. Some EPUBs expose only coarse chapter-level
        # TOC entries while actual story units are episode markers like 第X話.
        baseline_patterns = [
            r'^第[一二三四五六七八九十百千]+章',  # Japanese chapter (kanji numbers)
            r'^第\d+章',  # Japanese chapter (arabic numbers)
            r'^第[一二三四五六七八九十百千]+話',  # Japanese episode (kanji numbers)
            r'^第\d+話',  # Japanese episode (arabic numbers)
            r'^Chapter\s*\d+',  # English chapter
            r'^プロローグ',  # Prologue (JP)
            r'^エピローグ',  # Epilogue (JP)
            r'^幕間',  # Interlude (JP)
            r'^あとがき',  # Afterword (JP)
            r'^Prologue',
            r'^Epilogue',
            r'^Interlude',
        ]
        configured = set(config.chapter_title_patterns or [])
        for p in baseline_patterns:
            if p in configured:
                continue
            try:
                patterns.append(re.compile(p, re.IGNORECASE))
            except re.error:
                pass

        return patterns

    # =========================================================================
    # MISMATCH REPORTING
    # =========================================================================

    def get_session_mismatches(self) -> List[MismatchReport]:
        """Get all mismatches from current session."""
        return self._session_mismatches

    def clear_session_mismatches(self) -> None:
        """Clear session mismatch tracking."""
        self._session_mismatches = []

    def has_mismatches(self) -> bool:
        """Check if there are any mismatches in current session."""
        return len(self._session_mismatches) > 0

    def save_unconfirmed_patterns(
        self,
        source_epub: str,
        publisher_text: str,
        publisher_canonical: str = None
    ) -> None:
        """
        Save session mismatches to unconfirmed patterns file.

        Args:
            source_epub: Name of source EPUB file
            publisher_text: Raw publisher text from OPF
            publisher_canonical: Detected canonical name (if any)
        """
        if not self._session_mismatches:
            return

        # Load existing unconfirmed
        unconfirmed = {"version": "1.0", "patterns": []}
        if self.unconfirmed_path.exists():
            try:
                with open(self.unconfirmed_path, 'r', encoding='utf-8') as f:
                    unconfirmed = json.load(f)
            except json.JSONDecodeError:
                pass

        # Generate new entry
        entry = {
            "id": f"unc_{len(unconfirmed['patterns']) + 1:03d}",
            "detected_at": datetime.now().isoformat(),
            "source_epub": source_epub,
            "publisher_from_opf": publisher_text,
            "publisher_detected": publisher_canonical or "Unknown",
            "unmatched_images": [
                {
                    "filename": m.filename,
                    "suggested_type": m.suggested_type,
                    "suggested_pattern": m.suggested_pattern,
                    "reason": m.reason
                }
                for m in self._session_mismatches
            ],
            "status": "pending_review"
        }

        unconfirmed["patterns"].append(entry)

        with open(self.unconfirmed_path, 'w', encoding='utf-8') as f:
            json.dump(unconfirmed, f, indent=2, ensure_ascii=False)

        print(f"[INFO] Saved {len(self._session_mismatches)} unconfirmed patterns")
        print(f"       Review: {self.unconfirmed_path}")

    # =========================================================================
    # PATTERN CONFIRMATION
    # =========================================================================

    def add_publisher(
        self,
        canonical_name: str,
        aliases: List[str],
        country: str = "JP"
    ) -> bool:
        """
        Add a new publisher to the database.

        Args:
            canonical_name: Canonical publisher name
            aliases: List of name variants
            country: Country code

        Returns:
            True if added successfully
        """
        if canonical_name in self._database.get("publishers", {}):
            print(f"[WARNING] Publisher '{canonical_name}' already exists")
            return False

        self._database.setdefault("publishers", {})[canonical_name] = {
            "canonical_name": canonical_name,
            "aliases": aliases,
            "country": country,
            "confidence": "confirmed",
            "image_patterns": {
                "exclude": [],
                "cover": [],
                "kuchie": [],
                "illustration": []
            },
            "content_patterns": {
                "toc_handling": "standard",
                "chapter_merging": False
            }
        }

        self.save_database()
        self._load_profiles()

        print(f"[OK] Added publisher: {canonical_name}")
        return True

    def add_pattern(
        self,
        publisher: str,
        image_type: str,
        pattern: str,
        note: str = None
    ) -> bool:
        """
        Add a confirmed pattern to the database.

        Args:
            publisher: Publisher canonical name
            image_type: cover, kuchie, illustration, or exclude
            pattern: Regex pattern string
            note: Optional note about the pattern

        Returns:
            True if added successfully
        """
        if publisher not in self._database.get("publishers", {}):
            print(f"[ERROR] Unknown publisher: {publisher}")
            return False

        if image_type not in ["cover", "kuchie", "illustration", "exclude"]:
            print(f"[ERROR] Invalid image type: {image_type}")
            return False

        # Validate pattern compiles
        try:
            re.compile(pattern)
        except re.error as e:
            print(f"[ERROR] Invalid regex: {e}")
            return False

        # Add to database
        pub_patterns = self._database["publishers"][publisher].setdefault(
            "image_patterns", {}
        )
        type_patterns = pub_patterns.setdefault(image_type, [])

        new_pattern = {
            "pattern": pattern,
            "flags": "i",
            "priority": len(type_patterns) + 1
        }
        if note:
            new_pattern["note"] = note

        type_patterns.append(new_pattern)

        # Save and reload
        self.save_database()
        self._load_profiles()

        print(f"[OK] Added pattern to {publisher}/{image_type}: {pattern}")
        return True

    # =========================================================================
    # UTILITY
    # =========================================================================

    def list_publishers(self) -> List[str]:
        """List all known publishers."""
        return list(self._profiles.keys())

    def get_publisher_info(self, publisher: str) -> Optional[Dict[str, Any]]:
        """Get full publisher data from database."""
        return self._database.get("publishers", {}).get(publisher)

    def _create_default_database(self) -> Dict[str, Any]:
        """Create default database with all known patterns."""
        return {
            "$schema": "./publisher_schema.json",
            "version": "2.0",
            "last_updated": datetime.now().isoformat(),

            "publishers": {
                "KADOKAWA": {
                    "canonical_name": "KADOKAWA",
                    "aliases": [
                        "KADOKAWA", "角川", "株式会社KADOKAWA",
                        "KADOKAWA CORPORATION", "株式会社ＫＡＤＯＫＡＷＡ"
                    ],
                    "country": "JP",
                    "confidence": "confirmed",
                    "image_patterns": {
                        "exclude": [
                            {"pattern": "^gaiji[-_].*\\.(jpe?g|png)$", "flags": "i", "note": "Special character glyphs"}
                        ],
                        "cover": [
                            {"pattern": "^(i[-_])?cover\\.(jpe?g|png)$", "flags": "i", "priority": 1},
                            {"pattern": "^allcover[-_]\\d+\\.jpe?g$", "flags": "i", "priority": 2}
                        ],
                        "kuchie": [
                            {"pattern": "^kuchie[-_]\\d+\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^k\\d{3}\\.jpe?g$", "flags": "i", "priority": 2},
                            {"pattern": "^p00[1-9]\\.jpe?g$", "flags": "i", "priority": 3, "note": "p001-p009 reserved for kuchie"}
                        ],
                        "illustration": [
                            {"pattern": "^i[-_]\\d+\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^p0[1-9]\\d\\.jpe?g$", "flags": "i", "priority": 2, "note": "p010+ are illustrations"},
                            {"pattern": "^p[1-9]\\d+\\.jpe?g$", "flags": "i", "priority": 3}
                        ]
                    },
                    "content_patterns": {
                        "toc_handling": "standard",
                        "chapter_merging": False,
                        "filename_pattern": "\\d+\\.xhtml"
                    }
                },

                "Media Factory": {
                    "canonical_name": "Media Factory",
                    "aliases": [
                        "Media Factory", "メディアファクトリー", "株式会社メディアファクトリー"
                    ],
                    "country": "JP",
                    "confidence": "confirmed",
                    "image_patterns": {
                        "cover": [
                            {"pattern": "^o_hyoushi\\.jpe?g$", "flags": "i", "priority": 1, "note": "hyoushi = cover"},
                            {"pattern": "^cover\\.jpe?g$", "flags": "i", "priority": 2}
                        ],
                        "kuchie": [
                            {"pattern": "^o_kuchie_\\d+\\.jpe?g$", "flags": "i", "priority": 1}
                        ],
                        "illustration": [
                            {"pattern": "^o_p\\d{3,}\\.jpe?g$", "flags": "i", "priority": 1}
                        ]
                    },
                    "content_patterns": {
                        "toc_handling": "standard",
                        "chapter_merging": True,
                        "filename_pattern": "a_\\d+_\\d+\\.xhtml",
                        "nav_structure": "li > span > a"
                    }
                },

                "Overlap": {
                    "canonical_name": "Overlap",
                    "aliases": [
                        "Overlap", "オーバーラップ", "株式会社オーバーラップ"
                    ],
                    "country": "JP",
                    "confidence": "confirmed",
                    "image_patterns": {
                        "cover": [
                            {"pattern": "^cover\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^allcover\\.jpe?g$", "flags": "i", "priority": 2}
                        ],
                        "kuchie": [
                            {"pattern": "^k\\d{3}\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^k\\d{3}[-_]\\d{3}\\.jpe?g$", "flags": "i", "priority": 2, "note": "Spreads like k002-003.jpg"}
                        ],
                        "illustration": [
                            {"pattern": "^m\\d{3}\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^i[-_]\\d+\\.jpe?g$", "flags": "i", "priority": 2}
                        ]
                    },
                    "content_patterns": {
                        "toc_handling": "standard",
                        "chapter_merging": False,
                        "filename_pattern": "chapter\\d+\\.xhtml"
                    }
                },

                "SB Creative": {
                    "canonical_name": "SB Creative",
                    "aliases": [
                        "SB Creative", "SBクリエイティブ", "株式会社SBクリエイティブ", "SBCreative Corp."
                    ],
                    "country": "JP",
                    "confidence": "confirmed",
                    "image_patterns": {
                        "cover": [
                            {"pattern": "^cover\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^P000[a-c]?\\.jpe?g$", "flags": "i", "priority": 2}
                        ],
                        "kuchie": [
                            {"pattern": "^P00[1-9]\\.jpe?g$", "flags": "i", "priority": 1, "note": "Uppercase P"}
                        ],
                        "illustration": [
                            {"pattern": "^P0[1-9]\\d\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^P[1-9]\\d+\\.jpe?g$", "flags": "i", "priority": 2}
                        ]
                    },
                    "content_patterns": {
                        "toc_handling": "standard",
                        "chapter_merging": False
                    }
                },

                "Hifumi Shobo": {
                    "canonical_name": "Hifumi Shobo",
                    "aliases": [
                        "Hifumi Shobo", "一二三書房", "株式会社一二三書房"
                    ],
                    "country": "JP",
                    "confidence": "confirmed",
                    "image_patterns": {
                        "exclude": [
                            {"pattern": "^gaiji[-_].*\\.(jpe?g|png)$", "flags": "i", "note": "Special character glyphs"}
                        ],
                        "cover": [
                            {"pattern": "^cover\\.jpe?g$", "flags": "i", "priority": 1}
                        ],
                        "kuchie": [
                            {"pattern": "^p00[1-5]\\.jpe?g$", "flags": "i", "priority": 1, "note": "p001-p005 are typically kuchie"},
                            {"pattern": "^p002_003\\.jpe?g$", "flags": "i", "priority": 2, "note": "Spread format"}
                        ],
                        "illustration": [
                            {"pattern": "^p0[0-9][6-9]\\.jpe?g$", "flags": "i", "priority": 1},
                            {"pattern": "^p0[1-9]\\d\\.jpe?g$", "flags": "i", "priority": 2},
                            {"pattern": "^p[1-9]\\d{2}\\.jpe?g$", "flags": "i", "priority": 3}
                        ]
                    },
                    "content_patterns": {
                        "toc_handling": "spine_fallback",
                        "toc_min_entries": 3,
                        "chapter_merging": False,
                        "filename_pattern": "p-\\d+\\.xhtml",
                        "chapter_detection": {
                            "method": "content_scan",
                            "title_patterns": [
                                "^第[一二三四五六七八九十百千]+章",
                                "^第\\d+章",
                                "^プロローグ",
                                "^エピローグ",
                                "^幕間",
                                "^あとがき"
                            ],
                            "fallback_title": "Chapter {n}"
                        }
                    }
                },

                "Hobby Japan": {
                    "canonical_name": "Hobby Japan",
                    "aliases": [
                        "Hobby Japan", "ホビージャパン", "株式会社ホビージャパン"
                    ],
                    "country": "JP",
                    "confidence": "confirmed",
                    "image_patterns": {
                        "cover": [
                            {"pattern": "^cover\\.jpe?g$", "flags": "i", "priority": 1}
                        ],
                        "kuchie": [
                            {"pattern": "^kuchie[-_]\\d+\\.jpe?g$", "flags": "i", "priority": 1}
                        ],
                        "illustration": [
                            {"pattern": "^i[-_]\\d+\\.jpe?g$", "flags": "i", "priority": 1}
                        ]
                    },
                    "content_patterns": {
                        "toc_handling": "standard",
                        "chapter_merging": False
                    }
                }
            },

            "fallback_patterns": {
                "description": "Generic patterns used when publisher is unknown",
                "image_patterns": {
                    "exclude": [
                        {"pattern": "^gaiji[-_].*\\.(jpe?g|png)$", "flags": "i"}
                    ],
                    "cover": [
                        {"pattern": "^(o_|i[-_])?cover\\.(jpe?g|png)$", "flags": "i"},
                        {"pattern": "^(o_)?hyoushi\\.(jpe?g|png)$", "flags": "i"},
                        {"pattern": "^frontcover\\.(jpe?g|png)$", "flags": "i"},
                        {"pattern": "^h1\\.(jpe?g|png)$", "flags": "i"}
                    ],
                    "kuchie": [
                        {"pattern": "^(o_)?kuchie[-_]\\d+\\.jpe?g$", "flags": "i"},
                        {"pattern": "^k\\d{3}\\.jpe?g$", "flags": "i"},
                        {"pattern": "^p00[1-9](-\\d+)?\\.jpe?g$", "flags": "i"}
                    ],
                    "illustration": [
                        {"pattern": "^(o_)?i[-_]\\d+\\.jpe?g$", "flags": "i"},
                        {"pattern": "^(o_)?p0[1-9]\\d+\\.jpe?g$", "flags": "i"},
                        {"pattern": "^(o_)?p[1-9]\\d+\\.jpe?g$", "flags": "i"},
                        {"pattern": "^m\\d{3}\\.jpe?g$", "flags": "i"},
                        {"pattern": "^img[-_]p\\d+\\.jpe?g$", "flags": "i"}
                    ]
                },
                "content_patterns": {
                    "toc_handling": "auto",
                    "toc_min_entries": 3,
                    "chapter_merging": False,
                    "chapter_detection": {
                        "method": "content_scan",
                        "title_patterns": [
                            "^第[一二三四五六七八九十百千]+章",
                            "^第\\d+章",
                            "^Chapter\\s*\\d+",
                            "^プロローグ",
                            "^エピローグ",
                            "^幕間",
                            "^あとがき"
                        ],
                        "fallback_title": "Chapter {n}"
                    }
                }
            }
        }


# Singleton instance for convenience
_manager_instance: Optional[PublisherProfileManager] = None


def get_profile_manager() -> PublisherProfileManager:
    """Get singleton instance of PublisherProfileManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PublisherProfileManager()
    return _manager_instance
