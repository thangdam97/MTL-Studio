"""
Visual Asset Processor (Phase 1.6).

Pre-bakes visual analysis for all illustrations in a volume using
Gemini 3 Pro Vision with ThinkingConfig enabled.

This is the "Art Director" component of the CPU+GPU architecture.
It runs ONCE per volume and produces visual_cache.json containing
narrative interpretations of each illustration.

Features:
  - Cache invalidation via prompt+image+model hash
  - Retry with exponential backoff for transient API errors (429/503)
  - Configurable timeout, rate limit, and max retries
  - Safety block handling with meaningful fallback text
  - Thought logging for editorial review

Usage:
    mtl.py phase1.6 <volume_id>
"""

import json
import time
import base64
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from modules.multimodal.cache_manager import VisualCacheManager
from modules.multimodal.thought_logger import ThoughtLogger, VisualAnalysisLog
from pipeline.common.genai_factory import create_genai_client, resolve_api_key, resolve_genai_backend

logger = logging.getLogger(__name__)

# Default visual analysis prompt for Gemini 3 Pro Vision
VISUAL_ANALYSIS_PROMPT = """
Analyze this light novel illustration for translation assistance.

Provide a structured analysis as JSON:

1. "composition": Describe the panel layout, framing, focal points (1-2 sentences)
2. "emotional_delta": What emotions are being conveyed? Any contrasts? (1-2 sentences)
3. "key_details": Object with character expressions, actions, atmosphere details
4. "narrative_directives": Array of 3-5 specific instructions for how a translator
   should use this visual context to enhance the translated prose
5. "spoiler_prevention": Object with "do_not_reveal_before_text" array listing
   plot details visible in the image that the text hasn't confirmed yet

Output ONLY the JSON object. No commentary or explanation.
"""


class VisualAssetProcessor:
    """Pre-bake visual analysis for all illustrations in a volume."""

    def __init__(
        self,
        volume_path: Path,
        model: str = "gemini-3-flash-preview",
        thinking_level: str = "medium",
        api_key: Optional[str] = None,
        rate_limit_seconds: float = 3.0,
        max_retries: int = 3,
        timeout_seconds: float = 120.0
    ):
        self.volume_path = volume_path
        self.model = model
        self.thinking_level = thinking_level
        self.api_key = resolve_api_key(api_key=api_key, required=False)
        self.backend = resolve_genai_backend()
        self.rate_limit_seconds = rate_limit_seconds
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        if not self.api_key and self.backend == "developer":
            raise ValueError(
                "API key missing for developer mode. Set GOOGLE_API_KEY (or GEMINI_API_KEY)."
            )

        # Initialize components
        self.cache_manager = VisualCacheManager(volume_path)
        self.thought_logger = ThoughtLogger(volume_path)
        self.analysis_prompt = VISUAL_ANALYSIS_PROMPT

        # Deferred Gemini client initialization
        self._genai_client = None

    @property
    def genai_client(self):
        """Lazy initialization of Gemini client."""
        if self._genai_client is None:
            self._genai_client = create_genai_client(
                api_key=self.api_key,
                backend=self.backend,
            )
        return self._genai_client

    def process_volume(self) -> Dict[str, Any]:
        """
        Analyze all illustrations in the volume and cache results.

        Runs an illustration integrity check first. If mismatches are found
        between JP tags, asset files, and the manifest ID mapping, processing
        is blocked to prevent wasted API calls.

        Returns:
            Cache statistics dict.
        """
        # Pre-flight integrity check (guard for programmatic callers)
        from modules.multimodal.integrity_checker import check_illustration_integrity

        integrity = check_illustration_integrity(self.volume_path)
        if not integrity.passed:
            error_summary = "; ".join(integrity.errors[:3])
            logger.error(f"[PHASE 1.6] Integrity check failed: {error_summary}")
            return {"error": f"Illustration integrity check failed: {error_summary}"}

        if integrity.warnings:
            for w in integrity.warnings:
                logger.warning(f"[PHASE 1.6] {w}")

        # Find illustration assets
        # Librarian output structure:
        #   _assets/illustrations/illust-NNN.jpg   (inline illustrations)
        #   _assets/kuchie/kuchie-NNN.jpg          (color plates / front-matter art)
        #   _assets/cover.jpg                      (cover art)
        assets_dir = self.volume_path / "_assets"
        if not assets_dir.exists():
            assets_dir = self.volume_path / "assets"
        if not assets_dir.exists():
            logger.error(f"[PHASE 1.6] No assets directory found in {self.volume_path}")
            return {"error": "No assets directory found"}

        illustrations: List[Path] = []

        # Patterns to EXCLUDE from illustration inventory
        EXCLUDE_PATTERNS = {'cover', 'gaiji-', 'i-bookwalker', '_title'}
        KUCHIE_PATTERNS = {'kuchie-', 'k001', 'k002', 'k003', 'k004', 'k005', 'k006', 'k007', 'k008'}

        # 1. Inline illustrations: _assets/illustrations/ or _assets/ root
        # Accept ALL common EPUB illustration naming patterns:
        # - Standard: illust-NNN, p###, m###
        # - Special: profile, tokuten, ok, oku, allcover-NNN
        # - Legacy: image#, image_rsrc*
        illust_dir = assets_dir / "illustrations"
        for search_dir in [illust_dir, assets_dir]:
            if search_dir.exists():
                logger.debug(f"[PHASE 1.6] Scanning for illustrations in: {search_dir}")
                for img_file in sorted(search_dir.glob("*.*")):
                    if img_file.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                        continue
                    stem_lower = img_file.stem.lower()
                    # Skip exclusions (cover, gaiji, bookwalker branding)
                    if any(stem_lower.startswith(pattern) for pattern in EXCLUDE_PATTERNS):
                        logger.debug(f"[PHASE 1.6]   Excluded (system file): {img_file.name}")
                        continue
                    # Skip kuchie files (handled separately below)
                    if any(stem_lower.startswith(pattern) for pattern in KUCHIE_PATTERNS):
                        logger.debug(f"[PHASE 1.6]   Skipped (kuchie): {img_file.name}")
                        continue
                    logger.debug(f"[PHASE 1.6]   Added illustration: {img_file.name}")
                    illustrations.append(img_file)
                if illustrations:
                    logger.info(f"[PHASE 1.6] Found {len(illustrations)} inline illustration(s)")
                    break

        # 2. Kuchie color plates: _assets/kuchie/ or _assets/illustrations/
        # Accept both kuchie-NNN and k### naming patterns
        kuchie_files = []
        kuchie_dir = assets_dir / "kuchie"
        if kuchie_dir.exists():
            for img_file in sorted(kuchie_dir.glob("*.*")):
                if img_file.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    kuchie_files.append(img_file)
        
        # Also check illustrations/ directory for k### pattern files
        if illust_dir.exists():
            for img_file in sorted(illust_dir.glob("*.*")):
                if img_file.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue
                stem_lower = img_file.stem.lower()
                if any(stem_lower.startswith(pattern) for pattern in KUCHIE_PATTERNS):
                    if img_file not in kuchie_files:  # Avoid duplicates
                        kuchie_files.append(img_file)
            if kuchie_files:
                logger.info(f"[PHASE 1.6] Found {len(kuchie_files)} kuchie color plate(s)")
                illustrations.extend(kuchie_files)

        # 3. Cover art: _assets/cover.*
        for cover_path in assets_dir.glob("cover.*"):
            if cover_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                logger.info(f"[PHASE 1.6] Found cover art: {cover_path.name}")
                illustrations.append(cover_path)
                break

        if not illustrations:
            logger.warning(f"[PHASE 1.6] No illustrations found in {assets_dir}")
            return {"total": 0, "cached": 0, "generated": 0, "blocked": 0}

        logger.info(f"[PHASE 1.6] Found {len(illustrations)} illustrations to process")
        stats = {"total": len(illustrations), "cached": 0, "generated": 0, "blocked": 0}

        for img_path in illustrations:
            illust_id = img_path.stem
            current_key = VisualCacheManager.compute_cache_key(
                img_path, self.analysis_prompt, self.model
            )

            # Check if regeneration needed
            existing_entry = self.cache_manager.cache.get(illust_id)
            if not VisualCacheManager.should_regenerate(existing_entry, current_key):
                status = existing_entry.get("status", "cached")
                logger.info(f"  [SKIP] {illust_id}: Using existing cache (status={status})")
                stats["cached"] += 1
                continue

            # Process illustration
            logger.info(f"  [ANALYZE] {illust_id}: Running visual analysis...")
            start_time = time.time()

            try:
                analysis = self._analyze_illustration(img_path)
                elapsed = time.time() - start_time

                if analysis.get("status") == "safety_blocked":
                    stats["blocked"] += 1
                    logger.warning(f"  [BLOCKED] {illust_id}: Safety filter ({elapsed:.1f}s)")
                else:
                    stats["generated"] += 1
                    logger.info(f"  [DONE] {illust_id}: Analysis complete ({elapsed:.1f}s)")

                # Save to cache
                self.cache_manager.set_entry(illust_id, {
                    "status": analysis.get("status", "cached"),
                    "cache_key": current_key,
                    "cache_version": "1.0",
                    "generated_at": datetime.now().isoformat(),
                    "model": self.model,
                    "thinking_level": self.thinking_level,
                    "visual_ground_truth": analysis.get("visual_ground_truth", {}),
                    "spoiler_prevention": analysis.get("spoiler_prevention", {}),
                })

                # Log thoughts
                self.thought_logger.log_analysis(VisualAnalysisLog(
                    illustration_id=illust_id,
                    model=self.model,
                    thinking_level=self.thinking_level,
                    thoughts=analysis.get("thoughts", []),
                    iterations=1,
                    processing_time_seconds=elapsed,
                    timestamp=datetime.now().isoformat(),
                    success=analysis.get("status") != "safety_blocked",
                ))

            except Exception as e:
                logger.error(f"  [ERROR] {illust_id}: {e}")
                stats["blocked"] += 1
                self.cache_manager.set_entry(illust_id, {
                    "status": "error",
                    "cache_key": current_key,
                    "generated_at": datetime.now().isoformat(),
                    "error": str(e),
                    "visual_ground_truth": {
                        "composition": "ERROR",
                        "emotional_delta": "Analysis failed - use text context only",
                        "key_details": {},
                        "narrative_directives": [
                            "Visual analysis unavailable - use text context only"
                        ]
                    },
                })

            # Rate limiting
            time.sleep(self.rate_limit_seconds)

        # Save cache to disk
        self.cache_manager.save_cache()
        
        # Post-processing: Inject canon names from Librarian's ruby extraction
        self._inject_canon_names()

        # Summary
        logger.info(f"\n[PHASE 1.6] Asset Processing Complete:")
        logger.info(f"  Total: {stats['total']}")
        logger.info(f"  Cached (skipped): {stats['cached']}")
        logger.info(f"  Generated (new): {stats['generated']}")
        logger.info(f"  Blocked/Error: {stats['blocked']}")

        return stats
    
    def _inject_canon_names(self) -> None:
        """
        Post-process visual cache to inject canon names from manifest.
        
        This ensures Art Director's Notes use consistent character names
        that match the Librarian's ruby text extraction.
        """
        try:
            from modules.multimodal.kuchie_visualizer import KuchieVisualizer
            
            # Load manifest for character profiles
            manifest_path = self.volume_path / "manifest.json"
            if not manifest_path.exists():
                logger.debug("[PHASE 1.6] No manifest.json found, skipping canon injection")
                return
            
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            profiles = manifest.get("metadata_en", {}).get("character_profiles", {})
            
            if not profiles:
                logger.debug("[PHASE 1.6] No character profiles in manifest")
                return
            
            visualizer = KuchieVisualizer(self.volume_path, manifest)
            
            # Inject canon names into the cache
            updated_cache = visualizer.inject_canon_into_visual_cache(self.cache_manager.cache)
            self.cache_manager.cache = updated_cache
            self.cache_manager.save_cache()
            
            logger.info(f"[PHASE 1.6] Canon names injected from {len(profiles)} character profiles")
            
        except Exception as e:
            logger.warning(f"[PHASE 1.6] Failed to inject canon names: {e}")

    def _analyze_illustration(self, img_path: Path) -> Dict[str, Any]:
        """
        Analyze a single illustration using Gemini 3 Pro Vision + Thinking.

        Includes retry logic with exponential backoff for transient errors
        (429 rate limit, 503 service unavailable, connection errors).

        Returns:
            Dict with status, visual_ground_truth, thoughts, and spoiler_prevention.
        """
        from google.genai import types

        # Load image
        image_bytes = img_path.read_bytes()
        mime_type = "image/jpeg"
        if img_path.suffix.lower() == ".png":
            mime_type = "image/png"

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._call_gemini_vision(image_part, attempt)
            except Exception as e:
                last_error = e
                error_str = str(e)

                # Safety blocks are not retriable
                if "SAFETY" in error_str.upper() or "blocked" in error_str.lower():
                    return {
                        "status": "safety_blocked",
                        "visual_ground_truth": {
                            "composition": "SAFETY_FILTER_BLOCKED",
                            "emotional_delta": "Proceed with text-only context",
                            "key_details": {},
                            "narrative_directives": [
                                "Visual analysis unavailable due to safety filter"
                            ]
                        },
                        "thoughts": [],
                    }

                # Transient errors: retry with backoff
                is_transient = any(code in error_str for code in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
                is_timeout = "timeout" in error_str.lower() or "deadline" in error_str.lower()

                if (is_transient or is_timeout) and attempt < self.max_retries:
                    backoff = 2 ** attempt + 1  # 3s, 5s, 9s
                    logger.warning(f"  [RETRY] Attempt {attempt}/{self.max_retries}: {error_str[:100]}")
                    logger.warning(f"  [RETRY] Backing off {backoff}s...")
                    time.sleep(backoff)
                    continue

                # Non-retriable or final attempt
                raise

        # Should not reach here, but safety net
        raise last_error  # type: ignore

    def _call_gemini_vision(self, image_part, attempt: int = 1) -> Dict[str, Any]:
        """Execute a single Gemini Vision API call with timeout."""
        from google.genai import types

        try:
            response = self.genai_client.models.generate_content(
                model=self.model,
                contents=[self.analysis_prompt, image_part],
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=True,
                        thinking_level=self.thinking_level
                    ),
                    temperature=0.3,
                    max_output_tokens=4096,
                    http_options=types.HttpOptions(
                        timeout=int(self.timeout_seconds * 1000)  # ms
                    ) if hasattr(types, 'HttpOptions') else None,
                )
            )

            # Check for safety block
            if (response.candidates and
                response.candidates[0].finish_reason and
                str(response.candidates[0].finish_reason).upper() in ("SAFETY", "BLOCKED")):
                return {
                    "status": "safety_blocked",
                    "visual_ground_truth": {
                        "composition": "SAFETY_FILTER_BLOCKED",
                        "emotional_delta": "Proceed with text-only context",
                        "key_details": {},
                        "narrative_directives": [
                            "Visual analysis unavailable due to safety filter",
                            "Do not infer visual details from blocked illustration"
                        ]
                    },
                    "thoughts": [],
                }

            # Extract thoughts and response
            thoughts = []
            response_text = ""

            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        thoughts.append(part.text)
                    elif part.text:
                        response_text += part.text

            # Parse JSON response
            analysis = self._parse_analysis_json(response_text)

            return {
                "status": "cached",
                "visual_ground_truth": {
                    "composition": analysis.get("composition", ""),
                    "emotional_delta": analysis.get("emotional_delta", ""),
                    "key_details": analysis.get("key_details", {}),
                    "narrative_directives": analysis.get("narrative_directives", []),
                },
                "spoiler_prevention": analysis.get("spoiler_prevention", {}),
                "thoughts": thoughts,
            }

        except Exception as e:
            error_str = str(e)
            if "SAFETY" in error_str.upper() or "blocked" in error_str.lower():
                return {
                    "status": "safety_blocked",
                    "visual_ground_truth": {
                        "composition": "SAFETY_FILTER_BLOCKED",
                        "emotional_delta": "Proceed with text-only context",
                        "key_details": {},
                        "narrative_directives": [
                            "Visual analysis unavailable due to safety filter"
                        ]
                    },
                    "thoughts": [],
                }
            raise

    def _parse_analysis_json(self, text: str) -> Dict[str, Any]:
        """Parse the JSON response from visual analysis, handling markdown fences."""
        import re

        # Strip markdown code fences if present
        cleaned = text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"[PHASE 1.6] Failed to parse analysis JSON: {e}")
            logger.debug(f"[PHASE 1.6] Raw response: {text[:200]}...")
            # Return a best-effort fallback
            return {
                "composition": cleaned[:200] if cleaned else "Parse error",
                "emotional_delta": "Analysis produced non-JSON output",
                "key_details": {},
                "narrative_directives": ["Raw analysis available in thought logs"],
            }
