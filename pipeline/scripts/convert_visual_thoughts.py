#!/usr/bin/env python3
"""
Convert Visual Thought Logs (JSON) → Markdown

Converts Gemini 3 Pro's visual analysis thinking process stored in
cache/thoughts/*.json into human-readable markdown files that mirror
the THINKING/*.md format used by Gemini 2.5 Pro's translation reasoning.

Output: WORK/{volume_id}/THINKING/VISUAL_THINKING.md  (consolidated)
    or: WORK/{volume_id}/THINKING/visual_{id}_THINKING.md (per-illustration)

Usage:
    python scripts/convert_visual_thoughts.py <volume_id>
    python scripts/convert_visual_thoughts.py <volume_id> --split
    python scripts/convert_visual_thoughts.py <volume_id> --filter illust
    python scripts/convert_visual_thoughts.py <volume_id> --filter kuchie
    python scripts/convert_visual_thoughts.py <volume_id> --with-cache
"""

import json
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_volume_dir(work_root: Path, volume_id: str) -> Optional[Path]:
    """Locate volume directory by trailing ID slug."""
    for d in sorted(work_root.iterdir()):
        if d.is_dir() and d.name.endswith(volume_id):
            return d
    return None


def load_thought_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a single thought log JSON file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load {path.name}: {e}")
        return None


def load_visual_cache_entry(cache: Dict, illust_id: str) -> Optional[Dict]:
    """Get visual_ground_truth from visual_cache.json for an illustration."""
    entry = cache.get(illust_id)
    if not entry:
        return None
    return entry.get("visual_ground_truth")


def format_timestamp(iso_ts: str) -> str:
    """Convert ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return iso_ts or "Unknown"


def classify_illustration(illust_id: str) -> str:
    """Return a human label for the illustration type."""
    if illust_id.startswith("kuchie"):
        return "Color Plate (Kuchie)"
    elif illust_id.startswith("illust"):
        return "Inline Illustration"
    elif illust_id == "cover":
        return "Cover Art"
    return "Illustration"


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------

def render_thought_entry(
    data: Dict[str, Any],
    cache_entry: Optional[Dict] = None,
    include_cache: bool = False,
) -> str:
    """Render a single thought log entry as markdown."""

    illust_id = data.get("illustration_id", "unknown")
    model = data.get("model", "unknown")
    thinking_level = data.get("thinking_level", "N/A")
    proc_time = data.get("processing_time_seconds", 0)
    timestamp = format_timestamp(data.get("timestamp"))
    success = data.get("success", False)
    error = data.get("error")
    thoughts = data.get("thoughts", [])
    iterations = data.get("iterations", 1)
    illust_type = classify_illustration(illust_id)

    lines: List[str] = []

    # Header
    lines.append(f"## {illust_id}")
    lines.append("")
    lines.append(f"**Type**: {illust_type}")
    lines.append(f"**Model**: {model}")
    lines.append(f"**Thinking Level**: {thinking_level}")
    lines.append(f"**Processing Time**: {proc_time:.1f}s")
    lines.append(f"**Iterations**: {iterations}")
    lines.append(f"**Analyzed**: {timestamp}")
    lines.append(f"**Status**: {'✅ Success' if success else '❌ Failed'}")
    if error:
        lines.append(f"**Error**: {error}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Thinking process
    if thoughts:
        lines.append("### Gemini 3 Pro Visual Reasoning")
        lines.append("")
        for i, thought in enumerate(thoughts):
            if len(thoughts) > 1:
                lines.append(f"**Thought {i + 1}:**")
                lines.append("")
            lines.append(thought.strip())
            lines.append("")
    else:
        lines.append("### Gemini 3 Pro Visual Reasoning")
        lines.append("")
        lines.append("*No thinking process captured for this illustration.*")
        lines.append("")

    # Optional: Art Director's Notes from visual_cache.json
    if include_cache and cache_entry:
        lines.append("### Art Director's Notes (Output)")
        lines.append("")

        composition = cache_entry.get("composition", "")
        emotional = cache_entry.get("emotional_delta", "")
        details = cache_entry.get("key_details", {})
        directives = cache_entry.get("narrative_directives", [])

        if composition:
            lines.append(f"**Composition**: {composition}")
            lines.append("")
        if emotional:
            lines.append(f"**Emotional Context**: {emotional}")
            lines.append("")
        if details:
            lines.append("**Key Visual Details**:")
            for key, value in details.items():
                if isinstance(value, dict):
                    lines.append(f"- **{key}**:")
                    for sub_key, sub_val in value.items():
                        lines.append(f"  - {sub_key}: {sub_val}")
                else:
                    lines.append(f"- {key}: {value}")
            lines.append("")
        if directives:
            lines.append("**Translation Directives**:")
            for d in directives:
                lines.append(f"- {d}")
            lines.append("")

    return "\n".join(lines)


def render_consolidated_markdown(
    entries: List[Dict[str, Any]],
    volume_name: str,
    visual_cache: Optional[Dict] = None,
    include_cache: bool = False,
) -> str:
    """Render all thought entries into one consolidated markdown document."""

    total_time = sum(e.get("processing_time_seconds", 0) for e in entries)
    success_count = sum(1 for e in entries if e.get("success"))
    kuchie_count = sum(1 for e in entries if e["illustration_id"].startswith("kuchie"))
    illust_count = sum(1 for e in entries if e["illustration_id"].startswith("illust"))
    cover_count = sum(1 for e in entries if e["illustration_id"] == "cover")

    lines: List[str] = []

    # Document header – mirrors THINKING/chapter_XX_THINKING.md style
    lines.append("# Visual Analysis Reasoning Process")
    lines.append("")
    lines.append(f"**Volume**: {volume_name}")
    # Derive model from entries (avoid hardcoding)
    models_used = set(e.get("model", "unknown") for e in entries)
    model_str = ", ".join(sorted(models_used)) if models_used else "unknown"

    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Model**: {model_str}")
    lines.append(f"**Phase**: 1.6 (Multimodal Processor)")
    lines.append(f"**Illustrations Analyzed**: {len(entries)}"
                 f" ({illust_count} inline, {kuchie_count} kuchie, {cover_count} cover)")
    lines.append(f"**Total Processing Time**: {total_time:.1f}s"
                 f" (avg {total_time / len(entries):.1f}s)")
    lines.append(f"**Success Rate**: {success_count}/{len(entries)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("This document contains the internal reasoning process that "
                 "Gemini 3 Pro used while analyzing each illustration. "
                 "These \"thinking\" outputs show how the model interpreted "
                 "visual elements, identified emotional cues, and formulated "
                 "Art Director's Notes for the translation phase.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Entries grouped by type
    groups = [
        ("Cover Art", [e for e in entries if e["illustration_id"] == "cover"]),
        ("Color Plates (Kuchie)", [e for e in entries if e["illustration_id"].startswith("kuchie")]),
        ("Inline Illustrations", [e for e in entries if e["illustration_id"].startswith("illust")]),
    ]

    for group_title, group_entries in groups:
        if not group_entries:
            continue
        lines.append(f"# {group_title}")
        lines.append("")
        for entry in group_entries:
            cache_entry = None
            if include_cache and visual_cache:
                cache_entry = load_visual_cache_entry(visual_cache, entry["illustration_id"])
            lines.append(render_thought_entry(entry, cache_entry, include_cache))
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*This visual thinking process is automatically generated by "
                 "Gemini 3 Pro during Phase 1.6 (Multimodal Processor) and "
                 "provides insight into the visual analysis decision-making process.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert Gemini 3 Pro visual thought logs (JSON) to markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/convert_visual_thoughts.py 1d46
  python scripts/convert_visual_thoughts.py 1d46 --split
  python scripts/convert_visual_thoughts.py 1d46 --with-cache
  python scripts/convert_visual_thoughts.py 1d46 --filter kuchie
  python scripts/convert_visual_thoughts.py 1d46 --filter illust --split
        """,
    )
    parser.add_argument("volume_id", help="Volume ID (e.g. 1d46)")
    parser.add_argument(
        "--split", action="store_true",
        help="Generate one markdown file per illustration instead of consolidated"
    )
    parser.add_argument(
        "--with-cache", action="store_true",
        help="Include Art Director's Notes output from visual_cache.json"
    )
    parser.add_argument(
        "--filter",
        choices=["illust", "kuchie", "cover"],
        help="Only convert a specific illustration type"
    )
    parser.add_argument(
        "--output-dir",
        help="Custom output directory (default: THINKING/ inside volume)"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    # Locate volume
    work_root = Path("WORK")
    if not work_root.exists():
        work_root = Path(__file__).parent.parent / "WORK"
    if not work_root.exists():
        logger.error("WORK directory not found. Run from pipeline/ directory.")
        sys.exit(1)

    volume_dir = find_volume_dir(work_root, args.volume_id)
    if not volume_dir:
        logger.error(f"No volume found matching ID: {args.volume_id}")
        sys.exit(1)

    logger.info(f"Volume: {volume_dir.name}")

    # Locate thought logs
    thoughts_dir = volume_dir / "cache" / "thoughts"
    if not thoughts_dir.exists():
        logger.error(f"No thought logs found at: {thoughts_dir}")
        logger.error("Run Phase 1.6 first: python mtl.py phase1.6 <volume_id>")
        sys.exit(1)

    # Load all JSON thought logs
    json_files = sorted(thoughts_dir.glob("*.json"))
    if not json_files:
        logger.error("No .json files found in cache/thoughts/")
        sys.exit(1)

    entries: List[Dict[str, Any]] = []
    for jf in json_files:
        data = load_thought_json(jf)
        if data:
            entries.append(data)

    logger.info(f"Loaded {len(entries)} thought log(s)")

    # Apply filter
    if args.filter:
        if args.filter == "cover":
            entries = [e for e in entries if e["illustration_id"] == "cover"]
        else:
            entries = [e for e in entries if e["illustration_id"].startswith(args.filter)]
        logger.info(f"Filtered to {len(entries)} entries (type={args.filter})")

    if not entries:
        logger.warning("No entries after filtering. Nothing to convert.")
        sys.exit(0)

    # Load visual cache if requested
    visual_cache = None
    if args.with_cache:
        cache_path = volume_dir / "visual_cache.json"
        if cache_path.exists():
            with open(cache_path, 'r', encoding='utf-8') as f:
                visual_cache = json.load(f)
            logger.info(f"Loaded visual_cache.json ({len(visual_cache)} entries)")
        else:
            logger.warning("visual_cache.json not found, --with-cache ignored")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = volume_dir / "THINKING"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract volume name from directory
    vol_name = volume_dir.name.rsplit("_", 2)[0]  # strip date + id suffix

    # Generate output
    if args.split:
        # One file per illustration
        written = 0
        for entry in entries:
            illust_id = entry["illustration_id"]
            cache_entry = None
            if visual_cache:
                cache_entry = load_visual_cache_entry(visual_cache, illust_id)

            # Build per-illustration markdown
            md_lines = []
            md_lines.append("# Visual Analysis Reasoning Process")
            md_lines.append("")
            md_lines.append(f"**Volume**: {vol_name}")
            md_lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            md_lines.append(f"**Model**: {entry.get('model', 'gemini-3-pro-preview')}")
            md_lines.append(f"**Phase**: 1.6 (Multimodal Processor)")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
            md_lines.append(render_thought_entry(entry, cache_entry, args.with_cache))
            md_lines.append("---")
            md_lines.append("")
            md_lines.append(
                "*This visual thinking process is automatically generated by "
                "Gemini 3 Pro during Phase 1.6 (Multimodal Processor) and "
                "provides insight into the visual analysis decision-making process.*"
            )

            out_file = output_dir / f"visual_{illust_id}_THINKING.md"
            out_file.write_text("\n".join(md_lines), encoding="utf-8")
            written += 1
            logger.info(f"  ✓ {out_file.name}")

        logger.info(f"\n✅ Generated {written} visual thinking file(s) in {output_dir}")

    else:
        # Consolidated file
        markdown = render_consolidated_markdown(
            entries, vol_name, visual_cache, args.with_cache
        )
        out_file = output_dir / "VISUAL_THINKING.md"
        out_file.write_text(markdown, encoding="utf-8")
        logger.info(f"\n✅ Generated: {out_file}")
        logger.info(f"   {len(entries)} illustrations, "
                     f"{sum(e.get('processing_time_seconds', 0) for e in entries):.1f}s total")


if __name__ == "__main__":
    main()
