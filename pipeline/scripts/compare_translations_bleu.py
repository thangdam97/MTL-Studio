#!/usr/bin/env python3
"""
Compare two English translation runs using BLEU/chrF metrics.

Compares 331b06 (baseline) vs 165c (with v3.5 schema metadata).
Uses 331b06 as reference to measure how much 165c differs.

Usage:
    python scripts/compare_translations_bleu.py
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple
import sacrebleu
from dataclasses import dataclass


@dataclass
class ComparisonResult:
    """Results from comparing two translations."""
    chapter_id: str
    bleu_score: float
    chrf_score: float
    ter_score: float  # Translation Error Rate
    length_ratio: float  # candidate/reference length
    
    def quality_label(self) -> str:
        """Interpret chrF score as quality label."""
        if self.chrf_score >= 90:
            return "Nearly Identical"
        elif self.chrf_score >= 75:
            return "Very Similar"
        elif self.chrf_score >= 60:
            return "Similar"
        elif self.chrf_score >= 45:
            return "Moderate Difference"
        else:
            return "Significant Difference"


class TranslationComparator:
    """Compare two translation runs using BLEU metrics."""
    
    def __init__(
        self,
        baseline_dir: Path,
        candidate_dir: Path,
        output_dir: Path
    ):
        self.baseline_dir = Path(baseline_dir)
        self.candidate_dir = Path(candidate_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def load_chapter_text(self, file_path: Path) -> str:
        """Load chapter text, excluding metadata and headers."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove metadata blocks if present
        lines = content.split('\n')
        text_lines = []
        in_metadata = False
        
        for line in lines:
            # Skip metadata blocks
            if line.strip().startswith('---'):
                in_metadata = not in_metadata
                continue
            if in_metadata:
                continue
            
            # Skip chapter title headers (# Chapter X)
            if line.strip().startswith('#') and 'chapter' in line.lower():
                continue
            
            # Skip image references
            if '[ILLUSTRATION:' in line or '<img' in line:
                continue
                
            text_lines.append(line)
        
        return '\n'.join(text_lines).strip()
    
    def find_matching_chapters(self) -> List[Tuple[Path, Path]]:
        """Find matching chapter files between baseline and candidate."""
        pairs = []
        
        # Try different naming patterns
        baseline_files = list(self.baseline_dir.glob("chapter_*.md"))
        candidate_files = list(self.candidate_dir.glob("CHAPTER_*_EN.md"))
        
        for baseline_file in sorted(baseline_files):
            # Extract chapter number (e.g., chapter_01.md -> 01)
            chapter_num = baseline_file.stem.split('_')[-1]
            
            # Find corresponding candidate file
            for candidate_file in candidate_files:
                if chapter_num.upper() in candidate_file.stem:
                    pairs.append((baseline_file, candidate_file))
                    break
        
        return pairs
    
    def compare_chapters(self, baseline_text: str, candidate_text: str) -> ComparisonResult:
        """Compare two chapter texts using multiple metrics."""
        
        # Calculate BLEU (sentence-level)
        bleu = sacrebleu.corpus_bleu(
            [candidate_text],
            [[baseline_text]],
            lowercase=True
        )
        
        # Calculate chrF++ (character-level, better for similar texts)
        chrf = sacrebleu.corpus_chrf(
            [candidate_text],
            [[baseline_text]],
            word_order=2  # chrF++
        )
        
        # Calculate TER (Translation Error Rate)
        ter = sacrebleu.corpus_ter(
            [candidate_text],
            [[baseline_text]]
        )
        
        # Length ratio
        length_ratio = len(candidate_text) / len(baseline_text) if baseline_text else 0
        
        return ComparisonResult(
            chapter_id="",  # Will be set by caller
            bleu_score=bleu.score,
            chrf_score=chrf.score,
            ter_score=ter.score,
            length_ratio=length_ratio
        )
    
    def run_comparison(self) -> Dict:
        """Run full comparison and generate report."""
        chapter_pairs = self.find_matching_chapters()
        
        if not chapter_pairs:
            print("❌ No matching chapters found!")
            print(f"Baseline dir: {self.baseline_dir}")
            print(f"Candidate dir: {self.candidate_dir}")
            return {}
        
        print(f"✅ Found {len(chapter_pairs)} matching chapters")
        
        results = []
        
        for baseline_file, candidate_file in chapter_pairs:
            chapter_id = baseline_file.stem
            print(f"\n📖 Comparing {chapter_id}...")
            print(f"   Baseline: {baseline_file.name}")
            print(f"   Candidate: {candidate_file.name}")
            
            baseline_text = self.load_chapter_text(baseline_file)
            candidate_text = self.load_chapter_text(candidate_file)
            
            result = self.compare_chapters(baseline_text, candidate_text)
            result.chapter_id = chapter_id
            
            results.append(result)
            
            print(f"   📊 BLEU: {result.bleu_score:.2f}")
            print(f"   📊 chrF: {result.chrf_score:.2f} ({result.quality_label()})")
            print(f"   📊 TER: {result.ter_score:.2f}")
            print(f"   📊 Length Ratio: {result.length_ratio:.3f}")
        
        # Calculate averages
        avg_bleu = sum(r.bleu_score for r in results) / len(results)
        avg_chrf = sum(r.chrf_score for r in results) / len(results)
        avg_ter = sum(r.ter_score for r in results) / len(results)
        avg_length = sum(r.length_ratio for r in results) / len(results)
        
        report = {
            "comparison": {
                "baseline": str(self.baseline_dir),
                "candidate": str(self.candidate_dir),
                "chapters_compared": len(results)
            },
            "summary": {
                "avg_bleu_score": round(avg_bleu, 2),
                "avg_chrf_score": round(avg_chrf, 2),
                "avg_ter_score": round(avg_ter, 2),
                "avg_length_ratio": round(avg_length, 3)
            },
            "chapters": [
                {
                    "chapter_id": r.chapter_id,
                    "bleu_score": round(r.bleu_score, 2),
                    "chrf_score": round(r.chrf_score, 2),
                    "ter_score": round(r.ter_score, 2),
                    "length_ratio": round(r.length_ratio, 3),
                    "quality": r.quality_label()
                }
                for r in results
            ]
        }
        
        # Save report
        report_file = self.output_dir / "comparison_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print("\n" + "="*60)
        print("📊 OVERALL COMPARISON SUMMARY")
        print("="*60)
        print(f"Chapters compared: {len(results)}")
        print(f"Average BLEU:      {avg_bleu:.2f}")
        print(f"Average chrF:      {avg_chrf:.2f}")
        print(f"Average TER:       {avg_ter:.2f}")
        print(f"Average Length:    {avg_length:.3f}x")
        print(f"\n📄 Detailed report: {report_file}")
        
        return report


def main():
    """Main entry point."""
    workspace = Path(__file__).parent.parent.parent
    
    baseline_dir = workspace / "pipeline/WORK/弓道部の美人な先輩が、俺の部屋でお腹出して寝てる_20260114_331b06/EN"
    candidate_dir = workspace / "pipeline/WORK/弓道部の美人な先輩が、俺の部屋でお腹出して寝てる_20260129_165c/EN"
    output_dir = workspace / "pipeline/WORK/弓道部の美人な先輩が、俺の部屋でお腹出して寝てる_20260129_165c/QC"
    
    print("🔬 Translation Comparison: 331b06 vs 165c")
    print("="*60)
    print(f"Baseline (331b06):  {baseline_dir}")
    print(f"Candidate (165c):   {candidate_dir}")
    print(f"Output:             {output_dir}")
    print("="*60)
    
    comparator = TranslationComparator(baseline_dir, candidate_dir, output_dir)
    comparator.run_comparison()


if __name__ == "__main__":
    main()
