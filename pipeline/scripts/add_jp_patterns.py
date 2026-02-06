#!/usr/bin/env python3
"""
Add Japanese light novel patterns to existing ChromaDB index.
This script adds patterns incrementally to avoid timeout issues.
"""
import json
import sys
import time
import signal
from pathlib import Path

# Handle interrupts gracefully
def signal_handler(signum, frame):
    print(f"\n⚠️ Interrupted at pattern {current_index}. Progress saved.")
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

current_index = 0

def main():
    global current_index
    
    from modules.sino_vietnamese_store import SinoVietnameseStore
    
    persist_dir = Path(__file__).parent.parent / 'chroma_sino_vn'
    rag_path = Path(__file__).parent.parent / 'config/sino_vietnamese_rag.json'
    
    # Load RAG data
    with open(rag_path, 'r', encoding='utf-8') as f:
        rag_data = json.load(f)
    
    jp_patterns = rag_data['pattern_categories']['japanese_light_novel']['patterns']
    print(f"Total Japanese patterns to index: {len(jp_patterns)}")
    
    # Connect to existing store
    store = SinoVietnameseStore(
        persist_directory=str(persist_dir),
        rag_file_path=str(rag_path)
    )
    
    # Check current count
    current_count = store.vector_store.collection.count()
    print(f"Current vectors in index: {current_count}")
    
    # Index patterns in batches
    batch_size = 10
    success_count = 0
    
    for i, pattern in enumerate(jp_patterns):
        current_index = i
        
        try:
            store._index_pattern(
                pattern, 
                'japanese_light_novel',
                'Japanese light novel kanji compounds'
            )
            success_count += 1
            
            if (i + 1) % batch_size == 0:
                print(f"  Progress: {i + 1}/{len(jp_patterns)} (success: {success_count})")
                time.sleep(0.5)  # Small delay to avoid rate limiting
                
        except Exception as e:
            print(f"  ⚠️ Error at pattern {i} ({pattern.get('hanzi', '?')}): {e}")
            time.sleep(2)  # Longer delay on error
    
    # Final count
    final_count = store.vector_store.collection.count()
    print(f"\n✓ Indexing complete!")
    print(f"  Patterns processed: {len(jp_patterns)}")
    print(f"  Successfully indexed: {success_count}")
    print(f"  Total vectors: {final_count}")

if __name__ == '__main__':
    print("="*50)
    print("ADD JAPANESE PATTERNS TO INDEX")
    print("="*50)
    main()
