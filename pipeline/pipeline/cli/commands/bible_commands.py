"""Bible CLI command handlers for MTL Studio.

Commands:
    mtl bible list                  — Show all registered series bibles
    mtl bible show <bible_id>       — Display categorized bible contents
    mtl bible validate <bible_id>   — Check bible for issues
    mtl bible import <volume_id>    — Import terms from volume manifest → bible
    mtl bible link <volume_id>      — Link volume to its bible (auto-detect or specify)
    mtl bible unlink <volume_id>    — Unlink volume from bible
    mtl bible orphans               — Find WORK/ volumes not linked to any bible
    mtl bible prompt <bible_id>     — Preview the prompt block that gets injected
    mtl bible sync <volume_id>      — Run bible ↔ manifest sync (pull + push)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from pipeline.cli.commands.basic_commands import CommandResult

logger = logging.getLogger(__name__)

# Lazy import to avoid circular deps at module level
_ctrl = None

def _get_controller():
    """Lazy-init BibleController singleton."""
    global _ctrl
    if _ctrl is None:
        from pipeline.config import PIPELINE_ROOT
        from pipeline.translator.series_bible import BibleController
        _ctrl = BibleController(PIPELINE_ROOT)
    return _ctrl


def _get_work_dir():
    from pipeline.config import PIPELINE_ROOT
    return PIPELINE_ROOT / "WORK"


def handle_bible(args: Any, controller: Any) -> CommandResult:
    """Route bible subcommands."""
    action = getattr(args, 'bible_action', None)
    if not action:
        logger.info("Usage: mtl bible <list|show|validate|import|link|unlink|orphans|prompt|sync>")
        return CommandResult(exit_code=1)

    dispatch = {
        'list': _bible_list,
        'show': _bible_show,
        'validate': _bible_validate,
        'import': _bible_import,
        'link': _bible_link,
        'unlink': _bible_unlink,
        'orphans': _bible_orphans,
        'prompt': _bible_prompt,
        'sync': _bible_sync,
    }

    handler = dispatch.get(action)
    if not handler:
        logger.error(f"Unknown bible action: {action}")
        return CommandResult(exit_code=1)

    return handler(args, controller)


def _bible_list(args: Any, controller: Any) -> CommandResult:
    """List all registered series bibles."""
    ctrl = _get_controller()
    bibles = ctrl.list_bibles()

    if not bibles:
        logger.info("No bibles registered yet.")
        logger.info("  Create one with: mtl bible import <volume_id>")
        return CommandResult(exit_code=0)

    controller._ui_header("Series Bibles", f"{len(bibles)} registered")

    for b in bibles:
        if 'error' in b:
            logger.info(f"\n  ❌ {b['series_id']}: {b['error']}")
            continue

        sid = b['series_id']
        total = b['total_entries']
        vols = b['volumes']
        ws = b.get('world_setting', 'not set')

        logger.info(f"\n  📖 {sid}")
        logger.info(f"     Entries: {total} | Volumes: {vols} | World: {ws}")

        geo = b.get('geography', {})
        logger.info(f"     Characters: {b['characters']} | "
                     f"Geography: {sum(geo.values())} | "
                     f"Weapons: {b['weapons_artifacts']} | "
                     f"Cultural: {b['cultural_terms']} | "
                     f"Mythology: {b['mythology']}")

    # Global stats
    stats = ctrl.stats()
    logger.info(f"\n  Total: {stats['series_count']} series, "
                 f"{stats['total_entries']} entries, "
                 f"{stats['total_volumes']} volumes linked")

    return CommandResult(exit_code=0)


def _bible_show(args: Any, controller: Any) -> CommandResult:
    """Display categorized bible contents."""
    bible_id = getattr(args, 'bible_id', None)
    if not bible_id:
        logger.error("Usage: mtl bible show <bible_id>")
        return CommandResult(exit_code=1)

    ctrl = _get_controller()
    bible = ctrl.get_bible(bible_id)
    if not bible:
        logger.error(f"Bible not found: {bible_id}")
        logger.info("  Use 'mtl bible list' to see available bibles")
        return CommandResult(exit_code=1)

    controller._ui_header(
        f"Bible: {bible.series_title.get('en', bible_id)}",
        f"{bible.entry_count()} entries | {len(bible.volumes_registered)} volumes"
    )

    # World setting
    ws = bible.world_setting
    if ws:
        logger.info(f"\n  World: {ws.get('label', ws.get('type', '?'))}")
        hon = ws.get('honorifics', {})
        if hon:
            logger.info(f"    Honorifics: {hon.get('mode', '?')} — {hon.get('policy', '')[:80]}")
        no = ws.get('name_order', {})
        if no:
            logger.info(f"    Name Order: {no.get('default', '?')}")
        exceptions = ws.get('exceptions', [])
        if exceptions:
            logger.info(f"    Exceptions: {len(exceptions)}")
            for exc in exceptions:
                logger.info(f"      • {exc.get('character_en', '?')}: {exc.get('reason', '')}")

    # Volumes
    vols = bible.volumes_registered
    if vols:
        logger.info(f"\n  Volumes ({len(vols)}):")
        for v in vols:
            logger.info(f"    [{v.get('index', '?')}] {v.get('volume_id', '?')} — {v.get('title', '?')}")

    # Characters (top 15)
    chars = bible.data.get('characters', {})
    if chars:
        logger.info(f"\n  Characters ({len(chars)}):")
        for i, (jp, data) in enumerate(chars.items()):
            if i >= 15:
                logger.info(f"    ... and {len(chars) - 15} more")
                break
            if isinstance(data, dict):
                en = data.get('canonical_en', '?')
                short = data.get('short_name', '')
                suffix = f" ({short})" if short and short != en else ""
                cat = data.get('category', '')
                cat_tag = f" [{cat}]" if cat else ""
                logger.info(f"    {jp} = {en}{suffix}{cat_tag}")

    # Geography
    geo = bible.data.get('geography', {})
    for sub_name, sub_label in [('countries', 'Countries'), ('regions', 'Regions'), ('cities', 'Cities')]:
        items = geo.get(sub_name, {})
        if items:
            entries = [f"{jp}={d.get('canonical_en','?')}" for jp, d in items.items() if isinstance(d, dict)]
            logger.info(f"\n  {sub_label} ({len(items)}): {' | '.join(entries[:10])}")
            if len(entries) > 10:
                logger.info(f"    ... and {len(entries) - 10} more")

    # Weapons
    weapons = bible.data.get('weapons_artifacts', {})
    if weapons:
        total_w = sum(len(items) for items in weapons.values() if isinstance(items, dict))
        logger.info(f"\n  Weapons/Artifacts ({total_w}):")
        for sub_cat, items in weapons.items():
            if isinstance(items, dict):
                for jp, data in items.items():
                    if isinstance(data, dict):
                        en = data.get('canonical_en', '?')
                        extra = ""
                        if data.get('wielder'):
                            extra = f" → {data['wielder']}"
                        logger.info(f"    {jp} = {en}{extra}")

    # Organizations, Cultural, Mythology (compact)
    for section, label in [('organizations', 'Organizations'), ('cultural_terms', 'Cultural Terms'), ('mythology', 'Mythology')]:
        items = bible.data.get(section, {})
        if items:
            entries = [f"{jp}={d.get('canonical_en','?')}" for jp, d in items.items() if isinstance(d, dict)]
            logger.info(f"\n  {label} ({len(items)}): {' | '.join(entries)}")

    return CommandResult(exit_code=0)


def _bible_validate(args: Any, controller: Any) -> CommandResult:
    """Validate a bible for issues."""
    bible_id = getattr(args, 'bible_id', None)
    if not bible_id:
        logger.error("Usage: mtl bible validate <bible_id>")
        return CommandResult(exit_code=1)

    ctrl = _get_controller()
    result = ctrl.validate_bible(bible_id)

    if 'error' in result:
        logger.error(result['error'])
        return CommandResult(exit_code=1)

    controller._ui_header(f"Validate: {bible_id}", f"{result['entries']} entries")

    if result['valid']:
        logger.info("\n  ✅ Bible is valid — no issues found")
    else:
        logger.info(f"\n  ❌ {len(result['issues'])} issues found:")
        for issue in result['issues']:
            logger.info(f"    • {issue}")

    if result.get('warnings'):
        logger.info(f"\n  ⚠️  {len(result['warnings'])} warnings:")
        for warn in result['warnings']:
            logger.info(f"    • {warn}")

    return CommandResult(exit_code=0 if result['valid'] else 1)


def _bible_import(args: Any, controller: Any) -> CommandResult:
    """Import terms from a volume manifest into its bible."""
    volume_id = getattr(args, 'volume_id', None)
    if not volume_id:
        logger.error("Usage: mtl bible import <volume_id>")
        return CommandResult(exit_code=1)

    # Resolve volume directory
    work_dir = _get_work_dir()
    vol_dir = _resolve_volume_dir(volume_id, work_dir)
    if not vol_dir:
        return CommandResult(exit_code=1)

    # Load manifest
    manifest_path = vol_dir / "manifest.json"
    if not manifest_path.exists():
        logger.error(f"No manifest.json in {vol_dir.name}")
        return CommandResult(exit_code=1)

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    # Determine bible_id
    ctrl = _get_controller()
    bible_id = manifest.get('bible_id')
    if not bible_id:
        # Try auto-detect
        detected = ctrl.detect_series(manifest)
        if detected:
            bible_id = detected
            logger.info(f"Auto-detected series: {bible_id}")
        else:
            logger.error("No bible_id in manifest and couldn't auto-detect series.")
            logger.info("  Set bible_id in manifest first, or use: mtl bible link <volume_id>")
            return CommandResult(exit_code=1)

    bible = ctrl.get_bible(bible_id)
    if not bible:
        logger.error(f"Bible not found: {bible_id}")
        logger.info("  Available bibles: mtl bible list")
        return CommandResult(exit_code=1)

    controller._ui_header(f"Import → {bible_id}", f"From: {vol_dir.name}")

    summary = ctrl.import_from_manifest(manifest, bible_id)

    logger.info("\n  Import complete:")
    for cat, count in summary.items():
        logger.info(f"    {cat}: {count} entries added/enriched")
    logger.info(f"\n  Bible now has {bible.entry_count()} total entries")

    return CommandResult(exit_code=0)


def _bible_link(args: Any, controller: Any) -> CommandResult:
    """Link a volume to a bible."""
    volume_id = getattr(args, 'volume_id', None)
    if not volume_id:
        logger.error("Usage: mtl bible link <volume_id>")
        return CommandResult(exit_code=1)

    # Resolve volume directory
    work_dir = _get_work_dir()
    vol_dir = _resolve_volume_dir(volume_id, work_dir)
    if not vol_dir:
        return CommandResult(exit_code=1)

    manifest_path = vol_dir / "manifest.json"
    if not manifest_path.exists():
        logger.error(f"No manifest.json in {vol_dir.name}")
        return CommandResult(exit_code=1)

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    ctrl = _get_controller()

    # Check if explicit bible_id specified via --bible flag
    target_bible = getattr(args, 'bible_id', None)

    if not target_bible:
        # Auto-detect
        target_bible = ctrl.detect_series(manifest)
        if not target_bible:
            logger.error("Couldn't auto-detect series for this volume.")
            logger.info("  Specify explicitly: mtl bible link <volume_id> --bible <bible_id>")
            logger.info("  Available bibles: mtl bible list")
            return CommandResult(exit_code=1)
        logger.info(f"Auto-detected series: {target_bible}")

    # Link in index
    full_vid = manifest.get('volume_id', volume_id)
    ctrl.link_volume(full_vid, target_bible)

    # Also set bible_id in manifest if not already present
    if 'bible_id' not in manifest or manifest['bible_id'] != target_bible:
        manifest['bible_id'] = target_bible
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Set bible_id='{target_bible}' in manifest")

    logger.info(f"✅ Volume {volume_id} linked to bible '{target_bible}'")
    return CommandResult(exit_code=0)


def _bible_unlink(args: Any, controller: Any) -> CommandResult:
    """Unlink a volume from its bible."""
    volume_id = getattr(args, 'volume_id', None)
    if not volume_id:
        logger.error("Usage: mtl bible unlink <volume_id>")
        return CommandResult(exit_code=1)

    work_dir = _get_work_dir()
    vol_dir = _resolve_volume_dir(volume_id, work_dir)
    if not vol_dir:
        return CommandResult(exit_code=1)

    ctrl = _get_controller()

    # Build a full volume_id-like string for unlink resolution
    manifest_path = vol_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        full_vid = manifest.get('volume_id', volume_id)

        # Remove bible_id from manifest
        if 'bible_id' in manifest:
            old_id = manifest.pop('bible_id')
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            logger.info(f"Removed bible_id='{old_id}' from manifest")
    else:
        full_vid = volume_id

    sid = ctrl.unlink_volume(full_vid)
    if sid:
        logger.info(f"✅ Volume {volume_id} unlinked from '{sid}'")
    else:
        logger.info(f"Volume {volume_id} was not linked to any bible")

    return CommandResult(exit_code=0)


def _bible_orphans(args: Any, controller: Any) -> CommandResult:
    """Find WORK/ volumes not linked to any bible."""
    ctrl = _get_controller()
    work_dir = _get_work_dir()

    orphans = ctrl.find_orphan_volumes(work_dir)

    controller._ui_header("Orphan Volumes", "Volumes in WORK/ not linked to any bible")

    if not orphans:
        logger.info("\n  No orphan volumes found — all volumes are linked or no bibles exist.")
    else:
        logger.info(f"\n  {len(orphans)} orphan volumes:")
        for name in orphans:
            logger.info(f"    • {name}")
        logger.info(f"\n  Link with: mtl bible link <volume_id>")

    return CommandResult(exit_code=0)


def _bible_prompt(args: Any, controller: Any) -> CommandResult:
    """Preview the prompt block that gets injected into system instruction."""
    bible_id = getattr(args, 'bible_id', None)
    if not bible_id:
        logger.error("Usage: mtl bible prompt <bible_id>")
        return CommandResult(exit_code=1)

    ctrl = _get_controller()
    bible = ctrl.get_bible(bible_id)
    if not bible:
        logger.error(f"Bible not found: {bible_id}")
        return CommandResult(exit_code=1)

    prompt = bible.format_for_prompt()
    directive = bible.format_world_setting_directive()

    controller._ui_header(f"Prompt Preview: {bible_id}", f"{len(prompt)} chars")

    logger.info(f"\n  Short Directive: {directive}")
    logger.info(f"\n  Full Prompt Block:")
    logger.info("  " + "-" * 60)
    for line in prompt.split('\n'):
        logger.info(f"  {line}")
    logger.info("  " + "-" * 60)

    return CommandResult(exit_code=0)


def _bible_sync(args: Any, controller: Any) -> CommandResult:
    """Run bible ↔ manifest sync for a volume.

    Performs a two-way sync:
      PULL: Inherit canonical bible terms → manifest character_names
      PUSH: Export newly discovered manifest terms → bible
    """
    volume_id = getattr(args, 'volume_id', None)
    if not volume_id:
        logger.error("Usage: mtl bible sync <volume_id> [--direction pull|push|both]")
        return CommandResult(exit_code=1)

    work_dir = _get_work_dir()
    volume_dir = _resolve_volume_dir(volume_id, work_dir)
    if not volume_dir:
        return CommandResult(exit_code=1)

    direction = getattr(args, 'direction', 'both') or 'both'

    controller._ui_header("Bible Sync", f"{volume_dir.name} → direction={direction}")

    try:
        from pipeline.metadata_processor.bible_sync import BibleSyncAgent
        from pipeline.config import PIPELINE_ROOT

        result = BibleSyncAgent.manual_sync(volume_dir, PIPELINE_ROOT, direction)
    except FileNotFoundError as e:
        logger.error(str(e))
        return CommandResult(exit_code=1)
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return CommandResult(exit_code=1)

    if 'error' in result:
        logger.error(f"  {result['error']}")
        logger.info("  Ensure the volume has a bible_id in its manifest,")
        logger.info("  or link it with: mtl bible link <volume_id>")
        return CommandResult(exit_code=1)

    logger.info(f"\n  Series: {result['series_id']}")
    logger.info(f"  Volume: {result['volume_id']}")

    if 'pull' in result:
        p = result['pull']
        logger.info(f"\n  📥 PULL (Bible → Manifest):")
        logger.info(f"     Characters inherited: {p['characters_inherited']}")
        logger.info(f"     Geography inherited:  {p['geography_inherited']}")
        logger.info(f"     Weapons inherited:    {p['weapons_inherited']}")
        logger.info(f"     Other inherited:      {p['other_inherited']}")
        logger.info(f"     Total: {p['total_inherited']}")
        if p.get('manifest_updated'):
            logger.info(f"     ✅ manifest.json updated with bible terms")

    if 'push' in result:
        p = result['push']
        logger.info(f"\n  📤 PUSH (Manifest → Bible):")
        logger.info(f"     Characters added:    {p['characters_added']}")
        logger.info(f"     Characters enriched: {p['characters_enriched']}")
        logger.info(f"     Characters skipped:  {p['characters_skipped']}")
        logger.info(f"     Volume registered:   {'✅' if p['volume_registered'] else '—'}")
        if p['conflicts']:
            logger.warning(f"     ⚠️  {len(p['conflicts'])} conflicts (bible kept):")
            for c in p['conflicts']:
                logger.warning(f"       {c}")
        logger.info(f"     Total changes: {p['total_changes']}")

    return CommandResult(exit_code=0)


# ── Helpers ──────────────────────────────────────────────────────

def _resolve_volume_dir(volume_id: str, work_dir: Path) -> Path | None:
    """Resolve a short volume ID (e.g. '25d9') to its full WORK/ directory."""
    # Direct match
    for d in work_dir.iterdir():
        if d.is_dir() and d.name.endswith(f"_{volume_id}"):
            return d

    # Substring match
    matches = [d for d in work_dir.iterdir() if d.is_dir() and volume_id in d.name]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        logger.error(f"Ambiguous volume ID '{volume_id}'. Matches:")
        for m in matches:
            logger.error(f"  • {m.name}")
        return None

    logger.error(f"Volume not found: {volume_id}")
    return None
