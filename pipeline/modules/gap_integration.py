"""
Gap Integration Module - Week 2-3 Implementation
================================================

Integrates the Gap Semantic Analyzer into the translation pipeline:
- Pre-translation: Flag passages requiring special attention
- Post-translation: Validate gap preservation
- Review: Generate review reports for translator approval

Gap A: Emotion + Action sentence surgery
Gap B: Ruby visual joke preservation
Gap C: Sarcasm/Subtext layer preservation

Author: MTL Studio
Version: 1.0
"""

import json
import re
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

from modules.gap_semantic_analyzer import (
    GapSemanticAnalyzer, 
    GapAAnalysis, 
    GapBAnalysis, 
    GapCAnalysis,
    SpeakerArchetype,
    RubyJokeType
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes for Integration
# =============================================================================

@dataclass
class GapFlag:
    """A flagged passage requiring translator attention"""
    gap_type: str  # "A", "B", "C"
    chapter: str
    line_number: int
    jp_text: str
    en_text: str = ""
    analysis: Any = None  # GapAAnalysis, GapBAnalysis, or GapCAnalysis
    status: str = "pending"  # pending, reviewed, approved, rejected
    reviewer_notes: str = ""


@dataclass
class ChapterGapReport:
    """Gap analysis report for a single chapter"""
    chapter_id: str
    analyzed_at: str = ""
    gap_a_flags: List[GapFlag] = field(default_factory=list)
    gap_b_flags: List[GapFlag] = field(default_factory=list)
    gap_c_flags: List[GapFlag] = field(default_factory=list)
    total_flags: int = 0
    
    def _serialize_flag(self, flag: GapFlag) -> Dict:
        """Serialize a GapFlag with proper enum handling."""
        result = {
            "gap_type": flag.gap_type,
            "chapter": flag.chapter,
            "line_number": flag.line_number,
            "jp_text": flag.jp_text,
            "en_text": flag.en_text,
            "status": flag.status,
            "reviewer_notes": flag.reviewer_notes
        }
        
        # Serialize analysis based on type
        if flag.analysis:
            if hasattr(flag.analysis, 'archetype'):
                # GapCAnalysis
                result["analysis"] = {
                    "archetype": flag.analysis.archetype.value if hasattr(flag.analysis.archetype, 'value') else str(flag.analysis.archetype),
                    "markers_found": flag.analysis.markers_found,
                    "confidence": flag.analysis.confidence,
                    "surface_meaning": getattr(flag.analysis, 'surface_meaning', ''),
                    "actual_meaning": getattr(flag.analysis, 'actual_meaning', '')
                }
            elif hasattr(flag.analysis, 'joke_type'):
                # GapBAnalysis
                result["analysis"] = {
                    "kanji": flag.analysis.kanji,
                    "ruby": flag.analysis.ruby,
                    "joke_type": flag.analysis.joke_type.value if hasattr(flag.analysis.joke_type, 'value') else str(flag.analysis.joke_type),
                    "en_treatment": flag.analysis.en_treatment,
                    "needs_tl_note": flag.analysis.needs_tl_note
                }
            elif hasattr(flag.analysis, 'emotion_word'):
                # GapAAnalysis
                result["analysis"] = {
                    "emotion_word": flag.analysis.emotion_word,
                    "emotion_en": flag.analysis.emotion_en,
                    "action_word": flag.analysis.action_word,
                    "context_type": flag.analysis.context_type,
                    "sentence_count": flag.analysis.sentence_count,
                    "surgery_recommended": flag.analysis.surgery_recommended,
                    "confidence": flag.analysis.confidence
                }
        
        return result
    
    def to_dict(self) -> Dict:
        return {
            "chapter_id": self.chapter_id,
            "analyzed_at": self.analyzed_at,
            "gap_a_flags": [self._serialize_flag(f) for f in self.gap_a_flags],
            "gap_b_flags": [self._serialize_flag(f) for f in self.gap_b_flags],
            "gap_c_flags": [self._serialize_flag(f) for f in self.gap_c_flags],
            "total_flags": self.total_flags
        }


@dataclass
class VolumeGapReport:
    """Gap analysis report for entire volume"""
    volume_id: str
    analyzed_at: str = ""
    chapters: Dict[str, ChapterGapReport] = field(default_factory=dict)
    summary: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# Gap Integration Engine
# =============================================================================

class GapIntegrationEngine:
    """
    Integrates gap analysis into the translation pipeline.
    
    Usage:
        engine = GapIntegrationEngine(work_dir)
        
        # Pre-translation: Flag passages
        engine.analyze_chapter_pre_translation(chapter_num)
        
        # Post-translation: Validate
        engine.validate_chapter_gaps(chapter_num)
        
        # Generate review report
        engine.generate_review_report()
    """
    
    def __init__(self, work_dir: Path, target_language: str = "VN"):
        """
        Initialize the gap integration engine.
        
        Args:
            work_dir: Volume working directory (e.g., WORK/xxx_20260131_2218)
            target_language: Target language code (VN, EN, etc.)
        """
        self.work_dir = Path(work_dir)
        self.target_language = target_language
        self.jp_dir = self.work_dir / "JP"
        self.target_dir = self.work_dir / target_language
        self.audits_dir = self.work_dir / "audits"
        self.audits_dir.mkdir(exist_ok=True)
        
        # Initialize semantic analyzer
        self.analyzer = GapSemanticAnalyzer()
        
        # Volume report
        self.volume_report = VolumeGapReport(
            volume_id=self._extract_volume_id(),
            analyzed_at=datetime.now().isoformat()
        )
        
        # Load existing report if available
        self._load_existing_report()
    
    def _extract_volume_id(self) -> str:
        """Extract volume ID from work directory name"""
        match = re.search(r'_(\d{8})_([a-f0-9]{4})/?$', str(self.work_dir))
        if match:
            return match.group(2)
        return self.work_dir.name[-4:]
    
    def _load_existing_report(self):
        """Load existing gap report if available"""
        report_path = self.audits_dir / "gap_analysis_report.json"
        if report_path.exists():
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded existing gap report from {report_path}")
            except Exception as e:
                logger.warning(f"Failed to load existing report: {e}")
    
    def _save_report(self):
        """Save the gap report to JSON"""
        report_path = self.audits_dir / "gap_analysis_report.json"
        data = {
            "volume_id": self.volume_report.volume_id,
            "analyzed_at": self.volume_report.analyzed_at,
            "chapters": {
                k: v.to_dict() for k, v in self.volume_report.chapters.items()
            },
            "summary": self.volume_report.summary
        }
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved gap report to {report_path}")
    
    # =========================================================================
    # Pre-Translation Analysis
    # =========================================================================
    
    def analyze_chapter_pre_translation(self, chapter_num: int) -> ChapterGapReport:
        """
        Analyze a chapter's EN output to validate gap preservation.
        
        Analyzes both JP source (for Gap B ruby) and EN output (for Gap A/C preservation).
        Note: JP and EN line numbers don't correspond 1:1 due to translation restructuring.
        
        Args:
            chapter_num: Chapter number (1-indexed)
            
        Returns:
            ChapterGapReport with flagged passages
        """
        chapter_id = f"CHAPTER_{chapter_num:02d}"
        
        # Load JP source for Gap B ruby analysis
        jp_path = self.jp_dir / f"{chapter_id}.md"
        if not jp_path.exists():
            logger.warning(f"JP file not found: {jp_path}")
            jp_lines = []
        else:
            with open(jp_path, 'r', encoding='utf-8') as f:
                jp_lines = f.readlines()
        
        # Try to find EN file with various naming conventions
        en_patterns = [
            f"{chapter_id}.md",
            f"{chapter_id}_EN.md",
            f"{chapter_id}_en.md"
        ]
        
        en_path = None
        for pattern in en_patterns:
            candidate = self.target_dir / pattern
            if candidate.exists():
                en_path = candidate
                break
        
        if not en_path:
            logger.error(f"EN file not found for {chapter_id} in {self.target_dir}")
            return ChapterGapReport(chapter_id=chapter_id)
        
        # Read English translation
        with open(en_path, 'r', encoding='utf-8') as f:
            en_lines = f.readlines()
        
        report = ChapterGapReport(
            chapter_id=chapter_id,
            analyzed_at=datetime.now().isoformat()
        )
        
        logger.info(f"Analyzing {chapter_id} for gap patterns...")
        logger.info(f"  JP lines: {len(jp_lines)}, EN lines: {len(en_lines)}")
        
        # =====================================================================
        # Gap B: Ruby detection from JP source
        # =====================================================================
        for line_num, jp_line in enumerate(jp_lines, 1):
            jp_text = jp_line.strip()
            
            if not jp_text or jp_text.startswith('#'):
                continue
            
            # Extract and classify rubies
            rubies = self._extract_rubies(jp_text)
            for kanji, ruby in rubies:
                gap_b = self.analyzer.classify_ruby(kanji, ruby, jp_text)
                if gap_b.joke_type != RubyJokeType.STANDARD:
                    flag = GapFlag(
                        gap_type="B",
                        chapter=chapter_id,
                        line_number=line_num,
                        jp_text=jp_text,
                        en_text="(See JP line for ruby annotation)",
                        analysis=gap_b
                    )
                    report.gap_b_flags.append(flag)
        
        # =====================================================================
        # Gap A & C: Analyze EN output for preservation
        # =====================================================================
        # Build JP text corpus for reference
        jp_corpus = '\n'.join(line.strip() for line in jp_lines if line.strip() and not line.startswith('#'))
        
        for line_num, en_line in enumerate(en_lines, 1):
            en_text = en_line.strip()
            
            if not en_text or en_text.startswith('#'):
                continue
            
            # For Gap A/C, we need to find the corresponding JP segment
            # This is a simplified approach - in production, you'd want better alignment
            # For now, we'll analyze standalone to see if patterns are preserved
            
            # Skip Gap A/C analysis for EN output for now
            # TODO: Implement proper JP-EN alignment or analyze EN independently
            pass
        
        report.total_flags = (
            len(report.gap_a_flags) + 
            len(report.gap_b_flags) + 
            len(report.gap_c_flags)
        )
        
        # Store in volume report
        self.volume_report.chapters[chapter_id] = report
        self._update_summary()
        self._save_report()
        
        logger.info(
            f"  Gap A: {len(report.gap_a_flags)} flags, "
            f"Gap B: {len(report.gap_b_flags)} flags, "
            f"Gap C: {len(report.gap_c_flags)} flags"
        )
        
        return report
    
    def _extract_rubies(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract ruby annotations from Japanese text.
        
        Handles patterns like:
        - kanji{furigana} format (EPUB/aozorabunko style) - most common
        - 《ruby》kanji format (web novel style)
        - ｜kanji《ruby》 (vertical bar prefix)
        """
        rubies = []
        
        # Pattern 1: {furigana} notation (most common in EPUB light novels)
        # Example: 九条才斗{くじょうさいと}, 睨{にら}みつけて
        # This captures kanji followed by {hiragana/katakana}
        pattern_curly = re.compile(r'([一-龯々]+)\{([ぁ-んァ-ンー]+)\}')
        for match in pattern_curly.finditer(text):
            rubies.append((match.group(1), match.group(2)))
        
        # Pattern 2: 《》 ruby notation (web novels, some publishers)
        # Example: 光宙《ぴかちゅう》
        pattern_guillemet = re.compile(r'([一-龯]+)《([ぁ-んァ-ン]+)》')
        for match in pattern_guillemet.finditer(text):
            rubies.append((match.group(1), match.group(2)))
        
        # Pattern 3: ｜kanji《ruby》 (vertical bar prefix for mixed text)
        pattern_bar = re.compile(r'｜([一-龯]+)《([ぁ-んァ-ン]+)》')
        for match in pattern_bar.finditer(text):
            rubies.append((match.group(1), match.group(2)))
        
        return rubies
    
    # =========================================================================
    # Post-Translation Validation
    # =========================================================================
    
    def validate_chapter_gaps(self, chapter_num: int) -> Dict[str, List[Dict]]:
        """
        Validate gap preservation after translation.
        
        Args:
            chapter_num: Chapter number (1-indexed)
            
        Returns:
            Dict with validation results for each gap type
        """
        chapter_id = f"CHAPTER_{chapter_num:02d}"
        
        if chapter_id not in self.volume_report.chapters:
            logger.warning(f"No pre-translation analysis for {chapter_id}")
            return {}
        
        report = self.volume_report.chapters[chapter_id]
        
        # Load translated file
        suffix = f"_{self.target_language}" if self.target_language != "EN" else "_EN"
        target_path = self.target_dir / f"{chapter_id}{suffix}.md"
        
        if not target_path.exists():
            logger.error(f"Translated file not found: {target_path}")
            return {}
        
        with open(target_path, 'r', encoding='utf-8') as f:
            target_lines = f.readlines()
        
        validation_results = {
            "gap_a": [],
            "gap_b": [],
            "gap_c": []
        }
        
        # Validate Gap A flags
        for flag in report.gap_a_flags:
            if flag.line_number <= len(target_lines):
                en_line = target_lines[flag.line_number - 1].strip()
                flag.en_text = en_line
                
                # Basic validation: check if key emotion words made it through
                if flag.analysis and flag.analysis.emotion_en:
                    validation_results["gap_a"].append({
                        "line": flag.line_number,
                        "jp": flag.jp_text[:50],
                        "en": en_line[:50],
                        "emotion": flag.analysis.emotion_en,
                        "status": "needs_review"
                    })
        
        # Validate Gap C flags (sarcasm/subtext)
        for flag in report.gap_c_flags:
            if flag.line_number <= len(target_lines):
                en_line = target_lines[flag.line_number - 1].strip()
                flag.en_text = en_line
                
                if flag.analysis:
                    validation_results["gap_c"].append({
                        "line": flag.line_number,
                        "jp": flag.jp_text[:50],
                        "en": en_line[:50],
                        "archetype": flag.analysis.archetype.value,
                        "markers": flag.analysis.markers_found[:3],
                        "status": "needs_review"
                    })
        
        self._save_report()
        return validation_results
    
    # =========================================================================
    # Review Interface
    # =========================================================================
    
    def generate_review_report(self) -> str:
        """
        Generate a markdown review report for translator approval.
        
        Returns:
            Markdown string with flagged passages
        """
        report = []
        report.append("# Gap Analysis Review Report\n")
        report.append(f"**Volume:** {self.volume_report.volume_id}\n")
        report.append(f"**Generated:** {datetime.now().isoformat()}\n")
        report.append(f"**Target Language:** {self.target_language}\n\n")
        
        # Summary
        report.append("## Summary\n\n")
        report.append("| Gap Type | Description | Flagged |\n")
        report.append("|----------|-------------|--------|\n")
        report.append(f"| **Gap A** | Emotion + Action Surgery | {self.volume_report.summary.get('gap_a', 0)} |\n")
        report.append(f"| **Gap B** | Ruby Visual Jokes | {self.volume_report.summary.get('gap_b', 0)} |\n")
        report.append(f"| **Gap C** | Sarcasm/Subtext | {self.volume_report.summary.get('gap_c', 0)} |\n\n")
        
        # Per-chapter details
        for chapter_id, chapter_report in sorted(self.volume_report.chapters.items()):
            if chapter_report.total_flags == 0:
                continue
            
            report.append(f"## {chapter_id}\n\n")
            
            # Gap A
            if chapter_report.gap_a_flags:
                report.append("### Gap A: Emotion + Action Surgery\n\n")
                for flag in chapter_report.gap_a_flags:
                    report.append(f"**Line {flag.line_number}:**\n")
                    report.append(f"- JP: `{flag.jp_text[:80]}{'...' if len(flag.jp_text) > 80 else ''}`\n")
                    if flag.en_text:
                        report.append(f"- EN: `{flag.en_text[:80]}{'...' if len(flag.en_text) > 80 else ''}`\n")
                    if flag.analysis:
                        report.append(f"- Emotion: **{flag.analysis.emotion_word}** ({flag.analysis.emotion_en})\n")
                        report.append(f"- Action: **{flag.analysis.action_word}**\n")
                        report.append(f"- Context: {flag.analysis.context_type}\n")
                    report.append(f"- Status: `{flag.status}`\n\n")
            
            # Gap C
            if chapter_report.gap_c_flags:
                report.append("### Gap C: Sarcasm/Subtext Detection\n\n")
                for flag in chapter_report.gap_c_flags:
                    report.append(f"**Line {flag.line_number}:**\n")
                    report.append(f"- JP: `{flag.jp_text[:80]}{'...' if len(flag.jp_text) > 80 else ''}`\n")
                    if flag.en_text:
                        report.append(f"- EN: `{flag.en_text[:80]}{'...' if len(flag.en_text) > 80 else ''}`\n")
                    if flag.analysis:
                        report.append(f"- Archetype: **{flag.analysis.archetype.value}**\n")
                        report.append(f"- Markers: {', '.join(flag.analysis.markers_found[:3])}\n")
                        report.append(f"- Confidence: {flag.analysis.confidence:.0%}\n")
                    report.append(f"- Status: `{flag.status}`\n\n")
            
            # Gap B
            if chapter_report.gap_b_flags:
                report.append("### Gap B: Ruby Visual Jokes\n\n")
                for flag in chapter_report.gap_b_flags:
                    report.append(f"**Line {flag.line_number}:**\n")
                    if flag.analysis:
                        report.append(f"- Kanji: {flag.analysis.kanji} ({flag.analysis.ruby})\n")
                        report.append(f"- Type: **{flag.analysis.joke_type.value}**\n")
                        report.append(f"- Treatment: {flag.analysis.en_treatment}\n")
                        report.append(f"- TL Note: {'Yes' if flag.analysis.needs_tl_note else 'No'}\n")
                    report.append(f"- Status: `{flag.status}`\n\n")
        
        report_text = "".join(report)
        
        # Save to file
        report_path = self.audits_dir / "GAP_REVIEW_REPORT.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        logger.info(f"Generated review report: {report_path}")
        return report_text
    
    def _update_summary(self):
        """Update volume summary statistics"""
        summary = {"gap_a": 0, "gap_b": 0, "gap_c": 0, "total": 0}
        
        for chapter_report in self.volume_report.chapters.values():
            summary["gap_a"] += len(chapter_report.gap_a_flags)
            summary["gap_b"] += len(chapter_report.gap_b_flags)
            summary["gap_c"] += len(chapter_report.gap_c_flags)
        
        summary["total"] = summary["gap_a"] + summary["gap_b"] + summary["gap_c"]
        self.volume_report.summary = summary
    
    # =========================================================================
    # Full Volume Analysis
    # =========================================================================
    
    def analyze_volume(self) -> VolumeGapReport:
        """
        Analyze all chapters in the volume.
        
        Returns:
            VolumeGapReport with all flagged passages
        """
        jp_files = sorted(self.jp_dir.glob("CHAPTER_*.md"))
        
        logger.info(f"Analyzing {len(jp_files)} chapters for gap patterns...")
        
        for jp_file in jp_files:
            match = re.search(r'CHAPTER_(\d+)\.md', jp_file.name)
            if match:
                chapter_num = int(match.group(1))
                self.analyze_chapter_pre_translation(chapter_num)
        
        self._update_summary()
        self._save_report()
        self.generate_review_report()
        
        logger.info(f"Volume analysis complete: {self.volume_report.summary}")
        return self.volume_report


# =============================================================================
# CLI Interface
# =============================================================================

def run_gap_analysis(volume_id: str, chapters: List[int] = None) -> bool:
    """
    CLI entry point for gap analysis.
    
    Args:
        volume_id: Volume ID (e.g., "2218") or full volume directory name
        chapters: Specific chapters to analyze (None = all)
        
    Returns:
        True if successful
    """
    from pathlib import Path
    
    # Find volume directory
    work_dir = Path(__file__).parent.parent / "WORK"
    
    # Check if volume_id is already a full directory name
    full_path = work_dir / volume_id
    if full_path.exists() and full_path.is_dir():
        volume_path = full_path
    else:
        # Try to find by partial ID (last 4 chars)
        volume_dirs = list(work_dir.glob(f"*_{volume_id}"))
        
        if not volume_dirs:
            print(f"❌ Volume {volume_id} not found in WORK/")
            return False
        
        volume_path = volume_dirs[0]
    
    print(f"📂 Found volume: {volume_path.name}")
    
    # Initialize engine - analyze EN output instead of VN
    engine = GapIntegrationEngine(volume_path, target_language="EN")
    
    if chapters:
        for ch in chapters:
            engine.analyze_chapter_pre_translation(ch)
    else:
        engine.analyze_volume()
    
    # Generate report
    engine.generate_review_report()
    
    print("\n✅ Gap analysis complete!")
    print(f"   Gap A: {engine.volume_report.summary.get('gap_a', 0)} flags")
    print(f"   Gap B: {engine.volume_report.summary.get('gap_b', 0)} flags")
    print(f"   Gap C: {engine.volume_report.summary.get('gap_c', 0)} flags")
    print(f"\n📄 Review report: {engine.audits_dir / 'GAP_REVIEW_REPORT.md'}")
    
    return True


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python gap_integration.py <volume_id> [chapter_nums...]")
        print("Example: python gap_integration.py 2218")
        print("Example: python gap_integration.py 2218 1 2 3")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    chapters = [int(c) for c in sys.argv[2:]] if len(sys.argv) > 2 else None
    
    success = run_gap_analysis(volume_id, chapters)
    sys.exit(0 if success else 1)
