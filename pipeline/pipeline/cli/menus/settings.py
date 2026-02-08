"""
Settings panel component for the CLI TUI.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..components.styles import custom_style
from ..utils.config_bridge import ConfigBridge
from ..utils.cache_manager import purge_all_caches

console = Console()


def settings_panel(config: ConfigBridge) -> Optional[Dict[str, Any]]:
    """
    Display interactive settings panel.

    Args:
        config: Configuration bridge instance

    Returns:
        Dictionary of updated settings, or None if cancelled
    """
    console.print()
    console.print(Panel(
        "[bold]Settings[/bold]\n"
        "[dim]Use arrow keys to navigate, Space to toggle, Enter to confirm[/dim]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()

    while True:
        action = questionary.select(
            "Settings category:",
            choices=[
                questionary.Choice("Translation Settings", value="translation"),
                questionary.Choice("Model & Parameters", value="model"),
                questionary.Choice("Performance", value="performance"),
                questionary.Choice("Advanced", value="advanced"),
                questionary.Separator(),
                questionary.Choice("Clear All Caches", value="clear_cache"),
                questionary.Separator(),
                questionary.Choice("Save & Exit", value="save"),
                questionary.Choice("Discard Changes", value="cancel"),
            ],
            style=custom_style,
        ).ask()

        if action == "translation":
            _translation_settings(config)
        elif action == "model":
            _model_settings(config)
        elif action == "performance":
            _performance_settings(config)
        elif action == "advanced":
            _advanced_settings(config)
        elif action == "clear_cache":
            _clear_cache_menu(config)
        elif action == "save":
            config.save()
            console.print("[green]✓ Settings saved[/green]")
            return {"saved": True}
        elif action == "cancel" or action is None:
            return None


def _translation_settings(config: ConfigBridge) -> None:
    """Handle translation settings submenu."""
    console.print("\n[bold cyan]Translation Settings[/bold cyan]\n")

    # Language selection
    available_langs = config.get_available_languages()
    lang_choices = []

    for lang in available_langs:
        lang_config = config.get_language_config(lang)
        lang_name = lang_config.get('language_name', lang.upper())
        is_current = lang == config.target_language
        label = f"{lang_name} ({lang.upper()})"
        if is_current:
            label += " (Current)"
        lang_choices.append(questionary.Choice(label, value=lang))

    selected_lang = questionary.select(
        "Target Language:",
        choices=lang_choices,
        default=config.target_language,
        style=custom_style,
    ).ask()

    if selected_lang and selected_lang != config.target_language:
        config.target_language = selected_lang
        lang_config = config.get_language_config(selected_lang)
        console.print(f"[green]✓ Language changed to {lang_config.get('language_name', selected_lang)}[/green]")

    # Multimodal processor default switch
    toggle_multimodal = questionary.confirm(
        f"Enable Multimodal Processor by default? (currently {'ON' if config.multimodal_processor_enabled else 'OFF'})",
        default=config.multimodal_processor_enabled,
        style=custom_style,
    ).ask()

    if toggle_multimodal != config.multimodal_processor_enabled:
        config.multimodal_processor_enabled = bool(toggle_multimodal)
        status = "enabled" if toggle_multimodal else "disabled"
        console.print(f"[green]✓ Multimodal processor {status}[/green]")


def _model_settings(config: ConfigBridge) -> None:
    """Handle model and parameters settings submenu."""
    console.print("\n[bold cyan]Model & Parameters[/bold cyan]\n")

    # Model selection
    models = config.get_available_models()
    model_choices = []

    for m in models:
        is_current = m['value'] == config.model
        label = f"{m['label']} - {m['desc']}"
        if is_current:
            label += " (Current)"
        model_choices.append(questionary.Choice(label, value=m['value']))

    selected_model = questionary.select(
        "Translation Model:",
        choices=model_choices,
        default=config.model,
        style=custom_style,
    ).ask()

    if selected_model and selected_model != config.model:
        config.model = selected_model
        console.print(f"[green]✓ Model changed to {selected_model}[/green]")

    # Generation parameters
    console.print("\n[bold]Generation Parameters:[/bold]")

    # Temperature
    current_temp = config.temperature
    new_temp = questionary.text(
        f"Temperature (current: {current_temp}, range: 0.0-2.0):",
        default=str(current_temp),
        validate=lambda x: _validate_float(x, 0.0, 2.0),
        style=custom_style,
    ).ask()

    if new_temp:
        config.temperature = float(new_temp)

    # Top-P
    current_top_p = config.top_p
    new_top_p = questionary.text(
        f"Top-P (current: {current_top_p}, range: 0.0-1.0):",
        default=str(current_top_p),
        validate=lambda x: _validate_float(x, 0.0, 1.0),
        style=custom_style,
    ).ask()

    if new_top_p:
        config.top_p = float(new_top_p)

    # Top-K
    current_top_k = config.top_k
    new_top_k = questionary.text(
        f"Top-K (current: {current_top_k}, range: 1-100):",
        default=str(current_top_k),
        validate=lambda x: _validate_int(x, 1, 100),
        style=custom_style,
    ).ask()

    if new_top_k:
        config.top_k = int(new_top_k)


def _performance_settings(config: ConfigBridge) -> None:
    """Handle performance settings submenu."""
    console.print("\n[bold cyan]Performance Settings[/bold cyan]\n")

    # Build current options list
    options = [
        questionary.Choice(
            f"Context Caching {'[ON]' if config.caching_enabled else '[OFF]'}",
            value="caching",
            checked=config.caching_enabled,
        ),
    ]

    # Show current cache TTL
    if config.caching_enabled:
        console.print(f"  [dim]Cache TTL: {config.cache_ttl} minutes[/dim]")

    # Toggle caching
    toggle_caching = questionary.confirm(
        f"Enable Context Caching? (currently {'ON' if config.caching_enabled else 'OFF'})",
        default=config.caching_enabled,
        style=custom_style,
    ).ask()

    if toggle_caching != config.caching_enabled:
        config.caching_enabled = toggle_caching
        status = "enabled" if toggle_caching else "disabled"
        console.print(f"[green]✓ Context caching {status}[/green]")

    # Cache TTL (only if caching is enabled)
    if config.caching_enabled:
        current_ttl = config.cache_ttl
        new_ttl = questionary.text(
            f"Cache TTL in minutes (current: {current_ttl}):",
            default=str(current_ttl),
            validate=lambda x: _validate_int(x, 1, 120),
            style=custom_style,
        ).ask()

        if new_ttl:
            config.cache_ttl = int(new_ttl)

    # Smart Chunking toggle
    toggle_chunking = questionary.confirm(
        f"Enable Smart Chunking for massive chapters? (currently {'ON' if config.smart_chunking_enabled else 'OFF'})",
        default=config.smart_chunking_enabled,
        style=custom_style,
    ).ask()

    if toggle_chunking != config.smart_chunking_enabled:
        config.smart_chunking_enabled = bool(toggle_chunking)
        status = "enabled" if toggle_chunking else "disabled"
        console.print(f"[green]✓ Smart chunking {status}[/green]")


def _advanced_settings(config: ConfigBridge) -> None:
    """Handle advanced settings submenu."""
    console.print("\n[bold cyan]Advanced Settings[/bold cyan]\n")

    # Pre-TOC Detection
    toggle_pre_toc = questionary.confirm(
        f"Enable Pre-TOC Detection? (currently {'ON' if config.pre_toc_enabled else 'OFF'})",
        default=config.pre_toc_enabled,
        style=custom_style,
    ).ask()

    if toggle_pre_toc != config.pre_toc_enabled:
        config.pre_toc_enabled = toggle_pre_toc
        status = "enabled" if toggle_pre_toc else "disabled"
        console.print(f"[green]✓ Pre-TOC detection {status}[/green]")

    # Debug Mode
    toggle_debug = questionary.confirm(
        f"Enable Debug Mode? (currently {'ON' if config.debug_mode else 'OFF'})",
        default=config.debug_mode,
        style=custom_style,
    ).ask()

    if toggle_debug != config.debug_mode:
        config.debug_mode = toggle_debug
        status = "enabled" if toggle_debug else "disabled"
        console.print(f"[green]✓ Debug mode {status}[/green]")

    # Verbose Mode Default
    toggle_verbose = questionary.confirm(
        f"Default to Verbose Mode? (currently {'ON' if config.verbose_mode else 'OFF'})",
        default=config.verbose_mode,
        style=custom_style,
    ).ask()

    if toggle_verbose != config.verbose_mode:
        config.verbose_mode = toggle_verbose
        status = "enabled" if toggle_verbose else "disabled"
        console.print(f"[green]✓ Default verbose mode {status}[/green]")


def show_current_settings(config: ConfigBridge) -> None:
    """
    Display current settings in a formatted table.

    Args:
        config: Configuration bridge instance
    """
    # Language info
    lang = config.target_language
    lang_config = config.get_language_config(lang)
    lang_name = lang_config.get('language_name', lang.upper())

    # Create settings table
    table = Table(title="Current Settings", box=box.ROUNDED)
    table.add_column("Category", style="cyan", width=20)
    table.add_column("Setting", style="white", width=20)
    table.add_column("Value", style="green", width=25)

    # Translation
    table.add_row("Translation", "Target Language", f"{lang_name} ({lang.upper()})")
    table.add_row("", "Model", config.model)
    table.add_row("", "Multimodal Processor", "Enabled" if config.multimodal_processor_enabled else "Disabled")

    # Parameters
    table.add_row("Parameters", "Temperature", str(config.temperature))
    table.add_row("", "Top-P", str(config.top_p))
    table.add_row("", "Top-K", str(config.top_k))

    # Performance
    cache_status = "Enabled" if config.caching_enabled else "Disabled"
    table.add_row("Performance", "Context Caching", cache_status)
    if config.caching_enabled:
        table.add_row("", "Cache TTL", f"{config.cache_ttl} minutes")
    table.add_row("", "Smart Chunking", "Enabled" if config.smart_chunking_enabled else "Disabled")

    # Advanced
    pre_toc_status = "Enabled" if config.pre_toc_enabled else "Disabled"
    debug_status = "Enabled" if config.debug_mode else "Disabled"
    verbose_status = "Enabled" if config.verbose_mode else "Disabled"

    table.add_row("Advanced", "Pre-TOC Detection", pre_toc_status)
    table.add_row("", "Debug Mode", debug_status)
    table.add_row("", "Default Verbose", verbose_status)

    console.print()
    console.print(table)
    console.print()


def _validate_float(value: str, min_val: float, max_val: float) -> bool:
    """Validate float input within range."""
    try:
        f = float(value)
        return min_val <= f <= max_val
    except ValueError:
        return False


def _validate_int(value: str, min_val: int, max_val: int) -> bool:
    """Validate integer input within range."""
    try:
        i = int(value)
        return min_val <= i <= max_val
    except ValueError:
        return False


def _clear_cache_menu(config: ConfigBridge) -> None:
    """Handle cache clearing submenu."""
    console.print("\n[bold cyan]Cache Management[/bold cyan]\n")
    console.print("[dim]This will remove:[/dim]")
    console.print("  • Python bytecode cache (__pycache__, .pyc files)")
    console.print("  • Gemini API context caches")
    console.print("\n[yellow]Note: A fresh Python process is needed to reload updated modules.[/yellow]\n")

    confirm = questionary.confirm(
        "Proceed with cache purge?",
        default=False,
        style=custom_style,
    ).ask()

    if not confirm:
        console.print("[dim]Cache purge cancelled[/dim]")
        return

    console.print("\n[cyan]Purging caches...[/cyan]")

    # Get pipeline root (parent of config file)
    pipeline_root = Path(config.config_path).parent

    # Purge all caches
    results = purge_all_caches(pipeline_root)

    # Display results
    console.print("\n[bold green]✓ Cache Purge Complete[/bold green]\n")

    # Python cache results
    py_results = results["python"]
    py_total = py_results["total_items"]
    if py_total > 0:
        console.print(
            f"[green]Python Cache:[/green] Removed {py_results['cache_dirs_removed']} "
            f"directories and {py_results['pyc_files_removed']} bytecode files"
        )
    else:
        console.print("[dim]Python Cache:[/dim] No cache files found")

    # Gemini cache results
    gemini_results = results["gemini"]
    if gemini_results["success"]:
        cache_count = gemini_results["caches_removed"]
        if cache_count > 0:
            console.print(f"[green]Gemini API:[/green] Removed {cache_count} context cache(s)")
        else:
            console.print("[dim]Gemini API:[/dim] No active caches found")
    else:
        console.print(f"[yellow]Gemini API:[/yellow] {gemini_results['error']}")

    console.print("\n[bold cyan]→ Restart required for Python module changes to take effect[/bold cyan]\n")

    questionary.press_any_key_to_continue("Press any key to continue...").ask()
