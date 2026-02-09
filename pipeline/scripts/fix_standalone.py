#!/usr/bin/env python3
"""Manually add 2 standalone edge cases to bible system:
1. Add 0fa9 (迷子 vol.4) to existing 迷子 bible + populate characters
2. Create new 氷姫 bible from 1d46 + 1ab4
"""
import json
from pathlib import Path
from datetime import datetime, timezone

BIBLES = Path(__file__).resolve().parent.parent / "bibles"
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ============================================================
# 1. Update 迷子 bible: add 0fa9, populate characters
# ============================================================
maigo_path = BIBLES / "迷子になっていた幼女を助けたらお隣に住む美少女留学生が家に遊びに来るようになった件について.json"
with open(maigo_path, encoding="utf-8") as f:
    maigo = json.load(f)

maigo["series_title"]["en"] = "I Rescued a Lost Little Girl, and Now the Beautiful Exchange Student Next Door Won't Stop Visiting!"

maigo["volumes_registered"] = [
    {"volume_id": "0b24", "title": "I Rescued a Lost Little Girl, and Now the Beautiful Exchange Student Next Door Won't Stop Visiting!", "index": 1},
    {"volume_id": "0fa9", "title": "I Rescued a Lost Little Girl, and Now the Beautiful Exchange Student Next Door Won't Stop Visiting! 4", "index": 4},
    {"volume_id": "0a51", "title": "迷子になっていた幼女を助けたら、お隣に住む美少女留学生が家に遊びに来るようになった件について 5", "index": 5},
]

maigo["characters"] = {
    "青柳明人": {"canonical_en": "Aoyagi Akihito", "category": "protagonist"},
    "シャーロット・ベネット": {"canonical_en": "Charlotte Bennett"},
    "エマ・ベネット": {"canonical_en": "Emma Bennett"},
    "西園寺彰": {"canonical_en": "Saionji Akira"},
    "花澤美優": {"canonical_en": "Hanazawa Miyu"},
    "東雲": {"canonical_en": "Shinonome"},
    "クレア": {"canonical_en": "Claire"},
}

maigo["world_setting"]["exceptions"] = [
    {"character_jp": "シャーロット・ベネット", "character_en": "Charlotte Bennett", "reason": "Foreign character (Western)", "honorifics_override": "retain", "name_order_override": "given_family"},
    {"character_jp": "エマ・ベネット", "character_en": "Emma Bennett", "reason": "Foreign character (Western)", "honorifics_override": "retain", "name_order_override": "given_family"},
    {"character_jp": "クレア", "character_en": "Claire", "reason": "Foreign character (Western)", "honorifics_override": "retain", "name_order_override": "given_family"},
]

maigo["last_updated"] = now
with open(maigo_path, "w", encoding="utf-8") as f:
    json.dump(maigo, f, ensure_ascii=False, indent=2)
print(f"✅ 迷子 bible updated: {len(maigo['volumes_registered'])} volumes, {len(maigo['characters'])} characters")

# ============================================================
# 2. Create 他校の氷姫 bible from 1d46 + 1ab4
# ============================================================
koori_id = "他校の氷姫を助けたらお友達から始める事になりました"
koori = {
    "bible_version": "1.0",
    "series_id": koori_id,
    "series_title": {
        "ja": "他校の氷姫を助けたら、お友達から始める事になりました",
        "en": "After I Saved the Ice Princess of Another School, We Became Friends",
        "romaji": "",
    },
    "last_updated": now,
    "volumes_registered": [
        {"volume_id": "1d46", "title": "After I Saved the Ice Princess of Another School, We Became Friends", "index": 1},
        {"volume_id": "1ab4", "title": "After I Saved the Ice Princess of Another School, We Became Friends 2", "index": 2},
    ],
    "characters": {
        "海以蒼太": {"canonical_en": "Minori Souta", "category": "protagonist"},
        "蒼太": {"canonical_en": "Souta", "notes": "Short name for 海以蒼太"},
        "海以": {"canonical_en": "Minori", "notes": "Surname for 海以蒼太"},
        "東雲凪": {"canonical_en": "Shinonome Nagi", "category": "heroine"},
        "東雲": {"canonical_en": "Shinonome", "notes": "Surname / short ref for Nagi"},
        "巻坂瑛二": {"canonical_en": "Makizaka Eiji"},
        "瑛二": {"canonical_en": "Eiji", "notes": "Short name for 巻坂瑛二"},
        "巻坂": {"canonical_en": "Makizaka", "notes": "Surname for 巻坂瑛二"},
        "西沢霧香": {"canonical_en": "Nishizawa Kirika"},
        "霧香": {"canonical_en": "Kirika", "notes": "Given name for 西沢霧香"},
        "西沢": {"canonical_en": "Nishizawa", "notes": "Surname for 西沢霧香"},
        "羽山光": {"canonical_en": "Hayama Hikaru"},
        "羽山": {"canonical_en": "Hayama", "notes": "Surname for 羽山光"},
        "須坂翔子": {"canonical_en": "Suzaka Shouko"},
        "須坂": {"canonical_en": "Suzaka", "notes": "Surname for 須坂翔子"},
        "南川陽斗": {"canonical_en": "Minamikawa Youto"},
        "南川": {"canonical_en": "Minamikawa", "notes": "Surname for 南川陽斗"},
        "村田": {"canonical_en": "Murata"},
        "皐月陽龍": {"canonical_en": "Satsuki Hiryu"},
        "東雲宗一郎": {"canonical_en": "Shinonome Souichirou", "introduced_in": 2},
        "宗一郎": {"canonical_en": "Souichirou", "notes": "Short name for 東雲宗一郎"},
        "東雲千恵": {"canonical_en": "Shinonome Chie", "introduced_in": 2},
        "千恵": {"canonical_en": "Chie", "notes": "Short name for 東雲千恵"},
        "新谷静子": {"canonical_en": "Araya Shizuko", "introduced_in": 2},
    },
    "geography": {"countries": {}, "regions": {}, "cities": {}},
    "weapons_artifacts": {},
    "organizations": {},
    "cultural_terms": {},
    "mythology": {},
    "world_setting": {
        "type": "modern_japan",
        "label": "Contemporary Japanese Setting",
        "honorifics": {"mode": "retain", "policy": "Keep all JP honorifics (-san, -kun, -chan, -sama, -senpai, -sensei)."},
        "name_order": {"default": "family_given", "policy": "Japanese surname-first order for Japanese characters."},
        "exceptions": [],
    },
    "translation_rules": {"style": "Natural English prose matching the genre tone."},
}

koori_path = BIBLES / f"{koori_id}.json"
with open(koori_path, "w", encoding="utf-8") as f:
    json.dump(koori, f, ensure_ascii=False, indent=2)
print(f"✅ 氷姫 bible created: {len(koori['volumes_registered'])} volumes, {len(koori['characters'])} characters")

# ============================================================
# 3. Update index.json
# ============================================================
index_path = BIBLES / "index.json"
with open(index_path, encoding="utf-8") as f:
    index = json.load(f)

# Update 迷子 entry
maigo_key = "迷子になっていた幼女を助けたらお隣に住む美少女留学生が家に遊びに来るようになった件について"
index["series"][maigo_key]["volumes"] = ["0b24", "0fa9", "0a51"]
index["series"][maigo_key]["entry_count"] = len(maigo["characters"])
en_pattern = "I Rescued a Lost Little Girl, and Now the Beautiful Exchange Student Next Door Won't Stop Visiting!"
if en_pattern not in index["series"][maigo_key]["match_patterns"]:
    index["series"][maigo_key]["match_patterns"].append(en_pattern)
index["series"][maigo_key]["last_updated"] = now

# Add 氷姫 entry
index["series"][koori_id] = {
    "bible_file": f"{koori_id}.json",
    "match_patterns": [
        "他校の氷姫を助けたら、お友達から始める事になりました",
        "After I Saved the Ice Princess of Another School, We Became Friends",
        "After I Saved the Ice Princess From Another School",
    ],
    "volumes": ["1d46", "1ab4"],
    "entry_count": len(koori["characters"]),
    "last_updated": now,
}

index["last_updated"] = now
with open(index_path, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"✅ index.json updated: {len(index['series'])} total series")
