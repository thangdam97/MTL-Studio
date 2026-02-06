#!/usr/bin/env python3
"""
Test Sino-Vietnamese Vector Search Embeddings

This script tests the Sino-Vietnamese vector search system to ensure:
1. Embeddings are generated correctly
2. Similarity search returns relevant results
3. Disambiguation works for common problematic terms
4. Register filtering works correctly

Usage:
    python scripts/test_sino_vn_embeddings.py
    python scripts/test_sino_vn_embeddings.py --verbose
    python scripts/test_sino_vn_embeddings.py --interactive
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))

from modules.sino_vietnamese_store import SinoVietnameseStore


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


class SinoVietnameseTestSuite:
    """Test suite for Sino-Vietnamese vector search."""
    
    def __init__(self, store: SinoVietnameseStore):
        self.store = store
        self.results = {
            "passed": 0,
            "failed": 0,
            "tests": []
        }
    
    def run_test(
        self,
        name: str,
        query: str,
        expected_vn: str,
        unexpected_vn: str = "",
        prev_context: str = "",
        genre: str = "cultivation_novel"
    ) -> bool:
        """Run a single test case."""
        print(f"\n📝 Test: {name}")
        print(f"   Query: {query}")
        
        results = self.store.query_disambiguation(
            chinese_text=query,
            prev_context=prev_context,
            genre=genre,
            top_k=3
        )
        
        if not results:
            print(f"   ❌ FAIL: No results returned")
            self.results["failed"] += 1
            self.results["tests"].append({
                "name": name,
                "passed": False,
                "reason": "No results"
            })
            return False
        
        top_result = results[0]
        vn_correct = top_result.get("vn_correct", "") or top_result.get("vn_term", "")
        score = top_result.get("score", 0)
        
        print(f"   Result: {vn_correct} (score: {score:.4f})")
        
        # Check if expected translation is found
        passed = expected_vn.lower() in vn_correct.lower()
        
        # Check that unexpected translation is NOT in result
        if unexpected_vn and unexpected_vn.lower() in vn_correct.lower():
            passed = False
            print(f"   ⚠️ Found unexpected: {unexpected_vn}")
        
        if passed:
            print(f"   ✅ PASS")
            self.results["passed"] += 1
        else:
            print(f"   ❌ FAIL: Expected '{expected_vn}' in result")
            self.results["failed"] += 1
        
        self.results["tests"].append({
            "name": name,
            "passed": passed,
            "query": query,
            "expected": expected_vn,
            "got": vn_correct,
            "score": score
        })
        
        return passed
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all test cases."""
        
        print("\n" + "=" * 60)
        print("SINO-VIETNAMESE DISAMBIGUATION TESTS")
        print("=" * 60)
        
        # ============================================================
        # Category 1: Core Sino-Vietnamese Disambiguation
        # ============================================================
        print("\n" + "-" * 40)
        print("Category 1: Core Disambiguation")
        print("-" * 40)
        
        # 道 disambiguation
        self.run_test(
            name="道 as spiritual path",
            query="修道之人",
            expected_vn="tu đạo",
            unexpected_vn="sửa đường"
        )
        
        self.run_test(
            name="道 as Daoist temple",
            query="道观",
            expected_vn="đạo quán",
            unexpected_vn="quán đường"
        )
        
        # 修 disambiguation
        self.run_test(
            name="修 as cultivation",
            query="修真",
            expected_vn="tu chân",
            unexpected_vn="sửa chữa"
        )
        
        self.run_test(
            name="修炼 cultivation practice",
            query="修炼",
            expected_vn="tu luyện",
            unexpected_vn="sửa luyện"
        )
        
        # 气 disambiguation
        self.run_test(
            name="灵气 spiritual energy",
            query="灵气",
            expected_vn="linh khí",
            unexpected_vn="không khí"
        )
        
        self.run_test(
            name="真气 true qi",
            query="真气",
            expected_vn="chân khí"
        )
        
        # ============================================================
        # Category 2: Cultivation Realms (Proper Nouns)
        # ============================================================
        print("\n" + "-" * 40)
        print("Category 2: Cultivation Realms")
        print("-" * 40)
        
        self.run_test(
            name="筑基 Foundation Establishment",
            query="筑基期",
            expected_vn="Trúc Cơ",
            unexpected_vn="xây dựng"
        )
        
        self.run_test(
            name="金丹 Golden Core",
            query="金丹期",
            expected_vn="Kim Đan",
            unexpected_vn="viên thuốc"
        )
        
        self.run_test(
            name="元婴 Nascent Soul",
            query="元婴期",
            expected_vn="Nguyên Anh",
            unexpected_vn="em bé"
        )
        
        self.run_test(
            name="渡劫 Tribulation",
            query="渡劫期",
            expected_vn="Độ Kiếp",
            unexpected_vn="vượt cướp"
        )
        
        # ============================================================
        # Category 3: Titles and Honorifics
        # ============================================================
        print("\n" + "-" * 40)
        print("Category 3: Titles and Honorifics")
        print("-" * 40)
        
        self.run_test(
            name="师父 Master",
            query="师父",
            expected_vn="sư phụ",
            unexpected_vn="thầy cha"
        )
        
        self.run_test(
            name="前辈 Senior",
            query="前辈请",
            expected_vn="tiền bối"
        )
        
        self.run_test(
            name="道友 Fellow Daoist",
            query="道友可好",
            expected_vn="đạo hữu",
            unexpected_vn="bạn đi đường"
        )
        
        # ============================================================
        # Category 4: Cultivation Techniques
        # ============================================================
        print("\n" + "-" * 40)
        print("Category 4: Cultivation Techniques")
        print("-" * 40)
        
        self.run_test(
            name="功法 Cultivation technique",
            query="修炼功法",
            expected_vn="công pháp"
        )
        
        self.run_test(
            name="剑法 Sword technique",
            query="剑法",
            expected_vn="kiếm pháp"
        )
        
        self.run_test(
            name="飞剑 Flying sword",
            query="飞剑",
            expected_vn="phi kiếm"
        )
        
        # ============================================================
        # Category 5: Context-Dependent Terms
        # ============================================================
        print("\n" + "-" * 40)
        print("Category 5: Context-Dependent")
        print("-" * 40)
        
        self.run_test(
            name="灵 in spiritual context",
            query="灵石",
            expected_vn="linh thạch",
            prev_context="修炼需要"
        )
        
        self.run_test(
            name="门 as sect",
            query="门派",
            expected_vn="môn phái",
            unexpected_vn="cửa"
        )
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        total = self.results["passed"] + self.results["failed"]
        success_rate = (self.results["passed"] / total * 100) if total > 0 else 0
        
        print(f"\n✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"📊 Success Rate: {success_rate:.1f}%")
        
        if self.results["failed"] > 0:
            print("\n📋 Failed Tests:")
            for test in self.results["tests"]:
                if not test["passed"]:
                    print(f"   - {test['name']}")
                    print(f"     Query: {test.get('query', 'N/A')}")
                    print(f"     Expected: {test.get('expected', 'N/A')}")
                    print(f"     Got: {test.get('got', 'N/A')}")
        
        return self.results


def interactive_mode(store: SinoVietnameseStore):
    """Run interactive query mode."""
    print("\n" + "=" * 60)
    print("INTERACTIVE QUERY MODE")
    print("=" * 60)
    print("Enter Chinese text to query, or 'quit' to exit.")
    print("Format: <query> [| <prev_context>]")
    print()
    
    while True:
        try:
            user_input = input("🔍 Query: ").strip()
            
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Parse input
            parts = user_input.split("|")
            query = parts[0].strip()
            prev_context = parts[1].strip() if len(parts) > 1 else ""
            
            # Run query
            results = store.query_disambiguation(
                chinese_text=query,
                prev_context=prev_context,
                top_k=5
            )
            
            if not results:
                print("   No results found.\n")
                continue
            
            print(f"\n📊 Results for: {query}")
            if prev_context:
                print(f"   Context: {prev_context}")
            print()
            
            for i, r in enumerate(results, 1):
                vn = r.get("vn_correct") or r.get("vn_term", "")
                wrong = r.get("vn_wrong", "")
                score = r.get("score", 0)
                meaning = r.get("meaning", "")
                
                print(f"   {i}. {r['hanzi']} → {vn} (score: {score:.4f})")
                if wrong:
                    print(f"      ⚠️ Avoid: {wrong}")
                if meaning:
                    print(f"      📝 Meaning: {meaning}")
            
            # Show prompt injection
            guidance = store.get_translation_guidance(query, prev_context)
            if guidance["inject"]:
                print("\n   📋 Prompt injection:")
                injection = store.format_prompt_injection(guidance)
                for line in injection.split("\n")[:10]:
                    print(f"      {line}")
            
            print()
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"   Error: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test Sino-Vietnamese vector search system"
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default="./pipeline/chroma_sino_vn",
        help="Directory for ChromaDB persistence"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive query mode"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    # Initialize store
    print("⏳ Initializing Sino-Vietnamese store...")
    
    try:
        store = SinoVietnameseStore(persist_directory=args.persist_dir)
        
        # Check if index exists, build if not
        stats = store.get_stats()
        if stats["total_patterns"] == 0:
            print("⏳ No index found, building from RAG file...")
            store.build_index()
            stats = store.get_stats()  # Refresh stats after build
        
        print(f"✅ Store ready with {stats['total_patterns']} patterns")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("   Run build_sino_vn_index.py first to create the index.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing store: {e}")
        sys.exit(1)
    
    if args.interactive:
        interactive_mode(store)
    else:
        # Run test suite
        suite = SinoVietnameseTestSuite(store)
        results = suite.run_all_tests()
        
        if args.json:
            print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
        
        # Exit with error code if tests failed
        if results["failed"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
