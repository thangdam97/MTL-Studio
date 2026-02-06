"""
Japanese Dialect Detector
=========================

Detects regional Japanese dialects (Kansai, Tohoku, Kyushu, etc.) in source text
and flags them for special translation treatment.

Integrates with the translator to:
1. Pre-scan chapters for dialect markers
2. Add dialect preservation guidance to translation prompts
3. Suggest English dialect equivalents (e.g., Kansai → Southern US)

Author: MTL Studio
Version: 1.0
"""

import re
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Load dialect patterns from config
PATTERNS_FILE = Path(__file__).parent.parent / "config" / "gap_patterns_curated.json"


class DialectType(Enum):
    """Japanese regional dialects"""
    KANSAI = "kansai"      # Osaka/Kyoto area
    TOHOKU = "tohoku"      # Northern Honshu
    KYUSHU = "kyushu"      # Southern Japan
    OKINAWA = "okinawa"    # Ryukyu
    HIROSHIMA = "hiroshima"  # Chugoku region
    HAKATA = "hakata"      # Fukuoka dialect (subset of Kyushu)
    NAGOYA = "nagoya"      # Chubu region
    STANDARD = "standard"  # Tokyo standard


@dataclass
class DialectFlag:
    """A detected dialect marker in the text"""
    dialect: DialectType
    line_number: int
    matched_text: str
    pattern_matched: str
    context: str  # Surrounding text
    confidence: float
    en_equivalent_suggestion: Optional[str] = None


@dataclass
class DialectReport:
    """Summary of dialect analysis for a chapter"""
    chapter_id: str
    total_flags: int
    dialects_found: Dict[str, int]  # dialect_name -> count
    flags: List[DialectFlag]
    translation_guidance: str


class DialectDetector:
    """
    Detects and flags Japanese regional dialects for translation.
    
    Features:
    - Pattern-based detection for major dialect groups
    - Confidence scoring based on marker density
    - English equivalent suggestions for localization
    - Integration with translator prompt system
    """
    
    # Dialect patterns (can be augmented from config)
    DEFAULT_PATTERNS = {
        DialectType.KANSAI: {
            "markers": [
                r"や(で|ねん|ん|わ)$",  # Copula forms
                r"ホンマ",              # Really (honto ni)
                r"なんでやねん",         # Why?! (tsukkomi)
                r"おおきに",             # Thank you
                r"せやな",               # That's right
                r"あかん",               # No good
                r"ちゃう",               # Wrong / to be wrong
                r"けったい",             # Strange
                r"しんどい",             # Tired (Kansai origin)
                r"めっちゃ",             # Very (Kansai-derived)
                r"ぎょうさん",           # Many
            ],
            "en_equivalent": "Southern US (y'all, fixin' to) or British working class",
            "tone": "rough_pragmatic"
        },
        DialectType.TOHOKU: {
            "markers": [
                r"だべ$",               # Copula
                r"んだ$",               # Copula
                r"べ$",                 # Emphasis
                r"だっぺ",              # Copula
                r"けろ$",               # Request form
            ],
            "en_equivalent": "Rural American / Appalachian",
            "tone": "rural_gentle"
        },
        DialectType.KYUSHU: {
            "markers": [
                r"たい$",               # Emphasis
                r"ばい$",               # Emphasis
                r"けん$",               # Because
                r"っちゃ",              # Emphasis
                r"ごたる",              # Like/seems
                r"とよ$",               # Emphasis (Hakata)
            ],
            "en_equivalent": "Texas / Southwestern US",
            "tone": "energetic_warm"
        },
        DialectType.OKINAWA: {
            "markers": [
                r"さー$",               # Sentence-ending
                r"からさー",            # Because
                r"だはず",              # Should be
                r"でーじ",              # Very
                r"ちゃーがんじゅー",    # Strong/healthy
            ],
            "en_equivalent": "Hawaiian Pidgin or Caribbean",
            "tone": "relaxed_warm"
        },
        DialectType.HIROSHIMA: {
            "markers": [
                r"じゃけん",            # Because
                r"じゃけぇ",            # Because
                r"のう$",               # Emphasis
                r"わし",                # I (male)
            ],
            "en_equivalent": "Scottish or Irish",
            "tone": "rough_direct"
        },
        DialectType.NAGOYA: {
            "markers": [
                r"だがや",              # Copula
                r"だがね",              # Copula
                r"みゃー",              # Emphasis
                r"でら",                # Very
            ],
            "en_equivalent": "Midwest American",
            "tone": "friendly_direct"
        }
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize with optional external config."""
        self.patterns = self._load_patterns(config_path)
        self.confidence_threshold = 0.70
    
    def _load_patterns(self, config_path: Optional[Path]) -> Dict:
        """Load patterns from config file or use defaults."""
        patterns = self.DEFAULT_PATTERNS.copy()
        
        # Try to load from external config
        path = config_path or PATTERNS_FILE
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Merge dialect markers from config
                dialect_config = config.get('warning_thresholds', {}).get('dialect_detection', {})
                external_markers = dialect_config.get('markers', {})
                
                for dialect_name, marker_list in external_markers.items():
                    try:
                        dialect_type = DialectType(dialect_name)
                        if dialect_type in patterns:
                            patterns[dialect_type]['markers'].extend(marker_list)
                        else:
                            patterns[dialect_type] = {
                                'markers': marker_list,
                                'en_equivalent': 'Regional English variant',
                                'tone': 'regional'
                            }
                    except ValueError:
                        pass  # Unknown dialect type, skip
                
                # Update confidence threshold if specified
                threshold = dialect_config.get('threshold')
                if threshold:
                    self.confidence_threshold = threshold
                    
            except (json.JSONDecodeError, KeyError):
                pass  # Use defaults if config parsing fails
        
        return patterns
    
    def detect_dialects(self, text: str, chapter_id: str = "unknown") -> DialectReport:
        """
        Scan text for dialect markers and return a report.
        
        Args:
            text: Japanese source text
            chapter_id: Chapter identifier for reporting
            
        Returns:
            DialectReport with all detected flags and guidance
        """
        flags: List[DialectFlag] = []
        dialect_counts: Dict[str, int] = {}
        
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            for dialect_type, config in self.patterns.items():
                for pattern in config['markers']:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        # Calculate confidence based on match quality
                        confidence = self._calculate_confidence(line, pattern)
                        
                        if confidence >= self.confidence_threshold:
                            # Extract context
                            start_ctx = max(0, match.start() - 30)
                            end_ctx = min(len(line), match.end() + 30)
                            context = line[start_ctx:end_ctx]
                            
                            flag = DialectFlag(
                                dialect=dialect_type,
                                line_number=line_num,
                                matched_text=match.group(),
                                pattern_matched=pattern,
                                context=context,
                                confidence=confidence,
                                en_equivalent_suggestion=config['en_equivalent']
                            )
                            flags.append(flag)
                            
                            # Count dialects
                            dialect_name = dialect_type.value
                            dialect_counts[dialect_name] = dialect_counts.get(dialect_name, 0) + 1
        
        # Generate guidance
        guidance = self._generate_guidance(dialect_counts, flags)
        
        return DialectReport(
            chapter_id=chapter_id,
            total_flags=len(flags),
            dialects_found=dialect_counts,
            flags=flags,
            translation_guidance=guidance
        )
    
    def _calculate_confidence(self, line: str, pattern: str) -> float:
        """
        Calculate confidence score for a dialect match.
        
        Factors:
        - Match in dialogue (「」) = higher confidence
        - Multiple markers in same line = higher confidence
        - Pattern specificity (longer patterns = higher confidence)
        """
        confidence = 0.75  # Base confidence
        
        # Boost if in dialogue
        if '「' in line or '」' in line:
            confidence += 0.15
        
        # Boost for pattern length (longer = more specific)
        if len(pattern) > 5:
            confidence += 0.05
        
        # Cap at 1.0
        return min(confidence, 1.0)
    
    def _generate_guidance(self, dialect_counts: Dict[str, int], flags: List[DialectFlag]) -> str:
        """Generate translation guidance based on detected dialects."""
        if not flags:
            return ""
        
        lines = ["## Dialect Detection Report", ""]
        
        # Summary
        total = sum(dialect_counts.values())
        lines.append(f"**{total} dialect marker(s) detected** in this chapter:")
        lines.append("")
        
        for dialect, count in sorted(dialect_counts.items(), key=lambda x: -x[1]):
            # Get equivalent suggestion
            try:
                dialect_type = DialectType(dialect)
                config = self.patterns.get(dialect_type, {})
                equivalent = config.get('en_equivalent', 'Regional variant')
                tone = config.get('tone', 'regional')
            except ValueError:
                equivalent = 'Regional variant'
                tone = 'regional'
            
            lines.append(f"- **{dialect.upper()}**: {count} instance(s)")
            lines.append(f"  - Suggested English equivalent: {equivalent}")
            lines.append(f"  - Tone: {tone}")
        
        lines.append("")
        lines.append("### Translation Guidance")
        lines.append("")
        
        # Get primary dialect
        primary = max(dialect_counts.items(), key=lambda x: x[1])[0] if dialect_counts else None
        
        if primary == "kansai":
            lines.extend([
                "**Kansai Dialect Preservation Strategy:**",
                "- Use contracted forms: 'Cryin'' instead of 'Crying'",
                "- Add conversational tags: 'y'hear?' / 'ain't it?'",
                "- Use 'quit' instead of 'stop' for commands (rougher tone)",
                "- Consider Southern US dialect markers for working-class speakers",
                "- Preserve direct/pragmatic speech style (less hedging)",
                ""
            ])
        elif primary == "tohoku":
            lines.extend([
                "**Tohoku Dialect Preservation Strategy:**",
                "- Use rural American markers: 'reckon', 'might could'",
                "- Slower, gentler pacing in dialogue",
                "- Consider Appalachian patterns for elderly speakers",
                ""
            ])
        elif primary == "kyushu":
            lines.extend([
                "**Kyushu Dialect Preservation Strategy:**",
                "- Use energetic, warm tone",
                "- Texas/Southwestern markers: 'fixin' to', 'all y'all'",
                "- Preserve enthusiastic sentence endings",
                ""
            ])
        else:
            lines.extend([
                f"**{primary.upper() if primary else 'Regional'} Dialect Detected:**",
                "- Preserve regional flavor through vocabulary choices",
                "- Consider appropriate English dialect equivalent",
                "- Maintain consistent register throughout dialogue",
                ""
            ])
        
        # Sample flags
        lines.append("### Sample Markers Detected")
        for flag in flags[:5]:
            lines.append(f"- Line {flag.line_number}: `{flag.matched_text}` in context: \"{flag.context}...\"")
        
        if len(flags) > 5:
            lines.append(f"_(+ {len(flags) - 5} more markers)_")
        
        return "\n".join(lines)
    
    def format_for_prompt(self, report: DialectReport) -> str:
        """Format dialect report for injection into translation prompt."""
        if report.total_flags == 0:
            return ""
        
        return report.translation_guidance


# Convenience function for chapter processor integration
def detect_chapter_dialects(source_text: str, chapter_id: str = "unknown") -> Tuple[bool, str]:
    """
    Quick dialect detection for chapter processor.
    
    Returns:
        Tuple of (has_dialects: bool, guidance_text: str)
    """
    detector = DialectDetector()
    report = detector.detect_dialects(source_text, chapter_id)
    
    return report.total_flags > 0, detector.format_for_prompt(report)


if __name__ == "__main__":
    # Test with sample text
    test_text = """
「なんでやねん！ホンマにあかんわ」
彼女は怒りながらも、どこか楽しそうだった。
「せやな、ちゃうちゃう、めっちゃおもろいやん」
    """
    
    detector = DialectDetector()
    report = detector.detect_dialects(test_text, "test_chapter")
    
    print(f"Detected {report.total_flags} dialect markers")
    print(f"Dialects found: {report.dialects_found}")
    print("\nTranslation Guidance:")
    print(report.translation_guidance)
