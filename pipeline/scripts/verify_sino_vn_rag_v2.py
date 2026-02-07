#!/usr/bin/env python3
"""Verify sino_vietnamese_rag_v2.json integrity and schema compliance."""
import json
from pathlib import Path

v2_path = Path(__file__).parent.parent / "config" / "sino_vietnamese_rag_v2.json"
with open(v2_path) as f:
    v2 = json.load(f)

print("=== SCHEMA VALIDATION ===")

# Check top-level keys
required_keys = ["version", "description", "pattern_categories", "negative_vectors", "genre_mapping", "validation_rules"]
for k in required_keys:
    status = "✓" if k in v2 else "✗ MISSING"
    print(f"  {status} {k}")

# Check each category
cats = v2["pattern_categories"]
print(f"\n=== CATEGORIES ({len(cats)}) ===")
total_patterns = 0
total_contexts = 0
total_examples = 0
all_hanzi = set()

for cat_name, cat_data in cats.items():
    patterns = cat_data.get("patterns", [])
    n = len(patterns)
    total_patterns += n
    
    # Validate pattern schema
    issues = []
    cat_contexts = 0
    cat_examples = 0
    
    for i, p in enumerate(patterns):
        # Required fields
        if "hanzi" not in p:
            issues.append(f"  pattern[{i}] missing 'hanzi'")
        if "id" not in p:
            issues.append(f"  pattern[{i}] missing 'id'")
        
        hanzi = p.get("hanzi", "")
        all_hanzi.add(hanzi)
        
        # Check contexts exist (for indexing)
        if "contexts" in p:
            for ctx in p["contexts"]:
                cat_contexts += 1
                for ex in ctx.get("examples", []):
                    cat_examples += 1
                    if "zh" not in ex:
                        issues.append(f"  {hanzi}: example missing 'zh'")
                    if "vn_correct" not in ex:
                        issues.append(f"  {hanzi}: example missing 'vn_correct'")
        elif "examples" in p:
            for ex in p["examples"]:
                cat_examples += 1
    
    total_contexts += cat_contexts
    total_examples += cat_examples
    
    status = "✓" if not issues else "⚠"
    print(f"  {status} {cat_name}: {n} patterns, {cat_contexts} contexts, {cat_examples} examples")
    for issue in issues[:3]:
        print(f"    {issue}")

print(f"\n=== TOTALS ===")
print(f"  Total patterns: {total_patterns}")
print(f"  Total contexts: {total_contexts}")
print(f"  Total examples: {total_examples}")
print(f"  Unique hanzi: {len(all_hanzi)}")

# Check negative vectors
nv = v2.get("negative_vectors", {})
print(f"\n=== NEGATIVE VECTORS ===")
for cat, vectors in nv.items():
    print(f"  {cat}: {len(vectors)} vectors")

# Check false cognates are IN categories now
fc_in_cats = "false_cognates" in cats
fc_top_level = "false_cognates" in v2
print(f"\n=== BUG FIX VERIFICATION ===")
print(f"  false_cognates in pattern_categories: {'✓ YES' if fc_in_cats else '✗ NO'}")
print(f"  false_cognates as top-level (old bug): {'✗ STILL THERE' if fc_top_level else '✓ REMOVED'}")

# Check register_substitutions
reg = cats.get("register_substitutions", {}).get("patterns", [])
print(f"\n=== REGISTER SUBSTITUTIONS (NEW) ===")
for p in reg[:5]:
    hanzi = p.get("hanzi", "")
    contexts = p.get("contexts", [])
    readings = [c.get("vn_translation", "") for c in contexts]
    print(f"  {hanzi}: {' / '.join(readings)}")
print(f"  ... ({len(reg)} total)")

# Check corpus_discovered
cd = cats.get("corpus_discovered", {}).get("patterns", [])
print(f"\n=== CORPUS DISCOVERED (NEW) ===")
for p in cd[:5]:
    hanzi = p.get("hanzi", "")
    freq = p.get("corpus_frequency", 0)
    vn = p.get("primary_reading", "")
    print(f"  {hanzi} (freq={freq}): {vn}")
print(f"  ... ({len(cd)} total)")

# Version check
print(f"\n=== VERSION ===")
print(f"  Version: {v2.get('version')}")
print(f"  Status: {v2.get('status')}")
print(f"  Last updated: {v2.get('last_updated')}")

# File size
import os
size_kb = os.path.getsize(v2_path) / 1024
print(f"  File size: {size_kb:.1f} KB")

print(f"\n{'='*50}")
print(f"VALIDATION: {'PASSED ✓' if total_patterns > 800 and fc_in_cats else 'FAILED ✗'}")
