"""
Gemini API Client - Wrapper with retry logic and rate limiting.

Handles Gemini API communication for the Translator agent.
"""

import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from .config import (
    get_model_name,
    get_generation_params,
    get_safety_settings,
    get_rate_limit_config,
    get_caching_config
)


@dataclass
class GeminiResponse:
    """Response from Gemini API."""
    content: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    model: str
    thinking_content: Optional[str] = None  # CoT/thinking parts from model


class GeminiClientError(Exception):
    """Base exception for Gemini client errors."""
    pass


class RateLimitError(GeminiClientError):
    """Rate limit exceeded."""
    pass


class ContentBlockedError(GeminiClientError):
    """Content was blocked by safety filters."""
    pass


class GeminiClient:
    """
    Gemini API wrapper with retry logic and rate limiting.

    Handles:
    - API authentication
    - Request rate limiting
    - Exponential backoff for retries
    - Token counting
    - Content caching for RAG modules
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key. If not provided, reads from GEMINI_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise GeminiClientError(
                "GEMINI_API_KEY not found. Set environment variable or pass api_key parameter."
            )

        self.model_name = get_model_name()
        self.generation_params = get_generation_params()
        self.safety_settings = get_safety_settings()
        self.rate_limit_config = get_rate_limit_config()
        self.caching_config = get_caching_config()

        # Rate limiting state
        self._request_timestamps: List[float] = []
        self._last_request_time: float = 0
        
        # Thinking mode configuration
        self.thinking_mode_config = self._load_thinking_config()

        # Initialize client
        self._client = None
        self._model = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Gemini client and model."""
        try:
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=self.api_key)
            self._types = types
            print(f"[GEMINI] Initialized with model: {self.model_name}")
        except ImportError:
            raise GeminiClientError(
                "google-genai package not installed. Run: pip install google-genai"
            )

    def _load_thinking_config(self) -> Dict[str, Any]:
        """Load thinking mode configuration from config.yaml."""
        from pipeline.config import get_config_section
        
        gemini_config = get_config_section('gemini')
        return gemini_config.get('thinking_mode', {
            'enabled': False,
            'thinking_level': 'medium',
            'save_to_file': False,
            'output_dir': 'THINKING'
        })
    
    def _get_thinking_config(self) -> Optional[Any]:
        """Get ThinkingConfig for Gemini API if thinking mode is enabled."""
        if not self.thinking_mode_config.get('enabled', False):
            return None
        
        try:
            from google.genai import types
            
            thinking_level = self.thinking_mode_config.get('thinking_level', 'medium')
            
            # Gemini 3 uses thinking_level, Gemini 2.5 uses thinking_budget
            if 'gemini-3' in self.model_name.lower():
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
            # If ThinkingConfig not available, return None
            return None
    
    def _build_safety_settings(self) -> List[Any]:
        """Build safety settings for API request."""
        from google.genai import types

        # Map config names to API enum names
        category_map = {
            'harassment': 'HARM_CATEGORY_HARASSMENT',
            'hate_speech': 'HARM_CATEGORY_HATE_SPEECH',
            'sexually_explicit': 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
            'dangerous_content': 'HARM_CATEGORY_DANGEROUS_CONTENT',
        }

        settings = []
        for key, category in category_map.items():
            threshold = self.safety_settings.get(key, 'BLOCK_NONE')
            settings.append(types.SafetySetting(
                category=category,
                threshold=threshold
            ))

        return settings

    def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits."""
        rpm = self.rate_limit_config['requests_per_minute']
        now = time.time()

        # Remove timestamps older than 1 minute
        self._request_timestamps = [
            ts for ts in self._request_timestamps
            if now - ts < 60
        ]

        # If at limit, wait
        if len(self._request_timestamps) >= rpm:
            oldest = self._request_timestamps[0]
            wait_time = 60 - (now - oldest) + 0.1
            if wait_time > 0:
                print(f"[GEMINI] Rate limit reached, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)

        # Record this request
        self._request_timestamps.append(time.time())

    def _exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        base_delay = self.rate_limit_config['retry_delay_seconds']
        return base_delay * (2 ** attempt)

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> GeminiResponse:
        """
        Generate content using Gemini API.

        Args:
            prompt: The user prompt/content to process.
            system_instruction: Optional system instruction for the model.

        Returns:
            GeminiResponse with generated content and metadata.

        Raises:
            GeminiClientError: On API errors after retries exhausted.
            RateLimitError: On persistent rate limiting.
            ContentBlockedError: If content is blocked by safety filters.
        """
        from google.genai import types

        self._wait_for_rate_limit()

        max_retries = self.rate_limit_config['retry_attempts']

        for attempt in range(max_retries):
            try:
                # Build generation config
                gen_config = types.GenerateContentConfig(
                    temperature=self.generation_params['temperature'],
                    top_p=self.generation_params['top_p'],
                    top_k=self.generation_params['top_k'],
                    max_output_tokens=self.generation_params['max_output_tokens'],
                    safety_settings=self._build_safety_settings(),
                )
                
                # Enable thinking mode if configured
                thinking_config = self._get_thinking_config()
                if thinking_config:
                    gen_config.thinking_config = thinking_config

                # Add system instruction if provided
                if system_instruction:
                    gen_config.system_instruction = system_instruction

                # Make request
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=gen_config
                )

                # Check for blocked content
                if not response.candidates:
                    raise ContentBlockedError("No candidates returned - content may have been blocked")

                candidate = response.candidates[0]

                # Check finish reason
                finish_reason = str(candidate.finish_reason) if candidate.finish_reason else "STOP"
                if "SAFETY" in finish_reason.upper():
                    raise ContentBlockedError(f"Content blocked: {finish_reason}")

                # Extract text and thinking parts separately
                content = ""
                thinking_parts = []
                
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            # Check if this is a thinking/CoT part
                            is_thought = getattr(part, 'thought', False)
                            
                            if is_thought:
                                thinking_parts.append(part.text)
                            else:
                                content += part.text
                
                # Combine thinking parts into single string
                thinking_content = "\n\n".join(thinking_parts) if thinking_parts else None

                # Get token counts
                input_tokens = 0
                output_tokens = 0
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
                    output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

                return GeminiResponse(
                    content=content,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    finish_reason=finish_reason,
                    model=self.model_name,
                    thinking_content=thinking_content
                )

            except ContentBlockedError:
                raise  # Don't retry content blocks

            except Exception as e:
                error_str = str(e).lower()

                # Rate limit errors
                if '429' in error_str or 'rate' in error_str or 'quota' in error_str:
                    if attempt < max_retries - 1:
                        delay = self._exponential_backoff(attempt)
                        print(f"[GEMINI] Rate limited, retry {attempt + 1}/{max_retries} in {delay:.1f}s...")
                        time.sleep(delay)
                        continue
                    raise RateLimitError(f"Rate limit exceeded after {max_retries} retries: {e}")

                # Server errors (500, 503, etc.)
                if '500' in error_str or '503' in error_str or 'server' in error_str:
                    if attempt < max_retries - 1:
                        delay = self._exponential_backoff(attempt)
                        print(f"[GEMINI] Server error, retry {attempt + 1}/{max_retries} in {delay:.1f}s...")
                        time.sleep(delay)
                        continue

                # Other errors
                raise GeminiClientError(f"Gemini API error: {e}")

        raise GeminiClientError(f"Failed after {max_retries} retries")

    def get_token_count(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to count tokens for.

        Returns:
            Estimated token count.
        """
        try:
            response = self._client.models.count_tokens(
                model=self.model_name,
                contents=text
            )
            return response.total_tokens
        except Exception:
            # Fallback: rough estimate (1 token ~= 4 chars for English)
            return len(text) // 4

    def create_cache(
        self,
        content: str,
        display_name: str,
        ttl_minutes: int = 120
    ) -> Optional[str]:
        """
        Create cached content for repeated use (RAG modules).

        Args:
            content: Content to cache.
            display_name: Name for the cached content.
            ttl_minutes: Time-to-live in minutes.

        Returns:
            Cache ID if successful, None otherwise.
        """
        if not self.caching_config.get('enabled', False):
            return None

        try:
            from google.genai import types

            cached_content = self._client.caches.create(
                model=self.model_name,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    contents=content,
                    ttl=f"{ttl_minutes * 60}s"  # Convert to seconds
                )
            )

            return cached_content.name
        except Exception as e:
            print(f"[GEMINI] Cache creation failed: {e}")
            return None

    def delete_cache(self, cache_name: str) -> bool:
        """
        Delete a cached content.

        Args:
            cache_name: Name/ID of cache to delete.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._client.caches.delete(name=cache_name)
            return True
        except Exception as e:
            print(f"[GEMINI] Cache deletion failed: {e}")
            return False
