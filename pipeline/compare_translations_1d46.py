#!/usr/bin/env python3
"""
Comprehensive Quality Comparison: NEW (multimodal) vs OLD (pre-multimodal)
Volume: 1d46 - 他校の氷姫を助けたら、お友達から始める事になりました
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import defaultdict
from pipeline.post_processor.grammar_validator import GrammarValidator, GrammarReport

# Common AI-isms to detect
AI_ISMS = [
    r"couldn't help but",
    r"could(?:n't)? help but",
    r"a hint of",
    r"a surge of",
    r"for a moment",
    r"for a brief moment",
    r"for an instant",
    r"in that moment",
    r"a wave of",
    r"a pang of",
    r"a flicker of",
    r"a glimmer of",
    r"a flash of",
    r"washed over",
    r"coursed through",
    r"bubbled up",
    r"welled up",
    r"threatened to",
    r"betrayed (?:his|her|their)",
    r"(?:his|her|their) lips (?:curled|curved|quirked)",
    r"a small smile tugged at",
    r"heart skipped a beat",
    r"warmth (?:bloomed|spread)",
]

class TranslationComparator:
    def __init__(self, new_dir: Path, old_dir: Path):
        self.new_dir = new_dir
        self.old_dir = old_dir
        self.validator = GrammarValidator(auto_fix=False)

    def get_file_pairs(self) -> List[Tuple[Path, Path]]:
        """Get matching file pairs from NEW and OLD directories."""
        new_files = sorted(self.new_dir.glob("*_EN.md"))
        pairs = []

        for new_file in new_files:
            old_file = self.old_dir / new_file.name
            if old_file.exists():
                pairs.append((new_file, old_file))

        return pairs

    def count_ai_isms(self, text: str) -> Dict[str, int]:
        """Count occurrences of AI-isms in text."""
        counts = {}
        total = 0

        for pattern in AI_ISMS:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            if matches > 0:
                counts[pattern] = matches
                total += matches

        counts['__total__'] = total
        return counts

    def count_contractions(self, text: str) -> Dict[str, int]:
        """Count contractions vs full forms to measure dialogue naturalness."""
        contractions = len(re.findall(r"\b(?:I'm|you're|he's|she's|it's|we're|they're|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|won't|wouldn't|can't|couldn't|shouldn't|I'll|you'll|he'll|she'll|we'll|they'll|I've|you've|we've|they've|I'd|you'd|he'd|she'd|we'd|they'd)\b", text, re.IGNORECASE))

        full_forms = len(re.findall(r"\b(?:I am|you are|he is|she is|it is|we are|they are|is not|are not|was not|were not|do not|does not|did not|will not|would not|cannot|could not|should not|I will|you will|he will|she will|we will|they will|I have|you have|we have|they have|I would|you would|he would|she would|we would|they would)\b", text, re.IGNORECASE))

        return {
            'contractions': contractions,
            'full_forms': full_forms,
            'total': contractions + full_forms,
            'contraction_rate': contractions / (contractions + full_forms) if (contractions + full_forms) > 0 else 0
        }

    def extract_dialogue_lines(self, text: str) -> List[str]:
        """Extract dialogue lines from text."""
        lines = text.split('\n')
        dialogue = []

        for line in lines:
            line = line.strip()
            # Match lines starting with " or containing dialogue
            if line.startswith('"') or ('"' in line and not line.startswith('#')):
                dialogue.append(line)

        return dialogue

    def count_words(self, text: str) -> int:
        """Count words in text."""
        return len(re.findall(r'\b\w+\b', text))

    def analyze_file_pair(self, new_file: Path, old_file: Path) -> Dict[str, Any]:
        """Analyze a single file pair."""
        print(f"\nAnalyzing: {new_file.name}")

        # Read files
        with open(new_file, 'r', encoding='utf-8') as f:
            new_text = f.read()

        with open(old_file, 'r', encoding='utf-8') as f:
            old_text = f.read()

        # Grammar validation
        new_grammar = self.validator.validate_file(new_file)
        old_grammar = self.validator.validate_file(old_file)

        # AI-ism analysis
        new_ai_isms = self.count_ai_isms(new_text)
        old_ai_isms = self.count_ai_isms(old_text)

        # Contraction analysis
        new_contractions = self.count_contractions(new_text)
        old_contractions = self.count_contractions(old_text)

        # Dialogue analysis
        new_dialogue = self.extract_dialogue_lines(new_text)
        old_dialogue = self.extract_dialogue_lines(old_text)

        # Word counts
        new_words = self.count_words(new_text)
        old_words = self.count_words(old_text)

        return {
            'file_name': new_file.name,
            'new': {
                'grammar_report': new_grammar,
                'ai_isms': new_ai_isms,
                'contractions': new_contractions,
                'dialogue_lines': len(new_dialogue),
                'word_count': new_words,
                'text': new_text
            },
            'old': {
                'grammar_report': old_grammar,
                'ai_isms': old_ai_isms,
                'contractions': old_contractions,
                'dialogue_lines': len(old_dialogue),
                'word_count': old_words,
                'text': old_text
            }
        }

    def find_visual_references(self, text: str) -> List[str]:
        """Find references to illustrations or visual elements."""
        patterns = [
            r'\[.*?illustration.*?\]',
            r'\[.*?image.*?\]',
            r'\[.*?figure.*?\]',
            r'as shown in',
            r'in the (?:picture|image|illustration)',
            r'visual(?:ly)?',
            r'depicted',
            r'illustrated'
        ]

        references = []
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context_start = max(0, match.start() - 50)
                context_end = min(len(text), match.end() + 50)
                context = text[context_start:context_end].replace('\n', ' ')
                references.append(context)

        return references

    def generate_comparison_report(self) -> Dict[str, Any]:
        """Generate comprehensive comparison report."""
        print("=" * 80)
        print("COMPREHENSIVE QUALITY COMPARISON")
        print("NEW (multimodal) vs OLD (pre-multimodal)")
        print("Volume: 1d46")
        print("=" * 80)

        file_pairs = self.get_file_pairs()
        results = []

        # Analyze each file pair
        for new_file, old_file in file_pairs:
            result = self.analyze_file_pair(new_file, old_file)
            results.append(result)

        # Aggregate statistics
        aggregate = self._aggregate_results(results)

        # Visual context analysis (NEW only)
        visual_analysis = self._analyze_visual_context(results)

        # Find example passages
        examples = self._find_comparison_examples(results)

        return {
            'file_results': results,
            'aggregate': aggregate,
            'visual_analysis': visual_analysis,
            'examples': examples
        }

    def _aggregate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate statistics across all files."""
        new_totals = {
            'grammar_violations': 0,
            'grammar_high': 0,
            'grammar_medium': 0,
            'grammar_low': 0,
            'ai_isms_total': 0,
            'contractions': 0,
            'full_forms': 0,
            'word_count': 0
        }

        old_totals = {
            'grammar_violations': 0,
            'grammar_high': 0,
            'grammar_medium': 0,
            'grammar_low': 0,
            'ai_isms_total': 0,
            'contractions': 0,
            'full_forms': 0,
            'word_count': 0
        }

        for result in results:
            # NEW
            new_totals['grammar_violations'] += result['new']['grammar_report'].total_violations
            new_totals['grammar_high'] += result['new']['grammar_report'].violations_by_severity.get('high', 0)
            new_totals['grammar_medium'] += result['new']['grammar_report'].violations_by_severity.get('medium', 0)
            new_totals['grammar_low'] += result['new']['grammar_report'].violations_by_severity.get('low', 0)
            new_totals['ai_isms_total'] += result['new']['ai_isms'].get('__total__', 0)
            new_totals['contractions'] += result['new']['contractions']['contractions']
            new_totals['full_forms'] += result['new']['contractions']['full_forms']
            new_totals['word_count'] += result['new']['word_count']

            # OLD
            old_totals['grammar_violations'] += result['old']['grammar_report'].total_violations
            old_totals['grammar_high'] += result['old']['grammar_report'].violations_by_severity.get('high', 0)
            old_totals['grammar_medium'] += result['old']['grammar_report'].violations_by_severity.get('medium', 0)
            old_totals['grammar_low'] += result['old']['grammar_report'].violations_by_severity.get('low', 0)
            old_totals['ai_isms_total'] += result['old']['ai_isms'].get('__total__', 0)
            old_totals['contractions'] += result['old']['contractions']['contractions']
            old_totals['full_forms'] += result['old']['contractions']['full_forms']
            old_totals['word_count'] += result['old']['word_count']

        # Calculate rates per 1000 words
        new_totals['grammar_violations_per_1k'] = (new_totals['grammar_violations'] / new_totals['word_count']) * 1000 if new_totals['word_count'] > 0 else 0
        old_totals['grammar_violations_per_1k'] = (old_totals['grammar_violations'] / old_totals['word_count']) * 1000 if old_totals['word_count'] > 0 else 0

        new_totals['ai_isms_per_1k'] = (new_totals['ai_isms_total'] / new_totals['word_count']) * 1000 if new_totals['word_count'] > 0 else 0
        old_totals['ai_isms_per_1k'] = (old_totals['ai_isms_total'] / old_totals['word_count']) * 1000 if old_totals['word_count'] > 0 else 0

        new_totals['contraction_rate'] = new_totals['contractions'] / (new_totals['contractions'] + new_totals['full_forms']) if (new_totals['contractions'] + new_totals['full_forms']) > 0 else 0
        old_totals['contraction_rate'] = old_totals['contractions'] / (old_totals['contractions'] + old_totals['full_forms']) if (old_totals['contractions'] + old_totals['full_forms']) > 0 else 0

        # Calculate improvement/regression percentages
        grammar_change = ((new_totals['grammar_violations_per_1k'] - old_totals['grammar_violations_per_1k']) / old_totals['grammar_violations_per_1k'] * 100) if old_totals['grammar_violations_per_1k'] > 0 else 0

        ai_ism_change = ((new_totals['ai_isms_per_1k'] - old_totals['ai_isms_per_1k']) / old_totals['ai_isms_per_1k'] * 100) if old_totals['ai_isms_per_1k'] > 0 else 0

        return {
            'new': new_totals,
            'old': old_totals,
            'changes': {
                'grammar_violations_change_pct': grammar_change,
                'ai_isms_change_pct': ai_ism_change,
                'contraction_rate_change': new_totals['contraction_rate'] - old_totals['contraction_rate']
            }
        }

    def _analyze_visual_context(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze visual context integration in NEW version."""
        visual_refs = []

        for result in results:
            refs = self.find_visual_references(result['new']['text'])
            if refs:
                visual_refs.append({
                    'file': result['file_name'],
                    'references': refs
                })

        return {
            'total_references': sum(len(r['references']) for r in visual_refs),
            'files_with_references': len(visual_refs),
            'details': visual_refs
        }

    def _find_comparison_examples(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find interesting comparison examples."""
        examples = []

        for result in results:
            new_text = result['new']['text']
            old_text = result['old']['text']

            # Split into paragraphs
            new_paragraphs = [p.strip() for p in new_text.split('\n\n') if p.strip() and not p.strip().startswith('#')]
            old_paragraphs = [p.strip() for p in old_text.split('\n\n') if p.strip() and not p.strip().startswith('#')]

            # Find differences
            for i, (new_para, old_para) in enumerate(zip(new_paragraphs[:20], old_paragraphs[:20])):
                if len(new_para) > 50 and len(old_para) > 50:
                    # Check for significant differences
                    if new_para != old_para:
                        # Calculate similarity
                        common_words = set(new_para.lower().split()) & set(old_para.lower().split())
                        similarity = len(common_words) / max(len(new_para.split()), len(old_para.split()))

                        # If similar structure but different wording (70-95% similarity)
                        if 0.7 <= similarity <= 0.95:
                            examples.append({
                                'file': result['file_name'],
                                'paragraph_index': i,
                                'new': new_para[:300],
                                'old': old_para[:300],
                                'similarity': similarity
                            })

                            if len(examples) >= 15:
                                break

            if len(examples) >= 15:
                break

        return examples[:10]

    def print_report(self, report: Dict[str, Any]):
        """Print formatted comparison report."""
        print("\n" + "=" * 80)
        print("EXECUTIVE SUMMARY")
        print("=" * 80)

        agg = report['aggregate']

        print(f"\n### Grammar Quality")
        print(f"NEW: {agg['new']['grammar_violations']} violations ({agg['new']['grammar_violations_per_1k']:.2f} per 1k words)")
        print(f"  - High: {agg['new']['grammar_high']}, Medium: {agg['new']['grammar_medium']}, Low: {agg['new']['grammar_low']}")
        print(f"\nOLD: {agg['old']['grammar_violations']} violations ({agg['old']['grammar_violations_per_1k']:.2f} per 1k words)")
        print(f"  - High: {agg['old']['grammar_high']}, Medium: {agg['old']['grammar_medium']}, Low: {agg['old']['grammar_low']}")
        print(f"\nChange: {agg['changes']['grammar_violations_change_pct']:+.1f}%")

        print(f"\n### AI-ism Frequency")
        print(f"NEW: {agg['new']['ai_isms_total']} occurrences ({agg['new']['ai_isms_per_1k']:.2f} per 1k words)")
        print(f"OLD: {agg['old']['ai_isms_total']} occurrences ({agg['old']['ai_isms_per_1k']:.2f} per 1k words)")
        print(f"Change: {agg['changes']['ai_isms_change_pct']:+.1f}%")

        print(f"\n### Dialogue Naturalness (Contraction Rate)")
        print(f"NEW: {agg['new']['contraction_rate']:.1%} ({agg['new']['contractions']} contractions / {agg['new']['full_forms']} full forms)")
        print(f"OLD: {agg['old']['contraction_rate']:.1%} ({agg['old']['contractions']} contractions / {agg['old']['full_forms']} full forms)")
        print(f"Change: {agg['changes']['contraction_rate_change']:+.1%}")

        print(f"\n### Word Counts")
        print(f"NEW: {agg['new']['word_count']:,} words")
        print(f"OLD: {agg['old']['word_count']:,} words")
        print(f"Difference: {agg['new']['word_count'] - agg['old']['word_count']:+,} words ({((agg['new']['word_count'] / agg['old']['word_count']) - 1) * 100:+.1f}%)")

        # Visual context
        print("\n" + "=" * 80)
        print("VISUAL CONTEXT INTEGRATION (NEW only)")
        print("=" * 80)
        vis = report['visual_analysis']
        print(f"\nTotal visual references: {vis['total_references']}")
        print(f"Files with visual references: {vis['files_with_references']}")

        # Chapter breakdown
        print("\n" + "=" * 80)
        print("CHAPTER-BY-CHAPTER BREAKDOWN")
        print("=" * 80)

        for result in report['file_results']:
            print(f"\n### {result['file_name']}")
            print(f"Grammar violations: NEW={result['new']['grammar_report'].total_violations} | OLD={result['old']['grammar_report'].total_violations}")
            print(f"AI-isms: NEW={result['new']['ai_isms'].get('__total__', 0)} | OLD={result['old']['ai_isms'].get('__total__', 0)}")
            print(f"Word count: NEW={result['new']['word_count']:,} | OLD={result['old']['word_count']:,}")

        # Examples
        print("\n" + "=" * 80)
        print("SIDE-BY-SIDE COMPARISON EXAMPLES")
        print("=" * 80)

        for i, example in enumerate(report['examples'], 1):
            print(f"\n### Example {i} ({example['file']}, similarity: {example['similarity']:.1%})")
            print(f"\nOLD:")
            print(example['old'])
            print(f"\nNEW:")
            print(example['new'])
            print("-" * 80)

    def save_detailed_report(self, report: Dict[str, Any], output_path: Path):
        """Save detailed report to JSON."""
        # Convert GrammarReport objects to dicts for JSON serialization
        serializable_report = {
            'aggregate': report['aggregate'],
            'visual_analysis': report['visual_analysis'],
            'examples': report['examples'],
            'file_results': []
        }

        for result in report['file_results']:
            serializable_result = {
                'file_name': result['file_name'],
                'new': {
                    'grammar_report': result['new']['grammar_report'].to_dict(),
                    'ai_isms': result['new']['ai_isms'],
                    'contractions': result['new']['contractions'],
                    'dialogue_lines': result['new']['dialogue_lines'],
                    'word_count': result['new']['word_count']
                },
                'old': {
                    'grammar_report': result['old']['grammar_report'].to_dict(),
                    'ai_isms': result['old']['ai_isms'],
                    'contractions': result['old']['contractions'],
                    'dialogue_lines': result['old']['dialogue_lines'],
                    'word_count': result['old']['word_count']
                }
            }
            serializable_report['file_results'].append(serializable_result)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_report, f, indent=2, ensure_ascii=False)

        print(f"\n\nDetailed report saved to: {output_path}")


def main():
    new_dir = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/他校の氷姫を助けたら、お友達から始める事になりました_20260205_1d46/EN")
    old_dir = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/他校の氷姫を助けたら、お友達から始める事になりました_20260205_1d46/EN_premultimodal")

    comparator = TranslationComparator(new_dir, old_dir)
    report = comparator.generate_comparison_report()
    comparator.print_report(report)

    # Save detailed report
    output_path = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/他校の氷姫を助けたら、お友達から始める事になりました_20260205_1d46/translation_comparison_report.json")
    comparator.save_detailed_report(report, output_path)

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
