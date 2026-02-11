"""
Manga Panel Analyzer.

Sends manga pages to Gemini 3 Pro Vision for panel-level analysis.
Produces structured data: characters, dialogue, expressions, body language.

🧪 EXPERIMENTAL — Phase 1.8a

Each page produces:
  - Panel count and positions
  - Per-panel: characters, speaker, dialogue, expression, body language
  - Page-level: summary, narrative beat classification
"""

import json
import time
import base64
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from pipeline.common.genai_factory import create_genai_client

logger = logging.getLogger(__name__)

# ─── Manga-specific analysis prompt ──────────────────────────────────────────

MANGA_ANALYSIS_PROMPT = """
Analyze this manga page for light novel translation reference.

This manga is an adaptation of a light novel. Your analysis will help
a translator working with the ORIGINAL light novel text, not the manga.

For EACH panel on this page, provide:
1. "panel_id": Sequential ID ("panel01", "panel02", etc.)
2. "position": Where on the page (top-left, top-right, center, bottom-left, bottom-right, full-width, etc.)
3. "characters_present": Array of character names/descriptions visible
4. "speaker": Who is speaking (from speech bubble tails), or null if no dialogue
5. "dialogue_jp": Japanese text in speech bubbles (transcribe exactly), or null
6. "dialogue_context": What the dialogue means in context (1 sentence)
7. "expression": Detailed facial expression description
8. "body_language": Posture, gestures, physical stance
9. "atmosphere": Environmental and mood details
10. "emotional_intensity": 0.0 to 1.0 scale
11. "action": What the character is physically doing

Also provide page-level fields:
- "page_summary": 1-2 sentence summary of the page's narrative content
- "narrative_beat": Classification of the scene type

Narrative beat classifications:
  comedy, tension, revelation, quiet-moment, action, 
  romantic, melancholy, confrontation, transition, climax

Focus on VISUAL details a translator cannot get from text alone.
Output ONLY the JSON object. No commentary.

JSON structure:
{
  "panel_count": <number>,
  "panels": [ <panel objects> ],
  "page_summary": "<string>",
  "narrative_beat": "<string>"
}
"""


class MangaPanelAnalyzer:
    """
    Analyzes manga pages using Gemini 3 Pro Vision.
    
    Produces structured panel-level data for the Manga RAG pipeline.
    """
    
    def __init__(
        self,
        model: str = "gemini-3-pro-preview",
        thinking_level: str = "MEDIUM",
        max_retries: int = 3,
        rate_limit_delay: float = 2.0,
    ):
        self.model = model
        self.thinking_level = thinking_level
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self._client = None
    
    def _get_client(self):
        """Lazy-init Gemini client."""
        if self._client is None:
            try:
                self._client = create_genai_client()
            except ImportError:
                raise ImportError("Install google-genai: pip install google-genai")
        return self._client
    
    def analyze_page(
        self,
        image_path: Path,
        page_number: int,
        chapter_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a single manga page.
        
        Args:
            image_path: Path to the manga page image
            page_number: Page number in the manga volume
            chapter_number: Optional manga chapter number
            
        Returns:
            Structured analysis dict with panel-level data
        """
        client = self._get_client()
        
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        mime_type = "image/jpeg"
        if image_path.suffix.lower() == ".png":
            mime_type = "image/png"
        elif image_path.suffix.lower() == ".webp":
            mime_type = "image/webp"
        
        # Build request
        from google.genai import types
        
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_data, mime_type=mime_type),
                    types.Part.from_text(text=MANGA_ANALYSIS_PROMPT),
                ],
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=0.2,
            top_p=0.8,
            thinking_config=types.ThinkingConfig(
                thinking_budget=self._thinking_budget()
            ),
        )
        
        # Execute with retry
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                response = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                elapsed = time.time() - start_time
                
                # Parse response
                result = self._parse_response(response, page_number, chapter_number)
                result["processing_time_seconds"] = round(elapsed, 1)
                result["model"] = self.model
                result["timestamp"] = datetime.now().isoformat()
                
                logger.info(
                    f"  [MANGA] Page {page_number}: "
                    f"{result.get('panel_count', 0)} panels ({elapsed:.1f}s)"
                )
                
                return result
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait = self.rate_limit_delay * (2 ** attempt)
                    logger.warning(
                        f"  [MANGA] Page {page_number}: Retry {attempt+1} "
                        f"after {wait:.1f}s ({e})"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"  [MANGA] Page {page_number}: Failed after {self.max_retries} attempts: {e}")
                    return {
                        "page_number": page_number,
                        "chapter_number": chapter_number,
                        "status": "error",
                        "error": str(e),
                        "model": self.model,
                        "timestamp": datetime.now().isoformat(),
                    }
    
    def _thinking_budget(self) -> int:
        """Map thinking level to token budget."""
        levels = {"LOW": 1024, "MEDIUM": 4096, "HIGH": 8192}
        return levels.get(self.thinking_level, 4096)
    
    def _parse_response(
        self,
        response,
        page_number: int,
        chapter_number: Optional[int],
    ) -> Dict[str, Any]:
        """Parse Gemini response into structured page analysis."""
        # Extract text and thoughts
        text_parts = []
        thought_parts = []
        
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "thought") and part.thought:
                    thought_parts.append(part.text)
                elif part.text:
                    text_parts.append(part.text)
        
        raw_text = "\n".join(text_parts).strip()
        thoughts = thought_parts
        
        # Parse JSON from response
        try:
            # Strip markdown code fences if present
            clean = raw_text
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
            
            analysis = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning(f"  [MANGA] Page {page_number}: Failed to parse JSON, storing raw")
            analysis = {"raw_text": raw_text, "parse_error": True}
        
        # Enrich with metadata
        analysis["page_number"] = page_number
        analysis["chapter_number"] = chapter_number
        analysis["status"] = "success"
        analysis["thoughts"] = thoughts
        
        # Assign panel IDs with page context
        if "panels" in analysis:
            for i, panel in enumerate(analysis["panels"]):
                ch_prefix = f"ch{chapter_number:02d}_" if chapter_number else ""
                panel["panel_id"] = f"{ch_prefix}p{page_number:03d}_panel{i+1:02d}"
        
        return analysis
