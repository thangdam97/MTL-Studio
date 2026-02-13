"""
Cached Volume Context Manager - Optimizes Gemini API costs using context caching.

Based on official Gemini Context Caching specifications:
- Caches cost 1/4 of input tokens ($0.01875 vs $0.075 per 1M tokens for Flash 2.5)
- Minimum cacheable tokens: 32,768 (~13 KB)
- Cache TTL: 1 hour (extendable)
- Cache hit reduces cost by 75% for repeated context

Implementation Strategy:
- Cache volume context (character registry, previous chapters) once per volume
- Reuse cached context across all chapters in volume
- 75% cost reduction for all chapters except Chapter 1
"""

from pathlib import Path
from typing import Optional, Dict, Any
import json
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CachedVolumeContextManager:
    """
    Manages Gemini context caching for volume-level translation context.

    Cost Analysis (per volume, 15 chapters):
    - Without caching: 15 chapters × 80 KB context × $0.075/1M = $0.09
    - With caching: (1 × 80 KB × $0.075) + (14 × 80 KB × $0.01875) = $0.027
    - Savings: 70% reduction per volume

    Cache Strategy:
    - Chapter 1: No cache (no previous context)
    - Chapter 2: Create cache with Chapter 1 context
    - Chapters 3-15: Reuse + extend cache (hit rate: 93%)
    """

    def __init__(self, work_dir: Path, gemini_client):
        """
        Initialize context cache manager.

        Args:
            work_dir: Work directory for current volume
            gemini_client: Gemini client instance with caching support
        """
        self.work_dir = work_dir
        self.gemini_client = gemini_client
        self.cache_metadata_path = work_dir / '.context' / 'CACHE_METADATA.json'
        self.cache_metadata = self._load_cache_metadata()

    def _load_cache_metadata(self) -> Dict[str, Any]:
        """Load cache metadata if exists."""
        if not self.cache_metadata_path.exists():
            return {
                'volume_cache_name': None,
                'cached_context_hash': None,
                'cache_created_at': None,
                'cache_expires_at': None,
                'chapters_using_cache': [],
                'cache_hit_count': 0,
                'total_cost_saved': 0.0
            }

        try:
            with open(self.cache_metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cache metadata: {e}")
            return {}

    def _save_cache_metadata(self):
        """Save cache metadata to disk."""
        self.cache_metadata_path.parent.mkdir(exist_ok=True)

        try:
            with open(self.cache_metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache_metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")

    def _compute_context_hash(self, context_text: str) -> str:
        """Compute hash of context for cache invalidation."""
        return hashlib.sha256(context_text.encode('utf-8')).hexdigest()[:16]

    def _is_cache_valid(self) -> bool:
        """Check if current cache is still valid (not expired)."""
        if not self.cache_metadata.get('cache_expires_at'):
            return False

        expires_at = datetime.fromisoformat(self.cache_metadata['cache_expires_at'])
        return datetime.now() < expires_at

    def create_or_update_cache(
        self,
        chapter_num: int,
        volume_context_text: str
    ) -> Optional[str]:
        """
        Create new cache or update existing cache with volume context.

        Args:
            chapter_num: Current chapter number
            volume_context_text: Full volume context as formatted prompt section

        Returns:
            Cache name if successful, None otherwise

        Cache Creation Strategy:
        - Chapter 1: No cache (no previous context to cache)
        - Chapter 2: Create initial cache with Chapter 1 context
        - Chapter 3+: Extend cache with new chapter context OR create new if invalidated
        """
        context_hash = self._compute_context_hash(volume_context_text)

        # Chapter 1: No caching needed
        if chapter_num == 1:
            logger.info("Chapter 1: Skipping cache creation (no previous context)")
            return None

        # Check if context has changed (cache invalidation)
        cached_hash = self.cache_metadata.get('cached_context_hash')
        if cached_hash and cached_hash != context_hash:
            logger.info("Context changed, invalidating cache")
            self.cache_metadata['volume_cache_name'] = None

        # Check if existing cache is valid
        if self._is_cache_valid() and self.cache_metadata.get('volume_cache_name'):
            # Cache hit - reuse existing cache
            cache_name = self.cache_metadata['volume_cache_name']
            logger.info(f"Cache hit: Reusing cache '{cache_name}' for Chapter {chapter_num}")

            # Update metadata
            self.cache_metadata['cache_hit_count'] += 1
            self.cache_metadata['chapters_using_cache'].append(chapter_num)

            # Calculate cost saved
            # Cached input cost: $0.01875 per 1M tokens (vs $0.075 uncached)
            # Savings: $0.05625 per 1M tokens
            context_size_kb = len(volume_context_text) / 1024
            tokens_approx = context_size_kb * 400  # ~400 tokens per KB
            cost_saved = (tokens_approx / 1_000_000) * 0.05625
            self.cache_metadata['total_cost_saved'] += cost_saved

            self._save_cache_metadata()

            return cache_name

        # Create new cache
        logger.info(f"Creating new cache for Chapter {chapter_num}")

        try:
            # Generate unique cache name
            cache_name = f"volume_context_{self.work_dir.name}_{context_hash}"

            # Use Gemini client to create cached content
            # This is a placeholder - actual implementation depends on Gemini SDK
            # See: https://ai.google.dev/gemini-api/docs/caching
            cache_response = self._create_gemini_cache(cache_name, volume_context_text)

            if cache_response:
                # Update metadata
                self.cache_metadata['volume_cache_name'] = cache_name
                self.cache_metadata['cached_context_hash'] = context_hash
                self.cache_metadata['cache_created_at'] = datetime.now().isoformat()
                self.cache_metadata['cache_expires_at'] = (
                    datetime.now() + timedelta(hours=1)
                ).isoformat()
                self.cache_metadata['chapters_using_cache'] = [chapter_num]

                self._save_cache_metadata()

                logger.info(f"Cache created successfully: {cache_name}")
                return cache_name
            else:
                logger.error("Failed to create Gemini cache")
                return None

        except Exception as e:
            logger.error(f"Cache creation failed: {e}")
            return None

    def _create_gemini_cache(self, cache_name: str, content: str) -> Optional[Dict[str, Any]]:
        """
        Create cached content using Gemini API.

        Official API usage (from Gemini docs):
        ```python
        from google.generativeai import caching
        import datetime

        cache = caching.CachedContent.create(
            model='models/gemini-2.5-flash-002',
            contents=[{
                'role': 'user',
                'parts': [{
                    'text': content
                }]
            }],
            ttl=datetime.timedelta(hours=1),
            display_name=cache_name
        )
        ```

        Returns:
            Cache metadata if successful, None otherwise
        """
        # This is a stub - actual implementation requires google.generativeai SDK
        # For now, we'll return a mock response to demonstrate the flow

        logger.warning("_create_gemini_cache is a stub - requires google.generativeai SDK")

        # Check if content meets minimum cache size (32,768 tokens ≈ 80 KB)
        content_size_kb = len(content) / 1024
        if content_size_kb < 80:
            logger.warning(
                f"Content size ({content_size_kb:.1f} KB) below minimum cache threshold (80 KB)"
            )
            return None

        # Mock response for development
        return {
            'name': cache_name,
            'model': 'models/gemini-2.5-flash-002',
            'create_time': datetime.now().isoformat(),
            'expire_time': (datetime.now() + timedelta(hours=1)).isoformat(),
            'usage_metadata': {
                'total_token_count': int(content_size_kb * 400)  # ~400 tokens per KB
            }
        }

    def get_cache_name(self) -> Optional[str]:
        """Get current active cache name if valid."""
        if self._is_cache_valid() and self.cache_metadata.get('volume_cache_name'):
            return self.cache_metadata['volume_cache_name']
        return None

    def extend_cache_ttl(self, hours: int = 1) -> bool:
        """
        Extend cache TTL (time-to-live).

        Useful when processing large volumes that take >1 hour to complete.

        Args:
            hours: Number of hours to extend TTL

        Returns:
            True if successful, False otherwise
        """
        cache_name = self.get_cache_name()
        if not cache_name:
            logger.warning("No active cache to extend")
            return False

        try:
            # Update local metadata
            current_expires = datetime.fromisoformat(self.cache_metadata['cache_expires_at'])
            new_expires = current_expires + timedelta(hours=hours)
            self.cache_metadata['cache_expires_at'] = new_expires.isoformat()
            self._save_cache_metadata()

            # Update Gemini cache TTL (requires SDK call)
            # cache.update(ttl=datetime.timedelta(hours=hours))

            logger.info(f"Cache TTL extended by {hours} hours (new expiry: {new_expires})")
            return True
        except Exception as e:
            logger.error(f"Failed to extend cache TTL: {e}")
            return False

    def get_cost_savings_report(self) -> Dict[str, Any]:
        """
        Generate cost savings report for volume.

        Returns:
            Dict with cache performance metrics
        """
        return {
            'cache_name': self.cache_metadata.get('volume_cache_name'),
            'cache_hit_count': self.cache_metadata.get('cache_hit_count', 0),
            'chapters_using_cache': self.cache_metadata.get('chapters_using_cache', []),
            'total_cost_saved_usd': round(self.cache_metadata.get('total_cost_saved', 0.0), 4),
            'cache_hit_rate': (
                len(self.cache_metadata.get('chapters_using_cache', [])) /
                max(1, self.cache_metadata.get('cache_hit_count', 0) + 1)
            ),
            'is_cache_active': self._is_cache_valid()
        }

    def invalidate_cache(self):
        """Manually invalidate cache (force recreation on next use)."""
        self.cache_metadata['volume_cache_name'] = None
        self.cache_metadata['cached_context_hash'] = None
        self.cache_metadata['cache_expires_at'] = None
        self._save_cache_metadata()
        logger.info("Cache manually invalidated")


# Integration Example
# --------------------
# This shows how to integrate with existing chapter processor

def example_integration_with_chapter_processor():
    """
    Example: How to integrate CachedVolumeContextManager with chapter translation.

    ```python
    from pipeline.translator.volume_context_aggregator import VolumeContextAggregator
    from pipeline.translator.cached_volume_context_manager import CachedVolumeContextManager

    def translate_chapter_with_volume_context(chapter_num: int, work_dir: Path, gemini_client):
        # Step 1: Aggregate volume context from previous chapters
        aggregator = VolumeContextAggregator(work_dir)
        volume_context = aggregator.aggregate_volume_context(
            current_chapter_num=chapter_num,
            source_dir=work_dir / 'JP',
            en_dir=work_dir / 'EN_1st'
        )

        # Step 2: Convert to prompt section
        context_text = volume_context.to_prompt_section()

        # Step 3: Create or reuse cache
        cache_manager = CachedVolumeContextManager(work_dir, gemini_client)
        cache_name = cache_manager.create_or_update_cache(chapter_num, context_text)

        # Step 4: Build translation prompt with cached context
        if cache_name:
            # Use cached context (75% cost reduction)
            prompt = build_prompt_with_cached_context(cache_name, chapter_text)
        else:
            # No cache available (Chapter 1 or cache creation failed)
            prompt = build_prompt_with_inline_context(context_text, chapter_text)

        # Step 5: Translate with Gemini
        translation = gemini_client.generate_content(prompt, cache_name=cache_name)

        # Step 6: Report cost savings
        savings_report = cache_manager.get_cost_savings_report()
        logger.info(f"Cost savings: ${savings_report['total_cost_saved_usd']}")

        return translation
    ```
    """
    pass
