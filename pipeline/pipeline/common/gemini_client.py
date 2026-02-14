"""
Gemini API Client for MT Publishing Pipeline.
Shared between Translator and Critics agents.
"""

import time
import logging
import re
import hashlib
import backoff
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from google.genai import types
from pipeline.common.genai_factory import create_genai_client, resolve_api_key, resolve_genai_backend

logger = logging.getLogger(__name__)

@dataclass
class GeminiResponse:
    content: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    model: str
    cached_tokens: int = 0  # Track cached input tokens
    thinking_content: Optional[str] = None  # CoT/thinking parts from model

class GeminiClient:
    _CACHE_DISPLAY_NAME_MAX_LEN = 128

    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-2.5-pro",
        enable_caching: bool = True,
        backend: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
    ):
        """Initialize Gemini client with optional context caching."""
        self.backend = resolve_genai_backend(backend)
        self.api_key = resolve_api_key(api_key=api_key, required=(self.backend == "developer"))

        self.model = model
        self.client = create_genai_client(
            api_key=self.api_key,
            backend=self.backend,
            project=project,
            location=location,
        )
        self._last_request_time = 0
        self._rate_limit_delay = 6.0  # ~10 requests/min default

        # Context caching support
        self.enable_caching = enable_caching
        self._cached_content_name = None  # Cached content resource name
        
        # Thinking mode configuration
        self.thinking_mode_config = self._load_thinking_config()
        self._cache_created_at = None
        self._cache_ttl_minutes = 120  # Default 2 hour TTL
        self._cached_model = None  # Track which model the cache was created for
    
    def _load_thinking_config(self) -> Dict[str, Any]:
        """Load thinking mode configuration from config.yaml."""
        try:
            from pipeline.config import get_config_section
            gemini_config = get_config_section('gemini')
            return gemini_config.get('thinking_mode', {
                'enabled': False,
                'thinking_level': 'medium',
                'save_to_file': False,
                'output_dir': 'THINKING'
            })
        except:
            return {'enabled': False}
    
    def _get_thinking_config(self) -> Optional[Any]:
        """Get ThinkingConfig for Gemini API if thinking mode is enabled."""
        if not self.thinking_mode_config.get('enabled', False):
            return None
        
        try:
            thinking_level = self.thinking_mode_config.get('thinking_level', 'medium')
            
            # Gemini 3 uses thinking_level, Gemini 2.5 uses thinking_budget
            if 'gemini-3' in self.model.lower():
                return types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level=thinking_level  # minimal, low, medium, high
                )
            else:
                # Gemini 2.5 - use thinking_budget instead
                # -1 = dynamic (default), 0 = disabled, >0 = specific token budget
                return types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=-1  # Dynamic thinking for Gemini 2.5
                )
        except Exception as e:
            logger.debug(f"ThinkingConfig not available: {e}")
            return None

    def set_rate_limit(self, requests_per_minute: int):
        """Update rate limit delay."""
        if requests_per_minute > 0:
            self._rate_limit_delay = 60.0 / requests_per_minute

    def set_cache_ttl(self, minutes: int):
        """Set cache TTL in minutes (max 120)."""
        self._cache_ttl_minutes = min(minutes, 120)

    def _sanitize_cache_display_name(self, display_name: Optional[str]) -> Optional[str]:
        """
        Normalize cache display_name to satisfy API constraints.

        Gemini cache API requires display_name length <= 128.
        We enforce ASCII-safe names and hard-cap by byte length.
        """
        if display_name is None:
            return None

        raw = str(display_name).strip()
        if not raw:
            return None

        # Keep ASCII letters/digits plus dot/dash/underscore only.
        # Non-ASCII is normalized away to avoid byte-length surprises.
        has_non_ascii = any(ord(ch) > 127 for ch in raw)
        normalized = re.sub(r"\s+", "_", raw)
        normalized = re.sub(r"[^A-Za-z0-9.\-]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("._-")
        if not normalized:
            normalized = "cache"

        # If source contains non-ASCII, append deterministic hash suffix so
        # heavily-normalized display names remain traceable/unique.
        if has_non_ascii:
            short_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
            candidate = f"{normalized}-{short_hash}"
            if len(candidate.encode("utf-8")) <= self._CACHE_DISPLAY_NAME_MAX_LEN:
                normalized = candidate
            else:
                head_len = self._CACHE_DISPLAY_NAME_MAX_LEN - len(short_hash) - 1
                if head_len < 1:
                    normalized = short_hash[: self._CACHE_DISPLAY_NAME_MAX_LEN]
                else:
                    normalized = f"{normalized[:head_len].rstrip('._-') or 'cache'}-{short_hash}"

        if len(normalized.encode("utf-8")) <= self._CACHE_DISPLAY_NAME_MAX_LEN:
            return normalized

        # Deterministic truncation with suffix to preserve uniqueness.
        suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        head_len = self._CACHE_DISPLAY_NAME_MAX_LEN - len(suffix) - 1  # "-<suffix>"
        if head_len < 1:
            return suffix[: self._CACHE_DISPLAY_NAME_MAX_LEN]

        head = normalized[:head_len].rstrip("._-") or "cache"
        candidate = f"{head}-{suffix}"
        if len(candidate.encode("utf-8")) > self._CACHE_DISPLAY_NAME_MAX_LEN:
            candidate = candidate[: self._CACHE_DISPLAY_NAME_MAX_LEN]
        return candidate

    def create_cache(
        self,
        *,
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        contents: Optional[List[str]] = None,
        ttl_seconds: Optional[int] = None,
        display_name: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        tool_config: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Create a Gemini cached content resource and return its name.

        Supports both:
        - System-instruction-only cache (legacy behavior)
        - Full volume cache via `contents=[...]`
        """
        if not self.enable_caching:
            return None

        target_model = model or self.model
        ttl = ttl_seconds if ttl_seconds is not None else (self._cache_ttl_minutes * 60)

        try:
            config = types.CreateCachedContentConfig(ttl=f"{int(ttl)}s")
            if display_name:
                safe_display_name = self._sanitize_cache_display_name(display_name)
                if safe_display_name != display_name:
                    logger.debug(
                        "[CACHE] display_name normalized for API constraints (charset/length): %r -> %r",
                        display_name,
                        safe_display_name,
                    )
                config.display_name = safe_display_name
            if system_instruction:
                config.system_instruction = system_instruction
            if contents:
                config.contents = contents
            # When using cached_content in generate requests, Gemini requires tools/tool_config
            # to be attached to the cache, not the generate call.
            if tools:
                config.tools = tools
            if tool_config is not None:
                config.tool_config = tool_config

            cache = self.client.caches.create(model=target_model, config=config)
            return cache.name
        except Exception as e:
            logger.warning(f"Failed to create cache (model={target_model}): {e}")
            return None

    def delete_cache(self, cache_name: str) -> bool:
        """Delete a cache by resource name."""
        if not cache_name:
            return False
        try:
            self.client.caches.delete(name=cache_name)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete cache {cache_name}: {e}")
            return False

    def _create_cached_content(self, system_instruction: str, model: str) -> str:
        """Create cached content and return resource name."""
        if not self.enable_caching:
            return None

        try:
            logger.info(f"Creating context cache for system instruction ({len(system_instruction)} chars)...")
            start_time = time.time()

            cached_content_name = self.create_cache(
                model=model,
                system_instruction=system_instruction,
                ttl_seconds=self._cache_ttl_minutes * 60,
            )
            if not cached_content_name:
                raise RuntimeError("create_cache returned no cache name")

            duration = time.time() - start_time
            self._cached_content_name = cached_content_name
            self._cache_created_at = time.time()
            self._cached_model = model  # Track model for cache validation

            logger.info(
                f"✓ Context cache created: {cached_content_name} "
                f"(TTL: {self._cache_ttl_minutes}m) in {duration:.2f}s"
            )
            return cached_content_name

        except Exception as e:
            logger.warning(f"Failed to create context cache: {e}. Falling back to non-cached mode.")
            self.enable_caching = False
            return None

    def _is_cache_valid(self, model: str = None) -> bool:
        """Check if current cache is still valid for the given model.
        
        Args:
            model: Target model to check against. If None, only checks TTL.
        """
        if not self._cached_content_name or not self._cache_created_at:
            return False
        
        # If model specified, check if cache was created for same model
        if model and self._cached_model and model != self._cached_model:
            logger.debug(f"Cache invalid: created for {self._cached_model}, but need {model}")
            return False

        # Cache expires after TTL
        age_minutes = (time.time() - self._cache_created_at) / 60
        return age_minutes < self._cache_ttl_minutes

    def clear_cache(self):
        """Clear cached content."""
        if self._cached_content_name:
            try:
                logger.info(f"Clearing context cache: {self._cached_content_name}")
                self.delete_cache(self._cached_content_name)
            except Exception as e:
                logger.warning(f"Failed to delete cache: {e}")
            finally:
                self._cached_content_name = None
                self._cache_created_at = None
                self._cached_model = None

    def warm_cache(self, system_instruction: str, model: str = None) -> bool:
        """Pre-warm cache with system instruction before first translation.
        
        Args:
            system_instruction: The system instruction to cache
            model: Target model (uses default if not specified)
            
        Returns:
            True if cache was successfully created, False otherwise
        """
        if not self.enable_caching:
            logger.debug("Cache warming skipped (caching disabled)")
            return False
            
        if self._is_cache_valid(model):
            logger.debug("Cache already valid, skipping warm-up")
            return True
            
        target_model = model or self.model
        cached_content_name = self._create_cached_content(system_instruction, target_model)
        return cached_content_name is not None

    def get_token_count(self, text: str) -> int:
        """Count tokens for text."""
        try:
            response = self.client.models.count_tokens(
                model=self.model,
                contents=text
            )
            return response.total_tokens
        except Exception as e:
            logger.warning(f"Failed to count tokens: {e}")
            # Fallback estimation: ~4 chars per token
            return len(text) // 4

    @backoff.on_exception(
        backoff.expo,
        (Exception),
        max_tries=8,
        # Give up on 400 Bad Request and safety blocks (let safety_fallback handle)
        giveup=lambda e: (
            ("400" in str(e) and "429" not in str(e)) or
            "PROHIBITED_CONTENT" in str(e).upper() or
            "FinishReason.SAFETY" in str(e) or
            "FinishReason.PROHIBITED_CONTENT" in str(e)
        )
    )
    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        temperature: float = 0.7,
        max_output_tokens: int = 65536,
        safety_settings: Dict[str, str] = None,
        model: str = None,
        cached_content: str = None,
        force_new_session: bool = False,
        generation_config: Dict[str, Any] = None,
        tools: Optional[List[Any]] = None,
    ) -> GeminiResponse:
        """
        Generate content with retry logic, rate limiting, and optional context caching.
        
        Args:
            prompt: User prompt text
            system_instruction: System instruction (ignored if cached_content provided)
            temperature: Sampling temperature
            max_output_tokens: Maximum output tokens
            safety_settings: Safety settings
            model: Model override
            cached_content: External cached content name (from schema cache)
            force_new_session: If True, ignores internal cache and starts fresh (for Amnesia Protocol)
            generation_config: Dict with temperature, top_p, top_k overrides
            tools: Optional Gemini tools (e.g., Google Search grounding)
        """
        target_model = model or self.model
        
        # Apply generation_config overrides if provided
        if generation_config:
            temperature = generation_config.get('temperature', temperature)
            max_output_tokens = generation_config.get('max_output_tokens', max_output_tokens)
            top_p = generation_config.get('top_p', 0.95)
            top_k = generation_config.get('top_k', 40)
        else:
            top_p = 0.95
            top_k = 40

        # Enforce rate limit
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)

        if safety_settings is None:
            safety_settings = [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="BLOCK_NONE")
            ]

        try:
            # Context Caching Logic
            cached_content_name = cached_content  # Use external cache if provided
            
            # AMNESIA PROTOCOL: force_new_session bypasses internal cache
            if force_new_session:
                logger.info("[AMNESIA] Forcing new session - bypassing internal cache")
                cached_content_name = cached_content  # Only use external cache if provided
            # Only create/use internal cache if no external cache provided and not forcing new session
            elif not cached_content_name and self.enable_caching:
                # Check if cache is valid for target model
                if not self._is_cache_valid(target_model):
                    # Need to create new cache (only if system_instruction provided)
                    if system_instruction:
                        # Clear old cache if model changed
                        if self._cached_content_name and self._cached_model != target_model:
                            logger.info(f"Model changed ({self._cached_model} -> {target_model}), clearing old cache...")
                            self.clear_cache()
                        
                        # Create new cache for target model
                        cached_content_name = self._create_cached_content(system_instruction, target_model)
                else:
                    # Cache is valid - reuse it
                    cached_content_name = self._cached_content_name
                    cache_age = (time.time() - self._cache_created_at) / 60
                    logger.debug(f"Using existing context cache (age: {cache_age:.1f}m / {self._cache_ttl_minutes}m, model: {self._cached_model})")
            
            elif cached_content:
                logger.debug(f"Using external cached content: {cached_content}")

            # Build config based on caching mode
            if cached_content_name:
                # Use cached content (system_instruction is in the cache)
                cache_source = "external" if cached_content else "internal"
                config_kwargs = dict(
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    max_output_tokens=max_output_tokens,
                    cached_content=cached_content_name,
                    safety_settings=safety_settings,
                    automatic_function_calling=None  # Disable AFC to prevent loops
                )
                # NOTE: tools/tool_config cannot be passed with cached_content.
                # They must be provided at cache creation time.
                if tools:
                    logger.debug(
                        "Ignoring tools in generate() because cached_content is set; "
                        "tools must be embedded in CachedContent."
                    )
                config = types.GenerateContentConfig(**config_kwargs)
                
                # Add thinking config if enabled (works with cached content too)
                thinking_config = self._get_thinking_config()
                if thinking_config:
                    config.thinking_config = thinking_config
                    logger.debug(f"Thinking mode enabled with cached content (budget: -1)")
                
                logger.debug(f"Using {cache_source} cached system instruction: {cached_content_name}")
            else:
                # Standard mode (no caching or fallback)
                config_kwargs = dict(
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    max_output_tokens=max_output_tokens,
                    system_instruction=system_instruction,
                    safety_settings=safety_settings,
                    automatic_function_calling=None  # Disable AFC to prevent loops
                )
                if tools:
                    config_kwargs["tools"] = tools
                config = types.GenerateContentConfig(**config_kwargs)
                
                # Add thinking config if enabled
                thinking_config = self._get_thinking_config()
                if thinking_config:
                    config.thinking_config = thinking_config
                    logger.debug(f"Thinking mode enabled (budget: -1 dynamic)")

            # Log API call with accurate cache status (check AFTER internal cache logic)
            logger.info(f"Calling Gemini API (model: {target_model}, cached: {bool(cached_content_name)})...")
            start_time = time.time()
            response = self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )
            duration = time.time() - start_time
            # Safely extract finish_reason (candidates can be None or empty)
            finish_reason_str = 'N/A'
            if response.candidates and len(response.candidates) > 0:
                finish_reason_str = str(response.candidates[0].finish_reason)
            logger.info(f"Received Gemini response in {duration:.2f}s (finish_reason: {finish_reason_str})")

            self._last_request_time = time.time()

            usage = response.usage_metadata
            input_tokens = usage.prompt_token_count if usage else 0
            output_tokens = usage.candidates_token_count if usage else 0

            # Safely extract cached token count
            cached_tokens = 0
            if usage and hasattr(usage, 'cached_content_token_count'):
                cached_content_tokens = usage.cached_content_token_count
                cached_tokens = cached_content_tokens if cached_content_tokens is not None else 0

            # Log cache hit stats
            if cached_tokens > 0:
                logger.info(f"✓ Cache hit: {cached_tokens} tokens cached, {input_tokens} tokens from prompt")
            
            # Extract thinking content if present
            thinking_content = None
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    thinking_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            # Check if this is a thinking/CoT part
                            is_thought = getattr(part, 'thought', False)
                            if is_thought:
                                thinking_parts.append(part.text)
                    
                    if thinking_parts:
                        thinking_content = "\n\n".join(thinking_parts)
                        logger.debug(f"Extracted thinking content: {len(thinking_content)} chars")

            # Handle potential empty response/safety block
            if not response.text:
                finish_reason = "UNKNOWN"
                safety_ratings = []
                
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if candidate.finish_reason:
                        finish_reason = str(candidate.finish_reason)
                    
                    # Extract safety ratings if available
                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        safety_ratings = [
                            f"{rating.category.name}={rating.probability.name}"
                            for rating in candidate.safety_ratings
                            if rating.probability.name != "NEGLIGIBLE"
                        ]
                
                # Log detailed empty response info
                if safety_ratings:
                    logger.warning(f"Empty response from Gemini. Reason: {finish_reason}, Safety: {', '.join(safety_ratings)}")
                else:
                    logger.warning(f"Empty response from Gemini. Reason: {finish_reason}, Candidates: {len(response.candidates) if response.candidates else 0}")
                
                return GeminiResponse(
                    content="",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    finish_reason=finish_reason,
                    model=target_model,
                    cached_tokens=cached_tokens,
                    thinking_content=None
                )

            return GeminiResponse(
                content=response.text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason="STOP",  # Assumed success
                model=target_model,
                cached_tokens=cached_tokens,
                thinking_content=thinking_content
            )

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise
