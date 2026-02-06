"""
Illustration Analyzer - Gemini 3 Pro Cognitive Vision Module
Extracts emotional and contextual metadata from inline illustrations
to guide translation of surrounding prose.

MTL Studio Internal Test Build
Model: gemini-3-pro-preview (hardcoded for testing)
SDK: google-genai (googleapis/python-genai)
"""

import base64
import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class IllustrationContext:
    """Structured output from illustration analysis."""
    illustration_id: str
    
    # Visual Analysis
    characters_present: List[str] = field(default_factory=list)
    primary_emotion: str = ""  # e.g., "melancholy", "joy", "surprise"
    secondary_emotion: Optional[str] = None
    emotional_intensity: float = 0.5  # 0.0 - 1.0
    
    # Body Language
    posture: str = ""  # e.g., "tense", "relaxed", "defensive"
    gaze_direction: str = ""  # e.g., "direct", "averted", "downcast"
    hand_position: str = ""  # e.g., "clenched", "open", "covering_face"
    
    # Scene Atmosphere
    lighting_mood: str = ""  # e.g., "warm", "cold", "dramatic", "soft"
    background_elements: List[str] = field(default_factory=list)
    time_of_day: Optional[str] = None
    
    # Subtext Detection (for translation guidance)
    implied_subtext: str = ""  # What the character is NOT saying
    relationship_dynamic: str = ""  # e.g., "longing", "conflict", "tender"
    
    # Translation Directives
    prose_tone_recommendation: str = ""  # How to write the surrounding prose
    avoid_phrases: List[str] = field(default_factory=list)  # AI-isms that contradict visual
    
    # Gemini 3 Pro Thinking Process (for QA/audit)
    thought_summaries: List[str] = field(default_factory=list)  # Captured from part.thought=True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "IllustrationContext":
        """Create from dictionary."""
        return cls(**data)


class IllustrationAnalyzer:
    """
    Analyzes illustrations using Gemini 3 Pro's multimodal capabilities.
    
    Test Build Configuration:
    - Model: gemini-3-pro-preview (hardcoded)
    - media_resolution: HIGH (default)
    - thinking_level: HIGH (default)
    - Structured JSON output for deterministic integration
    """
    
    # Test build: hardcoded model
    MODEL_ID = "gemini-3-pro-preview"
    
    ANALYSIS_PROMPT = '''You are analyzing an illustration from a Japanese light novel for translation guidance.

**Your Task:** Extract emotional and contextual metadata that will help the translator write prose that perfectly matches this visual.

**Character Identification:**
Known characters in this series:
{character_registry}

**Critical Focus Areas:**
1. EMOTIONAL STATE - What is each character feeling? Look at micro-expressions.
2. BODY LANGUAGE - How are they holding themselves? What does it reveal?
3. SUBTEXT - What is the character NOT saying but clearly feeling?
4. ATMOSPHERE - How does the lighting/composition create mood?

**NARRATIVE WEIGHT FILTER (CRITICAL):**
Only describe visual elements relevant to the emotional focus. Prioritize:
1. Protagonist's face and expression (HIGHEST)
2. Other characters' expressions
3. Body language between characters
4. Lighting/atmosphere reinforcing mood
5. Setting ONLY if establishing shot

IGNORE: background characters, random animals, decorative objects, text on signs.

**Output Format (strict JSON):**
```json
{{
  "illustration_id": "{illustration_id}",
  "characters_present": ["name1", "name2"],
  "primary_emotion": "melancholy",
  "secondary_emotion": "hope",
  "emotional_intensity": 0.85,
  "posture": "shoulders slightly slumped, but chin raised",
  "gaze_direction": "looking away, possibly to hide tears",
  "hand_position": "one hand touching chest (heart)",
  "lighting_mood": "warm backlight creating halo effect",
  "background_elements": ["sunset", "cherry blossoms"],
  "time_of_day": "golden hour",
  "implied_subtext": "She loves him but believes she cannot have him",
  "relationship_dynamic": "restrained longing, dignified sadness",
  "prose_tone_recommendation": "Use bittersweet language. Emphasize the contrast between composed exterior and turbulent interior.",
  "avoid_phrases": ["she smiled", "her eyes sparkled", "she was happy"]
}}
```

Analyze the attached illustration now.'''

    def __init__(
        self,
        media_resolution: str = "high",
        thinking_level: str = "high",
        api_key: Optional[str] = None
    ):
        """
        Initialize analyzer with Gemini 3 Pro settings.
        
        Args:
            media_resolution: LOW/MEDIUM/HIGH - controls vision token cost
            thinking_level: LOW/HIGH - controls reasoning depth
            api_key: Optional API key (uses GOOGLE_API_KEY env var if not provided)
        """
        self.media_resolution = media_resolution
        self.thinking_level = thinking_level
        self.api_key = api_key
        self._client = None
        
        logger.info(f"IllustrationAnalyzer initialized")
        logger.info(f"  Model: {self.MODEL_ID}")
        logger.info(f"  Resolution: {media_resolution}")
        logger.info(f"  Thinking: {thinking_level}")
    
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
                logger.info(f"Gemini client initialized with new SDK: {self.MODEL_ID}")
            except ImportError:
                raise ImportError(
                    "google-genai package not installed. "
                    "Run: pip install google-genai"
                )
        return self._client
    
    def analyze_illustration(
        self,
        image_path: Path,
        illustration_id: str,
        character_registry: Dict[str, str]
    ) -> IllustrationContext:
        """
        Analyze a single illustration and extract translation context.
        
        Args:
            image_path: Path to illustration file (JPEG/PNG)
            illustration_id: ID from markdown (e.g., "illust-003")
            character_registry: Dict mapping character names to descriptions
            
        Returns:
            IllustrationContext with structured analysis
        """
        from google.genai import types
        
        image_path = Path(image_path)
        
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return IllustrationContext(
                illustration_id=illustration_id,
                primary_emotion="unknown",
                prose_tone_recommendation="[Image not found - proceed with text-only translation]"
            )
        
        # Load and encode image
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # Format character registry for prompt
        registry_str = "\n".join([
            f"- {name}: {desc}" 
            for name, desc in character_registry.items()
        ])
        
        # Build prompt
        prompt = self.ANALYSIS_PROMPT.format(
            character_registry=registry_str,
            illustration_id=illustration_id
        )
        
        logger.info(f"Analyzing: {illustration_id} ({image_path.name})")
        
        # Send to Gemini 3 Pro with image using new SDK
        try:
            # Build image part using new SDK types
            image_part = types.Part.from_bytes(
                data=image_data,
                mime_type=self._get_mime_type(image_path)
            )
            
            # Build ThinkingConfig to reveal internal reasoning
            thinking_config = types.ThinkingConfig(
                include_thoughts=True,
                thinking_level=self.thinking_level.upper()  # "LOW" or "HIGH"
            )
            
            response = self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=[
                    types.Part.from_text(text=prompt),
                    image_part
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,  # Low temp for consistent structured output
                    thinking_config=thinking_config,  # Enable thought process
                )
            )
            
            # Extract thoughts from response parts (correct method per Gemini docs)
            # Thoughts are in response.candidates[0].content.parts with part.thought=True
            thought_summaries = []
            response_text = ""
            
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        # This is a thought summary part
                        thought_summaries.append(part.text)
                    elif hasattr(part, 'text') and part.text:
                        response_text += part.text
            
            if thought_summaries:
                logger.debug(f"  Thoughts captured: {len(thought_summaries)} part(s)")
                for i, thought in enumerate(thought_summaries):
                    logger.debug(f"    Thought {i+1}: {len(thought)} chars")
            
            # Parse structured response (use response_text if extracted, else fallback)
            json_text = response_text if response_text else response.text
            context_dict = json.loads(json_text)
            logger.info(f"✓ Analysis complete: {illustration_id}")
            logger.info(f"  Primary emotion: {context_dict.get('primary_emotion', 'N/A')}")
            logger.info(f"  Characters: {context_dict.get('characters_present', [])}")
            
            # Include thought summaries in the context
            context_dict['thought_summaries'] = thought_summaries
            
            return IllustrationContext(**context_dict)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {response.text[:500]}")
            return IllustrationContext(
                illustration_id=illustration_id,
                primary_emotion="parse_error",
                prose_tone_recommendation="[Analysis failed - proceed with text-only translation]"
            )
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return IllustrationContext(
                illustration_id=illustration_id,
                primary_emotion="error",
                prose_tone_recommendation=f"[Error: {str(e)}]"
            )
    
    def batch_analyze_chapter(
        self,
        chapter_illustrations: List[Dict],
        assets_dir: Path,
        character_registry: Dict[str, str]
    ) -> Dict[str, IllustrationContext]:
        """
        Analyze all illustrations in a chapter.
        
        Args:
            chapter_illustrations: List of {id, filename} dicts
            assets_dir: Path to assets/ directory
            character_registry: Character name to description mapping
            
        Returns:
            Dict mapping illustration_id to IllustrationContext
        """
        results = {}
        
        for illust in chapter_illustrations:
            illust_id = illust["id"]
            image_path = Path(assets_dir) / "illustrations" / illust["filename"]
            
            if image_path.exists():
                context = self.analyze_illustration(
                    image_path=image_path,
                    illustration_id=illust_id,
                    character_registry=character_registry
                )
                results[illust_id] = context
            else:
                logger.warning(f"Illustration not found: {image_path}")
                
        return results
    
    @staticmethod
    def _get_mime_type(path: Path) -> str:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".heic": "image/heic",
        }.get(ext, "image/jpeg")
    
    def format_as_xml_context(self, context: IllustrationContext) -> str:
        """
        Format illustration context as XML for prompt injection.
        
        Inserted BEFORE the [ILLUSTRATION] tag in the source text.
        """
        avoid_str = ", ".join(context.avoid_phrases) if context.avoid_phrases else "N/A"
        
        return f'''<VISUAL_CONTEXT for="{context.illustration_id}">
  <characters>{", ".join(context.characters_present)}</characters>
  <emotion primary="{context.primary_emotion}" intensity="{context.emotional_intensity}"/>
  <subtext>{context.implied_subtext}</subtext>
  <body_language>
    <gaze>{context.gaze_direction}</gaze>
    <posture>{context.posture}</posture>
    <hands>{context.hand_position}</hands>
  </body_language>
  <atmosphere>{context.lighting_mood}</atmosphere>
  <translation_guidance>
    {context.prose_tone_recommendation}
  </translation_guidance>
  <avoid>{avoid_str}</avoid>
</VISUAL_CONTEXT>'''
