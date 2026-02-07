#!/usr/bin/env python3
"""Verify vietnamese_grammar_rag_v2.json structure and counts."""
import json
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
json_path = os.path.join(base_dir, 'config', 'vietnamese_grammar_rag_v2.json')

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Version: {data['version']}")
print(f"Embedding: {data['metadata']['embedding_model']}")
print(f"Collection: {data['metadata']['collection_name']}")

base_cats = data['pattern_categories']
adv_cats = data.get('advanced_patterns', {})

total_patterns = 0
total_examples = 0
neg_anchor_cats = 0
corpus_examples = 0

print(f"\n=== BASE CATEGORIES ({len(base_cats)}) ===")
for cat_name, cat_data in base_cats.items():
    patterns = cat_data.get('patterns', [])
    examples = sum(len(p.get('examples', [])) for p in patterns)
    corpus = sum(1 for p in patterns for e in p.get('examples', []) if 'source' in e)
    neg = 'negative_vectors' in cat_data
    total_patterns += len(patterns)
    total_examples += examples
    corpus_examples += corpus
    if neg:
        neg_anchor_cats += 1
    flag = " [NEG]" if neg else ""
    print(f"  {cat_name}: {len(patterns)} patterns, {examples} examples ({corpus} corpus){flag}")

print(f"\n=== ADVANCED CATEGORIES ===")
for key, val in adv_cats.items():
    if key == 'description':
        continue
    patterns = val.get('patterns', [])
    examples = sum(len(p.get('examples', [])) for p in patterns)
    corpus = sum(1 for p in patterns for e in p.get('examples', []) if 'source' in e)
    neg = 'negative_vectors' in val
    total_patterns += len(patterns)
    total_examples += examples
    corpus_examples += corpus
    if neg:
        neg_anchor_cats += 1
    flag = " [NEG]" if neg else ""
    print(f"  {key}: {len(patterns)} patterns, {examples} examples ({corpus} corpus){flag}")

adv_count = len([k for k in adv_cats if k != 'description'])
total_cats = len(base_cats) + adv_count

print(f"\n=== TOTALS ===")
print(f"Base categories: {len(base_cats)}")
print(f"Advanced categories: {adv_count}")
print(f"Total categories: {total_cats}")
print(f"Total patterns: {total_patterns}")
print(f"Total examples: {total_examples}")
print(f"  - From real corpus: {corpus_examples}")
print(f"Categories with negative anchors: {neg_anchor_cats}/{total_cats}")
print(f"RAG pipeline steps: {len(data['rag_retrieval_strategy']['steps'])}")
print(f"Negative anchor coverage: {len(data['rag_retrieval_strategy']['negative_anchor_system']['covered_categories'])} categories")

# Verify all pattern IDs are unique
all_ids = []
for cat_data in base_cats.values():
    for p in cat_data.get('patterns', []):
        all_ids.append(p['id'])
for key, val in adv_cats.items():
    if key == 'description':
        continue
    for p in val.get('patterns', []):
        all_ids.append(p['id'])

dupes = [pid for pid in all_ids if all_ids.count(pid) > 1]
if dupes:
    print(f"\n⚠️  DUPLICATE IDs: {set(dupes)}")
else:
    print(f"\n✅ All {len(all_ids)} pattern IDs are unique")

# File size
size = os.path.getsize(json_path)
print(f"\nFile size: {size:,} bytes ({size//1024} KB)")

# Line count
with open(json_path, 'r') as f:
    lines = len(f.readlines())
print(f"Line count: {lines:,}")
