#!/usr/bin/env python3
"""
Japanese Dialogue & Grammar Pattern Analyzer

Scans EPUB corpus to extract linguistic patterns for Vietnamese grammar RAG improvement:
1. Japanese interjections (感動詞) and their frequency
2. Sentence-ending particles (終助詞)
3. Honorific/register patterns (敬語)
4. Emotional expressions
5. Onomatopoeia (擬音語/擬態語)
6. Dialogue-specific structures

Usage:
    python scripts/analyze_dialogue_patterns.py --scan      # Full corpus analysis
    python scripts/analyze_dialogue_patterns.py --interjections
    python scripts/analyze_dialogue_patterns.py --particles
    python scripts/analyze_dialogue_patterns.py --export    # Export to JSON

Author: MTL Studio
Date: 2025-01-31
"""

import sys
import json
import argparse
import re
import html
import zipfile
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Set

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# Japanese Linguistic Patterns
# ============================================================

# Interjections (感動詞) - Common in light novels
JAPANESE_INTERJECTIONS = {
    # Surprise/Shock
    r'えっ': 'surprise_mild',
    r'ええっ': 'surprise_strong',
    r'え[ーー]+': 'surprise_prolonged',
    r'うわ[っ]?': 'shock',
    r'うわー': 'shock_prolonged',
    r'ひっ': 'fright',
    r'きゃ[っー]?': 'fright_female',
    r'ぎゃ[っー]?': 'fright_strong',
    r'わっ': 'startle',
    r'あっ': 'realization',
    
    # Agreement/Understanding
    r'うん': 'casual_yes',
    r'ううん': 'casual_no',
    r'はい': 'formal_yes',
    r'ええ': 'polite_yes',
    r'そうだね': 'agreement',
    r'なるほど': 'understanding',
    r'そっか': 'casual_understanding',
    
    # Hesitation/Thinking
    r'えっと': 'hesitation',
    r'えーっと': 'hesitation_long',
    r'あの[ーー]?': 'attention_getter',
    r'その[ーー]?': 'hesitation_polite',
    r'ええと': 'thinking',
    r'うーん': 'pondering',
    r'んー': 'pondering_casual',
    
    # Emotional expressions
    r'やれやれ': 'exasperation',
    r'あーあ': 'disappointment',
    r'はぁ': 'sigh',
    r'ふぅ': 'relief_sigh',
    r'ちっ': 'tch_annoyance',
    r'くっ': 'frustration',
    r'むっ': 'displeasure',
    r'ふん': 'dismissive',
    r'へぇ': 'impressed',
    r'ほう': 'interest',
    
    # Calling/Attention
    r'ねぇ': 'attention_casual',
    r'なぁ': 'attention_male',
    r'ちょっと': 'hey_wait',
    r'おい': 'hey_rough',
    r'ほら': 'look_here',
    r'さぁ': 'well_now',
    r'まぁ': 'well_soft',
    
    # Exclamations
    r'くそ': 'damn',
    r'ちくしょう': 'damn_strong',
    r'しまった': 'oops',
    r'やった': 'yay',
    r'よし': 'alright',
    r'よっし[ゃー]+': 'yay_energetic',
    r'すげー': 'awesome_male',
    r'すごい': 'amazing',
    r'やばい': 'yabai',
    r'マジ': 'seriously',
}

# Sentence-ending particles (終助詞)
SENTENCE_PARTICLES = {
    # Question markers
    r'か[？?]?$': 'question_neutral',
    r'かな[？?]?$': 'wondering',
    r'かしら[？?]?$': 'wondering_female',
    r'の[？?]$': 'question_soft',
    r'だろう[？?]?$': 'rhetorical_male',
    r'でしょう[？?]?$': 'rhetorical_polite',
    
    # Emphasis
    r'よ[！!]?$': 'emphasis',
    r'ね[！!]?$': 'seeking_agreement',
    r'よね[！!]?$': 'confirmation',
    r'ぞ[！!]?$': 'emphasis_male',
    r'ぜ[！!]?$': 'casual_male',
    r'わ[！!]?$': 'soft_female',
    r'な[ぁー]?$': 'reflection',
    r'さ$': 'casual_assertion',
    
    # Softening
    r'けど[ね]?$': 'trailing_but',
    r'から[ね]?$': 'because_trailing',
    r'し[ね]?$': 'listing_reason',
    r'もん$': 'childish_reason',
    r'のに$': 'disappointment',
}

# Honorific patterns
HONORIFIC_PATTERNS = {
    # Keigo levels
    r'です[。？]': 'desu_polite',
    r'ます[。？]': 'masu_polite',
    r'ございます': 'gozaimasu_humble',
    r'いらっしゃ': 'irassharu_honorific',
    r'おっしゃ': 'ossharu_honorific',
    r'くださ': 'kudasai_polite_request',
    r'いただ': 'itadaku_humble',
    
    # Casual speech
    r'だ[。！]': 'da_casual',
    r'じゃん': 'jan_casual',
    r'っす': 'ssu_young_male',
    r'だよ': 'dayo_casual_emphasis',
    r'なの': 'nano_soft',
}

# Onomatopoeia categories
ONOMATOPOEIA = {
    # Emotions
    r'ドキドキ': 'heartbeat_nervous',
    r'わくわく': 'excited',
    r'イライラ': 'irritated',
    r'ニコニコ': 'smiling',
    r'ニヤニヤ': 'grinning',
    r'メソメソ': 'whimpering',
    r'ぐすん': 'sniffling',
    r'えへへ': 'embarrassed_laugh',
    r'あはは': 'laughing',
    r'ふふ': 'chuckling',
    r'くすくす': 'giggling',
    
    # Physical states
    r'ぐったり': 'exhausted',
    r'ぼーっと': 'dazed',
    r'きょとん': 'blank_look',
    r'じーっと': 'staring',
    r'ちらちら': 'glancing',
    r'ごくり': 'gulping',
    
    # Actions/Sounds
    r'ガチャ': 'door_opening',
    r'バタン': 'door_slamming',
    r'ピンポン': 'doorbell',
    r'ブルブル': 'vibrating/shivering',
    r'ゴロゴロ': 'rolling/thunder',
}

# Dialogue structure patterns
DIALOGUE_STRUCTURES = {
    # Incomplete sentences (trailing off)
    r'[。、]\.{2,3}': 'trailing_off',
    r'[ーー]{2,}': 'prolonged_sound',
    r'っ[！!]': 'cut_off_emphatic',
    
    # Quoted speech patterns
    r'「[^」]+」と': 'quoted_with_to',
    r'『[^』]+』': 'inner_thought',
    
    # Interruption patterns
    r'[ーー]っ': 'interrupted',
}


def extract_text_from_epub(epub_path: Path) -> str:
    """Extract text content from EPUB file."""
    text_content = []
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as epub:
            for file_info in epub.filelist:
                filename = file_info.filename
                
                if not (filename.endswith('.xhtml') or filename.endswith('.html')):
                    continue
                
                if 'nav' in filename.lower() or 'toc' in filename.lower():
                    continue
                
                try:
                    content = epub.read(filename).decode('utf-8', errors='ignore')
                    text = re.sub(r'<[^>]+>', ' ', content)
                    text = html.unescape(text)
                    text_content.append(text)
                except:
                    continue
        
        return ' '.join(text_content)
    except Exception as e:
        print(f"Error reading {epub_path.name}: {e}")
        return ""


def extract_dialogue_lines(text: str) -> List[str]:
    """Extract dialogue lines (text within 「」brackets)."""
    dialogues = re.findall(r'「([^」]+)」', text)
    return dialogues


def analyze_interjections(dialogues: List[str]) -> Counter:
    """Count interjection usage in dialogues."""
    counts = Counter()
    
    for dialogue in dialogues:
        for pattern, category in JAPANESE_INTERJECTIONS.items():
            matches = re.findall(pattern, dialogue)
            if matches:
                counts[category] += len(matches)
    
    return counts


def analyze_particles(dialogues: List[str]) -> Counter:
    """Analyze sentence-ending particles."""
    counts = Counter()
    
    for dialogue in dialogues:
        # Split into sentences
        sentences = re.split(r'[。！？]', dialogue)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            for pattern, category in SENTENCE_PARTICLES.items():
                if re.search(pattern, sentence):
                    counts[category] += 1
    
    return counts


def analyze_honorifics(text: str) -> Counter:
    """Analyze honorific/register patterns."""
    counts = Counter()
    
    for pattern, category in HONORIFIC_PATTERNS.items():
        matches = re.findall(pattern, text)
        counts[category] += len(matches)
    
    return counts


def analyze_onomatopoeia(text: str) -> Counter:
    """Count onomatopoeia usage."""
    counts = Counter()
    
    for pattern, category in ONOMATOPOEIA.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        counts[category] += len(matches)
    
    return counts


def analyze_corpus(input_dir: Path, limit: int = None) -> Dict:
    """
    Full corpus analysis.
    
    Returns aggregated statistics and patterns.
    """
    epub_files = sorted(input_dir.glob("*.epub"))
    if limit:
        epub_files = epub_files[:limit]
    
    print(f"Analyzing {len(epub_files)} EPUB files...")
    
    # Aggregated counters
    all_interjections = Counter()
    all_particles = Counter()
    all_honorifics = Counter()
    all_onomatopoeia = Counter()
    
    # Track per-book stats
    book_stats = []
    total_dialogues = 0
    total_chars = 0
    
    for i, epub_path in enumerate(epub_files):
        print(f"  [{i+1}/{len(epub_files)}] {epub_path.name[:50]}...")
        
        text = extract_text_from_epub(epub_path)
        if not text:
            continue
        
        dialogues = extract_dialogue_lines(text)
        
        # Analyze
        interjections = analyze_interjections(dialogues)
        particles = analyze_particles(dialogues)
        honorifics = analyze_honorifics(text)
        onomatopoeia = analyze_onomatopoeia(text)
        
        # Aggregate
        all_interjections.update(interjections)
        all_particles.update(particles)
        all_honorifics.update(honorifics)
        all_onomatopoeia.update(onomatopoeia)
        
        total_dialogues += len(dialogues)
        total_chars += len(text)
        
        book_stats.append({
            'name': epub_path.stem[:50],
            'dialogues': len(dialogues),
            'chars': len(text)
        })
    
    return {
        'summary': {
            'total_books': len(epub_files),
            'total_dialogues': total_dialogues,
            'total_characters': total_chars,
            'avg_dialogues_per_book': total_dialogues // len(epub_files) if epub_files else 0
        },
        'interjections': dict(all_interjections.most_common(50)),
        'particles': dict(all_particles.most_common(30)),
        'honorifics': dict(all_honorifics.most_common(20)),
        'onomatopoeia': dict(all_onomatopoeia.most_common(30)),
        'book_stats': book_stats[:10]  # Top 10 for brevity
    }


def generate_grammar_improvements(analysis: Dict) -> Dict:
    """
    Generate suggested improvements for vietnamese_grammar_rag.json
    based on corpus analysis.
    """
    improvements = {
        "version": "2.0",
        "description": "Corpus-derived improvements for Vietnamese Grammar RAG",
        "source": f"Analyzed from {analysis['summary']['total_books']} light novels",
        
        "new_interjection_mappings": {},
        "new_onomatopoeia_mappings": {},
        "register_frequency_data": {},
        "dialogue_density_baseline": {}
    }
    
    # Map interjections to Vietnamese
    INTERJECTION_VN_MAP = {
        'surprise_mild': ['Ơ', 'Hả', 'Ủa'],
        'surprise_strong': ['Ơ!', 'Cái gì!', 'Sao!'],
        'shock': ['Ối', 'Trời', 'Chà'],
        'fright': ['Hự', 'Ái', 'Hự!'],
        'fright_female': ['Kyaa', 'Ái chà', 'Ôi'],
        'realization': ['À', 'Ồ', 'A'],
        'casual_yes': ['Ừ', 'Ờ', 'Um'],
        'casual_no': ['Không', 'Ừm không', 'Đâu có'],
        'formal_yes': ['Vâng', 'Dạ', 'Vâng ạ'],
        'polite_yes': ['Vâng', 'Dạ vâng', 'Ừm'],
        'hesitation': ['Ừm', 'À', 'Ờ'],
        'hesitation_long': ['Ừm...', 'À...', 'Ờ...'],
        'attention_getter': ['Này', 'Ơ này', 'À'],
        'thinking': ['Ừm', 'Để xem', 'Hmm'],
        'pondering': ['Hmm', 'Ừm...', 'Để nghĩ xem'],
        'exasperation': ['Trời ơi', 'Thôi rồi', 'Mệt ghê'],
        'disappointment': ['Haiz', 'Thở dài', 'Ôi trời'],
        'sigh': ['Hà', 'Phù', 'Thở'],
        'relief_sigh': ['Phù', 'Hú hồn', 'May quá'],
        'tch_annoyance': ['Tch', 'Xì', 'Hừ'],
        'frustration': ['Khh', 'Tức', 'Ức'],
        'displeasure': ['Hừ', 'Hmph', 'Xì'],
        'dismissive': ['Hừ', 'Hứ', 'Xì'],
        'impressed': ['Ồ', 'Chà', 'Hay'],
        'interest': ['Ồ', 'Hoh', 'Thú vị'],
        'attention_casual': ['Này', 'Ê', 'Nè'],
        'attention_male': ['Này', 'Ê', 'Ơi'],
        'hey_wait': ['Khoan', 'Này', 'Ê'],
        'hey_rough': ['Ê', 'Này', 'Ơi'],
        'look_here': ['Này', 'Xem này', 'Kìa'],
        'well_now': ['Nào', 'Thôi nào', 'Đi'],
        'well_soft': ['Ùi', 'Ôi', 'À'],
        'damn': ['Chết tiệt', 'Khốn', 'Đồ khốn'],
        'oops': ['Chết', 'Thôi chết', 'Hỏng rồi'],
        'yay': ['Yeah', 'Hura', 'Tuyệt'],
        'alright': ['Ok', 'Được rồi', 'Tốt'],
        'yay_energetic': ['Yess!', 'Tuyệt vời!', 'Đỉnh!'],
        'awesome_male': ['Đỉnh', 'Siêu', 'Bá'],
        'amazing': ['Tuyệt', 'Đẹp', 'Hay'],
        'yabai': ['Chết', 'Xong rồi', 'Toang'],
        'seriously': ['Thật à', 'Nghiêm túc', 'Thiệt hả'],
    }
    
    # Only include patterns that appeared frequently in corpus
    for category, count in analysis['interjections'].items():
        if count >= 50 and category in INTERJECTION_VN_MAP:  # Threshold
            improvements['new_interjection_mappings'][category] = {
                'frequency': count,
                'vietnamese_options': INTERJECTION_VN_MAP[category],
                'confidence': 'high' if count > 200 else 'medium'
            }
    
    # Onomatopoeia mappings
    ONOMATOPOEIA_VN_MAP = {
        'heartbeat_nervous': ['tim đập thình thịch', 'hồi hộp', 'đập thình thình'],
        'excited': ['háo hức', 'nôn nao', 'phấn khích'],
        'irritated': ['bực bội', 'khó chịu', 'cáu'],
        'smiling': ['tươi cười', 'nở nụ cười', 'cười'],
        'grinning': ['cười toe toét', 'cười nham hiểm', 'nhếch mép'],
        'whimpering': ['sụt sịt', 'thút thít', 'nức nở'],
        'embarrassed_laugh': ['cười ngượng', 'hì hì', 'he he'],
        'laughing': ['ha ha', 'cười lớn', 'cười'],
        'chuckling': ['khúc khích', 'hì hì', 'cười nhẹ'],
        'giggling': ['cười khúc khích', 'cười hí hí', 'cười'],
        'exhausted': ['kiệt sức', 'mệt lả', 'rã rời'],
        'dazed': ['ngẩn ngơ', 'thờ thẫn', 'lơ đễnh'],
        'blank_look': ['ngơ ngác', 'trống rỗng', 'không hiểu'],
        'staring': ['nhìn chằm chằm', 'chăm chú', 'đăm đăm'],
        'glancing': ['liếc', 'đưa mắt', 'nhìn lén'],
        'gulping': ['nuốt nước bọt', 'ực', 'nuốt khan'],
    }
    
    for category, count in analysis['onomatopoeia'].items():
        if count >= 20 and category in ONOMATOPOEIA_VN_MAP:
            improvements['new_onomatopoeia_mappings'][category] = {
                'frequency': count,
                'vietnamese_options': ONOMATOPOEIA_VN_MAP[category]
            }
    
    # Register frequency data
    improvements['register_frequency_data'] = {
        'polite_vs_casual_ratio': (
            analysis['honorifics'].get('desu_polite', 0) + 
            analysis['honorifics'].get('masu_polite', 0)
        ) / max(1, analysis['honorifics'].get('da_casual', 0) + 
                analysis['honorifics'].get('dayo_casual_emphasis', 0)),
        'note': 'Light novels typically have 60-70% casual speech'
    }
    
    # Dialogue density baseline
    improvements['dialogue_density_baseline'] = {
        'avg_dialogues_per_chapter': analysis['summary']['avg_dialogues_per_book'] // 10,
        'expected_particle_rate': '80%+ of dialogue lines should have particles'
    }
    
    return improvements


def print_analysis(analysis: Dict):
    """Pretty print analysis results."""
    print("\n" + "="*70)
    print("CORPUS ANALYSIS RESULTS")
    print("="*70)
    
    summary = analysis['summary']
    print(f"\n📚 Corpus Summary:")
    print(f"   Total books analyzed: {summary['total_books']}")
    print(f"   Total dialogue lines: {summary['total_dialogues']:,}")
    print(f"   Total characters: {summary['total_characters']:,}")
    print(f"   Avg dialogues/book: {summary['avg_dialogues_per_book']}")
    
    print(f"\n🎭 Top Interjections (by frequency):")
    for cat, count in list(analysis['interjections'].items())[:15]:
        print(f"   {cat}: {count:,}")
    
    print(f"\n💬 Top Sentence Particles:")
    for cat, count in list(analysis['particles'].items())[:10]:
        print(f"   {cat}: {count:,}")
    
    print(f"\n🎩 Honorific Patterns:")
    for cat, count in list(analysis['honorifics'].items())[:10]:
        print(f"   {cat}: {count:,}")
    
    print(f"\n🔊 Top Onomatopoeia:")
    for cat, count in list(analysis['onomatopoeia'].items())[:10]:
        print(f"   {cat}: {count:,}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Japanese dialogue patterns")
    parser.add_argument('--scan', action='store_true', help='Full corpus scan')
    parser.add_argument('--limit', type=int, default=None, help='Limit books to analyze')
    parser.add_argument('--export', action='store_true', help='Export improvements JSON')
    parser.add_argument('--output', type=str, default='grammar_improvements.json')
    
    args = parser.parse_args()
    
    input_dir = Path(__file__).parent.parent / "INPUT"
    
    if not input_dir.exists():
        print(f"Error: INPUT directory not found at {input_dir}")
        return 1
    
    if args.scan or args.export:
        analysis = analyze_corpus(input_dir, limit=args.limit)
        print_analysis(analysis)
        
        if args.export:
            improvements = generate_grammar_improvements(analysis)
            
            output_path = Path(__file__).parent.parent / "VN" / args.output
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(improvements, f, ensure_ascii=False, indent=2)
            
            print(f"\n✅ Exported improvements to: {output_path}")
            
            # Also save raw analysis
            analysis_path = Path(__file__).parent.parent / "VN" / "corpus_analysis.json"
            with open(analysis_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Saved raw analysis to: {analysis_path}")
    else:
        parser.print_help()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
