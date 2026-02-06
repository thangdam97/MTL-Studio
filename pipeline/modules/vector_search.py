"""
Vector Search Module for MTL Studio

Semantic pattern matching using embeddings for:
- Sino-Vietnamese disambiguation (ZH→VN)
- Japanese transcreation patterns (JP→EN)
- Character voice consistency

Key Features:
- Register metadata filtering (formal/casual/literary)
- Sliding window context for disambiguation
- High-threshold no-injection strategy (≥0.82)

Author: MTL Studio
Version: 1.0 (Experimental)
Date: 2026-01-31
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# ChromaDB for vector storage
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logging.warning("ChromaDB not installed. Run: pip install chromadb>=0.4.0")

# Gemini for embeddings
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google GenAI not installed.")

# Pinyin helper for Chinese text disambiguation
try:
    from modules.pinyin_helper import enhance_query_with_pinyin
    PINYIN_AVAILABLE = True
except ImportError:
    PINYIN_AVAILABLE = False
    def enhance_query_with_pinyin(text):
        return text

logger = logging.getLogger(__name__)


class PatternVectorStore:
    """
    ChromaDB-backed vector store for semantic pattern matching.
    
    Features:
    - Register-aware filtering (formal/casual/literary)
    - Sliding window context embedding
    - High-threshold injection strategy
    
    Usage:
        store = PatternVectorStore(persist_directory="data/vector_store")
        store.index_patterns("config/sino_vietnamese_rag.json")
        
        results = store.search_with_context(
            current="修道之人",
            prev="他来到了道观门前",
            top_k=3,
            register_filter="formal"
        )
    """
    
    # Threshold constants
    THRESHOLD_INJECT = 0.82      # High confidence: inject into prompt
    THRESHOLD_LOG = 0.65        # Uncertain: log but don't inject
    # Below 0.65: ignore completely
    
    def __init__(
        self,
        persist_directory: str = "data/vector_store",
        collection_name: str = "patterns",
        gemini_api_key: str = None
    ):
        """
        Initialize vector store.
        
        Args:
            persist_directory: Path to store ChromaDB files
            collection_name: Name of the ChromaDB collection
            gemini_api_key: Gemini API key (uses env var if not provided)
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB required. Install: pip install chromadb>=0.4.0")
        
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection with cosine similarity
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Initialize Gemini client for embeddings
        api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        if GEMINI_AVAILABLE and api_key:
            self.gemini_client = genai.Client(api_key=api_key)
            self._embedding_model = "gemini-embedding-001"
        else:
            self.gemini_client = None
            logger.warning("Gemini client not initialized. Embedding functions will fail.")
        
        # Track uncertain matches for analysis
        self._uncertain_matches_log: List[Dict] = []
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding using Gemini text-embedding-004.
        
        Args:
            text: Text to embed (supports Chinese, Japanese, Vietnamese, English)
            
        Returns:
            768-dimensional embedding vector
        """
        if not self.gemini_client:
            raise RuntimeError("Gemini client not initialized. Set GEMINI_API_KEY.")
        
        import time
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                result = self.gemini_client.models.embed_content(
                    model=self._embedding_model,
                    contents=text
                )
                return list(result.embeddings[0].values)
            except Exception as e:
                logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Embedding failed for text: {text[:50]}... Error: {e}")
                    raise

    def embed_texts_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single API call.

        This is much more efficient than calling embed_text() multiple times.
        Uses Gemini's embed_content endpoint with multiple contents.

        Args:
            texts: List of texts to embed (max 100 per batch recommended)

        Returns:
            List of 768-dimensional embedding vectors (one per input text)
        """
        if not self.gemini_client:
            raise RuntimeError("Gemini client not initialized. Set GEMINI_API_KEY.")

        if not texts:
            return []

        import time
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Use batch embedding endpoint (embed_content accepts list of strings)
                result = self.gemini_client.models.embed_content(
                    model=self._embedding_model,
                    contents=texts  # Pass list of texts directly
                )

                # Extract embeddings from batch result
                embeddings = []
                for embedding in result.embeddings:
                    embeddings.append(list(embedding.values))

                return embeddings

            except Exception as e:
                logger.warning(f"Batch embedding attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Batch embedding failed for {len(texts)} texts. Error: {e}")
                    raise

    def embed_with_context(
        self,
        current: str,
        prev: str = "",
        next_sent: str = ""
    ) -> List[float]:
        """
        Embed text with sliding window context.
        
        CRITICAL: Never embed just the current sentence.
        Ambiguity is resolved by surrounding context.
        
        Args:
            current: Current sentence/paragraph to translate
            prev: Previous 1-2 sentences (CRITICAL for disambiguation)
            next_sent: Next 1 sentence (optional, helps with forward reference)
            
        Returns:
            768-dimensional embedding vector
            
        Example:
            # Without context: "やっぱり" is unsolvable
            # With context: "牛乳買った？ やっぱり..." = "As I thought [you forgot]"
        """
        # Combine with structural markers
        parts = []
        if prev:
            parts.append(f"[PREV] {prev}")
        parts.append(f"[CURR] {current}")
        if next_sent:
            parts.append(f"[NEXT] {next_sent}")
        
        context_text = " ".join(parts)
        return self.embed_text(context_text)
    
    def add_pattern(
        self,
        pattern_id: str,
        text: str,
        metadata: Dict,
        embedding: Optional[List[float]] = None
    ):
        """
        Add a single pattern to the vector store.
        
        Args:
            pattern_id: Unique identifier for the pattern
            text: Text content (used for embedding if embedding not provided)
            metadata: Pattern metadata including:
                - category: Pattern category
                - register: formal | neutral | casual | literary
                - sino_vietnamese: bool - Is this a Sino-Vietnamese term?
                - genre_context: cultivation | modern | historical
                - hanzi: Original Chinese characters
                - vn_correct: Correct Vietnamese translation
                - vn_avoid: List of incorrect translations to avoid
            embedding: Pre-computed embedding (computes if not provided)
        """
        if embedding is None:
            embedding = self.embed_text(text)
        
        # Ensure required metadata fields
        metadata.setdefault("register", "neutral")
        metadata.setdefault("sino_vietnamese", False)
        metadata.setdefault("genre_context", "general")
        metadata.setdefault("added_date", datetime.now().isoformat())
        
        self.collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[pattern_id]
        )
    
    def index_patterns_from_json(self, json_path: str) -> int:
        """
        Index all patterns from a JSON RAG file.
        
        Args:
            json_path: Path to the RAG JSON file (e.g., sino_vietnamese_rag.json)
            
        Returns:
            Number of patterns indexed
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        count = 0
        pattern_categories = data.get('pattern_categories', {})
        
        for category_name, category_data in pattern_categories.items():
            patterns = category_data.get('patterns', [])
            
            for pattern in patterns:
                pattern_id_base = pattern.get('id', pattern.get('hanzi', f'pattern_{count}'))
                
                # Index each context/example
                contexts = pattern.get('contexts', [])
                examples = pattern.get('examples', [])
                
                # Handle patterns with contexts (Sino-Vietnamese style)
                for ctx_idx, context in enumerate(contexts):
                    for ex_idx, example in enumerate(context.get('examples', [])):
                        pattern_id = f"{pattern_id_base}_ctx{ctx_idx}_ex{ex_idx}"
                        
                        # Build text for embedding
                        zh_text = example.get('zh', '')
                        vn_correct = example.get('vn_correct', '')
                        text_to_embed = f"{zh_text} → {vn_correct}"
                        
                        metadata = {
                            "category": category_name,
                            "pattern_id_base": pattern_id_base,
                            "hanzi": pattern.get('hanzi', ''),
                            "primary_reading": pattern.get('primary_reading', ''),
                            "meaning": context.get('meaning', ''),
                            "register": context.get('register', 'neutral'),
                            "sino_vietnamese": pattern.get('sino_vietnamese', True),
                            "genre_context": example.get('context', 'general'),
                            "vn_correct": vn_correct,
                            "vn_wrong": example.get('vn_wrong', ''),
                            "zh_indicators": ",".join(context.get('zh_indicators', [])),
                            "vn_avoid": ",".join(context.get('avoid', []))
                        }
                        
                        self.add_pattern(pattern_id, text_to_embed, metadata)
                        count += 1
                
                # Handle patterns with direct examples (English grammar style)
                for ex_idx, example in enumerate(examples):
                    if 'zh' in example or 'jp' in example:
                        pattern_id = f"{pattern_id_base}_ex{ex_idx}"
                        
                        source = example.get('zh', example.get('jp', ''))
                        target = example.get('vn_correct', example.get('natural', ''))
                        text_to_embed = f"{source} → {target}"
                        
                        metadata = {
                            "category": category_name,
                            "pattern_id_base": pattern_id_base,
                            "hanzi": pattern.get('hanzi', ''),
                            "register": pattern.get('register', 'neutral'),
                            "sino_vietnamese": pattern.get('sino_vietnamese', False),
                            "genre_context": example.get('context', 'general'),
                            "vn_correct": target,
                            "vn_wrong": example.get('vn_wrong', example.get('literal', ''))
                        }
                        
                        self.add_pattern(pattern_id, text_to_embed, metadata)
                        count += 1
        
        logger.info(f"✓ Indexed {count} pattern examples from {json_path}")
        return count
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        register_filter: Optional[str] = None,
        genre_filter: Optional[str] = None,
        sino_only: Optional[bool] = None,
        domain_hint: str = "Sino-Vietnamese translation"
    ) -> List[Dict]:
        """
        Semantic search for relevant patterns.
        
        Args:
            query: Text to search for
            top_k: Number of results to return
            register_filter: Filter by register (formal | neutral | casual | literary)
            genre_filter: Filter by genre context (cultivation | modern | historical)
            sino_only: If True, only return Sino-Vietnamese patterns
            domain_hint: Semantic hint to improve embedding quality for short Chinese text
            
        Returns:
            List of matches with pattern_id, similarity, and metadata
        """
        # Enhance query with pinyin romanization
        # This helps Gemini text-embedding-004 produce distinguishable embeddings
        # for short Chinese text (which otherwise produces nearly identical embeddings)
        enhanced_query = enhance_query_with_pinyin(query)
        query_embedding = self.embed_text(enhanced_query)
        
        # Build filter conditions
        where_filter = {}
        if register_filter:
            where_filter["register"] = register_filter
        if genre_filter:
            where_filter["genre_context"] = genre_filter
        if sino_only is not None:
            where_filter["sino_vietnamese"] = sino_only
        
        # Execute search
        results = self.collection.query(
            query_embeddings=[query_embedding],
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
    
    def search_with_context(
        self,
        current: str,
        prev: str = "",
        next_sent: str = "",
        top_k: int = 5,
        register_filter: Optional[str] = None,
        genre_filter: Optional[str] = None,
        domain_hint: str = "cultivation novel translation"
    ) -> List[Dict]:
        """
        Search with sliding window context.
        
        This is the recommended method for disambiguation.
        
        Args:
            current: Current sentence to translate
            prev: Previous sentence(s) for context
            next_sent: Next sentence for forward reference
            top_k: Number of results
            register_filter: Optional register filter
            genre_filter: Optional genre filter
            domain_hint: Domain context hint for embedding
            
        Returns:
            List of matches with similarity scores
        """
        # Build context query
        # The current term is emphasized by placing it first and repeating
        # to ensure it has more weight than context
        query_parts = []
        query_parts.append(current)  # Current term first
        if prev:
            query_parts.append(prev)
        if next_sent:
            query_parts.append(next_sent)
        query_parts.append(current)  # Repeat current for emphasis
        
        query = " ".join(query_parts)
        
        return self.search(
            query=query,
            top_k=top_k,
            register_filter=register_filter,
            genre_filter=genre_filter,
            domain_hint=domain_hint
        )
    
    def get_patterns_for_injection(
        self,
        query: str,
        prev_context: str = "",
        top_k: int = 5,
        register_filter: Optional[str] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Get patterns to inject into translation prompt.
        
        Uses high-threshold strategy:
        - ≥0.82: Inject into prompt (high confidence)
        - 0.65-0.82: Log but DON'T inject (uncertain)
        - <0.65: Ignore completely
        
        Args:
            query: Current text to translate
            prev_context: Previous sentence(s) for context
            top_k: Number of results to consider
            register_filter: Optional register filter
            
        Returns:
            Tuple of (patterns_to_inject, patterns_logged)
        """
        results = self.search_with_context(
            current=query,
            prev=prev_context,
            top_k=top_k,
            register_filter=register_filter
        )
        
        patterns_to_inject = []
        patterns_logged = []
        
        for result in results:
            similarity = result['similarity']
            
            if similarity >= self.THRESHOLD_INJECT:
                # HIGH CONFIDENCE: Inject into prompt
                patterns_to_inject.append(result)
            elif similarity >= self.THRESHOLD_LOG:
                # UNCERTAIN: Log for analysis, but DON'T inject
                patterns_logged.append(result)
                self._log_uncertain_match(query, prev_context, result)
            # <0.65: Ignore completely (no action)
        
        return patterns_to_inject, patterns_logged
    
    def _log_uncertain_match(self, query: str, context: str, result: Dict):
        """Log uncertain matches for analysis and future training."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "context": context,
            "pattern_id": result['pattern_id'],
            "similarity": result['similarity'],
            "metadata": result['metadata']
        }
        self._uncertain_matches_log.append(log_entry)
        
        # Keep log size manageable
        if len(self._uncertain_matches_log) > 1000:
            self._uncertain_matches_log = self._uncertain_matches_log[-500:]
    
    def get_uncertain_matches_log(self) -> List[Dict]:
        """Get logged uncertain matches for analysis."""
        return self._uncertain_matches_log
    
    def save_uncertain_matches_log(self, filepath: str):
        """Save uncertain matches to JSON for analysis."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self._uncertain_matches_log, f, ensure_ascii=False, indent=2)
    
    def get_collection_stats(self) -> Dict:
        """Get statistics about the vector store."""
        return {
            "collection_name": self.collection.name,
            "total_patterns": self.collection.count(),
            "persist_directory": str(self.persist_directory),
            "thresholds": {
                "inject": self.THRESHOLD_INJECT,
                "log": self.THRESHOLD_LOG
            }
        }
    
    def clear_collection(self):
        """Clear all patterns from the collection. Use with caution."""
        # Delete and recreate collection
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Cleared collection: {self.collection.name}")


# Convenience function for quick disambiguation testing
def quick_disambiguate(
    hanzi: str,
    context: str,
    store_path: str = "data/sino_vietnamese_vectors"
) -> Dict:
    """
    Quick disambiguation for testing.
    
    Args:
        hanzi: Chinese characters to disambiguate
        context: Surrounding Chinese context
        store_path: Path to vector store
        
    Returns:
        Best match with Vietnamese translation
        
    Example:
        result = quick_disambiguate("道", "他走上了修道之路")
        # Returns: {"hanzi": "道", "vn": "đạo", "meaning": "spiritual_path", ...}
    """
    store = PatternVectorStore(persist_directory=store_path)
    
    results = store.search_with_context(
        current=hanzi,
        prev=context,
        top_k=1
    )
    
    if results and results[0]['similarity'] >= PatternVectorStore.THRESHOLD_INJECT:
        match = results[0]
        return {
            "hanzi": hanzi,
            "vn_translation": match['metadata'].get('vn_correct', ''),
            "meaning": match['metadata'].get('meaning', ''),
            "confidence": match['similarity'],
            "context_detected": match['metadata'].get('genre_context', ''),
            "avoid": match['metadata'].get('vn_avoid', '').split(',')
        }
    else:
        return {
            "hanzi": hanzi,
            "vn_translation": None,
            "message": "No high-confidence match found",
            "best_similarity": results[0]['similarity'] if results else 0
        }


if __name__ == "__main__":
    # Quick test
    print("Vector Search Module loaded successfully")
    print(f"ChromaDB available: {CHROMADB_AVAILABLE}")
    print(f"Gemini available: {GEMINI_AVAILABLE}")
