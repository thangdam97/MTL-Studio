"""
Dialogue Analyzer & Formality Scorer
Extracts character dialogue from EN markdown files and scores formality level
Part of Phase 3.5 Character Voice Validation System

Based on learnings from Kimi ni Todoke Vol 1 audit (Feb 2026)
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict


@dataclass
class DialogueInstance:
    """Single instance of character dialogue"""
    character: str
    text: str
    chapter: int
    line_number: int
    dialogue_type: str  # 'spoken' or 'internal'
    formality_score: Optional[float] = None
    violations: Optional[List[str]] = None


@dataclass
class CharacterProfile:
    """Character voice profile from manifest"""
    name: str
    voice_type: str
    formality_level: int
    formality_range: List[int]
    speech_markers: Dict
    internal_monologue: Optional[Dict] = None
    validation: Optional[Dict] = None
    notes: str = ""


class DialogueAnalyzer:
    """Extract and analyze character dialogue from EN chapters"""
    
    # Common dialogue attribution patterns
    SPEAKER_PATTERNS = [
        r'"([^"]+)"\s*,?\s*(\w+)\s+(?:said|asked|replied|answered|called|shouted|whispered|muttered|cried)',
        r'(\w+)\s+(?:said|asked|replied|answered|called|shouted|whispered|muttered|cried)\s*,?\s*"([^"]+)"',
        r'"([^"]+)"\s*—\s*(\w+)',  # Em dash style
        r'(\w+):\s*"([^"]+)"',  # Colon style
    ]
    
    # Internal monologue markers
    INTERNAL_PATTERNS = [
        r'\*([^*]+)\*',  # Italics (asterisk markdown)
        r'_([^_]+)_',    # Italics (underscore markdown)
        r'\(([^)]+)\)',  # Parenthetical thoughts
    ]
    
    def __init__(self, work_dir: Path, character_profiles: List[Dict]):
        """
        Initialize analyzer
        
        Args:
            work_dir: Path to volume work directory (contains EN/, JP/ folders)
            character_profiles: List of character profile dicts from manifest
        """
        self.work_dir = Path(work_dir)
        self.en_dir = self.work_dir / "EN"
        self.profiles = {p['name']: CharacterProfile(**p) for p in character_profiles}
        self.dialogue_instances: List[DialogueInstance] = []
        
    def extract_all_dialogue(self) -> List[DialogueInstance]:
        """Extract dialogue from all EN chapters"""
        self.dialogue_instances = []
        
        # Find all EN chapter files
        chapter_files = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        
        for chapter_file in chapter_files:
            chapter_num = self._extract_chapter_number(chapter_file.name)
            self._extract_from_chapter(chapter_file, chapter_num)
        
        return self.dialogue_instances
    
    def _extract_chapter_number(self, filename: str) -> int:
        """Extract chapter number from filename"""
        match = re.search(r'CHAPTER_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def _extract_from_chapter(self, chapter_file: Path, chapter_num: int):
        """Extract dialogue from single chapter file"""
        with open(chapter_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            # Extract spoken dialogue
            for pattern in self.SPEAKER_PATTERNS:
                matches = re.finditer(pattern, line)
                for match in matches:
                    # Pattern variations: some have character first, some have dialogue first
                    groups = match.groups()
                    if len(groups) >= 2:
                        # Determine which group is character vs dialogue
                        dialogue = groups[0] if len(groups[0]) > len(groups[1]) else groups[1]
                        character = groups[1] if dialogue == groups[0] else groups[0]
                        
                        # Normalize character name
                        character = self._normalize_character_name(character)
                        
                        if character in self.profiles:
                            self.dialogue_instances.append(DialogueInstance(
                                character=character,
                                text=dialogue.strip(),
                                chapter=chapter_num,
                                line_number=line_num,
                                dialogue_type='spoken'
                            ))
            
            # Extract internal monologue
            for pattern in self.INTERNAL_PATTERNS:
                matches = re.finditer(pattern, line)
                for match in matches:
                    thought = match.group(1).strip()
                    # Internal thoughts usually attributed by context, not explicit tags
                    # For now, skip if we can't determine character
                    # (Future: use context analysis to infer speaker)
                    pass
    
    def _normalize_character_name(self, name: str) -> str:
        """Normalize character name to match profile"""
        # Handle common variations
        name = name.strip().title()
        
        # Map common aliases to profile names
        aliases = {
            'Sadako': 'Kuronuma Sawako',  # Kimi ni Todoke specific
            'Sawako': 'Kuronuma Sawako',
            'Kazehaya': 'Kazehaya Shouta',
            'Chizuru': 'Yoshida Chizuru',
            'Ayane': 'Yano Ayane',
        }
        
        return aliases.get(name, name)
    
    def score_formality(self, dialogue: DialogueInstance, profile: CharacterProfile) -> Tuple[float, List[str]]:
        """
        Score dialogue formality against character profile
        
        Returns:
            (formality_score: 0-100, violations: list of issues)
        """
        text = dialogue.text.lower()
        score = 50  # Start at neutral
        violations = []
        
        # Check required markers (positive scoring)
        required_markers = profile.speech_markers.get('required', [])
        for marker in required_markers:
            if marker.lower() in text:
                score += 5
        
        # Check avoided markers (negative scoring)
        avoided_markers = profile.speech_markers.get('avoid', [])
        for marker in avoided_markers:
            if marker.lower() in text:
                score -= 15
                violations.append(f"Used '{marker}' (should avoid)")
        
        # Count contractions (affects formality)
        contractions = self._count_contractions(text)
        total_words = len(text.split())
        
        if total_words > 0:
            contraction_ratio = contractions / total_words
            
            # High formality characters should have few contractions
            if profile.formality_level >= 70:
                if contraction_ratio > 0.2:  # More than 20% contractions
                    score -= 10
                    violations.append(f"Too many contractions ({contractions}/{total_words} = {contraction_ratio:.0%})")
            
            # Low formality characters should have many contractions
            elif profile.formality_level <= 40:
                if contraction_ratio < 0.5:  # Less than 50% contractions
                    score -= 5
                    violations.append(f"Too few contractions for casual character")
        
        # Check sentence completeness (formal = complete sentences)
        if profile.formality_level >= 70:
            if not text.strip().endswith(('.', '!', '?', '…')):
                score -= 5
                violations.append("Incomplete sentence (formal characters use complete sentences)")
        
        # Clamp score to 0-100 range
        score = max(0, min(100, score))
        
        return score, violations
    
    def _count_contractions(self, text: str) -> int:
        """Count contractions in text"""
        contractions = [
            "i'm", "you're", "he's", "she's", "it's", "we're", "they're",
            "isn't", "aren't", "wasn't", "weren't", "hasn't", "haven't",
            "can't", "couldn't", "won't", "wouldn't", "don't", "doesn't", "didn't",
            "i'll", "you'll", "he'll", "she'll", "we'll", "they'll",
            "i'd", "you'd", "he'd", "she'd", "we'd", "they'd",
            "i've", "you've", "we've", "they've",
            "wanna", "gonna", "gotta", "shoulda", "coulda", "woulda"
        ]
        text_lower = text.lower()
        return sum(1 for c in contractions if c in text_lower)
    
    def analyze_character(self, character_name: str) -> Dict:
        """
        Analyze all dialogue for specific character
        
        Returns:
            {
                'character': str,
                'profile_target': int,
                'average_score': float,
                'instances_analyzed': int,
                'violations_count': int,
                'below_threshold': bool,
                'samples': List[Dict]
            }
        """
        profile = self.profiles.get(character_name)
        if not profile:
            return {'error': f'No profile found for {character_name}'}
        
        # Get all dialogue for this character
        character_dialogue = [d for d in self.dialogue_instances if d.character == character_name]
        
        if len(character_dialogue) < profile.validation.get('samples_required', 3):
            return {
                'character': character_name,
                'error': f'Insufficient samples ({len(character_dialogue)} found, {profile.validation.get("samples_required", 3)} required)'
            }
        
        # Score each dialogue instance
        total_score = 0
        total_violations = 0
        samples = []
        
        for dialogue in character_dialogue:
            score, violations = self.score_formality(dialogue, profile)
            dialogue.formality_score = score
            dialogue.violations = violations
            
            total_score += score
            total_violations += len(violations)
            
            samples.append({
                'chapter': dialogue.chapter,
                'line': dialogue.line_number,
                'text': dialogue.text[:80] + '...' if len(dialogue.text) > 80 else dialogue.text,
                'score': score,
                'violations': violations
            })
        
        average_score = total_score / len(character_dialogue)
        min_threshold = profile.validation.get('min_formality_score', profile.formality_level - 10)
        
        return {
            'character': character_name,
            'profile_target': profile.formality_level,
            'profile_range': profile.formality_range,
            'average_score': round(average_score, 1),
            'instances_analyzed': len(character_dialogue),
            'violations_count': total_violations,
            'below_threshold': average_score < min_threshold,
            'min_threshold': min_threshold,
            'samples': samples[:10]  # First 10 samples for report
        }
    
    def generate_report(self, output_file: Optional[Path] = None) -> Dict:
        """
        Generate full character voice validation report
        
        Returns:
            {
                'summary': {...},
                'characters': {...},
                'issues': [...]
            }
        """
        # Extract dialogue if not already done
        if not self.dialogue_instances:
            self.extract_all_dialogue()
        
        report = {
            'summary': {
                'total_dialogue_instances': len(self.dialogue_instances),
                'characters_analyzed': len(self.profiles),
                'characters_below_threshold': 0,
                'total_violations': 0
            },
            'characters': {},
            'issues': []
        }
        
        # Analyze each character
        for character_name in self.profiles.keys():
            analysis = self.analyze_character(character_name)
            report['characters'][character_name] = analysis
            
            if 'error' not in analysis:
                if analysis['below_threshold']:
                    report['summary']['characters_below_threshold'] += 1
                    report['issues'].append({
                        'severity': 'HIGH',
                        'character': character_name,
                        'issue': f"Average formality {analysis['average_score']} below threshold {analysis['min_threshold']}",
                        'recommendation': f"Review {character_name}'s dialogue and increase formality"
                    })
                
                report['summary']['total_violations'] += analysis['violations_count']
        
        # Write report to file if specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        
        return report
    
    def print_report_summary(self):
        """Print human-readable report summary"""
        report = self.generate_report()
        
        print("\n" + "="*70)
        print("CHARACTER VOICE VALIDATION REPORT")
        print("="*70)
        
        print(f"\nTotal Dialogue Instances: {report['summary']['total_dialogue_instances']}")
        print(f"Characters Analyzed: {report['summary']['characters_analyzed']}")
        print(f"Characters Below Threshold: {report['summary']['characters_below_threshold']}")
        print(f"Total Violations: {report['summary']['total_violations']}")
        
        print("\n" + "-"*70)
        print("CHARACTER ANALYSIS")
        print("-"*70)
        
        for char_name, analysis in report['characters'].items():
            if 'error' in analysis:
                print(f"\n⚠️  {char_name}: {analysis['error']}")
                continue
            
            status = "✅ PASS" if not analysis['below_threshold'] else "❌ FAIL"
            print(f"\n{status} {char_name}")
            print(f"  Target: {analysis['profile_target']} | Actual: {analysis['average_score']} | Threshold: {analysis['min_threshold']}")
            print(f"  Instances: {analysis['instances_analyzed']} | Violations: {analysis['violations_count']}")
            
            if analysis['violations_count'] > 0 and analysis['samples']:
                print(f"\n  Sample Violations:")
                for sample in analysis['samples'][:3]:
                    if sample['violations']:
                        print(f"    Ch{sample['chapter']}, L{sample['line']}: \"{sample['text']}\"")
                        for violation in sample['violations']:
                            print(f"      → {violation}")
        
        if report['issues']:
            print("\n" + "-"*70)
            print("ISSUES REQUIRING ATTENTION")
            print("-"*70)
            for issue in report['issues']:
                print(f"\n[{issue['severity']}] {issue['character']}")
                print(f"  Issue: {issue['issue']}")
                print(f"  Recommendation: {issue['recommendation']}")
        
        print("\n" + "="*70)


def main():
    """CLI entry point for testing"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python dialogue_analyzer.py <work_directory> [manifest.json]")
        print("\nExample:")
        print("  python dialogue_analyzer.py WORK/volume_dir/")
        print("  python dialogue_analyzer.py WORK/volume_dir/ WORK/volume_dir/manifest.json")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    manifest_path = Path(sys.argv[2]) if len(sys.argv) > 2 else work_dir / "manifest.json"
    
    # Load character profiles from manifest
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    character_profiles = manifest.get('character_profiles', [])
    
    if not character_profiles:
        print("⚠️  No character_profiles found in manifest.json")
        print("Add character_profiles section per MANIFEST_SCHEMA_V3.7_CHARACTER_VOICE.md")
        sys.exit(1)
    
    # Run analysis
    analyzer = DialogueAnalyzer(work_dir, character_profiles)
    analyzer.extract_all_dialogue()
    analyzer.print_report_summary()
    
    # Save JSON report
    report_path = work_dir / "character_voice_report.json"
    analyzer.generate_report(report_path)
    print(f"\n📄 Full report saved to: {report_path}")


if __name__ == "__main__":
    main()
