"""
Rebuild English Pattern Vectors from Scratch

This script completely rebuilds the English grammar pattern vector index.

Use this when:
- english_grammar_rag.json is updated with new patterns
- Embedding model changes
- ChromaDB schema changes
- Index becomes corrupted

Usage:
    python scripts/rebuild_english_vectors.py
"""

import sys
import os
from pathlib import Path
import shutil

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.english_pattern_store import EnglishPatternStore


def main():
    """Rebuild English pattern vector index from scratch."""
    print("="*70)
    print("  English Grammar Pattern Vector Index Rebuilder")
    print("="*70)
    print()
    print("⚠️  WARNING: This will DELETE the existing vector index and rebuild")
    print("   from scratch. All existing embeddings will be regenerated.")
    print()

    # Configuration
    persist_dir = Path("./chroma_english_patterns")
    rag_file = Path("./config/english_grammar_rag.json")

    # Check if RAG file exists
    if not rag_file.exists():
        print(f"❌ ERROR: RAG file not found at {rag_file}")
        print(f"   Please ensure english_grammar_rag.json exists in the config/ directory")
        sys.exit(1)

    print(f"📁 RAG File: {rag_file}")
    print(f"📁 Vector Store: {persist_dir}")
    print()

    # Check if index exists
    if persist_dir.exists():
        print(f"📂 Found existing index at {persist_dir}")
        print(f"   Directory size: {get_dir_size(persist_dir):.2f} MB")
    else:
        print(f"📂 No existing index found (will create new)")

    print()
    response = input("Continue with rebuild? (yes/N): ")
    if response.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    print()
    print("-"*70)
    print("  Step 1: Removing Existing Index")
    print("-"*70)
    print()

    # Remove existing index
    if persist_dir.exists():
        try:
            print(f"🗑️  Removing {persist_dir}...")
            shutil.rmtree(persist_dir)
            print("   ✓ Existing index removed")
        except Exception as e:
            print(f"   ❌ ERROR: Failed to remove existing index: {e}")
            sys.exit(1)
    else:
        print("   ℹ️  No existing index to remove")

    print()
    print("-"*70)
    print("  Step 2: Initializing New Vector Store")
    print("-"*70)
    print()

    # Initialize new store
    try:
        print("🔧 Initializing English Pattern Store...")
        store = EnglishPatternStore(
            persist_directory=str(persist_dir),
            rag_file_path=str(rag_file)
        )
        print("   ✓ Store initialized")
    except Exception as e:
        print(f"   ❌ ERROR: Failed to initialize store: {e}")
        sys.exit(1)

    print()
    print("-"*70)
    print("  Step 3: Building Vector Index")
    print("-"*70)
    print()
    print("This may take several minutes depending on:")
    print("  - Number of patterns in english_grammar_rag.json")
    print("  - Gemini API rate limits")
    print("  - Network speed")
    print()

    # Build index with force_rebuild=True
    try:
        indexed_counts = store.build_index(force_rebuild=True)
    except Exception as e:
        print(f"\n❌ ERROR: Index build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("="*70)
    print("  Rebuild Complete!")
    print("="*70)
    print()
    print(f"📊 Statistics:")
    print(f"   Total categories: {len(indexed_counts)}")
    total_patterns = sum(indexed_counts.values())
    print(f"   Total patterns: {total_patterns}")
    print()
    print(f"📁 Category Breakdown:")
    for category, count in sorted(indexed_counts.items()):
        print(f"   - {category}: {count} patterns")

    print()
    print(f"💾 Index Size: {get_dir_size(persist_dir):.2f} MB")

    print()
    print("-"*70)
    print("  Verification Test")
    print("-"*70)
    print()

    # Verify with a quick search
    test_query = "真理亜は変だが、如月さんも結構変だ"
    print(f"Testing search: {test_query}")

    try:
        results = store.search(test_query, top_k=1)
        if results:
            top_match = results[0]
            print(f"   ✓ Search successful!")
            print(f"     Similarity: {top_match['similarity']:.3f}")
            print(f"     Pattern: {top_match['metadata'].get('english_pattern', 'N/A')}")
        else:
            print(f"   ⚠️  No matches found (this may be normal if RAG file is empty)")
    except Exception as e:
        print(f"   ❌ Verification failed: {e}")

    print()
    print("="*70)
    print("  ✅ Rebuild Complete!")
    print("="*70)
    print()
    print("The vector index is now ready for use in English translations.")
    print()


def get_dir_size(directory: Path) -> float:
    """
    Calculate directory size in megabytes.

    Args:
        directory: Path to directory

    Returns:
        Size in MB
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except Exception as e:
        return 0.0

    return total_size / (1024 * 1024)  # Convert to MB


if __name__ == "__main__":
    main()
