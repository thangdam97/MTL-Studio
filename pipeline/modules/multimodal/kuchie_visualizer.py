"""
Kuchie Visualizer - Character Data Extraction from Front-Matter Illustrations.

Works in tandem with the Librarian's Ruby Text Extractor to:
1. Extract character names from kuchie (口絵) color plates using Gemini Vision
2. Cross-reference with ruby annotations from the text
3. Enforce canon names from manifest.json character_profiles

This module bridges the gap between visual OCR and textual ruby annotations,
ensuring character names are consistent across the entire translation.

Architecture:
  - Librarian (Phase 1): Extracts ruby text → character_profiles in manifest.json
  - KuchieVisualizer (Phase 1.6): Extracts visual names from kuchie → cross-validates
  - Multimodal Processor: Uses validated canon names in visual_cache.json
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class KuchieCharacter:
    """Character data extracted from kuchie illustration."""
    
    # OCR-extracted Japanese name
    japanese_name: str = ""
    japanese_reading: str = ""  # Furigana if visible
    
    # Romanized name (from OCR or visual text overlay)
    romanized_name: str = ""
    
    # Validated against manifest.json
    canon_name: str = ""  # Final authoritative name
    canon_full_name: str = ""
    
    # Visual traits
    visual_traits: List[str] = field(default_factory=list)
    
    # Cross-reference
    ruby_match_confidence: float = 0.0
    source_kuchie: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class RubyCanonEntry:
    """Canon name entry from Librarian's ruby extraction."""
    
    kanji: str  # e.g., "東雲凪"
    reading: str  # e.g., "しののめなぎ"
    full_name_en: str  # e.g., "Shinonome Nagi"
    nickname: str  # e.g., "Nagi"
    occurrences: int = 0


class KuchieVisualizer:
    """
    Extract and validate character data from kuchie illustrations.
    
    Works in tandem with the Librarian's ruby text extraction to ensure
    character names are consistent across visual and textual sources.
    """
    
    KUCHIE_OCR_PROMPT = """
Analyze this Japanese light novel kuchie (口絵/color plate illustration).

TASK: Extract all character information visible in the image.

For each character shown, provide:

1. "japanese_name": The character's name in Japanese (kanji if shown)
2. "japanese_reading": The furigana/reading if shown (hiragana/katakana)
3. "romanized_name": Roman alphabet name if shown
4. "visual_traits": Array of visible traits (hair color, eye color, distinctive features)
5. "text_overlays": Any Japanese text describing the character (personality, role)

Output as a JSON array of character objects.
If no text is visible, still describe the characters visually.

Example output:
[
  {
    "japanese_name": "東雲凪",
    "japanese_reading": "しののめなぎ",
    "romanized_name": "Nagi Shinonome",
    "visual_traits": ["silver-white hair", "blue eyes", "snowflake hair clip"],
    "text_overlays": ["氷姫 (Ice Princess)"]
  }
]
"""

    def __init__(
        self,
        volume_path: Path,
        manifest: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None
    ):
        self.volume_path = volume_path
        self.manifest = manifest or self._load_manifest()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        
        # Canon names from Librarian's ruby extraction
        self.canon_names: Dict[str, RubyCanonEntry] = {}
        self._load_canon_names()
        
        # Extracted kuchie characters
        self.kuchie_characters: List[KuchieCharacter] = []
    
    def _load_manifest(self) -> Dict[str, Any]:
        """Load manifest.json from volume path."""
        manifest_path = self.volume_path / "manifest.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        return {}
    
    def _load_canon_names(self) -> None:
        """
        Load canon names from manifest.json character_profiles.
        
        These are the authoritative names extracted by the Librarian
        from ruby annotations in the source text.
        """
        profiles = self.manifest.get("metadata_en", {}).get("character_profiles", {})
        
        for kanji_name, profile in profiles.items():
            self.canon_names[kanji_name] = RubyCanonEntry(
                kanji=kanji_name,
                reading=profile.get("ruby_reading", ""),
                full_name_en=profile.get("full_name", ""),
                nickname=profile.get("nickname", ""),
                occurrences=profile.get("occurrences", 0)
            )
        
        logger.info(f"[KUCHIE] Loaded {len(self.canon_names)} canon names from manifest")
    
    def match_to_canon(self, ocr_name: str, ocr_reading: str = "") -> Tuple[Optional[RubyCanonEntry], float]:
        """
        Match OCR-extracted name to canon names from ruby extraction.
        
        Args:
            ocr_name: Japanese name extracted from kuchie via OCR
            ocr_reading: Reading/furigana if available
            
        Returns:
            Tuple of (matching canon entry, confidence score) or (None, 0.0)
        """
        if not ocr_name:
            return None, 0.0
        
        # Exact kanji match
        if ocr_name in self.canon_names:
            return self.canon_names[ocr_name], 1.0
        
        # Partial match (surname or given name only)
        best_match = None
        best_confidence = 0.0
        
        for kanji, entry in self.canon_names.items():
            # Check if OCR name is contained in canon kanji
            if ocr_name in kanji or kanji in ocr_name:
                confidence = len(ocr_name) / max(len(kanji), 1) * 0.9
                if confidence > best_confidence:
                    best_match = entry
                    best_confidence = confidence
            
            # Check reading match
            if ocr_reading and entry.reading:
                if ocr_reading == entry.reading:
                    return entry, 0.95
                if ocr_reading in entry.reading or entry.reading in ocr_reading:
                    confidence = 0.85
                    if confidence > best_confidence:
                        best_match = entry
                        best_confidence = confidence
        
        return best_match, best_confidence
    
    def process_kuchie(self, kuchie_path: Path) -> Optional[List[KuchieCharacter]]:
        """
        Process a single kuchie image and extract character data.
        
        Args:
            kuchie_path: Path to kuchie image file
            
        Returns:
            List of KuchieCharacter objects, or None on error
        """
        if not self.api_key:
            logger.warning("[KUCHIE] No API key available, skipping OCR")
            return None
        
        from google import genai
        from google.genai import types
        
        try:
            client = genai.Client(api_key=self.api_key)
            
            # Load image
            image_bytes = kuchie_path.read_bytes()
            mime_type = "image/jpeg" if kuchie_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            
            response = client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=[self.KUCHIE_OCR_PROMPT, image_part],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=2048,
                )
            )
            
            # Parse response
            response_text = ""
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if part.text:
                        response_text += part.text
            
            characters = self._parse_character_json(response_text)
            
            # Cross-reference with canon names
            validated_chars = []
            for char_data in characters:
                kuchie_char = KuchieCharacter(
                    japanese_name=char_data.get("japanese_name", ""),
                    japanese_reading=char_data.get("japanese_reading", ""),
                    romanized_name=char_data.get("romanized_name", ""),
                    visual_traits=char_data.get("visual_traits", []),
                    source_kuchie=kuchie_path.name
                )
                
                # Match to canon
                canon_match, confidence = self.match_to_canon(
                    kuchie_char.japanese_name,
                    kuchie_char.japanese_reading
                )
                
                if canon_match:
                    kuchie_char.canon_name = canon_match.nickname
                    kuchie_char.canon_full_name = canon_match.full_name_en
                    kuchie_char.ruby_match_confidence = confidence
                    logger.info(
                        f"[KUCHIE] Matched '{kuchie_char.japanese_name}' → "
                        f"'{kuchie_char.canon_name}' (confidence: {confidence:.2f})"
                    )
                else:
                    # Use romanized name from OCR if no canon match
                    kuchie_char.canon_name = kuchie_char.romanized_name
                    kuchie_char.ruby_match_confidence = 0.0
                    logger.warning(
                        f"[KUCHIE] No canon match for '{kuchie_char.japanese_name}'"
                    )
                
                validated_chars.append(kuchie_char)
            
            self.kuchie_characters.extend(validated_chars)
            return validated_chars
            
        except Exception as e:
            logger.error(f"[KUCHIE] Failed to process {kuchie_path.name}: {e}")
            return None
    
    def _parse_character_json(self, text: str) -> List[Dict[str, Any]]:
        """Parse JSON array of character data from OCR response."""
        cleaned = text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = cleaned.strip()
        
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return [result]
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"[KUCHIE] Failed to parse character JSON: {e}")
            return []
    
    def process_all_kuchie(self) -> Dict[str, Any]:
        """
        Process all kuchie images in the volume's assets directory.
        
        Returns:
            Summary statistics and extracted character data
        """
        assets_dir = self.volume_path / "_assets"
        if not assets_dir.exists():
            assets_dir = self.volume_path / "assets"
        
        kuchie_dir = assets_dir / "kuchie" if (assets_dir / "kuchie").exists() else assets_dir
        
        kuchie_files = sorted(
            list(kuchie_dir.glob("kuchie-*.jpg")) +
            list(kuchie_dir.glob("kuchie-*.jpeg")) +
            list(kuchie_dir.glob("kuchie-*.png"))
        )
        
        if not kuchie_files:
            logger.warning(f"[KUCHIE] No kuchie files found in {kuchie_dir}")
            return {"total": 0, "processed": 0, "characters": []}
        
        logger.info(f"[KUCHIE] Found {len(kuchie_files)} kuchie files")
        
        stats = {"total": len(kuchie_files), "processed": 0, "characters": []}
        
        for kuchie_path in kuchie_files:
            logger.info(f"[KUCHIE] Processing {kuchie_path.name}...")
            chars = self.process_kuchie(kuchie_path)
            if chars:
                stats["processed"] += 1
                stats["characters"].extend([c.to_dict() for c in chars])
        
        return stats
    
    def get_canon_name_for_visual(self, japanese_name: str) -> str:
        """
        Get the canonical English name for a Japanese character name.
        
        This is the key integration point with the Multimodal Processor:
        ensures visual_cache.json uses canon names from manifest.json.
        
        Args:
            japanese_name: Character name in Japanese (kanji)
            
        Returns:
            Canonical English name, or empty string if not found
        """
        if japanese_name in self.canon_names:
            return self.canon_names[japanese_name].full_name_en
        
        # Try fuzzy match
        match, confidence = self.match_to_canon(japanese_name)
        if match and confidence >= 0.8:
            return match.full_name_en
        
        return ""
    
    def inject_canon_into_visual_cache(self, visual_cache: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process visual_cache.json to replace detected names with canon names.
        
        Delegates to CanonNameEnforcer.enforce_in_visual_context for recursive
        dict processing, avoiding duplicated logic.
        
        Args:
            visual_cache: The visual_cache.json dict
            
        Returns:
            Updated visual_cache with canon names injected
        """
        if not self.canon_names:
            logger.debug("[KUCHIE] No canon names loaded, skipping injection")
            return visual_cache
        
        from modules.multimodal.prompt_injector import CanonNameEnforcer
        
        # Build a manifest-like dict for the enforcer
        mock_manifest = {
            "metadata_en": {
                "character_profiles": {
                    kanji: {
                        "full_name": entry.full_name_en,
                        "nickname": entry.nickname,
                    }
                    for kanji, entry in self.canon_names.items()
                    if entry.full_name_en
                }
            }
        }
        
        enforcer = CanonNameEnforcer(mock_manifest)
        updated_cache = enforcer.enforce_in_visual_context(visual_cache)
        
        # Add canon name reference section
        updated_cache["_canon_names"] = {
            kanji: {
                "english": entry.full_name_en,
                "nickname": entry.nickname,
                "reading": entry.reading
            }
            for kanji, entry in self.canon_names.items()
            if entry.full_name_en
        }
        
        logger.info(f"[KUCHIE] Injected {len(enforcer.canon_map)} canon names into visual cache")
        return updated_cache


def integrate_with_asset_processor(
    volume_path: Path,
    manifest: Dict[str, Any],
    visual_cache: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Integration function for the Multimodal Asset Processor.
    
    Called after Phase 1.6 visual analysis to inject canon names
    from manifest.json into the visual_cache.
    
    Note: Kuchie OCR is available via visualizer.process_all_kuchie()
    but is not called automatically (CPU/API intensive). Run manually
    if character name cross-validation from color plates is needed.
    
    Args:
        volume_path: Path to volume working directory
        manifest: The manifest.json dict (contains character_profiles)
        visual_cache: The visual_cache.json dict
        
    Returns:
        Updated visual_cache with canon names injected
    """
    visualizer = KuchieVisualizer(volume_path, manifest)
    
    # Inject canon names into visual cache
    updated_cache = visualizer.inject_canon_into_visual_cache(visual_cache)
    
    return updated_cache
