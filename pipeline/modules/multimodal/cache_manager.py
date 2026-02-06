"""
Visual Cache Manager.

Handles loading, saving, and querying the visual_cache.json file
that stores pre-baked visual analysis from Gemini 3 Pro Vision.

The cache follows the "Game Engine" approach: expensive visual analysis
is computed once (Phase 1.6) and reused across translation runs.

Integration with Librarian's Ruby Text Extraction:
- Loads manifest.json for ID mapping (EPUB ID → cache ID)
- Loads character_profiles for canon name enforcement
- Initializes CanonNameEnforcer for consistent character naming
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class VisualCacheManager:
    """Manage visual analysis cache for multimodal translation."""

    def __init__(self, volume_path: Path, cache_filename: str = "visual_cache.json"):
        self.volume_path = volume_path
        self.cache_path = volume_path / cache_filename
        self.manifest: Dict[str, Any] = self._load_manifest()
        self.cache: Dict[str, Any] = self._load_cache()
        self.id_mapping: Dict[str, str] = self._load_id_mapping()
        
        # Canon name enforcement is handled by prompt_injector.build_chapter_visual_guidance(manifest=...)

    def _load_manifest(self) -> Dict[str, Any]:
        """Load manifest.json for ID mapping and character profiles."""
        manifest_path = self.volume_path / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                logger.debug(f"[MULTIMODAL] Loaded manifest.json")
                return manifest
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[MULTIMODAL] Failed to load manifest: {e}")
        return {}
    
    def get_manifest(self) -> Dict[str, Any]:
        """Get the loaded manifest dict for external use."""
        return self.manifest
    
    def get_character_profiles(self) -> Dict[str, Any]:
        """Get character profiles from manifest (Librarian's ruby extraction)."""
        return self.manifest.get("metadata_en", {}).get("character_profiles", {})
    
    def get_canon_name(self, japanese_name: str) -> Optional[str]:
        """
        Get the canonical English name for a Japanese character name.
        
        Uses the Librarian's ruby text extraction stored in manifest.json.
        
        Args:
            japanese_name: Character name in Japanese (kanji)
            
        Returns:
            Canonical English name, or None if not found
        """
        profiles = self.get_character_profiles()
        profile = profiles.get(japanese_name, {})
        return profile.get("full_name")

    def _load_cache(self) -> Dict[str, Any]:
        """Load existing cache from disk or return empty dict."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                logger.info(f"[MULTIMODAL] Loaded visual cache: {len(cache)} entries")
                return cache
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[MULTIMODAL] Failed to load visual cache: {e}")
                return {}
        return {}

    def _load_id_mapping(self) -> Dict[str, str]:
        """Load EPUB ID to cache ID mapping from already-loaded manifest."""
        mapping = self.manifest.get("multimodal", {}).get("epub_id_to_cache_id", {})
        if mapping:
            logger.info(f"[MULTIMODAL] Loaded ID mapping: {len(mapping)} entries")
        return mapping

    def _resolve_id(self, illustration_id: str) -> str:
        """Resolve an illustration ID to the cache key, using mapping if available."""
        # Strip file extension if present (e.g., "i-019.jpg" -> "i-019")
        base_id = illustration_id.rsplit('.', 1)[0] if '.' in illustration_id else illustration_id
        # Try direct lookup first, then check ID mapping
        if base_id in self.cache:
            return base_id
        return self.id_mapping.get(base_id, base_id)

    def save_cache(self) -> None:
        """Persist cache to disk."""
        try:
            logger.info(f"[MULTIMODAL] Saving visual cache to: {self.cache_path}")
            logger.info(f"[MULTIMODAL] Cache entries to save: {len(self.cache)}")
            
            # Ensure parent directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[MULTIMODAL] ✓ Visual cache saved successfully: {self.cache_path}")
            logger.info(f"[MULTIMODAL] ✓ File size: {self.cache_path.stat().st_size} bytes")
        except Exception as e:
            logger.error(f"[MULTIMODAL] ✗ Failed to save visual cache: {e}")
            raise

    def has_cache(self) -> bool:
        """Check if any cache entries exist."""
        return len(self.cache) > 0

    def get_visual_context(self, illustration_id: str) -> Dict[str, Any]:
        """
        Get cached visual analysis for a specific illustration.

        Supports both direct cache IDs (illust-001) and EPUB IDs (i-019)
        by using the epub_id_to_cache_id mapping from manifest.json.

        Returns:
            visual_ground_truth dict if found, empty dict otherwise.
        """
        resolved_id = self._resolve_id(illustration_id)
        entry = self.cache.get(resolved_id, {})
        if not entry:
            return {}

        status = entry.get("status", "unknown")
        if status in ("cached", "manual_override", "safety_blocked"):
            return entry.get("visual_ground_truth", {})

        return {}

    def get_spoiler_prevention(self, illustration_id: str) -> Dict[str, Any]:
        """Get spoiler prevention rules for a specific illustration."""
        resolved_id = self._resolve_id(illustration_id)
        entry = self.cache.get(resolved_id, {})
        return entry.get("spoiler_prevention", {})

    def get_cache_stats(self) -> Dict[str, int]:
        """Get summary statistics of cache contents."""
        stats = {"total": 0, "cached": 0, "safety_blocked": 0, "manual_override": 0}
        for entry in self.cache.values():
            stats["total"] += 1
            status = entry.get("status", "other")
            if status in stats:
                stats[status] += 1
        return stats

    def set_entry(self, illustration_id: str, entry: Dict[str, Any]) -> None:
        """Set a cache entry (used by VisualAssetProcessor during Phase 1.6)."""
        self.cache[illustration_id] = entry

    def is_manual_override(self, illustration_id: str) -> bool:
        """Check if an entry has been manually edited by a human."""
        entry = self.cache.get(illustration_id, {})
        return entry.get("status") == "manual_override"

    @staticmethod
    def compute_cache_key(img_path: Path, prompt: str, model: str) -> Dict[str, str]:
        """Generate cache key for invalidation checks."""
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        with open(img_path, 'rb') as f:
            image_hash = hashlib.sha256(f.read()).hexdigest()[:16]
        return {"model": model, "prompt_hash": prompt_hash, "image_hash": image_hash}

    @staticmethod
    def should_regenerate(
        entry: Optional[Dict], current_key: Dict[str, str], max_age_days: int = 90
    ) -> bool:
        """Determine if a cached analysis needs regeneration."""
        if not entry:
            return True
        if entry.get("status") == "manual_override":
            return False

        cached_key = entry.get("cache_key", {})
        if cached_key.get("model") != current_key["model"]:
            return True
        if cached_key.get("prompt_hash") != current_key["prompt_hash"]:
            return True
        if cached_key.get("image_hash") != current_key["image_hash"]:
            return True

        generated_at = entry.get("generated_at")
        if generated_at:
            try:
                from dateutil.parser import parse
                cache_age = datetime.now() - parse(generated_at)
                if cache_age > timedelta(days=max_age_days):
                    return True
            except (ImportError, ValueError):
                pass
        return False
