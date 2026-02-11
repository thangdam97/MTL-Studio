"""
Cache management utilities for the CLI.
"""

import shutil
from pathlib import Path
from typing import Tuple, Dict
from rich.console import Console

try:
    from pipeline.common.genai_factory import create_genai_client
except ImportError:
    create_genai_client = None

console = Console()


def purge_python_cache(pipeline_root: Path) -> Tuple[int, int]:
    """
    Remove all Python bytecode cache files and directories.

    Args:
        pipeline_root: Root directory of the pipeline

    Returns:
        Tuple of (cache_dirs_removed, pyc_files_removed)
    """
    cache_dirs = 0
    pyc_files = 0

    # Remove __pycache__ directories
    for cache_dir in pipeline_root.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            cache_dirs += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Could not remove {cache_dir}: {e}[/yellow]")

    # Remove .pyc and .pyo files
    for pyc_file in pipeline_root.rglob("*.pyc"):
        try:
            pyc_file.unlink()
            pyc_files += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Could not remove {pyc_file}: {e}[/yellow]")

    for pyo_file in pipeline_root.rglob("*.pyo"):
        try:
            pyo_file.unlink()
            pyc_files += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Could not remove {pyo_file}: {e}[/yellow]")

    return cache_dirs, pyc_files


def purge_gemini_cache() -> Dict[str, any]:
    """
    Remove all Gemini API context caches.

    Returns:
        Dictionary with cache purge results
    """
    try:
        if create_genai_client is None:
            return {
                "success": False,
                "error": "google-genai package not available",
                "caches_removed": 0
            }
        client = create_genai_client()
        caches = list(client.caches.list())

        if caches:
            for cache in caches:
                try:
                    client.caches.delete(name=cache.name)
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not delete cache {cache.name}: {e}[/yellow]")

        return {
            "success": True,
            "caches_removed": len(caches),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "caches_removed": 0
        }


def purge_all_caches(pipeline_root: Path) -> Dict[str, any]:
    """
    Purge all caches (Python bytecode + Gemini API).

    Args:
        pipeline_root: Root directory of the pipeline

    Returns:
        Dictionary with comprehensive purge results
    """
    results = {
        "python": {},
        "gemini": {}
    }

    # Purge Python cache
    cache_dirs, pyc_files = purge_python_cache(pipeline_root)
    results["python"] = {
        "cache_dirs_removed": cache_dirs,
        "pyc_files_removed": pyc_files,
        "total_items": cache_dirs + pyc_files
    }

    # Purge Gemini cache
    results["gemini"] = purge_gemini_cache()

    return results
