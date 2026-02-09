"""
Translation flow menu components.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..components.styles import custom_style
from ..components.confirmations import confirm_context_caching, confirm_continuity_pack
from ..utils.config_bridge import ConfigBridge

console = Console()


def start_translation_flow(
    config: ConfigBridge,
    input_dir: Path,
    work_dir: Path,
) -> Optional[Dict[str, Any]]:
    """
    Interactive flow for starting a new translation.

    Args:
        config: Configuration bridge instance
        input_dir: Path to INPUT directory
        work_dir: Path to WORK directory

    Returns:
        Dictionary with translation options, or None if cancelled
    """
    console.print()
    console.print(Panel(
        "[bold]Start New Translation[/bold]\n"
        "[dim]Select an EPUB file and configure options[/dim]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()

    # Step 1: Select EPUB file
    epub_files = list(input_dir.glob("*.epub"))

    if not epub_files:
        console.print("[red]No EPUB files found in INPUT directory[/red]")
        console.print(f"[dim]Place your Japanese EPUB files in: {input_dir}[/dim]")
        return None

    epub_choices = [
        questionary.Choice(f.name, value=str(f)) for f in sorted(epub_files)
    ]
    epub_choices.append(questionary.Separator())
    epub_choices.append(questionary.Choice("Back to Main Menu", value="back"))

    selected_epub = questionary.select(
        "Select EPUB file:",
        choices=epub_choices,
        style=custom_style,
    ).ask()

    if selected_epub == "back" or selected_epub is None:
        return None

    epub_path = Path(selected_epub)

    # Step 2: Generate or customize volume ID
    timestamp = datetime.now().strftime("%Y%m%d")
    auto_id = f"{epub_path.stem}_{timestamp}_{hash(str(epub_path)) % 10000:04x}"

    console.print(f"\n[dim]Auto-generated ID: {auto_id}[/dim]")

    use_auto_id = questionary.confirm(
        "Use auto-generated volume ID?",
        default=True,
        style=custom_style,
    ).ask()

    if use_auto_id:
        volume_id = auto_id
    else:
        volume_id = questionary.text(
            "Enter custom volume ID:",
            default=epub_path.stem,
            validate=lambda x: len(x) > 0 and " " not in x,
            style=custom_style,
        ).ask()

        if volume_id is None:
            return None

    # Step 3: Translation options
    console.print("\n[bold]Translation Options:[/bold]")

    # Language display
    lang = config.target_language
    lang_config = config.get_language_config(lang)
    lang_name = lang_config.get('language_name', lang.upper())
    console.print(f"  Language: [cyan]{lang_name}[/cyan]")
    console.print(f"  Model: [cyan]{config.model}[/cyan]")
    console.print()

    # Feature toggles
    features = questionary.checkbox(
        "Enable features:",
        choices=[
            questionary.Choice(
                "Context Caching (Recommended)",
                value="caching",
                checked=config.caching_enabled,
            ),
            questionary.Choice(
                "Auto-inherit Sequels",
                value="inherit",
                checked=True,
            ),
            questionary.Choice(
                "Force Re-translate (Overwrite)",
                value="force",
                checked=False,
            ),
            questionary.Choice(
                "Build EPUB After Translation",
                value="auto_build",
                checked=True,
            ),
        ],
        style=custom_style,
    ).ask()

    if features is None:
        return None

    # Step 4: Context caching confirmation
    if "caching" in features and config.caching_enabled:
        # Estimate instruction size (placeholder)
        estimated_size = 400 * 1024  # ~400KB typical
        confirm_context_caching(
            model=config.model,
            instruction_size=estimated_size,
            ttl=config.cache_ttl,
            auto_confirm=True,
        )

    # Step 5: Confirm and return
    console.print()
    console.print(Panel(
        f"[bold]Ready to translate:[/bold]\n\n"
        f"  EPUB: [cyan]{epub_path.name}[/cyan]\n"
        f"  Volume ID: [cyan]{volume_id}[/cyan]\n"
        f"  Language: [cyan]{lang_name}[/cyan]\n"
        f"  Model: [cyan]{config.model}[/cyan]\n"
        f"  Caching: [cyan]{'Yes' if 'caching' in features else 'No'}[/cyan]\n"
        f"  Auto-build: [cyan]{'Yes' if 'auto_build' in features else 'No'}[/cyan]",
        border_style="green",
        padding=(1, 2),
    ))

    if questionary.confirm("Start translation?", default=True, style=custom_style).ask():
        return {
            'epub_path': epub_path,
            'volume_id': volume_id,
            'caching': 'caching' in features,
            'auto_inherit': 'inherit' in features,
            'force': 'force' in features,
            'auto_build': 'auto_build' in features,
        }

    return None


def resume_volume_flow(
    config: ConfigBridge,
    work_dir: Path,
) -> Optional[Dict[str, Any]]:
    """
    Interactive flow for resuming an existing volume.

    Args:
        config: Configuration bridge instance
        work_dir: Path to WORK directory

    Returns:
        Dictionary with resume options, or None if cancelled
    """
    console.print()
    console.print(Panel(
        "[bold]Resume Volume[/bold]\n"
        "[dim]Select a volume to continue working on[/dim]",
        border_style="yellow",
        padding=(1, 2),
    ))
    console.print()

    # Get list of volumes
    volumes = _get_volume_list(work_dir)

    if not volumes:
        console.print("[red]No volumes found in WORK directory[/red]")
        console.print(f"[dim]Start a new translation first.[/dim]")
        return None

    # Build volume choices with status
    vol_choices = []
    for vol in volumes:
        status = vol.get('status', 'unknown')
        status_icon = {
            'completed': '[green]✓[/green]',
            'in_progress': '[yellow]...[/yellow]',
            'pending': '[dim]○[/dim]',
        }.get(status, '[dim]?[/dim]')

        title = vol.get('title', vol['id'])[:40]
        label = f"{status_icon} {vol['id']} - {title}"
        vol_choices.append(questionary.Choice(label, value=vol['id']))

    vol_choices.append(questionary.Separator())
    vol_choices.append(questionary.Choice("Back to Main Menu", value="back"))

    selected_volume = questionary.select(
        "Select volume to resume:",
        choices=vol_choices,
        style=custom_style,
    ).ask()

    if selected_volume == "back" or selected_volume is None:
        return None

    # Show volume details
    vol_info = next((v for v in volumes if v['id'] == selected_volume), {})
    _show_volume_details(vol_info)

    # Select action
    action = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("Continue Translation (Phase 2)", value="translate"),
            questionary.Choice("Run Phase 1.55 (Rich Metadata Cache)", value="phase1.55"),
            questionary.Choice("Run Phase 1.6 (Multimodal Processor)", value="phase1.6"),
            questionary.Choice("Build EPUB (Phase 4)", value="build"),
            questionary.Choice("Run Full Pipeline", value="run"),
            questionary.Choice("View Detailed Status", value="status"),
            questionary.Separator(),
            questionary.Choice("Back", value="back"),
        ],
        style=custom_style,
    ).ask()

    if action == "back" or action is None:
        return None

    return {
        'volume_id': selected_volume,
        'action': action,
    }


def select_chapters_flow(
    work_dir: Path,
    volume_id: str,
) -> Optional[List[str]]:
    """
    Interactive flow for selecting specific chapters to translate.

    Args:
        work_dir: Path to WORK directory
        volume_id: Volume identifier

    Returns:
        List of selected chapter IDs, or None if cancelled
    """
    import json

    manifest_path = work_dir / volume_id / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]Volume not found: {volume_id}[/red]")
        return None

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    chapters = manifest.get('chapters', [])
    if not chapters:
        console.print("[red]No chapters found in volume[/red]")
        return None

    # Build chapter choices
    chapter_choices = []
    for ch in chapters:
        status = ch.get('translation_status', 'pending')
        status_icon = {
            'completed': '[green]✓[/green]',
            'in_progress': '[yellow]...[/yellow]',
            'pending': '[dim]○[/dim]',
            'failed': '[red]✗[/red]',
        }.get(status, '[dim]?[/dim]')

        filename = ch.get('filename', 'unknown')
        title = ch.get('title', '')[:30] or filename
        label = f"{status_icon} {filename}: {title}"

        chapter_choices.append(questionary.Choice(
            label,
            value=filename,
            checked=(status != 'completed'),
        ))

    console.print("\n[bold]Select chapters to translate:[/bold]")
    console.print("[dim]Space to toggle, Enter to confirm[/dim]\n")

    selected = questionary.checkbox(
        "Chapters:",
        choices=chapter_choices,
        style=custom_style,
    ).ask()

    return selected if selected else None


def _get_volume_list(work_dir: Path) -> List[Dict[str, Any]]:
    """Get list of volumes with basic info."""
    import json

    volumes = []
    for vol_dir in work_dir.iterdir():
        if not vol_dir.is_dir():
            continue

        manifest_path = vol_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            # Determine overall status
            pipeline_state = manifest.get('pipeline_state', {})
            translator_status = pipeline_state.get('translator', {}).get('status', 'pending')

            volumes.append({
                'id': vol_dir.name,
                'title': manifest.get('metadata_en', {}).get('title_en') or
                        manifest.get('metadata', {}).get('title', 'Unknown'),
                'status': translator_status,
                'chapters': len(manifest.get('chapters', [])),
            })
        except Exception:
            continue

    return sorted(volumes, key=lambda x: x['id'], reverse=True)


def _show_volume_details(vol_info: Dict[str, Any]) -> None:
    """Display volume details in a table."""
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Volume ID", vol_info.get('id', 'N/A'))
    table.add_row("Title", vol_info.get('title', 'N/A'))
    table.add_row("Status", vol_info.get('status', 'N/A'))
    table.add_row("Chapters", str(vol_info.get('chapters', 0)))

    console.print()
    console.print(table)
    console.print()
