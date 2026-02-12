#!/usr/bin/env python3
"""
Comparative analysis of MTL Studio vs Web Gemini translations
Analyzes sentence length, dialogue metrics, contractions, and rhythm patterns
"""

import re
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

def extract_text_blocks(filepath: Path) -> Tuple[List[str], List[str]]:
    """Extract dialogue and narration blocks from markdown file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove headers and metadata
    content = re.sub(r'^#.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\[ILLUSTRATION:.*\]$', '', content, flags=re.MULTILINE)

    # Split into lines
    lines = [line.strip() for line in content.split('\n') if line.strip()]

    dialogue = []
    narration = []

    for line in lines:
        # Detect dialogue (quoted text)
        if re.search(r'^"[^"]+', line) or re.search(r'"[^"]+"', line):
            # Extract just the quoted parts
            quotes = re.findall(r'"([^"]+)"', line)
            dialogue.extend(quotes)
        else:
            # Everything else is narration
            narration.append(line)

    return dialogue, narration

def count_words(text: str) -> int:
    """Count words in text"""
    return len(re.findall(r'\b\w+\b', text))

def count_sentences(text: str) -> int:
    """Count sentences (periods, exclamation marks, question marks)"""
    # Handle ellipses and multiple punctuation
    text = re.sub(r'\.{2,}', '.', text)  # Normalize ellipses
    sentences = re.findall(r'[.!?]+', text)
    return len(sentences) if sentences else 1

def count_contractions(text: str) -> int:
    """Count contractions like I'm, don't, won't"""
    contractions = re.findall(r"\b\w+'\w+\b", text)
    return len(contractions)

def analyze_chapter(filepath: Path) -> Dict:
    """Analyze a single chapter file"""
    dialogue, narration = extract_text_blocks(filepath)

    # Combine all text for overall stats
    all_dialogue_text = ' '.join(dialogue)
    all_narration_text = ' '.join(narration)

    # Dialogue metrics
    dialogue_sentences = []
    for line in dialogue:
        sent_count = count_sentences(line)
        word_count = count_words(line)
        dialogue_sentences.append(word_count / max(sent_count, 1))

    # Narration metrics
    narration_sentences = []
    for line in narration:
        sent_count = count_sentences(line)
        word_count = count_words(line)
        narration_sentences.append(word_count / max(sent_count, 1))

    # All sentences combined
    all_sentences = dialogue_sentences + narration_sentences

    # Hard cap violations
    dialogue_over_10 = sum(1 for s in dialogue_sentences if s > 10)
    narration_over_15 = sum(1 for s in narration_sentences if s > 15)

    # Contractions
    total_contractions = count_contractions(all_dialogue_text) + count_contractions(all_narration_text)

    # Calculate averages
    avg_dialogue = sum(dialogue_sentences) / len(dialogue_sentences) if dialogue_sentences else 0
    avg_narration = sum(narration_sentences) / len(narration_sentences) if narration_sentences else 0
    avg_overall = sum(all_sentences) / len(all_sentences) if all_sentences else 0

    # Grade assessment (based on Netoge v1.4 standard: 8.14w = A-grade)
    def get_grade(avg):
        if avg <= 9:
            return "A"
        elif avg <= 11:
            return "B"
        elif avg <= 13:
            return "C"
        elif avg <= 15:
            return "D"
        else:
            return "F"

    return {
        'filepath': str(filepath),
        'dialogue_count': len(dialogue_sentences),
        'narration_count': len(narration_sentences),
        'total_sentences': len(all_sentences),
        'avg_dialogue': round(avg_dialogue, 2),
        'avg_narration': round(avg_narration, 2),
        'avg_overall': round(avg_overall, 2),
        'dialogue_over_10': dialogue_over_10,
        'dialogue_over_10_pct': round(100 * dialogue_over_10 / max(len(dialogue_sentences), 1), 1),
        'narration_over_15': narration_over_15,
        'narration_over_15_pct': round(100 * narration_over_15 / max(len(narration_sentences), 1), 1),
        'total_contractions': total_contractions,
        'grade': get_grade(avg_overall)
    }

def compare_translations():
    """Compare MTL Studio vs Web Gemini translations"""

    base_path = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/自分を負けヒロインだと思い込んでいるすでに勝利済みの幼馴染_20260210_1790")

    mtl_path = base_path / "EN"
    gemini_path = base_path / "WEB_GEMINI_ver"

    results = {
        'mtl_studio': {},
        'web_gemini': {}
    }

    # Analyze MTL Studio chapters
    for i in range(1, 4):
        chapter_file = mtl_path / f"CHAPTER_{i:02d}_EN.md"
        if chapter_file.exists():
            results['mtl_studio'][f'chapter_{i}'] = analyze_chapter(chapter_file)

    # Analyze Web Gemini chapters
    for i in range(1, 4):
        chapter_file = gemini_path / f"CHAPTER_{i:02d}_EN_NEW.md"
        if chapter_file.exists():
            results['web_gemini'][f'chapter_{i}'] = analyze_chapter(chapter_file)

    # Calculate aggregate statistics
    for system in ['mtl_studio', 'web_gemini']:
        chapters = list(results[system].values())
        if chapters:
            total_dialogue = sum(c['dialogue_count'] for c in chapters)
            total_narration = sum(c['narration_count'] for c in chapters)
            total_sentences = sum(c['total_sentences'] for c in chapters)

            weighted_avg_dialogue = sum(c['avg_dialogue'] * c['dialogue_count'] for c in chapters) / max(total_dialogue, 1)
            weighted_avg_narration = sum(c['avg_narration'] * c['narration_count'] for c in chapters) / max(total_narration, 1)
            weighted_avg_overall = sum(c['avg_overall'] * c['total_sentences'] for c in chapters) / max(total_sentences, 1)

            total_dialogue_over_10 = sum(c['dialogue_over_10'] for c in chapters)
            total_narration_over_15 = sum(c['narration_over_15'] for c in chapters)
            total_contractions = sum(c['total_contractions'] for c in chapters)

            def get_grade(avg):
                if avg <= 9:
                    return "A"
                elif avg <= 11:
                    return "B"
                elif avg <= 13:
                    return "C"
                elif avg <= 15:
                    return "D"
                else:
                    return "F"

            results[system]['aggregate'] = {
                'total_dialogue': total_dialogue,
                'total_narration': total_narration,
                'total_sentences': total_sentences,
                'avg_dialogue': round(weighted_avg_dialogue, 2),
                'avg_narration': round(weighted_avg_narration, 2),
                'avg_overall': round(weighted_avg_overall, 2),
                'dialogue_over_10': total_dialogue_over_10,
                'dialogue_over_10_pct': round(100 * total_dialogue_over_10 / max(total_dialogue, 1), 1),
                'narration_over_15': total_narration_over_15,
                'narration_over_15_pct': round(100 * total_narration_over_15 / max(total_narration, 1), 1),
                'total_contractions': total_contractions,
                'grade': get_grade(weighted_avg_overall)
            }

    return results

def format_comparison_report(results: Dict) -> str:
    """Format results into a readable comparison report"""

    report = []
    report.append("=" * 80)
    report.append("MTL STUDIO vs WEB GEMINI: QUANTITATIVE COMPARISON")
    report.append("Novel 1790: Childhood Friend Who Already Won (Chapters 1-3)")
    report.append("=" * 80)
    report.append("")

    # Aggregate comparison table
    report.append("## AGGREGATE METRICS (Chapters 1-3 Combined)")
    report.append("")
    report.append("| Metric                        | MTL Studio | Web Gemini | Difference |")
    report.append("|-------------------------------|------------|------------|------------|")

    mtl_agg = results['mtl_studio']['aggregate']
    gem_agg = results['web_gemini']['aggregate']

    metrics = [
        ('Average Overall (w/sent)', 'avg_overall', '%.2f'),
        ('Average Dialogue (w/sent)', 'avg_dialogue', '%.2f'),
        ('Average Narration (w/sent)', 'avg_narration', '%.2f'),
        ('Dialogue >10w (%)', 'dialogue_over_10_pct', '%.1f%%'),
        ('Narration >15w (%)', 'narration_over_15_pct', '%.1f%%'),
        ('Total Contractions', 'total_contractions', '%d'),
        ('Grade', 'grade', '%s'),
    ]

    for label, key, fmt in metrics:
        mtl_val = mtl_agg[key]
        gem_val = gem_agg[key]

        if key == 'grade':
            diff = f"{gem_val} vs {mtl_val}"
        elif '%' in fmt:
            diff = f"{gem_val - mtl_val:+.1f}pp"
        elif 'd' in fmt:
            diff = f"{gem_val - mtl_val:+d}"
        else:
            diff = f"{gem_val - mtl_val:+.2f}"

        if '%' in fmt and '%' not in str(mtl_val):
            mtl_str = fmt % mtl_val
            gem_str = fmt % gem_val
        else:
            mtl_str = str(mtl_val) if key == 'grade' else (fmt % mtl_val)
            gem_str = str(gem_val) if key == 'grade' else (fmt % gem_val)

        report.append(f"| {label:<29} | {mtl_str:<10} | {gem_str:<10} | {diff:<10} |")

    report.append("")
    report.append("")

    # Chapter-by-chapter breakdown
    report.append("## CHAPTER-BY-CHAPTER BREAKDOWN")
    report.append("")

    for i in range(1, 4):
        chapter_key = f'chapter_{i}'
        mtl_ch = results['mtl_studio'].get(chapter_key)
        gem_ch = results['web_gemini'].get(chapter_key)

        if not mtl_ch or not gem_ch:
            continue

        report.append(f"### Chapter {i}")
        report.append("")
        report.append("| Metric              | MTL Studio | Web Gemini | Difference |")
        report.append("|---------------------|------------|------------|------------|")

        ch_metrics = [
            ('Avg Overall', 'avg_overall', '%.2f'),
            ('Avg Dialogue', 'avg_dialogue', '%.2f'),
            ('Avg Narration', 'avg_narration', '%.2f'),
            ('Dialogue >10w', 'dialogue_over_10', '%d'),
            ('Narration >15w', 'narration_over_15', '%d'),
            ('Contractions', 'total_contractions', '%d'),
            ('Grade', 'grade', '%s'),
        ]

        for label, key, fmt in ch_metrics:
            mtl_val = mtl_ch[key]
            gem_val = gem_ch[key]

            if key == 'grade':
                diff = f"{gem_val} vs {mtl_val}"
            elif 'd' in fmt:
                diff = f"{gem_val - mtl_val:+d}"
            else:
                diff = f"{gem_val - mtl_val:+.2f}"

            mtl_str = str(mtl_val) if key == 'grade' else (fmt % mtl_val)
            gem_str = str(gem_val) if key == 'grade' else (fmt % gem_val)

            report.append(f"| {label:<19} | {mtl_str:<10} | {gem_str:<10} | {diff:<10} |")

        report.append("")

    return '\n'.join(report)

if __name__ == '__main__':
    results = compare_translations()
    report = format_comparison_report(results)

    # Save full results as JSON
    output_dir = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline")
    json_output = output_dir / "translation_comparison_metrics.json"
    with open(json_output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Save report as text
    report_output = output_dir / "translation_comparison_report.txt"
    with open(report_output, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    print(f"\n\nFull results saved to: {json_output}")
    print(f"Report saved to: {report_output}")
