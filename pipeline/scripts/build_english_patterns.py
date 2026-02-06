"""
Build English Grammar Pattern Vector Index
Reads config/english_grammar_rag.json and indexes patterns into ChromaDB

Usage:
    python scripts/build_english_patterns.py

This script will:
1. Load patterns from english_grammar_rag.json
2. Generate embeddings using Gemini text-embedding-004
3. Store vectors in ChromaDB at ./chroma_english_patterns
4. Run a test search to verify functionality
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.english_pattern_store import EnglishPatternStore


def main():
    """Build English pattern vector index from scratch."""
    print("="*70)
    print("  English Grammar Pattern Vector Index Builder")
    print("="*70)
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

    # Check if index already exists
    if persist_dir.exists():
        print(f"⚠️  WARNING: Vector store already exists at {persist_dir}")
        print(f"   This script will ADD to the existing index (not rebuild)")
        print(f"   To rebuild from scratch, use: python scripts/rebuild_english_vectors.py")
        response = input("\n   Continue adding to existing index? (y/N): ")
        if response.lower() != 'y':
            print("   Aborted.")
            sys.exit(0)
        print()

    # Initialize store
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
    print("  Building Vector Index")
    print("-"*70)
    print()

    # Build index
    try:
        indexed_counts = store.build_index(force_rebuild=False)
    except Exception as e:
        print(f"\n❌ ERROR: Index build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("="*70)
    print("  Index Build Complete!")
    print("="*70)
    print()
    print(f"📊 Statistics:")
    print(f"   Total categories: {len(indexed_counts)}")
    total_patterns = sum(indexed_counts.values())
    print(f"   Total patterns: {total_patterns}")
    print()
    print(f"📁 Category Breakdown:")
    for category, count in indexed_counts.items():
        print(f"   - {category}: {count} patterns")

    print()
    print("-"*70)
    print("  Testing Vector Search")
    print("-"*70)
    print()

    # Test search with sample Japanese text
    test_queries = [
        "真理亜は変だが、如月さんも結構変だ",
        "それはともかく、今日の授業はどうだった",
        "彼女は美しいだけでなく、頭もいい"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: {query}")
        try:
            results = store.search(query, top_k=1)
            if results:
                top_match = results[0]
                similarity = top_match['similarity']
                english_pattern = top_match['metadata'].get('english_pattern', 'N/A')
                natural = top_match['metadata'].get('natural', 'N/A')

                print(f"   ✓ Match found (similarity: {similarity:.3f})")
                print(f"     English Pattern: {english_pattern}")
                print(f"     Natural Example: {natural[:80]}...")

                if similarity >= EnglishPatternStore.THRESHOLD_INJECT:
                    print(f"     Status: HIGH CONFIDENCE (will be injected)")
                elif similarity >= EnglishPatternStore.THRESHOLD_LOG:
                    print(f"     Status: MEDIUM CONFIDENCE (will be logged)")
                else:
                    print(f"     Status: LOW CONFIDENCE (will be ignored)")
            else:
                print(f"   ⚠️  No matches found")
        except Exception as e:
            print(f"   ❌ Search failed: {e}")

        print()

    # Display collection stats
    print("-"*70)
    print("  Collection Statistics")
    print("-"*70)
    print()

    try:
        stats = store.get_collection_stats()
        print(f"Collection Name: {stats['collection_name']}")
        print(f"Total Patterns: {stats['total_patterns']}")
        print(f"Persist Directory: {stats['persist_directory']}")
        print(f"Thresholds:")
        print(f"  - Inject (high confidence): ≥{stats['thresholds']['inject']}")
        print(f"  - Log (medium confidence): ≥{stats['thresholds']['log']}")
    except Exception as e:
        print(f"⚠️  Could not retrieve stats: {e}")

    print()
    print("="*70)
    print("  ✅ Build Complete!")
    print("="*70)
    print()
    print("Next steps:")
    print("  1. Test pattern detection: python scripts/test_pattern_detection.py")
    print("  2. Run translation with pattern guidance enabled")
    print("  3. To rebuild index: python scripts/rebuild_english_vectors.py")
    print()


if __name__ == "__main__":
    main()
