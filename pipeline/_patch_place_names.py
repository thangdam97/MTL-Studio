#!/usr/bin/env python3
"""Inject place names + missing character names into both Vanadis manifests."""
import json

# ─── COMPREHENSIVE GLOSSARY (Vanadis Canon) ───
PLACE_NAMES = {
    # Countries
    "ザクスタン": "Sachstein",
    "アスヴァール": "Asvarre",
    # Zhcted Duchies
    "レグニーツァ": "Legnica",
    "ブレスト": "Brest",
    "ポリーシャ": "Polesia",
    "ルヴーシュ": "Lebus",
    "オステローデ": "Osterode",
    # Brune places
    "テリトアール": "Territoire",
    "ネメタクム": "Nemetacum",
    "アルテシウム": "Artesium",
    "ルテティア": "Lutetia",
    "ディナント": "Dinant",
    "オーランジュ": "Orangey",
    "ニース": "Nice",
    # V2-specific places
    "モーシア": "Molsheim",
    "リュベロン": "Luberon",
    "オルメア": "Ormea",
    "モントーバン": "Montauban",
    "シャトール": "Chatol",
    "カルヴァドス": "Calvados",
    "ヴァタン": "Vatan",
    # Mythology / Banners / Weapons
    "フレスベルグ": "Hraesvelgr",
    "デュランダル": "Durandal",
    "ペルクナス": "Perkunas",
    "ジルニトラ": "Zirnitra",
    "バヤール": "Bayard",
}

V2_CHARS = {
    "ボードワン": "Baudouin",
    "クレイシュ": "Kreisch",
    "ジェラール": "Gerard",
    "ローダント": "Rodant",
    "オリビエ": "Olivier",
    "ロラン": "Roland",
    "スティード": "Steed",
    "カシム": "Kasim",
    "エミール": "Emile",
    "フェリックス": "Felix",
    "アーロン": "Aaron",
    "アニエス": "Agnes",
    "ヴィクトール": "Viktor",
    "オーギュスト": "Auguste",
    "ドレカヴァク": "Drekavac",
    "ヴォジャノーイ": "Vodyanoy",
    "エリザヴェータ": "Elizavetta",
    "グレアスト": "Greast",
    "ファーロン": "Faron",
    "オージェ": "Augre",
    "ソフィー": "Sofie",
    "レグナス": "Regnas",
    "ヴォルン": "Vorn",
    "アラム": "Aram",
    "オルガ": "Olga",
    "ボロスロー": "Boroislav",
    "シルヴミーティオ": "Silver Meteor",
    "ソーニエ": "Saunier",
    "ソーニエール": "Sauniere",
    "メレヴィル": "Mereville",
}

BASE_CHARS = {
    "ブリューヌ": "Brune",
    "ジスタート": "Zhcted",
    "アルサス": "Alsace",
    "ライトメリッツ": "Leitmeritz",
    "オルミュッツ": "Olmutz",
    "セレスタ": "Celesta",
    "ムオジネル": "Muozinel",
    "エレオノーラ": "Eleonora",
    "ティッタ": "Titta",
    "レギン": "Regin",
    "ソフィーヤ": "Sofya",
    "アレクサンドラ": "Alexandra",
    "ルリエ": "Lourie",
    "テナルディエ": "Thenardier",
    "ガヌロン": "Ganelon",
    "ヴォージュ": "Vosges",
    "アリファル": "Arifal",
    "ラヴィアス": "Lavias",
    "ヴァレンティナ": "Valentina",
    "リュドミラ": "Ludmila",
    "ティグル": "Tigre",
    "ティグルヴルムド": "Tigrevurmud",
    "バートラン": "Bertrand",
    "マスハス": "Mashas",
    "ウルス": "Urs",
    "リムアリーシャ": "Limalisha",
    "ルーリック": "Rurick",
}

# V1 junk entries to remove
V1_JUNK = {"技量", "捕虜", "弓幹", "真似", "蝙蝠", "覚醒", "後輪", "刺青", "見做", "凛々", "楚々"}


def patch_manifest(path, is_v1=False):
    with open(path, "r", encoding="utf-8") as f:
        m = json.load(f)

    cn = m.setdefault("metadata_en", {}).setdefault("character_names", {})
    before = len(cn)
    removed = 0

    if is_v1:
        # Remove junk auto-generated entries
        for k in list(cn.keys()):
            if k in V1_JUNK:
                del cn[k]
                removed += 1
                print(f"  Removed junk: {k}")
        # Fix wrong entries
        if cn.get("リムアリーシャ") == "Limarisha":
            cn["リムアリーシャ"] = "Limalisha"
            print("  Fixed: Limarisha -> Limalisha")
        if cn.get("オージェ") == "Auge":
            cn["オージェ"] = "Augre"
            print("  Fixed: Auge -> Augre")

    added = 0
    # Add place names
    for jp, en in PLACE_NAMES.items():
        if jp not in cn:
            cn[jp] = en
            added += 1

    # Add character names
    for jp, en in V2_CHARS.items():
        if jp not in cn:
            cn[jp] = en
            added += 1

    for jp, en in BASE_CHARS.items():
        if jp not in cn:
            cn[jp] = en
            added += 1

    after = len(cn)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    print(f"  {before} -> {after} entries (+{added} added, -{removed} removed)")
    return after


print("=== V2 (15c4) ===")
v2_path = "WORK/魔弾の王と戦姫 第 2 章―出逢い―_20260208_15c4/manifest.json"
n2 = patch_manifest(v2_path, is_v1=False)

print("\n=== V1 (25d9) ===")
v1_path = "WORK/魔弾の王と戦姫 第1章―出逢い―_20260208_25d9/manifest.json"
n1 = patch_manifest(v1_path, is_v1=True)

print(f"\nDone. V2={n2} entries, V1={n1} entries")
