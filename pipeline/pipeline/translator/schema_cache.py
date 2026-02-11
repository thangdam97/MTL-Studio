"""
Schema Cache Manager - Gemini Context Caching for Continuity
Manages caching of schema for injection into next chapter's translation.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta

try:
    from pipeline.common.genai_factory import create_genai_client
except ImportError:
    create_genai_client = None

from pipeline.translator.schema_extractor import ChapterSnapshot

logger = logging.getLogger(__name__)


class SchemaCacheManager:
    """Manage schema caching for continuity between chapters."""
    
    def __init__(self, client=None):
        """
        Initialize cache manager.
        
        Args:
            client: Gemini client instance (optional, will create if None)
        """
        self.client = client
        self.current_cache = None
        self.cache_metadata_path = None
    
    def _ensure_client(self):
        """Ensure Gemini client is initialized."""
        if self.client is None and create_genai_client:
            self.client = create_genai_client()
    
    def cache_schema(
        self,
        snapshot: ChapterSnapshot,
        work_dir: Path,
        model: str = 'models/gemini-2.0-flash-exp',
        ttl_hours: int = 1
    ) -> Optional[str]:
        """
        Cache chapter schema for next chapter's translation.
        
        Args:
            snapshot: Chapter snapshot to cache
            work_dir: Working directory for metadata storage
            model: Gemini model to use
            ttl_hours: Time-to-live in hours
            
        Returns:
            Cache name if successful, None otherwise
        """
        if create_genai_client is None:
            logger.warning("google-genai not available, skipping cache")
            return None
        
        try:
            self._ensure_client()
            
            # Build context from schema
            context = self._build_context_from_schema(snapshot)
            system_instruction = self._build_system_instruction(snapshot)
            
            # Create cache
            cache_name = f"schema_ch{snapshot.chapter_num:02d}_for_ch{snapshot.chapter_num+1:02d}"
            
            logger.info(f"Creating cache: {cache_name}")
            logger.info(f"  TTL: {ttl_hours} hour(s)")
            logger.info(f"  Context size: ~{len(context)} chars")
            
            cache = self.client.caches.create(
                model=model,
                display_name=cache_name,
                system_instruction=system_instruction,
                contents=[context],
                ttl=f'{ttl_hours * 3600}s'  # Convert to seconds
            )
            
            self.current_cache = cache
            
            # Save cache metadata
            self._save_cache_metadata(snapshot, cache, work_dir)
            
            logger.info(f"✓ Cache created: {cache.name}")
            logger.info(f"  Expires: {cache.expire_time}")
            
            return cache.name
        
        except Exception as e:
            logger.error(f"Failed to create cache: {e}")
            return None
    
    def get_cached_content_name(self, work_dir: Path, chapter_num: int) -> Optional[str]:
        """
        Get cached content name for a chapter.
        
        Args:
            work_dir: Working directory
            chapter_num: Chapter number to get cache for
            
        Returns:
            Cache name if exists and valid, None otherwise
        """
        metadata_path = work_dir / ".context" / f"cache_ch{chapter_num:02d}.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Check if cache is still valid
            expire_time = datetime.fromisoformat(metadata['expire_time'].replace('Z', '+00:00'))
            if datetime.now(expire_time.tzinfo) >= expire_time:
                logger.warning(f"Cache for Ch{chapter_num} expired")
                return None
            
            logger.info(f"Found valid cache for Ch{chapter_num}: {metadata['cache_name']}")
            return metadata['cache_name']
        
        except Exception as e:
            logger.error(f"Error reading cache metadata: {e}")
            return None
    
    def invalidate_cache(self, cache_name: str):
        """Delete a cache."""
        if genai is None or not cache_name:
            return
        
        try:
            self._ensure_client()
            self.client.caches.delete(name=cache_name)
            logger.info(f"✓ Invalidated cache: {cache_name}")
        except Exception as e:
            logger.warning(f"Could not delete cache {cache_name}: {e}")
    
    def _build_context_from_schema(self, snapshot: ChapterSnapshot) -> str:
        """Build context string from schema snapshot."""
        lines = []
        
        lines.append("# CONTINUITY CONTEXT")
        lines.append(f"# From: {snapshot.chapter_id}")
        lines.append("")
        
        # Characters
        if snapshot.characters:
            lines.append("## CHARACTERS")
            for char in snapshot.characters:
                lines.append(f"- **{char.name}**")
                if char.japanese_name:
                    lines.append(f"  - Japanese: {char.japanese_name}")
                lines.append(f"  - Gender: {char.gender or 'unknown'}")
                lines.append(f"  - Role: {char.role or 'unknown'}")
                if char.archetype:
                    lines.append(f"  - Archetype: {char.archetype}")
                lines.append("")
        
        # Relationships
        if snapshot.relationships:
            lines.append("## RELATIONSHIPS")
            for rel in snapshot.relationships:
                lines.append(f"- **{rel.pair[0]} ↔ {rel.pair[1]}**")
                lines.append(f"  - Type: {rel.relationship_type}")
                lines.append(f"  - State: {rel.state}")
                if rel.pronoun_pair:
                    lines.append(f"  - Vietnamese Pronouns: {rel.pronoun_pair}")
                lines.append("")
        
        # Glossary
        if snapshot.glossary:
            lines.append("## GLOSSARY")
            for term in snapshot.glossary:
                term_name = term.romanized or term.japanese
                lines.append(f"- **{term_name}**")
                if term.english:
                    lines.append(f"  - English: {term.english}")
                if term.vietnamese:
                    lines.append(f"  - Vietnamese: {term.vietnamese}")
                if term.preserve:
                    lines.append(f"  - ⚠️ PRESERVE (do not translate)")
                lines.append("")
        
        # Narrative state
        if snapshot.narrative_flags:
            lines.append("## NARRATIVE STATE")
            for flag in snapshot.narrative_flags:
                lines.append(f"- {flag}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _build_system_instruction(self, snapshot: ChapterSnapshot) -> str:
        """Build system instruction for translation with continuity."""
        lines = []
        
        lines.append("You are translating a Japanese light novel.")
        lines.append("Use the continuity context provided to maintain consistency with previous chapters.")
        lines.append("")
        
        # Character consistency
        if snapshot.characters:
            lines.append("CHARACTER CONSISTENCY:")
            for char in snapshot.characters:
                line = f"- Always use '{char.name}' for this character"
                if char.gender:
                    line += f" ({char.gender})"
                lines.append(line)
            lines.append("")
        
        # Glossary terms
        if snapshot.glossary:
            preserve_terms = [t for t in snapshot.glossary if t.preserve]
            if preserve_terms:
                lines.append("PRESERVE THESE TERMS (do not translate):")
                for term in preserve_terms:
                    lines.append(f"- {term.romanized or term.japanese}")
                lines.append("")
        
        # Vietnamese-specific
        vn_rels = [r for r in snapshot.relationships if r.pronoun_pair]
        if vn_rels:
            lines.append("VIETNAMESE PRONOUN PAIRS:")
            for rel in vn_rels:
                lines.append(f"- {rel.pair[0]} → {rel.pair[1]}: {rel.pronoun_pair}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _save_cache_metadata(
        self,
        snapshot: ChapterSnapshot,
        cache,
        work_dir: Path
    ):
        """Save cache metadata for later retrieval."""
        context_dir = work_dir / ".context"
        context_dir.mkdir(exist_ok=True)
        
        # Save for next chapter
        next_chapter_num = snapshot.chapter_num + 1
        metadata_path = context_dir / f"cache_ch{next_chapter_num:02d}.json"
        
        metadata = {
            'cache_name': cache.name,
            'created_for_chapter': next_chapter_num,
            'from_chapter': snapshot.chapter_num,
            'created_at': datetime.now().isoformat(),
            'expire_time': cache.expire_time.isoformat() if hasattr(cache.expire_time, 'isoformat') else str(cache.expire_time),
            'model': cache.model if hasattr(cache, 'model') else 'unknown'
        }
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self.cache_metadata_path = metadata_path
        logger.info(f"✓ Saved cache metadata: {metadata_path.name}")
    
    def get_cache_info(self, work_dir: Path) -> Dict:
        """Get information about available caches."""
        context_dir = work_dir / ".context"
        if not context_dir.exists():
            return {}
        
        caches = {}
        for metadata_file in context_dir.glob("cache_ch*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                chapter_num = metadata['created_for_chapter']
                caches[chapter_num] = metadata
            except Exception as e:
                logger.warning(f"Could not read {metadata_file.name}: {e}")
        
        return caches
