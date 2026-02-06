"""
Atmosphere Marker Analyzer
Counts sensory atmosphere markers in EN translation and validates against genre expectations
Part of Phase 3.5 Genre-Aware Quality Validation System

Based on learnings from Kimi ni Todoke Vol 1 audit (Feb 2026)
Shoujo atmosphere score: 95/100 - This tool ensures that level of quality is maintained
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict, Counter


class AtmosphereAnalyzer:
    """Analyze sensory atmosphere markers in translated text"""
    
    def __init__(self, work_dir: Path, atmosphere_config: Dict):
        """
        Initialize analyzer
        
        Args:
            work_dir: Path to volume work directory (contains EN/ folder)
            atmosphere_config: atmosphere_validation dict from publisher database
        """
        self.work_dir = Path(work_dir)
        self.en_dir = self.work_dir / "EN"
        self.config = atmosphere_config
        self.results = defaultdict(list)
        
    def analyze_all_chapters(self) -> Dict:
        """Analyze all EN chapters and return comprehensive report"""
        chapter_files = sorted(self.en_dir.glob("CHAPTER_*_EN.md"))
        
        total_words = 0
        total_markers = Counter()
        total_kira_kira = 0
        chapter_reports = []
        
        for chapter_file in chapter_files:
            chapter_num = self._extract_chapter_number(chapter_file.name)
            report = self._analyze_chapter(chapter_file, chapter_num)
            chapter_reports.append(report)
            
            total_words += report['word_count']
            for category, count in report['marker_counts'].items():
                total_markers[category] += count
            total_kira_kira += report['kira_kira_count']
        
        # Calculate per-1000-word rates
        markers_per_1k = self._calculate_per_1k_rates(total_markers, total_words)
        
        # Validate against thresholds
        validation = self._validate_markers(markers_per_1k, total_kira_kira, len(chapter_reports))
        
        return {
            'summary': {
                'total_words': total_words,
                'total_chapters': len(chapter_reports),
                'markers_per_1000_words': markers_per_1k,
                'kira_kira_per_chapter': round(total_kira_kira / len(chapter_reports), 1) if chapter_reports else 0,
                'validation_status': validation['status'],
                'score': validation['score']
            },
            'validation': validation,
            'chapters': chapter_reports
        }
    
    def _extract_chapter_number(self, filename: str) -> int:
        """Extract chapter number from filename"""
        match = re.search(r'CHAPTER_(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def _analyze_chapter(self, chapter_file: Path, chapter_num: int) -> Dict:
        """Analyze single chapter for atmosphere markers"""
        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count words
        words = re.findall(r'\b\w+\b', content.lower())
        word_count = len(words)
        
        # Count markers by category
        marker_counts = {}
        marker_instances = {}
        
        markers_config = self.config.get('markers_per_1000_words', {})
        for category, config in markers_config.items():
            patterns = config.get('patterns', [])
            count, instances = self._count_patterns(content.lower(), patterns)
            marker_counts[category] = count
            marker_instances[category] = instances
        
        # Count kira-kira moments
        kira_kira_config = self.config.get('kira_kira_moments', {})
        kira_patterns = kira_kira_config.get('patterns', [])
        kira_count, kira_instances = self._count_patterns(content.lower(), kira_patterns)
        
        # Count micro-emotions (show-don't-tell physical reactions)
        micro_config = self.config.get('micro_emotions', {})
        micro_patterns = micro_config.get('physical_reactions', [])
        micro_count, micro_instances = self._count_patterns(content.lower(), micro_patterns)
        
        return {
            'chapter': chapter_num,
            'word_count': word_count,
            'marker_counts': marker_counts,
            'marker_instances': marker_instances,
            'kira_kira_count': kira_count,
            'kira_kira_instances': kira_instances,
            'micro_emotion_count': micro_count,
            'micro_emotion_instances': micro_instances
        }
    
    def _count_patterns(self, text: str, patterns: List[str]) -> Tuple[int, List[str]]:
        """Count occurrences of patterns in text"""
        instances = []
        for pattern in patterns:
            # Use word boundary matching to avoid partial matches
            regex = r'\b' + re.escape(pattern) + r'\b'
            matches = list(re.finditer(regex, text, re.IGNORECASE))
            for match in matches:
                # Get context (20 chars before and after)
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end].strip()
                instances.append({
                    'pattern': pattern,
                    'context': context
                })
        
        return len(instances), instances[:10]  # Return count and first 10 samples
    
    def _calculate_per_1k_rates(self, marker_counts: Counter, total_words: int) -> Dict:
        """Calculate markers per 1000 words"""
        if total_words == 0:
            return {}
        
        per_1k = {}
        for category, count in marker_counts.items():
            per_1k[category] = round((count / total_words) * 1000, 2)
        
        return per_1k
    
    def _validate_markers(self, markers_per_1k: Dict, total_kira_kira: int, chapter_count: int) -> Dict:
        """Validate marker density against genre thresholds"""
        validation = {
            'status': 'PASS',
            'score': 100,
            'issues': [],
            'strengths': [],
            'categories': {}
        }
        
        # Validate each marker category
        markers_config = self.config.get('markers_per_1000_words', {})
        for category, config in markers_config.items():
            min_threshold = config.get('min', 0)
            target = config.get('target', min_threshold * 2)
            actual = markers_per_1k.get(category, 0)
            
            status = 'EXCELLENT' if actual >= target else 'GOOD' if actual >= min_threshold else 'BELOW_THRESHOLD'
            
            validation['categories'][category] = {
                'min': min_threshold,
                'target': target,
                'actual': actual,
                'status': status
            }
            
            if status == 'BELOW_THRESHOLD':
                validation['status'] = 'REVIEW'
                validation['score'] -= 10
                validation['issues'].append(f"{category.title()} markers below minimum ({actual:.1f} < {min_threshold})")
            elif status == 'EXCELLENT':
                validation['strengths'].append(f"{category.title()} markers excellent ({actual:.1f} >= {target})")
        
        # Validate kira-kira moments
        kira_config = self.config.get('kira_kira_moments', {})
        min_kira = kira_config.get('min_per_chapter', 0)
        target_kira = kira_config.get('target_per_chapter', min_kira * 2)
        actual_kira_per_chapter = total_kira_kira / chapter_count if chapter_count > 0 else 0
        
        validation['kira_kira'] = {
            'min_per_chapter': min_kira,
            'target_per_chapter': target_kira,
            'actual_per_chapter': round(actual_kira_per_chapter, 1),
            'total': total_kira_kira
        }
        
        if actual_kira_per_chapter < min_kira:
            validation['status'] = 'REVIEW'
            validation['score'] -= 15
            validation['issues'].append(f"Kira-kira moments below minimum ({actual_kira_per_chapter:.1f} < {min_kira} per chapter)")
        elif actual_kira_per_chapter >= target_kira:
            validation['strengths'].append(f"Kira-kira moments excellent ({actual_kira_per_chapter:.1f} >= {target_kira} per chapter)")
        
        # Clamp score
        validation['score'] = max(0, min(100, validation['score']))
        
        if validation['score'] >= 90:
            validation['grade'] = 'A+'
        elif validation['score'] >= 85:
            validation['grade'] = 'A'
        elif validation['score'] >= 80:
            validation['grade'] = 'A-'
        elif validation['score'] >= 75:
            validation['grade'] = 'B+'
        else:
            validation['grade'] = 'B or below'
        
        return validation
    
    def generate_report(self, output_file: Path = None) -> Dict:
        """Generate full atmosphere analysis report"""
        report = self.analyze_all_chapters()
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        
        return report
    
    def print_report_summary(self):
        """Print human-readable report summary"""
        report = self.generate_report()
        
        print("\n" + "="*70)
        print("ATMOSPHERE MARKER ANALYSIS REPORT")
        print("="*70)
        
        summary = report['summary']
        print(f"\nTotal Words: {summary['total_words']:,}")
        print(f"Total Chapters: {summary['total_chapters']}")
        print(f"Validation Status: {summary['validation_status']}")
        print(f"Atmosphere Score: {summary['score']}/100 ({report['validation']['grade']})")
        
        print("\n" + "-"*70)
        print("SENSORY MARKERS (per 1,000 words)")
        print("-"*70)
        
        for category, data in report['validation']['categories'].items():
            status_emoji = "✅" if data['status'] == 'EXCELLENT' else "✓" if data['status'] == 'GOOD' else "⚠️"
            print(f"{status_emoji} {category.title():15} {data['actual']:6.2f} (min: {data['min']}, target: {data['target']})")
        
        kira = report['validation']['kira_kira']
        kira_status = "✅" if kira['actual_per_chapter'] >= kira['target_per_chapter'] else "✓" if kira['actual_per_chapter'] >= kira['min_per_chapter'] else "⚠️"
        print(f"\n{kira_status} Kira-Kira Moments: {kira['actual_per_chapter']:.1f} per chapter (min: {kira['min_per_chapter']}, target: {kira['target_per_chapter']})")
        print(f"   Total: {kira['total']} across {summary['total_chapters']} chapters")
        
        if report['validation']['strengths']:
            print("\n" + "-"*70)
            print("STRENGTHS")
            print("-"*70)
            for strength in report['validation']['strengths']:
                print(f"  ✅ {strength}")
        
        if report['validation']['issues']:
            print("\n" + "-"*70)
            print("ISSUES REQUIRING ATTENTION")
            print("-"*70)
            for issue in report['validation']['issues']:
                print(f"  ⚠️  {issue}")
        
        print("\n" + "-"*70)
        print("SAMPLE INSTANCES (First chapter)")
        print("-"*70)
        
        if report['chapters']:
            first_chapter = report['chapters'][0]
            print(f"\nChapter {first_chapter['chapter']} - {first_chapter['word_count']} words")
            
            for category, instances in first_chapter['marker_instances'].items():
                if instances:
                    print(f"\n  {category.title()} ({len(instances)} instances):")
                    for inst in instances[:3]:  # Show first 3
                        print(f"    • \"{inst['pattern']}\": ...{inst['context']}...")
        
        print("\n" + "="*70)


def main():
    """CLI entry point"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python atmosphere_analyzer.py <work_directory> [publisher_database.json]")
        print("\nExample:")
        print("  python atmosphere_analyzer.py WORK/volume_dir/")
        sys.exit(1)
    
    work_dir = Path(sys.argv[1])
    
    # Load atmosphere config from publisher database or manifest
    publisher_db_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "pipeline/librarian/publisher_profiles/publisher_database.json"
    
    with open(publisher_db_path, 'r', encoding='utf-8') as f:
        publisher_db = json.load(f)
    
    # Try to get config from manifest first
    manifest_path = work_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        publisher_name = manifest.get('metadata', {}).get('publisher_en', '')
        
        # Look up publisher config
        if publisher_name and publisher_name in publisher_db.get('publishers', {}):
            atmosphere_config = publisher_db['publishers'][publisher_name].get('atmosphere_validation', {})
        else:
            print(f"⚠️  Publisher '{publisher_name}' not found in database")
            atmosphere_config = {}
    else:
        print("⚠️  No manifest.json found, using default Cobalt Bunko (shoujo) config")
        atmosphere_config = publisher_db['publishers']['Cobalt Bunko'].get('atmosphere_validation', {})
    
    if not atmosphere_config:
        print("❌ No atmosphere_validation config found")
        print("Add atmosphere_validation section to publisher profile")
        sys.exit(1)
    
    # Run analysis
    analyzer = AtmosphereAnalyzer(work_dir, atmosphere_config)
    analyzer.print_report_summary()
    
    # Save JSON report
    report_path = work_dir / "atmosphere_analysis_report.json"
    analyzer.generate_report(report_path)
    print(f"\n📄 Full report saved to: {report_path}")


if __name__ == "__main__":
    main()
