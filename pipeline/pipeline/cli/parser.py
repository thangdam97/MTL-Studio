"""CLI parser construction for MTL Studio v5.2."""

import argparse


def _add_ui_flags(parser: argparse.ArgumentParser) -> None:
    """Attach shared UI flags to parser instances."""
    parser.add_argument(
        '--ui',
        choices=['auto', 'rich', 'plain'],
        default='auto',
        help='CLI presentation mode (auto=detect rich support)',
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output (useful for plain logs/CI)',
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser with all command definitions."""
    parser = argparse.ArgumentParser(
        description="MTL Studio v5.2 CLI | Bible + Series Continuity + Three-Pillar Translation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline Flow (v5.2):
  Phase 1 -> 1.5 -> 1.55 -> 1.6 -> 2 -> 3 -> 4
  Librarian -> Metadata -> Rich Cache -> Art Director -> Translator -> Critics -> Builder

Quick Start:
  mtl.py run INPUT/novel_v1.epub
  mtl.py run INPUT/novel_v1.epub --id novel_v1 --verbose

Core Commands:
  mtl.py phase1 INPUT/novel_v1.epub --id novel_v1
  mtl.py phase1.5 novel_v1
  mtl.py phase1.55 novel_v1
  mtl.py phase1.6 novel_v1
  mtl.py phase2 novel_v1 --enable-multimodal
  mtl.py phase4 novel_v1
  mtl.py bible list
  mtl.py bible sync novel_v1 --direction both

Quality Control:
  mtl.py cjk-clean novel_v1 --dry-run
  mtl.py heal novel_v1 --vn
  mtl.py metadata novel_v1 --validate

Inspection and Debug:
  mtl.py list
  mtl.py status novel_v1
  mtl.py cache-inspect novel_v1 --detail
  mtl.py visual-thinking novel_v1 --with-cache

Metadata Schema Auto-Transform:
  Enhanced v2.1 | Legacy V2 | V4 Nested -> Unified translator format
        """
    )
    _add_ui_flags(parser)

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        '--verbose',
        dest='verbose',
        action='store_true',
        default=True,
        help='Show detailed logs (default: enabled)',
    )
    parent_parser.add_argument(
        '--quiet',
        dest='verbose',
        action='store_false',
        help='Use concise logs (disables verbose debug output)',
    )
    _add_ui_flags(parent_parser)

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Run command (full pipeline)
    run_parser = subparsers.add_parser(
        'run',
        parents=[parent_parser],
        help='Run full pipeline (1 -> 1.5 -> 1.55 -> 1.6 -> 2 -> 4)'
    )
    run_parser.add_argument('epub_path', type=str, help='Path to Japanese EPUB file')
    run_parser.add_argument('--id', dest='volume_id', type=str, help='Custom volume ID (auto-generated if not provided)')
    run_parser.add_argument(
        '--skip-multimodal',
        action='store_true',
        help='Skip Phase 1.6 (visual analysis) for faster processing'
    )

    # Phase 0 (Deprecated - kept for backward compatibility)
    phase0_parser = subparsers.add_parser(
        'phase0',
        parents=[parent_parser],
        help='[DEPRECATED] Use phase1.6 instead. Pre-compute visual analysis for illustrations'
    )
    phase0_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')

    # Phase 1
    phase1_parser = subparsers.add_parser('phase1', parents=[parent_parser], help='Run Phase 1: Librarian (EPUB Extraction)')
    phase1_parser.add_argument('epub_path', type=str, help='Path to Japanese EPUB file')
    phase1_parser.add_argument('--id', dest='volume_id', type=str, required=False, help='Custom volume ID (auto-generated if not provided)')

    # Phase 1.5
    phase1_5_parser = subparsers.add_parser(
        'phase1.5',
        parents=[parent_parser],
        help='Run Phase 1.5: Metadata Processor (schema autoupdate + title/author/chapter translation)'
    )
    phase1_5_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')

    # Phase 1.55
    phase1_55_parser = subparsers.add_parser(
        'phase1.55',
        parents=[parent_parser],
        help='Run Phase 1.55: Full-LN cache rich metadata enrichment'
    )
    phase1_55_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')

    # Phase 1.6 (Multimodal Processor)
    phase1_6_parser = subparsers.add_parser(
        'phase1.6',
        parents=[parent_parser],
        help='Run Phase 1.6: Multimodal Processor (visual analysis for illustrations)'
    )
    phase1_6_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')

    # Multimodal Translator (Phase 1.6 + Phase 2)
    multimodal_parser = subparsers.add_parser(
        'multimodal',
        parents=[parent_parser],
        help='Run Multimodal Translator: Phase 1.6 (visual analysis) + Phase 2 (translation with visual context)'
    )
    multimodal_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    multimodal_parser.add_argument('--chapters', nargs='+', help='Specific chapters to translate')
    multimodal_parser.add_argument('--force', action='store_true', help='Re-translate completed chapters')

    # Phase 2
    phase2_parser = subparsers.add_parser('phase2', parents=[parent_parser], help='Run Phase 2: Translator (RAG + Vector + Visual)')
    phase2_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    phase2_parser.add_argument('--chapters', nargs='+', help='Specific chapters to translate')
    phase2_parser.add_argument('--force', action='store_true', help='Re-translate completed chapters')
    # Deprecated legacy continuity switch kept as hidden no-op for backward compatibility.
    phase2_parser.add_argument(
        '--enable-continuity',
        action='store_true',
        help=argparse.SUPPRESS,
    )
    phase2_parser.add_argument(
        '--enable-gap-analysis',
        action='store_true',
        help='Enable semantic gap analysis (Week 2-3 integration) for improved translation quality'
    )
    phase2_parser.add_argument(
        '--enable-multimodal',
        action='store_true',
        help='Enable multimodal visual context injection (requires Phase 1.6)'
    )

    # Phase 3
    phase3_parser = subparsers.add_parser('phase3', parents=[parent_parser], help='Show Phase 3 instructions (Manual/Agentic Workflow)')
    phase3_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')

    # Phase 4
    phase4_parser = subparsers.add_parser('phase4', parents=[parent_parser], help='Run Phase 4: Builder (EPUB Packaging)')
    phase4_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    phase4_parser.add_argument('--output', type=str, help='Custom output filename')

    # Cleanup
    cleanup_parser = subparsers.add_parser(
        'cleanup',
        parents=[parent_parser],
        help='Clean up translated chapter titles (remove wrong numbers, illustration markers)'
    )
    cleanup_parser.add_argument('volume_id', type=str, help='Volume ID')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='Preview changes without modifying files')

    # CJK Clean (Vietnamese post-processor)
    cjk_clean_parser = subparsers.add_parser(
        'cjk-clean',
        parents=[parent_parser],
        help='Run Vietnamese CJK hard substitution cleaner (少女→thiếu nữ, スタミナ→sức bền, etc.)'
    )
    cjk_clean_parser.add_argument('volume_id', type=str, help='Volume ID')
    cjk_clean_parser.add_argument('--dry-run', action='store_true', help='Preview substitutions without modifying files')

    # Self-Healing Anti-AI-ism Agent
    heal_parser = subparsers.add_parser(
        'heal',
        parents=[parent_parser],
        help='Run Self-Healing Anti-AI-ism Agent (3-layer detection + LLM auto-correction)'
    )
    heal_parser.add_argument('volume_id', type=str, help='Volume ID to heal')
    heal_parser.add_argument('--dry-run', action='store_true', help="Scan only, don't modify files")
    heal_parser.add_argument('--vn', action='store_true', help='Target Vietnamese (default: auto-detect)')
    heal_parser.add_argument('--en', action='store_true', help='Target English (default: auto-detect)')

    # Cache Inspect (Multimodal)
    cache_parser = subparsers.add_parser(
        'cache-inspect',
        parents=[parent_parser],
        help='Inspect visual analysis cache for a volume (multimodal)'
    )
    cache_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    cache_parser.add_argument('--detail', action='store_true', help='Show full analysis per illustration')

    # Visual Thinking (JSON → Markdown converter)
    vt_parser = subparsers.add_parser(
        'visual-thinking',
        parents=[parent_parser],
        help='Convert Gemini 3 Pro visual thought logs (JSON) to markdown'
    )
    vt_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    vt_parser.add_argument('--split', action='store_true', help='Generate one markdown file per illustration instead of consolidated')
    vt_parser.add_argument('--with-cache', action='store_true', help="Include Art Director's Notes output from visual_cache.json")
    vt_parser.add_argument('--filter', choices=['illust', 'kuchie', 'cover'], help='Only convert a specific illustration type')
    vt_parser.add_argument('--output-dir', type=str, help='Custom output directory (default: THINKING/ inside volume)')

    # Status
    status_parser = subparsers.add_parser('status', parents=[parent_parser], help='Show pipeline status for a volume')
    status_parser.add_argument('volume_id', type=str, help='Volume ID')

    # List
    subparsers.add_parser('list', parents=[parent_parser], help='List all volumes')

    # Config
    config_parser = subparsers.add_parser('config', parents=[parent_parser], help='View or modify v5.2 pipeline configuration')
    config_parser.add_argument('--show', action='store_true', help='Show current configuration')
    config_parser.add_argument('--toggle-pre-toc', action='store_true', help='Toggle pre-TOC content detection (rare opening hooks before prologue)')
    config_parser.add_argument('--toggle-multimodal', action='store_true', help='Toggle multimodal visual context (experimental)')
    config_parser.add_argument('--toggle-smart-chunking', action='store_true', help='Toggle smart chunking for massive chapters')
    config_parser.add_argument('--language', type=str, choices=['en', 'vn'], help='Switch target language (en=English, vn=Vietnamese)')
    config_parser.add_argument('--show-language', action='store_true', help='Show current target language details')
    config_parser.add_argument(
        '--model',
        type=str,
        choices=[
            'pro', 'flash', '2.5-pro', '2.5-flash',
            'gemini-3-pro-preview', 'gemini-3-flash-preview',
            'gemini-2.5-pro', 'gemini-2.5-flash'
        ],
        help='Switch translation model (aliases or full model IDs)'
    )
    config_parser.add_argument('--temperature', type=float, help='Set temperature (0.0-2.0, default: 0.6)')
    config_parser.add_argument('--top-p', type=float, help='Set top_p (0.0-1.0, default: 0.95)')
    config_parser.add_argument('--top-k', type=int, help='Set top_k (1-100, default: 40)')

    # Metadata inspection
    metadata_parser = subparsers.add_parser(
        'metadata',
        parents=[parent_parser],
        help='Inspect metadata schema and validate translator compatibility'
    )
    metadata_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    metadata_parser.add_argument('--validate', action='store_true', help='Run full validation with detailed compatibility report')

    # Schema command - advanced schema manipulation
    schema_parser = subparsers.add_parser(
        'schema',
        parents=[parent_parser],
        help='Advanced schema manipulation (add/edit characters, keigo_switch, validation)'
    )
    schema_parser.add_argument('volume_id', type=str, nargs='?', help='Volume ID (optional - will prompt if not provided)')
    schema_parser.add_argument(
        '--action',
        '-a',
        choices=['show', 'validate', 'add-character', 'bulk-keigo', 'apply-keigo', 'generate-keigo', 'sync', 'init', 'export'],
        default='show',
        help='Schema action to perform (default: show)'
    )
    schema_parser.add_argument('--name', '-n', help='Character name (for add-character)')
    schema_parser.add_argument('--json', '-j', help='JSON file (for apply-keigo, import)')
    schema_parser.add_argument('--output', '-o', help='Output file (for export, generate-keigo)')

    # Bible command - series bible management
    bible_parser = subparsers.add_parser(
        'bible',
        parents=[parent_parser],
        help='Series Bible management (cross-volume canonical metadata)'
    )
    bible_subparsers = bible_parser.add_subparsers(dest='bible_action')

    # bible list
    bible_subparsers.add_parser('list', help='List all registered series bibles')

    # bible show <bible_id>
    bible_show_p = bible_subparsers.add_parser('show', help='Display categorized bible contents')
    bible_show_p.add_argument('bible_id', type=str, help='Series bible ID (e.g. madan_no_ou_to_vanadis)')

    # bible validate <bible_id>
    bible_validate_p = bible_subparsers.add_parser('validate', help='Validate bible for issues')
    bible_validate_p.add_argument('bible_id', type=str, help='Series bible ID')

    # bible import <volume_id>
    bible_import_p = bible_subparsers.add_parser('import', help='Import terms from volume manifest into bible')
    bible_import_p.add_argument('volume_id', type=str, help='Volume ID (e.g. 25d9)')

    # bible link <volume_id> [--bible <bible_id>]
    bible_link_p = bible_subparsers.add_parser('link', help='Link volume to series bible')
    bible_link_p.add_argument('volume_id', type=str, help='Volume ID (e.g. 25d9)')
    bible_link_p.add_argument('--bible', dest='bible_id', type=str, help='Target bible ID (auto-detect if omitted)')

    # bible unlink <volume_id>
    bible_unlink_p = bible_subparsers.add_parser('unlink', help='Unlink volume from its bible')
    bible_unlink_p.add_argument('volume_id', type=str, help='Volume ID')

    # bible orphans
    bible_subparsers.add_parser('orphans', help='Find WORK/ volumes not linked to any bible')

    # bible prompt <bible_id>
    bible_prompt_p = bible_subparsers.add_parser('prompt', help='Preview injected prompt block')
    bible_prompt_p.add_argument('bible_id', type=str, help='Series bible ID')

    # bible sync <volume_id> [--direction pull|push|both]
    bible_sync_p = bible_subparsers.add_parser('sync', help='Run bible ↔ manifest sync (pull + push)')
    bible_sync_p.add_argument('volume_id', type=str, help='Volume short ID (e.g. 25d9)')
    bible_sync_p.add_argument('--direction', choices=['pull', 'push', 'both'],
                              default='both', help='Sync direction (default: both)')

    return parser
