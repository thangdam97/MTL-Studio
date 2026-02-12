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
    CULTURAL_TERM_DEFAULTS: Dict[str, str] = {
        "球技大会": "ball game tournament",
        "内申": "internal school record",
        "特別推薦": "special recommendation admission",
        "里親": "foster parent",
        "軟禁": "house confinement",
        "万歳三唱": "three cheers",
        "おにいちゃん": "big brother",
        "お姉さん": "big sister",
        "幼女": "little girl",
        "大和撫子": "Yamato Nadeshiko",
        "コミカライズ": "manga adaptation",
    }
    LOCATION_TERM_DEFAULTS: Dict[str, str] = {
        "教室": "classroom",
        "屋上": "rooftop",
        "体育館": "gymnasium",
        "保健室": "nurse's office",
        "職員室": "faculty room",
        "図書室": "library room",
        "校庭": "schoolyard",
        "部室": "club room",
        "廊下": "hallway",
        "昇降口": "shoe-locker entrance",
    }
    IDIOM_LIBRARY: Dict[str, Dict[str, str]] = {
        "雨降って地固まる": {
            "literal": "after the rain, the ground hardens",
            "meaning": "adversity can strengthen relationships",
            "category": "proverb",
        },
        "猫を被る": {
            "literal": "to wear a cat",
            "meaning": "to hide one's true nature and act innocent",
            "category": "set_phrase",
        },
        "二兎を追う者は一兎をも得ず": {
            "literal": "chase two rabbits and catch neither",
            "meaning": "trying to do too much leads to failure",
            "category": "proverb",
        },
        "百聞は一見に如かず": {
            "literal": "hearing a hundred times is not equal to seeing once",
            "meaning": "seeing is believing",
            "category": "proverb",
        },
        "一期一会": {
            "literal": "one time, one meeting",
            "meaning": "treasure each encounter as unique",
            "category": "set_phrase",
        },
        "七転八起": {
            "literal": "fall seven times, rise eight",
            "meaning": "keep getting back up",
            "category": "set_phrase",
        },
        "以心伝心": {
            "literal": "heart-to-heart transmission",
            "meaning": "understanding without words",
            "category": "set_phrase",
        },
    }
    BODY_IDIOM_LIBRARY: Dict[str, Dict[str, str]] = {
        "鼻が高い": {
            "literal": "my nose is high",
            "meaning": "to feel proud",
            "category": "body_part_idiom",
        },
        "頭が上がらない": {
            "literal": "can't raise my head",
            "meaning": "I am indebted and cannot oppose them",
            "category": "body_part_idiom",
        },
        "耳が痛い": {
            "literal": "my ears hurt",
            "meaning": "a criticism hits too close to home",
            "category": "body_part_idiom",
        },
        "目を丸くする": {
            "literal": "eyes become round",
            "meaning": "to stare in surprise",
            "category": "body_part_idiom",
        },
        "心が痛む": {
            "literal": "my heart hurts",
            "meaning": "to feel emotional pain",
            "category": "metaphorical_imagery",
        },
    }
    ONOMATOPOEIA_EQUIVALENTS: Dict[str, Dict[str, str]] = {
        "ドキドキ": {
            "literal": "doki-doki",
            "meaning": "heart pounding with nerves or excitement",
            "default_en": "my heart pounded",
        },
        "ワクワク": {
            "literal": "waku-waku",
            "meaning": "excited anticipation",
            "default_en": "I was buzzing with excitement",
        },
        "ニヤニヤ": {
            "literal": "niya-niya",
            "meaning": "grinning to oneself",
            "default_en": "he wore a smug grin",
        },
        "イライラ": {
            "literal": "ira-ira",
            "meaning": "irritated and restless",
            "default_en": "my irritation kept building",
        },
        "バタバタ": {
            "literal": "bata-bata",
            "meaning": "hurried commotion",
            "default_en": "everyone rushed around in a flurry",
        },
        "ガタガタ": {
            "literal": "gata-gata",
            "meaning": "rattling or trembling",
            "default_en": "it rattled violently",
        },
        "ゴロゴロ": {
            "literal": "goro-goro",
            "meaning": "rumbling / lazing around",
            "default_en": "thunder rolled in the distance",
        },
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
        self._chapter_text_cache: Optional[Dict[str, List[str]]] = None
        self._idiom_fallback_cache: Optional[Dict[str, Any]] = None

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

    def _load_chapter_text_map(self) -> Dict[str, List[str]]:
        """Load JP chapter text lines keyed by normalized chapter id."""
        if self._chapter_text_cache is not None:
            return self._chapter_text_cache

        chapter_map: Dict[str, List[str]] = {}
        for chapter in self._get_manifest_chapters():
            chapter_id = self._normalize_chapter_key(chapter.get("id", ""))
            jp_file = chapter.get("jp_file") or chapter.get("source_file")
            if not chapter_id or not jp_file:
                continue
            source_path = self.work_dir / "JP" / jp_file
            if not source_path.exists():
                continue
            try:
                chapter_map[chapter_id] = source_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

        self._chapter_text_cache = chapter_map
        return chapter_map

    def _infer_scene_for_line(
        self,
        chapter_key: str,
        line_number: int,
        scene_plan_index: Dict[str, Dict[str, Any]],
    ) -> str:
        plan = scene_plan_index.get(chapter_key, {})
        scenes = plan.get("scenes", []) if isinstance(plan, dict) else []
        if isinstance(scenes, list):
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                start = scene.get("start_paragraph")
                end = scene.get("end_paragraph")
                if isinstance(start, int) and isinstance(end, int):
                    if start <= line_number <= end:
                        sid = str(scene.get("id", "")).strip()
                        if sid:
                            return sid
        if isinstance(scenes, list):
            for scene in scenes:
                if isinstance(scene, dict):
                    sid = str(scene.get("id", "")).strip()
                    if sid:
                        return sid
        return f"{chapter_key.upper()}_SC01"

    def _transcreation_priority_from_category(self, category: str) -> str:
        cat = str(category or "").lower()
        if cat in {"wordplay", "cultural_subtext"}:
            return "critical"
        if cat in {"proverb", "body_part_idiom", "set_phrase"}:
            return "high"
        if cat in {"onomatopoeia", "metaphorical_imagery"}:
            return "medium"
        return "low"

    def _confidence_for_category(self, category: str, heuristic: bool = False) -> float:
        cat = str(category or "").lower()
        base = {
            "wordplay": 0.84,
            "proverb": 0.90,
            "set_phrase": 0.82,
            "body_part_idiom": 0.88,
            "onomatopoeia": 0.92,
            "metaphorical_imagery": 0.78,
            "cultural_subtext": 0.86,
        }.get(cat, 0.70)
        if heuristic:
            base -= 0.12
        return max(0.45, min(0.98, base))

    def _build_transcreation_options(
        self,
        *,
        japanese: str,
        literal: str,
        meaning: str,
        category: str,
    ) -> List[Dict[str, Any]]:
        cat = str(category or "").lower()
        equivalent = meaning.strip() if meaning else literal.strip()
        if cat == "onomatopoeia":
            source = self.ONOMATOPOEIA_EQUIVALENTS.get(japanese, {})
            equivalent = source.get("default_en", equivalent or "the sound was emphasized")

        creative = equivalent
        if cat == "proverb":
            creative = f"{equivalent[:1].upper() + equivalent[1:]}."
        elif cat == "body_part_idiom":
            creative = f"The feeling hit all at once: {equivalent}."
        elif cat == "wordplay":
            creative = f"Recast as natural English wordplay around: {equivalent}."
        elif cat == "onomatopoeia":
            creative = f"A sharper beat: {equivalent}."

        options: List[Dict[str, Any]] = [
            {
                "rank": 1,
                "text": equivalent or literal or japanese,
                "type": "english_equivalent",
                "confidence": round(self._confidence_for_category(category), 2),
                "reasoning": "Best balance of natural English and original meaning.",
                "register": "neutral",
                "preserves_imagery": cat in {"proverb", "metaphorical_imagery", "onomatopoeia"},
                "preserves_meaning": True,
                "literary_impact": "high" if cat in {"proverb", "wordplay"} else "medium",
            },
            {
                "rank": 2,
                "text": creative or equivalent or literal or japanese,
                "type": "creative_transcreation",
                "confidence": round(max(0.55, self._confidence_for_category(category) - 0.08), 2),
                "reasoning": "Stylized rendering for scenes requiring stronger literary punch.",
                "register": "literary",
                "preserves_imagery": True,
                "preserves_meaning": True,
                "literary_impact": "high",
            },
            {
                "rank": 3,
                "text": literal or japanese,
                "type": "literal",
                "confidence": round(max(0.40, self._confidence_for_category(category) - 0.26), 2),
                "reasoning": "Literal fallback; use only if context already explains intent.",
                "register": "literal",
                "preserves_imagery": True,
                "preserves_meaning": cat in {"onomatopoeia", "metaphorical_imagery"},
                "literary_impact": "low",
            },
        ]
        return options

    def _build_idiom_transcreation_from_text(
        self,
        scene_plan_index: Dict[str, Dict[str, Any]],
        min_items: int = 15,
    ) -> Dict[str, Any]:
        chapter_map = self._load_chapter_text_map()
        opportunities: List[Dict[str, Any]] = []
        wordplay_entries: List[Dict[str, Any]] = []
        seen: set = set()
        seen_wordplay: set = set()

        idiom_sources: List[Tuple[str, Dict[str, str]]] = []
        idiom_sources.extend(list(self.IDIOM_LIBRARY.items()))
        idiom_sources.extend(list(self.BODY_IDIOM_LIBRARY.items()))

        for chapter_key in sorted(chapter_map.keys()):
            lines = chapter_map.get(chapter_key, [])
            for line_no, raw_line in enumerate(lines, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                location = f"{chapter_key.upper()}_LINE_{line_no}"
                scene_id = self._infer_scene_for_line(chapter_key, line_no, scene_plan_index)

                for phrase, meta in idiom_sources:
                    if phrase not in line:
                        continue
                    dedupe = (location, phrase)
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    category = meta.get("category", "set_phrase")
                    confidence = self._confidence_for_category(category)
                    opportunities.append(
                        {
                            "id": f"trans_{len(opportunities) + 1:03d}",
                            "location": location,
                            "japanese": phrase,
                            "literal": meta.get("literal", phrase),
                            "meaning": meta.get("meaning", ""),
                            "category": category,
                            "context": {
                                "scene": scene_id,
                                "emotional_tone": "contextual",
                                "beat_type": "event",
                            },
                            "transcreation_priority": self._transcreation_priority_from_category(category),
                            "confidence": round(confidence, 2),
                            "options": self._build_transcreation_options(
                                japanese=phrase,
                                literal=meta.get("literal", phrase),
                                meaning=meta.get("meaning", ""),
                                category=category,
                            ),
                            "stage_2_guidance": "Prefer rank 1 unless scene voice requires a stronger literary beat.",
                        }
                    )

                for sound, meta in self.ONOMATOPOEIA_EQUIVALENTS.items():
                    if sound not in line:
                        continue
                    dedupe = (location, sound)
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    opportunities.append(
                        {
                            "id": f"trans_{len(opportunities) + 1:03d}",
                            "location": location,
                            "japanese": sound,
                            "literal": meta.get("literal", sound),
                            "meaning": meta.get("meaning", ""),
                            "category": "onomatopoeia",
                            "context": {
                                "scene": scene_id,
                                "emotional_tone": "expressive",
                                "beat_type": "escalation",
                            },
                            "transcreation_priority": "medium",
                            "confidence": round(self._confidence_for_category("onomatopoeia"), 2),
                            "options": self._build_transcreation_options(
                                japanese=sound,
                                literal=meta.get("literal", sound),
                                meaning=meta.get("meaning", ""),
                                category="onomatopoeia",
                            ),
                            "stage_2_guidance": "Use rank 1 for clean readability; rank 2 for heightened emotional prose.",
                        }
                    )

                for match in re.finditer(r"([一-龯ぁ-んァ-ンA-Za-z]+)だけに", line):
                    anchor = match.group(1)
                    dedupe = (location, anchor)
                    if dedupe in seen_wordplay:
                        continue
                    seen_wordplay.add(dedupe)
                    wordplay_entries.append(
                        {
                            "id": f"wordplay_{len(wordplay_entries) + 1:03d}",
                            "location": location,
                            "japanese": match.group(0),
                            "meaning": f"Wordplay emphasis around {anchor}.",
                            "transcreation_priority": "critical",
                            "confidence": 0.83,
                            "options": [
                                {"rank": 1, "text": f"English wordplay centered on '{anchor}'.", "confidence": 0.83},
                                {"rank": 2, "text": "Keep meaning and explain the pun through narration.", "confidence": 0.76},
                            ],
                            "stage_2_guidance": "Recast into natural English wit; avoid literal carryover.",
                        }
                    )

        if len(opportunities) < min_items:
            for chapter_key in sorted(chapter_map.keys()):
                lines = chapter_map.get(chapter_key, [])
                for line_no, raw_line in enumerate(lines, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    location = f"{chapter_key.upper()}_LINE_{line_no}"
                    scene_id = self._infer_scene_for_line(chapter_key, line_no, scene_plan_index)
                    for four in re.findall(r"[一-龯]{4}", line):
                        dedupe = (location, four)
                        if dedupe in seen:
                            continue
                        seen.add(dedupe)
                        opportunities.append(
                            {
                                "id": f"trans_{len(opportunities) + 1:03d}",
                                "location": location,
                                "japanese": four,
                                "literal": four,
                                "meaning": "Potential four-character idiom; verify context before transcreation.",
                                "category": "set_phrase",
                                "context": {
                                    "scene": scene_id,
                                    "emotional_tone": "contextual",
                                    "beat_type": "event",
                                },
                                "transcreation_priority": "low",
                                "confidence": round(self._confidence_for_category("set_phrase", heuristic=True), 2),
                                "options": self._build_transcreation_options(
                                    japanese=four,
                                    literal=four,
                                    meaning="Potential idiomatic emphasis.",
                                    category="set_phrase",
                                ),
                                "stage_2_guidance": "Only transcreate if surrounding context confirms idiomatic usage.",
                            }
                        )
                        if len(opportunities) >= min_items:
                            break
                    if len(opportunities) >= min_items:
                        break
                if len(opportunities) >= min_items:
                    break

        priority_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        confidence_sum = 0.0
        for item in opportunities:
            priority = str(item.get("transcreation_priority", "low")).lower()
            if priority in priority_counts:
                priority_counts[priority] += 1
            confidence_sum += float(item.get("confidence", 0.0) or 0.0)

        avg_conf = confidence_sum / len(opportunities) if opportunities else 0.0
        return {
            "volume_id": self.manifest.get("volume_id", self.work_dir.name),
            "generated_at": datetime.datetime.now().isoformat(),
            "processor_version": "1.1",
            "transcreation_opportunities": opportunities[:140],
            "wordplay_transcreations": wordplay_entries[:60],
            "summary": {
                "total_opportunities": len(opportunities[:140]),
                "by_priority": priority_counts,
                "avg_confidence": round(avg_conf, 3),
            },
        }

    def _get_or_build_idiom_fallback(self, scene_plan_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if self._idiom_fallback_cache is None:
            self._idiom_fallback_cache = self._build_idiom_transcreation_from_text(
                scene_plan_index=scene_plan_index,
                min_items=15,
            )
        return json.loads(json.dumps(self._idiom_fallback_cache))

    def _resolve_cultural_term_translation(self, jp_term: str, source: Any) -> Tuple[str, List[str], str]:
        if isinstance(source, dict):
            preferred = (
                source.get("preferred_en")
                or source.get("canonical_en")
                or source.get("meaning_en")
                or source.get("translation")
                or source.get("en")
                or ""
            )
            aliases = source.get("aliases") or source.get("aliases_en") or []
        else:
            preferred = str(source or "")
            aliases = []

        preferred = str(preferred).strip()
        if not preferred:
            preferred = self.CULTURAL_TERM_DEFAULTS.get(jp_term, "").strip()

        normalized_aliases: List[str] = []
        if isinstance(aliases, list):
            for alias in aliases:
                text = str(alias).strip()
                if text and text != preferred and text not in normalized_aliases:
                    normalized_aliases.append(text)

        reason = "Taken from canonical metadata."
        if jp_term in self.CULTURAL_TERM_DEFAULTS and preferred == self.CULTURAL_TERM_DEFAULTS[jp_term]:
            reason = "Fallback dictionary mapping for stable LN translation consistency."
        if not preferred:
            reason = "No stable equivalent found; requires model translation."
        return preferred, normalized_aliases, reason

    def _is_contemporary_japan_setting(self, metadata_en: Dict[str, Any]) -> bool:
        """Heuristic detector for modern/contemporary Japan setting."""
        text_chunks: List[str] = []

        metadata = self.manifest.get("metadata", {})
        if isinstance(metadata, dict):
            for key in ("title", "series", "description", "genre", "publisher"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    text_chunks.append(value.strip())

        for key in ("world_setting", "localization_notes", "translation_rules", "geography", "scene_contexts"):
            value = metadata_en.get(key)
            if value:
                text_chunks.append(json.dumps(value, ensure_ascii=False))

        haystack = " ".join(text_chunks).lower()
        if not haystack:
            return False

        positive_signals = (
            "contemporary japan",
            "modern japan",
            "present-day japan",
            "japanese high school",
            "japan",
            "tokyo",
            "osaka",
            "kyoto",
            "reiwa",
            "heisei",
            "slice-of-life",
            "school life",
        )
        negative_signals = (
            "isekai",
            "fantasy world",
            "alternate world",
            "parallel world",
            "magic academy",
            "dungeon",
            "kingdom",
            "empire",
            "medieval",
        )

        has_positive = any(token in haystack for token in positive_signals)
        has_negative = any(token in haystack for token in negative_signals)
        return has_positive and not has_negative

    def _is_fantasy_or_non_contemporary_setting(self, metadata_en: Dict[str, Any]) -> bool:
        """
        Detect fantasy/non-contemporary world settings.

        Rule: if Contemporary Japan is detected, this returns False.
        """
        if self._is_contemporary_japan_setting(metadata_en):
            return False

        text_chunks: List[str] = []
        metadata = self.manifest.get("metadata", {})
        if isinstance(metadata, dict):
            for key in ("title", "series", "description", "genre", "publisher"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    text_chunks.append(value.strip())

        for key in ("world_setting", "localization_notes", "translation_rules", "geography", "scene_contexts"):
            value = metadata_en.get(key)
            if value:
                text_chunks.append(json.dumps(value, ensure_ascii=False))

        haystack = " ".join(text_chunks).lower()
        if not haystack:
            return False

        fantasy_or_noncontemporary_signals = (
            "fantasy",
            "isekai",
            "alternate world",
            "parallel world",
            "otherworld",
            "medieval",
            "feudal",
            "historical",
            "pre-modern",
            "kingdom",
            "empire",
            "royal court",
            "magic academy",
            "sword",
            "sorcery",
            "dungeon",
            "noble academy",
            "non-contemporary",
        )
        return any(token in haystack for token in fantasy_or_noncontemporary_signals)

    def _is_noble_setting(self, metadata_en: Dict[str, Any]) -> bool:
        """Detect aristocratic/noble settings requiring title transcreation."""
        text_chunks: List[str] = []
        metadata = self.manifest.get("metadata", {})
        if isinstance(metadata, dict):
            for key in ("title", "series", "description", "genre"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    text_chunks.append(value.strip())

        for key in ("world_setting", "localization_notes", "translation_rules", "organizations", "geography", "scene_contexts"):
            value = metadata_en.get(key)
            if value:
                text_chunks.append(json.dumps(value, ensure_ascii=False))

        haystack = " ".join(text_chunks).lower()
        if not haystack:
            return False

        noble_signals = (
            "noble",
            "aristocrat",
            "aristocracy",
            "duke",
            "duchess",
            "count",
            "countess",
            "marquis",
            "marchioness",
            "earl",
            "baron",
            "viscount",
            "viscountess",
            "lord",
            "lady",
            "your grace",
            "your highness",
            "royal",
            "princess",
            "prince",
            "king",
            "queen",
            "court",
            "knight",
        )
        return any(token in haystack for token in noble_signals)

    def _contemporary_japan_honorific_policies(self) -> List[Dict[str, Any]]:
        """Canonical honorific retention policy for modern Japan settings."""
        return [
            {
                "pattern": "-san",
                "strategy": "retain_in_english",
                "rule": "Retain as suffix in English (e.g., Saki-san); do not omit or translate.",
            },
            {
                "pattern": "-chan",
                "strategy": "retain_in_english",
                "rule": "Retain as suffix in English (e.g., Emma-chan) to preserve intimacy nuance.",
            },
            {
                "pattern": "-kun",
                "strategy": "retain_in_english",
                "rule": "Retain as suffix in English (e.g., Yuuta-kun); do not flatten to first-name only.",
            },
            {
                "pattern": "-sama",
                "strategy": "retain_in_english",
                "rule": "Retain as suffix in English for elevated politeness/register.",
            },
            {
                "pattern": "-senpai",
                "strategy": "retain_in_english",
                "rule": "Retain senpai as title/suffix in English; do not translate to 'senior'.",
            },
            {
                "pattern": "-sensei",
                "strategy": "retain_in_english",
                "rule": "Retain sensei as title/suffix in English; do not translate to 'teacher/professor'.",
            },
            {
                "pattern": "先輩",
                "strategy": "retain_in_english",
                "rule": "Render as senpai in English output.",
            },
            {
                "pattern": "先生",
                "strategy": "retain_in_english",
                "rule": "Render as sensei in English output.",
            },
        ]

    def _fantasy_noncontemporary_honorific_policies(self) -> List[Dict[str, Any]]:
        """Default policy for fantasy/non-contemporary settings."""
        return [
            {
                "pattern": "name_order",
                "strategy": "given_name_first_convert_to_english_equivalent",
                "rule": "Use given-name-first order for character naming and prefer natural English equivalents.",
            },
            {
                "pattern": "-san",
                "strategy": "transcreate_to_english_equivalent",
                "rule": "Do not retain '-san'; convert to context-appropriate English address (Mr./Ms./title).",
            },
            {
                "pattern": "-chan",
                "strategy": "transcreate_to_english_equivalent",
                "rule": "Do not retain '-chan'; express closeness with tone, nickname, or Miss/young-lady styling by context.",
            },
            {
                "pattern": "-kun",
                "strategy": "transcreate_to_english_equivalent",
                "rule": "Do not retain '-kun'; convert to natural English peer/junior address.",
            },
            {
                "pattern": "-senpai",
                "strategy": "transcreate_to_english_equivalent",
                "rule": "Do not retain '-senpai'; convert to senior role/title in English context.",
            },
            {
                "pattern": "-sensei",
                "strategy": "transcreate_to_english_equivalent",
                "rule": "Do not retain '-sensei'; convert to Master/Instructor/Teacher based on world context.",
            },
        ]

    def _noble_honorific_policies(self) -> List[Dict[str, Any]]:
        """Policy for noble/aristocratic settings: transcreate JP honorifics to noble English titles."""
        return [
            {
                "pattern": "name_order",
                "strategy": "given_name_first_convert_to_english_equivalent",
                "rule": "Use given-name-first order and naturalized English naming in noble dialogue/narration.",
            },
            {
                "pattern": "-sama/様",
                "strategy": "transcreate_to_noble_english_equivalent",
                "rule": "Transcreate to noble address (e.g., My Lord, My Lady, Your Grace/Highness by rank).",
            },
            {
                "pattern": "-san",
                "strategy": "transcreate_to_noble_english_equivalent",
                "rule": "Transcreate to Lord/Lady or formal title based on status and scene register.",
            },
            {
                "pattern": "-kun",
                "strategy": "transcreate_to_noble_english_equivalent",
                "rule": "Transcreate to Young Lord/Young Master or equivalent noble junior address.",
            },
            {
                "pattern": "-chan",
                "strategy": "transcreate_to_noble_english_equivalent",
                "rule": "Transcreate to Lady/Miss or affectionate noble equivalent (avoid JP suffix retention).",
            },
            {
                "pattern": "-senpai/先輩",
                "strategy": "transcreate_to_noble_english_equivalent",
                "rule": "Transcreate to senior rank-role (e.g., Senior Knight, elder court member) by context.",
            },
            {
                "pattern": "-sensei/先生",
                "strategy": "transcreate_to_noble_english_equivalent",
                "rule": "Transcreate to Master, Tutor, or Court Instructor based on role.",
            },
        ]

    def _build_honorific_policies(self, metadata_en: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self._is_contemporary_japan_setting(metadata_en):
            return self._contemporary_japan_honorific_policies()
        if self._is_fantasy_or_non_contemporary_setting(metadata_en):
            if self._is_noble_setting(metadata_en):
                return self._noble_honorific_policies()
            return self._fantasy_noncontemporary_honorific_policies()

        policies: List[Dict[str, Any]] = [
            {
                "pattern": "-san",
                "strategy": "omit_in_english",
                "rule": "Default omission; keep role distance via tone or title when context requires.",
            },
            {
                "pattern": "-chan",
                "strategy": "omit_with_tender_tone",
                "rule": "Reflect intimacy through diction, not suffix carryover.",
            },
            {
                "pattern": "-kun",
                "strategy": "omit_with_peer_register",
                "rule": "Use casual peer voice in English lines.",
            },
            {
                "pattern": "先輩",
                "strategy": "translate_to_senior",
                "rule": "Use 'senior' when hierarchy matters; otherwise infer via voice dynamics.",
            },
            {
                "pattern": "先生",
                "strategy": "translate_to_teacher",
                "rule": "Prefer teacher/professor by setting context.",
            },
        ]

        localization_notes = metadata_en.get("localization_notes", {})
        if isinstance(localization_notes, dict):
            british = localization_notes.get("british_speech_exception", {})
            if isinstance(british, dict):
                chars = british.get("character")
                if chars:
                    policies.append(
                        {
                            "pattern": "formal_exception",
                            "strategy": "retain_formality_for_listed_characters",
                            "rule": f"Apply formal register to: {chars}",
                        }
                    )
        return policies

    def _build_location_terms(self) -> List[Dict[str, Any]]:
        chapter_map = self._load_chapter_text_map()
        all_text = "\n".join("\n".join(lines) for lines in chapter_map.values())
        location_terms: List[Dict[str, Any]] = []
        for jp, en in self.LOCATION_TERM_DEFAULTS.items():
            if jp in all_text:
                location_terms.append({"jp": jp, "en": en, "notes": "Detected in volume source text."})
        return location_terms

    def _enhance_character_registry_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        chars = payload.get("characters", [])
        if not isinstance(chars, list):
            return payload

        for char in chars:
            if not isinstance(char, dict):
                continue
            pronouns = [str(p).lower() for p in char.get("pronoun_hints_en", []) if isinstance(p, str)]
            if not char.get("gender"):
                if any(p in {"she", "her", "hers"} for p in pronouns):
                    char["gender"] = "female"
                elif any(p in {"he", "him", "his"} for p in pronouns):
                    char["gender"] = "male"
                else:
                    char["gender"] = "unknown"

            if "emotional_arc" not in char:
                char["emotional_arc"] = {}

            edges = char.get("relationship_edges", [])
            if isinstance(edges, list):
                for edge in edges:
                    if not isinstance(edge, dict):
                        continue
                    type_text = str(edge.get("type", "")).lower()
                    taxonomy = "friendship"
                    if any(k in type_text for k in ("romantic", "partner", "crush", "love")):
                        taxonomy = "romantic"
                    elif any(k in type_text for k in ("sister", "brother", "father", "mother", "family", "guardian")):
                        taxonomy = "familial"
                    elif any(k in type_text for k in ("teacher", "student", "mentor", "colleague", "professional")):
                        taxonomy = "professional"
                    elif any(k in type_text for k in ("hostile", "antagon", "strained", "conflict")):
                        taxonomy = "antagonistic"
                    edge["taxonomy"] = taxonomy

        summary = payload.get("summary", {})
        if isinstance(summary, dict):
            summary["total_characters"] = len([c for c in chars if isinstance(c, dict)])
        return payload

    def _enhance_cultural_glossary_payload(
        self,
        payload: Dict[str, Any],
        metadata_en: Dict[str, Any],
        scene_plan_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        source_terms = metadata_en.get("cultural_terms", {})
        if not isinstance(source_terms, dict):
            source_terms = {}

        raw_terms = payload.get("terms", [])
        if not isinstance(raw_terms, list) or not raw_terms:
            seed_terms = list(source_terms.keys())
            if not seed_terms:
                chapter_map = self._load_chapter_text_map()
                all_text = "\n".join("\n".join(lines) for lines in chapter_map.values())
                for jp_term in self.CULTURAL_TERM_DEFAULTS.keys():
                    if jp_term in all_text:
                        seed_terms.append(jp_term)
            raw_terms = [{"term_jp": key} for key in seed_terms[:80]]

        enriched_terms: List[Dict[str, Any]] = []
        consistency_rules: List[str] = []
        seen_terms: set = set()

        for term in raw_terms:
            if not isinstance(term, dict):
                continue
            term_jp = str(term.get("term_jp") or term.get("jp") or "").strip()
            if not term_jp or term_jp in seen_terms:
                continue
            seen_terms.add(term_jp)
            source = source_terms.get(term_jp, {})
            preferred, aliases, reason = self._resolve_cultural_term_translation(term_jp, source)
            notes = str(term.get("notes") or "").strip()
            if not notes and isinstance(source, dict):
                notes = str(source.get("notes") or source.get("context") or "").strip()

            entry = {
                "term_jp": term_jp,
                "preferred_en": preferred,
                "alternatives": aliases[:4],
                "chosen_reason": reason,
                "consistency_rule": f"Always translate {term_jp} as '{preferred}'." if preferred else "",
                "notes": notes,
            }
            enriched_terms.append(entry)
            if entry["consistency_rule"]:
                consistency_rules.append(entry["consistency_rule"])

        payload["terms"] = enriched_terms[:120]

        idioms = payload.get("idioms")
        if not isinstance(idioms, list) or not idioms:
            idiom_seed = self._get_or_build_idiom_fallback(scene_plan_index)
            idioms = []
            for item in idiom_seed.get("transcreation_opportunities", []):
                if not isinstance(item, dict):
                    continue
                category = str(item.get("category", "")).lower()
                if category not in {"proverb", "set_phrase", "body_part_idiom"}:
                    continue
                idioms.append(
                    {
                        "japanese": item.get("japanese", ""),
                        "meaning": item.get("meaning", ""),
                        "preferred_rendering": item.get("options", [{}])[0].get("text", "") if isinstance(item.get("options"), list) else "",
                        "confidence": item.get("confidence", 0.7),
                    }
                )
                if len(idioms) >= 20:
                    break
        payload["idioms"] = idioms if isinstance(idioms, list) else []

        honorifics = payload.get("honorific_policies")
        if not isinstance(honorifics, list) or not honorifics:
            honorifics = self._build_honorific_policies(metadata_en)
        if self._is_contemporary_japan_setting(metadata_en):
            honorifics = self._contemporary_japan_honorific_policies()
            consistency_rules.append(
                "Contemporary Japan setting detected: retain all honorifics in English "
                "(-san, -chan, -kun, -sama, senpai, sensei)."
            )
        elif self._is_fantasy_or_non_contemporary_setting(metadata_en):
            if self._is_noble_setting(metadata_en):
                honorifics = self._noble_honorific_policies()
                consistency_rules.append(
                    "Noble fantasy setting detected: transcreate JP honorifics into noble English equivalents "
                    "(My Lord/My Lady/Your Grace/Your Highness/Master/Tutor by rank/context)."
                )
            else:
                honorifics = self._fantasy_noncontemporary_honorific_policies()
                consistency_rules.append(
                    "Fantasy/non-contemporary setting detected: use given-name-first order and "
                    "convert JP honorifics to natural English equivalents."
                )
            consistency_rules.append(
                "Name-order policy: given-name-first with English-equivalent naming in non-contemporary settings."
            )
        payload["honorific_policies"] = honorifics

        location_terms = payload.get("location_terms")
        if not isinstance(location_terms, list) or not location_terms:
            location_terms = self._build_location_terms()
        payload["location_terms"] = location_terms

        payload["consistency_rules"] = consistency_rules[:200]
        payload["summary"] = {
            "total_terms": len(payload["terms"]),
            "total_idioms": len(payload["idioms"]),
            "translated_terms": len([t for t in payload["terms"] if isinstance(t, dict) and t.get("preferred_en")]),
            "consistency_rules": len(payload["consistency_rules"]),
        }
        return payload

    def _enhance_timeline_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        chapters = payload.get("chapter_timeline", [])
        if not isinstance(chapters, list):
            return payload

        flashback_markers = (
            "flashback",
            "past",
            "years ago",
            "middle school",
            "childhood",
            "昔",
            "回想",
        )

        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            scenes = chapter.get("scenes", [])
            if not isinstance(scenes, list):
                continue
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                summary = str(scene.get("summary", "")).lower()
                is_flashback = any(marker in summary for marker in flashback_markers)
                scene["temporal_type"] = "flashback" if is_flashback else "present_timeline"
                if is_flashback and "flashback_info" not in scene:
                    scene["flashback_info"] = {
                        "relative_time": "past",
                        "trigger": "narrative recollection",
                        "content": str(scene.get("summary", ""))[:160],
                    }
                scene["tense_guidance"] = {
                    "narrative": "past",
                    "dialogue": "present",
                    "flashback": "past_perfect" if is_flashback else "past",
                }

            chapter["scene_count"] = len([s for s in scenes if isinstance(s, dict)])

        payload["summary"] = {
            "chapter_count": len([c for c in chapters if isinstance(c, dict)]),
            "event_count": sum(int(c.get("scene_count", 0) or 0) for c in chapters if isinstance(c, dict)),
        }
        return payload

    def _enhance_idiom_payload(
        self,
        payload: Dict[str, Any],
        scene_plan_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback = self._get_or_build_idiom_fallback(scene_plan_index)
        opportunities = payload.get("transcreation_opportunities", [])
        if not isinstance(opportunities, list):
            opportunities = []
        wordplay = payload.get("wordplay_transcreations", [])
        if not isinstance(wordplay, list):
            wordplay = []

        if not opportunities:
            opportunities = fallback.get("transcreation_opportunities", [])
        else:
            existing = {
                (str(item.get("location", "")), str(item.get("japanese", "")))
                for item in opportunities
                if isinstance(item, dict)
            }
            for item in fallback.get("transcreation_opportunities", []):
                if not isinstance(item, dict):
                    continue
                key = (str(item.get("location", "")), str(item.get("japanese", "")))
                if key in existing:
                    continue
                opportunities.append(item)
                if len(opportunities) >= 140:
                    break

        if not wordplay:
            wordplay = fallback.get("wordplay_transcreations", [])

        normalized: List[Dict[str, Any]] = []
        for item in opportunities[:140]:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "set_phrase"))
            priority = str(item.get("transcreation_priority") or self._transcreation_priority_from_category(category)).lower()
            confidence = float(item.get("confidence", 0.0) or self._confidence_for_category(category))
            literal = str(item.get("literal", "") or item.get("japanese", ""))
            meaning = str(item.get("meaning", ""))
            options = item.get("options")
            if not isinstance(options, list) or not options:
                options = self._build_transcreation_options(
                    japanese=str(item.get("japanese", "")),
                    literal=literal,
                    meaning=meaning,
                    category=category,
                )
            item["transcreation_priority"] = priority if priority in {"critical", "high", "medium", "low"} else "medium"
            item["confidence"] = round(max(0.40, min(0.99, confidence)), 2)
            item["options"] = options[:4]
            if not item.get("stage_2_guidance"):
                item["stage_2_guidance"] = "Prefer rank 1 unless scene register requires stylistic lift."
            normalized.append(item)

        priority_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        conf_sum = 0.0
        for item in normalized:
            p = str(item.get("transcreation_priority", "low")).lower()
            if p in priority_counts:
                priority_counts[p] += 1
            conf_sum += float(item.get("confidence", 0.0) or 0.0)

        payload["transcreation_opportunities"] = normalized
        payload["wordplay_transcreations"] = [w for w in wordplay[:60] if isinstance(w, dict)]
        payload["summary"] = {
            "total_opportunities": len(normalized),
            "by_priority": priority_counts,
            "avg_confidence": round(conf_sum / len(normalized), 3) if normalized else 0.0,
        }
        return payload

    def _postprocess_context_processor_payload(
        self,
        processor_id: str,
        payload: Dict[str, Any],
        metadata_en: Dict[str, Any],
        scene_plan_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        payload["generated_at"] = datetime.datetime.now().isoformat()
        payload.setdefault("processor_version", "1.1")

        if processor_id == "character_context":
            return self._enhance_character_registry_payload(payload)
        if processor_id == "cultural_context":
            return self._enhance_cultural_glossary_payload(payload, metadata_en, scene_plan_index)
        if processor_id == "temporal_context":
            return self._enhance_timeline_payload(payload)
        if processor_id == "idiom_transcreation":
            return self._enhance_idiom_payload(payload, scene_plan_index)
        return payload

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

    def _extract_balanced_json_object(self, text: str) -> Optional[str]:
        """Extract first balanced top-level JSON object from arbitrary text."""
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
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        return None

    def _normalize_json_candidate(self, text: str) -> str:
        """Apply lightweight cleanup to likely-JSON text."""
        cleaned = text.replace("\ufeff", "").replace("“", '"').replace("”", '"')
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
        cleaned = re.sub(r"//.*", "", cleaned)  # single-line comments
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)  # block comments
        # Repair malformed keys like: temporal_markers": [...]
        cleaned = re.sub(r'(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\"?)\s*:', r'\1"\2":', cleaned)
        # Remove non-JSON control chars that models occasionally emit in long outputs.
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", cleaned)
        return cleaned.strip()

    def _repair_missing_comma_with_decoder_feedback(
        self,
        text: str,
        *,
        max_attempts: int = 10,
    ) -> Optional[str]:
        """
        Repair JSON that is syntactically valid except for missing commas.

        Uses JSON decoder feedback to insert a comma at the reported error offset
        when the decoder specifically asks for a comma delimiter.
        """
        candidate = text
        for _ in range(max_attempts):
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError as e:
                if "Expecting ',' delimiter" not in str(e.msg):
                    return None

                insert_at = int(e.pos)
                if insert_at <= 0 or insert_at > len(candidate):
                    return None

                # Insert before the current token, skipping leading whitespace.
                while insert_at > 0 and candidate[insert_at - 1].isspace():
                    insert_at -= 1

                prev = insert_at - 1
                while prev >= 0 and candidate[prev].isspace():
                    prev -= 1
                if prev < 0 or candidate[prev] in "{[,:":  # no valid value before insertion
                    return None
                if candidate[prev] == ",":
                    return None

                candidate = candidate[:insert_at] + "," + candidate[insert_at:]
                candidate = re.sub(r",\s*,+", ",", candidate)
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                continue
            except Exception:
                return None
        return None

    def _repair_truncated_json_candidate(self, text: str) -> Optional[str]:
        """
        Attempt recovery for truncated model JSON.

        Strategy:
        1. Close an unterminated string if needed.
        2. Replace a dangling key/value delimiter with null.
        3. Close remaining unbalanced objects/arrays.
        """
        candidate = text.strip()
        if not candidate or not candidate.startswith("{"):
            return None

        stack: List[str] = []
        in_string = False
        escaped = False
        for ch in candidate:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack and ((stack[-1] == "{" and ch == "}") or (stack[-1] == "[" and ch == "]")):
                    stack.pop()

        repaired = candidate
        if in_string:
            repaired += '"'

        # If output is cut at a dangling key/value marker, coerce to null.
        repaired = re.sub(r'("([^"\\]|\\.)*"\s*:\s*)$', r"\1null", repaired)
        repaired = re.sub(r",\s*$", "", repaired)

        while stack:
            opener = stack.pop()
            repaired += "}" if opener == "{" else "]"

        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        try:
            json.loads(repaired)
            return repaired
        except Exception:
            return None

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        candidates: List[str] = [text]

        balanced = self._extract_balanced_json_object(text)
        if balanced and balanced not in candidates:
            candidates.append(balanced)

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            regex_candidate = match.group(0)
            if regex_candidate not in candidates:
                candidates.append(regex_candidate)

        # Recovery: model may restart JSON mid-response. Prefer any block that
        # looks like a top-level schema root with "volume_id".
        for marker in re.finditer(r'\{\s*"volume_id"\s*:', text):
            sub = text[marker.start():]
            rooted = self._extract_balanced_json_object(sub)
            if rooted and rooted not in candidates:
                candidates.append(rooted)

        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except Exception as e:
                last_error = e

        # Repair pass for common model mistakes.
        for candidate in candidates:
            cleaned = self._normalize_json_candidate(candidate)
            try:
                return json.loads(cleaned)
            except Exception as e:
                last_error = e

            balanced_cleaned = self._extract_balanced_json_object(cleaned)
            if balanced_cleaned:
                try:
                    return json.loads(balanced_cleaned)
                except Exception as e:
                    last_error = e

            repaired_missing_commas = self._repair_missing_comma_with_decoder_feedback(cleaned)
            if repaired_missing_commas:
                try:
                    return json.loads(repaired_missing_commas)
                except Exception as e:
                    last_error = e

            repaired_truncated = self._repair_truncated_json_candidate(
                repaired_missing_commas or cleaned
            )
            if repaired_truncated:
                try:
                    return json.loads(repaired_truncated)
                except Exception as e:
                    last_error = e

        if last_error:
            raise last_error
        raise ValueError("Unable to parse JSON response")

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
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
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
            return None, f"call_failed: {str(e)[:240]}", None
        finally:
            if cache_name:
                self.client.delete_cache(cache_name)

        if not response or not response.content:
            return None, "empty_response", None
        try:
            payload = self._parse_json_response(response.content)
        except Exception as e:
            logger.warning(f"[P1.55] Processor JSON parse failed ({display_name}): {e}")
            debug_dir = self._context_dir_path() / "_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", display_name).strip("._-") or "processor"
            debug_path = debug_dir / f"{safe_name}_raw_response.txt"
            try:
                debug_path.write_text(response.content, encoding="utf-8")
            except Exception:
                debug_path = None
            return None, f"json_parse_failed: {str(e)[:240]}", (
                str(debug_path.relative_to(self.work_dir)) if debug_path else None
            )
        if not isinstance(payload, dict):
            return None, "non_dict_payload", None
        return payload, None, None

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

        payload = {
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
        return self._enhance_character_registry_payload(payload)

    def _fallback_cultural_glossary(self, metadata_en: Dict[str, Any]) -> Dict[str, Any]:
        terms: List[Dict[str, Any]] = []
        source_terms = metadata_en.get("cultural_terms", {})
        if isinstance(source_terms, dict):
            for key, value in list(source_terms.items())[:60]:
                if isinstance(value, dict):
                    meaning = (
                        value.get("preferred_en")
                        or value.get("canonical_en")
                        or value.get("meaning_en")
                        or value.get("translation")
                        or ""
                    )
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

        payload = {
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
        return self._enhance_cultural_glossary_payload(payload, metadata_en, {})

    def _fallback_timeline_map(self, scene_plan_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        if scene_plan_index:
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
        else:
            # Stage 1 plans may be missing for older/partial runs. Build a
            # minimal chapter-level timeline from JP source so Stage 2 still
            # receives continuity scaffolding instead of an empty map.
            chapter_map = self._load_chapter_text_map()
            for chapter_key in sorted(chapter_map.keys()):
                lines = chapter_map.get(chapter_key, [])
                excerpt = ""
                for raw in lines:
                    text = str(raw).strip()
                    if not text:
                        continue
                    if text.startswith("#"):
                        continue
                    excerpt = text
                    break
                if not excerpt:
                    excerpt = "Scene progression inferred from chapter source text."

                scene_summary = f"Inferred timeline from source: {excerpt[:140]}"
                sequence_index = int(chapter_key.split("_")[-1]) if "_" in chapter_key else 0
                beat = "setup" if sequence_index <= 1 else "event"
                fallback_scene = {
                    "id": "S01",
                    "beat_type": beat,
                    "summary": scene_summary,
                    "start_paragraph": 1,
                    "end_paragraph": max(1, len(lines)),
                }
                timeline.append(
                    {
                        "chapter_id": chapter_key,
                        "sequence_index": sequence_index,
                        "scene_count": 1,
                        "scenes": [fallback_scene],
                        "temporal_markers": [],
                        "continuity_constraints": [],
                    }
                )

        payload = {
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
        return self._enhance_timeline_payload(payload)

    def _fallback_idiom_transcreation(self) -> Dict[str, Any]:
        scene_plan_index = self._load_scene_plan_index()
        return self._get_or_build_idiom_fallback(scene_plan_index)

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
                    "Setting policy matrix (mandatory):\n"
                    "A) Contemporary Japan setting:\n"
                    "   - retain all Japanese honorifics in English output.\n"
                    "   - retain suffix/title forms: -san, -chan, -kun, -sama, -senpai, -sensei.\n"
                    "   - do not translate senpai/sensei to senior/teacher and do not omit these honorifics.\n"
                    "B) Fantasy or non-contemporary world setting:\n"
                    "   - use given-name-first order and convert names to natural English equivalents.\n"
                    "   - do not retain JP honorific suffixes verbatim by default; transcreate naturally.\n"
                    "C) Noble/aristocratic setting (takes priority inside B):\n"
                    "   - transcreate all JP honorifics to noble English equivalents (My Lord/My Lady/Your Grace/Your Highness, etc.).\n"
                    "Do not force transcreation; preserve clarity and narrative flow.\n"
                    "Output schema:\n"
                    "{\n"
                    '  "volume_id": "...",\n'
                    '  "generated_at": "...",\n'
                    '  "processor_version": "1.0",\n'
                    '  "terms": [{"term_jp":"string","preferred_en":"string","notes":"string","confidence":0.0}],\n'
                    '  "idioms": [{"japanese":"string","meaning":"string","preferred_rendering":"string","confidence":0.0}],\n'
                    '  "honorific_policies": [{"pattern":"-san","strategy":"retain_in_english|retain_or_adapt|transcreate_to_english_equivalent|transcreate_to_noble_english_equivalent|given_name_first_convert_to_english_equivalent","rule":"string"}],\n'
                    '  "location_terms": [{"jp":"string","en":"string","notes":"string"}],\n'
                    '  "summary": {"total_terms":0,"total_idioms":0}\n'
                    "}\n"
                ),
                "prompt": (
                    "Generate cultural context glossary for Phase 1.55.\n"
                    "Capture terms that Stage 2 repeatedly needs.\n"
                    "Apply the setting policy matrix strictly:\n"
                    "- Contemporary Japan => retain JP honorifics.\n"
                    "- Fantasy/non-contemporary => given-name-first + English-equivalent naming.\n"
                    "- Noble setting => transcreate all JP honorifics to noble English titles.\n"
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
            payload, fallback_reason, debug_artifact = self._generate_with_optional_cache(
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

            payload = self._postprocess_context_processor_payload(
                processor_id=processor_id,
                payload=payload,
                metadata_en=metadata_en,
                scene_plan_index=scene_plan_index,
            )

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
                if status == "fallback" and fallback_reason:
                    results["processors"][processor_id]["fallback_reason"] = fallback_reason
                if status == "fallback" and debug_artifact:
                    results["processors"][processor_id]["debug_artifact"] = debug_artifact
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
