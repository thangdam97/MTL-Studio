"""
MT Publishing Pipeline - Main TUI Application
Interactive terminal user interface for the translation pipeline.
"""

import sys
import os
import readline  # Enable delete key, arrow keys, and input history
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from rich.console import Console

from .menus.main_menu import (
    main_menu,
    show_header,
    phase_menu,
    post_translation_menu,
    confirm_exit,
)
from .menus.settings import settings_panel, show_current_settings
from .menus.translation import (
    start_librarian_flow,
    start_translation_flow,
    resume_volume_flow,
    select_chapters_flow,
)
from .menus.status import show_status_panel, list_volumes_panel
from .components.confirmations import confirm_continuity_pack, confirm_series_inheritance
from .components.progress import TranslationProgress
from .components.styles import custom_style
from .utils.config_bridge import ConfigBridge
from .utils.display import (
    console,
    print_header,
    print_success,
    print_error,
    print_warning,
)

# Setup logging
logger = logging.getLogger(__name__)


class MTLApp:
    """
    Main TUI Application for the MT Publishing Pipeline.

    Provides an interactive menu-driven interface with:
    - Arrow key navigation
    - Toggle switches for settings
    - Context caching confirmations
    - Continuity pack management
    - Progress display during translation
    """

    def __init__(self, work_dir: Optional[Path] = None, input_dir: Optional[Path] = None):
        """
        Initialize the TUI application.

        Args:
            work_dir: Path to WORK directory (default: auto-detect from project root)
            input_dir: Path to INPUT directory (default: auto-detect from project root)
        """
        # Determine project root (parent of pipeline module)
        self.project_root = Path(__file__).parent.parent.parent.resolve()

        self.work_dir = work_dir or self.project_root / "WORK"
        self.input_dir = input_dir or self.project_root / "INPUT"
        self.output_dir = self.project_root / "OUTPUT"

        # Ensure directories exist
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        self.config = ConfigBridge(self.project_root / "config.yaml")
        self.config.load()

        # State
        self.current_volume: Optional[str] = None
        self.running = False

    def run(self) -> int:
        """
        Main entry point - run the TUI application.

        Returns:
            Exit code (0 for success, non-zero for error)
        """
        self.running = True

        try:
            # Clear screen and show header
            self._clear_screen()
            show_header(self.config)

            # Main loop
            while self.running:
                action = main_menu()

                if action is None or action == "exit":
                    if confirm_exit():
                        self.running = False
                    else:
                        self._clear_screen()
                        show_header(self.config)
                        continue

                elif action == "new":
                    self._handle_new_translation()

                elif action == "phase1":
                    self._handle_phase1()

                elif action == "resume":
                    self._handle_resume_volume()

                elif action == "phase1.55":
                    self._handle_phase1_55()

                elif action == "settings":
                    self._handle_settings()

                elif action == "status":
                    self._handle_view_status()

                elif action == "list":
                    self._handle_list_volumes()

                # Refresh header after each action
                if self.running:
                    self._clear_screen()
                    show_header(self.config)

            console.print("\n[dim]Goodbye![/dim]\n")
            return 0

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted by user[/yellow]\n")
            return 130

        except Exception as e:
            print_error(f"Fatal error: {e}")
            logger.exception("Unhandled exception in TUI")
            return 1

    def _clear_screen(self) -> None:
        """Clear the terminal screen."""
        # Use ANSI escape codes (works on most terminals)
        console.print("\033[H\033[J", end="")

    def _handle_new_translation(self) -> None:
        """Handle starting a new translation."""
        result = start_translation_flow(
            config=self.config,
            input_dir=self.input_dir,
            work_dir=self.work_dir,
        )

        if result is None:
            return

        # Extract options
        epub_path = result['epub_path']
        volume_id = result['volume_id']
        auto_inherit = result.get('auto_inherit', True)
        force = result.get('force', False)
        auto_build = result.get('auto_build', True)

        self.current_volume = volume_id

        # Run the pipeline
        success = self._run_full_pipeline(
            epub_path=epub_path,
            volume_id=volume_id,
            auto_inherit=auto_inherit,
            force=force,
            auto_build=auto_build,
        )

        if success:
            print_success(f"Pipeline completed for {volume_id}")
        else:
            print_error(f"Pipeline failed for {volume_id}")

        input("\nPress Enter to continue...")

    def _handle_phase1(self) -> None:
        """Handle standalone Phase 1 (Librarian extraction)."""
        import questionary

        result = start_librarian_flow(input_dir=self.input_dir)
        if result is None:
            return

        epub_path = result['epub_path']
        volume_id = result['volume_id']
        self.current_volume = volume_id

        success = self._run_phase1(epub_path, volume_id)
        if not success:
            print_error(f"Phase 1 failed for {volume_id}")
            input("\nPress Enter to continue...")
            return

        print_success(f"Phase 1 completed for {volume_id}")

        next_action = questionary.select(
            "Phase 1 completed. Continue to metadata phases?",
            choices=[
                questionary.Choice(
                    "Continue with Phase 1.5 + Phase 1.55",
                    value="continue",
                ),
                questionary.Choice(
                    "Skip and return to Main Menu",
                    value="skip",
                ),
            ],
            style=custom_style,
        ).ask()

        if next_action == "continue":
            success_15 = self._run_phase1_5(volume_id)
            if not success_15:
                print_error(f"Phase 1.5 failed for {volume_id}")
                input("\nPress Enter to continue...")
                return

            success_155 = self._run_phase1_55(volume_id)
            if not success_155:
                print_error(f"Phase 1.55 failed for {volume_id}")
                input("\nPress Enter to continue...")
                return

            print_success(f"Phase 1.5 and Phase 1.55 completed for {volume_id}")

        input("\nPress Enter to continue...")

    def _handle_resume_volume(self) -> None:
        """Handle resuming an existing volume."""
        result = resume_volume_flow(
            config=self.config,
            work_dir=self.work_dir,
        )

        if result is None:
            return

        volume_id = result['volume_id']
        action = result['action']
        self.current_volume = volume_id

        if action == "translate":
            # Ask for specific chapters or all
            chapters = select_chapters_flow(self.work_dir, volume_id)
            success = self._run_phase2(volume_id, chapters=chapters)

        elif action == "build":
            success = self._run_phase4(volume_id)

        elif action == "phase1.55":
            success = self._run_phase1_55(volume_id)

        elif action == "phase1.6":
            success = self._run_phase1_6(volume_id)

        elif action == "run":
            success = self._run_phases_2_to_4(volume_id)

        elif action == "status":
            show_status_panel(self.work_dir, volume_id)
            input("\nPress Enter to continue...")
            return

        if action != "status":
            if success:
                print_success(f"Operation completed for {volume_id}")
            else:
                print_error(f"Operation failed for {volume_id}")
            input("\nPress Enter to continue...")

    def _handle_settings(self) -> None:
        """Handle settings panel."""
        # Show current settings first
        show_current_settings(self.config)

        # Open settings panel
        result = settings_panel(self.config)

        if result and result.get('saved'):
            # Reload config to ensure changes are reflected
            self.config.load()

    def _handle_view_status(self) -> None:
        """Handle viewing status."""
        if self.current_volume:
            # Show status for current volume
            show_status_panel(self.work_dir, self.current_volume)
        else:
            # Let user select a volume
            selected = list_volumes_panel(self.work_dir)
            if selected:
                show_status_panel(self.work_dir, selected)

        input("\nPress Enter to continue...")

    def _handle_list_volumes(self) -> None:
        """Handle listing volumes."""
        selected = list_volumes_panel(self.work_dir)

        if selected:
            show_status_panel(self.work_dir, selected)
            input("\nPress Enter to continue...")

    def _handle_phase1_55(self) -> None:
        """Handle running Phase 1.55 from main menu."""
        selected = list_volumes_panel(self.work_dir)
        if not selected:
            return

        success = self._run_phase1_55(selected)
        if success:
            print_success(f"Phase 1.55 completed for {selected}")
        else:
            print_error(f"Phase 1.55 failed for {selected}")
        input("\nPress Enter to continue...")

    # Pipeline execution methods

    def _run_full_pipeline(
        self,
        epub_path: Path,
        volume_id: str,
        auto_inherit: bool = True,
        force: bool = False,
        auto_build: bool = True,
    ) -> bool:
        """
        Run the complete pipeline.

        Args:
            epub_path: Path to EPUB file
            volume_id: Volume identifier
            auto_inherit: Whether to auto-inherit sequel metadata
            force: Whether to force re-translation
            auto_build: Whether to auto-build EPUB after translation

        Returns:
            True if successful
        """
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        # Phase 1: Librarian
        console.print("\n[bold cyan]Phase 1: Librarian[/bold cyan]")
        if not controller.run_phase1(epub_path, volume_id):
            return False

        # Phase 1.5: Metadata
        console.print("\n[bold cyan]Phase 1.5: Metadata[/bold cyan]")

        # Check for sequels
        if auto_inherit:
            sequel_info = self._check_for_sequel(volume_id)
            if sequel_info:
                if confirm_continuity_pack(sequel_info['title'], sequel_info['data']):
                    console.print("[green]✓ Inheriting from previous volume[/green]")
                else:
                    auto_inherit = False

        if not controller.run_phase1_5(volume_id):
            return False

        # Phase 1.55: Rich metadata cache enrichment
        console.print("\n[bold cyan]Phase 1.55: Rich Metadata Cache[/bold cyan]")
        if not controller.run_phase1_55(volume_id):
            return False

        # Phase 2: Translator
        console.print("\n[bold cyan]Phase 2: Translator[/bold cyan]")
        if not controller.run_phase2(volume_id, force=force):
            return False

        # Phase 4: Builder (optional)
        if auto_build:
            console.print("\n[bold cyan]Phase 4: Builder[/bold cyan]")
            return controller.run_phase4(volume_id)

        return True

    def _run_phase2(
        self,
        volume_id: str,
        chapters: Optional[list] = None,
        force: bool = False,
    ) -> bool:
        """Run Phase 2 (Translation) only."""
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        console.print("\n[bold cyan]Phase 2: Translator[/bold cyan]")
        return controller.run_phase2(volume_id, chapters=chapters, force=force)

    def _run_phase1(self, epub_path: Path, volume_id: str) -> bool:
        """Run Phase 1 (Librarian) only."""
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        console.print("\n[bold cyan]Phase 1: Librarian[/bold cyan]")
        return controller.run_phase1(epub_path, volume_id)

    def _run_phase1_5(self, volume_id: str) -> bool:
        """Run Phase 1.5 (Metadata) only."""
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        console.print("\n[bold cyan]Phase 1.5: Metadata[/bold cyan]")
        return controller.run_phase1_5(volume_id)

    def _run_phase1_55(self, volume_id: str) -> bool:
        """Run Phase 1.55 (Rich Metadata Cache) only."""
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        console.print("\n[bold cyan]Phase 1.55: Rich Metadata Cache[/bold cyan]")
        console.print("[dim]Caching full LN context + enriching rich metadata...[/dim]")
        return controller.run_phase1_55(volume_id)

    def _run_phase1_6(self, volume_id: str) -> bool:
        """Run Phase 1.6 (Multimodal Processor) only."""
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        console.print("\n[bold cyan]Phase 1.6: Multimodal Processor[/bold cyan]")
        console.print("[dim]Pre-baking illustration analysis with Gemini 3 Pro Vision...[/dim]")
        return controller.run_phase1_6(volume_id, standalone=True)

    def _run_phase4(self, volume_id: str) -> bool:
        """Run Phase 4 (Builder) only."""
        from scripts.mtl import PipelineController

        controller = PipelineController(
            work_dir=self.work_dir,
            verbose=self.config.verbose_mode,
        )

        console.print("\n[bold cyan]Phase 4: Builder[/bold cyan]")
        return controller.run_phase4(volume_id)

    def _run_phases_2_to_4(self, volume_id: str) -> bool:
        """Run Phases 2-4 for an existing volume."""
        if not self._run_phase2(volume_id):
            return False

        # Ask about building
        action = post_translation_menu(volume_id)

        if action == "build":
            return self._run_phase4(volume_id)
        elif action == "status":
            show_status_panel(self.work_dir, volume_id)
            return True

        return True

    def _check_for_sequel(self, volume_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if this volume is a sequel to an existing one.

        Returns:
            Dictionary with sequel info if found, None otherwise
        """
        import json

        manifest_path = self.work_dir / volume_id / "manifest.json"
        if not manifest_path.exists():
            return None

        with open(manifest_path, 'r', encoding='utf-8') as f:
            current_manifest = json.load(f)

        current_title = current_manifest.get('metadata', {}).get('title', '')
        if not current_title:
            return None

        # Search for potential predecessors
        for vol_dir in self.work_dir.iterdir():
            if not vol_dir.is_dir() or vol_dir.name == volume_id:
                continue

            other_manifest_path = vol_dir / "manifest.json"
            if not other_manifest_path.exists():
                continue

            try:
                with open(other_manifest_path, 'r', encoding='utf-8') as f:
                    other_manifest = json.load(f)

                other_title = other_manifest.get('metadata', {}).get('title', '')
                metadata_en = other_manifest.get('metadata_en', {})

                # Simple title prefix match (first 10 characters)
                if current_title and other_title and current_title[:10] == other_title[:10]:
                    return {
                        'volume_id': vol_dir.name,
                        'title': metadata_en.get('title_en', other_title),
                        'data': {
                            'character_names': metadata_en.get('character_names', {}),
                            'glossary': metadata_en.get('glossary', {}),
                            'series_title_en': metadata_en.get('series_title_en', ''),
                            'author_en': metadata_en.get('author_en', ''),
                        }
                    }
            except Exception:
                continue

        return None


def run_tui() -> int:
    """
    Convenience function to run the TUI application.

    Returns:
        Exit code
    """
    app = MTLApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(run_tui())
