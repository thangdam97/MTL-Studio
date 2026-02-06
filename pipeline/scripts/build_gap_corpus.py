#!/usr/bin/env python3
"""
Gap Corpus Builder - Extract patterns from 107 INPUT EPUBs for 3 Gaps.

Gap A: Emotion + Action patterns for sentence surgery
Gap C: Sarcasm/Hesitation/Contradiction patterns for subtext detection  
Gap B: Ruby text with comedic context for visual joke handling

Extracts from:
1. Raw EPUB content (for JP patterns)
2. Existing WORK/ JP-VN pairs (for aligned examples)
"""

import json
import re
import zipfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict, Counter
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
PIPELINE_DIR = Path(__file__).parent.parent
INPUT_DIR = PIPELINE_DIR / "INPUT"
WORK_DIR = PIPELINE_DIR / "WORK"
CONFIG_DIR = PIPELINE_DIR / "config"

# Output corpus files
EMOTION_ACTION_CORPUS = CONFIG_DIR / "emotion_action_corpus.json"
SARCASM_PATTERNS_CORPUS = CONFIG_DIR / "sarcasm_patterns_corpus.json"
RUBY_CONTEXT_CORPUS = CONFIG_DIR / "ruby_context_corpus.json"


@dataclass
class EmotionActionPattern:
    """Gap A: Emotion + Action pattern for sentence surgery."""
    jp_text: str                    # Original JP sentence
    emotion_word: str               # Detected emotion (e.g., 悲しそう, 怒って)
    action_word: str                # Associated action (e.g., 歩いた, 立ち去った)
    context_type: str               # dialogue, narrative
    source_epub: str                # Source EPUB filename
    source_chapter: str             # Chapter reference
    jp_sentence_count: int          # Number of JP sentences in this segment
    suggested_compression: str = "" # Suggested compressed EN version


@dataclass  
class SarcasmPattern:
    """Gap C: Sarcasm/Subtext pattern for detection."""
    jp_text: str                    # Original JP dialogue
    pattern_type: str               # hesitation, contradiction, tsundere_denial, lying
    markers: List[str]              # Detected markers (stuttering, trailing, etc.)
    speaker_archetype: str          # TSUNDERE, KUUDERE, etc. (if known)
    context_before: str             # Preceding context (body language, etc.)
    context_after: str              # Following context
    implication: str                # What the subtext means
    confidence: float               # Detection confidence
    source_epub: str
    source_chapter: str


@dataclass
class RubyJokePattern:
    """Gap B: Ruby visual joke pattern."""
    kanji: str                      # Base text
    ruby: str                       # Ruby reading
    joke_type: str                  # kirakira, archaic, misdirection
    context: str                    # Surrounding text
    character_reaction: str         # How characters react (if any)
    reveal_timing: str              # first_mention, delayed, character_reaction
    needs_note: bool                # Whether TL note is recommended
    source_epub: str


class GapCorpusBuilder:
    """
    Extract patterns from 107 EPUBs for Gap A, B, C.
    
    Uses:
    - Raw EPUB extraction for JP patterns
    - WORK/ aligned pairs for high-quality examples
    """
    
    def __init__(self):
        self.emotion_action_patterns: List[EmotionActionPattern] = []
        self.sarcasm_patterns: List[SarcasmPattern] = []
        self.ruby_joke_patterns: List[RubyJokePattern] = []
        
        # Statistics
        self.stats = {
            "epubs_processed": 0,
            "work_volumes_processed": 0,
            "emotion_action_count": 0,
            "sarcasm_count": 0,
            "ruby_joke_count": 0,
        }
        
        # Pattern libraries for detection
        self._load_detection_patterns()
    
    def _load_detection_patterns(self):
        """Load regex patterns for Gap detection."""
        
        # Gap A: Emotion words in Japanese
        self.emotion_words = {
            # Sad emotions
            "悲し": "sad",
            "寂し": "lonely", 
            "辛": "painful",
            "泣": "crying",
            "涙": "tears",
            "落ち込": "depressed",
            "しょんぼり": "dejected",
            
            # Angry emotions
            "怒": "angry",
            "腹立": "irritated",
            "イライラ": "frustrated",
            "ムカ": "pissed",
            "憤": "furious",
            "キレ": "snapped",
            
            # Happy emotions
            "嬉し": "happy",
            "喜": "joyful",
            "楽し": "fun",
            "ニコニコ": "smiling",
            "ウキウキ": "excited",
            "はしゃ": "frolicking",
            
            # Nervous emotions
            "緊張": "nervous",
            "ドキドキ": "heart pounding",
            "不安": "anxious",
            "びくびく": "trembling",
            "おどおど": "timid",
            "焦": "panicking",
            
            # Embarrassed emotions
            "恥ずかし": "embarrassed",
            "照れ": "shy",
            "赤面": "blushing",
            "顔が赤": "face red",
            "耳まで赤": "ears red",
            
            # Surprised emotions
            "驚": "surprised",
            "びっくり": "startled",
            "目を丸": "eyes wide",
            "呆然": "stunned",
        }
        
        # Gap A: Action verbs that can carry emotion
        self.action_verbs = [
            "歩", "走", "立", "座", "去", "出", "入", 
            "言", "話", "叫", "呟", "囁",
            "見", "眺", "睨", "振り返",
            "笑", "泣", "怒鳴",
        ]
        
        # Gap C: Hesitation markers
        self.hesitation_markers = {
            "stuttering": [
                r"[あ-んア-ン]、[あ-んア-ン]",  # あ、あの
                r"[あ-んア-ン]っ、",              # えっ、
                r"そ、それ",                      # そ、それは
                r"わ、私",                        # わ、私
                r"ぼ、僕",                        # ぼ、僕
                r"お、俺",                        # お、俺
            ],
            "trailing": [
                r"…ね$",
                r"…かな$",
                r"…だけど$",
                r"…けど$",
                r"…でも$",
                r"…が$",
            ],
            "hedging": [
                r"まあ[、。]",
                r"ちょっと[、。]",
                r"別に[、。]",
                r"なんか[、。]",
                r"一応[、。]",
            ],
        }
        
        # Gap C: Contradiction markers (body language vs. words)
        self.contradiction_markers = {
            "avoidance": [
                "目を逸らす", "目を逸らし", "顔を背け", "視線を外",
                "目を合わせず", "目をそらし", "うつむ",
            ],
            "physical_tension": [
                "手が震え", "声が震え", "体が震え",
                "拳を握", "唇を噛", "歯を食いしば",
            ],
            "emotional_leak": [
                "顔が赤", "耳まで赤", "頬を染め",
                "涙が", "目が潤",
            ],
        }
        
        # Gap C: Tsundere denial patterns
        self.tsundere_patterns = [
            r"別に.{0,20}(ない|ねー|ねぇ)(けど|が|でも|わけ)?",
            r"誰が.{0,20}(なんて|って)(言った|思った)?",
            r"勘違いしないで",
            r"そんな(わけ|こと)ない",
            r"ち、違う",
            r"バ、バカ",
            r"う、うるさい",
        ]
        
        # Gap C: Lying indicators (positive words + negative context)
        self.lying_indicators = {
            "positive_assertions": [
                "大丈夫", "平気", "問題ない", "何でもない",
                "心配しない", "気にしない",
            ],
            "negative_context": [
                "震え", "赤", "逸ら", "俯", "握",
            ],
        }
        
        # Gap B: Kira-kira name indicators
        self.kirakira_indicators = [
            # Kanji that often have unusual readings
            r"[愛美海心優空翔陽]",
            # Context indicating name surprise
            "キラキラネーム", "変わった名前", "珍しい名前",
            "えっ", "まさか", "本当に",
        ]
    
    def extract_from_epub(self, epub_path: Path) -> Tuple[List[str], List[Dict]]:
        """
        Extract text and ruby entries from EPUB.
        
        Returns:
            (text_lines, ruby_entries)
        """
        text_lines = []
        ruby_entries = []
        
        try:
            with zipfile.ZipFile(epub_path, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith(('.xhtml', '.html', '.htm')):
                        try:
                            content = zf.read(name).decode('utf-8')
                            soup = BeautifulSoup(content, 'html.parser')
                            
                            # Extract ruby annotations
                            for ruby in soup.find_all('ruby'):
                                rb = ruby.find('rb')
                                rt = ruby.find('rt')
                                if rb and rt:
                                    kanji = rb.get_text(strip=True)
                                    reading = rt.get_text(strip=True)
                                    context = self._get_surrounding_text(ruby, 50)
                                    ruby_entries.append({
                                        "kanji": kanji,
                                        "ruby": reading,
                                        "context": context,
                                        "source_file": name,
                                    })
                            
                            # Extract plain text
                            for p in soup.find_all(['p', 'div']):
                                text = p.get_text(strip=True)
                                if text and len(text) > 5:
                                    text_lines.append(text)
                                    
                        except Exception as e:
                            logger.debug(f"Error parsing {name}: {e}")
                            
        except zipfile.BadZipFile:
            logger.warning(f"Invalid EPUB: {epub_path}")
            
        return text_lines, ruby_entries
    
    def _get_surrounding_text(self, element, chars: int = 50) -> str:
        """Get text surrounding an element."""
        parent = element.parent
        if parent:
            full_text = parent.get_text()
            element_text = element.get_text()
            idx = full_text.find(element_text)
            if idx >= 0:
                start = max(0, idx - chars)
                end = min(len(full_text), idx + len(element_text) + chars)
                return full_text[start:end]
        return ""
    
    def detect_emotion_action_patterns(self, text_lines: List[str], epub_name: str) -> List[EmotionActionPattern]:
        """
        Detect Gap A patterns: Emotion + Action in same sentence/segment.
        
        Looks for patterns like:
        - 悲しそうに歩いた (walked looking sad)
        - 怒りながら立ち去った (left angrily)
        """
        patterns = []
        
        for i, line in enumerate(text_lines):
            # Check for emotion words
            for emotion_jp, emotion_en in self.emotion_words.items():
                if emotion_jp in line:
                    # Check for action verbs nearby
                    for action in self.action_verbs:
                        if action in line:
                            # Determine if dialogue or narrative
                            is_dialogue = "「" in line or "」" in line
                            context_type = "dialogue" if is_dialogue else "narrative"
                            
                            # Count JP sentences (rough: by 。)
                            sentence_count = line.count("。") + 1
                            
                            pattern = EmotionActionPattern(
                                jp_text=line,
                                emotion_word=emotion_jp,
                                action_word=action,
                                context_type=context_type,
                                source_epub=epub_name,
                                source_chapter=f"line_{i}",
                                jp_sentence_count=sentence_count,
                            )
                            patterns.append(pattern)
                            break  # One pattern per line max
                    break  # One emotion per line max
        
        return patterns
    
    def detect_sarcasm_patterns(self, text_lines: List[str], epub_name: str) -> List[SarcasmPattern]:
        """
        Detect Gap C patterns: Hesitation, Contradiction, Tsundere denial.
        """
        patterns = []
        
        for i, line in enumerate(text_lines):
            markers_found = []
            pattern_type = ""
            confidence = 0.0
            implication = ""
            
            # Check hesitation markers
            for marker_type, marker_patterns in self.hesitation_markers.items():
                for pattern in marker_patterns:
                    if re.search(pattern, line):
                        markers_found.append(f"{marker_type}:{pattern}")
                        pattern_type = "hesitation"
                        confidence = 0.7
                        implication = "Speaker is uncertain or reluctant"
            
            # Check tsundere patterns (higher confidence)
            for pattern in self.tsundere_patterns:
                if re.search(pattern, line):
                    markers_found.append(f"tsundere:{pattern}")
                    pattern_type = "tsundere_denial"
                    confidence = 0.9
                    implication = "Defensive denial of true feelings"
            
            # Check contradiction patterns (body language)
            context_before = text_lines[i-1] if i > 0 else ""
            context_after = text_lines[i+1] if i < len(text_lines)-1 else ""
            
            for marker_type, markers in self.contradiction_markers.items():
                for marker in markers:
                    # Check if body language appears BEFORE or AFTER positive assertion
                    if marker in context_before or marker in context_after:
                        for positive in self.lying_indicators["positive_assertions"]:
                            if positive in line:
                                markers_found.append(f"contradiction:{marker}+{positive}")
                                pattern_type = "contradiction"
                                confidence = 0.85
                                implication = "Speaker's words don't match body language (lying/hiding emotion)"
            
            if markers_found and confidence >= 0.7:
                # Determine archetype from context (simplified)
                archetype = self._guess_archetype(line, context_before, context_after)
                
                sarcasm_pattern = SarcasmPattern(
                    jp_text=line,
                    pattern_type=pattern_type,
                    markers=markers_found,
                    speaker_archetype=archetype,
                    context_before=context_before[:100],
                    context_after=context_after[:100],
                    implication=implication,
                    confidence=confidence,
                    source_epub=epub_name,
                    source_chapter=f"line_{i}",
                )
                patterns.append(sarcasm_pattern)
        
        return patterns
    
    def _guess_archetype(self, line: str, before: str, after: str) -> str:
        """Guess speaker archetype from context."""
        combined = line + before + after
        
        if any(p in combined for p in ["ツンデレ", "別に", "バカ", "勘違い"]):
            return "TSUNDERE"
        if any(p in combined for p in ["…", "静か", "無表情"]):
            return "KUUDERE"
        if any(p in combined for p in ["あ、あの", "す、すみません"]):
            return "DANDERE"
        if any(p in combined for p in ["お嬢様", "ですわ", "なさい"]):
            return "OJOU"
        if any(p in combined for p in ["ギャル", "マジ", "ウケる"]):
            return "GYARU"
        
        return "UNKNOWN"
    
    def detect_ruby_jokes(self, ruby_entries: List[Dict], epub_name: str) -> List[RubyJokePattern]:
        """
        Detect Gap B patterns: Ruby text with comedic context.
        
        Looks for:
        - Kira-kira names (kanji with unexpected katakana reading)
        - Delayed reveals (name without ruby first, then with)
        - Visual misdirection
        """
        patterns = []
        
        # Track name occurrences to detect delayed reveals
        name_occurrences = defaultdict(list)
        
        for entry in ruby_entries:
            kanji = entry["kanji"]
            ruby = entry["ruby"]
            context = entry["context"]
            
            joke_type = ""
            needs_note = False
            reveal_timing = "first_mention"
            character_reaction = ""
            
            # Check for kira-kira name (kanji with katakana reading)
            is_katakana_ruby = bool(re.match(r'^[ァ-ヶー]+$', ruby))
            is_kanji_base = bool(re.match(r'^[一-龯]+$', kanji))
            
            if is_kanji_base and is_katakana_ruby and len(kanji) >= 2:
                # Likely kira-kira name
                joke_type = "kirakira"
                needs_note = True
                
                # Check for reaction in context
                for indicator in self.kirakira_indicators:
                    if indicator in context:
                        character_reaction = f"Contains: {indicator}"
                        reveal_timing = "character_reaction"
                        break
            
            # Check for archaic/unusual reading
            elif is_kanji_base and len(ruby) > len(kanji) * 2:
                # Ruby much longer than kanji = unusual reading
                joke_type = "archaic"
                needs_note = True
            
            if joke_type:
                pattern = RubyJokePattern(
                    kanji=kanji,
                    ruby=ruby,
                    joke_type=joke_type,
                    context=context[:200],
                    character_reaction=character_reaction,
                    reveal_timing=reveal_timing,
                    needs_note=needs_note,
                    source_epub=epub_name,
                )
                patterns.append(pattern)
                
        return patterns
    
    def process_epub(self, epub_path: Path):
        """Process single EPUB for all gaps."""
        epub_name = epub_path.name
        logger.info(f"Processing: {epub_name}")
        
        text_lines, ruby_entries = self.extract_from_epub(epub_path)
        
        if not text_lines:
            logger.warning(f"No text extracted from {epub_name}")
            return
        
        # Gap A: Emotion + Action
        ea_patterns = self.detect_emotion_action_patterns(text_lines, epub_name)
        self.emotion_action_patterns.extend(ea_patterns)
        
        # Gap C: Sarcasm
        sc_patterns = self.detect_sarcasm_patterns(text_lines, epub_name)
        self.sarcasm_patterns.extend(sc_patterns)
        
        # Gap B: Ruby jokes
        rj_patterns = self.detect_ruby_jokes(ruby_entries, epub_name)
        self.ruby_joke_patterns.extend(rj_patterns)
        
        self.stats["epubs_processed"] += 1
        self.stats["emotion_action_count"] = len(self.emotion_action_patterns)
        self.stats["sarcasm_count"] = len(self.sarcasm_patterns)
        self.stats["ruby_joke_count"] = len(self.ruby_joke_patterns)
    
    def process_work_volume(self, volume_dir: Path):
        """
        Process WORK volume for aligned JP-VN pairs.
        Higher quality patterns from translated volumes.
        """
        jp_dir = volume_dir / "JP"
        vn_dir = volume_dir / "VN"
        
        if not jp_dir.exists() or not vn_dir.exists():
            return
        
        volume_name = volume_dir.name
        logger.info(f"Processing WORK volume: {volume_name}")
        
        # Process JP files
        for jp_file in sorted(jp_dir.glob("*.md")):
            try:
                jp_text = jp_file.read_text(encoding='utf-8')
                lines = jp_text.split('\n')
                
                # Extract patterns with chapter context
                ea_patterns = self.detect_emotion_action_patterns(lines, volume_name)
                for p in ea_patterns:
                    p.source_chapter = jp_file.stem
                self.emotion_action_patterns.extend(ea_patterns)
                
                sc_patterns = self.detect_sarcasm_patterns(lines, volume_name)
                for p in sc_patterns:
                    p.source_chapter = jp_file.stem
                self.sarcasm_patterns.extend(sc_patterns)
                
            except Exception as e:
                logger.debug(f"Error processing {jp_file}: {e}")
        
        self.stats["work_volumes_processed"] += 1
    
    def build_all(self):
        """Build corpus from all 107 EPUBs and WORK volumes."""
        logger.info("=" * 60)
        logger.info("GAP CORPUS BUILDER - Starting extraction")
        logger.info("=" * 60)
        
        # Process INPUT EPUBs
        epub_files = list(INPUT_DIR.glob("*.epub"))
        logger.info(f"Found {len(epub_files)} EPUBs in INPUT/")
        
        for epub_path in epub_files:
            try:
                self.process_epub(epub_path)
            except Exception as e:
                logger.error(f"Error processing {epub_path.name}: {e}")
        
        # Process WORK volumes for higher quality aligned examples
        work_volumes = [d for d in WORK_DIR.iterdir() if d.is_dir() and not d.name.startswith('.')]
        logger.info(f"Found {len(work_volumes)} WORK volumes")
        
        for volume_dir in work_volumes:
            try:
                self.process_work_volume(volume_dir)
            except Exception as e:
                logger.debug(f"Error processing {volume_dir.name}: {e}")
        
        # Deduplicate and save
        self._deduplicate_patterns()
        self._save_corpora()
        
        # Print statistics
        self._print_stats()
    
    def _deduplicate_patterns(self):
        """Remove duplicate patterns."""
        # Dedupe emotion_action by jp_text
        seen = set()
        unique = []
        for p in self.emotion_action_patterns:
            if p.jp_text not in seen:
                seen.add(p.jp_text)
                unique.append(p)
        self.emotion_action_patterns = unique
        
        # Dedupe sarcasm by jp_text
        seen = set()
        unique = []
        for p in self.sarcasm_patterns:
            if p.jp_text not in seen:
                seen.add(p.jp_text)
                unique.append(p)
        self.sarcasm_patterns = unique
        
        # Dedupe ruby by kanji+ruby
        seen = set()
        unique = []
        for p in self.ruby_joke_patterns:
            key = (p.kanji, p.ruby)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        self.ruby_joke_patterns = unique
        
        # Update stats
        self.stats["emotion_action_count"] = len(self.emotion_action_patterns)
        self.stats["sarcasm_count"] = len(self.sarcasm_patterns)
        self.stats["ruby_joke_count"] = len(self.ruby_joke_patterns)
    
    def _save_corpora(self):
        """Save extracted patterns to JSON files."""
        
        # Ensure config dir exists
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save Gap A corpus
        emotion_action_data = {
            "version": "1.0",
            "description": "Gap A: Emotion + Action patterns for sentence surgery",
            "extracted_at": datetime.now().isoformat(),
            "total_patterns": len(self.emotion_action_patterns),
            "patterns": [asdict(p) for p in self.emotion_action_patterns[:500]],  # Limit to 500
        }
        with open(EMOTION_ACTION_CORPUS, 'w', encoding='utf-8') as f:
            json.dump(emotion_action_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(self.emotion_action_patterns)} emotion_action patterns")
        
        # Save Gap C corpus
        sarcasm_data = {
            "version": "1.0",
            "description": "Gap C: Sarcasm/Subtext patterns for detection (threshold 0.85)",
            "extracted_at": datetime.now().isoformat(),
            "confidence_threshold": 0.85,
            "total_patterns": len(self.sarcasm_patterns),
            "patterns": [asdict(p) for p in self.sarcasm_patterns if p.confidence >= 0.85][:300],
        }
        with open(SARCASM_PATTERNS_CORPUS, 'w', encoding='utf-8') as f:
            json.dump(sarcasm_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len([p for p in self.sarcasm_patterns if p.confidence >= 0.85])} sarcasm patterns (>=0.85 confidence)")
        
        # Save Gap B corpus
        ruby_data = {
            "version": "1.0",
            "description": "Gap B: Ruby visual joke patterns",
            "extracted_at": datetime.now().isoformat(),
            "total_patterns": len(self.ruby_joke_patterns),
            "patterns": [asdict(p) for p in self.ruby_joke_patterns[:50]],  # Limit to 50
        }
        with open(RUBY_CONTEXT_CORPUS, 'w', encoding='utf-8') as f:
            json.dump(ruby_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(self.ruby_joke_patterns)} ruby_joke patterns")
    
    def _print_stats(self):
        """Print extraction statistics."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("EXTRACTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"EPUBs processed:        {self.stats['epubs_processed']}")
        logger.info(f"WORK volumes processed: {self.stats['work_volumes_processed']}")
        logger.info("")
        logger.info("CORPUS SIZES:")
        logger.info(f"  Gap A (emotion_action): {self.stats['emotion_action_count']} patterns")
        logger.info(f"  Gap C (sarcasm):        {self.stats['sarcasm_count']} patterns")
        logger.info(f"  Gap B (ruby_jokes):     {self.stats['ruby_joke_count']} patterns")
        logger.info("")
        logger.info("OUTPUT FILES:")
        logger.info(f"  {EMOTION_ACTION_CORPUS}")
        logger.info(f"  {SARCASM_PATTERNS_CORPUS}")
        logger.info(f"  {RUBY_CONTEXT_CORPUS}")


def main():
    """Main entry point."""
    builder = GapCorpusBuilder()
    builder.build_all()


if __name__ == "__main__":
    main()
