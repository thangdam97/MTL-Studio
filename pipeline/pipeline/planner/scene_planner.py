"""
Scene Planning Agent (v1.6 Stage 1).

Generates a structured scene plan from Japanese chapter text before translation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.common.gemini_client import GeminiClient
from pipeline.config import PIPELINE_ROOT

logger = logging.getLogger(__name__)


class ScenePlanningError(Exception):
    """Base exception for scene planning failures."""


@dataclass
class SceneBeat:
    """A narrative beat identified by Stage 1."""

    id: str
    beat_type: str
    emotional_arc: str
    dialogue_register: str
    target_rhythm: str
    illustration_anchor: bool = False
    start_paragraph: Optional[int] = None
    end_paragraph: Optional[int] = None


@dataclass
class CharacterProfile:
    """Chapter-local profile for character speech and emotion."""

    name: str
    emotional_state: str
    sentence_bias: str
    victory_patterns: List[str]
    denial_patterns: List[str]
    relationship_dynamic: str


@dataclass
class ScenePlan:
    """Narrative scaffold output for a chapter."""

    chapter_id: str
    scenes: List[SceneBeat]
    character_profiles: Dict[str, CharacterProfile]
    overall_tone: str
    pacing_strategy: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass plan to JSON-serializable dict."""
        return {
            "chapter_id": self.chapter_id,
            "scenes": [asdict(scene) for scene in self.scenes],
            "character_profiles": {
                name: asdict(profile)
                for name, profile in self.character_profiles.items()
            },
            "overall_tone": self.overall_tone,
            "pacing_strategy": self.pacing_strategy,
        }


class ScenePlanningAgent:
    """
    Stage 1 planner that creates scene/character rhythm scaffolds.

    Input:
      - chapter_id
      - Japanese chapter text
    Output:
      - ScenePlan dataclass
    """

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        config_path: Optional[Path] = None,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.3,
        max_output_tokens: int = 65535,
    ):
        self.config_path = config_path or (PIPELINE_ROOT / "config" / "planning_config.json")
        self.config = self._load_config(self.config_path)
        self.allowed_beat_types = self._extract_allowed_beat_types(self.config)
        self.allowed_registers = self._extract_allowed_registers(self.config)
        self.rhythm_targets = self._extract_rhythm_targets(self.config)
        self.default_rhythm = self._extract_default_rhythm(self.config)
        self._rhythm_levels = self._build_rhythm_levels()

        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.gemini = gemini_client or GeminiClient(model=model, enable_caching=False)
        self.planning_prompt = self._build_planning_prompt()

    @staticmethod
    def _extract_allowed_beat_types(config: Dict[str, Any]) -> List[str]:
        beat_types = config.get("beat_types", {})
        if isinstance(beat_types, dict):
            return [str(k) for k in beat_types.keys()]
        if isinstance(beat_types, list):
            return [str(v) for v in beat_types]
        return ["setup", "escalation", "punchline", "pivot", "illustration_anchor"]

    @staticmethod
    def _extract_allowed_registers(config: Dict[str, Any]) -> List[str]:
        registers = config.get("dialogue_registers", {})
        if isinstance(registers, dict):
            return [str(k) for k in registers.keys()]
        if isinstance(registers, list):
            return [str(v) for v in registers]
        return []

    @staticmethod
    def _extract_rhythm_targets(config: Dict[str, Any]) -> Dict[str, str]:
        rhythm_targets = config.get("rhythm_targets", {})
        if not isinstance(rhythm_targets, dict):
            return {}
        extracted: Dict[str, str] = {}
        for raw_key, raw_val in rhythm_targets.items():
            key = str(raw_key).strip()
            if not key:
                continue
            if isinstance(raw_val, dict):
                extracted[key] = str(raw_val.get("word_range", "")).strip()
            elif isinstance(raw_val, str):
                extracted[key] = raw_val.strip()
        return extracted

    @staticmethod
    def _extract_default_rhythm(config: Dict[str, Any]) -> str:
        rhythm_targets = config.get("rhythm_targets", {})
        if isinstance(rhythm_targets, dict) and rhythm_targets:
            first_key = str(next(iter(rhythm_targets.keys()))).strip()
            if first_key:
                return first_key
        return "medium_casual"

    @staticmethod
    def _load_config(config_path: Path) -> Dict[str, Any]:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.warning(f"Planning config not found at {config_path}; using defaults.")
        return {
            "beat_types": ["setup", "escalation", "punchline", "pivot", "illustration_anchor"],
            "dialogue_registers": {},
            "rhythm_targets": {},
        }

    def _build_planning_prompt(self) -> str:
        beat_types = ", ".join(self.allowed_beat_types) if self.allowed_beat_types else "setup, escalation, punchline, pivot"
        if self.allowed_registers:
            register_hint = ", ".join(self.allowed_registers[:12])
        else:
            register_hint = "casual_teen, flustered_defense, smug_teasing, formal_request"
        if self.rhythm_targets:
            rhythm_hint = ", ".join(list(self.rhythm_targets.keys())[:12])
        else:
            rhythm_hint = "short_fragments, medium_casual, long_confession"
        return (
            "# SCENE PLANNING DIRECTIVE\n\n"
            "You are a narrative structure analyst for Japanese light novels.\n"
            "DO NOT translate text.\n"
            "Output one JSON object only.\n\n"
            "Required top-level keys:\n"
            "- chapter_id (string)\n"
            "- scenes (array)\n"
            "- character_profiles (object)\n"
            "- overall_tone (string)\n"
            "- pacing_strategy (string)\n\n"
            "Scene item keys:\n"
            "- id (string)\n"
            f"- beat_type (one of: {beat_types})\n"
            "- emotional_arc (string)\n"
            f"- dialogue_register (suggested set: {register_hint})\n"
            f"- target_rhythm (one of: {rhythm_hint})\n"
            "- illustration_anchor (boolean)\n"
            "- consistency rule: if beat_type is 'illustration_anchor', illustration_anchor must be true\n"
            "- start_paragraph (integer or null)\n"
            "- end_paragraph (integer or null)\n\n"
            "Character profile keys:\n"
            "- name, emotional_state, sentence_bias, relationship_dynamic (string)\n"
            "- victory_patterns, denial_patterns (array of strings)\n\n"
            "Keep output compact and actionable."
        )

    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return paragraphs if paragraphs else [text.strip()] if text.strip() else []

    def _build_planning_input(self, chapter_id: str, japanese_text: str) -> str:
        paragraphs = self._split_paragraphs(japanese_text)
        numbered = []
        for idx, paragraph in enumerate(paragraphs, 1):
            numbered.append(f"[P{idx}] {paragraph}")
        numbered_text = "\n\n".join(numbered)
        return (
            f"CHAPTER_ID: {chapter_id}\n\n"
            "JAPANESE_TEXT:\n"
            f"{numbered_text}\n"
        )

    def generate_plan(
        self,
        chapter_id: str,
        japanese_text: str,
        *,
        model: Optional[str] = None,
    ) -> ScenePlan:
        if not japanese_text or not japanese_text.strip():
            raise ScenePlanningError(f"Empty Japanese text for chapter {chapter_id}")

        paragraph_count = len(self._split_paragraphs(japanese_text))
        planning_input = self._build_planning_input(chapter_id, japanese_text)
        response = self.gemini.generate(
            prompt=planning_input,
            system_instruction=self.planning_prompt,
            model=model or self.model,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )
        raw = getattr(response, "content", None) or ""
        if not raw.strip():
            raise ScenePlanningError(f"Planner returned empty response for {chapter_id}")

        plan_dict = self._parse_response_json(raw)
        if "chapter_id" not in plan_dict or not str(plan_dict.get("chapter_id", "")).strip():
            plan_dict["chapter_id"] = chapter_id

        normalized = self._normalize_plan_dict(plan_dict, total_paragraphs=paragraph_count)
        return self._build_scene_plan(normalized)

    @staticmethod
    def _extract_json_from_text(text: str) -> str:
        candidate = text.strip()
        fenced = re.findall(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced[0].strip()

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            return candidate[start : end + 1]
        return candidate

    def _parse_response_json(self, text: str) -> Dict[str, Any]:
        json_text = self._extract_json_from_text(text)
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ScenePlanningError(f"Failed parsing planner JSON: {e}") from e

        if not isinstance(parsed, dict):
            raise ScenePlanningError("Planner response must be a JSON object")
        return parsed

    @staticmethod
    def _coerce_text(value: Any, fallback: str = "") -> str:
        if value is None:
            return fallback
        if isinstance(value, str):
            out = value.strip()
            return out if out else fallback
        if isinstance(value, (int, float, bool)):
            return str(value)
        return fallback

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if value.isdigit():
                return int(value)
        return None

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _resolve_illustration_anchor(self, raw_scene: Dict[str, Any], beat_type: str) -> bool:
        """
        Resolve illustration anchor with resilient key lookup.

        Models sometimes emit alternate fields (e.g., scene_anchor, visual_anchor)
        or only signal this through beat_type. We preserve that intent here.
        """
        anchor_keys = (
            "illustration_anchor",
            "scene_anchor",
            "visual_anchor",
            "is_illustration_anchor",
            "has_illustration_anchor",
            "anchor_illustration",
        )
        for key in anchor_keys:
            if key in raw_scene:
                return self._coerce_bool(raw_scene.get(key))

        # Preserve explicit beat semantics when planner omits the boolean field.
        return beat_type == "illustration_anchor"

    @staticmethod
    def _coerce_string_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        for item in values:
            text = ScenePlanningAgent._coerce_text(item, "")
            if text:
                out.append(text)
        return out

    @staticmethod
    def _normalize_token(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    @staticmethod
    def _parse_word_range(value: str) -> Optional[tuple]:
        if not value:
            return None
        match = re.search(r"(\d+)\s*[-–]\s*(\d+)", value)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            return (start, end)
        single = re.search(r"\b(\d+)\s*words?\b", value.lower())
        if single:
            num = int(single.group(1))
            return (num, num)
        return None

    def _build_rhythm_levels(self) -> List[tuple]:
        levels: List[tuple] = []
        for key, word_range in self.rhythm_targets.items():
            parsed = self._parse_word_range(word_range)
            if not parsed:
                continue
            min_words, max_words = parsed
            midpoint = (min_words + max_words) / 2.0
            levels.append((key, min_words, max_words, midpoint))
        levels.sort(key=lambda item: item[3])
        return levels

    def _map_dialogue_register(self, raw_value: Any) -> str:
        if not self.allowed_registers:
            return self._coerce_text(raw_value, "casual_teen")

        fallback = "casual_teen" if "casual_teen" in self.allowed_registers else self.allowed_registers[0]
        raw_text = self._coerce_text(raw_value, fallback)
        raw_norm = self._normalize_token(raw_text)

        norm_to_register = {
            self._normalize_token(register): register
            for register in self.allowed_registers
        }
        if raw_norm in norm_to_register:
            return norm_to_register[raw_norm]

        for norm_key, register in norm_to_register.items():
            if norm_key and norm_key in raw_norm:
                return register

        def pick(candidates: Sequence[str], default: str) -> str:
            for candidate in candidates:
                if candidate in self.allowed_registers:
                    return candidate
            return default

        tokens = set(raw_norm.split("_")) if raw_norm else set()
        if tokens.intersection({"formal", "polite", "request", "strategic", "assertive"}):
            return pick(["formal_request", "casual_teen"], fallback)
        if tokens.intersection({"teasing", "smug", "playful", "banter", "competitive", "provocative"}):
            return pick(["smug_teasing", "casual_teen"], fallback)
        if tokens.intersection({"flustered", "defense", "defensive", "denial", "embarrassed", "shy", "panic"}):
            return pick(["flustered_defense", "breathless_shock", "casual_teen"], fallback)
        if tokens.intersection({"shock", "shocked", "breathless", "surprised"}):
            return pick(["breathless_shock", "flustered_defense", "casual_teen"], fallback)
        if tokens.intersection({"internal", "monologue", "narration", "reflective", "introspective"}):
            return pick(["casual_teen", "formal_request"], fallback)

        return fallback

    def _map_target_rhythm(self, raw_value: Any) -> str:
        if not self.rhythm_targets:
            return self._coerce_text(raw_value, self.default_rhythm)

        raw_text = self._coerce_text(raw_value, self.default_rhythm)
        raw_norm = self._normalize_token(raw_text)

        norm_to_key = {
            self._normalize_token(key): key
            for key in self.rhythm_targets.keys()
        }
        if raw_norm in norm_to_key:
            return norm_to_key[raw_norm]

        for norm_key, key in norm_to_key.items():
            if norm_key and norm_key in raw_norm:
                return key

        for key, word_range in self.rhythm_targets.items():
            if self._normalize_token(word_range) == raw_norm:
                return key

        parsed_range = self._parse_word_range(raw_text)
        if parsed_range and self._rhythm_levels:
            midpoint = (parsed_range[0] + parsed_range[1]) / 2.0
            return min(self._rhythm_levels, key=lambda item: abs(item[3] - midpoint))[0]

        if self._rhythm_levels:
            ordered_keys = [item[0] for item in self._rhythm_levels]
            short_keywords = {"quick", "fast", "rapid", "brief", "short", "snappy", "witty", "punchline", "reveal"}
            long_keywords = {"slow", "deliberate", "reflective", "strategic", "tender", "confession", "sensual", "climactic"}
            tokens = set(raw_norm.split("_")) if raw_norm else set()

            if tokens.intersection(short_keywords):
                return ordered_keys[0]
            if tokens.intersection(long_keywords):
                return ordered_keys[-1]

            return ordered_keys[len(ordered_keys) // 2]

        return self.default_rhythm

    def _heal_tiny_coverage_gaps(
        self,
        scenes: List[Dict[str, Any]],
        *,
        total_paragraphs: Optional[int] = None,
        max_gap: int = 2,
    ) -> None:
        if len(scenes) < 2:
            return

        healed = 0
        for idx in range(len(scenes) - 1):
            current = scenes[idx]
            nxt = scenes[idx + 1]
            current_end = current.get("end_paragraph")
            next_start = nxt.get("start_paragraph")

            if not isinstance(current_end, int) or not isinstance(next_start, int):
                continue

            gap_size = next_start - current_end - 1
            if gap_size > 0 and gap_size <= max_gap:
                current["end_paragraph"] = next_start - 1
                healed += 1

        if isinstance(total_paragraphs, int) and total_paragraphs > 0:
            last_end = scenes[-1].get("end_paragraph")
            if isinstance(last_end, int):
                tail_gap = total_paragraphs - last_end
                if tail_gap > 0 and tail_gap <= max_gap:
                    scenes[-1]["end_paragraph"] = total_paragraphs
                    healed += 1

        if healed:
            logger.debug(f"Healed {healed} tiny scene coverage gap(s) (<= {max_gap} paragraph(s)).")

    def _normalize_scene(self, raw_scene: Dict[str, Any], idx: int) -> Dict[str, Any]:
        beat_type = self._coerce_text(raw_scene.get("beat_type"), "setup").lower()
        if beat_type not in self.allowed_beat_types:
            logger.debug(f"Unknown beat_type '{beat_type}' in scene {idx}; fallback to setup.")
            beat_type = "setup"

        start_paragraph = self._coerce_int(raw_scene.get("start_paragraph"))
        end_paragraph = self._coerce_int(raw_scene.get("end_paragraph"))
        if start_paragraph is not None and end_paragraph is not None and end_paragraph < start_paragraph:
            end_paragraph = start_paragraph

        return {
            "id": self._coerce_text(raw_scene.get("id"), f"scene_{idx:02d}"),
            "beat_type": beat_type,
            "emotional_arc": self._coerce_text(raw_scene.get("emotional_arc"), "neutral_progression"),
            "dialogue_register": self._map_dialogue_register(raw_scene.get("dialogue_register")),
            "target_rhythm": self._map_target_rhythm(raw_scene.get("target_rhythm")),
            "illustration_anchor": self._resolve_illustration_anchor(raw_scene, beat_type),
            "start_paragraph": start_paragraph,
            "end_paragraph": end_paragraph,
        }

    def _normalize_profiles(self, raw_profiles: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(raw_profiles, dict):
            return {}

        profiles: Dict[str, Dict[str, Any]] = {}
        for raw_name, raw_profile in raw_profiles.items():
            key_name = self._coerce_text(raw_name, "")
            if not key_name or not isinstance(raw_profile, dict):
                continue

            name = self._coerce_text(raw_profile.get("name"), key_name)
            profiles[key_name] = {
                "name": name,
                "emotional_state": self._coerce_text(raw_profile.get("emotional_state"), "neutral"),
                "sentence_bias": self._coerce_text(raw_profile.get("sentence_bias"), "8-10w medium"),
                "victory_patterns": self._coerce_string_list(raw_profile.get("victory_patterns")),
                "denial_patterns": self._coerce_string_list(raw_profile.get("denial_patterns")),
                "relationship_dynamic": self._coerce_text(raw_profile.get("relationship_dynamic"), "unspecified"),
            }
        return profiles

    def _normalize_plan_dict(
        self,
        plan_dict: Dict[str, Any],
        *,
        total_paragraphs: Optional[int] = None,
    ) -> Dict[str, Any]:
        chapter_id = self._coerce_text(plan_dict.get("chapter_id"), "chapter_unknown")
        raw_scenes = plan_dict.get("scenes", [])
        scenes: List[Dict[str, Any]] = []

        if isinstance(raw_scenes, list):
            for idx, raw_scene in enumerate(raw_scenes, 1):
                if isinstance(raw_scene, dict):
                    scenes.append(self._normalize_scene(raw_scene, idx))

        if not scenes:
            scenes = [
                {
                    "id": "scene_01",
                    "beat_type": "setup",
                    "emotional_arc": "neutral_progression",
                    "dialogue_register": "casual_teen",
                    "target_rhythm": self.default_rhythm,
                    "illustration_anchor": False,
                    "start_paragraph": 1,
                    "end_paragraph": None,
                }
            ]

        self._heal_tiny_coverage_gaps(scenes, total_paragraphs=total_paragraphs)
        profiles = self._normalize_profiles(plan_dict.get("character_profiles", {}))

        return {
            "chapter_id": chapter_id,
            "scenes": scenes,
            "character_profiles": profiles,
            "overall_tone": self._coerce_text(plan_dict.get("overall_tone"), "neutral"),
            "pacing_strategy": self._coerce_text(plan_dict.get("pacing_strategy"), "standard"),
        }

    @staticmethod
    def _build_scene_plan(plan_dict: Dict[str, Any]) -> ScenePlan:
        scenes = [SceneBeat(**scene) for scene in plan_dict.get("scenes", [])]
        character_profiles = {
            name: CharacterProfile(**profile)
            for name, profile in plan_dict.get("character_profiles", {}).items()
        }
        return ScenePlan(
            chapter_id=plan_dict.get("chapter_id", "chapter_unknown"),
            scenes=scenes,
            character_profiles=character_profiles,
            overall_tone=plan_dict.get("overall_tone", "neutral"),
            pacing_strategy=plan_dict.get("pacing_strategy", "standard"),
        )

    @staticmethod
    def save_plan(plan: ScenePlan, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved scene plan: {output_path}")

    @staticmethod
    def load_plan(path: Path) -> ScenePlan:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ScenePlanningError(f"Invalid scene plan file: {path}")
        return ScenePlanningAgent._build_scene_plan(data)

    @staticmethod
    def filter_requested_chapters(
        chapters: Sequence[Dict[str, Any]],
        requested: Optional[Sequence[str]],
    ) -> List[Dict[str, Any]]:
        """Filter chapter dicts by requested IDs, source files, or chapter numbers."""
        chapter_list = [ch for ch in chapters if isinstance(ch, dict)]
        if not requested:
            return chapter_list

        normalized = {str(v).strip().lower() for v in requested if str(v).strip()}
        selected: List[Dict[str, Any]] = []
        for chapter in chapter_list:
            chapter_id = str(chapter.get("id", "")).strip()
            source_file = str(chapter.get("source_file", "")).strip()
            source_stem = Path(source_file).stem if source_file else ""
            candidates = {
                chapter_id.lower(),
                source_file.lower(),
                source_stem.lower(),
            }

            match = re.search(r"(\d+)", chapter_id) or re.search(r"(\d+)", source_stem)
            if match:
                number = str(int(match.group(1)))
                candidates.add(number)
                candidates.add(f"chapter_{int(number):02d}")

            if normalized.intersection(candidates):
                selected.append(chapter)
        return selected
