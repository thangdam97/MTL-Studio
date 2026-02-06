#!/usr/bin/env python3
"""
Build Sino-Vietnamese Vector Index

This script builds the ChromaDB vector index from sino_vietnamese_rag.json.
Run this once after updating the RAG file, or use --force to rebuild.

Usage:
    python scripts/build_sino_vn_index.py
    python scripts/build_sino_vn_index.py --force
    python scripts/build_sino_vn_index.py --validate
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))

from modules.sino_vietnamese_store import SinoVietnameseStore, create_sino_vn_store


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build Sino-Vietnamese vector search index"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force rebuild of existing index"
    )
    parser.add_argument(
        "--validate", "-v",
        action="store_true",
        help="Run validation tests after building"
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default="./pipeline/chroma_sino_vn",
        help="Directory for ChromaDB persistence (default: ./pipeline/chroma_sino_vn)"
    )
    parser.add_argument(
        "--rag-file",
        type=str,
        default="./pipeline/config/sino_vietnamese_rag.json",
        help="Path to RAG JSON file"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    print("=" * 60)
    print("Sino-Vietnamese Vector Index Builder")
    print("=" * 60)
    
    # Check RAG file exists
    rag_path = Path(args.rag_file)
    if not rag_path.exists():
        logger.error(f"RAG file not found: {rag_path}")
        print(f"\n❌ Error: RAG file not found at {rag_path}")
        print("  Please ensure sino_vietnamese_rag.json exists.")
        sys.exit(1)
    
    print(f"\n📁 RAG file: {rag_path}")
    print(f"📂 Persist directory: {args.persist_dir}")
    
    try:
        # Initialize store
        print("\n⏳ Initializing store...")
        store = SinoVietnameseStore(
            persist_directory=args.persist_dir,
            rag_file_path=str(rag_path)
        )
        
        # Build index
        print("⏳ Building index...")
        counts = store.build_index(force_rebuild=args.force)
        
        print("\n✅ Index built successfully!")
        print("\n📊 Indexed patterns by category:")
        for category, count in counts.items():
            print(f"   - {category}: {count} patterns")
        
        total = sum(counts.values())
        print(f"\n   Total: {total} patterns")
        
        # Validation
        if args.validate:
            print("\n" + "=" * 60)
            print("Running Validation Tests")
            print("=" * 60)
            
            validation = store.validate_index()
            
            print(f"\n📋 Validation Results:")
            print(f"   Passed: {validation['passed']}/{validation['total_tests']}")
            print(f"   Success Rate: {validation['success_rate']:.1f}%")
            
            if validation['failed'] > 0:
                print("\n❌ Failed tests:")
                for detail in validation['details']:
                    if not detail['passed']:
                        print(f"   - Query: {detail['query']}")
            else:
                print("\n✅ All validation tests passed!")
        
        # Print stats
        stats = store.get_stats()
        print("\n📈 Index Statistics:")
        print(f"   Inject threshold: {stats['thresholds']['inject']}")
        print(f"   Log threshold: {stats['thresholds']['log']}")
        
        print("\n" + "=" * 60)
        print("Build Complete!")
        print("=" * 60)
        
    except Exception as e:
        logger.exception("Build failed")
        print(f"\n❌ Build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
