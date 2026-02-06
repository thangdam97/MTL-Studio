"""
Vision-Enhanced Translator with Multimodal Function Responses
Complete implementation for MTL Studio + Gemini 3 Pro

MTL Studio Internal Test Build
Model: gemini-3-pro-preview (hardcoded for testing)
SDK: google-genai (googleapis/python-genai)

Thinking Mode: ENABLED by default (reveals internal reasoning)
Prompts: Loaded from EN translator pipeline (master_prompt + grammar RAGs)
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, List, Any

from .illustration_analyzer import IllustrationAnalyzer, IllustrationContext
from .function_handler import IllustrationFunctionHandler, TOOL_DECLARATIONS

logger = logging.getLogger(__name__)


class VisionEnhancedTranslator:
    """
    Translator that uses Gemini 3 Pro's multimodal function responses
    to provide on-demand illustration access during translation.
    
    Test Build Configuration:
    - Model: gemini-3-pro-preview (hardcoded)
    - thinking_level: HIGH (default, reveals internal reasoning)
    - include_thoughts: True (exposes "black box")
    - Function calling: AUTO mode
    - System prompt: Loaded from EN translator pipeline
    """
    
    # Test build: hardcoded model
    MODEL_ID = "gemini-3-pro-preview"
    
    def __init__(
        self,
        work_dir: Path,
        gcs_bucket: Optional[str] = None,
        thinking_level: str = "high",
        include_thoughts: bool = True,
        api_key: Optional[str] = None,
        load_pipeline_prompt: bool = True
    ):
        """
        Initialize vision-enhanced translator.
        
        Args:
            work_dir: Volume working directory containing assets/
            gcs_bucket: GCS bucket for large images (optional, not used in test)
            thinking_level: LOW/HIGH reasoning depth (default: HIGH)
            include_thoughts: Enable thought process output (default: True)
            api_key: Optional API key (uses GOOGLE_API_KEY env var if not provided)
            load_pipeline_prompt: Load EN master prompt + RAGs from translator pipeline
        """
        self.work_dir = Path(work_dir)
        self.thinking_level = thinking_level.upper()  # Normalize to uppercase
        self.include_thoughts = include_thoughts
        self.api_key = api_key
        self._client = None
        self._system_instruction = None
        
        # Initialize function handler
        self.function_handler = IllustrationFunctionHandler(
            work_dir=work_dir,
            gcs_bucket=gcs_bucket,
            use_gcs=False  # Disabled for test build
        )
        
        # Load EN translator pipeline prompts if requested
        if load_pipeline_prompt:
            self._load_pipeline_prompts()
        
        logger.info(f"VisionEnhancedTranslator initialized")
        logger.info(f"  Model: {self.MODEL_ID}")
        logger.info(f"  Work dir: {self.work_dir}")
        logger.info(f"  Thinking level: {self.thinking_level}")
        logger.info(f"  Include thoughts: {self.include_thoughts}")
        logger.info(f"  Pipeline prompts loaded: {load_pipeline_prompt}")
    
    def _load_pipeline_prompts(self):
        """
        Load EN master prompt and grammar RAGs from translator pipeline.
        This ensures the test suite uses the exact same prompts as production.
        """
        try:
            from pipeline.translator.prompt_loader import PromptLoader
            
            loader = PromptLoader(target_language='en')
            
            # Build complete system instruction with all RAG modules injected
            self._system_instruction = loader.build_system_instruction(genre='romcom')
            
            instruction_size_kb = len(self._system_instruction.encode('utf-8')) / 1024
            logger.info(f"✓ Loaded EN pipeline prompts: {instruction_size_kb:.1f}KB")
            logger.info(f"  Master prompt + RAG modules injected")
            
        except ImportError as e:
            logger.warning(f"Could not load pipeline prompts: {e}")
            logger.warning(f"Using fallback minimal prompt")
            self._system_instruction = None
        except Exception as e:
            logger.warning(f"Error loading pipeline prompts: {e}")
            self._system_instruction = None
    
    def get_system_instruction(self) -> Optional[str]:
        """Get the loaded system instruction (for inspection/debugging)."""
        return self._system_instruction
    
    @property
    def client(self):
        """Lazy initialization of Gemini client using new google-genai SDK."""
        if self._client is None:
            try:
                from google import genai
                
                # Use provided API key or environment variable
                api_key = self.api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
                
                if not api_key:
                    raise ValueError(
                        "API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable, "
                        "or provide api_key parameter."
                    )
                
                self._client = genai.Client(api_key=api_key)
                logger.info(f"Gemini client initialized with new SDK")
                logger.info(f"  Available tools: {list(TOOL_DECLARATIONS.keys())}")
                
            except ImportError:
                raise ImportError(
                    "google-genai package not installed. "
                    "Run: pip install google-genai"
                )
        return self._client
    
    def translate_segment(
        self,
        source_text: str,
        system_prompt: Optional[str] = None,
        max_function_calls: int = 10
    ) -> Dict[str, Any]:
        """
        Translate a text segment with vision-enhanced illustration handling.
        
        The model will automatically request illustrations when it
        encounters [ILLUSTRATION: illust-XXX.jpg] markers.
        
        Args:
            source_text: Japanese source text to translate
            system_prompt: Translation system prompt (uses pipeline prompt if None)
            max_function_calls: Safety limit for function call loop
            
        Returns:
            Dict with translation result, thoughts (if enabled), and metadata
        """
        from google.genai import types
        
        # Use provided system_prompt or fall back to loaded pipeline prompt
        effective_prompt = system_prompt or self._system_instruction
        if not effective_prompt:
            logger.warning("No system prompt available - using minimal fallback")
            effective_prompt = "You are a JP→EN light novel translator. Translate naturally."
        
        # Build tool declarations for the new SDK format
        tool_decls = [
            types.FunctionDeclaration(
                name=decl["name"],
                description=decl["description"],
                parameters=types.Schema(
                    type=decl["parameters"]["type"].upper(),
                    properties={
                        k: types.Schema(
                            type=v["type"].upper(),
                            description=v.get("description", "")
                        )
                        for k, v in decl["parameters"].get("properties", {}).items()
                    },
                    required=decl["parameters"].get("required", [])
                )
            )
            for decl in TOOL_DECLARATIONS.values()
        ]
        tool = types.Tool(function_declarations=tool_decls)
        
        # Build ThinkingConfig to reveal internal reasoning
        thinking_config = types.ThinkingConfig(
            include_thoughts=self.include_thoughts,
            thinking_level=self.thinking_level  # "LOW" or "HIGH"
        )
        
        # Track function calls and thoughts for analysis
        function_call_log = []
        thoughts_log = []
        
        # Build conversation history using new SDK types
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=source_text)]
            )
        ]
        
        logger.info(f"Starting translation with vision enhancement")
        logger.info(f"  Source length: {len(source_text)} chars")
        logger.info(f"  System prompt: {len(effective_prompt)} chars")
        logger.info(f"  Thinking: {self.thinking_level} (include_thoughts={self.include_thoughts})")
        
        # Iterative function calling loop
        for iteration in range(max_function_calls):
            logger.info(f"[Iteration {iteration + 1}/{max_function_calls}] Calling API...")
            try:
                response = self.client.models.generate_content(
                    model=self.MODEL_ID,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=effective_prompt,
                        tools=[tool],
                        temperature=1.0,
                        top_p=0.95,
                        thinking_config=thinking_config,  # Enable thought process
                        # Disable automatic function calling - we handle it manually
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        )
                    )
                )
                
                logger.info(f"[Iteration {iteration + 1}] API response received")
                
                # Check for function calls using new SDK response format
                if response.candidates and response.candidates[0].content.parts:
                    parts = response.candidates[0].content.parts
                    
                    function_calls_in_response = []
                    text_response = None
                    thought_text = None
                    
                    for part in parts:
                        # Check for function calls using new SDK
                        if hasattr(part, 'function_call') and part.function_call:
                            fc = part.function_call
                            function_calls_in_response.append({
                                "name": fc.name,
                                "args": dict(fc.args) if fc.args else {}
                            })
                        elif hasattr(part, 'text') and part.text:
                            # Check if this is a thought part (thinking mode)
                            if hasattr(part, 'thought') and part.thought:
                                thought_text = part.text
                            else:
                                text_response = part.text
                    
                    # Capture thoughts if present
                    if thought_text:
                        thoughts_log.append({
                            "iteration": iteration + 1,
                            "thoughts": thought_text
                        })
                        logger.info(f"[Iteration {iteration + 1}] Thought summary captured: {len(thought_text)} chars")
                    
                    # If there are function calls, handle them
                    if function_calls_in_response:
                        logger.info(f"[Iteration {iteration + 1}] Model requested {len(function_calls_in_response)} function(s)")
                        
                        # Add model's response (with function call) to history
                        contents.append(response.candidates[0].content)
                        
                        # Handle each function call and collect responses
                        function_response_parts = []
                        for fc in function_calls_in_response:
                            logger.info(f"  → {fc['name']}({fc['args']})")
                            
                            result = self.function_handler.handle_function_call(
                                fc["name"],
                                fc["args"]
                            )
                            
                            function_call_log.append({
                                "iteration": iteration + 1,
                                "function": fc["name"],
                                "args": fc["args"],
                                "success": result.get("success", False)
                            })
                            
                            # Build function response part using new SDK types
                            function_response_parts.append(
                                types.Part.from_function_response(
                                    name=fc["name"],
                                    response=result["response"]
                                )
                            )
                            
                            # If image data was returned, add it as inline data
                            if result.get("image"):
                                import base64
                                # Decode base64 to raw bytes for inline data
                                image_bytes = base64.b64decode(result["image"]["data"])
                                function_response_parts.append(
                                    types.Part.from_bytes(
                                        data=image_bytes,
                                        mime_type=result["image"]["mime_type"]
                                    )
                                )
                        
                        # Add function responses as tool role content
                        contents.append(
                            types.Content(
                                role="user",  # Function responses go as user in new SDK
                                parts=function_response_parts
                            )
                        )
                        
                        continue  # Continue loop for next model response
                    
                    # No function calls - translation complete
                    if text_response:
                        logger.info(f"✓ Translation complete after {iteration + 1} iteration(s)")
                        logger.info(f"  Function calls made: {len(function_call_log)}")
                        logger.info(f"  Thoughts captured: {len(thoughts_log)} entries")
                        
                        return {
                            "success": True,
                            "translation": text_response,
                            "iterations": iteration + 1,
                            "function_calls": function_call_log,
                            "thoughts": thoughts_log  # Include model's reasoning
                        }
                
                # Fallback: check for direct text response
                if response.text:
                    return {
                        "success": True,
                        "translation": response.text,
                        "iterations": iteration + 1,
                        "function_calls": function_call_log,
                        "thoughts": thoughts_log
                    }
                    
            except Exception as e:
                logger.error(f"Translation error at iteration {iteration + 1}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "iterations": iteration + 1,
                    "function_calls": function_call_log,
                    "thoughts": thoughts_log
                }
        
        # Max iterations reached
        logger.warning(f"Max function calls ({max_function_calls}) reached")
        return {
            "success": False,
            "error": "Max function calls reached",
            "iterations": max_function_calls,
            "function_calls": function_call_log,
            "thoughts": thoughts_log
        }


class VisionTranslationResult:
    """Container for vision-enhanced translation results."""
    
    def __init__(
        self,
        source_text: str,
        translation: str,
        illustration_contexts: Dict[str, IllustrationContext],
        function_calls: List[Dict],
        thoughts: Optional[List[Dict]] = None
    ):
        self.source_text = source_text
        self.translation = translation
        self.illustration_contexts = illustration_contexts
        self.function_calls = function_calls
        self.thoughts = thoughts or []
    
    def to_dict(self) -> Dict:
        return {
            "source_text": self.source_text,
            "translation": self.translation,
            "illustration_contexts": {
                k: v.to_dict() for k, v in self.illustration_contexts.items()
            },
            "function_calls": self.function_calls,
            "thoughts": self.thoughts
        }
