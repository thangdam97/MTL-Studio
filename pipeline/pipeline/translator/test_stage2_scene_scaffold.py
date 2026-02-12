import json
from pathlib import Path

from pipeline.translator.chapter_processor import ChapterProcessor
from pipeline.translator.context_manager import ContextManager
from pipeline.translator.prompt_loader import PromptLoader


class _DummyClient:
    model = "gemini-2.5-flash"


def _build_processor(work_dir: Path) -> ChapterProcessor:
    manifest_path = work_dir / "manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                {
                    "metadata_en": {"character_profiles": {}},
                    "pipeline_state": {},
                }
            ),
            encoding="utf-8",
        )
    prompt_loader = PromptLoader(target_language="en")
    context_manager = ContextManager(work_dir)
    return ChapterProcessor(_DummyClient(), prompt_loader, context_manager, target_language="en")


def test_stage2_guidance_maps_legacy_labels_to_config_enums(tmp_path):
    processor = _build_processor(tmp_path)

    scene_plan = {
        "chapter_id": "chapter_02",
        "overall_tone": "romcom",
        "pacing_strategy": "tight",
        "scenes": [
            {
                "id": "S01",
                "beat_type": "setup",
                "emotional_arc": "tease",
                "dialogue_register": "internal_monologue",
                "target_rhythm": "quick_sharp_reveal",
                "illustration_anchor": False,
                "start_paragraph": 2,
                "end_paragraph": 20,
            },
            {
                "id": "S02",
                "beat_type": "pivot",
                "emotional_arc": "hesitation",
                "dialogue_register": "strategic",
                "target_rhythm": "slow_reflective",
                "illustration_anchor": False,
                "start_paragraph": 21,
                "end_paragraph": 40,
            },
        ],
        "character_profiles": {},
    }

    guidance = processor._format_stage2_scene_guidance(scene_plan)
    assert "register=casual_teen" in guidance
    assert "register=formal_request" in guidance
    assert "rhythm=short_fragments (4-6 words)" in guidance
    assert "rhythm=long_confession (15-20 words)" in guidance


def test_stage2_guidance_is_injected_before_source_marker(tmp_path):
    processor = _build_processor(tmp_path)

    scene_plan = {
        "chapter_id": "chapter_03",
        "overall_tone": "romcom",
        "pacing_strategy": "alternating banter and confession",
        "scenes": [
            {
                "id": "S01",
                "beat_type": "setup",
                "emotional_arc": "calm",
                "dialogue_register": "casual_teen",
                "target_rhythm": "medium_casual",
                "illustration_anchor": False,
                "start_paragraph": 1,
                "end_paragraph": 8,
            }
        ],
        "character_profiles": {},
    }

    prompt = processor._build_user_prompt(
        chapter_id="chapter_03",
        source_text="JP LINE 1\n\nJP LINE 2",
        context_str="",
        chapter_title="Chapter 3",
        scene_plan=scene_plan,
    )

    stage2_idx = prompt.find("STAGE 2 SCENE RHYTHM SCAFFOLD")
    source_idx = prompt.find("<!-- SOURCE TEXT TO TRANSLATE -->")
    assert stage2_idx != -1
    assert source_idx != -1
    assert stage2_idx < source_idx
    assert "Source precedence rule: Japanese source text is the only source of truth." in prompt
    assert "- Narration soft target: 12-14 words in descriptive passages" in prompt
    assert '- Do not use: "couldn\'t help but"' in prompt
