"""
Manga Vector Store.

ChromaDB-backed semantic search over manga panel analyses.
Follows the same pattern as modules/sino_vietnamese_store.py
wrapping modules/vector_search.py's PatternVectorStore.

Each document = one manga panel's analysis.
Collection per volume: manga_panels_{volume_id}

🧪 EXPERIMENTAL — Phase 1.8b
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ChromaDB
try:
    import chromadb
    from chromadb.config import Settings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Gemini embeddings
try:
    from google import genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


@dataclass
class PanelSearchResult:
    """Result from a manga panel vector search."""

    panel_id: str
    page_number: int
    chapter_number: Optional[int]
    similarity: float
    speaker: Optional[str]
    characters: List[str]
    expression: Optional[str]
    body_language: Optional[str]
    dialogue_jp: Optional[str]
    dialogue_context: Optional[str]
    atmosphere: Optional[str]
    emotional_intensity: float
    narrative_beat: Optional[str]
    page_summary: Optional[str]


class MangaVectorStore:
    """
    ChromaDB-backed vector store for manga panel retrieval.

    Collection: manga_panels_{volume_id}

    Each document = one panel's composite embedding text.
    Metadata includes chapter, page, speaker, characters, emotional_intensity.
    Embedding source: panel description + dialogue context (built by build_embedding_text).
    """

    COLLECTION_PREFIX = "manga_panels"

    # Retrieval thresholds
    THRESHOLD_INJECT = 0.80  # High confidence → inject into prompt
    THRESHOLD_LOG = 0.65  # Medium confidence → log for review

    def __init__(
        self,
        volume_path: Path,
        volume_id: str,
        persist_directory: str = "chroma_manga",
        gemini_api_key: Optional[str] = None,
    ):
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB required: pip install chromadb>=0.4.0")

        self.volume_path = volume_path
        self.volume_id = volume_id
        self.persist_dir = volume_path / persist_directory
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.collection_name = f"{self.COLLECTION_PREFIX}_{volume_id}"

        # ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # Gemini embedding client
        api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        if GEMINI_AVAILABLE and api_key:
            self.gemini_client = genai.Client(api_key=api_key)
            self._embedding_model = "gemini-embedding-001"
        else:
            self.gemini_client = None
            logger.warning("[MANGA] Gemini client not initialized — embeddings unavailable")

        logger.info(
            f"[MANGA] Vector store ready: {self.collection_name} "
            f"({self.collection.count()} documents)"
        )

    # ─── Embedding ───────────────────────────────────────────────────

    def _embed(self, text: str) -> List[float]:
        """Generate embedding for a text string."""
        if not self.gemini_client:
            raise RuntimeError("Gemini client not initialized for embeddings")
        result = self.gemini_client.models.embed_content(
            model=self._embedding_model,
            contents=text,
        )
        return result.embeddings[0].values

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embed multiple texts."""
        if not self.gemini_client:
            raise RuntimeError("Gemini client not initialized for embeddings")
        result = self.gemini_client.models.embed_content(
            model=self._embedding_model,
            contents=texts,
        )
        return [e.values for e in result.embeddings]

    # ─── Indexing ────────────────────────────────────────────────────

    def index_panels(
        self,
        panels: List[Dict[str, Any]],
        batch_size: int = 50,
    ) -> int:
        """
        Index manga panels into ChromaDB.

        Args:
            panels: List of panel analysis dicts (from MangaCacheManager.get_all_panels)
            batch_size: Number of panels to embed per API call

        Returns:
            Number of panels indexed
        """
        if not panels:
            logger.warning("[MANGA] No panels to index")
            return 0

        indexed = 0

        for i in range(0, len(panels), batch_size):
            batch = panels[i : i + batch_size]

            ids = []
            documents = []
            metadatas = []

            for panel in batch:
                panel_id = panel.get("panel_id", f"unknown_{i}")
                embed_text = build_embedding_text(panel)

                if not embed_text.strip():
                    continue

                ids.append(panel_id)
                documents.append(embed_text)
                metadatas.append(
                    {
                        "chapter_number": panel.get("chapter_number") or -1,
                        "page_number": panel.get("page_number", -1),
                        "panel_index": panel.get("panel_index", 0),
                        "speaker": panel.get("speaker") or "",
                        "characters": ", ".join(panel.get("characters_present", [])),
                        "emotional_intensity": panel.get("emotional_intensity", 0.0),
                        "narrative_beat": panel.get("narrative_beat") or "",
                        "has_dialogue": bool(panel.get("dialogue_jp")),
                    }
                )

            if not ids:
                continue

            # Embed and upsert
            try:
                embeddings = self._embed_batch(documents)
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                indexed += len(ids)
                logger.info(
                    f"[MANGA] Indexed batch {i // batch_size + 1}: "
                    f"{len(ids)} panels (total: {indexed})"
                )
            except Exception as e:
                logger.error(f"[MANGA] Batch indexing failed: {e}")
                continue

        logger.info(f"[MANGA] ✓ Indexed {indexed} panels into {self.collection_name}")
        return indexed

    # ─── Query ───────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        n_results: int = 4,
        where: Optional[Dict[str, Any]] = None,
        min_similarity: float = 0.0,
    ) -> List[PanelSearchResult]:
        """
        Semantic search for manga panels.

        Args:
            query_text: Search query (segment text, dialogue, etc.)
            n_results: Max results to return
            where: ChromaDB metadata filter (e.g., {"chapter_number": 3})
            min_similarity: Minimum cosine similarity threshold

        Returns:
            List of PanelSearchResult sorted by similarity (descending)
        """
        try:
            query_embedding = self._embed(query_text)
        except Exception as e:
            logger.error(f"[MANGA] Query embedding failed: {e}")
            return []

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = self.collection.query(**kwargs)
        except Exception as e:
            logger.error(f"[MANGA] ChromaDB query failed: {e}")
            return []

        panel_results = []
        if results and results["ids"] and results["ids"][0]:
            for idx, panel_id in enumerate(results["ids"][0]):
                # ChromaDB returns distance; convert to similarity
                distance = results["distances"][0][idx]
                similarity = 1.0 - distance  # cosine distance → similarity

                if similarity < min_similarity:
                    continue

                meta = results["metadatas"][0][idx] if results["metadatas"] else {}

                panel_results.append(
                    PanelSearchResult(
                        panel_id=panel_id,
                        page_number=meta.get("page_number", -1),
                        chapter_number=meta.get("chapter_number"),
                        similarity=round(similarity, 4),
                        speaker=meta.get("speaker") or None,
                        characters=(
                            meta.get("characters", "").split(", ")
                            if meta.get("characters")
                            else []
                        ),
                        expression=None,  # Not stored in metadata (in document text)
                        body_language=None,
                        dialogue_jp=None,
                        dialogue_context=None,
                        atmosphere=None,
                        emotional_intensity=meta.get("emotional_intensity", 0.0),
                        narrative_beat=meta.get("narrative_beat") or None,
                        page_summary=None,
                    )
                )

        panel_results.sort(key=lambda r: r.similarity, reverse=True)
        return panel_results

    # ─── Utilities ───────────────────────────────────────────────────

    def count(self) -> int:
        """Return number of indexed panels."""
        return self.collection.count()

    def clear(self) -> None:
        """Delete and recreate the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"[MANGA] Cleared collection: {self.collection_name}")


# ─── Embedding Text Builder ─────────────────────────────────────────────

def build_embedding_text(panel: Dict[str, Any]) -> str:
    """
    Build composite text for embedding from a manga panel analysis.

    Combines characters, speaker, dialogue, expression, and body language
    into a single searchable text string.
    """
    parts = []

    if panel.get("characters_present"):
        parts.append(f"Characters: {', '.join(panel['characters_present'])}")

    if panel.get("speaker"):
        parts.append(f"Speaker: {panel['speaker']}")

    if panel.get("dialogue_jp"):
        parts.append(f"Dialogue: {panel['dialogue_jp']}")

    if panel.get("expression"):
        parts.append(f"Expression: {panel['expression']}")

    if panel.get("body_language"):
        parts.append(f"Body language: {panel['body_language']}")

    if panel.get("dialogue_context"):
        parts.append(f"Context: {panel['dialogue_context']}")

    if panel.get("atmosphere"):
        parts.append(f"Atmosphere: {panel['atmosphere']}")

    if panel.get("action"):
        parts.append(f"Action: {panel['action']}")

    return " | ".join(parts)
