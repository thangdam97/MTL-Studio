#!/usr/bin/env python3
"""
Rebuild ChromaDB vector index for Sino-Vietnamese patterns.
"""

import sys
sys.path.insert(0, '..')

from modules.sino_vietnamese_store import SinoVietnameseStore

def main():
    print("=" * 60)
    print("REBUILDING CHROMADB VECTOR INDEX")
    print("=" * 60)
    
    store = SinoVietnameseStore()
    
    print(f"\nCurrent vectors: {store.vector_store.collection.count()}")
    print("\nRebuilding index (force_rebuild=True)...")
    
    result = store.build_index(force_rebuild=True)
    
    print(f"\nResult: {result}")
    print(f"Total vectors after rebuild: {store.vector_store.collection.count()}")
    print("\n✓ Rebuild complete")

if __name__ == "__main__":
    main()
