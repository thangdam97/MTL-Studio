"""
Pinyin Helper for Chinese Text Disambiguation

This module provides pinyin romanization for common Chinese terms
used in cultivation novels. It helps Gemini text-embedding-004
produce distinguishable embeddings for short Chinese phrases.

Note: This is a simplified lookup-based approach. For full pinyin
support, consider using pypinyin library.
"""

# Common cultivation novel terms with pinyin
PINYIN_MAP = {
    # Cultivation realms
    "修真": "xiuzhen",
    "修仙": "xiuxian", 
    "修炼": "xiulian",
    "修为": "xiuwei",
    "修士": "xiushi",
    "练气": "lianqi",
    "练气期": "lianqiqi",
    "筑基": "zhuji",
    "筑基期": "zhujiqi",
    "金丹": "jindan",
    "金丹期": "jindanqi",
    "元婴": "yuanying",
    "元婴期": "yuanyingqi",
    "化神": "huashen",
    "化神期": "huashenqi",
    "渡劫": "dujie",
    "渡劫期": "dujieqi",
    "大乘": "dacheng",
    "大乘期": "dachengqi",
    "飞升": "feisheng",
    "成仙": "chengxian",
    "结丹": "jiedan",
    "修道": "xiudao",
    "修道之人": "xiudaozhiren",
    
    # Energy and spiritual concepts
    "灵气": "lingqi",
    "灵力": "lingli",
    "灵石": "lingshi",
    "灵脉": "lingmai",
    "灵根": "linggen",
    "灵宝": "lingbao",
    "灵丹": "lingdan",
    "灵兽": "lingshou",
    "真气": "zhenqi",
    "仙气": "xianqi",
    "妖气": "yaoqi",
    "魔气": "moqi",
    "气运": "qiyun",
    "气息": "qixi",
    "元气": "yuanqi",
    "神识": "shenshi",
    "神魂": "shenhun",
    "识海": "shihai",
    "丹田": "dantian",
    
    # Titles and honorifics
    "道友": "daoyou",
    "道友可好": "daoyoukehao",
    "道长": "daozhang",
    "师父": "shifu",
    "师兄": "shixiong",
    "师姐": "shijie",
    "师弟": "shidi",
    "师妹": "shimei",
    "前辈": "qianbei",
    "前辈请": "qianbeiqing",
    "晚辈": "wanbei",
    "掌门": "zhangmen",
    "长老": "zhanglao",
    "真人": "zhenren",
    "散修": "sanxiu",
    
    # Techniques and methods
    "功法": "gongfa",
    "修炼功法": "xiuliangongfa",
    "心法": "xinfa",
    "剑法": "jianfa",
    "刀法": "daofa",
    "拳法": "quanfa",
    "身法": "shenfa",
    "飞剑": "feijian",
    "法宝": "fabao",
    "法器": "faqi",
    "灵丹": "lingdan",
    "丹药": "danyao",
    "阵法": "zhenfa",
    "禁制": "jinzhi",
    "结界": "jiejie",
    
    # Places and concepts
    "道观": "daoguan",
    "仙门": "xianmen",
    "门派": "menpai",
    "宗门": "zongmen",
    "洞府": "dongfu",
    "福地": "fudi",
    "秘境": "mijing",
    "天道": "tiandao",
    "大道": "dadao",
    "道心": "daoxin",
    "境界": "jingjie",
    "瓶颈": "pingjing",
    "突破": "tupo",
    "闭关": "biguan",
    
    # Character types
    "魔修": "moxiu",
    "妖修": "yaoxiu",
    "鬼修": "guixiu",
    "剑修": "jianxiu",
    "体修": "tixiu",
    "炼器师": "lianqishi",
    "炼丹师": "liandanshi",
    "阵法师": "zhenfashi",
    
    # Actions
    "参悟": "canwu",
    "顿悟": "dunwu",
    "入定": "ruding",
    "吐纳": "tuna",
    "运功": "yungong",
    "炼化": "lianhua",
    "祭炼": "jilian",
    "御剑": "yujian",
    "飞遁": "feidun",
    
    # Common words (non-cultivation)
    "真的": "zhende",
    "不是": "bushi",
    "什么": "shenme",
    "这个": "zhege",
    "那个": "nage",
    
    # Individual characters for building compound pinyin
    "修": "xiu",
    "道": "dao",
    "气": "qi",
    "灵": "ling",
    "真": "zhen",
    "的": "de",
    "是": "shi",
    "不": "bu",
    "了": "le",
    "我": "wo",
    "你": "ni",
    "他": "ta",
    "她": "ta",
    "它": "ta",
    "们": "men",
    "这": "zhe",
    "那": "na",
    "什": "shen",
    "么": "me",
    "需": "xu",
    "要": "yao",
    "就": "jiu",
    "也": "ye",
    "都": "dou",
    "能": "neng",
    "会": "hui",
    "在": "zai",
    "有": "you",
    "到": "dao",
    "说": "shuo",
    "看": "kan",
    "把": "ba",
    "上": "shang",
    "下": "xia",
    "来": "lai",
    "去": "qu",
    "出": "chu",
    "进": "jin",
    "过": "guo",
    "还": "hai",
    "很": "hen",
    "更": "geng",
    "大": "da",
    "小": "xiao",
    "高": "gao",
    "低": "di",
    "中": "zhong",
    "仙": "xian",
    "魔": "mo",
    "妖": "yao",
    "剑": "jian",
    "丹": "dan",
    "法": "fa",
    "境": "jing",
    "期": "qi",
    "之": "zhi",
    "人": "ren",
    "请": "qing",
    "可": "ke",
    "好": "hao",
    "石": "shi",
    "神": "shen",
    "观": "guan",
    "基": "ji",
    "筑": "zhu",
    "金": "jin",
    "元": "yuan",
    "婴": "ying",
    "化": "hua",
    "渡": "du",
    "劫": "jie",
    "练": "lian",
    "炼": "lian",
    "功": "gong",
    "师": "shi",
    "父": "fu",
    "前": "qian",
    "辈": "bei",
    "友": "you",
    "门": "men",
    "派": "pai",
    "宗": "zong",
    "飞": "fei",
    "运": "yun",
}


def get_pinyin(chinese_text: str) -> str:
    """
    Get pinyin romanization for Chinese text.
    
    Tries to match the full text first, then individual characters.
    
    Args:
        chinese_text: Chinese text to romanize
        
    Returns:
        Pinyin string, or empty string if no match found
    """
    # Try full text match first
    if chinese_text in PINYIN_MAP:
        return PINYIN_MAP[chinese_text]
    
    # Try to build pinyin character by character
    pinyin_parts = []
    for char in chinese_text:
        if char in PINYIN_MAP:
            pinyin_parts.append(PINYIN_MAP[char])
        elif '\u4e00' <= char <= '\u9fff':
            # Chinese character without pinyin mapping
            pinyin_parts.append('?')
    
    if pinyin_parts and '?' not in pinyin_parts:
        return ''.join(pinyin_parts)
    
    return ""


def enhance_query_with_pinyin(chinese_text: str) -> str:
    """
    Enhance Chinese text with pinyin for better embedding.
    
    Handles multi-segment queries by processing each segment individually.
    
    Args:
        chinese_text: Original Chinese text (may contain spaces for multi-segment)
        
    Returns:
        Enhanced text with pinyin (e.g., "修真 xiuzhen")
    """
    # Check for multi-segment (space-separated) queries first
    if ' ' in chinese_text:
        segments = chinese_text.split()
        enhanced_segments = []
        
        for segment in segments:
            # Check if segment contains Chinese characters
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in segment)
            if has_chinese:
                segment_pinyin = get_pinyin(segment)
                if segment_pinyin:
                    enhanced_segments.append(f"{segment} {segment_pinyin}")
                else:
                    enhanced_segments.append(segment)
            else:
                enhanced_segments.append(segment)
        
        return " ".join(enhanced_segments)
    
    # Single segment: try to add pinyin
    pinyin = get_pinyin(chinese_text)
    if pinyin:
        return f"{chinese_text} {pinyin}"
    return chinese_text


def enhance_document_with_pinyin(
    chinese_text: str,
    vietnamese_text: str,
    meaning: str = ""
) -> str:
    """
    Create an enhanced document string for indexing.
    
    Format: "修真 xiuzhen - tu chân (cultivation practice)"
    
    Args:
        chinese_text: Original Chinese text
        vietnamese_text: Vietnamese translation
        meaning: Optional English meaning
        
    Returns:
        Enhanced document string for embedding
    """
    pinyin = get_pinyin(chinese_text)
    
    parts = [chinese_text]
    if pinyin:
        parts.append(pinyin)
    
    if vietnamese_text:
        parts.append(f"- {vietnamese_text}")
    
    if meaning:
        parts.append(f"({meaning})")
    
    return " ".join(parts)


if __name__ == "__main__":
    # Test the module
    test_terms = ["修真", "金丹", "灵气", "道友", "师父", "筑基期"]
    
    print("Testing pinyin helper:")
    for term in test_terms:
        enhanced = enhance_query_with_pinyin(term)
        print(f"  {term} → {enhanced}")
