"""
Rich Metadata Cache Updater (Phase 1.55)
========================================

Runs after Phase 1.5 metadata processing and before Phase 1.6 multimodal.

Workflow:
1. Resolve/load bible continuity for the target volume.
2. Build one full-volume JP cache (all chapter source markdown).
3. Call Gemini 2.5 Flash (temperature 0.5) with cached volume context.
4. Merge returned rich metadata patch into manifest metadata_<lang>.
5. Run context offload co-processors and write .context caches:
   - character_registry.json
   - cultural_glossary.json
   - timeline_map.json
   - idiom_transcreation_cache.json (with Google Search grounding)
6. Push enriched profile data back to the series bible when available.
"""

import argparse
import datetime
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from google.genai import types
except Exception:
    types = None

from pipeline.common.gemini_client import GeminiClient
from pipeline.config import PIPELINE_ROOT, WORK_DIR, get_target_language

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("RichMetadataCache")


class RichMetadataCacheUpdater:
    """Cache full LN JP context and enrich rich metadata fields."""

    MODEL_NAME = "gemini-2.5-flash"
    TEMPERATURE = 0.5
    CACHE_TTL_SECONDS = 7200
    PROCESSOR_MAX_OUTPUT_TOKENS = 24576
    CONTEXT_DIR = ".context"
    CONTEXT_PROCESSOR_FILES = {
        "character_context": "character_registry.json",
        "cultural_context": "cultural_glossary.json",
        "temporal_context": "timeline_map.json",
        "idiom_transcreation": "idiom_transcreation_cache.json",
    }

    # Keep translation outputs untouched in this phase.
    PROTECTED_FIELDS = {
        "title_en",
        "author_en",
        "illustrator_en",
        "publisher_en",
        "series_en",
        "character_names",
        "chapters",
        "target_language",
        "language_code",
        "glossary",
        "translation_timestamp",
    }
    # Restrict patch structure to v4.0 fields (bible + rich metadata).
    ALLOWED_PATCH_FIELDS = {
        "character_profiles",
        "localization_notes",
        "world_setting",
        "geography",
        "weapons_artifacts",
        "organizations",
        "cultural_terms",
        "mythology",
        "translation_rules",
        "dialogue_patterns",
        "scene_contexts",
        "emotional_pronoun_shifts",
        "translation_guidelines",
        "schema_version",
        "official_localization",
    }

    PLACEHOLDER_TOKENS = (
        "[to be filled",
        "[to be determined",
        "[identify",
        "[fill",
        "tbd",
    )

    def __init__(
        self,
        work_dir: Path,
        target_language: Optional[str] = None,
        cache_only: bool = False,
    ):
        self.work_dir = work_dir
        self.manifest_path = work_dir / "manifest.json"
        self.schema_spec_path = PIPELINE_ROOT / "SCHEMA_V3.9_AGENT.md"
        self.target_language = target_language or get_target_language()
        self.metadata_key = f"metadata_{self.target_language}"
        self.client = GeminiClient(model=self.MODEL_NAME, enable_caching=True)
        self.manifest: Dict[str, Any] = {}
        self.cache_only = cache_only

    def run(self) -> bool:
        if not self.manifest_path.exists():
            logger.error(f"Manifest not found: {self.manifest_path}")
            return False

        self.manifest = self._load_manifest()
        self._ensure_ruby_names()
        volume_id = self.manifest.get("volume_id", self.work_dir.name)

        logger.info("Starting Phase 1.55 rich metadata cache update")
        logger.info(f"Volume: {volume_id}")
        logger.info(f"Model: {self.MODEL_NAME} (temperature={self.TEMPERATURE})")
        if self.cache_only:
            logger.info("Mode: cache_only (skip metadata patch merge)")

        bible_sync = None
        pull_result = None
        try:
            from pipeline.metadata_processor.bible_sync import BibleSyncAgent

            bible_sync = BibleSyncAgent(self.work_dir, PIPELINE_ROOT)
            if bible_sync.resolve(self.manifest):
                if bible_sync.series_id and self.manifest.get("bible_id") != bible_sync.series_id:
                    self.manifest["bible_id"] = bible_sync.series_id
                    # Persist immediately so linkage survives downstream API failures.
                    self._save_manifest()
                    logger.info(f"Linked manifest to bible_id: {bible_sync.series_id}")
                pull_result = bible_sync.pull(self.manifest)
                logger.info(f"Bible continuity loaded: {pull_result.summary()}")
            else:
                logger.info("No bible linked/resolved for this volume; running manifest-only enrichment")
        except Exception as e:
            logger.warning(f"Bible continuity load failed (continuing): {e}")

        full_volume_text, cache_stats = self._build_full_volume_payload()
        if not full_volume_text:
            logger.error("No JP chapter content found. Cannot build full-LN cache.")
            self._mark_pipeline_state(
                status="failed",
                error="No JP chapter content available for cache payload",
                cache_stats=cache_stats,
            )
            self._save_manifest()
            return False

        system_instruction = self._build_system_instruction()
        scene_plan_index = self._load_scene_plan_index()
        context_processor_stats: Dict[str, Any] = {
            "status": "not_started",
            "processors": {},
            "output_files": [],
        }

        if self.cache_only:
            cache_name = None
            used_external_cache = False
            cache_error: Optional[str] = None
            try:
                cache_name = self.client.create_cache(
                    model=self.MODEL_NAME,
                    system_instruction=system_instruction,
                    contents=[full_volume_text],
                    ttl_seconds=self.CACHE_TTL_SECONDS,
                    display_name=f"{volume_id}_richmeta_cacheonly",
                )
                if cache_name:
                    used_external_cache = True
                    logger.info(
                        f"[CACHE] Full-LN cache created (cache-only): {cache_name} "
                        f"({cache_stats.get('cached_chapters', 0)}/{cache_stats.get('target_chapters', 0)} chapters)"
                    )
                else:
                    logger.warning("[CACHE] Full-LN cache creation failed in cache-only mode")
            except Exception as e:
                cache_error = str(e)[:500]
                logger.warning(
                    "Cache-only run could not create external cache; "
                    f"continuing in fallback mode: {cache_error}"
                )
            finally:
                if cache_name:
                    self.client.delete_cache(cache_name)

            metadata_snapshot = self._get_metadata_block()
            context_processor_stats = self._run_context_processors(
                full_volume_text=full_volume_text,
                metadata_en=metadata_snapshot,
                cache_stats=cache_stats,
                scene_plan_index=scene_plan_index,
            )

            if not used_external_cache:
                fallback_reason = (
                    cache_error
                    if cache_error
                    else "Cache-only mode could not create external full-LN cache"
                )
                logger.warning(
                    "[CACHE] Cache-only fallback: external full-LN cache unavailable. "
                    "Proceeding without cache verification."
                )
                self._mark_pipeline_state(
                    status="completed",
                    error=f"fallback_no_external_cache: {fallback_reason}",
                    cache_stats=cache_stats,
                    used_external_cache=False,
                    mode="cache_only",
                    context_processor_stats=context_processor_stats,
                )
                self._save_manifest()
                logger.info(
                    "Phase 1.55 cache-only complete in FALLBACK mode: "
                    f"external cache not verified ({cache_stats.get('cached_chapters', 0)}/"
                    f"{cache_stats.get('target_chapters', 0)} chapters payload prepared)."
                )
                return True

            self._mark_pipeline_state(
                status="completed",
                cache_stats=cache_stats,
                used_external_cache=True,
                output_tokens=0,
                patch_keys=[],
                mode="cache_only",
                context_processor_stats=context_processor_stats,
            )
            self._save_manifest()
            logger.info(
                "Phase 1.55 cache-only complete: full-LN cache path verified "
                f"({cache_stats.get('cached_chapters', 0)}/{cache_stats.get('target_chapters', 0)} chapters)."
            )
            return True

        prompt = self._build_prompt(
            metadata_en=self._get_metadata_block(),
            bible_context=(pull_result.context_block if pull_result else ""),
            cache_stats=cache_stats,
        )

        response = None
        cache_name = None
        used_external_cache = False
        try:
            cache_name = self.client.create_cache(
                model=self.MODEL_NAME,
                system_instruction=system_instruction,
                contents=[full_volume_text],
                ttl_seconds=self.CACHE_TTL_SECONDS,
                display_name=f"{volume_id}_richmeta",
            )
            if cache_name:
                used_external_cache = True
                logger.info(
                    f"[CACHE] Full-LN cache created: {cache_name} "
                    f"({cache_stats.get('cached_chapters', 0)}/{cache_stats.get('target_chapters', 0)} chapters)"
                )
                response = self.client.generate(
                    prompt=prompt,
                    temperature=self.TEMPERATURE,
                    model=self.MODEL_NAME,
                    cached_content=cache_name,
                )
            else:
                logger.warning("[CACHE] Full-LN cache creation failed; using direct prompt mode")
                response = self.client.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=self.TEMPERATURE,
                    model=self.MODEL_NAME,
                )
        except Exception as e:
            logger.error(f"Gemini enrichment call failed: {e}")
            self._mark_pipeline_state(
                status="failed",
                error=str(e)[:500],
                cache_stats=cache_stats,
                used_external_cache=used_external_cache,
            )
            self._save_manifest()
            return False
        finally:
            if cache_name:
                self.client.delete_cache(cache_name)

        if not response or not response.content:
            logger.error("Gemini returned empty content for rich metadata update")
            self._mark_pipeline_state(
                status="failed",
                error="Empty Gemini response content",
                cache_stats=cache_stats,
                used_external_cache=used_external_cache,
            )
            self._save_manifest()
            return False

        try:
            payload = self._parse_json_response(response.content)
            patch = payload.get("metadata_en_patch", payload)
            if not isinstance(patch, dict):
                raise ValueError("Response did not include a valid metadata_en_patch object")
            patch = self._sanitize_patch(patch)
        except Exception as e:
            logger.error(f"Failed to parse rich metadata patch: {e}")
            self._mark_pipeline_state(
                status="failed",
                error=f"Patch parse error: {str(e)[:420]}",
                cache_stats=cache_stats,
                used_external_cache=used_external_cache,
            )
            self._save_manifest()
            return False

        metadata_block = self._get_metadata_block()
        filtered_patch = self._filter_patch_to_placeholders(metadata_block, patch)
        merged_metadata = self._deep_merge_dict(metadata_block, filtered_patch)
        visual_backfilled = self._backfill_visual_identity_non_color(merged_metadata)
        if visual_backfilled:
            logger.info(f"Visual identity backfilled: {visual_backfilled} profile(s)")
        self._set_metadata_block(merged_metadata)
        self._save_metadata_file(merged_metadata)

        patch_path = self.work_dir / "rich_metadata_cache_patch.json"
        try:
            with open(patch_path, "w", encoding="utf-8") as f:
                json.dump(filtered_patch, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not write patch artifact: {e}")

        if bible_sync and getattr(bible_sync, "bible", None):
            try:
                event_stats = self._push_volume_event_metadata_only(bible_sync, merged_metadata)
                logger.info(
                    "Bible event sync complete: "
                    f"updated={event_stats['updated']}, skipped={event_stats['skipped']}, "
                    f"missing_in_bible={event_stats['missing_in_bible']}"
                )
            except Exception as e:
                logger.warning(f"Bible PUSH after rich update failed (non-fatal): {e}")

        context_processor_stats = self._run_context_processors(
            full_volume_text=full_volume_text,
            metadata_en=merged_metadata,
            cache_stats=cache_stats,
            scene_plan_index=scene_plan_index,
        )

        self._mark_pipeline_state(
            status="completed",
            cache_stats=cache_stats,
            used_external_cache=used_external_cache,
            output_tokens=getattr(response, "output_tokens", 0),
            patch_keys=sorted(list(filtered_patch.keys())),
            mode="full",
            context_processor_stats=context_processor_stats,
        )
        self._save_manifest()

        logger.info(
            "Phase 1.55 complete: rich metadata merged "
            f"({len(filtered_patch)} top-level keys, cache_used={used_external_cache})"
        )
        return True

    def _ensure_ruby_names(self) -> None:
        """
        Ruby name extraction is intentionally disabled in Phase 1.55.

        Canon character metadata should come from grounding/bible sync flows,
        not ruby extraction fallback.
        """
        logger.debug("Ruby extraction/recording disabled in RichMetadataCache")

    def _load_manifest(self) -> Dict[str, Any]:
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_manifest(self) -> None:
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

    def _save_metadata_file(self, metadata: Dict[str, Any]) -> None:
        """Persist merged rich metadata to metadata_<lang>.json as translator source-of-truth."""
        metadata_path = self.work_dir / f"metadata_{self.target_language}.json"
        try:
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not write {metadata_path.name}: {e}")

    def _get_manifest_chapters(self) -> List[Dict[str, Any]]:
        chapters = self.manifest.get("chapters", [])
        if not chapters:
            chapters = self.manifest.get("structure", {}).get("chapters", [])
        return chapters if isinstance(chapters, list) else []

    def _build_full_volume_payload(self) -> Tuple[str, Dict[str, Any]]:
        chapter_blocks: List[str] = []
        cached_chapter_ids: List[str] = []
        missing_chapter_ids: List[str] = []

        chapters = self._get_manifest_chapters()
        for chapter in chapters:
            chapter_id = chapter.get("id", "unknown")
            jp_file = chapter.get("jp_file") or chapter.get("source_file")
            if not jp_file:
                missing_chapter_ids.append(chapter_id)
                continue

            source_path = self.work_dir / "JP" / jp_file
            if not source_path.exists():
                missing_chapter_ids.append(chapter_id)
                continue

            try:
                jp_text = source_path.read_text(encoding="utf-8")
                chapter_blocks.append(f"<CHAPTER id='{chapter_id}'>\n{jp_text}\n</CHAPTER>")
                cached_chapter_ids.append(chapter_id)
            except Exception:
                missing_chapter_ids.append(chapter_id)

        payload = "\n\n---\n\n".join(chapter_blocks)
        stats = {
            "target_chapters": len(chapters),
            "cached_chapters": len(cached_chapter_ids),
            "cached_chapter_ids": cached_chapter_ids,
            "missing_chapter_ids": missing_chapter_ids,
            "volume_chars": len(payload),
        }
        return payload, stats

    def _build_system_instruction(self) -> str:
        base_instruction = (
            "You are the Phase 1.55 Rich Metadata Updater for MTL Studio.\n"
            "Use the cached full Japanese LN text to refine rich metadata quality.\n"
            "Return JSON only. No markdown.\n"
            "Output shape:\n"
            "{\n"
            '  "metadata_en_patch": {\n'
            '    "character_profiles": {...},\n'
            '    "localization_notes": {...},\n'
            '    "world_setting": {...},\n'
            '    "geography": {...},\n'
            '    "weapons_artifacts": {...},\n'
            '    "organizations": {...},\n'
            '    "cultural_terms": {...},\n'
            '    "mythology": {...},\n'
            '    "translation_rules": {...},\n'
            '    "dialogue_patterns": {...},\n'
            '    "scene_contexts": {...},\n'
            '    "emotional_pronoun_shifts": {...},\n'
            '    "translation_guidelines": {...},\n'
            '    "official_localization": {...},\n'
            '    "schema_version": "v4.0_cached_enrichment"\n'
            "  }\n"
            "}\n"
            "Rules:\n"
            "0) Scan the ENTIRE cached LN corpus before deciding updates.\n"
            "1) Keep Japanese surname-first order for Japanese characters (absolute).\n"
            "2) Follow v4.0 schema structure exactly for metadata_en_patch fields.\n"
            "3) ONLY fill blank/placeholder values. Do NOT overwrite already-populated fields.\n"
            "4) Do NOT modify title_en/author_en/chapter title fields/character_names/glossary.\n"
            "5) Keep unknown values empty instead of guessing.\n"
            "6) Prefer concrete character evidence from cached chapter text.\n"
            "7) Maintain character_profiles.*.visual_identity_non_color with non-color identity markers:\n"
            "   hairstyle, outfit silhouette/signature, expression baseline, posture/gesture, accessories.\n"
            "8) Keep Bible-compatible continuity fields schema-safe: world_setting/geography/weapons_artifacts/"
            "organizations/cultural_terms/mythology/translation_rules.\n"
        )
        if self.schema_spec_path.exists():
            try:
                schema_text = self.schema_spec_path.read_text(encoding="utf-8")
                return f"{base_instruction}\n\nReference schema (v4.0):\n{schema_text}"
            except Exception:
                pass
        return base_instruction

    def _build_prompt(
        self,
        metadata_en: Dict[str, Any],
        bible_context: str,
        cache_stats: Dict[str, Any],
    ) -> str:
        prompt_payload = {
            "metadata": self.manifest.get("metadata", {}),
            "metadata_en_current": metadata_en,
            "cache_stats": cache_stats,
            "bible_id": self.manifest.get("bible_id", ""),
            "series_context": bible_context[:32000] if bible_context else "",
        }
        return (
            "Refine and expand rich metadata for this volume using the cached full LN text.\n"
            "Focus on character_profiles, localization_notes, dialogue/register behavior,\n"
            "and any semantic guidance that improves Phase 2 translation consistency.\n"
            "Keep Bible continuity categories aligned and schema-safe:\n"
            "world_setting, geography, weapons_artifacts, organizations, cultural_terms, mythology, translation_rules.\n"
            "For character_profiles, fill/maintain `visual_identity_non_color` with non-color descriptors.\n"
            "Directive: only fill blank or placeholder values in current metadata_en.\n"
            "Do not overwrite existing populated values.\n"
            "Return only valid JSON in the required output shape.\n\n"
            f"INPUT:\n{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"
        )

    def _get_metadata_block(self) -> Dict[str, Any]:
        metadata = self.manifest.get(self.metadata_key, {})
        if isinstance(metadata, dict) and metadata:
            return metadata
        if self.target_language == "en":
            fallback = self.manifest.get("metadata_en", {})
            if isinstance(fallback, dict):
                return fallback
        return {}

    def _set_metadata_block(self, value: Dict[str, Any]) -> None:
        self.manifest[self.metadata_key] = value
        if self.target_language == "en":
            self.manifest["metadata_en"] = value

    def _sanitize_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}
        for key, value in patch.items():
            if key in self.PROTECTED_FIELDS:
                continue
            if key not in self.ALLOWED_PATCH_FIELDS:
                continue
            cleaned[key] = value
        return cleaned

    def _is_blank_or_placeholder(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return True
            lower = s.lower()
            if lower in {"unknown", "n/a"}:
                return True
            return any(tok in lower for tok in self.PLACEHOLDER_TOKENS)
        if isinstance(value, list):
            if len(value) == 0:
                return True
            return all(self._is_blank_or_placeholder(v) for v in value)
        if isinstance(value, dict):
            if len(value) == 0:
                return True
            return all(self._is_blank_or_placeholder(v) for v in value.values())
        return False

    def _filter_patch_to_placeholders(
        self,
        current: Dict[str, Any],
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Allow patch writes only where current metadata is blank/placeholder/missing."""
        filtered: Dict[str, Any] = {}
        for key, new_value in patch.items():
            if key not in current:
                filtered[key] = new_value
                continue

            cur_value = current.get(key)
            if isinstance(new_value, dict) and isinstance(cur_value, dict):
                nested = self._filter_patch_to_placeholders(cur_value, new_value)
                if nested:
                    filtered[key] = nested
                continue

            if self._is_blank_or_placeholder(cur_value):
                filtered[key] = new_value
        return filtered

    def _deep_merge_dict(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        for key, value in patch.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge_dict(result[key], value)
            else:
                result[key] = value
        return result

    def _backfill_visual_identity_non_color(self, metadata_block: Dict[str, Any]) -> int:
        """
        Add baseline non-color visual identity payload where missing.

        Uses existing `appearance` text as a safe fallback summary.
        """
        profiles = metadata_block.get("character_profiles", {})
        if not isinstance(profiles, dict):
            return 0

        updated = 0
        for _, profile in profiles.items():
            if not isinstance(profile, dict):
                continue

            existing = profile.get("visual_identity_non_color")
            has_existing = False
            if isinstance(existing, dict):
                has_existing = any(
                    isinstance(v, str) and v.strip() or isinstance(v, list) and len(v) > 0
                    for v in existing.values()
                )
            elif isinstance(existing, str):
                has_existing = bool(existing.strip())
            elif isinstance(existing, list):
                has_existing = any(str(v).strip() for v in existing)
            if has_existing:
                continue

            appearance = profile.get("appearance")
            if isinstance(appearance, str) and appearance.strip():
                profile["visual_identity_non_color"] = {
                    "identity_summary": appearance.strip()
                }
                updated += 1

        return updated

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                raise
            return json.loads(match.group(0))

    def _extract_event_metadata(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only current-volume event/relationship metadata from character profile."""
        event_fields = {}
        for key in (
            "relationship_to_protagonist",
            "relationship_to_others",
            "rtas_relationships",
            "how_character_refers_to_others",
            "keigo_switch",
            "contraction_rate",
            "character_arc",
        ):
            value = profile_data.get(key)
            if value and not self._is_blank_or_placeholder(value):
                event_fields[key] = value

        # Preserve volume-scoped dynamics (e.g., volume_2_development)
        for key, value in profile_data.items():
            if key.lower().startswith("volume_") and value and not self._is_blank_or_placeholder(value):
                event_fields[key] = value

        return event_fields

    def _push_volume_event_metadata_only(
        self,
        bible_sync: Any,
        metadata_block: Dict[str, Any],
    ) -> Dict[str, int]:
        """Push only volume-scoped event metadata; never touch canonical naming fields."""
        bible = getattr(bible_sync, "bible", None)
        if not bible:
            return {"updated": 0, "skipped": 0, "missing_in_bible": 0}

        profiles = metadata_block.get("character_profiles", {})
        if not isinstance(profiles, dict):
            return {"updated": 0, "skipped": 0, "missing_in_bible": 0}

        volume_id = self.manifest.get("volume_id", "")
        short_id = bible_sync.bible_ctrl._extract_short_id(volume_id) or volume_id

        updated = 0
        skipped = 0
        missing_in_bible = 0

        for profile_key, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                skipped += 1
                continue

            jp_key = None
            try:
                jp_key = bible_sync._resolve_profile_key(profile_key, profile_data)
            except Exception:
                jp_key = profile_key if re.search(r'[\u3040-\u9fff]', profile_key) else None

            if not jp_key:
                skipped += 1
                continue

            char_entry = bible.data.get("characters", {}).get(jp_key)
            if not isinstance(char_entry, dict):
                missing_in_bible += 1
                continue

            event_payload = self._extract_event_metadata(profile_data)
            if not event_payload:
                skipped += 1
                continue

            volume_events = char_entry.setdefault("volume_events", {})
            if not isinstance(volume_events, dict):
                volume_events = {}
                char_entry["volume_events"] = volume_events

            existing = volume_events.get(short_id, {})
            if not isinstance(existing, dict):
                existing = {}
            merged = self._deep_merge_dict(existing, event_payload)

            if merged != existing:
                volume_events[short_id] = merged
                updated += 1
            else:
                skipped += 1

        # Keep volume registration current without altering canonical naming metadata.
        title = self.manifest.get("metadata", {}).get("title", "")
        try:
            from pipeline.metadata_processor.agent import extract_volume_number
            idx = extract_volume_number(title) or len(bible.volumes_registered) + 1
        except Exception:
            idx = len(bible.volumes_registered) + 1
        bible.register_volume(volume_id=short_id, title=title, index=idx)
        if short_id:
            try:
                bible_sync.bible_ctrl.link_volume(volume_id, bible.series_id)
            except Exception:
                pass

        if updated > 0:
            bible.save()
            entry = bible_sync.bible_ctrl.index.get("series", {}).get(bible.series_id, {})
            entry["entry_count"] = bible.entry_count()
            bible_sync.bible_ctrl._save_index()

        return {"updated": updated, "skipped": skipped, "missing_in_bible": missing_in_bible}

    def _context_dir_path(self) -> Path:
        context_dir = self.work_dir / self.CONTEXT_DIR
        context_dir.mkdir(parents=True, exist_ok=True)
        return context_dir

    def _context_output_path(self, processor_id: str) -> Path:
        filename = self.CONTEXT_PROCESSOR_FILES.get(processor_id, f"{processor_id}.json")
        return self._context_dir_path() / filename

    def _normalize_chapter_key(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        match = re.search(r"chapter[_\-\s]*0*(\d+)", raw, re.IGNORECASE)
        if not match:
            match = re.search(r"\bch[_\-\s]*0*(\d+)\b", raw, re.IGNORECASE)
        if not match:
            match = re.search(r"\b0*(\d{1,3})\b", raw)
        if not match:
            return ""
        return f"chapter_{int(match.group(1)):02d}"

    def _load_scene_plan_index(self) -> Dict[str, Dict[str, Any]]:
        plans_dir = self.work_dir / "PLANS"
        index: Dict[str, Dict[str, Any]] = {}
        if not plans_dir.exists():
            return index

        for path in sorted(plans_dir.glob("*_scene_plan.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            chapter_key = self._normalize_chapter_key(payload.get("chapter_id") or path.stem)
            if not chapter_key:
                continue

            scenes: List[Dict[str, Any]] = []
            raw_scenes = payload.get("scenes", [])
            if isinstance(raw_scenes, list):
                for scene in raw_scenes:
                    if not isinstance(scene, dict):
                        continue
                    scenes.append(
                        {
                            "id": str(scene.get("id") or "").strip(),
                            "beat_type": str(scene.get("beat_type") or "").strip(),
                            "emotional_arc": str(scene.get("emotional_arc") or "").strip(),
                            "dialogue_register": str(scene.get("dialogue_register") or "").strip(),
                            "target_rhythm": str(scene.get("target_rhythm") or "").strip(),
                            "start_paragraph": scene.get("start_paragraph"),
                            "end_paragraph": scene.get("end_paragraph"),
                            "illustration_anchor": bool(scene.get("illustration_anchor")),
                        }
                    )

            index[chapter_key] = {
                "chapter_id": chapter_key,
                "overall_tone": str(payload.get("overall_tone") or "").strip(),
                "pacing_strategy": str(payload.get("pacing_strategy") or "").strip(),
                "scenes": scenes,
            }

        return index

    def _build_processor_context_payload(
        self,
        metadata_en: Dict[str, Any],
        cache_stats: Dict[str, Any],
        scene_plan_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        metadata = self.manifest.get("metadata", {})
        char_names = metadata_en.get("character_names", {})
        profiles = metadata_en.get("character_profiles", {})

        profile_summary: Dict[str, Dict[str, Any]] = {}
        if isinstance(profiles, dict):
            for key, value in list(profiles.items())[:40]:
                if not isinstance(value, dict):
                    continue
                profile_summary[key] = {
                    "name_en": value.get("name_en", ""),
                    "role": value.get("role", ""),
                    "archetype": value.get("archetype", ""),
                    "speech_pattern": value.get("speech_pattern", ""),
                    "personality": value.get("personality", ""),
                }

        scene_summary: Dict[str, Dict[str, Any]] = {}
        for chapter_key, plan in scene_plan_index.items():
            scenes = plan.get("scenes", [])
            compact_scenes = []
            if isinstance(scenes, list):
                for scene in scenes[:24]:
                    if not isinstance(scene, dict):
                        continue
                    compact_scenes.append(
                        {
                            "id": scene.get("id"),
                            "beat_type": scene.get("beat_type"),
                            "dialogue_register": scene.get("dialogue_register"),
                            "target_rhythm": scene.get("target_rhythm"),
                            "start_paragraph": scene.get("start_paragraph"),
                            "end_paragraph": scene.get("end_paragraph"),
                        }
                    )
            scene_summary[chapter_key] = {
                "overall_tone": plan.get("overall_tone", ""),
                "pacing_strategy": plan.get("pacing_strategy", ""),
                "scene_count": len(scenes) if isinstance(scenes, list) else 0,
                "scenes": compact_scenes,
            }

        return {
            "volume_id": self.manifest.get("volume_id", self.work_dir.name),
            "book_title_jp": metadata.get("title", ""),
            "book_author_jp": metadata.get("author", ""),
            "book_genre": metadata.get("genre", ""),
            "target_language": self.target_language,
            "cache_stats": cache_stats,
            "character_names": char_names if isinstance(char_names, dict) else {},
            "character_profiles_summary": profile_summary,
            "scene_plan_summary": scene_summary,
            "existing_cultural_terms": metadata_en.get("cultural_terms", {}),
            "existing_localization_notes": metadata_en.get("localization_notes", {}),
        }

    def _generate_with_optional_cache(
        self,
        *,
        prompt: str,
        system_instruction: str,
        full_volume_text: str,
        display_name: str,
        tools: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        response = None
        cache_name = None
        try:
            cache_name = self.client.create_cache(
                model=self.MODEL_NAME,
                system_instruction=system_instruction,
                contents=[full_volume_text],
                ttl_seconds=self.CACHE_TTL_SECONDS,
                display_name=display_name,
                tools=tools,
            )
            if cache_name:
                response = self.client.generate(
                    prompt=prompt,
                    temperature=self.TEMPERATURE,
                    max_output_tokens=self.PROCESSOR_MAX_OUTPUT_TOKENS,
                    model=self.MODEL_NAME,
                    cached_content=cache_name,
                )
            else:
                response = self.client.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=self.TEMPERATURE,
                    max_output_tokens=self.PROCESSOR_MAX_OUTPUT_TOKENS,
                    model=self.MODEL_NAME,
                    tools=tools,
                )
        except Exception as e:
            logger.warning(f"[P1.55] Processor call failed ({display_name}): {e}")
            return None
        finally:
            if cache_name:
                self.client.delete_cache(cache_name)

        if not response or not response.content:
            return None
        try:
            payload = self._parse_json_response(response.content)
        except Exception as e:
            logger.warning(f"[P1.55] Processor JSON parse failed ({display_name}): {e}")
            return None
        return payload if isinstance(payload, dict) else None

    def _fallback_character_registry(self, metadata_en: Dict[str, Any]) -> Dict[str, Any]:
        characters: List[Dict[str, Any]] = []
        profiles = metadata_en.get("character_profiles", {})
        if isinstance(profiles, dict):
            for idx, (key, value) in enumerate(profiles.items(), start=1):
                if not isinstance(value, dict):
                    continue
                characters.append(
                    {
                        "id": f"char_{idx:03d}",
                        "key": key,
                        "canonical_name": value.get("name_en") or key,
                        "japanese_name": value.get("name_jp") or key,
                        "role": value.get("role", ""),
                        "archetype": value.get("archetype", ""),
                    }
                )

        return {
            "volume_id": self.manifest.get("volume_id", self.work_dir.name),
            "generated_at": datetime.datetime.now().isoformat(),
            "processor_version": "1.0",
            "characters": characters,
            "relationship_graph": {},
            "pronoun_resolution_hints": [],
            "summary": {
                "total_characters": len(characters),
                "total_relationship_edges": 0,
            },
        }

    def _fallback_cultural_glossary(self, metadata_en: Dict[str, Any]) -> Dict[str, Any]:
        terms: List[Dict[str, Any]] = []
        source_terms = metadata_en.get("cultural_terms", {})
        if isinstance(source_terms, dict):
            for key, value in list(source_terms.items())[:60]:
                if isinstance(value, dict):
                    meaning = value.get("meaning_en") or value.get("translation") or ""
                    notes = value.get("notes") or value.get("context") or ""
                else:
                    meaning = str(value)
                    notes = ""
                terms.append(
                    {
                        "term_jp": key,
                        "preferred_en": meaning,
                        "notes": notes,
                    }
                )

        return {
            "volume_id": self.manifest.get("volume_id", self.work_dir.name),
            "generated_at": datetime.datetime.now().isoformat(),
            "processor_version": "1.0",
            "terms": terms,
            "idioms": [],
            "honorific_policies": [],
            "location_terms": [],
            "summary": {
                "total_terms": len(terms),
                "total_idioms": 0,
            },
        }

    def _fallback_timeline_map(self, scene_plan_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        for chapter_key in sorted(scene_plan_index.keys()):
            plan = scene_plan_index.get(chapter_key, {})
            scenes = plan.get("scenes", [])
            timeline.append(
                {
                    "chapter_id": chapter_key,
                    "sequence_index": int(chapter_key.split("_")[-1]) if "_" in chapter_key else 0,
                    "scene_count": len(scenes) if isinstance(scenes, list) else 0,
                    "scenes": scenes if isinstance(scenes, list) else [],
                    "temporal_markers": [],
                    "continuity_constraints": [],
                }
            )

        return {
            "volume_id": self.manifest.get("volume_id", self.work_dir.name),
            "generated_at": datetime.datetime.now().isoformat(),
            "processor_version": "1.0",
            "chapter_timeline": timeline,
            "global_continuity_rules": [],
            "summary": {
                "chapter_count": len(timeline),
                "event_count": sum(item.get("scene_count", 0) for item in timeline),
            },
        }

    def _fallback_idiom_transcreation(self) -> Dict[str, Any]:
        return {
            "volume_id": self.manifest.get("volume_id", self.work_dir.name),
            "generated_at": datetime.datetime.now().isoformat(),
            "processor_version": "1.0",
            "transcreation_opportunities": [],
            "wordplay_transcreations": [],
            "summary": {
                "total_opportunities": 0,
                "by_priority": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "avg_confidence": 0.0,
            },
        }

    def _estimate_processor_items(self, processor_id: str, payload: Dict[str, Any]) -> int:
        if processor_id == "character_context":
            return len(payload.get("characters", []))
        if processor_id == "cultural_context":
            return len(payload.get("terms", [])) + len(payload.get("idioms", []))
        if processor_id == "temporal_context":
            return len(payload.get("chapter_timeline", []))
        if processor_id == "idiom_transcreation":
            return len(payload.get("transcreation_opportunities", [])) + len(payload.get("wordplay_transcreations", []))
        return 0

    def _run_context_processors(
        self,
        *,
        full_volume_text: str,
        metadata_en: Dict[str, Any],
        cache_stats: Dict[str, Any],
        scene_plan_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        context_payload = self._build_processor_context_payload(
            metadata_en=metadata_en,
            cache_stats=cache_stats,
            scene_plan_index=scene_plan_index,
        )
        if types is None:
            logger.warning(
                "[P1.55] google.genai.types unavailable; idiom transcreation processor "
                "will run without Google Search grounding."
            )
        volume_id = self.manifest.get("volume_id", self.work_dir.name)
        self._context_dir_path()

        processor_specs: List[Dict[str, Any]] = [
            {
                "id": "character_context",
                "display_name": f"{volume_id}_p155_character_ctx",
                "system_instruction": (
                    "You are Processor 1: Character Context Processor.\n"
                    "Return JSON only.\n"
                    "Task: Use full cached LN text + input context payload to build a chapter-agnostic character registry.\n"
                    "Do not invent characters not in source.\n"
                    "Output schema:\n"
                    "{\n"
                    '  "volume_id": "...",\n'
                    '  "generated_at": "...",\n'
                    '  "processor_version": "1.0",\n'
                    '  "characters": [\n'
                    "    {\n"
                    '      "id": "char_001",\n'
                    '      "canonical_name": "string",\n'
                    '      "japanese_name": "string",\n'
                    '      "aliases": ["..."],\n'
                    '      "role": "string",\n'
                    '      "voice_register": "string",\n'
                    '      "relationship_edges": [{"with":"char_002","type":"string","status":"string"}],\n'
                    '      "pronoun_hints_en": ["..."]\n'
                    "    }\n"
                    "  ],\n"
                    '  "relationship_graph": {"char_001_char_002":{"type":"string","status":"string"}},\n'
                    '  "pronoun_resolution_hints": [{"pattern":"string","likely_character":"char_001"}],\n'
                    '  "summary": {"total_characters": 0, "total_relationship_edges": 0}\n'
                    "}\n"
                ),
                "prompt": (
                    "Generate character context registry for Phase 1.55.\n"
                    "Use robust canonical naming, aliases, relationships, and pronoun disambiguation hints.\n"
                    "Prefer source-grounded evidence from full cached LN.\n"
                    f"INPUT:\n{json.dumps(context_payload, ensure_ascii=False, indent=2)}"
                ),
                "fallback_builder": self._fallback_character_registry,
                "tools": None,
            },
            {
                "id": "cultural_context",
                "display_name": f"{volume_id}_p155_cultural_ctx",
                "system_instruction": (
                    "You are Processor 2: Cultural Context Processor.\n"
                    "Return JSON only.\n"
                    "Task: Pre-resolve cultural terms, honorific handling, idioms, and location-specific context.\n"
                    "Do not force transcreation; preserve clarity and narrative flow.\n"
                    "Output schema:\n"
                    "{\n"
                    '  "volume_id": "...",\n'
                    '  "generated_at": "...",\n'
                    '  "processor_version": "1.0",\n'
                    '  "terms": [{"term_jp":"string","preferred_en":"string","notes":"string","confidence":0.0}],\n'
                    '  "idioms": [{"japanese":"string","meaning":"string","preferred_rendering":"string","confidence":0.0}],\n'
                    '  "honorific_policies": [{"pattern":"-san","strategy":"retain_or_adapt","rule":"string"}],\n'
                    '  "location_terms": [{"jp":"string","en":"string","notes":"string"}],\n'
                    '  "summary": {"total_terms":0,"total_idioms":0}\n'
                    "}\n"
                ),
                "prompt": (
                    "Generate cultural context glossary for Phase 1.55.\n"
                    "Capture terms that Stage 2 repeatedly needs.\n"
                    f"INPUT:\n{json.dumps(context_payload, ensure_ascii=False, indent=2)}"
                ),
                "fallback_builder": self._fallback_cultural_glossary,
                "tools": None,
            },
            {
                "id": "temporal_context",
                "display_name": f"{volume_id}_p155_temporal_ctx",
                "system_instruction": (
                    "You are Processor 3: Temporal Context Processor.\n"
                    "Return JSON only.\n"
                    "Task: Build chapter/scenes timeline map and continuity constraints from cached LN + scene plans.\n"
                    "Output schema:\n"
                    "{\n"
                    '  "volume_id": "...",\n'
                    '  "generated_at": "...",\n'
                    '  "processor_version": "1.0",\n'
                    '  "chapter_timeline": [\n'
                    "    {\n"
                    '      "chapter_id":"chapter_01",\n'
                    '      "sequence_index":1,\n'
                    '      "scenes":[{"id":"S01","beat_type":"setup","summary":"string","start_paragraph":0,"end_paragraph":0}],\n'
                    '      "temporal_markers":["string"],\n'
                    '      "continuity_constraints":["string"]\n'
                    "    }\n"
                    "  ],\n"
                    '  "global_continuity_rules": ["string"],\n'
                    '  "summary": {"chapter_count":0,"event_count":0}\n'
                    "}\n"
                ),
                "prompt": (
                    "Generate temporal continuity map for Phase 1.55.\n"
                    "Align with chapter scene plans when available.\n"
                    f"INPUT:\n{json.dumps(context_payload, ensure_ascii=False, indent=2)}"
                ),
                "fallback_builder": lambda data: self._fallback_timeline_map(scene_plan_index),
                "tools": None,
            },
            {
                "id": "idiom_transcreation",
                "display_name": f"{volume_id}_p155_idiom_transcreation",
                "system_instruction": (
                    "You are Processor 4: Opportunistic Idiom Transcreation Processor.\n"
                    "Return JSON only.\n"
                    "Goal: detect high-impact JP idiom/subtext/wordplay opportunities where literal EN may lose literary impact.\n"
                    "Opportunistic means: suggest options, do NOT force transcreation when literal works.\n"
                    "Grounding directive: use Google Search for idiom/proverb/cultural-subtext verification and English equivalence checks.\n"
                    "Source priority for grounding: Official Localization -> AniDB -> MyAnimeList -> Ranobe-Mori -> Fan Translation -> Heuristic Inference.\n"
                    "Output schema:\n"
                    "{\n"
                    '  "volume_id":"...",\n'
                    '  "generated_at":"...",\n'
                    '  "processor_version":"1.0",\n'
                    '  "transcreation_opportunities":[\n'
                    "    {\n"
                    '      "id":"trans_001",\n'
                    '      "location":"CHAPTER_01_LINE_123",\n'
                    '      "japanese":"string",\n'
                    '      "literal":"string",\n'
                    '      "meaning":"string",\n'
                    '      "category":"proverb|onomatopoeia|cultural_subtext|wordplay|metaphorical_imagery|body_part_idiom|set_phrase",\n'
                    '      "context":{"scene":"CH01_SC01","character_speaking":"string","emotional_tone":"string","beat_type":"string"},\n'
                    '      "transcreation_priority":"critical|high|medium|low",\n'
                    '      "confidence":0.0,\n'
                    '      "options":[\n'
                    '        {"rank":1,"text":"string","type":"english_equivalent|creative_transcreation|literal|hybrid","confidence":0.0,"reasoning":"string","register":"string","preserves_imagery":true,"preserves_meaning":true,"literary_impact":"high|medium|low"}\n'
                    "      ],\n"
                    '      "stage_2_guidance":"string"\n'
                    "    }\n"
                    "  ],\n"
                    '  "wordplay_transcreations":[\n'
                    '    {"id":"wordplay_001","location":"CHAPTER_02_LINE_210","japanese":"string","meaning":"string","transcreation_priority":"critical|high|medium|low","confidence":0.0,"options":[{"rank":1,"text":"string","confidence":0.0}]}\n'
                    "  ],\n"
                    '  "summary":{"total_opportunities":0,"by_priority":{"critical":0,"high":0,"medium":0,"low":0},"avg_confidence":0.0}\n'
                    "}\n"
                    "Constraints:\n"
                    "- Max 140 opportunities total.\n"
                    "- Keep options concise, stage-usable, and voice-aware.\n"
                    "- For low priority opportunities, literal can be rank 1.\n"
                ),
                "prompt": (
                    "Generate idiom transcreation cache for Stage 2.\n"
                    "Include confidence-ranked options and guidance, filtered for literary impact.\n"
                    "Do not over-transcreate low-priority items.\n"
                    f"INPUT:\n{json.dumps(context_payload, ensure_ascii=False, indent=2)}"
                ),
                "fallback_builder": lambda data: self._fallback_idiom_transcreation(),
                "tools": [types.Tool(google_search=types.GoogleSearch())] if types else None,
            },
        ]

        results: Dict[str, Any] = {
            "status": "completed",
            "processors": {},
            "output_files": [],
        }

        for spec in processor_specs:
            processor_id = spec["id"]
            output_path = self._context_output_path(processor_id)
            payload = self._generate_with_optional_cache(
                prompt=spec["prompt"],
                system_instruction=spec["system_instruction"],
                full_volume_text=full_volume_text,
                display_name=spec["display_name"],
                tools=spec.get("tools"),
            )
            if not isinstance(payload, dict):
                payload = spec["fallback_builder"](metadata_en)
                status = "fallback"
            else:
                status = "completed"

            if "volume_id" not in payload:
                payload["volume_id"] = self.manifest.get("volume_id", self.work_dir.name)
            if "generated_at" not in payload:
                payload["generated_at"] = datetime.datetime.now().isoformat()
            if "processor_version" not in payload:
                payload["processor_version"] = "1.0"

            try:
                output_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                item_count = self._estimate_processor_items(processor_id, payload)
                results["processors"][processor_id] = {
                    "status": status,
                    "file": str(output_path.relative_to(self.work_dir)),
                    "items": item_count,
                    "used_grounding": bool(spec.get("tools")),
                }
                results["output_files"].append(str(output_path.relative_to(self.work_dir)))
                logger.info(
                    f"[P1.55] {processor_id}: {status} -> {output_path.name} ({item_count} items)"
                )
            except Exception as e:
                results["processors"][processor_id] = {
                    "status": "failed",
                    "error": str(e)[:240],
                    "file": str(output_path.relative_to(self.work_dir)),
                }
                results["status"] = "partial"
                logger.warning(f"[P1.55] Failed writing {output_path.name}: {e}")

        has_failure = any(v.get("status") == "failed" for v in results["processors"].values())
        has_fallback = any(v.get("status") == "fallback" for v in results["processors"].values())
        if has_failure:
            results["status"] = "partial"
        elif has_fallback:
            results["status"] = "fallback"
        return results

    def _mark_pipeline_state(
        self,
        *,
        status: str,
        cache_stats: Optional[Dict[str, Any]] = None,
        used_external_cache: bool = False,
        output_tokens: int = 0,
        patch_keys: Optional[List[str]] = None,
        error: Optional[str] = None,
        mode: str = "full",
        context_processor_stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        pipeline_state = self.manifest.setdefault("pipeline_state", {})
        state = {
            "status": status,
            "timestamp": datetime.datetime.now().isoformat(),
            "model": self.MODEL_NAME,
            "temperature": self.TEMPERATURE,
            "used_external_cache": used_external_cache,
            "output_tokens": output_tokens,
            "cache_stats": cache_stats or {},
            "patch_keys": patch_keys or [],
            "mode": mode,
        }
        if context_processor_stats:
            state["context_processors"] = context_processor_stats
        if error:
            state["error"] = error
        pipeline_state["rich_metadata_cache"] = state


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1.55 rich metadata cache updater")
    parser.add_argument("--volume", type=str, required=True, help="Volume ID in WORK/")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Build/verify full-LN cache path only (skip metadata enrichment merge).",
    )
    args = parser.parse_args()

    work_dir = WORK_DIR / args.volume
    if not work_dir.exists():
        logger.error(f"Volume directory not found: {work_dir}")
        sys.exit(1)

    updater = RichMetadataCacheUpdater(work_dir, cache_only=args.cache_only)
    success = updater.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
