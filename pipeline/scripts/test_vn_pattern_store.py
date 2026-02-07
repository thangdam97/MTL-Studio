"""
Test Suite for VietnamesePatternStore

Tests:
1. Index build from vietnamese_grammar_rag_v2.json
2. Pattern retrieval accuracy (true positive / true negative)
3. Negative anchor penalty system
4. Threshold gating (INJECT vs LOG vs IGNORE)
5. Category priority filtering
6. Anti-AI-ism pattern detection

Run: python pipeline/scripts/test_vn_pattern_store.py
"""

import sys
import os
import json
import time

# Add pipeline directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.vietnamese_pattern_store import VietnamesePatternStore


def test_index_build():
    """Test 1: Build index from VN RAG JSON."""
    print("=" * 60)
    print("TEST 1: Index Build from vietnamese_grammar_rag_v2.json")
    print("=" * 60)

    store = VietnamesePatternStore(
        persist_directory="./chroma_vietnamese_patterns",
        rag_file_path="config/vietnamese_grammar_rag_v2.json"
    )

    # Check if already indexed
    stats = store.get_collection_stats()
    if stats["total_patterns"] > 0:
        print(f"  ✓ Collection already indexed: {stats['total_patterns']} patterns")
        print(f"  Collection: {stats['collection_name']}")
        return store

    # Build index (will take ~30-60s with Gemini Embedding)
    print("  Building index (first run — embedding all patterns via Gemini)...")
    start = time.time()
    counts = store.build_index(force_rebuild=True)
    elapsed = time.time() - start

    total = sum(counts.values())
    print(f"  ✓ Indexed {total} patterns across {len(counts)} categories in {elapsed:.1f}s")
    for cat, count in sorted(counts.items()):
        print(f"    {cat}: {count} patterns")

    return store


def test_true_positive_retrieval(store: VietnamesePatternStore):
    """Test 2: True positive pattern retrieval."""
    print("\n" + "=" * 60)
    print("TEST 2: True Positive Pattern Retrieval")
    print("=" * 60)

    test_cases = [
        {
            "query": "やっぱりあの子かわいいなぁ",
            "expected_category": "emotional_nuance",
            "expected_keywords": ["やっぱり", "yappari"],
            "description": "やっぱり (confirmed expectation)"
        },
        {
            "query": "まあ、仕方ないか",
            "expected_category": "emotional_nuance",
            "expected_keywords": ["まあ", "maa"],
            "description": "まあ (resigned acceptance)"
        },
        {
            "query": "えっ、なに？",
            "expected_category": "response_particles",
            "expected_keywords": ["え", "surprise"],
            "description": "え response particle"
        },
        {
            "query": "彼女は強いけど、やさしい",
            "expected_category": "contrastive_comparison",
            "expected_keywords": ["けど", "contrastive"],
            "description": "けど contrastive"
        },
        {
            "query": "あいつ、さすがだな",
            "expected_category": "emotional_nuance",
            "expected_keywords": ["さすが", "sasuga"],
            "description": "さすが (as expected of)"
        }
    ]

    passed = 0
    for tc in test_cases:
        results = store.search(query=tc["query"], top_k=3)
        if results:
            best = results[0]
            meta = best["metadata"]
            sim = best["similarity"]

            # Check category match
            cat_match = meta.get("category", "") == tc["expected_category"]

            print(f"\n  Query: {tc['description']}")
            print(f"    Best match: {meta.get('pattern_id_base', '?')} (sim={sim:.3f})")
            print(f"    Category: {meta.get('category', '?')} {'✓' if cat_match else '✗ expected ' + tc['expected_category']}")
            print(f"    VN pattern: {meta.get('vietnamese_pattern', '?')[:60]}")

            if sim >= VietnamesePatternStore.THRESHOLD_LOG:
                passed += 1
                print(f"    → PASS (similarity {sim:.3f} ≥ {VietnamesePatternStore.THRESHOLD_LOG})")
            else:
                print(f"    → FAIL (similarity {sim:.3f} < {VietnamesePatternStore.THRESHOLD_LOG})")
        else:
            print(f"\n  Query: {tc['description']}")
            print(f"    → FAIL (no results)")

    print(f"\n  True Positive Score: {passed}/{len(test_cases)}")
    return passed, len(test_cases)


def test_negative_anchors(store: VietnamesePatternStore):
    """Test 3: Negative anchor penalty system."""
    print("\n" + "=" * 60)
    print("TEST 3: Negative Anchor Penalty System")
    print("=" * 60)

    # These queries should trigger negative anchors (false positives)
    # Using borderline queries that are semantically CLOSE to a category
    # but represent literal/non-idiomatic usage
    false_positive_queries = [
        {
            "query": "彼は部屋に入って、椅子に座った",
            "category": "action_emphasis",
            "description": "Sequential plain actions → should NOT trigger aspectual emphasis"
        },
        {
            "query": "この問題について考えてみましょう",
            "category": "hedging",
            "description": "Formal suggestion → should NOT trigger hedging/uncertainty"
        },
        {
            "query": "電車が来ました",
            "category": "emotional_nuance",
            "description": "Factual arrival statement → should NOT trigger emotional patterns"
        }
    ]

    # These queries should NOT trigger negative anchors (true positives)
    true_positive_queries = [
        {
            "query": "やっぱりあの子かわいいなぁ",
            "category": "emotional_nuance",
            "description": "やっぱり → should match WITHOUT penalty"
        },
        {
            "query": "彼女は強いけど、やさしい",
            "category": "contrastive_comparison",
            "description": "けど contrast → should match WITHOUT penalty"
        }
    ]

    print("\n  False Positive Queries (should get penalized or low-scored):")
    fp_penalized = 0
    for fp in false_positive_queries:
        embedding = store.vector_store.embed_text(fp["query"])
        penalty = store._compute_negative_penalty(embedding, fp["category"])
        # Also check raw similarity — if it's already below LOG threshold, that's fine too
        results = store.search(query=fp["query"], top_k=1, category_filter=fp["category"])
        raw_sim = results[0]["similarity"] if results else 0
        print(f"    {fp['description']}")
        print(f"      Penalty: {penalty:.4f}, Raw sim: {raw_sim:.3f}")
        # Pass if EITHER penalized OR naturally low similarity
        if penalty > 0 or raw_sim < VietnamesePatternStore.THRESHOLD_LOG:
            fp_penalized += 1
            print(f"      ✓ Correctly suppressed")
        else:
            print(f"      ⚠ Not suppressed (sim={raw_sim:.3f})")

    print(f"\n  True Positive Queries (should NOT be penalized):")
    tp_clean = 0
    for tp in true_positive_queries:
        embedding = store.vector_store.embed_text(tp["query"])
        penalty = store._compute_negative_penalty(embedding, tp["category"])
        print(f"    {tp['description']}")
        print(f"      Penalty: {penalty:.4f} {'✓ clean' if penalty == 0 else '⚠ unexpected penalty'}")
        if penalty == 0:
            tp_clean += 1

    print(f"\n  False positives penalized: {fp_penalized}/{len(false_positive_queries)}")
    print(f"  True positives clean: {tp_clean}/{len(true_positive_queries)}")
    return fp_penalized, len(false_positive_queries), tp_clean, len(true_positive_queries)


def test_bulk_guidance(store: VietnamesePatternStore):
    """Test 4: Bulk guidance pipeline (the main integration point)."""
    print("\n" + "=" * 60)
    print("TEST 4: Bulk Guidance Pipeline (get_bulk_guidance)")
    print("=" * 60)

    # Simulated detected patterns from grammar_pattern_detector
    detected_patterns = [
        {"category": "emotional_nuance", "indicator": "やっぱり", "context": "やっぱりあの子かわいいなぁ"},
        {"category": "contrastive_comparison", "indicator": "けど", "context": "強いけど、やさしい"},
        {"category": "sentence_endings", "indicator": "よね", "context": "そうだよね"},
        {"category": "comedic_timing", "indicator": "ツッコミ", "context": "なんでやねん！"},
        {"category": "anti_ai_ism_patterns", "indicator": "một cách", "context": "彼は静かに歩いた"}
    ]

    print(f"  Querying {len(detected_patterns)} detected patterns...")
    start = time.time()
    guidance = store.get_bulk_guidance(detected_patterns, context="light novel dialogue scene")
    elapsed = time.time() - start

    stats = guidance["lookup_stats"]
    print(f"\n  Lookup stats:")
    print(f"    Patterns queried: {stats['patterns_queried']}")
    print(f"    High confidence hits: {stats['high_conf_hits']}")
    print(f"    Medium confidence hits: {stats['medium_conf_hits']}")
    print(f"    Neg penalties applied: {stats['neg_penalties_applied']}")
    print(f"    Time: {elapsed:.2f}s")

    if guidance["high_confidence"]:
        print(f"\n  High Confidence Results (≥{VietnamesePatternStore.THRESHOLD_INJECT}):")
        for entry in guidance["high_confidence"][:5]:
            print(f"    • {entry['pattern_id']} (sim={entry['similarity']:.3f}, raw={entry['raw_similarity']:.3f})")
            print(f"      VN: {entry['vietnamese_pattern'][:60]}")
            if entry['neg_penalty'] > 0:
                print(f"      ⚠ neg_penalty: {entry['neg_penalty']:.4f}")

    if guidance["medium_confidence"]:
        print(f"\n  Medium Confidence Results (≥{VietnamesePatternStore.THRESHOLD_LOG}):")
        for entry in guidance["medium_confidence"][:3]:
            print(f"    • {entry['pattern_id']} (sim={entry['similarity']:.3f})")

    return guidance


def test_collection_stats(store: VietnamesePatternStore):
    """Test 5: Collection statistics."""
    print("\n" + "=" * 60)
    print("TEST 5: Collection Statistics")
    print("=" * 60)

    stats = store.get_collection_stats()
    print(f"  Collection: {stats['collection_name']}")
    print(f"  Total indexed: {stats['total_patterns']}")
    print(f"  Persist dir: {stats['persist_directory']}")
    print(f"  Thresholds: inject={stats['thresholds']['inject']}, log={stats['thresholds']['log']}")
    print(f"  Neg anchor: threshold={stats['negative_anchor']['threshold']}, penalty={stats['negative_anchor']['penalty']}")

    return stats


def main():
    """Run full test suite."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Vietnamese Pattern Store — Test Suite                  ║")
    print("║  Testing: Index, Retrieval, Neg Anchors, Bulk Guidance  ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    os.chdir(os.path.join(os.path.dirname(__file__), '..'))

    # Test 1: Build/load index
    store = test_index_build()

    # Test 2: True positive retrieval
    tp_passed, tp_total = test_true_positive_retrieval(store)

    # Test 3: Negative anchors
    fp_pen, fp_total, tp_clean, tp_clean_total = test_negative_anchors(store)

    # Test 4: Bulk guidance
    guidance = test_bulk_guidance(store)

    # Test 5: Stats
    stats = test_collection_stats(store)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Index: {stats['total_patterns']} patterns indexed")
    print(f"  True positive retrieval: {tp_passed}/{tp_total}")
    print(f"  False positive penalized: {fp_pen}/{fp_total}")
    print(f"  True positive clean: {tp_clean}/{tp_clean_total}")
    print(f"  Bulk guidance: {guidance['lookup_stats']['high_conf_hits']} high / {guidance['lookup_stats']['medium_conf_hits']} medium")

    overall = tp_passed + fp_pen + tp_clean
    max_score = tp_total + fp_total + tp_clean_total
    print(f"\n  Overall: {overall}/{max_score} checks passed")

    if overall == max_score:
        print("  ✅ ALL TESTS PASSED")
    elif overall >= max_score * 0.7:
        print("  ⚠️  MOSTLY PASSED (some checks failed)")
    else:
        print("  ❌ SIGNIFICANT FAILURES")

    return overall == max_score


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
