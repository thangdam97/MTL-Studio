import json
from dataclasses import dataclass

from pipeline.planner.scene_planner import ScenePlanningAgent


@dataclass
class _DummyResponse:
    content: str


class _DummyGeminiClient:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return _DummyResponse(content=self.payload)


def test_generate_plan_parses_fenced_json():
    payload = """```json
{
  "chapter_id": "chapter_02",
  "scenes": [
    {
      "id": "scene_open",
      "beat_type": "setup",
      "emotional_arc": "neutral -> tease",
      "dialogue_register": "casual_teen",
      "target_rhythm": "8-10 words",
      "illustration_anchor": false,
      "start_paragraph": 1,
      "end_paragraph": 4
    }
  ],
  "character_profiles": {
    "Ako": {
      "name": "Ako",
      "emotional_state": "playful_banter",
      "sentence_bias": "8-10w medium",
      "victory_patterns": ["Got you."],
      "denial_patterns": [],
      "relationship_dynamic": "teasing_aggressor"
    }
  },
  "overall_tone": "romcom",
  "pacing_strategy": "quick_escalation"
}
```"""
    client = _DummyGeminiClient(payload)
    planner = ScenePlanningAgent(gemini_client=client)
    plan = planner.generate_plan("chapter_02", "JP line 1\n\nJP line 2")

    assert plan.chapter_id == "chapter_02"
    assert len(plan.scenes) == 1
    assert plan.scenes[0].id == "scene_open"
    assert "Ako" in plan.character_profiles
    assert client.calls, "Expected generate() to be called"


def test_generate_plan_normalizes_invalid_types():
    payload = """
{
  "chapter_id": "",
  "scenes": [
    {
      "id": 123,
      "beat_type": "INVALID_BEAT",
      "emotional_arc": null,
      "dialogue_register": 99,
      "target_rhythm": "",
      "illustration_anchor": "yes",
      "start_paragraph": "10",
      "end_paragraph": "5"
    }
  ],
  "character_profiles": {
    "Hero": {
      "name": null,
      "emotional_state": 1,
      "sentence_bias": null,
      "victory_patterns": [1, "Done."],
      "denial_patterns": "not-a-list",
      "relationship_dynamic": ""
    }
  },
  "overall_tone": null,
  "pacing_strategy": null
}
"""
    client = _DummyGeminiClient(payload)
    planner = ScenePlanningAgent(gemini_client=client)
    plan = planner.generate_plan("chapter_99", "JP line")

    assert plan.chapter_id == "chapter_99"
    assert plan.scenes[0].beat_type == "setup"
    assert plan.scenes[0].illustration_anchor is True
    assert plan.scenes[0].start_paragraph == 10
    assert plan.scenes[0].end_paragraph == 10
    assert plan.character_profiles["Hero"].name == "Hero"
    assert plan.character_profiles["Hero"].victory_patterns == ["1", "Done."]


def test_filter_requested_chapters_supports_id_file_and_number():
    chapters = [
        {"id": "CHAPTER_01", "source_file": "CHAPTER_01.md"},
        {"id": "chapter_02", "source_file": "prologue_02.md"},
        {"id": "AFTERWORD", "source_file": "AFTERWORD.md"},
    ]

    selected = ScenePlanningAgent.filter_requested_chapters(chapters, ["1", "prologue_02", "afterword.md"])
    ids = [ch["id"] for ch in selected]

    assert "CHAPTER_01" in ids
    assert "chapter_02" in ids
    assert "AFTERWORD" in ids


def test_generate_plan_hard_maps_register_and_rhythm_enums_and_fills_tiny_gaps(tmp_path):
    config_path = tmp_path / "planning_config.json"
    config_path.write_text(
        json.dumps(
            {
                "beat_types": ["setup", "escalation", "punchline", "pivot", "illustration_anchor"],
                "dialogue_registers": {
                    "casual_teen": "default casual",
                    "flustered_defense": "denial and panic",
                    "smug_teasing": "playful pressure",
                    "formal_request": "polite request",
                    "breathless_shock": "shocked fragments",
                },
                "rhythm_targets": {
                    "short_fragments": {"word_range": "4-6 words"},
                    "medium_casual": {"word_range": "8-10 words"},
                    "long_confession": {"word_range": "15-20 words"},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = """
{
  "chapter_id": "chapter_02",
  "scenes": [
    {
      "id": "S01",
      "beat_type": "setup",
      "emotional_arc": "neutral",
      "dialogue_register": "internal_monologue",
      "target_rhythm": "quick_sharp_reveal",
      "illustration_anchor": false,
      "start_paragraph": 2,
      "end_paragraph": 4
    },
    {
      "id": "S02",
      "beat_type": "pivot",
      "emotional_arc": "rising",
      "dialogue_register": "shy_request",
      "target_rhythm": "slow_reflective",
      "illustration_anchor": false,
      "start_paragraph": 6,
      "end_paragraph": 8
    },
    {
      "id": "S03",
      "beat_type": "escalation",
      "emotional_arc": "push",
      "dialogue_register": "competitive",
      "target_rhythm": "8-10 words",
      "illustration_anchor": false,
      "start_paragraph": 9,
      "end_paragraph": 17
    }
  ],
  "character_profiles": {},
  "overall_tone": "romcom",
  "pacing_strategy": "tight"
}
"""
    chapter_text = "\n\n".join([f"P{i}" for i in range(1, 19)])
    client = _DummyGeminiClient(payload)
    planner = ScenePlanningAgent(gemini_client=client, config_path=config_path)
    plan = planner.generate_plan("chapter_02", chapter_text)

    assert [scene.dialogue_register for scene in plan.scenes] == [
        "casual_teen",
        "formal_request",
        "smug_teasing",
    ]
    assert [scene.target_rhythm for scene in plan.scenes] == [
        "short_fragments",
        "long_confession",
        "medium_casual",
    ]

    # Tiny internal gap P5 should be absorbed into S01.
    assert plan.scenes[0].end_paragraph == 5
    # Tiny tail gap P18 should be absorbed into the final scene.
    assert plan.scenes[-1].end_paragraph == 18


def test_generate_plan_infers_illustration_anchor_from_beat_and_alt_keys():
    payload = """
{
  "chapter_id": "chapter_03",
  "scenes": [
    {
      "id": "S01",
      "beat_type": "illustration_anchor",
      "emotional_arc": "visual beat",
      "dialogue_register": "casual_teen",
      "target_rhythm": "medium_casual",
      "start_paragraph": 1,
      "end_paragraph": 3
    },
    {
      "id": "S02",
      "beat_type": "setup",
      "emotional_arc": "setup",
      "dialogue_register": "casual_teen",
      "target_rhythm": "medium_casual",
      "scene_anchor": "yes",
      "start_paragraph": 4,
      "end_paragraph": 6
    }
  ],
  "character_profiles": {},
  "overall_tone": "romcom",
  "pacing_strategy": "steady"
}
"""
    client = _DummyGeminiClient(payload)
    planner = ScenePlanningAgent(gemini_client=client)
    plan = planner.generate_plan("chapter_03", "P1\n\nP2\n\nP3\n\nP4\n\nP5\n\nP6")

    assert plan.scenes[0].illustration_anchor is True
    assert plan.scenes[1].illustration_anchor is True
