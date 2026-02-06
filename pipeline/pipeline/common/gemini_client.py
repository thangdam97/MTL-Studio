"""
Gemini API Client for MT Publishing Pipeline.
Shared between Translator and Critics agents.
"""

import os
import time
import logging
import backoff
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from google import genai
from google.genai import types

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
    def __init__(self, api_key: str = None, model: str = "gemini-2.5-pro", enable_caching: bool = True):
        """Initialize Gemini client with optional context caching."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        self.model = model
        self.client = genai.Client(api_key=self.api_key)
        self._last_request_time = 0
        self._rate_limit_delay = 6.0  # ~10 requests/min default

        # Context caching support
        self.enable_caching = enable_caching
        self._cached_content_name = None  # Cached content resource name
        
        # Thinking mode configuration
        self.thinking_mode_config = self._load_thinking_config()
        self._cache_created_at = None
        self._cache_ttl_minutes = 60  # Default 1 hour TTL
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
        """Set cache TTL in minutes (max 60)."""
        self._cache_ttl_minutes = min(minutes, 60)

    def _create_cached_content(self, system_instruction: str, model: str) -> str:
        """Create cached content and return resource name."""
        if not self.enable_caching:
            return None

        try:
            logger.info(f"Creating context cache for system instruction ({len(system_instruction)} chars)...")
            start_time = time.time()

            # Create cached content
            # TTL must be in seconds format (e.g., "3600s"), not minutes
            ttl_seconds = self._cache_ttl_minutes * 60
            cached_content = self.client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_instruction,
                    ttl=f"{ttl_seconds}s"
                )
            )

            duration = time.time() - start_time
            self._cached_content_name = cached_content.name
            self._cache_created_at = time.time()
            self._cached_model = model  # Track model for cache validation

            logger.info(f"✓ Context cache created: {cached_content.name} (TTL: {self._cache_ttl_minutes}m) in {duration:.2f}s")
            return cached_content.name

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
                self.client.caches.delete(name=self._cached_content_name)
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
        generation_config: Dict[str, Any] = None
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
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    max_output_tokens=max_output_tokens,
                    cached_content=cached_content_name,
                    safety_settings=safety_settings,
                    automatic_function_calling=None  # Disable AFC to prevent loops
                )
                
                # Add thinking config if enabled (works with cached content too)
                thinking_config = self._get_thinking_config()
                if thinking_config:
                    config.thinking_config = thinking_config
                    logger.debug(f"Thinking mode enabled with cached content (budget: -1)")
                
                logger.debug(f"Using {cache_source} cached system instruction: {cached_content_name}")
            else:
                # Standard mode (no caching or fallback)
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    max_output_tokens=max_output_tokens,
                    system_instruction=system_instruction,
                    safety_settings=safety_settings,
                    automatic_function_calling=None  # Disable AFC to prevent loops
                )
                
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
