#!/usr/bin/env python3
"""
Build EPUB for Vol 1 (25b4)
"""

import sys
from pathlib import Path

# Add pipeline directory to path
pipeline_dir = Path(__file__).parent.parent
sys.path.insert(0, str(pipeline_dir))

from pipeline.builder.agent import BuilderAgent

def main():
    print("=" * 70)
    print("BUILDING EPUB FOR VOL 1 (25b4)")
    print("=" * 70)
    
    # Initialize builder agent
    builder = BuilderAgent()
    
    # Build EPUB for Vol 1
    volume_id = "(迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について (1)_20260126_25b4"
    
    result = builder.build_epub(
        volume_id=volume_id,
        output_filename=None,  # Use default naming
        skip_qc_check=True     # Skip QC since we're rebuilding
    )
    
    if result.success:
        print("\n" + "=" * 70)
        print("✓ EPUB BUILD SUCCESSFUL")
        print("=" * 70)
        print(f"Output: {result.epub_path}")
        print(f"Language: {result.language}")
        if result.metadata:
            print(f"Title: {result.metadata.get('title_english', 'N/A')}")
            print(f"Volume: {result.metadata.get('volume_number', 'N/A')}")
        print("=" * 70)
        return 0
    else:
        print("\n" + "=" * 70)
        print("✗ EPUB BUILD FAILED")
        print("=" * 70)
        print(f"Error: {result.error}")
        print("=" * 70)
        return 1

if __name__ == '__main__':
    sys.exit(main())
