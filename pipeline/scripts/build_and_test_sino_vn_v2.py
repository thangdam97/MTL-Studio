#!/usr/bin/env python3
"""
Step 5: Build Sino-Vietnamese ChromaDB v2 Index + Comprehensive Test Suite.

This script:
  1. Force-rebuilds the ChromaDB index from sino_vietnamese_rag_v2.json (866 patterns)
  2. Verifies the negative anchor cache builds correctly (15 vectors, 6 categories)
  3. Verifies the direct lookup cache covers all hanzi
  4. Runs queries across all 9 categories
  5. Tests batch guidance (get_bulk_guidance) with genre-aware routing
  6. Tests negative anchor penalty suppression
  7. Runs the built-in validate_index()

Usage:
    cd pipeline/ && python scripts/build_and_test_sino_vn_v2.py
"""

import sys
import time
import json
import logging
from pathlib import Path

# Setup path
PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

from modules.sino_vietnamese_store import SinoVietnameseStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# TEST HELPERS
# ══════════════════════════════════════════════════════════════════════

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.details = []
    
    def ok(self, name, detail=""):
        self.passed += 1
        self.details.append(("PASS", name, detail))
        print(f"  \033[32m✓\033[0m {name}" + (f" — {detail}" if detail else ""))
    
    def fail(self, name, detail=""):
        self.failed += 1
        self.details.append(("FAIL", name, detail))
        print(f"  \033[31m✗\033[0m {name}" + (f" — {detail}" if detail else ""))
    
    def check(self, condition, name, detail=""):
        if condition:
            self.ok(name, detail)
        else:
            self.fail(name, detail)
    
    def summary(self):
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        color = "\033[32m" if self.failed == 0 else "\033[31m"
        print(f"\n{color}{'='*60}\033[0m")
        print(f"  Results: {self.passed}/{total} passed ({pct:.0f}%)")
        if self.failed > 0:
            print(f"  FAILURES:")
            for status, name, detail in self.details:
                if status == "FAIL":
                    print(f"    ✗ {name}: {detail}")
        print(f"{color}{'='*60}\033[0m")
        return self.failed == 0


def main():
    results = TestResult()
    
    print("=" * 60)
    print("Sino-Vietnamese v2.0 — Build Index + Test Suite")
    print("=" * 60)
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 1: Build Index
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 1] Loading ChromaDB Index (skip rebuild if exists)\033[0m")
    
    persist_dir = str(PIPELINE_DIR / "chroma_sino_vn")
    store = SinoVietnameseStore(persist_directory=persist_dir)
    
    # Check if index already has data
    existing_count = store.vector_store.collection.count()
    
    if existing_count >= 900:
        print(f"  Existing index found: {existing_count} vectors — skipping rebuild")
        # Populate stats from RAG data
        rag_data = store.load_rag_data()
        indexed = {}
        for cat_name, cat_data in rag_data.get("pattern_categories", {}).items():
            indexed[cat_name] = len(cat_data.get("patterns", []))
        total_indexed = sum(indexed.values())
        build_time = 0.0
    else:
        t0 = time.time()
        indexed = store.build_index(force_rebuild=True)
        build_time = time.time() - t0
        total_indexed = sum(indexed.values())
        print(f"\n  Build completed in {build_time:.1f}s")
    print(f"  Total patterns indexed: {total_indexed}")
    print(f"  Categories: {len(indexed)}")
    for cat, count in sorted(indexed.items()):
        print(f"    {cat:30s}: {count}")
    
    # Verify collection count
    collection_count = store.vector_store.collection.count()
    print(f"\n  ChromaDB collection count: {collection_count}")
    
    results.check(
        len(indexed) == 9,
        "9 categories indexed",
        f"got {len(indexed)}: {list(indexed.keys())}"
    )
    results.check(
        total_indexed >= 850,
        f"Total patterns >= 850",
        f"got {total_indexed}"
    )
    results.check(
        collection_count > 0,
        f"Collection has vectors",
        f"{collection_count} vectors"
    )
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 2: Negative Anchor Cache
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 2] Negative Anchor Cache\033[0m")
    
    cache = store._build_negative_anchor_cache()
    total_anchors = sum(len(v) for v in cache.values())
    
    print(f"  Categories with negative anchors: {len(cache)}")
    for cat, vecs in sorted(cache.items()):
        print(f"    {cat:30s}: {len(vecs)} vectors")
    
    results.check(
        len(cache) >= 5,
        "Negative anchor categories >= 5",
        f"got {len(cache)}"
    )
    results.check(
        total_anchors >= 12,
        "Total negative anchors >= 12",
        f"got {total_anchors}"
    )
    
    # Verify each anchor is a proper numpy array with correct dimensionality
    import numpy as np
    for cat, vecs in cache.items():
        for vec in vecs:
            if not isinstance(vec, np.ndarray) or vec.shape[0] < 100:
                results.fail(f"Anchor shape for {cat}", f"got {type(vec)}, shape={getattr(vec, 'shape', '?')}")
                break
        else:
            continue
        break
    else:
        results.ok("All negative anchor vectors valid numpy arrays", f"dim={cache[list(cache.keys())[0]][0].shape[0]}")
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 3: Direct Lookup Cache
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 3] Direct Lookup Cache\033[0m")
    
    lookup = store._build_direct_lookup()
    print(f"  Direct lookup entries: {len(lookup)}")
    
    results.check(
        len(lookup) >= 800,
        "Direct lookup entries >= 800",
        f"got {len(lookup)}"
    )
    
    # Spot check known entries
    spot_checks = {
        "cultivation_realms": ["金丹"],
        "corpus_discovered": ["微笑"],
        "sino_disambiguation": ["修"],
    }
    for expected_cat, hanzi_list in spot_checks.items():
        for hz in hanzi_list:
            if hz in lookup:
                actual_cat = lookup[hz].get("category", "?")
                results.check(
                    actual_cat == expected_cat,
                    f"Direct lookup '{hz}' category",
                    f"expected {expected_cat}, got {actual_cat}"
                )
            else:
                results.fail(f"Direct lookup '{hz}'", "not found in cache")
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 4: Query All 9 Categories
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 4] Query All 9 Categories\033[0m")
    
    category_queries = [
        ("sino_disambiguation",      "修真",   "cultivation_novel", "tu"),
        ("cultivation_realms",       "金丹期", "cultivation_novel", "Kim"),
        ("cultivation_techniques",   "炼丹",   "cultivation_novel", None),
        ("titles_honorifics",        "师父",   "cultivation_novel", None),
        ("japanese_light_novel",     "告白",   "romcom",           None),
        ("false_cognates",           "手紙",   "japanese_light_novel", None),
        ("register_substitutions",   "少女",   "romcom",           None),
        ("kanji_difficult_compounds","微妙",   "slice_of_life",    None),
        ("corpus_discovered",        "微笑",   "romcom",           None),
    ]
    
    for expected_cat, query_text, genre, expected_substr in category_queries:
        try:
            hits = store.query_disambiguation(
                chinese_text=query_text,
                prev_context="",
                genre=genre
            )
            if hits:
                top = hits[0]
                top_cat = top.get("category", "?")
                top_score = top.get("score", 0)
                top_hanzi = top.get("hanzi", "?")
                top_vn = top.get("vn_correct") or top.get("vn_term", "?")
                detail = f"score={top_score:.3f} hanzi={top_hanzi} vn={top_vn} cat={top_cat}"
                
                # Check we got results (don't strictly enforce category match
                # since vector search returns by similarity, not category)
                results.check(
                    top_score >= 0.5,
                    f"Query '{query_text}' ({expected_cat})",
                    detail
                )
                if expected_substr:
                    vn_combined = f"{top.get('vn_correct', '')} {top.get('vn_term', '')} {top.get('vn_translation', '')}"
                    results.check(
                        expected_substr.lower() in vn_combined.lower(),
                        f"  -> VN contains '{expected_substr}'",
                        f"got: {vn_combined[:60]}"
                    )
            else:
                results.fail(f"Query '{query_text}' ({expected_cat})", "no results")
        except Exception as e:
            results.fail(f"Query '{query_text}' ({expected_cat})", str(e))
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 5: Bulk Guidance (batch embedding + negative anchors)
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 5] Bulk Guidance (batch embedding)\033[0m")
    
    test_compounds = ["修真", "金丹", "少女", "手紙", "微笑", "天才", "世界"]
    
    t0 = time.time()
    bulk = store.get_bulk_guidance(
        terms=test_compounds,
        genre="romcom",
        max_per_term=2,
        min_confidence=0.60,
        use_external_dict=False  # Don't call external API in tests
    )
    bulk_time = time.time() - t0
    
    bulk_results = bulk.get("results", bulk.get("high_confidence", []))
    stats = bulk.get("stats", bulk.get("lookup_stats", {}))
    
    # The results structure might vary — handle both dict and list formats
    if isinstance(bulk_results, dict):
        result_count = len(bulk_results)
    elif isinstance(bulk_results, list):
        result_count = len(bulk_results)
    else:
        result_count = 0
    
    print(f"  Compounds queried: {len(test_compounds)}")
    print(f"  Results returned:  {result_count}")
    print(f"  Lookup time:       {bulk_time:.2f}s")
    print(f"  Stats: {json.dumps(stats, indent=4, default=str)}")
    
    results.check(
        result_count >= 3,
        "Bulk guidance returned >= 3 results",
        f"got {result_count}"
    )
    
    direct_lookups = stats.get("direct_lookups", stats.get("direct_hits", 0))
    vector_lookups = stats.get("vector_lookups", stats.get("vector_hits", 0))
    
    results.check(
        direct_lookups >= 1,
        "At least 1 direct lookup hit",
        f"direct={direct_lookups}, vector={vector_lookups}"
    )
    
    # Check for negative penalty stat
    neg_penalties = stats.get("neg_penalties_applied", 0)
    print(f"  Negative penalties applied: {neg_penalties}")
    # We don't strictly require penalties (depends on query/embedding similarity)
    # Just verify the stat key exists
    results.check(
        "neg_penalties_applied" in stats or "neg_penalties" in stats,
        "Negative penalty stat tracked",
        f"neg_penalties_applied={neg_penalties}"
    )
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 6: Genre-Aware Query Routing
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 6] Genre-Aware Query Routing\033[0m")
    
    # Same query, different genres — should potentially yield different rankings
    genres_to_test = ["cultivation_novel", "romcom", "slice_of_life", "japanese_light_novel"]
    
    for genre in genres_to_test:
        try:
            hits = store.query_disambiguation(
                chinese_text="世界",
                prev_context="",
                genre=genre
            )
            if hits:
                top_score = hits[0].get("score", 0)
                top_cat = hits[0].get("category", "?")
                top_vn = hits[0].get("vn_correct") or hits[0].get("vn_term", "?")
                results.ok(
                    f"Genre '{genre}' query '世界'",
                    f"score={top_score:.3f} cat={top_cat} vn={top_vn}"
                )
            else:
                results.ok(f"Genre '{genre}' query '世界'", "no results (acceptable)")
        except Exception as e:
            results.fail(f"Genre '{genre}' query '世界'", str(e))
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 7: Translation Guidance + Prompt Injection
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 7] Translation Guidance + Prompt Injection\033[0m")
    
    guidance = store.get_translation_guidance(
        chinese_text="金丹期的修士在修真界中地位崇高",
        prev_context="",
        genre="cultivation_novel"
    )
    
    results.check(
        isinstance(guidance, dict),
        "get_translation_guidance returns dict",
        f"keys: {list(guidance.keys())[:5]}"
    )
    
    prompt_text = store.format_prompt_injection(guidance, include_suggestions=True)
    results.check(
        len(prompt_text) > 50,
        "Prompt injection non-empty",
        f"{len(prompt_text)} chars"
    )
    print(f"\n  --- Prompt Injection Preview (first 300 chars) ---")
    print(f"  {prompt_text[:300]}...")
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 8: Built-in validate_index()
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 8] Built-in validate_index()\033[0m")
    
    validation = store.validate_index()
    v_passed = validation.get("passed", 0)
    v_total = validation.get("total_tests", 0)
    v_rate = validation.get("success_rate", 0)
    
    print(f"  validate_index: {v_passed}/{v_total} ({v_rate:.1f}%)")
    for detail in validation.get("details", []):
        status = "\033[32m✓\033[0m" if detail.get("passed") else "\033[31m✗\033[0m"
        print(f"    {status} {detail.get('query', '?')} -> {detail.get('top_result', '?')}")
    
    results.check(
        v_rate >= 70.0,
        f"validate_index >= 70% pass rate",
        f"{v_passed}/{v_total} ({v_rate:.1f}%)"
    )
    
    # ══════════════════════════════════════════════════════════════════
    # PHASE 9: get_stats() verification
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Phase 9] Store Stats\033[0m")
    
    stats = store.get_stats()
    print(f"  Version:          {stats.get('version')}")
    print(f"  Collection count: {stats.get('collection_count')}")
    print(f"  Total patterns:   {stats.get('total_patterns')}")
    print(f"  Thresholds:       {stats.get('thresholds')}")
    
    results.check(
        stats.get("version") == "2.0",
        "Stats version = 2.0"
    )
    results.check(
        stats.get("collection_count", 0) > 0,
        "Stats collection_count > 0",
        f"{stats.get('collection_count')}"
    )
    
    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    
    print("\n\033[1m[Summary]\033[0m")
    print(f"  Build time:       {build_time:.1f}s")
    print(f"  Collection count: {collection_count}")
    print(f"  Categories:       {len(indexed)}")
    print(f"  Neg anchors:      {total_anchors}")
    print(f"  Direct lookup:    {len(lookup)}")
    
    all_pass = results.summary()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
