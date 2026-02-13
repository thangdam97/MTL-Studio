"""
Stage 1 Scene Planner runner.

CLI usage:
  python -m pipeline.planner.agent --volume <volume_id>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.config import WORK_DIR

from .scene_planner import ScenePlanningAgent, ScenePlanningError

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ScenePlannerAgent")

DEFAULT_STAGE1_MODEL = "gemini-2.5-flash"


class Stage1PlannerRunner:
    """Runs Stage 1 planning across chapter files in a volume."""

    def __init__(self, work_base: Optional[Path] = None):
        self.work_base = Path(work_base) if work_base else WORK_DIR

    @staticmethod
    def _load_manifest(manifest_path: Path) -> Dict[str, Any]:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ScenePlanningError(f"Invalid manifest structure: {manifest_path}")
        return data

    @staticmethod
    def _save_manifest(manifest_path: Path, manifest: Dict[str, Any]) -> None:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")

    @staticmethod
    def _load_jp_text(work_dir: Path, source_file: str) -> str:
        jp_path = work_dir / "JP" / source_file
        if not jp_path.exists():
            raise FileNotFoundError(f"JP source file not found: {jp_path}")
        return jp_path.read_text(encoding="utf-8")

    def run(
        self,
        *,
        volume_id: str,
        chapters: Optional[List[str]] = None,
        force: bool = False,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_output_tokens: int = 65535,
        fail_on_partial: bool = False,
    ) -> bool:
        logger.info("=" * 60)
        logger.info(f"STAGE 1 SCENE PLANNER - Volume: {volume_id}")
        logger.info("=" * 60)

        work_dir = self.work_base / volume_id
        manifest_path = work_dir / "manifest.json"
        manifest = self._load_manifest(manifest_path)

        chapter_entries = manifest.get("chapters", [])
        selected = ScenePlanningAgent.filter_requested_chapters(chapter_entries, chapters)
        if not selected:
            logger.error("No chapters selected for planning.")
            return False

        planner = ScenePlanningAgent(
            model=model or DEFAULT_STAGE1_MODEL,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        plans_dir = work_dir / "PLANS"
        plans_dir.mkdir(parents=True, exist_ok=True)

        generated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []

        for idx, chapter in enumerate(selected, 1):
            chapter_id = str(chapter.get("id", f"chapter_{idx:02d}")).strip() or f"chapter_{idx:02d}"
            source_file = str(chapter.get("source_file", "")).strip()
            if not source_file:
                logger.warning(f"[SKIP] {chapter_id}: missing source_file")
                skipped += 1
                continue

            out_path = plans_dir / f"{chapter_id}_scene_plan.json"
            if out_path.exists() and not force:
                logger.info(f"[SKIP] {chapter_id}: plan exists (use --force to regenerate)")
                chapter["scene_plan_file"] = f"PLANS/{out_path.name}"
                skipped += 1
                continue

            try:
                jp_text = self._load_jp_text(work_dir, source_file)
                logger.info(f"[PLAN] {chapter_id} ({source_file})")
                plan = planner.generate_plan(chapter_id=chapter_id, japanese_text=jp_text, model=model)
                planner.save_plan(plan, out_path)
                chapter["scene_plan_file"] = f"PLANS/{out_path.name}"
                generated += 1
            except Exception as e:
                failed += 1
                msg = f"{chapter_id}: {e}"
                errors.append(msg)
                logger.error(f"[FAIL] {msg}")

        pipeline_state = manifest.setdefault("pipeline_state", {})
        planner_state = pipeline_state.setdefault("scene_planner", {})
        planner_state.update(
            {
                "status": "completed" if failed == 0 else "partial",
                "generated_plans": generated,
                "skipped_plans": skipped,
                "failed_plans": failed,
                "total_selected": len(selected),
                "model": model or DEFAULT_STAGE1_MODEL,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": errors[:20],
            }
        )
        self._save_manifest(manifest_path, manifest)

        logger.info("")
        logger.info("=" * 60)
        logger.info("STAGE 1 SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Selected:  {len(selected)}")
        logger.info(f"Generated: {generated}")
        logger.info(f"Skipped:   {skipped}")
        logger.info(f"Failed:    {failed}")
        logger.info(f"Plans dir: {plans_dir}")
        logger.info("=" * 60)

        if fail_on_partial:
            return failed == 0
        return (generated + skipped) > 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 1 Scene Planner (v1.6 pre-translation narrative scaffold)"
    )
    parser.add_argument("--volume", required=True, help="Volume ID under WORK/")
    parser.add_argument(
        "--work-dir",
        default=str(WORK_DIR),
        help="Base WORK directory",
    )
    parser.add_argument(
        "--chapters",
        nargs="+",
        help="Optional chapter selectors (id, source file, or number)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing plan files",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_STAGE1_MODEL,
        help=f"Gemini model override for planning (default: {DEFAULT_STAGE1_MODEL})",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="Planning temperature (default: 0.3)",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=65535,
        help="Max output tokens for planning response (default: 65535)",
    )
    parser.add_argument(
        "--fail-on-partial",
        action="store_true",
        help="Exit non-zero when any chapter planning fails",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runner = Stage1PlannerRunner(work_base=Path(args.work_dir))
    ok = runner.run(
        volume_id=args.volume,
        chapters=args.chapters,
        force=args.force,
        model=args.model,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        fail_on_partial=args.fail_on_partial,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
