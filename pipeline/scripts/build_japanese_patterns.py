#!/usr/bin/env python3
"""
Japanese Pattern Builder

Scans EPUB files in INPUT/ folder, extracts kanji compounds, and builds
a Sino-Vietnamese pattern database for translation disambiguation.

Usage:
    python scripts/build_japanese_patterns.py --scan          # Scan and show stats
    python scripts/build_japanese_patterns.py --build         # Build pattern JSON
    python scripts/build_japanese_patterns.py --build --min-freq 5  # Filter by frequency
"""

import sys
import json
import argparse
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple, Set
import zipfile
import html
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.kanji_extractor import extract_kanji_compounds, is_kanji


def extract_text_from_epub(epub_path: Path) -> str:
    """
    Extract text content from EPUB file.
    
    Args:
        epub_path: Path to EPUB file
        
    Returns:
        Extracted text content
    """
    text_content = []
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as epub:
            # Find all XHTML/HTML files
            for file_info in epub.filelist:
                filename = file_info.filename
                
                # Skip non-content files
                if not (filename.endswith('.xhtml') or filename.endswith('.html') or filename.endswith('.htm')):
                    continue
                
                # Skip navigation/TOC files
                if 'nav' in filename.lower() or 'toc' in filename.lower():
                    continue
                
                # Extract and decode content
                try:
                    content = epub.read(filename).decode('utf-8', errors='ignore')
                    
                    # Remove HTML tags
                    text = re.sub(r'<[^>]+>', ' ', content)
                    
                    # Decode HTML entities
                    text = html.unescape(text)
                    
                    # Remove excessive whitespace
                    text = re.sub(r'\s+', ' ', text)
                    
                    text_content.append(text)
                    
                except Exception as e:
                    print(f"  Warning: Failed to extract {filename}: {e}")
                    continue
        
        return ' '.join(text_content)
        
    except Exception as e:
        print(f"Error reading EPUB {epub_path.name}: {e}")
        return ""


def scan_input_folder(input_dir: Path) -> List[Path]:
    """
    Scan INPUT folder for EPUB files.
    
    Args:
        input_dir: Path to INPUT directory
        
    Returns:
        List of EPUB file paths
    """
    epub_files = list(input_dir.glob("*.epub"))
    return sorted(epub_files)


def extract_patterns_from_corpus(
    epub_files: List[Path],
    min_length: int = 2,
    max_length: int = 4,
    min_frequency: int = 3
) -> Counter:
    """
    Extract kanji patterns from multiple EPUB files.
    
    Args:
        epub_files: List of EPUB file paths
        min_length: Minimum compound length
        max_length: Maximum compound length
        min_frequency: Minimum frequency across corpus
        
    Returns:
        Counter of kanji compounds with frequencies
    """
    print(f"\n{'='*60}")
    print(f"EXTRACTING PATTERNS FROM {len(epub_files)} EPUB FILES")
    print(f"{'='*60}\n")
    
    all_compounds = Counter()
    
    for i, epub_path in enumerate(epub_files, 1):
        print(f"[{i}/{len(epub_files)}] Processing: {epub_path.name}")
        
        # Extract text
        text = extract_text_from_epub(epub_path)
        if not text:
            print(f"  → No text extracted, skipping")
            continue
        
        print(f"  → Extracted {len(text):,} characters")
        
        # Extract compounds
        compounds = extract_kanji_compounds(
            text,
            min_length=min_length,
            max_length=max_length,
            include_single=False
        )
        
        # Add to global counter
        for compound, freq in compounds:
            all_compounds[compound] += freq
        
        print(f"  → Found {len(compounds):,} unique compounds")
    
    # Filter by minimum frequency
    filtered = Counter({
        compound: freq 
        for compound, freq in all_compounds.items() 
        if freq >= min_frequency
    })
    
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Total unique compounds: {len(all_compounds):,}")
    print(f"After filtering (≥{min_frequency}): {len(filtered):,}")
    
    return filtered


def categorize_patterns(compounds: Counter) -> Dict[str, List[Tuple[str, int]]]:
    """
    Categorize kanji compounds by semantic domain.
    
    Basic categorization by common patterns.
    
    Args:
        compounds: Counter of compounds with frequencies
        
    Returns:
        Dictionary of categorized patterns
    """
    categories = {
        "relationships": [],
        "emotions": [],
        "actions": [],
        "time": [],
        "places": [],
        "titles": [],
        "general": []
    }
    
    # Relationship keywords
    relationship_kanji = {'友', '恋', '愛', '人', '関', '係', '家', '族', '親', '子', '兄', '弟', '姉', '妹'}
    
    # Emotion keywords
    emotion_kanji = {'心', '気', '感', '情', '思', '好', '嫌', '楽', '悲', '喜', '怒', '哀'}
    
    # Action keywords
    action_kanji = {'行', '動', '見', '聞', '言', '話', '考', '思', '来', '行', '帰', '出', '入'}
    
    # Time keywords
    time_kanji = {'時', '間', '日', '年', '月', '週', '今', '昨', '明', '前', '後', '朝', '昼', '夜', '晩'}
    
    # Place keywords
    place_kanji = {'場', '所', '家', '学', '校', '部', '屋', '店', '街', '町', '駅', '道'}
    
    # Title keywords
    title_kanji = {'先', '生', '様', '君', '氏', '先', '輩', '後', '輩', '師', '主', '王'}
    
    for compound, freq in compounds.most_common():
        # Check which category it belongs to
        compound_kanji = set(compound)
        
        if compound_kanji & relationship_kanji:
            categories["relationships"].append((compound, freq))
        elif compound_kanji & emotion_kanji:
            categories["emotions"].append((compound, freq))
        elif compound_kanji & action_kanji:
            categories["actions"].append((compound, freq))
        elif compound_kanji & time_kanji:
            categories["time"].append((compound, freq))
        elif compound_kanji & place_kanji:
            categories["places"].append((compound, freq))
        elif compound_kanji & title_kanji:
            categories["titles"].append((compound, freq))
        else:
            categories["general"].append((compound, freq))
    
    return categories


def generate_rag_json(
    categorized_patterns: Dict[str, List[Tuple[str, int]]],
    output_path: Path,
    top_n_per_category: int = 100
) -> None:
    """
    Generate RAG JSON file for Sino-Vietnamese patterns.
    
    Args:
        categorized_patterns: Dictionary of categorized patterns
        output_path: Path to output JSON file
        top_n_per_category: Maximum patterns per category
    """
    rag_data = {
        "metadata": {
            "name": "Japanese Light Novel Patterns - Auto-Generated",
            "version": "1.0",
            "source": "Extracted from INPUT/ EPUB corpus",
            "language_pair": "Japanese → Vietnamese",
            "description": "Kanji compound patterns extracted from Japanese light novels for Sino-Vietnamese disambiguation"
        },
        "categories": {}
    }
    
    for category, patterns in categorized_patterns.items():
        if not patterns:
            continue
        
        # Take top N most frequent
        top_patterns = patterns[:top_n_per_category]
        
        # Convert to RAG format
        pattern_list = []
        for compound, freq in top_patterns:
            pattern_list.append({
                "zh": compound,  # Same as Japanese kanji
                "vn_correct": "",  # To be filled in
                "vn_wrong": "",     # To be filled in
                "context": category,
                "frequency": freq,
                "note": f"Auto-extracted from corpus (freq: {freq})"
            })
        
        rag_data["categories"][category] = pattern_list
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rag_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ RAG JSON generated: {output_path}")
    print(f"  Total categories: {len(rag_data['categories'])}")
    print(f"  Total patterns: {sum(len(v) for v in rag_data['categories'].values())}")


def show_statistics(categorized_patterns: Dict[str, List[Tuple[str, int]]]) -> None:
    """Display pattern statistics."""
    print(f"\n{'='*60}")
    print("PATTERN STATISTICS BY CATEGORY")
    print(f"{'='*60}\n")
    
    for category, patterns in categorized_patterns.items():
        if not patterns:
            continue
        
        print(f"📁 {category.upper()}")
        print(f"   Total patterns: {len(patterns)}")
        
        # Show top 10
        print(f"   Top 10 most frequent:")
        for compound, freq in patterns[:10]:
            print(f"      {compound:6s} → {freq:6,} occurrences")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Build Japanese pattern database from EPUB corpus"
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan corpus and show statistics only"
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build RAG JSON file"
    )
    parser.add_argument(
        "--min-freq",
        type=int,
        default=3,
        help="Minimum frequency threshold (default: 3)"
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=2,
        help="Minimum compound length (default: 2)"
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=4,
        help="Maximum compound length (default: 4)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="config/japanese_patterns_auto.json",
        help="Output JSON file path (default: config/japanese_patterns_auto.json)"
    )
    
    args = parser.parse_args()
    
    if not args.scan and not args.build:
        parser.print_help()
        sys.exit(1)
    
    # Find INPUT directory
    project_root = Path(__file__).parent.parent
    input_dir = project_root / "INPUT"
    
    if not input_dir.exists():
        print(f"Error: INPUT directory not found at {input_dir}")
        sys.exit(1)
    
    # Scan for EPUB files
    epub_files = scan_input_folder(input_dir)
    
    if not epub_files:
        print(f"No EPUB files found in {input_dir}")
        sys.exit(1)
    
    print(f"Found {len(epub_files)} EPUB file(s):")
    for epub in epub_files:
        print(f"  - {epub.name}")
    
    # Extract patterns
    compounds = extract_patterns_from_corpus(
        epub_files,
        min_length=args.min_length,
        max_length=args.max_length,
        min_frequency=args.min_freq
    )
    
    # Categorize
    categorized = categorize_patterns(compounds)
    
    # Show statistics
    show_statistics(categorized)
    
    # Build RAG JSON if requested
    if args.build:
        output_path = project_root / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        generate_rag_json(categorized, output_path)
        
        print(f"\n{'='*60}")
        print("NEXT STEPS")
        print(f"{'='*60}")
        print(f"1. Review generated patterns: {output_path}")
        print(f"2. Fill in Vietnamese translations (vn_correct, vn_wrong)")
        print(f"3. Merge into sino_vietnamese_rag.json")
        print(f"4. Rebuild vector index:")
        print(f"   python scripts/test_sino_vn_embeddings.py --build")


if __name__ == "__main__":
    main()
