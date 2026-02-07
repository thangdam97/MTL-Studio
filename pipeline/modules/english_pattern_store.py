"""
English Grammar Pattern Vector Store Module
Specialized wrapper for English translation natural phrasing

This module provides:
1. Pre-built index for Japanese→English grammar patterns
2. Pattern category filtering (contrastive_comparison, etc.)
3. Register awareness (casual/formal)
4. Priority-based pattern injection for natural English
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from modules.vector_search import PatternVectorStore

logger = logging.getLogger(__name__)


class EnglishPatternStore:
    """
    Specialized vector store for English natural phrasing patterns.

    Wraps PatternVectorStore with English-specific:
    - Category filtering (contrastive_comparison, dismissive_acknowledgment, etc.)
    - Register awareness (casual/formal)
    - Japanese indicator matching
    - Priority-based pattern injection
    """

    # English-specific thresholds (tuned for light novel genre)
    THRESHOLD_INJECT = 0.78  # High confidence: inject into prompt (lowered from 0.82)
    THRESHOLD_LOG = 0.65     # Medium confidence: log but don't inject

    # Negative Anchor thresholds
    # If a query's cosine similarity to any negative vector exceeds this,
    # the match score is penalized to suppress false positives
    NEGATIVE_ANCHOR_THRESHOLD = 0.72  # Above this → penalty kicks in
    NEGATIVE_ANCHOR_PENALTY = 0.15    # Score reduction when negative fires

    # Category priorities (higher = more important)
    CATEGORY_PRIORITIES = {
        "contrastive_comparison": 10,       # "X is one thing, but Y..."
        "dismissive_acknowledgment": 9,     # "X aside..."
        "intensifiers": 8,                  # "pretty", "really"
        "hedging": 7,                       # "kind of", "sort of"
        "response_particles": 6,            # "Yeah", "I mean"
        "natural_transitions": 5,           # "anyway", "by the way"
        "giving_receiving": 9,              # くれる/もらう/あげる social dynamics
        "structure_particles": 8,           # わけ/はず/こそ meaning shifts
        "desire_intention": 7,              # たい/ほしい/気になる motivation
        "inner_monologue": 7,              # 思わず/ふと/なぜか narrator voice
        "quotation_hearsay": 6,            # って言う/という/そうだ reporting
        "onomatopoeia": 6,                 # ドキドキ/ニヤリ/チラッ mimetics
        "concession_contrast": 5           # のに/にしても/くせに despite-type
    }

    def __init__(
        self,
        persist_directory: str = "./chroma_english_patterns",
        api_key: Optional[str] = None,
        rag_file_path: Optional[str] = None
    ):
        """
        Initialize English pattern store.

        Args:
            persist_directory: ChromaDB storage location
            api_key: Gemini API key (uses GOOGLE_API_KEY env var if not provided)
            rag_file_path: Path to english_grammar_rag.json
        """
        self.persist_directory = persist_directory
        self.api_key = api_key

        # Default RAG file location
        if rag_file_path is None:
            self.rag_file_path = Path(__file__).parent.parent / "config" / "english_grammar_rag.json"
        else:
            self.rag_file_path = Path(rag_file_path)

        # Initialize core vector store with English-specific collection
        self.vector_store = PatternVectorStore(
            collection_name="english_grammar_patterns",
            persist_directory=persist_directory,
            gemini_api_key=api_key
        )

        # Cache for loaded RAG data
        self._rag_cache: Optional[Dict] = None

        # Index statistics
        self._stats = {
            "total_patterns": 0,
            "by_category": {},
            "by_priority": {}
        }

        # Negative anchor cache: {category: [np.array(embedding), ...]}
        # Lazily built on first get_bulk_guidance() call
        self._negative_anchor_cache: Optional[Dict[str, List[np.ndarray]]] = None

        logger.info(f"EnglishPatternStore initialized with persist_directory={persist_directory}")

        # Auto-rebuild: if collection is empty and RAG file exists, build index automatically
        # This handles the case where the DB was deleted (e.g., embedding dimension change)
        # and needs to be rebuilt without manual intervention
        collection_count = self.vector_store.collection.count()
        if collection_count == 0 and self.rag_file_path.exists():
            logger.warning("[GRAMMAR] Vector store is empty — auto-rebuilding from english_grammar_rag.json...")
            try:
                indexed = self.build_index(force_rebuild=False)
                total = sum(indexed.values())
                logger.info(f"[GRAMMAR] ✓ Auto-rebuild complete: {total} patterns across {len(indexed)} categories")
            except Exception as e:
                logger.error(f"[GRAMMAR] Auto-rebuild failed: {e}")
                logger.warning("[GRAMMAR] Grammar pattern guidance will be unavailable this session")
        elif collection_count > 0:
            logger.info(f"[GRAMMAR] Vector store loaded: {collection_count} indexed patterns")

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
        Build vector index from english_grammar_rag.json.

        This extracts patterns from all categories and indexes them
        with appropriate metadata for English natural phrasing.

        Args:
            force_rebuild: If True, clears existing index first

        Returns:
            Dictionary of indexed counts by category
        """
        if force_rebuild:
            logger.warning("Force rebuilding index - clearing existing data")
            self.vector_store.clear_collection()

        rag_data = self.load_rag_data()
        pattern_categories = rag_data.get("pattern_categories", {})
        advanced_patterns = rag_data.get("advanced_patterns", {})

        # Merge advanced_patterns into pattern_categories for indexing
        # Skip non-category keys like 'description'
        for key, value in advanced_patterns.items():
            if isinstance(value, dict) and "patterns" in value:
                pattern_categories[key] = value

        indexed_counts = {}
        total_indexed = 0

        for category_name, category_data in pattern_categories.items():
            patterns = category_data.get("patterns", [])
            category_description = category_data.get("description", "")

            logger.info(f"Indexing category: {category_name} ({len(patterns)} patterns)")
            print(f"  → {category_name}: {len(patterns)} patterns")

            for i, pattern in enumerate(patterns):
                if (i + 1) % 20 == 0:
                    print(f"    Progress: {i + 1}/{len(patterns)}")
                indexed = self._index_pattern(pattern, category_name, category_description)
                total_indexed += indexed

            indexed_counts[category_name] = len(patterns)
            print(f"    ✓ Completed {category_name}")

        # Update stats
        self._stats["total_patterns"] = total_indexed
        self._stats["by_category"] = indexed_counts

        logger.info(f"Index built: {total_indexed} patterns across {len(indexed_counts)} categories")
        return indexed_counts

    def _index_pattern(
        self,
        pattern: Dict,
        category_name: str,
        category_description: str
    ) -> int:
        """
        Index a single pattern from english_grammar_rag.json.

        Pattern structure:
        {
            "id": "one_thing_but",
            "japanese_structure": "AはBだが、CもBだ",
            "japanese_indicators": ["けど", "が", "も"],
            "english_pattern": "X is one thing, but Y is [quality]",
            "examples": [
                {
                    "jp": "真理亜は変だが、如月さんも結構変だ",
                    "literal": "Maria's weird, but Kisaragi-san is pretty weird...",
                    "natural": "Maria's one thing, but Kisaragi-san is pretty weird..."
                }
            ],
            "usage_rules": [...],
            "priority": "high"
        }

        We index each example with:
        - Document: japanese_structure + japanese_indicators + jp example
        - Metadata: english_pattern, natural, priority, category, usage_rules

        Returns:
            Number of examples indexed (1 per example)
        """
        pattern_id_base = pattern.get("id", "unknown")
        japanese_structure = pattern.get("japanese_structure", "")
        japanese_indicators = pattern.get("japanese_indicators", [])
        english_pattern = pattern.get("english_pattern", "")
        usage_rules = pattern.get("usage_rules", [])
        priority = pattern.get("priority", "medium")
        examples = pattern.get("examples", [])

        if not examples:
            logger.warning(f"Pattern {pattern_id_base} has no examples, skipping")
            return 0

        # Get numeric priority
        priority_value = self.CATEGORY_PRIORITIES.get(category_name, 5)

        indexed_count = 0

        # Index each example separately (for better context matching)
        for ex_idx, example in enumerate(examples):
            pattern_id = f"{pattern_id_base}_ex{ex_idx}"

            jp_text = example.get("jp", "")
            literal = example.get("literal", "")
            natural = example.get("natural", "")
            source = example.get("source", "")

            # Build text for embedding
            # Structure: Japanese pattern + indicators + actual example
            # This allows semantic matching against detected patterns in source text
            text_parts = []

            # Add Japanese structure for pattern matching
            if japanese_structure:
                text_parts.append(f"Structure: {japanese_structure}")

            # Add indicators for keyword matching
            if japanese_indicators:
                indicators_str = ", ".join(japanese_indicators)
                text_parts.append(f"Indicators: {indicators_str}")

            # Add actual example (most important for context)
            if jp_text:
                text_parts.append(f"Example: {jp_text}")

            # Add natural English for semantic similarity
            if natural:
                text_parts.append(f"Natural EN: {natural}")

            text_to_embed = " | ".join(text_parts)

            # Metadata for retrieval
            metadata = {
                "category": category_name,
                "pattern_id_base": pattern_id_base,
                "japanese_structure": japanese_structure,
                "japanese_indicators": ",".join(japanese_indicators),
                "english_pattern": english_pattern,
                "jp_example": jp_text,
                "literal": literal,
                "natural": natural,
                "priority": priority,
                "priority_value": priority_value,
                "usage_rules": " | ".join(usage_rules) if usage_rules else "",
                "source": source
            }

            # Add to vector store
            self.vector_store.add_pattern(
                pattern_id=pattern_id,
                text=text_to_embed,
                metadata=metadata
            )

            indexed_count += 1

        return indexed_count

    def _build_negative_anchor_cache(self) -> Dict[str, List[np.ndarray]]:
        """
        Build and cache negative anchor embeddings from RAG JSON.

        Reads negative_vectors from each category, batch-embeds them,
        and stores as numpy arrays for fast cosine similarity computation.

        Called lazily on first get_bulk_guidance() invocation.

        Returns:
            Dict mapping category name → list of numpy embedding arrays
        """
        if self._negative_anchor_cache is not None:
            return self._negative_anchor_cache

        rag_data = self.load_rag_data()
        negative_texts_by_category: Dict[str, List[str]] = {}

        # Collect negative vector texts from pattern_categories and advanced_patterns
        for section_key in ["pattern_categories", "advanced_patterns"]:
            section = rag_data.get(section_key, {})
            for cat_name, cat_data in section.items():
                if not isinstance(cat_data, dict):
                    continue
                neg_block = cat_data.get("negative_vectors", {})
                neg_texts = neg_block.get("texts", [])
                if neg_texts:
                    negative_texts_by_category[cat_name] = neg_texts

        if not negative_texts_by_category:
            logger.info("[GRAMMAR] No negative_vectors found in RAG data")
            self._negative_anchor_cache = {}
            return self._negative_anchor_cache

        # Batch embed all negative texts in one API call
        all_texts = []
        text_to_category_map = []  # (category, index_in_category)

        for cat_name, texts in negative_texts_by_category.items():
            for i, text in enumerate(texts):
                all_texts.append(text)
                text_to_category_map.append((cat_name, i))

        logger.info(f"[GRAMMAR] Embedding {len(all_texts)} negative anchors across {len(negative_texts_by_category)} categories...")

        try:
            embeddings = self.vector_store.embed_texts_batch(all_texts)
        except Exception as e:
            logger.warning(f"[GRAMMAR] Failed to embed negative anchors: {e}")
            self._negative_anchor_cache = {}
            return self._negative_anchor_cache

        # Organize into cache
        cache: Dict[str, List[np.ndarray]] = {}
        for (cat_name, _), embedding in zip(text_to_category_map, embeddings):
            if cat_name not in cache:
                cache[cat_name] = []
            cache[cat_name].append(np.array(embedding, dtype=np.float32))

        self._negative_anchor_cache = cache
        logger.info(f"[GRAMMAR] ✓ Negative anchor cache built: {len(cache)} categories, {len(all_texts)} vectors")
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
            # Scale penalty: at threshold → 0, at 1.0 → full penalty
            overshoot = (max_neg_similarity - self.NEGATIVE_ANCHOR_THRESHOLD) / (1.0 - self.NEGATIVE_ANCHOR_THRESHOLD)
            penalty = overshoot * self.NEGATIVE_ANCHOR_PENALTY
            logger.debug(
                f"[NEG-ANCHOR] {category}: neg_sim={max_neg_similarity:.3f} → penalty={penalty:.3f}"
            )
            return penalty

        return 0.0

    def search(
        self,
        query: str,
        top_k: int = 5,
        category_filter: Optional[str] = None,
        priority_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Semantic search for relevant English patterns.

        Args:
            query: Japanese text or pattern to search for
            top_k: Number of results to return
            category_filter: Filter by category (contrastive_comparison, etc.)
            priority_filter: Filter by priority (high, medium, low)

        Returns:
            List of matches with pattern_id, similarity, and metadata
        """
        # Build filter conditions
        where_filter = {}
        if category_filter:
            where_filter["category"] = category_filter
        if priority_filter:
            where_filter["priority"] = priority_filter

        # Execute search
        results = self.vector_store.collection.query(
            query_embeddings=[self.vector_store.embed_text(query)],
            n_results=top_k,
            where=where_filter if where_filter else None
        )

        # Format results
        matches = []
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                distance = results['distances'][0][i] if results['distances'] else 0
                similarity = 1 - distance  # Convert distance to similarity

                matches.append({
                    "pattern_id": results['ids'][0][i],
                    "distance": distance,
                    "similarity": similarity,
                    "document": results['documents'][0][i] if results['documents'] else "",
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                })

        return matches

    def get_bulk_guidance(
        self,
        patterns: List[Dict],
        context: str = "",
        max_per_pattern: int = 2,
        min_confidence: float = 0.75
    ) -> Dict[str, List[Dict]]:
        """
        Get English pattern guidance for multiple detected Japanese patterns.

        Uses batch embedding for efficiency (1 API call instead of N calls).

        Args:
            patterns: List of detected patterns from grammar_pattern_detector
                     Each pattern: {"category": "...", "indicator": "...", "context": "..."}
            context: Surrounding Japanese context
            max_per_pattern: Maximum matches per detected pattern
            min_confidence: Minimum similarity threshold

        Returns:
            Dictionary with:
            - high_confidence: List of patterns with similarity ≥ THRESHOLD_INJECT
            - medium_confidence: List of patterns with similarity ≥ THRESHOLD_LOG
            - lookup_stats: Statistics about retrieval
        """
        if not patterns:
            return {
                "high_confidence": [],
                "medium_confidence": [],
                "lookup_stats": {"patterns_queried": 0, "high_conf_hits": 0, "medium_conf_hits": 0}
            }

        high_confidence = []
        medium_confidence = []

        # === OPTIMIZATION: Batch embed all queries at once ===
        # Build all queries first
        queries = []
        query_metadata = []  # Track which query corresponds to which pattern

        for pattern_info in patterns:
            category = pattern_info.get("category", "")
            indicator = pattern_info.get("indicator", "")
            pattern_context = pattern_info.get("context", "")

            # Build search query
            query = f"{pattern_context} {indicator} {context}"
            queries.append(query)
            query_metadata.append({
                "category": category,
                "indicator": indicator,
                "pattern_context": pattern_context
            })

        # Generate embeddings for all queries in 1 API call
        try:
            query_embeddings = self.vector_store.embed_texts_batch(queries)
        except Exception as e:
            logger.warning(f"Batch embedding failed, falling back to sequential: {e}")
            # Fallback to sequential if batch fails
            query_embeddings = [self.vector_store.embed_text(q) for q in queries]

        # === Search ChromaDB with pre-computed embeddings ===
        # Pre-build negative anchor cache (lazy, only on first call)
        self._build_negative_anchor_cache()
        neg_penalties_applied = 0

        for idx, (embedding, meta) in enumerate(zip(query_embeddings, query_metadata)):
            category = meta["category"]

            # Build filter conditions
            where_filter = {}
            if category:
                where_filter["category"] = category

            # Query ChromaDB directly with pre-computed embedding
            results = self.vector_store.collection.query(
                query_embeddings=[embedding],
                n_results=max_per_pattern,
                where=where_filter if where_filter else None
            )

            # === NEGATIVE ANCHOR: compute penalty for this query ===
            neg_penalty = self._compute_negative_penalty(embedding, category)
            if neg_penalty > 0:
                neg_penalties_applied += 1

            # Format results
            if results['ids'] and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    distance = results['distances'][0][i] if results['distances'] else 0
                    raw_similarity = 1 - distance
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}

                    # Apply negative anchor penalty
                    similarity = max(0.0, raw_similarity - neg_penalty)

                    # Build guidance entry
                    guidance_entry = {
                        "pattern_id": results['ids'][0][i],
                        "similarity": similarity,
                        "raw_similarity": raw_similarity,
                        "neg_penalty": neg_penalty,
                        "japanese_structure": metadata.get("japanese_structure", ""),
                        "english_pattern": metadata.get("english_pattern", ""),
                        "natural_example": metadata.get("natural", ""),
                        "jp_example": metadata.get("jp_example", ""),
                        "priority": metadata.get("priority", "medium"),
                        "usage_rules": metadata.get("usage_rules", "").split(" | ") if metadata.get("usage_rules") else []
                    }

                    # Categorize by confidence (using penalty-adjusted similarity)
                    if similarity >= self.THRESHOLD_INJECT:
                        high_confidence.append(guidance_entry)
                    elif similarity >= self.THRESHOLD_LOG:
                        medium_confidence.append(guidance_entry)

        # Sort by similarity (descending)
        high_confidence.sort(key=lambda x: x["similarity"], reverse=True)
        medium_confidence.sort(key=lambda x: x["similarity"], reverse=True)

        return {
            "high_confidence": high_confidence,
            "medium_confidence": medium_confidence,
            "lookup_stats": {
                "patterns_queried": len(patterns),
                "high_conf_hits": len(high_confidence),
                "medium_conf_hits": len(medium_confidence),
                "neg_penalties_applied": neg_penalties_applied
            }
        }

    def get_collection_stats(self) -> Dict:
        """Get statistics about the vector store."""
        return {
            "collection_name": self.vector_store.collection.name,
            "total_patterns": self.vector_store.collection.count(),
            "persist_directory": str(self.persist_directory),
            "thresholds": {
                "inject": self.THRESHOLD_INJECT,
                "log": self.THRESHOLD_LOG
            },
            "categories": self._stats.get("by_category", {})
        }


# Convenience function for quick testing
def quick_pattern_search(
    japanese_text: str,
    store_path: str = "./chroma_english_patterns"
) -> Dict:
    """
    Quick pattern search for testing.

    Args:
        japanese_text: Japanese text containing grammar patterns
        store_path: Path to vector store

    Returns:
        Best match with English pattern

    Example:
        result = quick_pattern_search("真理亜は変だが、如月さんも結構変だ")
        # Returns: {"english_pattern": "X is one thing, but Y...", ...}
    """
    store = EnglishPatternStore(persist_directory=store_path)

    results = store.search(query=japanese_text, top_k=1)

    if results and results[0]['similarity'] >= EnglishPatternStore.THRESHOLD_INJECT:
        match = results[0]
        return {
            "japanese_text": japanese_text,
            "english_pattern": match['metadata'].get('english_pattern', ''),
            "natural_example": match['metadata'].get('natural', ''),
            "confidence": match['similarity'],
            "priority": match['metadata'].get('priority', 'medium')
        }
    else:
        return {
            "japanese_text": japanese_text,
            "english_pattern": None,
            "message": "No high-confidence match found",
            "best_similarity": results[0]['similarity'] if results else 0
        }


if __name__ == "__main__":
    # Quick test
    print("English Pattern Store Module loaded successfully")
    print(f"Thresholds: inject={EnglishPatternStore.THRESHOLD_INJECT}, log={EnglishPatternStore.THRESHOLD_LOG}")
