"""
Vietnamese CJK Leak Cleaner - Post-Processing Hard Substitution

This module performs HARD substitution of CJK characters that leaked through 
LLM translation despite advisory guidance. It runs AFTER translation to clean
the Vietnamese output.

Unlike the prompt-based CJK prevention (which is advisory), this module:
1. Detects CJK leaks in Vietnamese translated text
2. Performs regex-based HARD substitution with Vietnamese equivalents
3. Logs all substitutions for audit

Version: 1.0
Author: MTL Studio
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class CJKSubstitution:
    """Record of a CJK substitution."""
    original: str
    replacement: str
    line_number: int
    context: str
    pattern_type: str  # 'kanji', 'katakana', 'hiragana', 'mixed'


class VietnameseCJKCleaner:
    """
    Hard substitution cleaner for CJK leaks in Vietnamese translations.
    
    This runs AFTER Gemini translation to catch any CJK characters that 
    leaked through despite advisory guidance.
    """
    
    # ==========================================
    # HARD SUBSTITUTION PATTERNS (MANDATORY)
    # ==========================================
    # These patterns are applied unconditionally via regex
    # Format: (pattern, replacement, description)
    
    KANJI_SUBSTITUTIONS = {
        # Common nouns that frequently leak
        '少女': 'thiếu nữ',
        '美少女': 'mỹ thiếu nữ',
        '少年': 'thiếu niên',
        '世界': 'thế giới',
        '元気': 'khỏe mạnh',
        '可愛': 'dễ thương',
        '先生': 'thầy giáo',
        '先輩': 'tiền bối',
        '後輩': 'hậu bối',
        '彼女': 'cô ấy',
        '彼': 'anh ấy',
        '俺': 'tôi',
        '私': 'tôi',
        '僕': 'tôi',
        '君': 'cậu',
        '貴方': 'anh',
        '意識': 'ý thức',
        '精神': 'tinh thần',
        
        # Numbers (when used in metaphors/descriptions)
        '一': 'một',
        '二': 'hai',
        '三': 'ba',
        '四': 'bốn',
        '五': 'năm',
        
        # Merchandise/bonus terms
        '特典': 'đặc quyền',  # bonus/privilege
        '限定': 'giới hạn',  # limited edition
        '予約': 'đặt trước',  # reservation
        '勇者': 'dũng giả',
        '魔法': 'pháp thuật',
        '学校': 'trường học',
        '教室': 'lớp học',
        '友達': 'bạn bè',
        '恋人': 'người yêu',
        '結婚': 'kết hôn',
        '家族': 'gia đình',
        '両親': 'bố mẹ',
        '兄弟': 'anh em',
        '姉妹': 'chị em',
        '心': 'trái tim',
        '愛': 'tình yêu',
        '涙': 'nước mắt',
        '笑': 'cười',
        '泣': 'khóc',
        '怒': 'giận',
        '悲': 'buồn',
        '楽': 'vui',
        '痛': 'đau',
        
        # Idol/entertainment industry terms
        '公演': 'buổi biểu diễn',  # performance/show
        '握手会': 'buổi bắt tay',  # handshake event
        '握手': 'bắt tay',  # handshake
        '紺': 'xanh đậm',  # navy blue (color)
        '会場': 'hội trường',  # venue
        '舞台': 'sân khấu',  # stage
        '楽屋': 'phòng hậu trường',  # backstage room
        '衣装': 'trang phục',  # costume
        '歌': 'bài hát',  # song
        '踊り': 'điệu nhảy',  # dance
        '練習': 'luyện tập',  # practice
        '撮影': 'buổi chụp',  # photoshoot
        '収録': 'buổi thu',  # recording
        '生放送': 'phát trực tiếp',  # live broadcast
        
        # Single kanji adverbs/particles
        '更': 'càng',  # more/further
        
        # Chinese characters that leak (not Japanese)
        '这边': 'bên này',
        '这个': 'cái này',
        '这': 'này',
        '之所以': 'sở dĩ',  # the reason why (Chinese grammar particle)
        '趁': 'khi còn',  # while/take advantage of (Chinese)
        
        # Japanese grammar patterns that leak
        '本格的な': 'chính quy',  # authentic/genuine
        '本格': 'chính quy',  # authentic
        '的な': '',  # な-adjective suffix (often leaves orphaned)
        
        '嬉': 'vui mừng',
        '恥': 'xấu hổ',
        '驚': 'kinh ngạc',
        
        # Kanji compound verbs that commonly leak
        '思い出': 'kỷ niệm',  # memory/recollection
        '気持ち': 'cảm xúc',  # feeling
        '出来': 'có thể',  # can do
        '分かる': 'hiểu',  # understand
        '見える': 'nhìn thấy',  # can see
        '聞こえる': 'nghe thấy',  # can hear
        '食べる': 'ăn',  # eat
        '飲む': 'uống',  # drink
        '言う': 'nói',  # say
        '思う': 'nghĩ',  # think
        '知る': 'biết',  # know
        '見る': 'nhìn',  # look
        '聞く': 'nghe',  # listen
        '行く': 'đi',  # go
        '来る': 'đến',  # come
        '帰る': 'về',  # return
        '入る': 'vào',  # enter
        '出る': 'ra',  # exit
        '待つ': 'đợi',  # wait
        '始める': 'bắt đầu',  # begin
        '終わる': 'kết thúc',  # end
        '続ける': 'tiếp tục',  # continue
        
        # Japanese food terms (often kept in original or transliterated)
        '親子丼': 'oyakodon',  # chicken-and-egg rice bowl
        '牛丼': 'gyudon',  # beef bowl
        '天丼': 'tendon',  # tempura bowl
        '丼': 'don',  # bowl (suffix)
        'ラーメン': 'ramen',
        '寿司': 'sushi',
        '刺身': 'sashimi',
        '焼肉': 'yakiniku',
        '弁当': 'bentou',
        
        # Mixed patterns (Vietnamese + CJK leak)
        'mỹ少女': 'mỹ thiếu nữ',
        'cô少女': 'cô gái',
        'người少女': 'cô gái',
    }
    
    # Hangul (Korean) leaks - rare but happen with multilingual models
    HANGUL_SUBSTITUTIONS = {
        '희미': 'mờ nhạt',  # faint/dim
        '사랑': 'tình yêu',  # love
        '감사': 'cảm ơn',  # thanks
        '네': 'vâng',  # yes
        '아니': 'không',  # no
    }
    
    KATAKANA_SUBSTITUTIONS = {
        # Common katakana words that leak
        'スタミナ': 'sức bền',
        'エネルギー': 'năng lượng',
        'パワー': 'sức mạnh',
        'レベル': 'cấp độ',
        'ステータス': 'trạng thái',
        'スキル': 'kỹ năng',
        'クラス': 'lớp',
        'ギルド': 'hội',
        'パーティー': 'nhóm',
        'メンバー': 'thành viên',
        'リーダー': 'đội trưởng',
        'ボス': 'trùm',
        'モンスター': 'quái vật',
        'ダンジョン': 'hầm ngục',
        'クエスト': 'nhiệm vụ',
        'アイテム': 'vật phẩm',
        'ポイント': 'điểm',
        'ランク': 'hạng',
        'イベント': 'sự kiện',
        'チャンス': 'cơ hội',
        'システム': 'hệ thống',
        'データ': 'dữ liệu',
        'プログラム': 'chương trình',
        'コンピューター': 'máy tính',
        'インターネット': 'mạng',
        'メール': 'thư',
        'メッセージ': 'tin nhắn',
        'アプリ': 'ứng dụng',
        'ゲーム': 'trò chơi',
        'アニメ': 'hoạt hình',
        'マンガ': 'truyện tranh',
        'キャラクター': 'nhân vật',
        'シーン': 'cảnh',
        'ストーリー': 'câu chuyện',
        'エンディング': 'kết thúc',
        'オープニング': 'mở đầu',
        'テーマ': 'chủ đề',
        'カフェ': 'quán cà phê',
        'レストラン': 'nhà hàng',
        'ホテル': 'khách sạn',
        'ショップ': 'cửa hàng',
        'コンビニ': 'cửa hàng tiện lợi',
        'スーパー': 'siêu thị',
        'デパート': 'trung tâm thương mại',
        'ファッション': 'thời trang',
        'スタイル': 'phong cách',
        'デザイン': 'thiết kế',
        'カラー': 'màu sắc',
        'サイズ': 'kích cỡ',
        'ブランド': 'thương hiệu',
        
        # School/idol related (for romcom volumes)
        'アイドル': 'thần tượng',
        'ファン': 'người hâm mộ',
        'ライブ': 'buổi biểu diễn',
        'コンサート': 'buổi hòa nhạc',
        'デビュー': 'ra mắt',
        'センター': 'trung tâm',
        'グループ': 'nhóm',
        'ユニット': 'đơn vị',
        'プロデューサー': 'nhà sản xuất',
        'マネージャー': 'quản lý',
        
        # Japanese punctuation that leaks
        '・': '·',  # middle dot (nakaguro) → standard middle dot
    }
    
    # Hiragana adverbs/expressions that leak
    HIRAGANA_SUBSTITUTIONS = {
        # Small kana (used for emphasis/stretching) - remove when isolated
        'っ': '',  # small tsu (glottal stop/emphasis)
        'ッ': '',  # katakana small tsu
        
        # Adverbs
        'わざわざ': 'cố tình',  # deliberately, on purpose
        'ますます': 'càng lúc càng',  # more and more
        'どんどん': 'liên tục',  # rapidly
        'ちゃんと': 'đàng hoàng',  # properly
        'しっかり': 'chắc chắn',  # firmly
        'ぜんぜん': 'hoàn toàn',  # completely (with negative)
        'やっぱり': 'quả nhiên',  # as expected
        'たぶん': 'có lẽ',  # probably
        'まさか': 'chẳng lẽ',  # could it be / don't tell me
        'なんとなく': 'không hiểu sao',  # somehow
        'とりあえず': 'tạm thời',  # for now
        'いつも': 'luôn luôn',  # always
        'たまに': 'thỉnh thoảng',  # sometimes
        
        # Compound verb endings (て-form + auxiliary)
        'てしまう': ' mất',  # regrettable completion
        'てしまった': ' mất rồi',
        'ちゃった': ' mất rồi',  # casual てしまった
        'ちゃう': ' mất',  # casual てしまう
        'ていく': ' dần',  # continuing action (going)
        'てくる': ' dần',  # continuing action (coming)
        'てみる': ' thử',  # try doing
        'てみた': ' thử rồi',
        'ておく': ' sẵn',  # do in advance
        'ている': ' đang',  # progressive
        'てある': ' rồi',  # resultant state
        
        # Common compound verbs
        'し始める': 'bắt đầu làm',
        'し続ける': 'tiếp tục làm',
        'し終わる': 'làm xong',
        '食べ始める': 'bắt đầu ăn',
        '見上げる': 'ngước nhìn',
        '見下ろす': 'nhìn xuống',
        '思い出す': 'nhớ lại',
        '飛び出す': 'lao ra',
        '走り出す': 'chạy ra',
        '立ち上がる': 'đứng dậy',
        '座り込む': 'ngồi phịch',
        '振り返る': 'quay lại',
        '追いかける': 'đuổi theo',
        '引き返す': 'quay về',
        '落ち着く': 'bình tĩnh',
        '気づく': 'nhận ra',
        '気がする': 'cảm thấy',
        
        # Sentence-ending particles
        'だよね': ' nhỉ',
        'だよ': ' đấy',
        'だね': ' nhỉ',
        'かな': ' nhỉ',
        'のに': ' mà',
        'けど': ' nhưng',
        'から': ' vì',
    }
    
    # Cyrillic leaks (rare but happen)
    CYRILLIC_SUBSTITUTIONS = {
        'добавление': 'bổ sung',
        'привет': 'xin chào',
        'да': 'vâng',
        'нет': 'không',
    }
    
    # CJK Unicode ranges
    CJK_UNIFIED = r'[\u4E00-\u9FFF]'  # Chinese/Japanese Kanji
    HIRAGANA = r'[\u3040-\u309F]'
    KATAKANA = r'[\u30A0-\u30FF]'
    HANGUL = r'[\uAC00-\uD7AF]'  # Korean
    CYRILLIC = r'[\u0400-\u04FF]'
    
    def __init__(self, strict_mode: bool = True, log_substitutions: bool = True):
        """
        Initialize Vietnamese CJK cleaner.
        
        Args:
            strict_mode: If True, auto-applies substitutions. If False, only detects.
            log_substitutions: If True, logs all substitutions made.
        """
        self.strict_mode = strict_mode
        self.log_substitutions = log_substitutions
        self.substitution_log: List[CJKSubstitution] = []
        
        # Compile patterns for efficiency
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for all substitution rules."""
        self.compiled_kanji = {
            re.compile(re.escape(k)): v 
            for k, v in self.KANJI_SUBSTITUTIONS.items()
        }
        self.compiled_katakana = {
            re.compile(re.escape(k)): v 
            for k, v in self.KATAKANA_SUBSTITUTIONS.items()
        }
        self.compiled_hiragana = {
            re.compile(re.escape(k)): v 
            for k, v in self.HIRAGANA_SUBSTITUTIONS.items()
        }
        self.compiled_cyrillic = {
            re.compile(re.escape(k)): v 
            for k, v in self.CYRILLIC_SUBSTITUTIONS.items()
        }
        self.compiled_hangul = {
            re.compile(re.escape(k)): v 
            for k, v in self.HANGUL_SUBSTITUTIONS.items()
        }
        
        # Pattern to detect any remaining CJK
        self.cjk_detect_pattern = re.compile(
            f'{self.CJK_UNIFIED}|{self.HIRAGANA}|{self.KATAKANA}|{self.HANGUL}'
        )
        self.cyrillic_detect_pattern = re.compile(self.CYRILLIC)
    
    def clean_text(self, text: str, line_offset: int = 0) -> Tuple[str, List[CJKSubstitution]]:
        """
        Clean CJK leaks from Vietnamese text.
        
        Args:
            text: Vietnamese text with potential CJK leaks
            line_offset: Line number offset for logging
            
        Returns:
            Tuple of (cleaned_text, list_of_substitutions)
        """
        substitutions = []
        cleaned = text
        
        # Apply Kanji substitutions
        for pattern, replacement in self.compiled_kanji.items():
            matches = list(pattern.finditer(cleaned))
            for match in matches:
                if self.log_substitutions:
                    # Get context
                    start = max(0, match.start() - 20)
                    end = min(len(cleaned), match.end() + 20)
                    context = cleaned[start:end]
                    
                    substitutions.append(CJKSubstitution(
                        original=match.group(),
                        replacement=replacement,
                        line_number=line_offset,
                        context=context,
                        pattern_type='kanji'
                    ))
                
                if self.strict_mode:
                    cleaned = pattern.sub(replacement, cleaned)
        
        # Apply Katakana substitutions
        for pattern, replacement in self.compiled_katakana.items():
            matches = list(pattern.finditer(cleaned))
            for match in matches:
                if self.log_substitutions:
                    start = max(0, match.start() - 20)
                    end = min(len(cleaned), match.end() + 20)
                    context = cleaned[start:end]
                    
                    substitutions.append(CJKSubstitution(
                        original=match.group(),
                        replacement=replacement,
                        line_number=line_offset,
                        context=context,
                        pattern_type='katakana'
                    ))
                
                if self.strict_mode:
                    cleaned = pattern.sub(replacement, cleaned)
        
        # Apply Hiragana substitutions (adverbs, expressions)
        for pattern, replacement in self.compiled_hiragana.items():
            matches = list(pattern.finditer(cleaned))
            for match in matches:
                if self.log_substitutions:
                    start = max(0, match.start() - 20)
                    end = min(len(cleaned), match.end() + 20)
                    context = cleaned[start:end]
                    
                    substitutions.append(CJKSubstitution(
                        original=match.group(),
                        replacement=replacement,
                        line_number=line_offset,
                        context=context,
                        pattern_type='hiragana'
                    ))
                
                if self.strict_mode:
                    cleaned = pattern.sub(replacement, cleaned)
        
        # Apply Hangul (Korean) substitutions
        for pattern, replacement in self.compiled_hangul.items():
            matches = list(pattern.finditer(cleaned))
            for match in matches:
                if self.log_substitutions:
                    start = max(0, match.start() - 20)
                    end = min(len(cleaned), match.end() + 20)
                    context = cleaned[start:end]
                    
                    substitutions.append(CJKSubstitution(
                        original=match.group(),
                        replacement=replacement,
                        line_number=line_offset,
                        context=context,
                        pattern_type='hangul'
                    ))
                
                if self.strict_mode:
                    cleaned = pattern.sub(replacement, cleaned)
        
        # Apply Cyrillic substitutions
        for pattern, replacement in self.compiled_cyrillic.items():
            matches = list(pattern.finditer(cleaned))
            for match in matches:
                if self.log_substitutions:
                    start = max(0, match.start() - 20)
                    end = min(len(cleaned), match.end() + 20)
                    context = cleaned[start:end]
                    
                    substitutions.append(CJKSubstitution(
                        original=match.group(),
                        replacement=replacement,
                        line_number=line_offset,
                        context=context,
                        pattern_type='cyrillic'
                    ))
                
                if self.strict_mode:
                    cleaned = pattern.sub(replacement, cleaned)
        
        return cleaned, substitutions
    
    def detect_remaining_leaks(self, text: str) -> List[Tuple[str, int, str]]:
        """
        Detect any remaining CJK/Cyrillic leaks after substitution.
        
        Returns list of (character, position, type)
        """
        leaks = []
        
        # CJK leaks
        for match in self.cjk_detect_pattern.finditer(text):
            char = match.group()
            pos = match.start()
            
            # Determine type
            code = ord(char)
            if 0x4E00 <= code <= 0x9FFF:
                char_type = 'kanji'
            elif 0x3040 <= code <= 0x309F:
                char_type = 'hiragana'
            elif 0x30A0 <= code <= 0x30FF:
                char_type = 'katakana'
            elif 0xAC00 <= code <= 0xD7AF:
                char_type = 'hangul'
            else:
                char_type = 'unknown_cjk'
            
            leaks.append((char, pos, char_type))
        
        # Cyrillic leaks
        for match in self.cyrillic_detect_pattern.finditer(text):
            leaks.append((match.group(), match.start(), 'cyrillic'))
        
        return leaks
    
    def clean_file(self, filepath: Path) -> Dict[str, any]:
        """
        Clean CJK leaks from a translated Vietnamese file.
        
        Args:
            filepath: Path to Vietnamese markdown file
            
        Returns:
            Dictionary with statistics and results
        """
        if not filepath.exists():
            return {
                'file': str(filepath),
                'error': 'File not found',
                'substitutions': 0,
                'remaining_leaks': 0,
                'modified': False
            }
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        all_substitutions = []
        
        # Process line by line for accurate line numbers
        lines = content.split('\n')
        cleaned_lines = []
        
        for line_num, line in enumerate(lines, 1):
            cleaned_line, subs = self.clean_text(line, line_num)
            cleaned_lines.append(cleaned_line)
            all_substitutions.extend(subs)
        
        cleaned_content = '\n'.join(cleaned_lines)
        
        # Detect remaining leaks
        remaining_leaks = self.detect_remaining_leaks(cleaned_content)
        
        result = {
            'file': filepath.name,
            'substitutions': len(all_substitutions),
            'remaining_leaks': len(remaining_leaks),
            'modified': False,
            'substitution_details': [],
            'leak_details': []
        }
        
        # Log substitutions
        for sub in all_substitutions:
            result['substitution_details'].append({
                'original': sub.original,
                'replacement': sub.replacement,
                'line': sub.line_number,
                'type': sub.pattern_type,
                'context': sub.context[:60] + '...' if len(sub.context) > 60 else sub.context
            })
        
        # Log remaining leaks
        for char, pos, char_type in remaining_leaks:
            result['leak_details'].append({
                'char': char,
                'code': f'U+{ord(char):04X}',
                'type': char_type,
                'position': pos
            })
        
        # Write back if modified
        if cleaned_content != original_content and self.strict_mode:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            result['modified'] = True
            logger.info(f"✓ Cleaned {filepath.name}: {len(all_substitutions)} substitutions, "
                       f"{len(remaining_leaks)} remaining leaks")
        
        return result
    
    def clean_volume(self, vn_dir: Path) -> Dict[str, any]:
        """
        Clean all Vietnamese chapter files in a volume.
        
        Args:
            vn_dir: Path to VN directory containing CHAPTER_*.md files
            
        Returns:
            Summary statistics
        """
        if not vn_dir.exists():
            return {
                'directory': str(vn_dir),
                'error': 'Directory not found',
                'files_processed': 0
            }
        
        files = sorted(vn_dir.glob('CHAPTER_*.md'))
        
        results = {
            'directory': str(vn_dir),
            'files_processed': 0,
            'files_modified': 0,
            'total_substitutions': 0,
            'total_remaining_leaks': 0,
            'file_results': []
        }
        
        logger.info(f"\n[VN CJK CLEANER] Processing {len(files)} files in {vn_dir.name}...")
        
        for filepath in files:
            file_result = self.clean_file(filepath)
            results['files_processed'] += 1
            results['total_substitutions'] += file_result['substitutions']
            results['total_remaining_leaks'] += file_result['remaining_leaks']
            
            if file_result.get('modified'):
                results['files_modified'] += 1
            
            if file_result['substitutions'] > 0 or file_result['remaining_leaks'] > 0:
                results['file_results'].append(file_result)
        
        # Summary log
        logger.info(f"[VN CJK CLEANER] Complete: {results['files_processed']} files, "
                   f"{results['total_substitutions']} substitutions, "
                   f"{results['total_remaining_leaks']} remaining leaks")
        
        return results


def format_cleaner_report(results: Dict[str, any]) -> str:
    """Format cleaner results into a readable report."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("VIETNAMESE CJK LEAK CLEANER REPORT")
    lines.append("=" * 60)
    
    lines.append(f"\nDirectory: {results.get('directory', 'Unknown')}")
    lines.append(f"Files processed: {results['files_processed']}")
    lines.append(f"Files modified: {results['files_modified']}")
    lines.append(f"Total substitutions: {results['total_substitutions']}")
    lines.append(f"Remaining leaks: {results['total_remaining_leaks']}")
    
    for file_result in results.get('file_results', []):
        if file_result['substitutions'] > 0 or file_result['remaining_leaks'] > 0:
            lines.append(f"\n  File: {file_result['file']}")
            lines.append(f"    Substitutions: {file_result['substitutions']}")
            lines.append(f"    Remaining leaks: {file_result['remaining_leaks']}")
            
            # Show substitution details
            for detail in file_result.get('substitution_details', [])[:5]:
                lines.append(f"    ✓ Line {detail['line']}: '{detail['original']}' → '{detail['replacement']}' ({detail['type']})")
            
            if len(file_result.get('substitution_details', [])) > 5:
                remaining = len(file_result['substitution_details']) - 5
                lines.append(f"    ... and {remaining} more substitutions")
            
            # Show remaining leaks
            for leak in file_result.get('leak_details', [])[:5]:
                lines.append(f"    ⚠ Unknown: '{leak['char']}' ({leak['code']}, {leak['type']})")
            
            if len(file_result.get('leak_details', [])) > 5:
                remaining = len(file_result['leak_details']) - 5
                lines.append(f"    ... and {remaining} more unknown leaks")
    
    lines.append("\n" + "=" * 60 + "\n")
    
    return '\n'.join(lines)


# Entry point for CLI usage
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vn_cjk_cleaner.py <VN_DIRECTORY>")
        sys.exit(1)
    
    vn_dir = Path(sys.argv[1])
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    cleaner = VietnameseCJKCleaner(strict_mode=True, log_substitutions=True)
    results = cleaner.clean_volume(vn_dir)
    
    print(format_cleaner_report(results))
