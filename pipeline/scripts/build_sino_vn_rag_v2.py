#!/usr/bin/env python3
"""
Sino-Vietnamese RAG v2 Builder
================================
Merges 4 data sources + corpus-discovered compounds into a unified v2 schema:
1. sino_vietnamese_rag.json v1 (722 patterns: 10+6+3+3+700)
2. kanji_difficult.json (71 kanji, 78 compounds)
3. sino_vietnamese_context_rules.json (25 terms, 3-tier register)
4. false_cognates (2 patterns - was stranded as top-level key)
5. corpus_scan_sino_vn.json (29 new high-frequency compounds)

Output: pipeline/config/sino_vietnamese_rag_v2.json
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
VN_DIR = BASE_DIR / "VN"
SCRIPTS_DIR = BASE_DIR / "scripts"


def load_rag_v1():
    """Load and parse RAG v1."""
    with open(CONFIG_DIR / "sino_vietnamese_rag.json") as f:
        return json.load(f)


def load_kanji_difficult():
    """Load kanji_difficult.json."""
    with open(VN_DIR / "kanji_difficult.json") as f:
        return json.load(f)


def load_context_rules():
    """Load context rules."""
    with open(CONFIG_DIR / "sino_vietnamese_context_rules.json") as f:
        return json.load(f)


def load_corpus_scan():
    """Load corpus scan results."""
    with open(SCRIPTS_DIR / "corpus_scan_sino_vn.json") as f:
        return json.load(f)


# ============================================================================
# CATEGORY 1: sino_disambiguation (from v1 — 10 patterns, keep as-is)
# ============================================================================

def build_sino_disambiguation(rag_v1):
    """Migrate sino_disambiguation patterns from v1. No changes needed."""
    cat = rag_v1["pattern_categories"]["sino_disambiguation"]
    return {
        "description": "Context-aware Hán-Việt homonym resolution for polysemous characters",
        "patterns": cat["patterns"]
    }


# ============================================================================
# CATEGORY 2: cultivation_realms (from v1 — 6 patterns, keep as-is)
# ============================================================================

def build_cultivation_realms(rag_v1):
    """Migrate cultivation_realms from v1."""
    cat = rag_v1["pattern_categories"]["cultivation_realms"]
    return {
        "description": "Cultivation power system progression tiers",
        "patterns": cat["patterns"]
    }


# ============================================================================
# CATEGORY 3: cultivation_techniques (from v1 — 3 patterns, keep as-is)
# ============================================================================

def build_cultivation_techniques(rag_v1):
    """Migrate cultivation_techniques from v1."""
    cat = rag_v1["pattern_categories"]["cultivation_techniques"]
    return {
        "description": "Cultivation technique and skill naming conventions",
        "patterns": cat["patterns"]
    }


# ============================================================================
# CATEGORY 4: titles_honorifics (from v1 — 3 patterns, keep as-is)
# ============================================================================

def build_titles_honorifics(rag_v1):
    """Migrate titles_honorifics from v1."""
    cat = rag_v1["pattern_categories"]["titles_honorifics"]
    return {
        "description": "Formal titles and honorific conventions",
        "patterns": cat["patterns"]
    }


# ============================================================================
# CATEGORY 5: japanese_light_novel (from v1 — 700 patterns, keep as-is)
# ============================================================================

def build_japanese_light_novel(rag_v1):
    """Migrate JP LN patterns from v1."""
    cat = rag_v1["pattern_categories"]["japanese_light_novel"]
    return {
        "description": "High-frequency Japanese light novel kanji compounds with Sino-Vietnamese disambiguation",
        "patterns": cat["patterns"]
    }


# ============================================================================
# CATEGORY 6: false_cognates (from v1 top-level — NOW INSIDE pattern_categories)
# ============================================================================

def build_false_cognates(rag_v1):
    """
    Move false_cognates from stranded top-level key INTO pattern_categories.
    Convert to standard pattern schema so build_index() can iterate them.
    """
    fc = rag_v1.get("false_cognates", {})
    fc_patterns = fc.get("patterns", [])
    
    converted_patterns = []
    for p in fc_patterns:
        zh = p.get("zh", "")
        cult_meaning = p.get("cultivation_meaning", "")
        casual_meaning = p.get("casual_meaning", "")
        distinguish = p.get("how_to_distinguish", "")
        
        converted_patterns.append({
            "id": f"fc_{zh}",
            "hanzi": zh,
            "primary_reading": cult_meaning.split(" (")[0] if " (" in cult_meaning else cult_meaning,
            "sino_vietnamese": True,
            "corpus_frequency": 500,
            "contexts": [
                {
                    "meaning": "cultivation_spiritual",
                    "register": "formal",
                    "zh_indicators": ["修炼", "丹田", "入魔", "真气", "灵气"],
                    "vn_translation": cult_meaning.split(" (")[0] if " (" in cult_meaning else cult_meaning,
                    "vn_phrases": [cult_meaning.split(" (")[0] if " (" in cult_meaning else cult_meaning],
                    "avoid": [casual_meaning.split(" (")[0] if " (" in casual_meaning else casual_meaning],
                    "examples": [
                        {
                            "zh": zh,
                            "vn_correct": cult_meaning.split(" (")[0] if " (" in cult_meaning else cult_meaning,
                            "vn_wrong": casual_meaning.split(" (")[0] if " (" in casual_meaning else casual_meaning,
                            "context": "cultivation_novel",
                            "note": distinguish
                        }
                    ]
                },
                {
                    "meaning": "casual_everyday",
                    "register": "casual",
                    "zh_indicators": ["好运", "幸运", "武器", "枪"],
                    "vn_translation": casual_meaning.split(" (")[0] if " (" in casual_meaning else casual_meaning,
                    "vn_phrases": [casual_meaning.split(" (")[0] if " (" in casual_meaning else casual_meaning],
                    "avoid": [cult_meaning.split(" (")[0] if " (" in cult_meaning else cult_meaning],
                    "examples": [
                        {
                            "zh": zh,
                            "vn_correct": casual_meaning.split(" (")[0] if " (" in casual_meaning else casual_meaning,
                            "vn_wrong": cult_meaning.split(" (")[0] if " (" in cult_meaning else cult_meaning,
                            "context": "modern",
                            "note": distinguish
                        }
                    ]
                }
            ]
        })
    
    return {
        "description": "False cognates: same kanji, completely different meanings by context. CRITICAL for disambiguation.",
        "patterns": converted_patterns
    }


# ============================================================================
# CATEGORY 7: register_substitutions (from context_rules — 25 terms)
# ============================================================================

def build_register_substitutions(context_rules):
    """
    Convert context_rules.json mandatory_substitutions into indexable patterns.
    3-tier register system: technical_formal, historical_formal, modern_casual.
    """
    patterns = []
    seen_kanji = set()
    
    # Tier 3 mandatory substitutions (most important — modern casual genre)
    tier3 = context_rules.get("tier_3_modern_casual", {})
    for sub in tier3.get("mandatory_substitutions", []):
        kanji = sub.get("kanji", "")
        if not kanji or kanji in seen_kanji:
            continue
        seen_kanji.add(kanji)
        
        sino_vn = sub.get("sino_vietnamese", "")
        natural_vn = sub.get("natural_vietnamese", "")
        romaji = sub.get("romaji", "")
        rationale = sub.get("rationale", "")
        
        patterns.append({
            "id": f"reg_{kanji}",
            "hanzi": kanji,
            "primary_reading": natural_vn.split("/")[0].strip() if natural_vn else sino_vn,
            "sino_vietnamese": True,
            "corpus_frequency": 1000,
            "romaji": romaji,
            "contexts": [
                {
                    "meaning": "modern_casual",
                    "register": "casual",
                    "zh_indicators": [],
                    "vn_translation": natural_vn,
                    "vn_phrases": [x.strip() for x in natural_vn.split("/") if x.strip()] if natural_vn else [],
                    "avoid": [sino_vn] if sino_vn else [],
                    "examples": [
                        {
                            "zh": kanji,
                            "vn_correct": natural_vn.split("/")[0].strip() if natural_vn else "",
                            "vn_wrong": sino_vn,
                            "context": "modern",
                            "note": rationale
                        }
                    ]
                },
                {
                    "meaning": "historical_formal",
                    "register": "formal",
                    "zh_indicators": [],
                    "vn_translation": sino_vn,
                    "vn_phrases": [sino_vn] if sino_vn else [],
                    "avoid": [natural_vn.split("/")[0].strip()] if natural_vn else [],
                    "examples": [
                        {
                            "zh": kanji,
                            "vn_correct": sino_vn,
                            "vn_wrong": natural_vn.split("/")[0].strip() if natural_vn else "",
                            "context": "historical",
                            "note": f"In formal/historical context, {sino_vn} is appropriate"
                        }
                    ]
                }
            ]
        })
    
    # Tier 1 technical formal examples
    tier1 = context_rules.get("tier_1_technical_formal", {})
    for ex in tier1.get("examples", []):
        kanji = ex.get("kanji", "")
        if not kanji or kanji in seen_kanji:
            continue
        seen_kanji.add(kanji)
        
        sino_vn = ex.get("sino_vietnamese", "")
        romaji = ex.get("romaji", "")
        rationale = ex.get("rationale", "")
        
        patterns.append({
            "id": f"reg_{kanji}",
            "hanzi": kanji,
            "primary_reading": sino_vn,
            "sino_vietnamese": True,
            "corpus_frequency": 800,
            "romaji": romaji,
            "contexts": [
                {
                    "meaning": "technical_formal",
                    "register": "formal",
                    "zh_indicators": [],
                    "vn_translation": sino_vn,
                    "vn_phrases": [sino_vn],
                    "avoid": [],
                    "examples": [
                        {
                            "zh": kanji,
                            "vn_correct": sino_vn,
                            "vn_wrong": "",
                            "context": "technical",
                            "note": rationale
                        }
                    ]
                }
            ]
        })
    
    # Tier 2 historical formal examples
    tier2 = context_rules.get("tier_2_historical_formal", {})
    for ex in tier2.get("examples", []):
        kanji = ex.get("kanji", "")
        if not kanji or kanji in seen_kanji:
            continue
        seen_kanji.add(kanji)
        
        sino_vn = ex.get("sino_vietnamese", "")
        natural_vn = ex.get("natural_vietnamese", "")
        romaji = ex.get("romaji", "")
        rationale = ex.get("rationale", "")
        use = ex.get("use", "sino_vietnamese")
        
        contexts = [{
            "meaning": "historical_formal",
            "register": "formal",
            "zh_indicators": [],
            "vn_translation": sino_vn,
            "vn_phrases": [sino_vn] if sino_vn else [],
            "avoid": [],
            "examples": [{
                "zh": kanji,
                "vn_correct": sino_vn,
                "vn_wrong": natural_vn or "",
                "context": "historical",
                "note": rationale
            }]
        }]
        
        if natural_vn:
            contexts.append({
                "meaning": "modern_casual",
                "register": "casual",
                "zh_indicators": [],
                "vn_translation": natural_vn,
                "vn_phrases": [natural_vn],
                "avoid": [sino_vn] if use == "natural_vietnamese" else [],
                "examples": [{
                    "zh": kanji,
                    "vn_correct": natural_vn,
                    "vn_wrong": sino_vn if use == "natural_vietnamese" else "",
                    "context": "modern",
                    "note": f"In modern/casual context, {natural_vn} is more natural"
                }]
            })
        
        patterns.append({
            "id": f"reg_{kanji}",
            "hanzi": kanji,
            "primary_reading": sino_vn if use == "sino_vietnamese" else (natural_vn or sino_vn),
            "sino_vietnamese": True,
            "corpus_frequency": 600,
            "romaji": romaji,
            "contexts": contexts
        })
    
    return {
        "description": "Register-aware substitutions: Hán Việt vs native Vietnamese by genre/context tier",
        "patterns": patterns
    }


# ============================================================================
# CATEGORY 8: kanji_difficult_compounds (from kanji_difficult.json)
# ============================================================================

def build_kanji_difficult(kd_data, existing_hanzi):
    """
    Convert kanji_difficult.json entries into indexable patterns.
    Only include entries NOT already in RAG v1.
    """
    patterns = []
    seen = set()
    
    for entry in kd_data.get("kanji_entries", []):
        kanji = entry.get("kanji", "")
        han_viet = entry.get("han_viet", "N/A")
        meaning = entry.get("meaning", "")
        priority = entry.get("priority", "LOW")
        category = entry.get("difficulty_category", "")
        genre_relevance = entry.get("genre_relevance", [])
        translation_notes = entry.get("translation_notes", "")
        
        # Process compounds (the main value of this file)
        for compound_data in entry.get("common_compounds", []):
            compound = compound_data.get("compound", "")
            if not compound or compound in existing_hanzi or compound in seen:
                continue
            seen.add(compound)
            
            reading = compound_data.get("reading", "")
            vn_translation = compound_data.get("vn_translation", "")
            usage = compound_data.get("usage", "")
            
            # Determine register based on han_viet and genre
            register = "neutral"
            avoid_list = []
            if han_viet and han_viet != "N/A":
                # If han_viet exists but should be avoided in casual, add to avoid
                if priority in ("TOP", "HIGH") and any(g in genre_relevance for g in ["romcom", "school", "slice_of_life"]):
                    avoid_list = [han_viet] if han_viet != vn_translation.split(",")[0].strip() else []
            
            # Map priority to corpus_frequency
            freq_map = {"TOP": 2000, "HIGH": 1500, "MEDIUM": 800, "LOW": 200}
            corpus_freq = freq_map.get(priority, 200)
            
            contexts = [{
                "meaning": category.replace("_", " "),
                "register": register,
                "zh_indicators": [],
                "vn_translation": vn_translation.split(",")[0].strip(),
                "vn_phrases": [x.strip() for x in vn_translation.split(",") if x.strip()],
                "avoid": avoid_list,
                "examples": [{
                    "zh": compound,
                    "vn_correct": vn_translation.split(",")[0].strip(),
                    "vn_wrong": han_viet if han_viet != "N/A" and avoid_list else "",
                    "context": genre_relevance[0] if genre_relevance else "general",
                    "note": translation_notes[:200] if translation_notes else usage
                }]
            }]
            
            patterns.append({
                "id": f"kd_{compound}",
                "hanzi": compound,
                "primary_reading": vn_translation.split(",")[0].strip(),
                "sino_vietnamese": han_viet != "N/A",
                "corpus_frequency": corpus_freq,
                "han_viet": han_viet,
                "genre_relevance": genre_relevance,
                "priority_tag": priority,
                "contexts": contexts
            })
        
        # Also include the kanji itself if it has a han_viet and isn't already covered
        if kanji and kanji not in existing_hanzi and kanji not in seen:
            if han_viet and han_viet != "N/A":
                seen.add(kanji)
                
                freq_map = {"TOP": 2000, "HIGH": 1500, "MEDIUM": 800, "LOW": 200}
                corpus_freq = freq_map.get(priority, 200)
                
                patterns.append({
                    "id": f"kd_{kanji}",
                    "hanzi": kanji,
                    "primary_reading": han_viet,
                    "sino_vietnamese": True,
                    "corpus_frequency": corpus_freq,
                    "han_viet": han_viet,
                    "genre_relevance": genre_relevance,
                    "priority_tag": priority,
                    "contexts": [{
                        "meaning": meaning,
                        "register": "neutral",
                        "zh_indicators": [],
                        "vn_translation": han_viet,
                        "vn_phrases": [han_viet],
                        "avoid": [],
                        "examples": [{
                            "zh": kanji,
                            "vn_correct": han_viet,
                            "vn_wrong": "",
                            "context": genre_relevance[0] if genre_relevance else "general",
                            "note": translation_notes[:200] if translation_notes else meaning
                        }]
                    }]
                })
    
    return {
        "description": "Difficult kanji with production-validated translations. Includes rare/archaic characters and their compounds.",
        "patterns": patterns
    }


# ============================================================================
# CATEGORY 9: corpus_discovered (from corpus scanner — 29 new compounds)
# ============================================================================

# Manually curated translations for the 29 corpus-discovered high-frequency compounds
# These are real compounds that appear 1800+ times across 148 EPUBs but were missing from all sources
CORPUS_COMPOUND_TRANSLATIONS = {
    "微笑": {"vn": "mỉm cười", "avoid": "vi tiếu", "meaning": "gentle smile", "register": "neutral"},
    "緊張": {"vn": "căng thẳng", "avoid": "khẩn trương", "meaning": "nervous/tense", "register": "neutral"},
    "納得": {"vn": "hiểu ra, chấp nhận", "avoid": "nạp đắc", "meaning": "understand/accept", "register": "neutral"},
    "相談": {"vn": "bàn bạc, trao đổi", "avoid": "tương đàm", "meaning": "discuss/consult", "register": "neutral"},
    "返事": {"vn": "trả lời", "avoid": "phản sự", "meaning": "reply/response", "register": "neutral"},
    "用意": {"vn": "chuẩn bị", "avoid": "dụng ý", "meaning": "preparation", "register": "neutral", "note": "用意 (youi) = preparation, NOT 'intention' (dụng ý). Common false friend."},
    "身体": {"vn": "cơ thể", "avoid": "thân thể", "meaning": "body/health", "register": "neutral", "note": "thân thể too literary for romcom. Use cơ thể."},
    "美味": {"vn": "ngon", "avoid": "mỹ vị", "meaning": "delicious", "register": "casual"},
    "一瞬": {"vn": "một thoáng, khoảnh khắc", "avoid": "nhất thuấn", "meaning": "an instant/moment", "register": "neutral"},
    "勝手": {"vn": "tự ý, tùy tiện", "avoid": "thắng thủ", "meaning": "selfish/at will", "register": "casual"},
    "素直": {"vn": "thật thà, ngoan ngoãn", "avoid": "tố trực", "meaning": "honest/obedient", "register": "casual"},
    "上手": {"vn": "giỏi, khéo", "avoid": "thượng thủ", "meaning": "skillful/good at", "register": "casual"},
    "挨拶": {"vn": "chào hỏi", "avoid": "ai tát", "meaning": "greeting", "register": "neutral"},
    "約束": {"vn": "hẹn, lời hứa", "avoid": "ước thúc", "meaning": "promise/appointment", "register": "neutral"},
    "夏休": {"vn": "nghỉ hè", "avoid": "hạ hưu", "meaning": "summer vacation", "register": "casual"},
    "連絡": {"vn": "liên lạc", "avoid": "", "meaning": "contact/communicate", "register": "neutral", "note": "liên lạc is already natural Sino-Vietnamese that works in modern context"},
    "興味": {"vn": "hứng thú", "avoid": "hưng vị", "meaning": "interest/curiosity", "register": "neutral"},
    "手伝": {"vn": "giúp đỡ", "avoid": "thủ truyền", "meaning": "help/assist", "register": "casual"},
    "自信": {"vn": "tự tin", "avoid": "", "meaning": "self-confidence", "register": "neutral", "note": "tự tin is natural SV that works across registers"},
    "廊下": {"vn": "hành lang", "avoid": "lang hạ", "meaning": "hallway/corridor", "register": "neutral"},
    "着替": {"vn": "thay đồ", "avoid": "trước thế", "meaning": "change clothes", "register": "casual"},
    "簡単": {"vn": "đơn giản", "avoid": "giản đơn", "meaning": "simple/easy", "register": "neutral", "note": "đơn giản is more natural word order than giản đơn in spoken VN"},
    "期待": {"vn": "mong đợi", "avoid": "kỳ đãi", "meaning": "expectation/look forward to", "register": "neutral"},
    "画面": {"vn": "màn hình", "avoid": "họa diện", "meaning": "screen/scene", "register": "neutral"},
    "大切": {"vn": "quan trọng", "avoid": "đại thiết", "meaning": "important/precious", "register": "neutral"},
    "迷惑": {"vn": "phiền phức, làm phiền", "avoid": "mê hoặc", "meaning": "annoyance/trouble", "register": "neutral", "note": "迷惑 (meiwaku) = annoyance, NOT 'enchant' (mê hoặc). Critical false cognate."},
    "参加": {"vn": "tham gia", "avoid": "", "meaning": "participate", "register": "neutral", "note": "tham gia is natural SV that works across registers"},
    # Filter out character names: 帝野 and 押尾 are names, not compounds
}


def build_corpus_discovered(corpus_scan, existing_hanzi):
    """
    Build patterns from corpus-discovered high-frequency compounds.
    """
    patterns = []
    
    # Get frequency data from corpus scan
    freq_map = {}
    for item in corpus_scan.get("compound_frequency", {}).get("top_500", []):
        freq_map[item["compound"]] = item["frequency"]
    
    for hanzi, data in CORPUS_COMPOUND_TRANSLATIONS.items():
        if hanzi in existing_hanzi:
            continue
        
        vn = data["vn"]
        avoid = data.get("avoid", "")
        meaning = data.get("meaning", "")
        register = data.get("register", "neutral")
        note = data.get("note", "")
        freq = freq_map.get(hanzi, 1500)
        
        vn_primary = vn.split(",")[0].strip()
        vn_phrases = [x.strip() for x in vn.split(",") if x.strip()]
        
        contexts = [{
            "meaning": meaning.replace(" ", "_"),
            "register": register,
            "zh_indicators": [],
            "vn_translation": vn_primary,
            "vn_phrases": vn_phrases,
            "avoid": [avoid] if avoid else [],
            "examples": [{
                "zh": hanzi,
                "vn_correct": vn_primary,
                "vn_wrong": avoid if avoid else "",
                "context": "japanese_light_novel",
                "note": note if note else f"Corpus frequency: {freq}. Use natural Vietnamese, avoid Hán Việt."
            }]
        }]
        
        patterns.append({
            "id": f"cd_{hanzi}",
            "hanzi": hanzi,
            "primary_reading": vn_primary,
            "sino_vietnamese": True,
            "corpus_frequency": freq,
            "source": "corpus_scanner_v1",
            "contexts": contexts
        })
    
    return {
        "description": "High-frequency compounds discovered by corpus scanner (148 EPUBs). Not in any prior data source.",
        "patterns": patterns
    }


# ============================================================================
# NEGATIVE VECTORS (for negative anchor system)
# ============================================================================

def build_negative_vectors():
    """
    Build negative vector anchors for each category.
    These are patterns that should NOT match for a given category.
    """
    return {
        "sino_disambiguation": [
            {"text": "casual conversation everyday modern dialogue", "label": "not_disambiguation"},
            {"text": "simple vocabulary basic translation word-for-word", "label": "not_disambiguation"},
            {"text": "person name character name location name proper noun", "label": "not_disambiguation"}
        ],
        "cultivation_realms": [
            {"text": "modern school romcom contemporary slice of life", "label": "not_cultivation"},
            {"text": "everyday conversation casual dialogue friends", "label": "not_cultivation"},
            {"text": "general vocabulary common words basic translation", "label": "not_cultivation"}
        ],
        "false_cognates": [
            {"text": "straightforward translation no ambiguity clear meaning", "label": "not_false_cognate"},
            {"text": "simple kanji basic vocabulary no confusion", "label": "not_false_cognate"}
        ],
        "register_substitutions": [
            {"text": "technical academic formal legal medical political", "label": "not_casual_register"},
            {"text": "cultivation xianxia wuxia martial arts historical", "label": "not_casual_register"},
            {"text": "informal slang colloquial internet speak", "label": "not_formal_register"}
        ],
        "kanji_difficult_compounds": [
            {"text": "common easy simple basic everyday vocabulary", "label": "not_difficult"},
            {"text": "N5 N4 basic JLPT elementary beginner", "label": "not_difficult"}
        ],
        "corpus_discovered": [
            {"text": "rare obscure archaic literary classical", "label": "not_corpus_common"},
            {"text": "cultivation fantasy mythical supernatural", "label": "not_corpus_common"}
        ]
    }


# ============================================================================
# MAIN BUILDER
# ============================================================================

def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Sino-Vietnamese RAG v2 Builder                        ║")
    print("║  Merging 4 sources + corpus compounds                   ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    # Load all sources
    print("Loading data sources...")
    rag_v1 = load_rag_v1()
    kd_data = load_kanji_difficult()
    cr_data = load_context_rules()
    corpus_scan = load_corpus_scan()
    
    # Track existing hanzi to avoid duplicates
    existing_hanzi = set()
    
    # Build each category
    print("\nBuilding categories...")
    
    # Cat 1: sino_disambiguation (10 patterns)
    cat_sino = build_sino_disambiguation(rag_v1)
    for p in cat_sino["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  1. sino_disambiguation: {len(cat_sino['patterns'])} patterns")
    
    # Cat 2: cultivation_realms (6 patterns)
    cat_cult_realms = build_cultivation_realms(rag_v1)
    for p in cat_cult_realms["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  2. cultivation_realms: {len(cat_cult_realms['patterns'])} patterns")
    
    # Cat 3: cultivation_techniques (3 patterns)
    cat_cult_tech = build_cultivation_techniques(rag_v1)
    for p in cat_cult_tech["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  3. cultivation_techniques: {len(cat_cult_tech['patterns'])} patterns")
    
    # Cat 4: titles_honorifics (3 patterns)
    cat_titles = build_titles_honorifics(rag_v1)
    for p in cat_titles["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  4. titles_honorifics: {len(cat_titles['patterns'])} patterns")
    
    # Cat 5: japanese_light_novel (700 patterns)
    cat_jp_ln = build_japanese_light_novel(rag_v1)
    for p in cat_jp_ln["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  5. japanese_light_novel: {len(cat_jp_ln['patterns'])} patterns")
    
    # Cat 6: false_cognates (from top-level → now inside categories)
    cat_fc = build_false_cognates(rag_v1)
    for p in cat_fc["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  6. false_cognates: {len(cat_fc['patterns'])} patterns (FIXED: now indexable)")
    
    # Cat 7: register_substitutions (from context_rules)
    cat_reg = build_register_substitutions(cr_data)
    for p in cat_reg["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  7. register_substitutions: {len(cat_reg['patterns'])} patterns (NEW: from context_rules)")
    
    # Cat 8: kanji_difficult_compounds (from kanji_difficult)
    cat_kd = build_kanji_difficult(kd_data, existing_hanzi)
    for p in cat_kd["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  8. kanji_difficult_compounds: {len(cat_kd['patterns'])} patterns (NEW: from kanji_difficult)")
    
    # Cat 9: corpus_discovered (from corpus scanner)
    cat_cd = build_corpus_discovered(corpus_scan, existing_hanzi)
    for p in cat_cd["patterns"]:
        existing_hanzi.add(p.get("hanzi", ""))
    print(f"  9. corpus_discovered: {len(cat_cd['patterns'])} patterns (NEW: from corpus scanner)")
    
    # Build v2 JSON
    total_patterns = sum(len(cat["patterns"]) for cat in [
        cat_sino, cat_cult_realms, cat_cult_tech, cat_titles, cat_jp_ln,
        cat_fc, cat_reg, cat_kd, cat_cd
    ])
    
    v2 = {
        "version": "2.0",
        "description": "Sino-Vietnamese Disambiguation RAG v2.0 — Unified database merging 4 sources + corpus analysis",
        "last_updated": "2026-02-07",
        "status": "production",
        "changelog": {
            "v2.0": "Merged RAG v1 (722) + kanji_difficult (71+78) + context_rules (25) + false_cognates (2) + corpus scanner (27). Fixed false cognate indexing bug. Added register substitutions. Added negative vectors.",
            "v1.0": "Initial experimental release with 722 patterns"
        },
        "statistics": {
            "total_patterns": total_patterns,
            "total_categories": 9,
            "sources_merged": [
                "sino_vietnamese_rag.json v1 (722 patterns)",
                "kanji_difficult.json (71 kanji, 78 compounds)",
                "sino_vietnamese_context_rules.json (25 terms)",
                "false_cognates (2 patterns, was stranded)",
                "corpus_scan_sino_vn.json (27 new compounds)"
            ],
            "corpus_stats": {
                "epubs_scanned": 148,
                "total_jp_chars": 17993660,
                "jp_vn_paired_examples": 2903,
                "native_vn_ratio": "92.9%"
            }
        },
        "notes": {
            "purpose": "Context-aware disambiguation of Hán-Việt homonyms for JP→VN translation",
            "target_genres": [
                "japanese_light_novel",
                "cultivation/xianxia",
                "wuxia",
                "historical",
                "romcom",
                "school_life",
                "slice_of_life"
            ],
            "embedding_model": "Gemini text-embedding-004 (768D via PatternVectorStore)",
            "key_improvements_v2": [
                "false_cognates now inside pattern_categories (was stranded, never indexed)",
                "register_substitutions: 3-tier Hán Việt vs native Vietnamese by genre",
                "kanji_difficult: production-validated difficult kanji compounds",
                "corpus_discovered: 27 high-frequency compounds missing from all prior sources",
                "negative_vectors: per-category negative anchors for precision",
                "unified schema: all patterns use contexts[] format for consistent indexing"
            ]
        },
        "pattern_categories": {
            "sino_disambiguation": cat_sino,
            "cultivation_realms": cat_cult_realms,
            "cultivation_techniques": cat_cult_tech,
            "titles_honorifics": cat_titles,
            "japanese_light_novel": cat_jp_ln,
            "false_cognates": cat_fc,
            "register_substitutions": cat_reg,
            "kanji_difficult_compounds": cat_kd,
            "corpus_discovered": cat_cd
        },
        "register_guide": rag_v1.get("register_guide", {}),
        "genre_mapping": cr_data.get("genre_mapping", {}),
        "validation_rules": cr_data.get("validation_rules", []),
        "negative_vectors": build_negative_vectors()
    }
    
    # Write output
    output_path = CONFIG_DIR / "sino_vietnamese_rag_v2.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
    
    file_size = output_path.stat().st_size / 1024
    
    print(f"\n{'='*60}")
    print(f"BUILD COMPLETE")
    print(f"{'='*60}")
    print(f"  Output: {output_path}")
    print(f"  Size: {file_size:.1f} KB")
    print(f"  Total patterns: {total_patterns}")
    print(f"  Categories: 9")
    print(f"  Unique hanzi: {len(existing_hanzi)}")
    print(f"\n  Category breakdown:")
    for cat_name, cat_data in v2["pattern_categories"].items():
        n = len(cat_data["patterns"])
        print(f"    {cat_name}: {n}")


if __name__ == "__main__":
    main()
