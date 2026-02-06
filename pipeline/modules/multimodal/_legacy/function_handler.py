"""
Multimodal Function Response Handler for MTL Studio
Handles illustration requests during translation with optional GCS integration.

MTL Studio Internal Test Build
Model: gemini-3-pro-preview (hardcoded for testing)
"""

import base64
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class IllustrationFunctionHandler:
    """
    Handles function calls for illustration retrieval during translation.
    Returns multimodal responses with actual image data.
    
    Test Build: GCS disabled by default, uses inline base64 encoding.
    """
    
    def __init__(
        self,
        work_dir: Path,
        gcs_bucket: Optional[str] = None,
        use_gcs: bool = False,  # Disabled for test build
        manifest_override: Optional[Path] = None  # For test data
    ):
        """
        Initialize handler.
        
        Args:
            work_dir: Volume working directory containing assets/
            gcs_bucket: GCS bucket for large images (>7MB inline limit)
            use_gcs: Whether to use GCS URIs (disabled for test build)
            manifest_override: Optional path to custom manifest (for testing)
        """
        self.work_dir = Path(work_dir)
        self.assets_dir = self.work_dir / "assets"
        self.gcs_bucket = gcs_bucket
        self.use_gcs = use_gcs and gcs_bucket is not None
        
        # Load manifest for metadata (support override for testing)
        self.manifest = self._load_manifest(manifest_override)
        self.character_refs = self.manifest.get("character_references", {})
        
        logger.info(f"IllustrationFunctionHandler initialized")
        logger.info(f"  Work dir: {self.work_dir}")
        logger.info(f"  Assets dir: {self.assets_dir}")
        logger.info(f"  GCS mode: {self.use_gcs}")
    
    def _load_manifest(self, override_path: Optional[Path] = None) -> Dict:
        """Load manifest.json from work directory or override path."""
        if override_path and Path(override_path).exists():
            manifest_path = Path(override_path)
        else:
            manifest_path = self.work_dir / "manifest.json"
        
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        logger.warning(f"Manifest not found: {manifest_path}")
        return {}
    
    def handle_function_call(
        self,
        function_name: str,
        arguments: Dict[str, Any]
    ) -> Dict:
        """
        Handle a function call and return response data.
        
        Args:
            function_name: Name of the function called
            arguments: Function arguments from model
            
        Returns:
            Dict with response data and optional image bytes
        """
        if function_name == "get_illustration":
            return self._handle_get_illustration(arguments.get("illustration_id", ""))
        elif function_name == "get_character_reference":
            return self._handle_get_character_reference(arguments.get("character_name", ""))
        elif function_name == "get_kuchie":
            return self._handle_get_kuchie(arguments.get("kuchie_id", ""))
        else:
            return self._error_response(function_name, f"Unknown function: {function_name}")
    
    def _handle_get_illustration(self, illustration_id: str) -> Dict:
        """Return illustration with image data."""
        
        # Map illustration_id to file path
        filename = f"{illustration_id}.jpg"
        local_path = self.assets_dir / "illustrations" / filename
        
        if not local_path.exists():
            # Fallback: try PNG
            filename = f"{illustration_id}.png"
            local_path = self.assets_dir / "illustrations" / filename
        
        if not local_path.exists():
            return self._error_response(
                "get_illustration",
                f"Illustration not found: {illustration_id}"
            )
        
        # Get illustration metadata from manifest
        metadata = self._get_illustration_metadata(illustration_id)
        
        # Load image data
        image_data = self._load_image(local_path)
        
        return {
            "function_name": "get_illustration",
            "success": True,
            "response": {
                "illustration_id": illustration_id,
                "chapter": metadata.get("chapter", "unknown"),
                "line": metadata.get("line", "unknown"),
                "scene_context": metadata.get("scene_context", ""),
                "characters_likely_present": metadata.get("characters", []),
                "chronological_warning": metadata.get("scene_position") == "climax",
                "guidance": "This illustration shows the scene's climax. Forecast mood, not action." 
                           if metadata.get("scene_position") == "climax" else None
            },
            "image": image_data
        }
    
    def _handle_get_character_reference(self, character_name: str) -> Dict:
        """Return character reference illustration."""
        
        ref_info = self.character_refs.get(character_name.lower())
        
        if not ref_info:
            return self._error_response(
                "get_character_reference",
                f"No reference illustration for: {character_name}"
            )
        
        local_path = self.assets_dir / ref_info.get("path", "")
        
        if not local_path.exists():
            return self._error_response(
                "get_character_reference",
                f"Reference image not found: {local_path}"
            )
        
        image_data = self._load_image(local_path)
        
        return {
            "function_name": "get_character_reference",
            "success": True,
            "response": {
                "character_name": character_name,
                "description": ref_info.get("description", ""),
                "distinctive_features": ref_info.get("features", [])
            },
            "image": image_data
        }
    
    def _handle_get_kuchie(self, kuchie_id: str) -> Dict:
        """Return kuchie color plate."""
        
        filename = f"{kuchie_id}.jpg"
        local_path = self.assets_dir / "kuchie" / filename
        
        if not local_path.exists():
            return self._error_response(
                "get_kuchie",
                f"Kuchie not found: {kuchie_id}"
            )
        
        image_data = self._load_image(local_path)
        
        return {
            "function_name": "get_kuchie",
            "success": True,
            "response": {
                "kuchie_id": kuchie_id,
                "type": "color_plate"
            },
            "image": image_data
        }
    
    def _load_image(self, path: Path) -> Dict:
        """Load image and return as dict with mime type and data."""
        with open(path, "rb") as f:
            image_bytes = f.read()
        
        return {
            "mime_type": self._get_mime_type(path),
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
            "filename": path.name,
            "size_bytes": len(image_bytes)
        }
    
    def _error_response(self, function_name: str, error_message: str) -> Dict:
        """Return error response for missing assets."""
        logger.warning(f"Function error: {error_message}")
        return {
            "function_name": function_name,
            "success": False,
            "response": {
                "error": True,
                "message": error_message,
                "fallback": "Continue translation without visual reference"
            },
            "image": None
        }
    
    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp"
        }.get(ext, "image/jpeg")
    
    def _get_illustration_metadata(self, illustration_id: str) -> Dict:
        """Get illustration metadata from manifest."""
        illustrations = self.manifest.get("illustrations", {})
        return illustrations.get(illustration_id, {})


# Tool declarations for Gemini function calling
TOOL_DECLARATIONS = {
    "get_illustration": {
        "name": "get_illustration",
        "description": """Retrieves an inline illustration from the light novel.
Call this tool when you encounter an [ILLUSTRATION: illust-XXX.jpg] marker
in the source text. The image will help you write prose that accurately
describes the scene's emotional content.

WHEN TO CALL:
- You see [ILLUSTRATION: illust-XXX.jpg] in the source text
- The surrounding text describes character emotions or appearance
- You need to verify visual details before writing descriptions

The returned image shows the exact scene at that point in the story.
Use it to:
1. Match your prose tone to the character's visible emotion
2. Describe body language, posture, and gaze accurately
3. Avoid contradicting what the illustration shows""",
        "parameters": {
            "type": "object",
            "properties": {
                "illustration_id": {
                    "type": "string",
                    "description": "The illustration ID from the marker (e.g., 'illust-002')"
                }
            },
            "required": ["illustration_id"]
        }
    },
    "get_character_reference": {
        "name": "get_character_reference",
        "description": """Retrieves a reference illustration of a specific character.
Use this when you need to verify a character's appearance for
accurate description (hair color, eye color, distinctive features).

WHEN TO CALL:
- First mention of a character's physical appearance
- Describing a character in detail
- Verifying distinctive features (e.g., white hair, blue eyes)""",
        "parameters": {
            "type": "object",
            "properties": {
                "character_name": {
                    "type": "string",
                    "description": "The character's name (e.g., 'Nagi', 'Souta')"
                }
            },
            "required": ["character_name"]
        }
    },
    "get_kuchie": {
        "name": "get_kuchie",
        "description": """Retrieves a kuchie (color plate illustration) that provides broader
scene context. Kuchie often show character relationships, settings,
or emotional atmosphere for entire arcs.

WHEN TO CALL:
- Starting a new chapter or major scene
- Need to understand the overall mood/atmosphere
- Describing settings or environmental details""",
        "parameters": {
            "type": "object",
            "properties": {
                "kuchie_id": {
                    "type": "string",
                    "description": "The kuchie ID (e.g., 'kuchie-001')"
                }
            },
            "required": ["kuchie_id"]
        }
    }
}
