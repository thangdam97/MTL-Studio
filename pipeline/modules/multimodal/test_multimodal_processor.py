#!/usr/bin/env python3
"""
MTL Studio Multimodal Processor Test Suite
Internal test for Gemini 3 Pro Cognitive Vision Integration

This test suite validates the Multimodal Processor foundation using
three prose segments from Ice Princess Volume 1 (1d46).

Test Cases:
  1. illust-001.jpg - First train meeting (character introduction)
  2. illust-002.jpg - Mont Blanc jealousy (spoiler prevention)
  3. illust-004.jpg - "It's a secret" (emotional peak)

Features:
  - Thinking Mode ENABLED: Reveals Gemini's internal reasoning ("black box")
  - EN Pipeline Prompts: Uses exact same master_prompt + RAGs as production
  - google-genai SDK: New official SDK from googleapis/python-genai

Usage:
  python test_multimodal_processor.py --mode analyze
  python test_multimodal_processor.py --mode translate
  python test_multimodal_processor.py --mode full

Requirements:
  - google-genai >= 1.0.0
  - GOOGLE_API_KEY or GEMINI_API_KEY environment variable set
  - Access to gemini-3-pro-preview model
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add parent modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.multimodal.illustration_analyzer import IllustrationAnalyzer, IllustrationContext
from modules.multimodal.function_handler import IllustrationFunctionHandler
from modules.multimodal.vision_translator import VisionEnhancedTranslator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class MultimodalProcessorTestSuite:
    """
    Test suite for validating Multimodal Processor components.
    
    Test Configuration (hardcoded for internal testing):
    - Model: gemini-3-pro-preview
    - media_resolution: HIGH
    - thinking_level: HIGH
    - GCS: disabled (inline base64)
    """
    
    def __init__(
        self,
        volume_dir: Path,
        api_key: Optional[str] = None
    ):
        """
        Initialize test suite.
        
        Args:
            volume_dir: Path to 1d46 volume directory
            api_key: Optional API key (uses GOOGLE_API_KEY or GEMINI_API_KEY env var if not provided)
        """
        self.volume_dir = Path(volume_dir)
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Load test data
        self.test_data_dir = Path(__file__).parent / "test_data"
        self.manifest = self._load_json(self.test_data_dir / "test_manifest.json")
        self.test_segments = self._load_json(self.test_data_dir / "test_segments.json")
        
        # Initialize components with Thinking Mode ENABLED
        self.analyzer = IllustrationAnalyzer(
            media_resolution="high",
            thinking_level="high",  # Reveals internal reasoning
            api_key=self.api_key
        )
        
        # Use test manifest for enhanced metadata
        test_manifest_path = self.test_data_dir / "test_manifest.json"
        
        self.function_handler = IllustrationFunctionHandler(
            work_dir=self.volume_dir,
            use_gcs=False,
            manifest_override=test_manifest_path
        )
        
        # Initialize translator with EN pipeline prompts and thinking enabled
        self.translator = VisionEnhancedTranslator(
            work_dir=self.volume_dir,
            thinking_level="high",  # Reveals internal reasoning
            include_thoughts=True,  # Capture thought process in output
            api_key=self.api_key,
            load_pipeline_prompt=True  # Load EN master_prompt + grammar RAGs
        )
        
        # Results storage
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "model": "gemini-3-pro-preview",
            "thinking_enabled": True,
            "pipeline_prompts_loaded": self.translator.get_system_instruction() is not None,
            "tests": []
        }
        
        logger.info("=" * 60)
        logger.info("MTL Studio Multimodal Processor Test Suite")
        logger.info("=" * 60)
        logger.info(f"Volume: {self.volume_dir.name}")
        logger.info(f"Test segments: {len(self.test_segments['segments'])}")
        logger.info(f"Thinking Mode: ENABLED (HIGH)")
        logger.info(f"Pipeline Prompts: {'Loaded' if self.results['pipeline_prompts_loaded'] else 'Not loaded'}")
    
    def _load_json(self, path: Path) -> Dict:
        """Load JSON file."""
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    
    def run_analysis_tests(self) -> Dict:
        """
        Test 1: Illustration Analysis
        
        Validates IllustrationAnalyzer's ability to extract emotional
        and contextual metadata from illustrations.
        """
        logger.info("\n" + "=" * 60)
        logger.info("TEST 1: Illustration Analysis")
        logger.info("=" * 60)
        
        character_registry = self.manifest.get("character_registry", {})
        results = []
        
        for segment in self.test_segments["segments"]:
            illust_id = segment["illustration_id"]
            scene_name = segment["scene_name"]
            
            logger.info(f"\n[{illust_id}] {scene_name}")
            logger.info("-" * 40)
            
            # Get illustration path
            illust_info = self.manifest["illustrations"].get(illust_id, {})
            filename = illust_info.get("filename", f"{illust_id}.jpg")
            image_path = self.volume_dir / "assets" / "illustrations" / filename
            
            if not image_path.exists():
                logger.error(f"Image not found: {image_path}")
                results.append({
                    "illustration_id": illust_id,
                    "scene_name": scene_name,
                    "success": False,
                    "error": "Image not found"
                })
                continue
            
            # Analyze illustration
            try:
                context = self.analyzer.analyze_illustration(
                    image_path=image_path,
                    illustration_id=illust_id,
                    character_registry=character_registry
                )
                
                # Validate against expected guidance
                expected = segment.get("expected_vision_guidance", {})
                
                logger.info(f"  Primary emotion: {context.primary_emotion}")
                logger.info(f"  Expected: {expected.get('primary_emotion', 'N/A')}")
                logger.info(f"  Characters: {context.characters_present}")
                logger.info(f"  Subtext: {context.implied_subtext[:100]}...")
                logger.info(f"  Prose guidance: {context.prose_tone_recommendation[:100]}...")
                
                # Generate XML context
                xml_context = self.analyzer.format_as_xml_context(context)
                logger.info(f"\nGenerated XML context:\n{xml_context[:500]}...")
                
                results.append({
                    "illustration_id": illust_id,
                    "scene_name": scene_name,
                    "success": True,
                    "context": context.to_dict(),
                    "xml_context": xml_context
                })
                
            except Exception as e:
                logger.error(f"Analysis failed: {e}")
                results.append({
                    "illustration_id": illust_id,
                    "scene_name": scene_name,
                    "success": False,
                    "error": str(e)
                })
        
        self.results["tests"].append({
            "name": "illustration_analysis",
            "results": results
        })
        
        return results
    
    def run_function_handler_tests(self) -> Dict:
        """
        Test 2: Function Handler
        
        Validates IllustrationFunctionHandler's ability to process
        function calls and return image data.
        """
        logger.info("\n" + "=" * 60)
        logger.info("TEST 2: Function Handler")
        logger.info("=" * 60)
        
        results = []
        
        for segment in self.test_segments["segments"]:
            illust_id = segment["illustration_id"]
            scene_name = segment["scene_name"]
            
            logger.info(f"\n[{illust_id}] {scene_name}")
            logger.info("-" * 40)
            
            # Test get_illustration function
            result = self.function_handler.handle_function_call(
                "get_illustration",
                {"illustration_id": illust_id}
            )
            
            if result.get("success"):
                logger.info(f"  ✓ Function call successful")
                logger.info(f"  Response: {json.dumps(result['response'], indent=2)[:200]}...")
                
                if result.get("image"):
                    img = result["image"]
                    logger.info(f"  Image: {img['filename']} ({img['size_bytes']} bytes)")
                    logger.info(f"  MIME: {img['mime_type']}")
                
                results.append({
                    "function": "get_illustration",
                    "illustration_id": illust_id,
                    "success": True,
                    "response": result["response"],
                    "image_size": result.get("image", {}).get("size_bytes", 0)
                })
            else:
                logger.error(f"  ✗ Function call failed: {result['response'].get('message')}")
                results.append({
                    "function": "get_illustration",
                    "illustration_id": illust_id,
                    "success": False,
                    "error": result["response"].get("message")
                })
        
        # Test get_character_reference
        logger.info("\nTesting get_character_reference...")
        for char_name in ["nagi", "souta"]:
            result = self.function_handler.handle_function_call(
                "get_character_reference",
                {"character_name": char_name}
            )
            status = "✓" if result.get("success") else "✗"
            logger.info(f"  {status} {char_name}: {result['response']}")
            results.append({
                "function": "get_character_reference",
                "character": char_name,
                "success": result.get("success", False)
            })
        
        # Test get_kuchie
        logger.info("\nTesting get_kuchie...")
        result = self.function_handler.handle_function_call(
            "get_kuchie",
            {"kuchie_id": "kuchie-001"}
        )
        status = "✓" if result.get("success") else "✗"
        logger.info(f"  {status} kuchie-001: {result['response']}")
        results.append({
            "function": "get_kuchie",
            "kuchie_id": "kuchie-001",
            "success": result.get("success", False)
        })
        
        self.results["tests"].append({
            "name": "function_handler",
            "results": results
        })
        
        return results
    
    def run_translation_tests(self) -> Dict:
        """
        Test 3: Vision-Enhanced Translation
        
        Validates VisionEnhancedTranslator's ability to translate
        prose segments with on-demand illustration access.
        """
        logger.info("\n" + "=" * 60)
        logger.info("TEST 3: Vision-Enhanced Translation")
        logger.info("=" * 60)
        
        results = []
        
        # Simplified system prompt for testing
        system_prompt = self._build_test_system_prompt()
        
        for segment in self.test_segments["segments"]:
            illust_id = segment["illustration_id"]
            scene_name = segment["scene_name"]
            source_jp = segment["source_jp"]
            reference_en = segment["reference_en"]
            
            logger.info(f"\n[{illust_id}] {scene_name}")
            logger.info("-" * 40)
            logger.info(f"Source length: {len(source_jp)} chars")
            
            try:
                result = self.translator.translate_segment(
                    source_text=source_jp,
                    system_prompt=system_prompt,
                    max_function_calls=5
                )
                
                if result.get("success"):
                    translation = result["translation"]
                    
                    logger.info(f"  ✓ Translation successful")
                    logger.info(f"  Iterations: {result['iterations']}")
                    logger.info(f"  Function calls: {len(result['function_calls'])}")
                    
                    for fc in result["function_calls"]:
                        logger.info(f"    → {fc['function']}({fc['args']}) = {fc['success']}")
                    
                    logger.info(f"\n  Translation preview:\n  {translation[:300]}...")
                    
                    results.append({
                        "illustration_id": illust_id,
                        "scene_name": scene_name,
                        "success": True,
                        "source_jp": source_jp,
                        "translation": translation,
                        "iterations": result["iterations"],
                        "function_calls": result["function_calls"],
                        "reference_en": reference_en,
                        "thoughts": result.get("thoughts", [])
                    })
                else:
                    logger.error(f"  ✗ Translation failed: {result.get('error')}")
                    results.append({
                        "illustration_id": illust_id,
                        "scene_name": scene_name,
                        "success": False,
                        "error": result.get("error"),
                        "function_calls": result.get("function_calls", [])
                    })
                    
            except Exception as e:
                logger.error(f"Translation error: {e}")
                results.append({
                    "illustration_id": illust_id,
                    "scene_name": scene_name,
                    "success": False,
                    "error": str(e)
                })
        
        self.results["tests"].append({
            "name": "vision_translation",
            "results": results
        })
        
        return results
    
    def _build_test_system_prompt(self) -> str:
        """Build simplified system prompt for testing."""
        return """You are a professional Japanese-to-English light novel translator.

TRANSLATION RULES:
1. Preserve the narrative voice and emotional tone
2. Use natural English prose, avoid literal translation
3. Match prose quality to the visual context from illustrations

ILLUSTRATION HANDLING:
When you encounter [ILLUSTRATION: illust-XXX.jpg] markers:
1. Call get_illustration(illustration_id="illust-XXX") to see the image
2. Use the visual to guide your prose tone and descriptions
3. Match character emotions to what you see in the illustration

CHRONOLOGICAL VISUAL DISCIPLINE (CRITICAL):
- If an illustration shows a climactic moment (kiss, tears, embrace)
- But the [ILLUSTRATION] tag appears BEFORE that moment in text
- Then forecast the MOOD but don't describe the ACTION until text reaches it

CHARACTER VOICE:
- Nagi (東雲): Elegant, reserved, gradually warming
- Souta (海以): Observant, slightly nervous around Nagi, kind

Translate the following Japanese text to English. Include the [ILLUSTRATION] markers in your output."""
    
    def save_results(self, output_path: Optional[Path] = None) -> Path:
        """Save test results to JSON file."""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.test_data_dir / f"test_results_{timestamp}.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\nResults saved to: {output_path}")
        return output_path
    
    def save_markdown(self, output_path: Optional[Path] = None) -> Path:
        """
        Save translation results to a single Markdown file.
        
        Format:
        1. JP text (source)
        2. Reference EN text
        3. Translated EN text (multimodal)
        4. Thought Process
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.test_data_dir / f"translation_comparison_{timestamp}.md"
        
        lines = []
        lines.append("# MTL Studio Multimodal Translation Comparison")
        lines.append("")
        lines.append(f"**Generated:** {self.results['timestamp']}")
        lines.append(f"**Model:** {self.results['model']}")
        lines.append(f"**Thinking Mode:** {'ENABLED' if self.results['thinking_enabled'] else 'Disabled'}")
        lines.append(f"**Pipeline Prompts:** {'Loaded' if self.results['pipeline_prompts_loaded'] else 'Not loaded'}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Find translation results
        translation_test = None
        for test in self.results["tests"]:
            if test["name"] == "vision_translation":
                translation_test = test
                break
        
        if not translation_test:
            lines.append("*No translation results available.*")
        else:
            for i, result in enumerate(translation_test["results"], 1):
                illust_id = result.get("illustration_id", "unknown")
                scene_name = result.get("scene_name", "Unknown Scene")
                
                lines.append(f"## Scene {i}: {scene_name}")
                lines.append(f"**Illustration:** `{illust_id}`")
                lines.append("")
                
                if not result.get("success"):
                    lines.append(f"**Error:** {result.get('error', 'Unknown error')}")
                    lines.append("")
                    lines.append("---")
                    lines.append("")
                    continue
                
                # 1. JP Text (Source)
                lines.append("### 1. 📖 Japanese Source")
                lines.append("")
                lines.append("```")
                source_jp = result.get("source_jp", "*Not available*")
                lines.append(source_jp)
                lines.append("```")
                lines.append("")
                
                # 2. Reference EN Text
                lines.append("### 2. 📚 Reference EN (Expected)")
                lines.append("")
                reference_en = result.get("reference_en", "*Not available*")
                lines.append(reference_en)
                lines.append("")
                
                # 3. Translated EN Text (Multimodal)
                lines.append("### 3. 🎨 Multimodal Translation")
                lines.append("")
                translation = result.get("translation", "*Translation failed*")
                lines.append(translation)
                lines.append("")
                
                # Function calls info
                function_calls = result.get("function_calls", [])
                if function_calls:
                    lines.append(f"**Function Calls:** {len(function_calls)}")
                    for fc in function_calls:
                        status = "✓" if fc.get("success") else "✗"
                        lines.append(f"- {status} `{fc['function']}({fc['args']})`")
                    lines.append("")
                
                lines.append(f"**Iterations:** {result.get('iterations', 'N/A')}")
                lines.append("")
                
                # 4. Thought Process
                lines.append("### 4. 🧠 Thought Process")
                lines.append("")
                thoughts = result.get("thoughts", [])
                if thoughts:
                    for thought in thoughts:
                        iteration = thought.get("iteration", "?")
                        thought_text = thought.get("thoughts", "")
                        lines.append(f"#### Iteration {iteration}")
                        lines.append("")
                        lines.append("```")
                        lines.append(thought_text)
                        lines.append("```")
                        lines.append("")
                else:
                    lines.append("*No thought process captured (API may not support ThinkingConfig)*")
                    lines.append("")
                
                lines.append("---")
                lines.append("")
        
        # Write file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.info(f"\nMarkdown saved to: {output_path}")
        return output_path
    
    def print_summary(self):
        """Print test summary."""
        logger.info("\n" + "=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        
        for test in self.results["tests"]:
            name = test["name"]
            results = test["results"]
            
            passed = sum(1 for r in results if r.get("success"))
            total = len(results)
            
            status = "✓ PASS" if passed == total else "✗ PARTIAL" if passed > 0 else "✗ FAIL"
            logger.info(f"{name}: {status} ({passed}/{total})")
        
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="MTL Studio Multimodal Processor Test Suite"
    )
    parser.add_argument(
        "--mode",
        choices=["analyze", "handler", "translate", "full"],
        default="full",
        help="Test mode: analyze, handler, translate, or full"
    )
    parser.add_argument(
        "--volume-dir",
        type=Path,
        default=None,
        help="Path to 1d46 volume directory"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Google API key (or set GOOGLE_API_KEY env var)"
    )
    parser.add_argument(
        "--save-results",
        action="store_true",
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Save translation comparison to Markdown file"
    )
    
    args = parser.parse_args()
    
    # Find volume directory
    if args.volume_dir:
        volume_dir = args.volume_dir
    else:
        # Auto-detect from workspace
        base_path = Path(__file__).parent.parent.parent  # pipeline/
        work_dir = base_path / "WORK"
        
        # Find 1d46 directory
        matches = list(work_dir.glob("*1d46*"))
        if matches:
            volume_dir = matches[0]
        else:
            logger.error("Could not find 1d46 volume directory")
            logger.error(f"Searched in: {work_dir}")
            sys.exit(1)
    
    logger.info(f"Using volume: {volume_dir}")
    
    # Check if volume exists
    if not volume_dir.exists():
        logger.error(f"Volume directory not found: {volume_dir}")
        sys.exit(1)
    
    # Initialize test suite
    try:
        suite = MultimodalProcessorTestSuite(
            volume_dir=volume_dir,
            api_key=args.api_key
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    
    # Run selected tests
    if args.mode in ["analyze", "full"]:
        suite.run_analysis_tests()
    
    if args.mode in ["handler", "full"]:
        suite.run_function_handler_tests()
    
    if args.mode in ["translate", "full"]:
        suite.run_translation_tests()
    
    # Print summary
    suite.print_summary()
    
    # Save results if requested
    if args.save_results:
        suite.save_results()
    
    # Save markdown if requested (or always for translate mode)
    if args.markdown or args.mode in ["translate", "full"]:
        suite.save_markdown()


if __name__ == "__main__":
    main()
