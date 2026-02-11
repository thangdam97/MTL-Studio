"""
Gap Analysis Semantic Analyzer - Gemini 2.5 Pro Hardcoded
=========================================================

This module uses Gemini 2.5 Pro for semantic analysis of Gap A/B/C patterns
instead of automated regex-based extraction. The patterns are curated
manually for quality over quantity.

Gap A: Emotion + Action sentence surgery (temp=0.4, conservative)
Gap B: Ruby visual joke classification
Gap C: Sarcasm/Subtext detection (temp=1.0, creative)

Author: MTL Studio
Version: 2.0
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
from google.genai import types
from pipeline.common.genai_factory import create_genai_client, resolve_api_key

# Load curated patterns
PATTERNS_FILE = Path(__file__).parent.parent / "config" / "gap_patterns_curated.json"


class SpeakerArchetype(Enum):
    """Character archetype for subtext analysis"""
    TSUNDERE = "tsundere"
    KUUDERE = "kuudere"
    YANDERE = "yandere"
    DANDERE = "dandere"
    UNKNOWN = "unknown"


class RubyJokeType(Enum):
    """Classification of ruby visual jokes"""
    KIRA_KIRA = "kira_kira"  # DQN names with unusual readings
    ARCHAIC = "archaic"      # Standard literary kanji
    MISREADING = "misreading"  # Deliberate wrong furigana
    DOUBLE_MEANING = "double_meaning"  # Subtext layer
    CHARACTER_NAME = "character_name"  # Character names with readings (Ghost Ruby)
    STANDARD = "standard"    # No special treatment needed


@dataclass
class GapAAnalysis:
    """Result of Gap A emotion+action analysis"""
    jp_text: str
    emotion_word: str
    emotion_en: str
    action_word: str
    context_type: str  # dialogue/narrative
    sentence_count: int
    surgery_recommended: bool
    surgery_suggestion: Optional[str] = None
    confidence: float = 0.0


@dataclass
class GapBAnalysis:
    """Result of Gap B ruby joke analysis"""
    kanji: str
    ruby: str
    joke_type: RubyJokeType
    context: str
    en_treatment: str
    needs_tl_note: bool


@dataclass
class GapCAnalysis:
    """Result of Gap C sarcasm/subtext analysis"""
    jp_text: str
    markers_found: List[str]
    archetype: SpeakerArchetype
    surface_meaning: str
    actual_meaning: str
    translation_approach: str
    confidence: float


class GapSemanticAnalyzer:
    """
    Semantic analyzer for Gap A/B/C using Gemini 2.5 Pro.
    
    Unlike the automated corpus extraction, this uses curated patterns
    and LLM analysis for higher quality results.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Gemini API key."""
        self.patterns = self._load_patterns()
        
        # Configure API client
        api_key = resolve_api_key(api_key=api_key, required=False)
        if not api_key:
            raise ValueError("GOOGLE_API_KEY (or GEMINI_API_KEY) not found in environment")
        
        self.client = create_genai_client(api_key=api_key)
        self.model_name = 'gemini-2.5-pro'
        
        # Generation configs for different gaps
        self.config_conservative = types.GenerateContentConfig(
            temperature=0.4,  # Gap A: conservative
            max_output_tokens=2048
        )
        
        self.config_creative = types.GenerateContentConfig(
            temperature=1.0,  # Gap C: creative
            max_output_tokens=2048
        )
    
    def _load_patterns(self) -> Dict[str, Any]:
        """Load curated patterns from JSON."""
        if PATTERNS_FILE.exists():
            with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    # =========================================================================
    # Gap A: Emotion + Action Sentence Surgery
    # =========================================================================
    
    def detect_emotion_action(self, jp_text: str) -> Optional[GapAAnalysis]:
        """
        Detect emotion+action patterns in Japanese text.
        Only processes passages ≤3 sentences per the safety threshold.
        """
        # Count sentences (rough estimate)
        sentence_count = len(re.findall(r'[。！？」]', jp_text))
        
        if sentence_count > 3:
            return None  # Safety threshold
        
        # Check for emotion markers
        emotion_markers = self.patterns.get('gap_a_emotion_action', {}).get(
            'detection_markers', {}
        ).get('emotion_words', {})
        
        found_emotion = None
        for emotion, data in emotion_markers.items():
            if emotion in jp_text:
                found_emotion = (emotion, data.get('en', emotion))
                break
        
        if not found_emotion:
            return None
        
        # Check for action markers
        action_pairs = self.patterns.get('gap_a_emotion_action', {}).get(
            'detection_markers', {}
        ).get('action_pairs', {})
        
        found_action = None
        for action in action_pairs.keys():
            if action in jp_text:
                found_action = action
                break
        
        if not found_action:
            return None
        
        # Determine context type
        context_type = "dialogue" if jp_text.startswith('「') else "narrative"
        
        return GapAAnalysis(
            jp_text=jp_text,
            emotion_word=found_emotion[0],
            emotion_en=found_emotion[1],
            action_word=found_action,
            context_type=context_type,
            sentence_count=sentence_count,
            surgery_recommended=True,
            confidence=0.8
        )
    
    def analyze_gap_a_with_llm(self, jp_text: str, en_draft: str) -> GapAAnalysis:
        """
        Use Gemini 2.5 Pro to analyze if sentence surgery would improve translation.
        Temperature 0.4 for conservative suggestions.
        """
        prompt = f"""Analyze this Japanese-English translation pair for Gap A (emotion+action restructuring).

Japanese: {jp_text}
English Draft: {en_draft}

The Japanese has an emotion+action pairing. Evaluate:
1. Does the English preserve the emotional beat?
2. Would restructuring improve flow while keeping nuance?
3. Are any hedging/trailing markers lost in translation?

If restructuring would help, suggest a revised English translation.
Be CONSERVATIVE - only suggest changes if clearly beneficial.

Respond in JSON:
{{
  "emotion_preserved": true/false,
  "restructure_recommended": true/false,
  "lost_nuances": ["list of any lost markers"],
  "suggested_revision": "revised EN if restructuring helps, else null",
  "confidence": 0.0-1.0
}}
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.config_conservative
        )
        
        try:
            result = json.loads(response.text)
            
            analysis = self.detect_emotion_action(jp_text) or GapAAnalysis(
                jp_text=jp_text,
                emotion_word="",
                emotion_en="",
                action_word="",
                context_type="unknown",
                sentence_count=0,
                surgery_recommended=False
            )
            
            analysis.surgery_recommended = result.get('restructure_recommended', False)
            analysis.surgery_suggestion = result.get('suggested_revision')
            analysis.confidence = result.get('confidence', 0.0)
            
            return analysis
            
        except json.JSONDecodeError:
            return self.detect_emotion_action(jp_text)
    
    # =========================================================================
    # Gap B: Ruby Visual Joke Classification
    # =========================================================================
    
    def classify_ruby(self, kanji: str, ruby: str, context: str = "") -> GapBAnalysis:
        """
        Classify a ruby annotation for appropriate EN treatment.
        
        Categories:
        - KIRA_KIRA: DQN names with unusual readings (e.g., 光宙=ぴかちゅう, 愛梨=ラブリ)
        - CHARACTER_NAME: Character names with standard readings (Ghost Ruby)
        - ARCHAIC: Literary kanji with standard readings
        - MISREADING: Deliberate wrong furigana for irony
        - STANDARD: Normal ruby for reading assistance
        """
        # Check kira-kira patterns first (unusual/creative name readings)
        # Kira-kira names often have katakana readings or phonetic wordplay
        if self._is_kira_kira_name(kanji, ruby):
            return GapBAnalysis(
                kanji=kanji,
                ruby=ruby,
                joke_type=RubyJokeType.KIRA_KIRA,
                context=context,
                en_treatment=f"Kira-kira name: {kanji} read as '{ruby}' - TL note recommended",
                needs_tl_note=True
            )
        
        # Check curated kira-kira examples
        kira_kira_examples = self.patterns.get('gap_b_ruby_jokes', {}).get(
            'categories', {}
        ).get('kira_kira_names', {}).get('examples', [])
        
        for example in kira_kira_examples:
            if example.get('kanji') == kanji or example.get('ruby') == ruby:
                return GapBAnalysis(
                    kanji=kanji,
                    ruby=ruby,
                    joke_type=RubyJokeType.KIRA_KIRA,
                    context=context,
                    en_treatment=example.get('en_approach', 'Add TL note'),
                    needs_tl_note=True
                )
        
        # Check if this is a character name (Ghost Ruby)
        # Character names typically: 2+ kanji, hiragana reading, appears to be a name
        if self._is_character_name(kanji, ruby):
            return GapBAnalysis(
                kanji=kanji,
                ruby=ruby,
                joke_type=RubyJokeType.CHARACTER_NAME,
                context=context,
                en_treatment=f"Character name: {kanji} ({ruby})",
                needs_tl_note=False  # Names usually don't need TL notes
            )
        
        # Check archaic readings
        archaic_examples = self.patterns.get('gap_b_ruby_jokes', {}).get(
            'categories', {}
        ).get('archaic_readings', {}).get('examples_from_corpus', [])
        
        for example in archaic_examples:
            if example.get('kanji') == kanji:
                return GapBAnalysis(
                    kanji=kanji,
                    ruby=ruby,
                    joke_type=RubyJokeType.ARCHAIC,
                    context=context,
                    en_treatment=example.get('en', kanji),
                    needs_tl_note=False
                )
        
        # Default: standard treatment
        return GapBAnalysis(
            kanji=kanji,
            ruby=ruby,
            joke_type=RubyJokeType.STANDARD,
            context=context,
            en_treatment="Standard translation",
            needs_tl_note=False
        )
    
    def _is_kira_kira_name(self, kanji: str, ruby: str) -> bool:
        """
        Detect if a ruby annotation is a kira-kira (DQN) name.
        
        Kira-kira names are characterized by:
        - Katakana readings (often English loanwords like ラブリ, エンジェル)
        - Unusual kanji-reading combinations
        - Name-like kanji with non-standard pronunciations
        """
        import re
        
        # Must be 1-4 kanji (name length)
        if len(kanji) < 1 or len(kanji) > 4:
            return False
        
        # Must be all kanji
        if not re.match(r'^[一-龯々]+$', kanji):
            return False
        
        # Key indicator: Katakana reading (very common in kira-kira names)
        is_katakana = bool(re.match(r'^[ァ-ヴー]+$', ruby))
        
        if is_katakana:
            # Check if kanji contains typical kira-kira name components
            # Expanded list of kanji commonly used in kira-kira names
            kira_kanji = set(
                # Love/Emotion: 愛, 心, 恋, 幸, 優, 絆, 祈, 願
                '愛心恋幸優絆祈願'
                # Beauty/Appearance: 美, 麗, 華, 花, 姫, 妃, 嬢, 雅, 艶
                '美麗華花姫妃嬢雅艶'
                # Celestial/Nature: 光, 星, 月, 空, 海, 陽, 宙, 輝, 煌, 天, 雲, 虹, 霧
                '光星月空海陽宙輝煌天雲虹霧'
                # Precious/Valuable: 宝, 珠, 玉, 金, 銀, 琥, 珀, 瑠, 璃, 翡, 翠, 碧, 琉
                '宝珠玉金銀琥珀瑠璃翡翠碧琉'
                # Music/Sound: 音, 奏, 響, 詩, 唄, 歌, 譜, 律, 調
                '音奏響詩唄歌譜律調'
                # Dream/Hope: 夢, 希, 望, 想, 念, 憧, 志
                '夢希望想念憧志'
                # Royalty/Noble: 王, 子, 姫, 妃, 皇, 帝, 君, 覇
                '王子姫妃皇帝君覇'
                # Nature elements: 風, 雨, 雪, 氷, 霜, 露, 桜, 梅, 蓮, 莉, 菜, 葉
                '風雨雪氷霜露桜梅蓮莉菜葉'
                # Angels/Divine: 使, 神, 聖, 守, 護, 禊, 巫
                '使神聖守護禊巫'
            )
            
            if any(k in kira_kanji for k in kanji):
                # Check for extensive list of kira-kira reading patterns
                kira_patterns = [
                    # Love/Emotion words
                    'ラブ', 'ハート', 'キュート', 'プリティ', 'スイート', 'ダーリン',
                    'ハニー', 'キス', 'ピース', 'スマイル', 'ジョイ', 'ハッピー',
                    # Royalty/Noble
                    'プリンセス', 'キング', 'クイーン', 'プリンス', 'ロイヤル', 'ノーブル',
                    'エンペラー', 'マジェスティ', 'ハイネス', 'グレース',
                    # Celestial/Space
                    'スター', 'ムーン', 'サン', 'スカイ', 'ヘブン', 'ギャラクシー',
                    'コスモ', 'プラネット', 'オービット', 'メテオ', 'コメット',
                    # Nature
                    'オーシャン', 'シー', 'マリン', 'レイク', 'リバー', 'スノー',
                    'フラワー', 'ブロッサム', 'ペタル', 'リーフ', 'ツリー',
                    # Light/Shine
                    'ライト', 'シャイン', 'グロー', 'ブライト', 'ラディアント',
                    'スパークル', 'グリッター', 'トゥインクル', 'ルミナス',
                    # Precious stones
                    'ダイヤ', 'ダイヤモンド', 'ルビー', 'サファイア', 'エメラルド',
                    'パール', 'ジュエル', 'ジェム', 'クリスタル', 'アメジスト',
                    # Flowers
                    'ローズ', 'リリー', 'アイリス', 'ヴァイオレット', 'ジャスミン',
                    'サクラ', 'ロータス', 'チューリップ', 'デイジー',
                    # Angels/Divine
                    'エンジェル', 'セラフ', 'ヘブンリー', 'ディバイン', 'ブレス',
                    'ミラクル', 'マジカル', 'ミスティック',
                    # Dreams/Spirit
                    'ドリーム', 'ホープ', 'ウィッシュ', 'ファンタジー', 'ビジョン',
                    'ソウル', 'スピリット', 'ハーモニー', 'メロディ', 'リズム',
                    # Virtue/Quality
                    'ピュア', 'イノセント', 'エレガント', 'グラマラス', 'チャーミング',
                    'ラブリー', 'ビューティ', 'グローリー', 'ヴィクトリー',
                    # Unique/Creative
                    'ユニーク', 'レア', 'エクストラ', 'スペシャル', 'ワンダー',
                    'マーベラス', 'ファビュラス', 'ゴージャス',
                    # Pokemon/Anime influence
                    'ピカチュウ', 'サトシ', 'ヒカリ', 'ハルカ', 'アイリス',
                    # Technology/Modern
                    'デジタル', 'サイバー', 'ネオン', 'レーザー', 'ホログラム',
                ]
                
                if any(p in ruby for p in kira_patterns):
                    return True
            
            # If kanji is 2+ chars and reading is katakana 3+ chars, likely kira-kira
            # Example: 愛梨{ラブリ}, 光宙{ピカチュウ}
            if len(kanji) >= 2 and len(ruby) >= 3:
                return True
            
            # Single kanji with long katakana reading (4+ chars) is often kira-kira
            # Example: 愛{ラブ} would be 2 chars, but 光{ライト} is common
            if len(kanji) == 1 and len(ruby) >= 4:
                # Check if it contains kira kanji
                if kanji in kira_kanji:
                    return True
        
        return False
    
    def _is_character_name(self, kanji: str, ruby: str) -> bool:
        """
        Detect if a ruby annotation is likely a character name (Ghost Ruby).
        
        Character names typically:
        - 2-4 kanji characters for full names (surname + given name)
        - 2 kanji for given names only
        - Contains name-specific kanji patterns
        - NOT common vocabulary words
        """
        import re
        
        # Blacklist: Common words that look like names but aren't
        common_words = {
            '日和見', '貴方', '呑気', '他人事', '流石', '横槍', '華奢', 
            '最中', '出鱈目', '矢張', '所詮', '仕方', '彼方', '何処', 
            '何方', '本当', '素直', '可愛', '綺麗', '駄目', '無理',
            '大丈夫', '一緒', '普通', '最初', '最後', '今日', '明日',
            '昨日', '今朝', '今夜', '当然', '当時', '相手', '自分',
            '彼女', '彼氏', '一人', '二人', '三人', '上手', '下手',
            '本人', '本気', '元気', '勇気', '人気', '天気', '空気',
            '様子', '調子', '拍子', '返事', '食事', '家事', '仕事',
            '世話', '邪魔', '馬鹿', '阿呆', '素人', '玄人', '大人',
            '子供', '親子', '夫婦', '兄弟', '姉妹', '友人', '恋人',
            '知人', '他人', '主人', '女主人', '御馳走', '挨拶', '喧嘩',
            '我慢', '面倒', '厄介', '台無', '無駄', '余計', '相当',
            '随分', '案外', '意外', '以外', '結局', '結果', '原因',
            '理由', '目的', '方法', '手段', '道具', '材料', '準備',
            # Additional emotion/feeling words
            '安堵', '愛嬌', '感謝', '歓喜', '憤怒', '悲嘆', '恐怖',
            '驚愕', '困惑', '焦燥', '嫉妬', '羨望', '後悔', '反省',
            '期待', '失望', '絶望', '希望', '満足', '不満', '興奮',
            # Common noun compounds
            '瞬間', '時間', '空間', '期間', '年間', '月間', '週間',
            '生涯', '人生', '一生', '半生', '前世', '来世', '現世',
            '世界', '社会', '世間', '人間', '自然', '環境', '状況',
            '状態', '様態', '形態', '姿態', '事態', '実態', '全体',
        }
        
        if kanji in common_words:
            return False
        
        # Must be 2-4 kanji
        if len(kanji) < 2 or len(kanji) > 4:
            return False
        
        # Must be all kanji (no hiragana/katakana mixed)
        if not re.match(r'^[一-龯々]+$', kanji):
            return False
        
        # Reading should be 3-10 hiragana (typical name length)
        if not re.match(r'^[ぁ-ん]{3,10}$', ruby):
            return False
        
        # Strong name indicators: Common surname kanji
        surname_kanji = set('田中山川野村上下木林森本井口石原北東西南高橋渡辺佐藤伊鈴加小大岡松竹梅柳杉桜藤吉池沢谷島崎宮城堀黒白赤青金銀鉄長短前後左右内外新古早遅近遠広狭深浅厚薄軽重強弱明暗清濁正副主客老若男女父母夫妻兄弟姉妹孫曾玄甥姪')
        
        # Strong name indicators: Common given name kanji
        given_name_kanji = set('一二三四五六七八九十百千万郎太朗介助輔亮真樹斗翔悠陽海空星凛玲音花美愛彩莉咲優奈紗結華那香澄智勇仁義礼信和平安康健勝利成功栄光明希夢幸福寿')
        
        # Count how many kanji match name patterns
        surname_match = sum(1 for k in kanji if k in surname_kanji)
        given_match = sum(1 for k in kanji if k in given_name_kanji)
        
        # Full name (3-4 kanji): needs at least 1 surname + 1 given name kanji
        if len(kanji) >= 3:
            if surname_match >= 1 and given_match >= 1:
                return True
            # Or if 2+ kanji match either set
            if surname_match + given_match >= 2:
                return True
        
        # Given name only (2 kanji): needs at least 1 given name kanji
        if len(kanji) == 2:
            if given_match >= 1:
                return True
            # Check for common given name endings
            common_endings = ['斗', '介', '輔', '郎', '太', '翔', '悠', '陽', '真', '樹', 
                              '奈', '美', '愛', '香', '音', '花', '子', '菜', '衣', '乃',
                              '一', '二', '三', '平', '夫', '雄', '男', '助', '彦']
            if any(kanji.endswith(e) for e in common_endings):
                return True
        
        return False
    
    def analyze_ruby_with_llm(self, kanji: str, ruby: str, context: str) -> GapBAnalysis:
        """
        Use Gemini 2.5 Pro to classify ambiguous ruby patterns.
        """
        prompt = f"""Classify this Japanese ruby (furigana) annotation:

Kanji: {kanji}
Ruby: {ruby}
Context: {context}

Categories:
1. KIRA_KIRA: Unusual/creative name readings (like 光宙=ぴかちゅう)
2. ARCHAIC: Literary kanji with standard readings
3. MISREADING: Deliberate wrong furigana for irony
4. DOUBLE_MEANING: Ruby adds subtext layer
5. STANDARD: Normal reading, no special treatment

Respond in JSON:
{{
  "category": "one of above",
  "en_treatment": "how to handle in English translation",
  "needs_tl_note": true/false,
  "explanation": "why this classification"
}}
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.config_conservative
        )
        
        try:
            result = json.loads(response.text)
            
            category_map = {
                'KIRA_KIRA': RubyJokeType.KIRA_KIRA,
                'ARCHAIC': RubyJokeType.ARCHAIC,
                'MISREADING': RubyJokeType.MISREADING,
                'DOUBLE_MEANING': RubyJokeType.DOUBLE_MEANING,
                'STANDARD': RubyJokeType.STANDARD
            }
            
            return GapBAnalysis(
                kanji=kanji,
                ruby=ruby,
                joke_type=category_map.get(result.get('category', 'STANDARD'), RubyJokeType.STANDARD),
                context=context,
                en_treatment=result.get('en_treatment', 'Standard translation'),
                needs_tl_note=result.get('needs_tl_note', False)
            )
            
        except json.JSONDecodeError:
            return self.classify_ruby(kanji, ruby, context)
    
    # =========================================================================
    # Gap C: Sarcasm and Subtext Detection
    # =========================================================================
    
    def detect_sarcasm_markers(self, jp_text: str) -> List[str]:
        """
        Detect sarcasm/subtext markers in Japanese text.
        """
        found_markers = []
        
        detection_patterns = self.patterns.get('gap_c_sarcasm_subtext', {}).get(
            'detection_patterns', {}
        )
        
        # Check stuttering
        for pattern in detection_patterns.get('stuttering', []):
            if re.search(pattern, jp_text):
                found_markers.append(f"stuttering:{pattern}")
        
        # Check hedging
        for pattern in detection_patterns.get('hedging', []):
            if re.search(pattern, jp_text):
                found_markers.append(f"hedging:{pattern}")
        
        # Check contradiction markers
        for pattern in detection_patterns.get('contradiction_markers', []):
            if re.search(pattern, jp_text):
                found_markers.append(f"contradiction:{pattern}")
        
        # Check tsundere patterns
        for pattern in detection_patterns.get('tsundere_patterns', []):
            if re.search(pattern, jp_text):
                found_markers.append(f"tsundere:{pattern}")
        
        return found_markers
    
    def identify_archetype(self, markers: List[str]) -> SpeakerArchetype:
        """
        Identify speaker archetype from detected markers.
        """
        # Count marker types
        tsundere_count = sum(1 for m in markers if 'tsundere' in m or 'stuttering' in m)
        hedging_count = sum(1 for m in markers if 'hedging' in m)
        
        if tsundere_count >= 2:
            return SpeakerArchetype.TSUNDERE
        elif hedging_count >= 2 and tsundere_count == 0:
            return SpeakerArchetype.KUUDERE
        
        return SpeakerArchetype.UNKNOWN
    
    def analyze_gap_c(self, jp_text: str, context_before: str = "", context_after: str = "") -> Optional[GapCAnalysis]:
        """
        Detect and analyze sarcasm/subtext patterns.
        Returns None if confidence < 0.85 threshold.
        """
        markers = self.detect_sarcasm_markers(jp_text)
        
        if not markers:
            return None
        
        archetype = self.identify_archetype(markers)
        
        # Calculate confidence based on marker count and type
        base_confidence = min(0.5 + (len(markers) * 0.1), 0.95)
        
        if archetype != SpeakerArchetype.UNKNOWN:
            base_confidence += 0.1
        
        if base_confidence < 0.85:
            return None  # Below threshold
        
        return GapCAnalysis(
            jp_text=jp_text,
            markers_found=markers,
            archetype=archetype,
            surface_meaning="",  # To be filled by LLM
            actual_meaning="",   # To be filled by LLM
            translation_approach="",  # To be filled by LLM
            confidence=base_confidence
        )
    
    def analyze_gap_c_with_llm(
        self, 
        jp_text: str, 
        en_draft: str,
        context_before: str = "",
        context_after: str = ""
    ) -> GapCAnalysis:
        """
        Use Gemini 2.5 Pro to analyze subtext and suggest translation approach.
        Temperature 1.0 for creative interpretation.
        """
        markers = self.detect_sarcasm_markers(jp_text)
        archetype = self.identify_archetype(markers)
        
        # Get archetype info from patterns
        archetype_info = self.patterns.get('gap_c_sarcasm_subtext', {}).get(
            'archetypes', {}
        ).get(archetype.value.upper(), {})
        
        prompt = f"""Analyze this Japanese dialogue for subtext and sarcasm.

Japanese: {jp_text}
Current English: {en_draft}
Context Before: {context_before}
Context After: {context_after}

Detected markers: {markers}
Likely archetype: {archetype.value}
Archetype traits: {archetype_info.get('description', 'Unknown')}

Analyze:
1. What is the character SAYING on the surface?
2. What are they ACTUALLY feeling/meaning?
3. How should the English preserve this gap between surface and subtext?

Be CREATIVE with the translation approach - this is where MTL often fails.

Respond in JSON:
{{
  "surface_meaning": "what they literally said",
  "actual_meaning": "what they actually mean/feel",
  "translation_approach": "how to translate preserving the subtext",
  "suggested_en": "your suggested translation",
  "confidence": 0.0-1.0
}}
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self.config_creative
        )
        
        try:
            result = json.loads(response.text)
            
            return GapCAnalysis(
                jp_text=jp_text,
                markers_found=markers,
                archetype=archetype,
                surface_meaning=result.get('surface_meaning', ''),
                actual_meaning=result.get('actual_meaning', ''),
                translation_approach=result.get('translation_approach', ''),
                confidence=result.get('confidence', 0.85)
            )
            
        except json.JSONDecodeError:
            basic = self.analyze_gap_c(jp_text, context_before, context_after)
            return basic or GapCAnalysis(
                jp_text=jp_text,
                markers_found=markers,
                archetype=archetype,
                surface_meaning="",
                actual_meaning="",
                translation_approach="",
                confidence=0.5
            )
    
    # =========================================================================
    # Batch Processing
    # =========================================================================
    
    def process_chapter(
        self, 
        jp_lines: List[str], 
        en_lines: List[str]
    ) -> Dict[str, List[Any]]:
        """
        Process a chapter for all three gaps.
        
        Returns dict with:
        - gap_a: List of emotion+action analyses
        - gap_b: List of ruby classifications (requires separate ruby extraction)
        - gap_c: List of sarcasm/subtext analyses
        """
        results = {
            'gap_a': [],
            'gap_c': []
        }
        
        for i, (jp, en) in enumerate(zip(jp_lines, en_lines)):
            # Gap A: Check for emotion+action
            gap_a = self.detect_emotion_action(jp)
            if gap_a:
                # Run LLM analysis for detected patterns
                full_analysis = self.analyze_gap_a_with_llm(jp, en)
                full_analysis.jp_text = jp  # Preserve original
                results['gap_a'].append({
                    'line': i,
                    'analysis': full_analysis
                })
            
            # Gap C: Check for sarcasm/subtext
            context_before = jp_lines[i-1] if i > 0 else ""
            context_after = jp_lines[i+1] if i < len(jp_lines)-1 else ""
            
            gap_c = self.analyze_gap_c(jp, context_before, context_after)
            if gap_c and gap_c.confidence >= 0.85:
                # Run LLM analysis for high-confidence patterns
                full_analysis = self.analyze_gap_c_with_llm(
                    jp, en, context_before, context_after
                )
                results['gap_c'].append({
                    'line': i,
                    'analysis': full_analysis
                })
        
        return results


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Test the semantic analyzer."""
    import asyncio
    
    analyzer = GapSemanticAnalyzer()
    
    # Test Gap A detection
    test_lines = [
        "「……真樹、大丈夫？　私がいなくて、寂しくなって泣いちゃいたりしない？」",
        "親友と離れ離れになり、初めのうちは落ち込んでいた天海さんだったものの、持ち前の切り替えの早さで、いつもの溌溂とした笑顔を取り戻している。",
        "「い、いや別にしてない、けど……」"
    ]
    
    print("=== Gap A Detection ===")
    for line in test_lines:
        result = analyzer.detect_emotion_action(line)
        if result:
            print(f"✓ Found: {result.emotion_word} + {result.action_word}")
            print(f"  Type: {result.context_type}")
            print(f"  Text: {line[:50]}...")
            print()
    
    print("=== Gap C Detection ===")
    for line in test_lines:
        markers = analyzer.detect_sarcasm_markers(line)
        if markers:
            archetype = analyzer.identify_archetype(markers)
            print(f"✓ Markers: {markers}")
            print(f"  Archetype: {archetype.value}")
            print(f"  Text: {line[:50]}...")
            print()
    
    print("=== Ruby Classification ===")
    test_rubies = [
        ("頷", "うなず", "元気よく頷いた"),
        ("光宙", "ぴかちゅう", "彼の名前は光宙という"),
        ("訝", "いぶか", "訝しげな表情で")
    ]
    
    for kanji, ruby, context in test_rubies:
        result = analyzer.classify_ruby(kanji, ruby, context)
        print(f"✓ {kanji}（{ruby}）-> {result.joke_type.value}")
        print(f"  Treatment: {result.en_treatment}")
        print()


if __name__ == "__main__":
    main()
