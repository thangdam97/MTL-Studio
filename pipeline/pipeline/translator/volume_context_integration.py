"""
Volume Context Integration for ChapterProcessor.
Adds volume-level translation context support with caching optimization.

Integration Instructions:
1. Add this import to chapter_processor.py:
   from pipeline.translator.volume_context_integration import VolumeContextIntegration

2. In ChapterProcessor.__init__(), add:
   self.volume_context = VolumeContextIntegration(
       work_dir=work_dir,  # Pass from agent
       gemini_client=self.client
   )

3. In translate_chapter(), after line 832 (context_str = self.context_manager.get_context_prompt):
   # Get volume-level context
   volume_context_text, volume_cache_name = self.volume_context.get_volume_context(
       chapter_id=chapter_id,
       source_dir=source_path.parent,
       en_dir=output_path.parent
   )

4. In _build_user_prompt(), add parameter:
   volume_context: Optional[str] = None

5. In _build_user_prompt(), after line 1786 (previous_context=context_str):
   volume_context=volume_context_text if volume_context_text else None

6. In prompt_loader.build_translation_prompt(), inject volume context before source text
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import logging
import re

from pipeline.translator.volume_context_aggregator import (
    VolumeContextAggregator,
    VolumeContext
)
from pipeline.translator.cached_volume_context_manager import CachedVolumeContextManager

logger = logging.getLogger(__name__)


class VolumeContextIntegration:
    """
    Integration layer for volume-level context in chapter translation.

    Manages:
    - Context aggregation from previous chapters
    - Context caching for cost reduction
    - Cache lifecycle (creation, hits, expiration)
    - Integration with ChapterProcessor
    """

    def __init__(self, work_dir: Path, gemini_client):
        """
        Initialize volume context integration.

        Args:
            work_dir: Work directory for current volume
            gemini_client: GeminiClient instance for context caching
        """
        self.work_dir = work_dir
        self.gemini_client = gemini_client

        # Initialize aggregator and cache manager
        self.aggregator = VolumeContextAggregator(work_dir)
        self.cache_manager = CachedVolumeContextManager(work_dir, gemini_client)

        # Track current volume context
        self.current_volume_context: Optional[VolumeContext] = None
        self.current_cache_name: Optional[str] = None

        logger.info(f"✓ Volume context integration initialized for: {work_dir.name}")

    def get_volume_context(
        self,
        chapter_id: str,
        source_dir: Path,
        en_dir: Path
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get volume-level context for chapter translation with caching.

        Args:
            chapter_id: Chapter identifier (e.g., "CHAPTER_05")
            source_dir: Directory containing JP source chapters
            en_dir: Directory containing EN translated chapters

        Returns:
            Tuple of (context_text, cache_name):
            - context_text: Formatted volume context prompt section (None if Chapter 1)
            - cache_name: Gemini cache resource name (None if not cached)

        Workflow:
        1. Extract chapter number from chapter_id
        2. Aggregate context from previous chapters (if any)
        3. Create or reuse cache
        4. Return formatted context + cache name
        """
        # Extract chapter number
        chapter_num = self._extract_chapter_number(chapter_id)

        if chapter_num is None:
            logger.warning(f"Could not extract chapter number from: {chapter_id}")
            return (None, None)

        # Chapter 1: No previous context
        if chapter_num == 1:
            logger.info(f"[VOLUME-CTX] Chapter 1: No previous context available")
            return (None, None)

        # Aggregate volume context from previous chapters
        logger.info(f"[VOLUME-CTX] Aggregating context from Chapters 1-{chapter_num-1}...")

        volume_context = self.aggregator.aggregate_volume_context(
            current_chapter_num=chapter_num,
            source_dir=source_dir,
            en_dir=en_dir
        )

        # Convert to formatted prompt section
        context_text = volume_context.to_prompt_section()

        if not context_text or len(context_text) < 100:
            logger.warning(f"[VOLUME-CTX] Volume context too small or empty, skipping caching")
            return (context_text, None)

        # Create or reuse cache for cost optimization
        cache_name = self.cache_manager.create_or_update_cache(
            chapter_num=chapter_num,
            volume_context_text=context_text
        )

        # Store for later reference
        self.current_volume_context = volume_context
        self.current_cache_name = cache_name

        # Log results
        context_size_kb = len(context_text) / 1024
        if cache_name:
            logger.info(
                f"[VOLUME-CTX] ✓ Context ready: {context_size_kb:.1f} KB, "
                f"cached as: {cache_name[:50]}..."
            )
        else:
            logger.info(
                f"[VOLUME-CTX] ✓ Context ready: {context_size_kb:.1f} KB (uncached)"
            )

        return (context_text, cache_name)

    def get_cost_savings_report(self) -> Dict[str, Any]:
        """Generate cost savings report for volume."""
        return self.cache_manager.get_cost_savings_report()

    def invalidate_cache(self):
        """Manually invalidate cache (useful for debugging/retranslation)."""
        self.cache_manager.invalidate_cache()
        logger.info("[VOLUME-CTX] Cache manually invalidated")

    def extend_cache_ttl(self, hours: int = 1) -> bool:
        """
        Extend cache TTL for large volumes that take >1 hour to translate.

        Args:
            hours: Number of hours to extend

        Returns:
            True if successful
        """
        return self.cache_manager.extend_cache_ttl(hours)

    def _extract_chapter_number(self, chapter_id: str) -> Optional[int]:
        """
        Extract chapter number from chapter_id.

        Supports formats:
        - "CHAPTER_05" → 5
        - "Chapter 5" → 5
        - "Ch05" → 5
        - "05" → 5
        """
        # Try standard format: CHAPTER_05
        match = re.search(r'CHAPTER[_\s]*(\d+)', chapter_id, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Try short format: Ch05
        match = re.search(r'CH[_\s]*(\d+)', chapter_id, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Try bare number: 05
        match = re.search(r'^(\d+)$', chapter_id)
        if match:
            return int(match.group(1))

        return None


# === Integration Example for ChapterProcessor ===

def example_chapter_processor_integration():
    """
    Example showing how to integrate VolumeContextIntegration into ChapterProcessor.

    Modifications needed:

    1. In ChapterProcessor.__init__():
    ```python
    def __init__(
        self,
        gemini_client: GeminiClient,
        prompt_loader: PromptLoader,
        context_manager: ContextManager,
        target_language: str = "en",
        work_dir: Optional[Path] = None  # ADD THIS PARAMETER
    ):
        # ... existing initialization ...

        # Initialize volume context integration (NEW)
        self.volume_context_integration = None
        if work_dir:
            self.volume_context_integration = VolumeContextIntegration(
                work_dir=work_dir,
                gemini_client=self.client
            )
            logger.info("✓ Volume-level context integration enabled")
    ```

    2. In translate_chapter(), after getting context_str (line ~834):
    ```python
    # Get Context (Continuity)
    logger.debug(f"[VERBOSE] Getting context prompt...")
    context_str = self.context_manager.get_context_prompt(chapter_id)
    logger.debug(f"[VERBOSE] Context length: {len(context_str)} characters")

    # Get Volume-Level Context (NEW)
    volume_context_text = None
    volume_cache_name = None
    if self.volume_context_integration:
        volume_context_text, volume_cache_name = self.volume_context_integration.get_volume_context(
            chapter_id=chapter_id,
            source_dir=source_path.parent,
            en_dir=output_path.parent
        )

        # If volume cache exists, use it instead of effective_cache
        if volume_cache_name:
            effective_cache = volume_cache_name
            logger.info(f"[VOLUME-CACHE] Using volume-level cache: {volume_cache_name[:50]}...")
    ```

    3. In _build_user_prompt(), add volume_context parameter:
    ```python
    def _build_user_prompt(
        self,
        chapter_id: str,
        source_text: str,
        context_str: str,
        chapter_title: Optional[str] = None,
        sino_vn_guidance: Optional[Dict] = None,
        gap_flags: Optional[Dict] = None,
        dialect_guidance: Optional[str] = None,
        en_pattern_guidance: Optional[Dict] = None,
        vn_pattern_guidance: Optional[Dict] = None,
        visual_guidance: Optional[str] = None,
        scene_plan: Optional[Dict[str, Any]] = None,
        volume_context: Optional[str] = None,  # NEW PARAMETER
    ) -> str:
        # ... existing code ...

        # Inject Volume Context before source text (NEW)
        if volume_context:
            logger.debug(f"[VOLUME-CTX] Injecting volume context ({len(volume_context)} chars)")
            base_prompt = f"{base_prompt}\n\n{volume_context}"

        return base_prompt
    ```

    4. In translate_chapter(), pass volume_context to _build_user_prompt (line ~839):
    ```python
    user_prompt = self._build_user_prompt(
        chapter_id,
        source_content_only,
        context_str,
        en_title,
        sino_vn_guidance=sino_vn_guidance,
        gap_flags=gap_flags,
        dialect_guidance=dialect_guidance,
        en_pattern_guidance=en_pattern_guidance,
        vn_pattern_guidance=vn_pattern_guidance,
        visual_guidance=visual_guidance,
        scene_plan=scene_plan,
        volume_context=volume_context_text,  # NEW ARGUMENT
    )
    ```

    5. After translation completes, optionally log cost savings:
    ```python
    # Log volume context cost savings
    if self.volume_context_integration:
        savings_report = self.volume_context_integration.get_cost_savings_report()
        if savings_report['cache_hit_count'] > 0:
            logger.info(
                f"[VOLUME-CACHE] Cost savings: ${savings_report['total_cost_saved_usd']:.4f} "
                f"({savings_report['cache_hit_count']} cache hits)"
            )
    ```
    """
    pass


# === Prompt Loader Integration Example ===

def example_prompt_loader_integration():
    """
    Example showing how to modify PromptLoader.build_translation_prompt()
    to inject volume context.

    Modifications needed in prompt_loader.py:

    ```python
    def build_translation_prompt(
        self,
        source_text: str,
        chapter_title: str = "",
        chapter_id: str = "",
        previous_context: Optional[str] = None,
        name_registry: Optional[Dict[str, str]] = None,
        volume_context: Optional[str] = None,  # NEW PARAMETER
    ) -> str:
        # ... existing code to load template ...

        # === VOLUME CONTEXT INJECTION (NEW) ===
        # Insert volume context BEFORE source text for best Gemini performance
        # Per official Gemini docs: "put query at END after all context"
        if volume_context:
            # Insert volume context section
            volume_section = f'''
---

# VOLUME-LEVEL CONTEXT

{volume_context}

---
'''
            # Insert before source text
            prompt = prompt.replace(
                '# SOURCE TEXT',
                f'{volume_section}\n\n# SOURCE TEXT'
            )

        # ... rest of existing code ...

        return prompt
    ```

    This ensures volume context appears in the prompt BEFORE the source text,
    following Gemini's best practice: "context first, query last".
    """
    pass
