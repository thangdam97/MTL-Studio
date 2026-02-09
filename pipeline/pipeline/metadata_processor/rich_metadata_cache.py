"""
Rich Metadata Cache Updater (Phase 1.55)
========================================

Runs after Phase 1.5 metadata processing and before Phase 1.6 multimodal.

Workflow:
1. Resolve/load bible continuity for the target volume.
2. Build one full-volume JP cache (all chapter source markdown).
3. Call Gemini 2.5 Flash (temperature 0.5) with cached volume context.
4. Merge returned rich metadata patch into manifest metadata_<lang>.
5. Push enriched profile data back to the series bible when available.
"""

import argparse
import datetime
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    # Restrict patch structure to v3.9-rich fields only.
    ALLOWED_PATCH_FIELDS = {
        "character_profiles",
        "localization_notes",
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

    def __init__(self, work_dir: Path, target_language: Optional[str] = None):
        self.work_dir = work_dir
        self.manifest_path = work_dir / "manifest.json"
        self.schema_spec_path = PIPELINE_ROOT / "SCHEMA_V3.9_AGENT.md"
        self.target_language = target_language or get_target_language()
        self.metadata_key = f"metadata_{self.target_language}"
        self.client = GeminiClient(model=self.MODEL_NAME, enable_caching=True)
        self.manifest: Dict[str, Any] = {}

    def run(self) -> bool:
        if not self.manifest_path.exists():
            logger.error(f"Manifest not found: {self.manifest_path}")
            return False

        self.manifest = self._load_manifest()
        volume_id = self.manifest.get("volume_id", self.work_dir.name)

        logger.info("Starting Phase 1.55 rich metadata cache update")
        logger.info(f"Volume: {volume_id}")
        logger.info(f"Model: {self.MODEL_NAME} (temperature={self.TEMPERATURE})")

        bible_sync = None
        pull_result = None
        try:
            from pipeline.metadata_processor.bible_sync import BibleSyncAgent

            bible_sync = BibleSyncAgent(self.work_dir, PIPELINE_ROOT)
            if bible_sync.resolve(self.manifest):
                if bible_sync.series_id and self.manifest.get("bible_id") != bible_sync.series_id:
                    self.manifest["bible_id"] = bible_sync.series_id
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

        self._mark_pipeline_state(
            status="completed",
            cache_stats=cache_stats,
            used_external_cache=used_external_cache,
            output_tokens=getattr(response, "output_tokens", 0),
            patch_keys=sorted(list(filtered_patch.keys())),
        )
        self._save_manifest()

        logger.info(
            "Phase 1.55 complete: rich metadata merged "
            f"({len(filtered_patch)} top-level keys, cache_used={used_external_cache})"
        )
        return True

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
            '    "dialogue_patterns": {...},\n'
            '    "scene_contexts": {...},\n'
            '    "emotional_pronoun_shifts": {...},\n'
            '    "translation_guidelines": {...},\n'
            '    "schema_version": "v3.9_cached_enrichment"\n'
            "  }\n"
            "}\n"
            "Rules:\n"
            "0) Scan the ENTIRE cached LN corpus before deciding updates.\n"
            "1) Keep Japanese surname-first order for Japanese characters (absolute).\n"
            "2) Follow v3.9 schema structure exactly for metadata_en_patch fields.\n"
            "3) ONLY fill blank/placeholder values. Do NOT overwrite already-populated fields.\n"
            "4) Do NOT modify title_en/author_en/chapter title fields/character_names/glossary.\n"
            "5) Keep unknown values empty instead of guessing.\n"
            "6) Prefer concrete character evidence from cached chapter text.\n"
        )
        if self.schema_spec_path.exists():
            try:
                schema_text = self.schema_spec_path.read_text(encoding="utf-8")
                return f"{base_instruction}\n\nReference schema (v3.9):\n{schema_text}"
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

    def _mark_pipeline_state(
        self,
        *,
        status: str,
        cache_stats: Optional[Dict[str, Any]] = None,
        used_external_cache: bool = False,
        output_tokens: int = 0,
        patch_keys: Optional[List[str]] = None,
        error: Optional[str] = None,
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
        }
        if error:
            state["error"] = error
        pipeline_state["rich_metadata_cache"] = state


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1.55 rich metadata cache updater")
    parser.add_argument("--volume", type=str, required=True, help="Volume ID in WORK/")
    args = parser.parse_args()

    work_dir = WORK_DIR / args.volume
    if not work_dir.exists():
        logger.error(f"Volume directory not found: {work_dir}")
        sys.exit(1)

    updater = RichMetadataCacheUpdater(work_dir)
    success = updater.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
