"""CLI dispatch helpers for extracted command handling."""

from typing import Any, Optional

from pipeline.cli.commands.basic_commands import HANDLERS
from pipeline.cli.commands.bible_commands import handle_bible

# Register bible command handler
HANDLERS['bible'] = handle_bible


PHASE_NAMES = {
    'phase0': 'Phase 0 - Deprecated Alias (use phase1.6)',
    'phase1.5': 'Phase 1.5 - Schema Autoupdate + Metadata Translation',
    'phase1.6': 'Phase 1.6 - Multimodal Processor (Visual Analysis)',
    'multimodal': 'Multimodal Translator (Phase 1.6 + Phase 2 with Visual Context)',
    'phase2': 'Phase 2 - Translator',
    'phase3': 'Phase 3 - Critics',
    'phase4': 'Phase 4 - Builder',
    'cache-inspect': 'Visual Cache Inspector (Multimodal)',
    'metadata': 'Metadata Schema Inspection',
    'schema': 'Schema Manipulator',
    'heal': 'Self-Healing Anti-AI-ism Agent (3-Layer Detection + LLM Correction)',
    'visual-thinking': 'Visual Thinking Log Converter (JSON → Markdown)'
}


def resolve_volume_id_for_args(args: Any, controller: Any, logger: Any) -> None:
    """
    Resolve interactive/partial volume IDs in-place.

    Preserves existing mtl.py behavior and exits via SystemExit if required
    resolution fails (same as previous inline logic).
    """
    if not hasattr(args, 'volume_id'):
        return

    if args.command in PHASE_NAMES:
        phase_name = PHASE_NAMES[args.command]
        if args.volume_id:
            resolved = controller.resolve_volume_id(args.volume_id, allow_interactive=True, phase_name=phase_name)
        else:
            resolved = controller.interactive_volume_selection(phase_name=phase_name)

        if not resolved:
            logger.error("No volume selected. Exiting.")
            raise SystemExit(1)

        args.volume_id = resolved
        return

    if args.volume_id:
        resolved = controller.resolve_volume_id(args.volume_id, allow_interactive=False)
        if resolved:
            args.volume_id = resolved


def dispatch_extracted_command(args: Any, controller: Any) -> Optional[int]:
    """
    Execute extracted command handlers.

    Returns:
      - exit code if command is handled here
      - None if command should fall through to legacy dispatch
    """
    handler = HANDLERS.get(args.command)
    if handler is None:
        return None

    result = handler(args, controller)
    return result.exit_code
