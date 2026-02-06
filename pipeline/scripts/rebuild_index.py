#!/usr/bin/env python3
"""
Rebuild ChromaDB index with Japanese patterns merged into RAG database.

Due to API rate limits and the large number of patterns, this script:
1. Merges Japanese patterns into the main RAG database (fast)
2. Optionally rebuilds the ChromaDB vector index (slow, requires API calls)

Usage:
    # Merge only (fast)
    python scripts/rebuild_index.py --merge-only
    
    # Full rebuild (slow, may take several minutes)
    python scripts/rebuild_index.py
"""
import json
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def merge_japanese_patterns():
    """Merge Japanese patterns into main RAG database."""
    
    # Load Japanese patterns
    jp_path = Path(__file__).parent.parent / 'config/japanese_patterns_auto.json'
    with open(jp_path, 'r', encoding='utf-8') as f:
        jp_data = json.load(f)
    
    # Load main RAG file
    rag_path = Path(__file__).parent.parent / 'config/sino_vietnamese_rag.json'
    with open(rag_path, 'r', encoding='utf-8') as f:
        rag_data = json.load(f)
    
    # Check if already merged
    existing = rag_data.get('pattern_categories', {}).get('japanese_light_novel', {})
    if existing.get('patterns'):
        print(f'✓ Japanese patterns already merged ({len(existing["patterns"])} patterns)')
        return len(existing['patterns'])
    
    # Convert Japanese patterns to RAG format
    converted_patterns = []
    for category_name, patterns in jp_data.get('categories', {}).items():
        for p in patterns:
            if p.get('vn_correct') and not p['vn_correct'].startswith('[TODO'):
                converted_pattern = {
                    'id': f"jp_{p['zh']}_{category_name}",
                    'hanzi': p['zh'],
                    'primary_reading': p['vn_correct'],
                    'sino_vietnamese': True,
                    'corpus_frequency': p.get('frequency', 0),
                    'contexts': [{
                        'meaning': category_name,
                        'register': 'neutral',
                        'zh_indicators': [],
                        'vn_translation': p['vn_correct'],
                        'vn_phrases': [p['vn_correct']],
                        'avoid': [p['vn_wrong']] if p.get('vn_wrong') else [],
                        'examples': [{
                            'zh': p['zh'],
                            'vn_correct': p['vn_correct'],
                            'vn_wrong': p.get('vn_wrong', ''),
                            'context': 'japanese_light_novel'
                        }]
                    }]
                }
                converted_patterns.append(converted_pattern)
    
    # Add to RAG categories
    rag_data['pattern_categories']['japanese_light_novel'] = {
        'description': 'Japanese light novel kanji compounds for Vietnamese translation',
        'patterns': converted_patterns
    }
    
    # Update metadata
    rag_data['last_updated'] = '2025-01-31'
    if 'japanese_light_novel' not in rag_data['notes']['target_genres']:
        rag_data['notes']['target_genres'].append('japanese_light_novel')
    
    # Save updated RAG file
    with open(rag_path, 'w', encoding='utf-8') as f:
        json.dump(rag_data, f, ensure_ascii=False, indent=4)
    
    print(f'✓ Merged {len(converted_patterns)} Japanese patterns into RAG database')
    print(f'  Categories in RAG: {list(rag_data["pattern_categories"].keys())}')
    
    return len(converted_patterns)

def rebuild_chromadb_index():
    """Rebuild the ChromaDB vector index with retry logic."""
    from modules.sino_vietnamese_store import SinoVietnameseStore
    import shutil
    import time
    
    persist_dir = Path(__file__).parent.parent / 'chroma_sino_vn'
    rag_path = Path(__file__).parent.parent / 'config/sino_vietnamese_rag.json'
    
    # Delete old index if exists
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
        print(f'✓ Deleted old index at {persist_dir}')
    
    # Create new store and build index
    print('Building new ChromaDB index (this may take several minutes)...')
    print('  Note: Each pattern requires an API call for embeddings')
    start_time = time.time()
    
    # Retry logic for network issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            store = SinoVietnameseStore(
                persist_directory=str(persist_dir),
                rag_file_path=str(rag_path)
            )
            
            # Build the index with progress
            store.build_index(force_rebuild=(attempt == 0))
            
            elapsed = time.time() - start_time
            
            # Verify - access collection through vector_store
            count = store.vector_store.collection.count() if store.vector_store else 0
            print(f'✓ ChromaDB index rebuilt with {count} vectors in {elapsed:.1f}s')
            
            return count
            
        except Exception as e:
            print(f'⚠️ Attempt {attempt + 1} failed: {e}')
            if attempt < max_retries - 1:
                print(f'   Retrying in 5 seconds...')
                time.sleep(5)
            else:
                print(f'❌ Failed after {max_retries} attempts')
                raise
    
    return 0

def verify_rag_data():
    """Verify the RAG data is correctly structured."""
    rag_path = Path(__file__).parent.parent / 'config/sino_vietnamese_rag.json'
    
    with open(rag_path, 'r', encoding='utf-8') as f:
        rag_data = json.load(f)
    
    categories = rag_data.get('pattern_categories', {})
    
    print('\n=== RAG Database Summary ===')
    total = 0
    for cat_name, cat_data in categories.items():
        count = len(cat_data.get('patterns', []))
        total += count
        print(f'  {cat_name}: {count} patterns')
    
    print(f'  Total: {total} patterns')
    return total

def test_direct_lookup():
    """Test direct lookup without vector search (faster verification)."""
    rag_path = Path(__file__).parent.parent / 'config/sino_vietnamese_rag.json'
    
    with open(rag_path, 'r', encoding='utf-8') as f:
        rag_data = json.load(f)
    
    # Build a quick lookup index
    lookup = {}
    for cat_name, cat_data in rag_data.get('pattern_categories', {}).items():
        for pattern in cat_data.get('patterns', []):
            hanzi = pattern.get('hanzi', '')
            if hanzi:
                lookup[hanzi] = {
                    'vn': pattern.get('primary_reading', ''),
                    'category': cat_name
                }
    
    # Test some Japanese patterns
    test_terms = ['彼女', '少女', '世界', '魔法', '勇者', '二人', '一人', '可愛']
    
    print('\n=== Direct Lookup Test ===')
    found = 0
    for term in test_terms:
        if term in lookup:
            print(f'  ✓ {term} → {lookup[term]["vn"]} ({lookup[term]["category"]})')
            found += 1
        else:
            print(f'  ✗ {term} not found')
    
    print(f'  Found: {found}/{len(test_terms)}')
    return found

def test_search():
    """Test search functionality."""
    from modules.sino_vietnamese_store import SinoVietnameseStore
    
    persist_dir = Path(__file__).parent.parent / 'chroma_sino_vn'
    rag_path = Path(__file__).parent.parent / 'config/sino_vietnamese_rag.json'
    
    store = SinoVietnameseStore(
        persist_directory=str(persist_dir),
        rag_file_path=str(rag_path)
    )
    
    # Test searches
    test_queries = ['彼女', '少女', '世界', '魔法', '勇者']
    print('\n=== Search Tests ===')
    for query in test_queries:
        results = store.vector_store.search(query, top_k=3)
        if results:
            print(f'  {query}:')
            for r in results[:2]:
                jp = r.get("japanese", r.get("hanzi", "?"))
                vn = r.get("vietnamese", r.get("primary_reading", "?"))
                score = r.get("similarity", 0)
                print(f'    → {jp} = {vn} (score: {score:.3f})')
        else:
            print(f'  {query}: No results')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Rebuild Sino-Vietnamese index')
    parser.add_argument('--merge-only', action='store_true', 
                        help='Only merge JSON, skip vector index rebuild')
    parser.add_argument('--verify', action='store_true',
                        help='Verify RAG data without rebuilding')
    parser.add_argument('--test-lookup', action='store_true',
                        help='Test direct lookup (no vector search)')
    args = parser.parse_args()
    
    print('='*50)
    print('SINO-VIETNAMESE INDEX TOOL')
    print('='*50)
    
    if args.verify:
        # Just verify the data
        verify_rag_data()
        sys.exit(0)
    
    if args.test_lookup:
        # Just test direct lookup
        verify_rag_data()
        test_direct_lookup()
        sys.exit(0)
    
    # Step 1: Merge Japanese patterns
    print('\n[1/3] Merging Japanese patterns...')
    pattern_count = merge_japanese_patterns()
    
    # Verify
    verify_rag_data()
    
    if args.merge_only:
        print('\n✓ Merge complete. Run without --merge-only to rebuild vector index.')
        test_direct_lookup()
        sys.exit(0)
    
    # Step 2: Rebuild ChromaDB index
    print('\n[2/3] Rebuilding ChromaDB index...')
    vector_count = rebuild_chromadb_index()
    
    # Step 3: Test search
    print('\n[3/3] Testing search...')
    test_search()
    
    print('\n' + '='*50)
    print(f'INDEX REBUILD COMPLETE')
    print(f'  Patterns merged: {pattern_count}')
    print(f'  Vectors indexed: {vector_count}')
    print('='*50)
