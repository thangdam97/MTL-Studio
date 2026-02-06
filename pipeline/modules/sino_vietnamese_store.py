"""
Sino-Vietnamese Vector Store Module
Specialized wrapper for Vietnamese translation disambiguation

This module provides:
1. Pre-built index for Sino-Vietnamese patterns
2. Register-aware pattern retrieval
3. Cultivation-specific terminology handling
4. False cognate detection and correction
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from modules.vector_search import PatternVectorStore
from modules.pinyin_helper import enhance_query_with_pinyin, enhance_document_with_pinyin, get_pinyin

logger = logging.getLogger(__name__)


class SinoVietnameseStore:
    """
    Specialized vector store for Sino-Vietnamese disambiguation.
    
    Wraps PatternVectorStore with Vietnamese-specific:
    - Category filtering (sino_disambiguation, cultivation_realms, etc.)
    - Register awareness (formal/casual/literary)
    - False cognate warnings
    - Cultivation terminology prioritization
    """
    
    # Vietnamese-specific thresholds (stricter than generic)
    THRESHOLD_INJECT = 0.85  # Higher threshold for Vietnamese due to tone complexity
    THRESHOLD_LOG = 0.70
    
    # Category priorities (higher = more important)
    CATEGORY_PRIORITIES = {
        "cultivation_realms": 10,      # Proper nouns, must be correct
        "titles_honorifics": 9,        # Formal titles
        "sino_disambiguation": 8,      # Core disambiguation
        "cultivation_techniques": 7,   # Technique names
        "false_cognates": 6            # Warning patterns
    }
    
    def __init__(
        self,
        persist_directory: str = "./chroma_sino_vn",
        api_key: Optional[str] = None,
        rag_file_path: Optional[str] = None
    ):
        """
        Initialize Sino-Vietnamese store.
        
        Args:
            persist_directory: ChromaDB storage location
            api_key: Gemini API key (uses GOOGLE_API_KEY env var if not provided)
            rag_file_path: Path to sino_vietnamese_rag.json
        """
        self.persist_directory = persist_directory
        self.api_key = api_key
        
        # Default RAG file location
        if rag_file_path is None:
            self.rag_file_path = Path(__file__).parent.parent / "config" / "sino_vietnamese_rag.json"
        else:
            self.rag_file_path = Path(rag_file_path)
        
        # Initialize core vector store with Vietnamese-specific collection
        self.vector_store = PatternVectorStore(
            collection_name="sino_vietnamese_patterns",
            persist_directory=persist_directory,
            gemini_api_key=api_key
        )
        
        # Cache for loaded RAG data
        self._rag_cache: Optional[Dict] = None
        
        # Index statistics
        self._stats = {
            "total_patterns": 0,
            "by_category": {},
            "by_register": {}
        }
        
        logger.info(f"SinoVietnameseStore initialized with persist_directory={persist_directory}")
    
    def load_rag_data(self) -> Dict:
        """
        Load and cache RAG data from JSON file.
        
        Returns:
            Parsed RAG dictionary
        """
        if self._rag_cache is not None:
            return self._rag_cache
        
        if not self.rag_file_path.exists():
            raise FileNotFoundError(f"RAG file not found: {self.rag_file_path}")
        
        with open(self.rag_file_path, 'r', encoding='utf-8') as f:
            self._rag_cache = json.load(f)
        
        logger.info(f"Loaded RAG data from {self.rag_file_path}")
        return self._rag_cache
    
    def build_index(self, force_rebuild: bool = False) -> Dict[str, int]:
        """
        Build vector index from sino_vietnamese_rag.json.
        
        This extracts patterns from all categories and indexes them
        with appropriate metadata for Vietnamese disambiguation.
        
        Args:
            force_rebuild: If True, clears existing index first
            
        Returns:
            Dictionary of indexed counts by category
        """
        if force_rebuild:
            logger.warning("Force rebuilding index - clearing existing data")
            # Note: Would need to implement clear() in PatternVectorStore
        
        rag_data = self.load_rag_data()
        pattern_categories = rag_data.get("pattern_categories", {})
        
        indexed_counts = {}
        total_indexed = 0
        
        for category_name, category_data in pattern_categories.items():
            patterns = category_data.get("patterns", [])
            category_description = category_data.get("description", "")
            
            logger.info(f"Indexing category: {category_name} ({len(patterns)} patterns)")
            print(f"  → {category_name}: {len(patterns)} patterns")
            
            for i, pattern in enumerate(patterns):
                if (i + 1) % 50 == 0:
                    print(f"    Progress: {i + 1}/{len(patterns)}")
                indexed = self._index_pattern(pattern, category_name, category_description)
                total_indexed += indexed
            
            indexed_counts[category_name] = len(patterns)
            print(f"    ✓ Completed {category_name}")
        
        # Update stats
        self._stats["total_patterns"] = total_indexed
        self._stats["by_category"] = indexed_counts
        
        logger.info(f"Index build complete: {total_indexed} total patterns indexed")
        return indexed_counts
    
    def _index_pattern(
        self,
        pattern: Dict,
        category: str,
        category_description: str
    ) -> int:
        """
        Index a single pattern with all its contexts and examples.
        
        Returns count of indexed items.
        """
        indexed_count = 0
        
        hanzi = pattern.get("hanzi", "")
        pattern_id = pattern.get("id", hanzi)
        
        # Handle patterns with contexts (sino_disambiguation)
        if "contexts" in pattern:
            for ctx_idx, context in enumerate(pattern["contexts"]):
                for ex_idx, example in enumerate(context.get("examples", [])):
                    # Build searchable text with pinyin for better embedding distinction
                    # Gemini text-embedding-004 has trouble distinguishing short Chinese text
                    # Adding pinyin romanization helps create unique embeddings
                    zh_text = example.get("zh", "")
                    meaning = context.get("meaning", "")
                    vn_correct = example.get("vn_correct", "")
                    pinyin = get_pinyin(zh_text)
                    
                    # Format: "修真 xiuzhen - tu chân (cultivation practice)"
                    search_text = enhance_document_with_pinyin(
                        chinese_text=zh_text,
                        vietnamese_text=vn_correct,
                        meaning=meaning.replace("_", " ")
                    )
                    
                    # Rich metadata
                    metadata = {
                        "pattern_id": pattern_id,
                        "category": category,
                        "hanzi": hanzi,
                        "pinyin": pinyin,
                        "meaning": meaning,
                        "register": context.get("register", "neutral"),
                        "vn_correct": example.get("vn_correct", ""),
                        "vn_wrong": example.get("vn_wrong", ""),
                        "vn_translation": context.get("vn_translation", ""),
                        "vn_phrases": json.dumps(context.get("vn_phrases", []), ensure_ascii=False),
                        "avoid": json.dumps(context.get("avoid", []), ensure_ascii=False),
                        "zh_indicators": json.dumps(context.get("zh_indicators", []), ensure_ascii=False),
                        "sino_vietnamese": str(pattern.get("sino_vietnamese", True)),
                        "example_context": example.get("context", "general"),
                        "priority": str(self.CATEGORY_PRIORITIES.get(category, 5)),
                        "source_file": str(self.rag_file_path.name)
                    }
                    
                    # Add note if present
                    if "note" in example:
                        metadata["note"] = example["note"]
                    
                    # Generate unique ID
                    doc_id = f"{pattern_id}_{ctx_idx}_{ex_idx}"
                    
                    self.vector_store.add_pattern(
                        text=search_text,
                        metadata=metadata,
                        pattern_id=doc_id
                    )
                    indexed_count += 1
        
        # Handle patterns without contexts (cultivation_realms, techniques, honorifics)
        elif "examples" in pattern:
            for ex_idx, example in enumerate(pattern.get("examples", [])):
                zh_text = example.get("zh", "")
                vn_term = pattern.get("vn_term", "")
                vn_correct = example.get("vn_correct", "")
                explanation = pattern.get("explanation", "")
                pinyin = get_pinyin(zh_text)
                
                # Format: "金丹期 jindanqi - Kim Đan kỳ (Golden Core period)"
                search_text = enhance_document_with_pinyin(
                    chinese_text=zh_text,
                    vietnamese_text=vn_correct or vn_term,
                    meaning=explanation
                )
                
                metadata = {
                    "pattern_id": pattern_id,
                    "category": category,
                    "hanzi": hanzi,
                    "pinyin": pinyin,
                    "vn_term": pattern.get("vn_term", ""),
                    "literal_wrong": pattern.get("literal_wrong", ""),
                    "register": pattern.get("register", "formal"),
                    "vn_correct": example.get("vn_correct", ""),
                    "vn_wrong": example.get("vn_wrong", ""),
                    "explanation": pattern.get("explanation", ""),
                    "sino_vietnamese": str(pattern.get("sino_vietnamese", True)),
                    "example_context": example.get("context", "cultivation_novel"),
                    "priority": str(self.CATEGORY_PRIORITIES.get(category, 5)),
                    "source_file": str(self.rag_file_path.name)
                }
                
                doc_id = f"{pattern_id}_{ex_idx}"
                
                self.vector_store.add_pattern(
                    text=search_text,
                    metadata=metadata,
                    pattern_id=doc_id
                )
                indexed_count += 1
        
        # Handle simple patterns (no contexts/examples)
        else:
            pinyin = get_pinyin(hanzi)
            vn_term = pattern.get('vn_term', '')
            search_text = enhance_document_with_pinyin(
                chinese_text=hanzi,
                vietnamese_text=vn_term,
                meaning=""
            )
            
            metadata = {
                "pattern_id": pattern_id,
                "category": category,
                "hanzi": hanzi,
                "vn_term": pattern.get("vn_term", ""),
                "register": pattern.get("register", "neutral"),
                "sino_vietnamese": str(pattern.get("sino_vietnamese", True)),
                "priority": str(self.CATEGORY_PRIORITIES.get(category, 5)),
                "source_file": str(self.rag_file_path.name)
            }
            
            self.vector_store.add_pattern(
                text=search_text,
                metadata=metadata,
                pattern_id=pattern_id
            )
            indexed_count += 1
        
        return indexed_count
    
    def query_disambiguation(
        self,
        chinese_text: str,
        prev_context: str = "",
        next_context: str = "",
        register: Optional[str] = None,
        genre: str = "cultivation_novel",
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query for Sino-Vietnamese disambiguation patterns.
        
        This is the main entry point for Vietnamese translation assistance.
        
        Args:
            chinese_text: The Chinese text to translate
            prev_context: Previous sentence(s) for context
            next_context: Following sentence(s) for context
            register: Optional register filter (formal/casual/literary)
            genre: Genre context for filtering
            top_k: Maximum results to return
            
        Returns:
            List of relevant patterns with confidence scores
        """
        # Build domain hint based on genre for better embedding disambiguation
        domain_hints = {
            "cultivation_novel": "Chinese cultivation novel Sino-Vietnamese translation",
            "wuxia": "Chinese martial arts wuxia novel Vietnamese translation",
            "xianxia": "Chinese immortal cultivation xianxia Sino-Vietnamese translation",
            "general": "Chinese to Vietnamese Sino-Vietnamese translation"
        }
        domain_hint = domain_hints.get(genre, domain_hints["general"])
        
        # Use sliding window context embedding
        results = self.vector_store.search_with_context(
            current=chinese_text,
            prev=prev_context,
            next_sent=next_context,
            register_filter=register,
            top_k=top_k * 2,  # Get more results to filter
            domain_hint=domain_hint
        )
        
        # Post-process and filter results
        processed_results = []
        
        for result in results:
            score = result.get("similarity", 0)
            metadata = result.get("metadata", {})
            
            # Check if genre matches
            example_context = metadata.get("example_context", "")
            if genre and example_context not in ["general", genre]:
                # Reduce score for genre mismatch
                score *= 0.85
            
            # Boost score for high-priority categories
            priority = int(metadata.get("priority", 5))
            score *= (1 + (priority - 5) * 0.02)  # ±2% per priority level
            
            processed_results.append({
                "score": score,
                "pattern_id": metadata.get("pattern_id", ""),
                "hanzi": metadata.get("hanzi", ""),
                "vn_correct": metadata.get("vn_correct", ""),
                "vn_wrong": metadata.get("vn_wrong", ""),
                "vn_term": metadata.get("vn_term", ""),
                "meaning": metadata.get("meaning", ""),
                "register": metadata.get("register", "neutral"),
                "explanation": metadata.get("explanation", ""),
                "category": metadata.get("category", ""),
                "avoid": metadata.get("avoid", "[]"),
                "vn_phrases": metadata.get("vn_phrases", "[]"),
                "note": metadata.get("note", ""),
                "raw_metadata": metadata
            })
        
        # Sort by score and limit
        processed_results.sort(key=lambda x: x["score"], reverse=True)
        return processed_results[:top_k]
    
    def get_translation_guidance(
        self,
        chinese_text: str,
        prev_context: str = "",
        genre: str = "cultivation_novel"
    ) -> Dict[str, Any]:
        """
        Get formatted translation guidance for injection into prompts.
        
        This method returns structured guidance suitable for LLM prompts.
        
        Args:
            chinese_text: Source text to translate
            prev_context: Previous context
            genre: Genre for filtering
            
        Returns:
            Dictionary with 'inject' (high confidence), 'suggestions' (medium),
            and 'warnings' (false cognates)
        """
        results = self.query_disambiguation(
            chinese_text=chinese_text,
            prev_context=prev_context,
            genre=genre,
            top_k=10
        )
        
        guidance = {
            "inject": [],      # High confidence - include in prompt
            "suggestions": [], # Medium confidence - show as suggestions
            "warnings": [],    # False cognates to warn about
            "metadata": {
                "query_text": chinese_text,
                "genre": genre,
                "total_matches": len(results)
            }
        }
        
        for result in results:
            score = result["score"]
            
            # Build guidance item
            item = {
                "hanzi": result["hanzi"],
                "vn_correct": result["vn_correct"] or result["vn_term"],
                "vn_avoid": result["vn_wrong"],
                "meaning": result["meaning"],
                "score": round(score, 4)
            }
            
            # Add explanation if available
            if result["explanation"]:
                item["explanation"] = result["explanation"]
            
            # Add phrases if available
            if result["vn_phrases"] and result["vn_phrases"] != "[]":
                try:
                    item["phrases"] = json.loads(result["vn_phrases"])
                except json.JSONDecodeError:
                    pass
            
            # Categorize by confidence
            if score >= self.THRESHOLD_INJECT:
                guidance["inject"].append(item)
            elif score >= self.THRESHOLD_LOG:
                guidance["suggestions"].append(item)
            
            # Check for false cognates
            if result["category"] == "false_cognates":
                guidance["warnings"].append(item)
        
        return guidance
    
    def get_bulk_guidance(
        self,
        terms: List[str],
        genre: str = "general",
        max_per_term: int = 2,
        min_confidence: float = 0.65,
        context: Optional[str] = None,
        prev_context: Optional[str] = None,
        next_context: Optional[str] = None,
        use_external_dict: bool = False
    ) -> Dict[str, Any]:
        """
        Get translation guidance for multiple kanji/Chinese terms.
        
        Uses HYBRID approach with CONTEXT-AWARE DISAMBIGUATION:
        1. First tries DIRECT LOOKUP (exact hanzi match) - always 1.0 confidence
        2. Falls back to VECTOR SEARCH with context for semantic similarity
        3. Optionally queries EXTERNAL DICTIONARY API for unknown terms
        
        Context-Aware Features:
        - Uses surrounding sentences to improve disambiguation
        - Boosts scores for patterns that match context indicators
        - External dictionary fallback for terms not in RAG database
        
        Optimized for batch processing (e.g., pre-translation kanji scanning).
        
        Args:
            terms: List of Chinese/kanji terms to look up
            genre: Genre context for filtering
            max_per_term: Maximum results per term (default: 2)
            min_confidence: Minimum confidence threshold (default: 0.65)
            context: Current sentence being translated (for context awareness)
            prev_context: Previous sentence(s) for better disambiguation
            next_context: Following sentence(s) for better disambiguation
            use_external_dict: If True, query external dictionary for unknown terms
            
        Returns:
            Dictionary with aggregated guidance:
            {
                "terms": {term: [guidance_items]},
                "high_confidence": [items],
                "medium_confidence": [items],
                "external_dict": [items from external API],
                "summary": {stats}
            }
        """
        bulk_guidance = {
            "terms": {},
            "high_confidence": [],
            "medium_confidence": [],
            "external_dict": [],
            "total_terms_scanned": len(terms),
            "total_matches_found": 0,
            "lookup_stats": {
                "direct_hits": 0,
                "vector_hits": 0,
                "external_hits": 0,
                "not_found": 0
            }
        }
        
        # Build direct lookup index from RAG data (exact hanzi match)
        rag_data = self.load_rag_data()
        direct_lookup = {}
        for cat_name, cat_data in rag_data.get("pattern_categories", {}).items():
            for pattern in cat_data.get("patterns", []):
                hanzi = pattern.get("hanzi", "")
                if hanzi and hanzi not in direct_lookup:
                    # Extract context indicators for context-aware matching
                    zh_indicators = []
                    contexts = pattern.get("contexts", [])
                    if contexts:
                        for ctx in contexts:
                            zh_indicators.extend(ctx.get("zh_indicators", []))
                    
                    direct_lookup[hanzi] = {
                        "hanzi": hanzi,
                        "vn": pattern.get("primary_reading", ""),
                        "avoid": "",
                        "meaning": cat_name,
                        "score": 1.0,  # Exact match = perfect score
                        "category": cat_name,
                        "zh_indicators": zh_indicators  # For context matching
                    }
                    # Get avoid from contexts if available
                    if contexts:
                        avoids = contexts[0].get("avoid", [])
                        if avoids:
                            direct_lookup[hanzi]["avoid"] = avoids[0] if isinstance(avoids, list) else avoids
        
        # Track terms not found for external dictionary lookup
        not_found_terms = []
        
        # Combine all context for context-aware disambiguation
        full_context = ""
        if context:
            full_context = context
        if prev_context:
            full_context = f"{prev_context} {full_context}"
        if next_context:
            full_context = f"{full_context} {next_context}"
        
        for term in terms:
            term_guidance = []
            
            # 1. Try DIRECT LOOKUP first (exact match)
            if term in direct_lookup:
                item = direct_lookup[term].copy()
                
                # Context-aware scoring: boost if context contains relevant indicators
                if full_context and item.get("zh_indicators"):
                    for indicator in item["zh_indicators"]:
                        if indicator in full_context:
                            # Indicator found in context - this is the right meaning
                            item["score"] = 1.0
                            item["context_match"] = True
                            break
                
                term_guidance.append(item)
                bulk_guidance["total_matches_found"] += 1
                bulk_guidance["high_confidence"].append(item)
                bulk_guidance["lookup_stats"]["direct_hits"] += 1
                logger.debug(f"[DIRECT] {term} → {item['vn']}")
            else:
                # 2. Fall back to VECTOR SEARCH with context
                results = self.query_disambiguation(
                    chinese_text=term,
                    prev_context=prev_context or "",
                    next_context=next_context or "",
                    genre=genre,
                    top_k=max_per_term
                )
                
                found_match = False
                for result in results:
                    score = result["score"]
                    
                    # Context-aware score adjustment
                    if full_context:
                        zh_indicators_str = result.get("raw_metadata", {}).get("zh_indicators", "[]")
                        try:
                            zh_indicators = json.loads(zh_indicators_str) if isinstance(zh_indicators_str, str) else zh_indicators_str
                            for indicator in zh_indicators:
                                if indicator in full_context:
                                    # Boost score for context match
                                    score = min(1.0, score * 1.15)
                                    break
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    # Skip low confidence
                    if score < min_confidence:
                        continue
                    
                    found_match = True
                    item = {
                        "hanzi": result["hanzi"],
                        "vn": result["vn_correct"] or result["vn_term"],
                        "avoid": result["vn_wrong"],
                        "meaning": result["meaning"],
                        "score": round(score, 4)
                    }
                    
                    term_guidance.append(item)
                    bulk_guidance["total_matches_found"] += 1
                    bulk_guidance["lookup_stats"]["vector_hits"] += 1
                    
                    # Categorize by confidence
                    if score >= self.THRESHOLD_INJECT:
                        bulk_guidance["high_confidence"].append(item)
                    elif score >= self.THRESHOLD_LOG:
                        bulk_guidance["medium_confidence"].append(item)
                
                if not found_match:
                    not_found_terms.append(term)
                    bulk_guidance["lookup_stats"]["not_found"] += 1
            
            if term_guidance:
                bulk_guidance["terms"][term] = term_guidance
        
        # 3. External dictionary lookup for unknown terms
        if use_external_dict and not_found_terms:
            try:
                from modules.external_dictionary import batch_lookup_terms
                external_results = batch_lookup_terms(not_found_terms, target_lang='vn')
                
                for term, ext_data in external_results.items():
                    # KanjiAPI returns meanings[] array
                    meanings = ext_data.get('meanings', [])
                    if meanings:
                        vn_meaning = '; '.join(meanings[:3])  # Top 3 meanings
                    else:
                        # Fallback for old format compatibility
                        vn_meaning = ext_data.get('vietnamese', ext_data.get('english', ''))
                    
                    if vn_meaning:
                        item = {
                            "hanzi": term,
                            "vn": vn_meaning,
                            "avoid": "",
                            "meaning": "external_dictionary",
                            "score": 0.70,  # Fixed score for external results
                            "source": ext_data.get('source', 'external'),
                            "reading": ext_data.get('reading', ''),
                            "jlpt": ext_data.get('jlpt', '')  # Include JLPT level
                        }
                        
                        if term not in bulk_guidance["terms"]:
                            bulk_guidance["terms"][term] = []
                        bulk_guidance["terms"][term].append(item)
                        bulk_guidance["external_dict"].append(item)
                        bulk_guidance["total_matches_found"] += 1
                        bulk_guidance["lookup_stats"]["external_hits"] += 1
                        
                        jlpt_str = f" [JLPT N{item['jlpt']}]" if item['jlpt'] else ""
                        logger.debug(f"[EXTERNAL] {term} → {vn_meaning}{jlpt_str}")
                        
            except ImportError:
                logger.warning("External dictionary module not available")
            except Exception as e:
                logger.warning(f"External dictionary error: {e}")
        
        return bulk_guidance
    
    def format_prompt_injection(
        self,
        guidance: Dict[str, Any],
        include_suggestions: bool = False
    ) -> str:
        """
        Format guidance into a prompt injection string.
        
        Args:
            guidance: Output from get_translation_guidance()
            include_suggestions: Whether to include medium-confidence suggestions
            
        Returns:
            Formatted string for prompt injection
        """
        if not guidance["inject"] and not (include_suggestions and guidance["suggestions"]):
            return ""
        
        lines = ["## Sino-Vietnamese Translation Guidance\n"]
        
        # High confidence patterns
        if guidance["inject"]:
            lines.append("### Required Terminology (use exactly as shown):\n")
            for item in guidance["inject"]:
                hanzi = item["hanzi"]
                correct = item["vn_correct"]
                avoid = item.get("vn_avoid", "")
                
                line = f"- **{hanzi}** → `{correct}`"
                if avoid:
                    line += f" (NOT: {avoid})"
                lines.append(line)
            lines.append("")
        
        # Medium confidence suggestions
        if include_suggestions and guidance["suggestions"]:
            lines.append("### Suggested Terminology (verify context):\n")
            for item in guidance["suggestions"]:
                hanzi = item["hanzi"]
                correct = item["vn_correct"]
                meaning = item.get("meaning", "")
                
                line = f"- {hanzi} → {correct}"
                if meaning:
                    line += f" ({meaning})"
                lines.append(line)
            lines.append("")
        
        # Warnings
        if guidance["warnings"]:
            lines.append("### ⚠️ False Cognate Warnings:\n")
            for item in guidance["warnings"]:
                hanzi = item["hanzi"]
                explanation = item.get("explanation", "Context-dependent meaning")
                lines.append(f"- **{hanzi}**: {explanation}")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get index statistics.
        
        Returns:
            Dictionary of statistics about the indexed patterns
        """
        return {
            **self._stats,
            "thresholds": {
                "inject": self.THRESHOLD_INJECT,
                "log": self.THRESHOLD_LOG
            },
            "persist_directory": self.persist_directory,
            "rag_file": str(self.rag_file_path)
        }
    
    def validate_index(self) -> Dict[str, Any]:
        """
        Validate the index by running test queries.
        
        Returns:
            Validation results with pass/fail status
        """
        test_cases = [
            {
                "query": "修真",
                "expected_hanzi": "修",
                "expected_vn_contains": "tu"
            },
            {
                "query": "金丹期",
                "expected_hanzi": "金丹",
                "expected_vn_contains": "Kim Đan"
            },
            {
                "query": "灵气",
                "expected_hanzi": "灵",
                "expected_vn_contains": "linh"
            },
            {
                "query": "师父",
                "expected_hanzi": "师",
                "expected_vn_contains": "sư"
            }
        ]
        
        results = {
            "total_tests": len(test_cases),
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
        for test in test_cases:
            query_results = self.query_disambiguation(
                chinese_text=test["query"],
                top_k=3
            )
            
            passed = False
            if query_results:
                top_result = query_results[0]
                vn_correct = top_result.get("vn_correct", "") or top_result.get("vn_term", "")
                
                if test["expected_vn_contains"].lower() in vn_correct.lower():
                    passed = True
            
            if passed:
                results["passed"] += 1
            else:
                results["failed"] += 1
            
            results["details"].append({
                "query": test["query"],
                "passed": passed,
                "top_result": query_results[0] if query_results else None
            })
        
        results["success_rate"] = results["passed"] / results["total_tests"] * 100
        return results


# Convenience function for quick initialization
def create_sino_vn_store(
    persist_directory: str = "./chroma_sino_vn",
    build_index: bool = True
) -> SinoVietnameseStore:
    """
    Create and initialize a Sino-Vietnamese store.
    
    Args:
        persist_directory: Where to store ChromaDB data
        build_index: Whether to build/update index from RAG file
        
    Returns:
        Initialized SinoVietnameseStore
    """
    store = SinoVietnameseStore(persist_directory=persist_directory)
    
    if build_index:
        logger.info("Building Sino-Vietnamese index...")
        counts = store.build_index()
        logger.info(f"Index built: {counts}")
    
    return store


if __name__ == "__main__":
    # Test the store
    logging.basicConfig(level=logging.INFO)
    
    print("Testing SinoVietnameseStore...")
    
    store = create_sino_vn_store(
        persist_directory="./test_chroma_sino_vn",
        build_index=True
    )
    
    # Test query
    print("\n--- Testing query: 修真界 ---")
    results = store.query_disambiguation(
        chinese_text="修真界",
        prev_context="他突破了筑基期",
        genre="cultivation_novel"
    )
    
    for r in results[:3]:
        print(f"Score: {r['score']:.4f} | {r['hanzi']} → {r['vn_correct'] or r['vn_term']}")
    
    # Test guidance
    print("\n--- Testing translation guidance ---")
    guidance = store.get_translation_guidance(
        chinese_text="金丹期的修士",
        prev_context="",
        genre="cultivation_novel"
    )
    
    print(store.format_prompt_injection(guidance, include_suggestions=True))
    
    # Validation
    print("\n--- Running validation ---")
    validation = store.validate_index()
    print(f"Validation: {validation['passed']}/{validation['total_tests']} passed ({validation['success_rate']:.1f}%)")
