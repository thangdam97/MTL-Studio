"""Low-risk extracted CLI command handlers."""

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandResult:
    """Normalized return payload for CLI command execution."""

    exit_code: int = 0


def handle_status(args: Any, controller: Any) -> CommandResult:
    controller.show_status(args.volume_id)
    return CommandResult(exit_code=0)


def handle_list(args: Any, controller: Any) -> CommandResult:
    controller.list_volumes()
    return CommandResult(exit_code=0)


def handle_config(args: Any, controller: Any) -> CommandResult:
    controller.handle_config(
        toggle_pre_toc=args.toggle_pre_toc,
        show=args.show,
        model=args.model if hasattr(args, 'model') else None,
        temperature=args.temperature if hasattr(args, 'temperature') else None,
        top_p=args.top_p if hasattr(args, 'top_p') else None,
        top_k=args.top_k if hasattr(args, 'top_k') else None,
        backend=args.backend if hasattr(args, 'backend') else None,
        language=args.language if hasattr(args, 'language') else None,
        show_language=args.show_language if hasattr(args, 'show_language') else False,
        toggle_multimodal=args.toggle_multimodal if hasattr(args, 'toggle_multimodal') else False,
        toggle_smart_chunking=args.toggle_smart_chunking if hasattr(args, 'toggle_smart_chunking') else False
    )
    return CommandResult(exit_code=0)


def handle_metadata(args: Any, controller: Any) -> CommandResult:
    validate = getattr(args, 'validate', False)
    is_compatible = controller.inspect_metadata(args.volume_id, validate=validate)
    return CommandResult(exit_code=0 if is_compatible else 1)


HANDLERS = {
    'status': handle_status,
    'list': handle_list,
    'config': handle_config,
    'metadata': handle_metadata,
}
