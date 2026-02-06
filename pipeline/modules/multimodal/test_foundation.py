#!/usr/bin/env python3
"""
Quick validation test for Multimodal Processor foundation.
Runs without API calls - just validates image loading, manifest parsing,
and SDK availability.
"""

import sys
from pathlib import Path

# Add module path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def check_sdk():
    """Verify the correct google-genai SDK is installed."""
    print("SDK Verification:")
    print("-" * 40)
    
    # Check for NEW SDK (google-genai)
    try:
        from google import genai
        from google.genai import types
        print("  ✓ google-genai SDK found (correct)")
        
        # Verify key classes exist
        assert hasattr(genai, 'Client'), "genai.Client not found"
        assert hasattr(types, 'Part'), "types.Part not found"
        assert hasattr(types, 'GenerateContentConfig'), "types.GenerateContentConfig not found"
        assert hasattr(types, 'FunctionDeclaration'), "types.FunctionDeclaration not found"
        assert hasattr(types, 'ThinkingConfig'), "types.ThinkingConfig not found"
        print("  ✓ Required classes available")
        print("  ✓ ThinkingConfig available (for thought process)")
        return True
    except ImportError:
        print("  ✗ google-genai SDK NOT found")
        print("    Run: pip install google-genai")
        return False
    except AssertionError as e:
        print(f"  ✗ SDK incomplete: {e}")
        return False


def check_pipeline_prompts():
    """Verify EN pipeline prompts can be loaded."""
    print("Pipeline Prompts Verification:")
    print("-" * 40)
    
    try:
        from pipeline.translator.prompt_loader import PromptLoader
        
        loader = PromptLoader(target_language='en')
        system_instruction = loader.build_system_instruction(genre='romcom')
        
        size_kb = len(system_instruction.encode('utf-8')) / 1024
        print(f"  ✓ PromptLoader found")
        print(f"  ✓ EN system instruction built: {size_kb:.1f}KB")
        
        # Check for key RAG modules
        if "english_grammar_rag" in system_instruction.lower() or "grammar" in system_instruction.lower():
            print(f"  ✓ Grammar RAG detected in prompt")
        else:
            print(f"  ⚠ Grammar RAG may not be injected")
        
        return True
    except ImportError as e:
        print(f"  ✗ PromptLoader not found: {e}")
        return False
    except Exception as e:
        print(f"  ⚠ Error loading prompts: {e}")
        return False


def main():
    print("=" * 60)
    print("Multimodal Processor - Foundation Validation")
    print("=" * 60)
    print()
    
    # First check SDK
    sdk_ok = check_sdk()
    print()
    
    # Check pipeline prompts
    prompts_ok = check_pipeline_prompts()
    print()
    
    from modules.multimodal.function_handler import IllustrationFunctionHandler
    
    # Find 1d46 volume
    work_dir = Path(__file__).parent.parent.parent / "WORK"
    matches = list(work_dir.glob("*1d46*"))
    
    if not matches:
        print("✗ Volume not found")
        return 1
    
    volume_dir = matches[0]
    print(f"Volume: {volume_dir.name}")
    print()
    
    # Use test manifest for enhanced metadata
    test_manifest = Path(__file__).parent / "test_data" / "test_manifest.json"
    print(f"Using test manifest: {test_manifest.name}")
    print()
    
    # Initialize handler with test manifest
    print("Initializing IllustrationFunctionHandler...")
    handler = IllustrationFunctionHandler(
        work_dir=volume_dir,
        manifest_override=test_manifest
    )
    print(f"  Assets dir: {handler.assets_dir}")
    print()
    
    # Test get_illustration for all 3 test cases
    print("Testing get_illustration:")
    print("-" * 40)
    
    test_illustrations = ["illust-001", "illust-002", "illust-004"]
    all_passed = True
    
    for illust_id in test_illustrations:
        result = handler.handle_function_call(
            "get_illustration",
            {"illustration_id": illust_id}
        )
        
        if result["success"]:
            img = result.get("image", {})
            resp = result.get("response", {})
            print(f"  ✓ {illust_id}")
            print(f"      File: {img.get('filename', 'N/A')}")
            print(f"      Size: {img.get('size_bytes', 0):,} bytes")
            print(f"      Chapter: {resp.get('chapter', 'N/A')}")
            print(f"      Context: {resp.get('scene_context', 'N/A')[:50]}...")
        else:
            print(f"  ✗ {illust_id}: {result['response'].get('message')}")
            all_passed = False
    
    print()
    
    # Test kuchie
    print("Testing get_kuchie:")
    print("-" * 40)
    
    result = handler.handle_function_call("get_kuchie", {"kuchie_id": "kuchie-001"})
    if result["success"]:
        img = result.get("image", {})
        print(f"  ✓ kuchie-001: {img.get('filename', 'N/A')} ({img.get('size_bytes', 0):,} bytes)")
    else:
        print(f"  ✗ kuchie-001: {result['response'].get('message')}")
    
    print()
    print("=" * 60)
    
    if all_passed and sdk_ok and prompts_ok:
        print("✓ All foundation tests PASSED")
        print("  SDK: google-genai (correct)")
        print("  ThinkingConfig: Available")
        print("  Pipeline prompts: Loaded")
        print("  Function handler correctly loads illustrations")
        print("  Ready for API integration testing")
        return 0
    elif all_passed and sdk_ok and not prompts_ok:
        print("⚠ Foundation tests passed, but pipeline prompts not loaded")
        print("  Translator will use fallback minimal prompt")
        return 0
    elif all_passed and not sdk_ok:
        print("⚠ Foundation tests passed, but SDK not installed")
        print("  Run: pip install google-genai")
        return 1
    else:
        print("✗ Some tests FAILED")
        print("  Check that assets are properly extracted")
        return 1


if __name__ == "__main__":
    sys.exit(main())
