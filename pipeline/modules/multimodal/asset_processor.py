"""
Visual Asset Processor (Phase 1.6).

Pre-bakes visual analysis for all illustrations in a volume using
Gemini 3 Multimodal Vision with ThinkingConfig enabled.

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
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

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
6. "identity_resolution": Object with:
   - "recognized_characters": array of objects:
       {"canonical_name": "...", "japanese_name": "...", "confidence": 0.0-1.0, "non_color_evidence": ["..."]}
   - "unresolved_characters": array of brief descriptors if identity remains uncertain

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
        timeout_seconds: float = 120.0,
        force_override: bool = False,
    ):
        self.volume_path = volume_path
        self.model = model
        self.thinking_level = thinking_level
        self.api_key = resolve_api_key(api_key=api_key, required=False)
        self.backend = resolve_genai_backend()
        self.rate_limit_seconds = rate_limit_seconds
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.force_override = force_override

        if not self.api_key and self.backend == "developer":
            raise ValueError(
                "API key missing for developer mode. Set GOOGLE_API_KEY (or GEMINI_API_KEY)."
            )

        # Initialize components
        self.cache_manager = VisualCacheManager(volume_path)
        self.thought_logger = ThoughtLogger(volume_path)
        self.identity_lock_status: Dict[str, Any] = {
            "enabled": False,
            "manifest_canon": 0,
            "bible_canon": 0,
        }
        self.analysis_prompt = self._build_analysis_prompt()

        # Deferred Gemini client initialization
        self._genai_client = None

    def _build_analysis_prompt(self) -> str:
        """
        Build visual analysis prompt with identity lock context.

        Identity lock uses canon real names + non-color visual markers so the
        vision model resolves character identity before scene analysis.
        """
        base_prompt = VISUAL_ANALYSIS_PROMPT.strip()
        try:
            from modules.multimodal.prompt_injector import build_multimodal_identity_lock

            manifest = self.cache_manager.get_manifest()
            bible_characters = self._load_bible_characters(manifest)
            metadata_en = manifest.get("metadata_en", {}) if isinstance(manifest, dict) else {}
            profiles = metadata_en.get("character_profiles", {}) if isinstance(metadata_en, dict) else {}
            manifest_canon = 0
            if isinstance(profiles, dict):
                manifest_canon = sum(
                    1 for p in profiles.values()
                    if isinstance(p, dict) and str(p.get("full_name", "")).strip()
                )
            bible_canon = 0
            if isinstance(bible_characters, dict):
                bible_canon = sum(
                    1 for p in bible_characters.values()
                    if isinstance(p, dict) and str(p.get("canonical_en", "")).strip()
                )
            identity_lock = build_multimodal_identity_lock(
                manifest, bible_characters=bible_characters
            )
            if identity_lock:
                self.identity_lock_status = {
                    "enabled": True,
                    "manifest_canon": manifest_canon,
                    "bible_canon": bible_canon,
                }
                return (
                    f"{base_prompt}\n\n"
                    f"{identity_lock}\n\n"
                    "IDENTITY RESOLUTION RULES:\n"
                    "- Resolve identity with canonical names above before prose directives.\n"
                    "- Prioritize non-color markers (hairstyle, outfit silhouette, expression, posture, accessories).\n"
                    "- Do not invent alternate names if a canonical match exists.\n"
                    "- If uncertain, report unresolved descriptors and continue scene analysis.\n"
                )
        except Exception as e:
            logger.debug(f"[PHASE 1.6] Identity lock prompt build skipped: {e}")
        self.identity_lock_status = {
            "enabled": False,
            "manifest_canon": 0,
            "bible_canon": 0,
        }
        return base_prompt

    def _load_bible_characters(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Load character registry from linked series bible (if available)."""
        if not isinstance(manifest, dict):
            return {}
        bible_id = str(manifest.get("bible_id", "")).strip()
        if not bible_id:
            return {}
        try:
            from pipeline.config import PIPELINE_ROOT
            from pipeline.translator.series_bible import BibleController

            ctrl = BibleController(PIPELINE_ROOT)
            bible = ctrl.get_bible(bible_id)
            if bible:
                chars = bible.get_all_characters()
                if isinstance(chars, dict):
                    return chars
        except Exception as e:
            logger.debug(f"[PHASE 1.6] Could not load bible identities: {e}")
        return {}

    def _manifest_chapters(self) -> List[Dict[str, Any]]:
        """Return normalized manifest chapter list."""
        manifest = self.cache_manager.get_manifest()
        if not isinstance(manifest, dict):
            return []
        chapters = manifest.get("chapters", [])
        if not isinstance(chapters, list) or not chapters:
            structure = manifest.get("structure", {})
            if isinstance(structure, dict):
                chapters = structure.get("chapters", [])
        return chapters if isinstance(chapters, list) else []

    def _chapter_for_illustration(self, image_name: str) -> Optional[Dict[str, Any]]:
        """Find chapter metadata entry that owns this illustration."""
        image_stem = Path(image_name).stem
        for chapter in self._manifest_chapters():
            if not isinstance(chapter, dict):
                continue
            illustrations = chapter.get("illustrations", [])
            if not isinstance(illustrations, list):
                continue
            for ill in illustrations:
                ill_name = str(ill).strip()
                if not ill_name:
                    continue
                if ill_name == image_name or Path(ill_name).stem == image_stem:
                    return chapter
        return None

    def _scene_local_candidates(self, img_path: Path) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Build scene-local identity candidates from JP text near the illustration marker.

        Returns tuple:
            - candidate list
            - source anchor string
        """
        chapter = self._chapter_for_illustration(img_path.name)
        if not chapter:
            return [], None

        source_file = str(chapter.get("source_file", "")).strip()
        if not source_file:
            return [], None

        jp_path = self.volume_path / "JP" / source_file
        if not jp_path.exists():
            return [], None

        try:
            lines = jp_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return [], None

        marker_idx = None
        marker_tokens = [img_path.name, img_path.stem, f"![illustration]({img_path.name})"]
        for i, line in enumerate(lines):
            if any(tok in line for tok in marker_tokens):
                marker_idx = i
                break

        if marker_idx is None:
            return [], None

        window_start = max(0, marker_idx - 40)
        window_end = min(len(lines), marker_idx + 41)
        scene_lines_raw = lines[window_start:window_end]
        # Strip ruby annotations: 笠{かさ}原 -> 笠原
        scene_lines = [re.sub(r"\{[^{}]*\}", "", ln) for ln in scene_lines_raw]

        manifest = self.cache_manager.get_manifest()
        metadata_en = manifest.get("metadata_en", {}) if isinstance(manifest, dict) else {}
        profiles = metadata_en.get("character_profiles", {}) if isinstance(metadata_en, dict) else {}
        character_names = metadata_en.get("character_names", {}) if isinstance(metadata_en, dict) else {}
        if not isinstance(profiles, dict):
            return [], None

        candidates: List[Dict[str, Any]] = []
        canonical_name_map: Dict[str, str] = {}
        if isinstance(character_names, dict):
            for jp_name, en_name in character_names.items():
                jp = str(jp_name).strip()
                en = str(en_name).strip()
                if jp and en:
                    canonical_name_map[en] = jp

        profile_rows: List[Dict[str, Any]] = []
        for jp_name, profile in profiles.items():
            if jp_name == "Unknown" or not isinstance(profile, dict):
                continue

            canonical_name = str(profile.get("full_name", "")).strip()
            if not canonical_name:
                canonical_name = canonical_name_map.get(str(jp_name).strip(), "")
            if not canonical_name:
                continue

            ruby_base = str(profile.get("ruby_base", "")).strip()
            alias_tokens = self._build_jp_alias_tokens(
                profile_key=str(jp_name),
                profile=profile,
                canonical_name=canonical_name,
            )
            if not alias_tokens:
                continue

            profile_rows.append({
                "canonical_name": canonical_name,
                "japanese_name": ruby_base or canonical_name,
                "visual_identity_non_color": profile.get("visual_identity_non_color"),
                "alias_tokens": alias_tokens,
            })

        token_owner_count: Dict[str, int] = {}
        for row in profile_rows:
            for token in set(row.get("alias_tokens", [])):
                token_owner_count[token] = token_owner_count.get(token, 0) + 1

        for row in profile_rows:
            match_score = 0.0
            matched_tokens: List[str] = []
            for offset, line in enumerate(scene_lines):
                line_no = window_start + offset
                distance = abs(line_no - marker_idx)
                proximity_weight = 1.0 / (1.0 + float(distance))
                for token in row.get("alias_tokens", []):
                    owner_count = token_owner_count.get(token, 1)
                    if owner_count > 1 and len(token) <= 3:
                        continue
                    uniqueness_weight = 1.0 / float(owner_count * owner_count)
                    if len(token) == 1:
                        hit = re.search(
                            rf"{re.escape(token)}(?:さん|君|ちゃん|くん|は|が|を|に|と|、|。|！|？)",
                            line,
                        ) is not None
                    else:
                        hit = token in line
                    if hit:
                        match_score += proximity_weight * uniqueness_weight
                        matched_tokens.append(token)

            if match_score <= 0:
                continue

            visual_non_color = row.get("visual_identity_non_color")
            candidates.append({
                "canonical_name": row.get("canonical_name", ""),
                "japanese_name": row.get("japanese_name", ""),
                "visual_identity_non_color": visual_non_color if isinstance(visual_non_color, (dict, list, str)) else "",
                "match_score": round(match_score, 4),
                "matched_tokens": sorted(set(matched_tokens)),
            })

        if candidates:
            candidates.sort(
                key=lambda c: (
                    -float(c.get("match_score", 0.0)),
                    str(c.get("canonical_name", "")),
                )
            )
            best_score = float(candidates[0].get("match_score", 0.0))
            if best_score > 0:
                floor = best_score * 0.25
                candidates = [c for c in candidates if float(c.get("match_score", 0.0)) >= floor][:8]

        source_anchor = f"{source_file}:{marker_idx + 1}"
        return candidates, source_anchor

    @staticmethod
    def _expand_jp_name_tokens(raw_name: str) -> List[str]:
        """Expand a JP name string into matchable tokens."""
        name = str(raw_name or "").strip()
        if not name:
            return []
        tokens = set()
        collapsed = re.sub(r"[ \u3000]", "", name)
        if collapsed:
            tokens.add(collapsed)
        for part in re.split(r"[ \u3000・･／/,，、]+", name):
            token = part.strip()
            if token:
                tokens.add(token)
        return sorted(tokens, key=len, reverse=True)

    def _build_jp_alias_tokens(
        self,
        *,
        profile_key: str,
        profile: Dict[str, Any],
        canonical_name: str,
    ) -> List[str]:
        """Collect JP-side alias tokens for scene-local matching."""
        aliases = set()
        if any(ord(ch) > 127 for ch in profile_key):
            aliases.update(self._expand_jp_name_tokens(profile_key))

        ruby_base = str(profile.get("ruby_base", "")).strip()
        if ruby_base:
            aliases.update(self._expand_jp_name_tokens(ruby_base))

        if canonical_name:
            aliases.update(self._expand_jp_name_tokens(canonical_name))

        nickname = str(profile.get("nickname", "")).strip()
        if nickname:
            for part in re.split(r"[,\u3001\uFF0C/／|]+", nickname):
                piece = part.strip()
                if any(ord(ch) > 127 for ch in piece):
                    aliases.update(self._expand_jp_name_tokens(piece))

        raw_aliases = profile.get("aliases")
        if isinstance(raw_aliases, list):
            for item in raw_aliases:
                token = str(item).strip()
                if any(ord(ch) > 127 for ch in token):
                    aliases.update(self._expand_jp_name_tokens(token))
        elif isinstance(raw_aliases, str):
            for part in re.split(r"[,\u3001\uFF0C/／|]+", raw_aliases):
                token = part.strip()
                if any(ord(ch) > 127 for ch in token):
                    aliases.update(self._expand_jp_name_tokens(token))

        return sorted({t for t in aliases if t}, key=len, reverse=True)

    @staticmethod
    def _format_identity_hint(identity_value: Any) -> str:
        """Render compact non-color identity hint."""
        if isinstance(identity_value, str):
            return identity_value.strip()[:200]
        if isinstance(identity_value, list):
            vals = [str(v).strip() for v in identity_value if str(v).strip()]
            return ", ".join(vals[:4])[:200]
        if isinstance(identity_value, dict):
            chunks: List[str] = []
            for key in ("hairstyle", "clothing_signature", "expression_signature", "posture_signature", "identity_summary"):
                value = identity_value.get(key)
                if isinstance(value, str) and value.strip():
                    chunks.append(value.strip())
                elif isinstance(value, list):
                    vals = [str(v).strip() for v in value if str(v).strip()]
                    if vals:
                        chunks.append(", ".join(vals[:3]))
            return " | ".join(chunks[:3])[:220]
        return ""

    def _build_scene_candidate_prompt(
        self,
        img_path: Path,
    ) -> Tuple[str, List[str], bool, Optional[str]]:
        """
        Build scene-local candidate prompt block.

        Returns tuple:
            - prompt block string
            - allowed canonical names
            - multi-character expected signal
            - source anchor
        """
        candidates, source_anchor = self._scene_local_candidates(img_path)
        if not candidates:
            lines = [
                "=== SCENE-LOCAL IDENTITY CANDIDATES (RAW TEXT ANCHOR) ===",
                "No reliable JP name candidates were found near this illustration marker.",
                "Do NOT invent proper names from prior knowledge or external canon.",
                "If identity is uncertain, prefer unresolved_characters with neutral descriptors.",
                "Variation Tolerance: attire/hairstyle/expression may deviate from profile snapshots.",
            ]
            if source_anchor:
                lines.append(f"Source anchor: {source_anchor}")
            lines.extend([
                "SOURCE OF TRUTH: Multimodal is descriptive only; raw text is canonical truth.",
                "=== END SCENE-LOCAL CANDIDATES ===",
            ])
            return "\n".join(lines), [], False, source_anchor

        allowed_names = [c["canonical_name"] for c in candidates if c.get("canonical_name")]
        multi_expected = len(allowed_names) >= 2

        lines = [
            "=== SCENE-LOCAL IDENTITY CANDIDATES (RAW TEXT ANCHOR) ===",
            "Raw text near this illustration is canonical for who is present.",
            "Use ONLY the following canonical names for recognized_characters in this scene.",
            "If uncertain, keep unresolved_characters and DO NOT guess outside this list.",
            "Variation Tolerance: hairstyle, outfit, and facial expression can differ across scenes.",
            "Do NOT eliminate a candidate from one visual mismatch; use aggregate cues + text anchor.",
        ]
        if source_anchor:
            lines.append(f"Source anchor: {source_anchor}")
        for c in candidates[:10]:
            canonical = c.get("canonical_name", "")
            jp = c.get("japanese_name", "")
            score = c.get("match_score", 0.0)
            tokens = c.get("matched_tokens", [])
            lines.append(f"- {canonical} [{jp}]")
            lines.append(f"  anchor-score: {score}")
            if tokens:
                lines.append(f"  text-evidence: {', '.join(str(t) for t in tokens[:6])}")
            hint = self._format_identity_hint(c.get("visual_identity_non_color"))
            if hint:
                lines.append(f"  non-color-id: {hint}")

        lines.extend([
            "SOURCE OF TRUTH: Multimodal is descriptive only; raw text is canonical truth.",
            "=== END SCENE-LOCAL CANDIDATES ===",
        ])
        return "\n".join(lines), allowed_names, multi_expected, source_anchor

    @staticmethod
    def _coerce_identity_resolution(identity_resolution: Any) -> Dict[str, Any]:
        """Normalize identity_resolution to stable schema."""
        result = {"recognized_characters": [], "unresolved_characters": []}
        if not isinstance(identity_resolution, dict):
            return result

        recognized = identity_resolution.get("recognized_characters", [])
        if isinstance(recognized, list):
            for item in recognized:
                if not isinstance(item, dict):
                    continue
                canonical = str(item.get("canonical_name", "")).strip()
                if not canonical:
                    continue
                jp = str(item.get("japanese_name", "")).strip()
                confidence_raw = item.get("confidence", 0.0)
                try:
                    confidence = float(confidence_raw)
                except Exception:
                    confidence = 0.0
                evidence = item.get("non_color_evidence", [])
                if not isinstance(evidence, list):
                    evidence = []
                evidence = [str(v).strip() for v in evidence if str(v).strip()][:6]
                result["recognized_characters"].append({
                    "canonical_name": canonical,
                    "japanese_name": jp,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "non_color_evidence": evidence,
                })

        unresolved = identity_resolution.get("unresolved_characters", [])
        if isinstance(unresolved, list):
            result["unresolved_characters"] = [str(v).strip() for v in unresolved if str(v).strip()][:8]
        return result

    @staticmethod
    def _infer_multi_character_expected(
        visual_ground_truth: Dict[str, Any],
        scene_multi_signal: bool,
    ) -> bool:
        """Infer whether multi-character identity resolution should be present."""
        if scene_multi_signal:
            return True
        composition = str(visual_ground_truth.get("composition", "")).lower()
        cues = (
            "two characters",
            "both characters",
            "across from each other",
            "handshake",
            "face-off",
            "pair shot",
        )
        return any(cue in composition for cue in cues)

    def _validate_identity_resolution(
        self,
        identity_resolution: Dict[str, Any],
        *,
        allowed_names: List[str],
        multi_expected: bool,
        text_mentions: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Validate and sanitize identity_resolution against scene-local candidates.
        """
        normalized = self._coerce_identity_resolution(identity_resolution)
        recognized = normalized.get("recognized_characters", [])
        unresolved = normalized.get("unresolved_characters", [])

        allowed_set = {str(n).strip() for n in allowed_names if str(n).strip()}
        out_of_candidate: List[str] = []
        if allowed_set:
            kept = []
            for item in recognized:
                canonical = str(item.get("canonical_name", "")).strip()
                if canonical in allowed_set:
                    kept.append(item)
                else:
                    out_of_candidate.append(canonical)
                    unresolved.append(f"out_of_candidate:{canonical}")
            recognized = kept
            normalized["recognized_characters"] = recognized
            normalized["unresolved_characters"] = sorted(set(unresolved))

        recognized_names = sorted({str(item.get("canonical_name", "")).strip() for item in recognized if str(item.get("canonical_name", "")).strip()})
        text_mentioned_names = sorted({str(n).strip() for n in (text_mentions or []) if str(n).strip()})

        status = "pass"
        reason = "ok"
        if out_of_candidate:
            status = "fail"
            reason = "out_of_candidate_names"
        elif recognized_names and text_mentioned_names and set(recognized_names) != set(text_mentioned_names):
            status = "fail"
            reason = "text_vs_identity_conflict"
        elif multi_expected and not recognized:
            status = "fail"
            reason = "missing_recognized_for_multi_character_scene"
        elif multi_expected and len(recognized) == 1:
            status = "warn"
            reason = "single_recognized_for_multi_character_scene"
        elif not allowed_set:
            status = "warn"
            reason = "no_scene_local_candidates_available"

        validation = {
            "identity_consistency": {
                "status": status,
                "reason": reason,
                "out_of_candidate_names": out_of_candidate,
                "text_mentioned_names": text_mentioned_names,
                "recognized_names": recognized_names,
            },
            "recognized_count": len(recognized),
            "multi_character_expected": bool(multi_expected),
            "allowed_candidates": sorted(allowed_set),
            "checked_at": datetime.now().isoformat(),
        }
        return normalized, validation

    @staticmethod
    def _extract_canonical_mentions_from_visual(
        visual_ground_truth: Dict[str, Any],
        candidate_names: List[str],
    ) -> List[str]:
        """Extract canonical name mentions from visual fields for consistency checks."""
        if not isinstance(visual_ground_truth, dict) or not candidate_names:
            return []
        chunks: List[str] = [
            str(visual_ground_truth.get("composition", "")),
            str(visual_ground_truth.get("emotional_delta", "")),
        ]
        key_details = visual_ground_truth.get("key_details", {})
        if isinstance(key_details, dict):
            chunks.extend(str(v) for v in key_details.values())
        directives = visual_ground_truth.get("narrative_directives", [])
        if isinstance(directives, list):
            chunks.extend(str(v) for v in directives)
        text = "\n".join(chunks)

        mentions: List[str] = []
        for name in candidate_names:
            if not name:
                continue
            if re.search(rf"\b{re.escape(name)}\b", text):
                mentions.append(name)
        return sorted(set(mentions))

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

        inline_illustrations: List[Path] = []

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
                    inline_illustrations.append(img_file)
                if inline_illustrations:
                    logger.info(f"[PHASE 1.6] Found {len(inline_illustrations)} inline illustration(s)")
                    break

        # 2. Kuchie color plates: _assets/kuchie/ or _assets/illustrations/
        # Accept both kuchie-NNN and k### naming patterns
        kuchie_files: List[Path] = []
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

        # 3. Cover art: _assets/cover.*
        cover_files: List[Path] = []
        for cover_path in assets_dir.glob("cover.*"):
            if cover_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                logger.info(f"[PHASE 1.6] Found cover art: {cover_path.name}")
                cover_files.append(cover_path)
                break

        # Processing priority:
        # 1) Kuchie (color plates) first for strongest identity grounding
        # 2) Inline illustrations
        # 3) Cover art
        illustrations: List[Path] = []
        seen_paths = set()
        for img_path in kuchie_files + inline_illustrations + cover_files:
            resolved = str(img_path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            illustrations.append(img_path)

        if not illustrations:
            logger.warning(f"[PHASE 1.6] No illustrations found in {assets_dir}")
            return {"total": 0, "cached": 0, "generated": 0, "blocked": 0}

        logger.info(f"[PHASE 1.6] Found {len(illustrations)} illustrations to process")
        logger.info(
            "[PHASE 1.6] Processing priority: kuchie (color) -> inline illustrations -> cover"
        )
        if self.identity_lock_status.get("enabled"):
            logger.info(
                "[PHASE 1.6] Identity lock active BEFORE analysis: "
                f"manifest canon={self.identity_lock_status.get('manifest_canon', 0)}, "
                f"bible canon={self.identity_lock_status.get('bible_canon', 0)}"
            )
        else:
            logger.warning("[PHASE 1.6] Identity lock unavailable before analysis (base prompt fallback)")
        stats = {"total": len(illustrations), "cached": 0, "generated": 0, "blocked": 0}

        for img_path in illustrations:
            illust_id = img_path.stem
            current_key = VisualCacheManager.compute_cache_key(
                img_path, self.analysis_prompt, self.model
            )

            scene_prompt, allowed_candidates, scene_multi_expected, source_anchor = self._build_scene_candidate_prompt(img_path)

            # Check if regeneration needed
            existing_entry = self.cache_manager.cache.get(illust_id)
            if not VisualCacheManager.should_regenerate(
                existing_entry,
                current_key,
                force_override=self.force_override,
            ):
                status = existing_entry.get("status", "cached")
                logger.info(f"  [SKIP] {illust_id}: Using existing cache (status={status})")
                stats["cached"] += 1
                continue

            # Process illustration
            logger.info(f"  [ANALYZE] {illust_id}: Running visual analysis...")
            start_time = time.time()

            try:
                analysis = self._analyze_illustration(img_path, prompt_override=scene_prompt)
                elapsed = time.time() - start_time

                visual_ground_truth = analysis.get("visual_ground_truth", {})
                identity_resolution = analysis.get("identity_resolution", {})
                multi_expected = self._infer_multi_character_expected(
                    visual_ground_truth if isinstance(visual_ground_truth, dict) else {},
                    scene_multi_expected,
                )
                text_mentions = self._extract_canonical_mentions_from_visual(
                    visual_ground_truth if isinstance(visual_ground_truth, dict) else {},
                    allowed_candidates,
                )
                identity_resolution, validation = self._validate_identity_resolution(
                    identity_resolution if isinstance(identity_resolution, dict) else {},
                    allowed_names=allowed_candidates,
                    multi_expected=multi_expected,
                    text_mentions=text_mentions,
                )

                final_status = analysis.get("status", "cached")
                if (
                    final_status == "cached"
                    and validation.get("identity_consistency", {}).get("status") == "fail"
                ):
                    final_status = "needs_review"
                    logger.warning(
                        f"  [REVIEW] {illust_id}: identity consistency failed "
                        f"({validation.get('identity_consistency', {}).get('reason')})"
                    )

                if final_status == "safety_blocked":
                    stats["blocked"] += 1
                    logger.warning(f"  [BLOCKED] {illust_id}: Safety filter ({elapsed:.1f}s)")
                else:
                    stats["generated"] += 1
                    logger.info(f"  [DONE] {illust_id}: Analysis complete ({elapsed:.1f}s, status={final_status})")

                # Save to cache
                self.cache_manager.set_entry(illust_id, {
                    "status": final_status,
                    "cache_key": current_key,
                    "cache_version": "1.0",
                    "generated_at": datetime.now().isoformat(),
                    "model": self.model,
                    "thinking_level": self.thinking_level,
                    "visual_ground_truth": visual_ground_truth,
                    "spoiler_prevention": analysis.get("spoiler_prevention", {}),
                    "identity_resolution": identity_resolution,
                    "scene_local_candidates": allowed_candidates,
                    "source_anchor": source_anchor,
                    "multi_character_expected": multi_expected,
                    "validation": validation,
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
            
            logger.info(
                f"[PHASE 1.6] Post-analysis canon reconciliation applied "
                f"from {len(profiles)} character profiles"
            )
            
        except Exception as e:
            logger.warning(f"[PHASE 1.6] Failed to inject canon names: {e}")

    def _analyze_illustration(self, img_path: Path, prompt_override: str = "") -> Dict[str, Any]:
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
                return self._call_gemini_vision(image_part, attempt, prompt_override=prompt_override)
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

    def _call_gemini_vision(self, image_part, attempt: int = 1, prompt_override: str = "") -> Dict[str, Any]:
        """Execute a single Gemini Vision API call with timeout."""
        from google.genai import types

        try:
            prompt_text = self.analysis_prompt
            if prompt_override:
                prompt_text = f"{prompt_text}\n\n{prompt_override}"

            response = self.genai_client.models.generate_content(
                model=self.model,
                contents=[prompt_text, image_part],
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

            # Parse JSON response (with one strict retry when output is malformed)
            analysis = self._parse_analysis_json(response_text)
            if analysis.get("_parse_failed"):
                strict_prompt = (
                    f"{prompt_text}\n\n"
                    "STRICT JSON RETRY:\n"
                    "Return exactly one valid JSON object (no markdown, no prose).\n"
                    "Required keys: composition, emotional_delta, key_details, "
                    "narrative_directives, spoiler_prevention, identity_resolution.\n"
                )
                retry_response = self.genai_client.models.generate_content(
                    model=self.model,
                    contents=[strict_prompt, image_part],
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(
                            include_thoughts=True,
                            thinking_level=self.thinking_level
                        ),
                        temperature=0.2,
                        max_output_tokens=4096,
                    )
                )
                retry_text = ""
                if retry_response.candidates and retry_response.candidates[0].content:
                    for part in retry_response.candidates[0].content.parts:
                        if part.text and not (hasattr(part, "thought") and part.thought):
                            retry_text += part.text
                analysis_retry = self._parse_analysis_json(retry_text)
                if not analysis_retry.get("_parse_failed"):
                    analysis = analysis_retry

            return {
                "status": "cached",
                "visual_ground_truth": {
                    "composition": analysis.get("composition", ""),
                    "emotional_delta": analysis.get("emotional_delta", ""),
                    "key_details": analysis.get("key_details", {}),
                    "narrative_directives": analysis.get("narrative_directives", []),
                },
                "spoiler_prevention": analysis.get("spoiler_prevention", {}),
                "identity_resolution": analysis.get("identity_resolution", {}),
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

    def _extract_first_json_object(self, text: str) -> Optional[str]:
        """
        Extract first balanced JSON object from mixed text.

        Handles prose wrappers around JSON and ignores braces inside quoted strings.
        """
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False

        for idx in range(start, len(text)):
            ch = text[idx]

            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == "\"":
                    in_string = False
                continue

            if ch == "\"":
                in_string = True
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]

        return None

    def _repair_json_text(self, raw: str) -> str:
        """
        Apply conservative JSON repairs for common model-formatting issues.

        - Normalize smart quotes to ASCII
        - Remove trailing commas before } or ]
        """
        repaired = raw
        repaired = repaired.replace("\u201c", "\"").replace("\u201d", "\"")
        repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
        return repaired

    def _parse_analysis_json(self, text: str) -> Dict[str, Any]:
        """Parse visual analysis JSON with resilient fallback/repair passes."""
        # Strip markdown code fences if present
        cleaned = text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = cleaned.strip()

        candidates: List[str] = []
        if cleaned:
            candidates.append(cleaned)

        extracted = self._extract_first_json_object(cleaned)
        if extracted and extracted not in candidates:
            candidates.append(extracted)

        last_error: Optional[Exception] = None
        for candidate in candidates:
            # Pass 1: strict
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                last_error = e

            # Pass 2: conservative repair (trailing commas, smart quotes)
            repaired = self._repair_json_text(candidate)
            if repaired != candidate:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError as e:
                    last_error = e

        logger.warning(f"[PHASE 1.6] Failed to parse analysis JSON: {last_error}")
        logger.debug(f"[PHASE 1.6] Raw response: {text[:200]}...")
        # Return a best-effort fallback
        return {
            "composition": cleaned[:200] if cleaned else "Parse error",
            "emotional_delta": "Analysis produced non-JSON output",
            "key_details": {},
            "narrative_directives": ["Raw analysis available in thought logs"],
            "spoiler_prevention": {},
            "identity_resolution": {"recognized_characters": [], "unresolved_characters": []},
            "_parse_failed": True,
        }
