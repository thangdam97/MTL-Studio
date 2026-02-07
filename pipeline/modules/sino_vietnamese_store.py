"""
Sino-Vietnamese Vector Store Module v2
=======================================
Specialized wrapper for Vietnamese translation disambiguation.

v2 Changes from v1:
- Loads sino_vietnamese_rag_v2.json (866 patterns, 9 categories)
- Auto-rebuild on empty collection (no manual intervention)
- Negative anchor system (per-category penalty for false positives)
- Updated CATEGORY_PRIORITIES for 9 categories
- Batch embedding in get_bulk_guidance() (1 API call instead of N)
- Genre-aware domain hints (romcom, cultivation, historical, etc.)
- register_substitutions category properly indexed
- false_cognates category now indexable (moved from stranded top-level)

This module provides:
1. Pre-built index for Sino-Vietnamese patterns
2. Register-aware pattern retrieval (3-tier: formal/casual/literary)
3. Cultivation-specific terminology handling
4. False cognate detection and correction
5. Negative anchor suppression for false positives
6. Batch embedding for performance
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from modules.vector_search import PatternVectorStore
from modules.pinyin_helper import enhance_query_with_pinyin, enhance_document_with_pinyin, get_pinyin

logger = logging.getLogger(__name__)


class SinoVietnameseStore:
    """
    Specialized vector store for Sino-Vietnamese disambiguation.
    
    Wraps PatternVectorStore with Vietnamese-specific:
    - Category filtering (9 categories including register_substitutions, corpus_discovered)
    - Register awareness (formal/casual/literary)
    - False cognate warnings
    - Cultivation terminology prioritization
    - Negative anchor penalty system
    - Auto-rebuild on empty collection
    """
    
    # Vietnamese-specific thresholds (stricter than generic)
    THRESHOLD_INJECT = 0.85  # Higher threshold for Vietnamese due to tone complexity
    THRESHOLD_LOG = 0.70
    
    # Negative anchor thresholds
    NEGATIVE_ANCHOR_THRESHOLD = 0.72  # Above this, penalty kicks in
    NEGATIVE_ANCHOR_PENALTY = 0.15    # Max score reduction when negative fires
    
    # Category priorities (higher = more important) - v2: 9 categories
    CATEGORY_PRIORITIES = {
        "cultivation_realms": 10,           # Proper nouns, must be correct
        "titles_honorifics": 9,             # Formal titles
        "false_cognates": 9,                # CRITICAL: same kanji, different meaning
        "sino_disambiguation": 8,           # Core disambiguation
        "register_substitutions": 8,        # Han Viet vs native VN by genre
        "cultivation_techniques": 7,        # Technique names
        "kanji_difficult_compounds": 6,     # Production-validated difficult kanji
        "corpus_discovered": 5,             # Corpus-found high-frequency gaps
        "japanese_light_novel": 5           # JP LN compounds (700)
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
            rag_file_path: Path to sino_vietnamese_rag_v2.json
        """
        self.persist_directory = persist_directory
        self.api_key = api_key
        
        # Default RAG file location - v2 path
        if rag_file_path is None:
            self.rag_file_path = Path(__file__).parent.parent / "config" / "sino_vietnamese_rag_v2.json"
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
        
        # Negative anchor cache: {category: [np.array(embedding), ...]}
        # Lazily built on first get_bulk_guidance() call
        self._negative_anchor_cache: Optional[Dict[str, List[np.ndarray]]] = None
        
        # Direct lookup cache (built lazily)
        self._direct_lookup_cache: Optional[Dict[str, Dict]] = None
        
        # Index statistics
        self._stats = {
            "total_patterns": 0,
            "by_category": {},
            "by_register": {}
        }
        
        logger.info(f"SinoVietnameseStore v2 initialized with persist_directory={persist_directory}")
        
        # Auto-rebuild: if collection is empty and RAG file exists, build index automatically
        collection_count = self.vector_store.collection.count()
        if collection_count == 0 and self.rag_file_path.exists():
            logger.warning("[SINO-VN] Vector store is empty - auto-rebuilding from sino_vietnamese_rag_v2.json...")
            try:
                indexed = self.build_index(force_rebuild=False)
                total = sum(indexed.values())
                logger.info(f"[SINO-VN] Auto-rebuild complete: {total} patterns across {len(indexed)} categories")
            except Exception as e:
                logger.error(f"[SINO-VN] Auto-rebuild failed: {e}")
                logger.warning("[SINO-VN] Sino-VN disambiguation will be unavailable this session")
        elif collection_count > 0:
            logger.info(f"[SINO-VN] Loaded existing index: {collection_count} vectors")
    
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
        Build vector index from sino_vietnamese_rag_v2.json.
        
        This extracts patterns from all 9 categories and indexes them
        with appropriate metadata for Vietnamese disambiguation.
        
        Args:
            force_rebuild: If True, clears existing index first
            
        Returns:
            Dictionary of indexed counts by category
        """
        if force_rebuild:
            logger.warning("Force rebuilding index - clearing existing data")
            try:
                # Must delete and recreate collection (not just clear items)
                # to handle embedding dimension changes between model versions
                self.vector_store.clear_collection()
            except Exception:
                pass
        
        rag_data = self.load_rag_data()
        pattern_categories = rag_data.get("pattern_categories", {})
        
        indexed_counts = {}
        total_indexed = 0
        
        for category_name, category_data in pattern_categories.items():
            patterns = category_data.get("patterns", [])
            category_description = category_data.get("description", "")
            
            logger.info(f"Indexing category: {category_name} ({len(patterns)} patterns)")
            print(f"  -> {category_name}: {len(patterns)} patterns")
            
            for i, pattern in enumerate(patterns):
                if (i + 1) % 50 == 0:
                    print(f"    Progress: {i + 1}/{len(patterns)}")
                indexed = self._index_pattern(pattern, category_name, category_description)
                total_indexed += indexed
            
            indexed_counts[category_name] = len(patterns)
            print(f"    Done {category_name}")
        
        # Update stats
        self._stats["total_patterns"] = total_indexed
        self._stats["by_category"] = indexed_counts
        
        # Reset caches so they rebuild with new data
        self._negative_anchor_cache = None
        self._direct_lookup_cache = None
        
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
    
    # ========================================================================
    # NEGATIVE ANCHOR SYSTEM (v2)
    # ========================================================================
    
    def _build_negative_anchor_cache(self) -> Dict[str, List[np.ndarray]]:
        """
        Build and cache negative anchor embeddings from RAG v2 JSON.
        
        Reads negative_vectors from the top-level key in the v2 schema.
        Called lazily on first get_bulk_guidance() invocation.
        
        Returns:
            Dict mapping category name to list of numpy embedding arrays
        """
        if self._negative_anchor_cache is not None:
            return self._negative_anchor_cache
        
        rag_data = self.load_rag_data()
        negative_vectors = rag_data.get("negative_vectors", {})
        
        if not negative_vectors:
            logger.info("[SINO-VN] No negative_vectors found in RAG v2 data")
            self._negative_anchor_cache = {}
            return self._negative_anchor_cache
        
        # Collect all negative texts for batch embedding
        all_texts = []
        text_to_category_map = []  # (category, index_in_category)
        
        for cat_name, vectors in negative_vectors.items():
            for i, vec_data in enumerate(vectors):
                text = vec_data.get("text", "") if isinstance(vec_data, dict) else str(vec_data)
                if text:
                    all_texts.append(text)
                    text_to_category_map.append((cat_name, i))
        
        if not all_texts:
            self._negative_anchor_cache = {}
            return self._negative_anchor_cache
        
        logger.info(f"[SINO-VN] Embedding {len(all_texts)} negative anchors across {len(negative_vectors)} categories...")
        
        try:
            embeddings = self.vector_store.embed_texts_batch(all_texts)
        except Exception as e:
            logger.warning(f"[SINO-VN] Failed to embed negative anchors: {e}")
            self._negative_anchor_cache = {}
            return self._negative_anchor_cache
        
        # Organize into cache
        cache: Dict[str, List[np.ndarray]] = {}
        for (cat_name, _), embedding in zip(text_to_category_map, embeddings):
            if cat_name not in cache:
                cache[cat_name] = []
            cache[cat_name].append(np.array(embedding, dtype=np.float32))
        
        self._negative_anchor_cache = cache
        logger.info(f"[SINO-VN] Negative anchor cache built: {len(cache)} categories, {len(all_texts)} vectors")
        return self._negative_anchor_cache
    
    def _compute_negative_penalty(
        self,
        query_embedding: List[float],
        category: str
    ) -> float:
        """
        Compute penalty based on query similarity to negative anchors.
        
        If the query is semantically close to a negative anchor for the category,
        returns a penalty value to subtract from the match score.
        
        Args:
            query_embedding: The query's embedding vector
            category: The pattern category to check negatives for
            
        Returns:
            Penalty value (0.0 = no penalty, up to NEGATIVE_ANCHOR_PENALTY)
        """
        cache = self._build_negative_anchor_cache()
        
        if category not in cache:
            return 0.0
        
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return 0.0
        query_vec = query_vec / query_norm
        
        max_neg_similarity = 0.0
        for neg_vec in cache[category]:
            neg_norm = np.linalg.norm(neg_vec)
            if neg_norm == 0:
                continue
            cos_sim = float(np.dot(query_vec, neg_vec / neg_norm))
            if cos_sim > max_neg_similarity:
                max_neg_similarity = cos_sim
        
        # If max negative similarity exceeds threshold, apply proportional penalty
        if max_neg_similarity >= self.NEGATIVE_ANCHOR_THRESHOLD:
            overshoot = (max_neg_similarity - self.NEGATIVE_ANCHOR_THRESHOLD) / (1.0 - self.NEGATIVE_ANCHOR_THRESHOLD)
            penalty = overshoot * self.NEGATIVE_ANCHOR_PENALTY
            logger.debug(
                f"[NEG-ANCHOR] {category}: neg_sim={max_neg_similarity:.3f} penalty={penalty:.3f}"
            )
            return penalty
        
        return 0.0
    
    # ========================================================================
    # DIRECT LOOKUP CACHE (v2)
    # ========================================================================
    
    def _build_direct_lookup(self) -> Dict[str, Dict]:
        """
        Build direct lookup index from RAG data for O(1) exact hanzi matching.
        Caches result for reuse across calls.
        
        Returns:
            Dict mapping hanzi string to lookup data dict
        """
        if self._direct_lookup_cache is not None:
            return self._direct_lookup_cache
        
        rag_data = self.load_rag_data()
        direct_lookup = {}
        
        for cat_name, cat_data in rag_data.get("pattern_categories", {}).items():
            for pattern in cat_data.get("patterns", []):
                hanzi = pattern.get("hanzi", "")
                if not hanzi or hanzi in direct_lookup:
                    continue
                
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
                    "score": 1.0,
                    "category": cat_name,
                    "zh_indicators": zh_indicators
                }
                
                # Get avoid from contexts if available
                if contexts:
                    avoids = contexts[0].get("avoid", [])
                    if avoids:
                        direct_lookup[hanzi]["avoid"] = avoids[0] if isinstance(avoids, list) else avoids
        
        self._direct_lookup_cache = direct_lookup
        logger.info(f"[SINO-VN] Direct lookup cache built: {len(direct_lookup)} entries")
        return self._direct_lookup_cache
    
    # ========================================================================
    # QUERY METHODS
    # ========================================================================
    
    def query_disambiguation(
        self,
        chinese_text: str,
        prev_context: str = "",
        next_context: str = "",
        register: Optional[str] = None,
        genre: str = "general",
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query for Sino-Vietnamese disambiguation patterns.
        
        This is the main entry point for Vietnamese translation assistance.
        
        Args:
            chinese_text: The Chinese/Japanese text to translate
            prev_context: Previous sentence(s) for context
            next_context: Following sentence(s) for context
            register: Optional register filter (formal/casual/literary)
            genre: Genre context for filtering (no longer hardcoded)
            top_k: Maximum results to return
            
        Returns:
            List of relevant patterns with confidence scores
        """
        # v2: Expanded domain hints covering all genres
        domain_hints = {
            "cultivation_novel": "Chinese cultivation novel Sino-Vietnamese translation",
            "wuxia": "Chinese martial arts wuxia novel Vietnamese translation",
            "xianxia": "Chinese immortal cultivation xianxia Sino-Vietnamese translation",
            "romcom": "Japanese light novel romcom Vietnamese translation casual register",
            "school_life": "Japanese school life light novel Vietnamese translation casual register",
            "slice_of_life": "Japanese slice of life light novel Vietnamese translation casual register",
            "contemporary": "Modern Japanese light novel Vietnamese translation natural register",
            "historical": "Historical Japanese novel formal Vietnamese translation Han Viet register",
            "fantasy_classical": "Fantasy novel with classical setting Vietnamese translation formal register",
            "general": "Japanese to Vietnamese Sino-Vietnamese translation"
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
            if genre and example_context not in ["general", genre, "japanese_light_novel"]:
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
        genre: str = "general"
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
        2. Falls back to VECTOR SEARCH with batch embeddings + negative anchors
        3. Optionally queries EXTERNAL DICTIONARY API for unknown terms
        
        v2 Improvements:
        - Batch embedding: 1 API call for all vector search queries
        - Negative anchor penalty: suppresses false positive matches
        - Direct lookup cache: O(1) exact match from pre-built dict
        - Genre parameter: passed through properly (was hardcoded "general")
        
        Args:
            terms: List of Chinese/kanji terms to look up
            genre: Genre context for filtering (extracted from manifest)
            max_per_term: Maximum results per term (default: 2)
            min_confidence: Minimum confidence threshold (default: 0.65)
            context: Current sentence being translated (for context awareness)
            prev_context: Previous sentence(s) for better disambiguation
            next_context: Following sentence(s) for better disambiguation
            use_external_dict: If True, query external dictionary for unknown terms
            
        Returns:
            Dictionary with aggregated guidance
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
                "not_found": 0,
                "neg_penalties_applied": 0
            }
        }
        
        if not terms:
            return bulk_guidance
        
        # Build direct lookup index (cached)
        direct_lookup = self._build_direct_lookup()
        
        # Combine all context for context-aware disambiguation
        full_context = ""
        if context:
            full_context = context
        if prev_context:
            full_context = f"{prev_context} {full_context}"
        if next_context:
            full_context = f"{full_context} {next_context}"
        
        # Separate terms into direct-hit vs needs-vector-search
        direct_terms = []
        vector_terms = []
        
        for term in terms:
            if term in direct_lookup:
                direct_terms.append(term)
            else:
                vector_terms.append(term)
        
        # === Phase 1: Process direct lookup hits ===
        for term in direct_terms:
            item = direct_lookup[term].copy()
            
            # Context-aware scoring: boost if context contains relevant indicators
            if full_context and item.get("zh_indicators"):
                for indicator in item["zh_indicators"]:
                    if indicator in full_context:
                        item["score"] = 1.0
                        item["context_match"] = True
                        break
            
            bulk_guidance["terms"][term] = [item]
            bulk_guidance["total_matches_found"] += 1
            bulk_guidance["high_confidence"].append(item)
            bulk_guidance["lookup_stats"]["direct_hits"] += 1
            logger.debug(f"[DIRECT] {term} -> {item['vn']}")
        
        # === Phase 2: Batch vector search for remaining terms ===
        if vector_terms:
            # Build all queries
            queries = []
            query_term_map = []  # Track which query maps to which term
            
            for term in vector_terms:
                query = f"{term} {full_context[:200]}" if full_context else term
                queries.append(query)
                query_term_map.append(term)
            
            # Batch embed all queries in 1 API call
            try:
                query_embeddings = self.vector_store.embed_texts_batch(queries)
            except Exception as e:
                logger.warning(f"[SINO-VN] Batch embedding failed, falling back to sequential: {e}")
                query_embeddings = [self.vector_store.embed_text(q) for q in queries]
            
            # Pre-build negative anchor cache (lazy, only on first call)
            self._build_negative_anchor_cache()
            
            # Search ChromaDB with pre-computed embeddings
            for idx, (embedding, term) in enumerate(zip(query_embeddings, query_term_map)):
                results = self.vector_store.collection.query(
                    query_embeddings=[embedding],
                    n_results=max_per_term
                )
                
                if not results['ids'] or not results['ids'][0]:
                    bulk_guidance["lookup_stats"]["not_found"] += 1
                    continue
                
                found_match = False
                for i in range(len(results['ids'][0])):
                    distance = results['distances'][0][i] if results['distances'] else 0
                    raw_similarity = 1 - distance
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                    
                    # Apply negative anchor penalty
                    category = metadata.get("category", "")
                    neg_penalty = self._compute_negative_penalty(embedding, category)
                    if neg_penalty > 0:
                        bulk_guidance["lookup_stats"]["neg_penalties_applied"] += 1
                    
                    score = max(0.0, raw_similarity - neg_penalty)
                    
                    # Context-aware score adjustment
                    if full_context:
                        zh_indicators_str = metadata.get("zh_indicators", "[]")
                        try:
                            zh_indicators = json.loads(zh_indicators_str) if isinstance(zh_indicators_str, str) else zh_indicators_str
                            for indicator in zh_indicators:
                                if indicator in full_context:
                                    score = min(1.0, score * 1.15)
                                    break
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    # Skip low confidence
                    if score < min_confidence:
                        continue
                    
                    found_match = True
                    item = {
                        "hanzi": metadata.get("hanzi", term),
                        "vn": metadata.get("vn_correct", "") or metadata.get("vn_term", ""),
                        "avoid": metadata.get("vn_wrong", ""),
                        "meaning": metadata.get("meaning", ""),
                        "score": round(score, 4),
                        "category": category,
                        "raw_similarity": round(raw_similarity, 4),
                        "neg_penalty": round(neg_penalty, 4)
                    }
                    
                    if term not in bulk_guidance["terms"]:
                        bulk_guidance["terms"][term] = []
                    bulk_guidance["terms"][term].append(item)
                    bulk_guidance["total_matches_found"] += 1
                    bulk_guidance["lookup_stats"]["vector_hits"] += 1
                    
                    # Categorize by confidence
                    if score >= self.THRESHOLD_INJECT:
                        bulk_guidance["high_confidence"].append(item)
                    elif score >= self.THRESHOLD_LOG:
                        bulk_guidance["medium_confidence"].append(item)
                
                if not found_match:
                    bulk_guidance["lookup_stats"]["not_found"] += 1
        
        # === Phase 3: External dictionary lookup for unknown terms ===
        not_found_terms = [t for t in terms if t not in bulk_guidance["terms"]]
        
        if use_external_dict and not_found_terms:
            try:
                from modules.external_dictionary import batch_lookup_terms
                external_results = batch_lookup_terms(not_found_terms, target_lang='vn')
                
                for term, ext_data in external_results.items():
                    meanings = ext_data.get('meanings', [])
                    if meanings:
                        vn_meaning = '; '.join(meanings[:3])
                    else:
                        vn_meaning = ext_data.get('vietnamese', ext_data.get('english', ''))
                    
                    if vn_meaning:
                        item = {
                            "hanzi": term,
                            "vn": vn_meaning,
                            "avoid": "",
                            "meaning": "external_dictionary",
                            "score": 0.70,
                            "source": ext_data.get('source', 'external'),
                            "reading": ext_data.get('reading', ''),
                            "jlpt": ext_data.get('jlpt', '')
                        }
                        
                        if term not in bulk_guidance["terms"]:
                            bulk_guidance["terms"][term] = []
                        bulk_guidance["terms"][term].append(item)
                        bulk_guidance["external_dict"].append(item)
                        bulk_guidance["total_matches_found"] += 1
                        bulk_guidance["lookup_stats"]["external_hits"] += 1
                        
                        jlpt_str = f" [JLPT N{item['jlpt']}]" if item['jlpt'] else ""
                        logger.debug(f"[EXTERNAL] {term} -> {vn_meaning}{jlpt_str}")
                        
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
        collection_count = self.vector_store.collection.count()
        return {
            **self._stats,
            "collection_count": collection_count,
            "thresholds": {
                "inject": self.THRESHOLD_INJECT,
                "log": self.THRESHOLD_LOG,
                "negative_anchor": self.NEGATIVE_ANCHOR_THRESHOLD,
                "negative_penalty": self.NEGATIVE_ANCHOR_PENALTY
            },
            "persist_directory": self.persist_directory,
            "rag_file": str(self.rag_file_path),
            "version": "2.0"
        }
    
    def validate_index(self) -> Dict[str, Any]:
        """
        Validate the index by running test queries.
        
        Returns:
            Validation results with pass/fail status
        """
        test_cases = [
            # Cultivation terms
            {
                "query": "修真",
                "expected_hanzi": "修",
                "expected_vn_contains": "tu"
            },
            {
                "query": "金丹期",
                "expected_hanzi": "金丹",
                "expected_vn_contains": "Kim"
            },
            {
                "query": "灵气",
                "expected_hanzi": "灵",
                "expected_vn_contains": "linh"
            },
            {
                "query": "师父",
                "expected_hanzi": "师",
                "expected_vn_contains": "ph"
            },
            # v2: Register substitution / JLN tests
            {
                "query": "少女",
                "expected_hanzi": "少女",
                "expected_vn_contains": "n"
            },
            # v2: Corpus discovered tests  
            {
                "query": "微笑",
                "expected_hanzi": "微笑",
                "expected_vn_contains": "m"
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
    # ── v2 Test Suite ──────────────────────────────────────────────
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("SinoVietnameseStore v2.0 — Test Suite")
    print("=" * 60)
    
    store = create_sino_vn_store(
        persist_directory="./test_chroma_sino_vn",
        build_index=True
    )
    
    # ── Test 1: Cultivation query (classic category) ──
    print("\n--- Test 1: Cultivation query (修真界) ---")
    results = store.query_disambiguation(
        chinese_text="修真界",
        prev_context="他突破了筑基期",
        genre="cultivation_novel"
    )
    for r in results[:3]:
        print(f"  Score: {r['score']:.4f} | {r['hanzi']} → {r['vn_correct'] or r['vn_term']}")
    
    # ── Test 2: Register substitution (romcom genre) ──
    print("\n--- Test 2: Register substitution (少女, romcom) ---")
    results = store.query_disambiguation(
        chinese_text="少女",
        prev_context="教室の中で少女が笑った",
        genre="romcom"
    )
    for r in results[:3]:
        print(f"  Score: {r['score']:.4f} | {r['hanzi']} → {r['vn_correct'] or r['vn_term']}")
    
    # ── Test 3: False cognate detection ──
    print("\n--- Test 3: False cognate (手紙) ---")
    results = store.query_disambiguation(
        chinese_text="手紙",
        prev_context="彼女に手紙を書いた",
        genre="japanese_light_novel"
    )
    for r in results[:3]:
        print(f"  Score: {r['score']:.4f} | {r['hanzi']} → {r['vn_correct'] or r['vn_term']}")
    
    # ── Test 4: Translation guidance with prompt injection ──
    print("\n--- Test 4: Translation guidance (金丹期の修士) ---")
    guidance = store.get_translation_guidance(
        chinese_text="金丹期的修士",
        prev_context="",
        genre="cultivation_novel"
    )
    print(store.format_prompt_injection(guidance, include_suggestions=True))
    
    # ── Test 5: Bulk guidance (batch embedding + negative anchors) ──
    print("\n--- Test 5: Bulk guidance (batch embedding) ---")
    test_compounds = ["修真", "少女", "手紙", "微笑", "天才"]
    bulk = store.get_bulk_guidance(
        compounds=test_compounds,
        genre="japanese_light_novel"
    )
    print(f"  Compounds queried: {len(test_compounds)}")
    print(f"  Results returned:  {len(bulk.get('results', {}))}")
    stats = bulk.get('stats', {})
    print(f"  Direct lookups:    {stats.get('direct_lookups', 0)}")
    print(f"  Vector lookups:    {stats.get('vector_lookups', 0)}")
    print(f"  Neg penalties:     {stats.get('neg_penalties_applied', 0)}")
    for compound, data in bulk.get('results', {}).items():
        vn = data.get('vn_correct') or data.get('vn_term', '?')
        src = data.get('source', '?')
        print(f"    {compound} → {vn} (source: {src})")
    
    # ── Test 6: Stats ──
    print("\n--- Test 6: Store stats ---")
    stats = store.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    # ── Test 7: Validation ──
    print("\n--- Test 7: Validation ---")
    validation = store.validate_index()
    print(f"  Passed: {validation['passed']}/{validation['total_tests']} ({validation['success_rate']:.1f}%)")
    for detail in validation.get('details', []):
        status = "✓" if detail.get('passed') else "✗"
        print(f"    {status} {detail.get('query', '?')} → {detail.get('top_result', '?')}")
    
    print("\n" + "=" * 60)
    print("v2.0 Test Suite Complete")
    print("=" * 60)
