"""
MT Publishing Pipeline - Machine Translation for Light Novels

A multi-stage pipeline for translating Japanese light novels to English:
1. Librarian - EPUB extraction, metadata parsing, content cataloging
1.5. Metadata Processor - Schema autoupdate + metadata translation
2. Translator - Gemini-powered translation with RAG knowledge base
3. Critics - Manual/Agentic audit workflow (Claude Code + IDE Agent)
4. Builder - EPUB assembly and professional packaging

Usage:
    python -m pipeline.librarian.agent INPUT/Novel.epub --volume-id novel_v1
    python -m pipeline.metadata_processor.agent --volume novel_v1
    python -m pipeline.translator.agent --volume novel_v1
    # Phase 3: Use Claude Code for agentic QC (see .agent/ for instructions)
    python -m pipeline.builder.agent novel_v1
"""

__version__ = "1.0.0"
__author__ = "MT Publishing Pipeline"

from pathlib import Path

# Base paths
PIPELINE_ROOT = Path(__file__).parent.parent
INPUT_DIR = PIPELINE_ROOT / "INPUT"
WORK_DIR = PIPELINE_ROOT / "WORK"
OUTPUT_DIR = PIPELINE_ROOT / "OUTPUT"
PROMPTS_DIR = PIPELINE_ROOT / "prompts"
MODULES_DIR = PIPELINE_ROOT / "modules"
TEMPLATES_DIR = PIPELINE_ROOT / "templates"
