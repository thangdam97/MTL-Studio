#!/usr/bin/env python3
"""
Prose Quality QC Tool

Detects translationese patterns based on industry standard analysis
comparing MTL output with Yen Press and J-Novel Club standards.

Patterns are loaded from: config/anti_ai_ism_patterns.json
Reference: RESEARCH_INDUSTRIAL_PRACTICES.md
"""

import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json


# ============================================================
# PATTERN LOADER - Single Source of Truth
# ============================================================

def load_patterns_from_json(config_path: Path = None) -> Dict:
    """Load anti-AI-ism patterns from JSON config file."""
    if config_path is None:
        # Default path relative to this script
        script_dir = Path(__file__).parent.parent
        config_path = script_dir / "config" / "anti_ai_ism_patterns.json"
    
    if not config_path.exists():
        print(f"Warning: Pattern config not found at {config_path}, using built-in defaults")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def patterns_to_tuples(patterns_json: Dict) -> Tuple[List, List, List]:
    """Convert JSON patterns to tuple format for compatibility."""
    critical = []
    major = []
    minor = []
    
    if patterns_json is None:
        return critical, major, minor
    
    # CRITICAL patterns
    if "CRITICAL" in patterns_json:
        for p in patterns_json["CRITICAL"].get("patterns", []):
            critical.append((
                p["regex"],
                p["display"],
                p["fix"],
                p["source"]
            ))
    
    # MAJOR patterns - flatten categories
    if "MAJOR" in patterns_json:
        for category_name, category_data in patterns_json["MAJOR"].get("categories", {}).items():
            for p in category_data.get("patterns", []):
                flags = re.MULTILINE if p.get("flags") == "MULTILINE" else 0
                if flags:
                    major.append((p["regex"], p["display"], p["fix"], p["source"], flags))
                else:
                    major.append((p["regex"], p["display"], p["fix"], p["source"]))
    
    # MINOR patterns - flatten categories
    if "MINOR" in patterns_json:
        for category_name, category_data in patterns_json["MINOR"].get("categories", {}).items():
            for p in category_data.get("patterns", []):
                flags = re.MULTILINE if p.get("flags") == "MULTILINE" else 0
                if flags:
                    minor.append((p["regex"], p["display"], p["fix"], p["source"], flags))
                else:
                    minor.append((p["regex"], p["display"], p["fix"], p["source"]))
    
    return critical, major, minor


@dataclass
class ProseIssue:
    """Single prose quality issue."""
    category: str
    severity: str  # critical, major, minor
    pattern: str
    text: str
    line_number: int
    suggestion: str
    context: str = ""


@dataclass
class FileAnalysis:
    """Analysis results for a single file."""
    filepath: str
    issues: List[ProseIssue] = field(default_factory=list)
    word_count: int = 0
    sentence_count: int = 0
    
    @property
    def issue_density(self) -> float:
        """Issues per 1000 words."""
        if self.word_count == 0:
            return 0
        return (len(self.issues) / self.word_count) * 1000
    
    def grade(self) -> str:
        """Calculate prose quality grade."""
        density = self.issue_density
        critical_count = sum(1 for i in self.issues if i.severity == "critical")
        
        if critical_count > 0:
            return "C" if critical_count < 5 else "F"
        if density < 2:
            return "A+"
        if density < 5:
            return "A"
        if density < 10:
            return "B"
        if density < 20:
            return "C"
        return "F"


class ProseQualityChecker:
    """
    Prose quality checker based on industry standard analysis.
    
    Patterns loaded from: config/anti_ai_ism_patterns.json
    
    Detects:
    - Literal Japanese idiom translations
    - Subject repetition (Japanese calque)
    - Overwrought metaphors
    - Transitional word overuse
    - Teen register violations
    - Translationese patterns
    - AI-ism patterns (filter phrases, process verbs, etc.)
    """
    
    def __init__(self, config_path: Path = None):
        """Initialize checker with patterns from JSON config."""
        # Load patterns from JSON
        patterns_json = load_patterns_from_json(config_path)
        
        if patterns_json:
            self.CRITICAL_PATTERNS, self.MAJOR_PATTERNS, self.MINOR_PATTERNS = \
                patterns_to_tuples(patterns_json)
            self.target_density = patterns_json.get("_meta", {}).get("target_density_per_1k_words", 0.02)
        else:
            # Fallback to empty if no config found
            self.CRITICAL_PATTERNS = []
            self.MAJOR_PATTERNS = []
            self.MINOR_PATTERNS = []
            self.target_density = 0.02
    
    # ============================================================
    # SUBJECT REPETITION DETECTION
    # ============================================================
    
    def check_subject_repetition(self, text: str, line_num: int) -> List[ProseIssue]:
        """Detect repeated subjects across consecutive sentences."""
        issues = []
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for i in range(len(sentences) - 1):
            # Extract first word/subject of each sentence
            words1 = sentences[i].split()
            words2 = sentences[i + 1].split()
            
            if not words1 or not words2:
                continue
            
            # Check if same proper noun starts both sentences
            first1 = words1[0].strip('"\'')
            first2 = words2[0].strip('"\'')
            
            # Check for repeated names (capitalized, not common words)
            if (first1 == first2 and 
                first1[0].isupper() and 
                first1.lower() not in {'the', 'a', 'an', 'this', 'that', 'i', 'but', 'and', 'so'}):
                issues.append(ProseIssue(
                    category="subject_repetition",
                    severity="minor",
                    pattern=f"'{first1}' repeated",
                    text=f"...{sentences[i][-50:]} {sentences[i+1][:50]}...",
                    line_number=line_num,
                    suggestion=f"Use pronoun: 'She' / 'He' instead of '{first1}'",
                    context="Japanese calque - English uses pronouns after first mention"
                ))
        
        return issues
    
    # ============================================================
    # METAPHOR DENSITY CHECK
    # ============================================================
    
    def check_metaphor_density(self, text: str, line_num: int) -> List[ProseIssue]:
        """Detect overwrought metaphors (multiple in same sentence)."""
        issues = []
        
        metaphor_markers = [
            r"like a \w+",
            r"as if \w+",
            r"as though \w+",
            r"seemed to \w+",
            r"\w+ was a \w+",  # X was a Y (metaphor)
        ]
        
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            count = 0
            for pattern in metaphor_markers:
                count += len(re.findall(pattern, sentence, re.IGNORECASE))
            
            if count >= 3:
                issues.append(ProseIssue(
                    category="overwrought_metaphor",
                    severity="minor",
                    pattern=f"{count} metaphors in one sentence",
                    text=sentence[:100] + "...",
                    line_number=line_num,
                    suggestion="One strong metaphor > three weak ones",
                    context="Purple prose - reduce metaphor density"
                ))
        
        return issues
    
    # ============================================================
    # MAIN ANALYSIS
    # ============================================================
    
    def analyze_file(self, filepath: Path) -> FileAnalysis:
        """Analyze a single file for prose quality issues."""
        result = FileAnalysis(filepath=str(filepath))
        
        try:
            content = filepath.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  Error reading {filepath}: {e}")
            return result
        
        lines = content.split('\n')
        result.word_count = len(content.split())
        result.sentence_count = len(re.findall(r'[.!?]+', content))
        
        for line_num, line in enumerate(lines, 1):
            # Skip empty lines
            if not line.strip():
                continue
            
            # Check critical patterns
            for pattern_tuple in self.CRITICAL_PATTERNS:
                pattern, name, suggestion, context = pattern_tuple[:4]
                flags = pattern_tuple[4] if len(pattern_tuple) > 4 else 0
                
                matches = re.findall(pattern, line, re.IGNORECASE | flags)
                for match in matches:
                    result.issues.append(ProseIssue(
                        category="critical_translationese",
                        severity="critical",
                        pattern=name,
                        text=match if isinstance(match, str) else match[0],
                        line_number=line_num,
                        suggestion=suggestion,
                        context=context
                    ))
            
            # Check major patterns
            for pattern_tuple in self.MAJOR_PATTERNS:
                pattern, name, suggestion, context = pattern_tuple[:4]
                flags = pattern_tuple[4] if len(pattern_tuple) > 4 else 0
                
                matches = re.findall(pattern, line, re.IGNORECASE | flags)
                for match in matches:
                    result.issues.append(ProseIssue(
                        category="major_translationese",
                        severity="major",
                        pattern=name,
                        text=match if isinstance(match, str) else match[0],
                        line_number=line_num,
                        suggestion=suggestion,
                        context=context
                    ))
            
            # Check minor patterns
            for pattern_tuple in self.MINOR_PATTERNS:
                pattern, name, suggestion, context = pattern_tuple[:4]
                flags = pattern_tuple[4] if len(pattern_tuple) > 4 else 0
                
                matches = re.findall(pattern, line, re.IGNORECASE | flags)
                for match in matches:
                    result.issues.append(ProseIssue(
                        category="minor_style",
                        severity="minor",
                        pattern=name,
                        text=match if isinstance(match, str) else match[0],
                        line_number=line_num,
                        suggestion=suggestion,
                        context=context
                    ))
            
            # Check subject repetition
            result.issues.extend(self.check_subject_repetition(line, line_num))
            
            # Check metaphor density
            result.issues.extend(self.check_metaphor_density(line, line_num))
        
        return result
    
    def analyze_directory(self, directory: Path) -> Dict[str, FileAnalysis]:
        """Analyze all text files in a directory."""
        results = {}
        
        # Find all text/markdown files
        for ext in ['*.txt', '*.md']:
            for filepath in directory.rglob(ext):
                # Skip non-chapter files
                if any(skip in filepath.name.lower() for skip in ['readme', 'config', 'metadata', 'audit']):
                    continue
                
                print(f"  Analyzing: {filepath.name}")
                results[str(filepath)] = self.analyze_file(filepath)
        
        return results


def print_report(results: Dict[str, FileAnalysis], verbose: bool = False):
    """Print formatted analysis report."""
    print("\n" + "=" * 70)
    print("PROSE QUALITY QC REPORT")
    print("Based on Yen Press / J-Novel Club Industry Standards")
    print("=" * 70 + "\n")
    
    total_issues = 0
    total_critical = 0
    total_major = 0
    total_minor = 0
    
    # Sort by filename
    for filepath in sorted(results.keys()):
        analysis = results[filepath]
        filename = Path(filepath).name
        
        critical = sum(1 for i in analysis.issues if i.severity == "critical")
        major = sum(1 for i in analysis.issues if i.severity == "major")
        minor = sum(1 for i in analysis.issues if i.severity == "minor")
        
        total_issues += len(analysis.issues)
        total_critical += critical
        total_major += major
        total_minor += minor
        
        grade = analysis.grade()
        grade_color = {
            "A+": "🏆", "A": "✅", "B": "📝", "C": "⚠️", "F": "❌"
        }.get(grade, "")
        
        print(f"{grade_color} {filename}")
        print(f"   Grade: {grade} | Words: {analysis.word_count:,} | Issues: {len(analysis.issues)}")
        print(f"   Density: {analysis.issue_density:.1f}/1000 words")
        print(f"   Critical: {critical} | Major: {major} | Minor: {minor}")
        
        if verbose and analysis.issues:
            print("\n   Issues:")
            for issue in analysis.issues[:10]:  # Limit to first 10
                print(f"     L{issue.line_number}: [{issue.severity.upper()}] {issue.pattern}")
                print(f"        → {issue.suggestion}")
            if len(analysis.issues) > 10:
                print(f"     ... and {len(analysis.issues) - 10} more issues")
        
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total Files: {len(results)}")
    print(f"Total Issues: {total_issues}")
    print(f"  - Critical: {total_critical}")
    print(f"  - Major: {total_major}")
    print(f"  - Minor: {total_minor}")
    
    # Category breakdown
    category_counts = defaultdict(int)
    for analysis in results.values():
        for issue in analysis.issues:
            category_counts[issue.category] += 1
    
    if category_counts:
        print("\nBy Category:")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            print(f"  - {cat}: {count}")
    
    # Top patterns
    pattern_counts = defaultdict(int)
    for analysis in results.values():
        for issue in analysis.issues:
            pattern_counts[issue.pattern] += 1
    
    if pattern_counts:
        print("\nTop 5 Issues:")
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"  - {pattern}: {count} occurrences")


def main():
    parser = argparse.ArgumentParser(
        description="Prose Quality QC Tool - Detect translationese patterns"
    )
    parser.add_argument(
        "path",
        help="File or directory to analyze"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed issue list"
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--min-severity",
        choices=["critical", "major", "minor"],
        default="minor",
        help="Minimum severity to report"
    )
    
    args = parser.parse_args()
    
    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path does not exist: {path}")
        sys.exit(1)
    
    checker = ProseQualityChecker()
    
    # Verbose: Show loaded patterns info
    if args.verbose:
        print("=" * 70)
        print("PROSE QUALITY QC - Anti-AI-ism Detection")
        print("=" * 70)
        print(f"📁 Config: config/anti_ai_ism_patterns.json")
        print(f"📊 Patterns loaded:")
        print(f"   CRITICAL: {len(checker.CRITICAL_PATTERNS)} patterns (blocks publication)")
        print(f"   MAJOR:    {len(checker.MAJOR_PATTERNS)} patterns (requires revision)")
        print(f"   MINOR:    {len(checker.MINOR_PATTERNS)} patterns (style polish)")
        print(f"🎯 Target density: <{checker.target_density} issues per 1k words")
        print("-" * 70)
    
    print(f"Analyzing: {path}")
    
    if path.is_file():
        results = {str(path): checker.analyze_file(path)}
    else:
        results = checker.analyze_directory(path)
    
    # Filter by severity if specified
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    min_level = severity_order[args.min_severity]
    
    for filepath in results:
        results[filepath].issues = [
            i for i in results[filepath].issues 
            if severity_order.get(i.severity, 2) <= min_level
        ]
    
    if args.json:
        output = {}
        for filepath, analysis in results.items():
            output[filepath] = {
                "grade": analysis.grade(),
                "word_count": analysis.word_count,
                "issue_count": len(analysis.issues),
                "issue_density": analysis.issue_density,
                "issues": [
                    {
                        "category": i.category,
                        "severity": i.severity,
                        "pattern": i.pattern,
                        "line": i.line_number,
                        "suggestion": i.suggestion
                    }
                    for i in analysis.issues
                ]
            }
        print(json.dumps(output, indent=2))
    else:
        print_report(results, verbose=args.verbose)


if __name__ == "__main__":
    main()
