#!/usr/bin/env python3
"""
Comprehensive JP Grammar Pattern Corpus Scanner
Scans 148 EPUBs to find high-frequency grammar patterns NOT in the current RAG database.
"""
import os, re, json, zipfile, sys
from collections import Counter, defaultdict
from html.parser import HTMLParser

# === HTML text extractor ===
class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'rt'):  # skip ruby annotation
            self.skip = True
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'rt'):
            self.skip = False
    def handle_data(self, data):
        if not self.skip:
            self.result.append(data)
    def get_text(self):
        return ''.join(self.result)

def extract_text_from_epub(epub_path):
    """Extract all Japanese text from an EPUB file."""
    text_parts = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            xhtml_files = [f for f in z.namelist() 
                          if f.endswith(('.xhtml', '.html', '.htm'))
                          and 'nav' not in f.lower() 
                          and 'toc' not in f.lower()]
            for xf in sorted(xhtml_files):
                try:
                    with z.open(xf) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        parser = HTMLTextExtractor()
                        parser.feed(content)
                        text = parser.get_text().strip()
                        if text and len(text) > 50:
                            text_parts.append(text)
                except:
                    continue
    except Exception as e:
        print(f"  ⚠️ Failed to read: {os.path.basename(epub_path)}: {e}", file=sys.stderr)
    return '\n'.join(text_parts)


# === Define CANDIDATE patterns to scan for ===
CANDIDATE_PATTERNS = {
    # --- HEDGING / UNCERTAINTY (detector has rules, RAG has NOTHING) ---
    "hedging_kamoshirenai": (r'かもしれない|かもしれません|かも知れない', "かもしれない — may/might"),
    "hedging_darou": (r'だろう|でしょう|だろうか', "だろう/でしょう — probably/I suppose"),
    "hedging_rashii": (r'らしい[。、」]|っぽい[。、」]', "らしい/っぽい — seems like/apparently"),
    "hedging_mitai": (r'みたいだ|みたいな|みたいに', "みたい — like/seems"),
    "hedging_you_da": (r'ようだ[。、]|ような[。、]|ように[。、]', "ようだ — it appears/as if"),
    "hedging_to_omou": (r'と思う|と思った|と思います', "と思う — I think/feel"),
    "hedging_ki_ga_suru": (r'気がする|気がした', "気がする — I get the feeling"),

    # --- RESPONSE PARTICLES (detector has rules, RAG has NOTHING) ---
    "response_aa": (r'「ああ[、。」]|「あぁ[、。」]', "ああ — response particle"),
    "response_un": (r'「うん[、。」]|「うーん[、。」]', "うん — casual yes"),
    "response_ee": (r'「ええ[、。」]', "ええ — polite yes"),
    "response_sou": (r'「そう[だかなね]', "そうだね/そうか — I see/is that so"),
    "response_hee": (r'「へえ[ー～]?[、。」]', "へえ — surprised interest"),
    "response_oi": (r'「おい[、。」！]', "おい — hey (masculine)"),
    "response_nee": (r'「ねえ[、。」]|「ねぇ[、。」]', "ねえ — hey (attention-getting)"),
    "response_hora": (r'ほら[、。]|ほら[ね]?[、。」]', "ほら — look/see"),

    # --- NATURAL TRANSITIONS (detector has rules, RAG has NOTHING) ---
    "transition_tonikaku": (r'とにかく', "とにかく — anyway/in any case"),
    "transition_tokoro_de": (r'ところで', "ところで — by the way"),
    "transition_sate": (r'さて[、。]|さてと', "さて — well then/now"),
    "transition_soredewa": (r'それでは|それじゃ|じゃあ', "それでは/じゃあ — well then"),
    "transition_tsumari": (r'つまり', "つまり — in other words/basically"),
    "transition_dakara": (r'だから[、。]|ですから', "だから — so/that's why"),
    "transition_shikashi": (r'しかし[、。]', "しかし — however"),
    "transition_demo": (r'でも[、。]', "でも — but/however"),
    "transition_soreni": (r'それに[、。]', "それに — besides/moreover"),
    "transition_datte_reason": (r'だって[、。」]', "だって — because/but (reason)"),
    "transition_sorede": (r'それで[、。？]', "それで — and then/so"),
    "transition_sokode": (r'そこで[、。]', "そこで — thereupon"),

    # --- ONOMATOPOEIA / MIMETIC WORDS (not in detector OR RAG) ---
    "ono_dokidoki": (r'ドキドキ|どきどき|ドキッ|どきっ', "ドキドキ — heart pounding"),
    "ono_kirakira": (r'キラキラ|きらきら', "キラキラ — sparkling"),
    "ono_iraira": (r'イライラ|いらいら', "イライラ — irritated"),
    "ono_wakuwaku": (r'ワクワク|わくわく', "ワクワク — excited"),
    "ono_nikoniko": (r'ニコニコ|にこにこ|ニコッ|にこっ', "ニコニコ — smiling"),
    "ono_gakkari": (r'がっかり|ガッカリ', "がっかり — disappointed"),
    "ono_bikkuri": (r'びっくり|ビックリ', "びっくり — startled"),
    "ono_niyari": (r'ニヤリ|にやり|ニヤニヤ|にやにや|ニヤッ', "ニヤリ — smirk/grin"),
    "ono_jirojiro": (r'ジロジロ|じろじろ|ジーッ|じーっ|ジロッ', "ジロジロ — staring"),
    "ono_hakkiri": (r'はっきり|ハッキリ', "はっきり — clearly"),
    "ono_pittari": (r'ぴったり|ピッタリ', "ぴったり — perfectly"),
    "ono_sowasowa": (r'ソワソワ|そわそわ', "ソワソワ — restless"),
    "ono_mojimuji": (r'モジモジ|もじもじ', "モジモジ — fidgeting shyly"),
    "ono_boyatto": (r'ぼーっと|ボーッと|ぼうっと', "ぼーっと — spacing out"),
    "ono_uttori": (r'うっとり|ウットリ', "うっとり — entranced"),
    "ono_shikkari": (r'しっかり|シッカリ', "しっかり — firmly"),
    "ono_gussuri": (r'ぐっすり|グッスリ', "ぐっすり — sound asleep"),
    "ono_kurukuru": (r'クルクル|くるくる', "クルクル — spinning"),
    "ono_chira": (r'チラ[ッチリ]|ちら[っちり]', "チラッ — glance"),
    "ono_gu": (r'グッ[と]|ぐっ[と]', "グッと — tightly/firmly"),
    "ono_bata_bata": (r'バタバタ|ばたばた', "バタバタ — bustling"),
    "ono_potsu_potsu": (r'ポツポツ|ぽつぽつ|ポツリ|ぽつり', "ポツリ — muttering"),
    "ono_suya_suya": (r'スヤスヤ|すやすや', "スヤスヤ — sleeping peacefully"),
    "ono_mota_mota": (r'モタモタ|もたもた', "モタモタ — dawdling"),
    "ono_pero_pero": (r'ペロペロ|ぺろぺろ|ペロッ|ぺろっ', "ペロ — lick"),
    "ono_gata_gata": (r'ガタガタ|がたがた|ガタッ', "ガタ — rattling/shaking"),
    "ono_zawa_zawa": (r'ザワザワ|ざわざわ|ザワッ', "ザワ — murmuring crowd"),
    "ono_hara_hara": (r'ハラハラ|はらはら', "ハラハラ — anxious/tears falling"),
    "ono_fuwa_fuwa": (r'フワフワ|ふわふわ|フワッ', "フワ — fluffy/floating"),
    "ono_kya": (r'キャッ|きゃっ|きゃあ|キャー', "キャー — shriek/squeal"),

    # --- KEIGO / POLITENESS SHIFTS (not in RAG) ---
    "keigo_desu_masu": (r'です[。、」]|ます[。、」]|ました[。、」]|でした[。、」]', "です/ます — polite form"),
    "keigo_kudasai": (r'ください|下さい', "ください — please"),
    "keigo_gozaimasu": (r'ございます|ございました', "ございます — very polite"),
    "keigo_itadaku": (r'いただ[きくけ]|頂[きくけ]', "いただく — humble receive"),
    "keigo_ossharu": (r'おっしゃ[いるれっ]', "おっしゃる — honorific say"),
    "keigo_irassharu": (r'いらっしゃ[いるれっ]', "いらっしゃる — honorific be/go"),

    # --- INNER MONOLOGUE / NARRATION (common in LN, not in RAG) ---
    "mono_omowazu": (r'思わず', "思わず — involuntarily"),
    "mono_tsui": (r'つい[、。]|ついつい', "つい — inadvertently"),
    "mono_futo": (r'ふと[、。]|ふっと[、。]', "ふと — suddenly (thought)"),
    "mono_naze_ka": (r'なぜか|何故か', "なぜか — for some reason"),
    "mono_douyara": (r'どうやら', "どうやら — it seems"),
    "mono_masani": (r'まさに', "まさに — exactly/precisely"),
    "mono_sore_demo": (r'それでも', "それでも — even so/still"),
    "mono_soushite": (r'そうして|そして', "そして — and then"),
    "mono_ikanimo": (r'いかにも', "いかにも — indeed/truly"),
    "mono_doushitemo": (r'どうしても', "どうしても — no matter what"),

    # --- SENTENCE-ENDING NUANCES (expand what RAG has) ---
    "ending_kana": (r'かな[。」]|かなぁ[。」]', "かな — I wonder"),
    "ending_kashira": (r'かしら[。」]', "かしら — I wonder (feminine)"),
    "ending_noda": (r'のだ[。」]|んだ[。」]', "のだ/んだ — explanatory"),
    "ending_desho": (r'でしょ[。？」う]', "でしょ — right?/probably"),
    "ending_tte": (r'って[。」]|ってば[。」！]', "って/ってば — I said/telling you"),
    "ending_mono": (r'もの[。」]|もん[。」]', "もの/もん — because (childish)"),
    "ending_nano": (r'なの[。？」]', "なの — is it?/it is (soft)"),
    "ending_sa": (r'さ[。」]', "さ — casual masculine assertion"),
    "ending_wa_yo": (r'わよ[。」！]|のよ[。」！]', "わよ/のよ — feminine emphasis"),
    "ending_zo": (r'ぞ[。」！]', "ぞ — masculine emphasis"),
    "ending_na_excl": (r'な[。」！]', "な — exclamatory/reflective"),

    # --- CAUSATIVE / GIVING-RECEIVING (complex grammar, not in RAG) ---
    "causative_saseru": (r'させ[るたてら]', "させる — make/let do"),
    "receiving_morau": (r'もらう|もらった|もらえ[るば]', "もらう — get someone to"),
    "receiving_kureru": (r'くれる|くれた|くれない', "くれる — do for me (favor)"),
    "receiving_ageru": (r'てあげる|てあげた', "てあげる — do for someone"),

    # --- QUOTATION / HEARSAY ---
    "quote_tte_iu": (r'って言[うった]|と言[うった]', "って言う — said/called"),
    "quote_to_iu": (r'という[のこもは]', "という — so-called/the thing called"),
    "quote_sou_da_hearsay": (r'だそうだ|だそうです|とのことだ', "そうだ — I heard/reportedly"),
    "quote_toka_iu": (r'とか[言い]', "とか言う — something like"),

    # --- DESIRE / INTENTION ---
    "desire_tai": (r'たい[。、」]|たかった[。、」]|たくな[いか]', "たい — want to"),
    "desire_hoshii": (r'ほしい|欲しい|ほしかった', "ほしい — want"),
    "desire_tsumori": (r'つもり[だはでな]', "つもり — intend to"),
    "desire_you_to_suru": (r'ようとし[たて]|ようとする', "ようとする — try to"),
    "desire_ki_ni_naru": (r'気になる|気になった|気になって', "気になる — bothered by/curious"),

    # --- CONCESSION / CONTRAST (partially covered) ---
    "concession_noni": (r'のに[。、」]', "のに — even though/despite"),
    "concession_kuse_ni": (r'くせに|癖に', "くせに — even though (critical)"),
    "concession_toshitemo": (r'としても|にしても', "にしても — even if/granting that"),
    "concession_nagara_mo": (r'ながらも', "ながらも — while/although"),

    # --- TOPIC / STRUCTURE PARTICLES ---
    "structure_koso": (r'こそ[、。がは]', "こそ — precisely/it is X that"),
    "structure_bakari": (r'ばかり[、。だで]|ばっかり', "ばかり — only/nothing but"),
    "structure_shika_nai": (r'しかない|しかなかった', "しかない — no choice but"),
    "structure_wake": (r'わけ[がにではも]|わけない', "わけ — reason/it means"),
    "structure_hazu": (r'はず[がだでなの]', "はず — should be/supposed to"),
    "structure_tokoro": (r'ところだ[。っ]|ところだった', "ところだ — just about to/was about to"),

    # --- LIGHT NOVEL SPECIFIC ---
    "ln_muri": (r'無理[だでは。！]|ムリ', "無理 — impossible/can't"),
    "ln_uso": (r'嘘[だで。！？]|ウソ', "嘘 — no way!/lie"),
    "ln_yabai": (r'ヤバ[いイ]|やばい|ヤバ[。！]', "ヤバい — oh no/amazing"),
    "ln_sugoi": (r'すごい|凄い|スゴイ|すげえ|すげぇ', "すごい — amazing"),
    "ln_kawaii": (r'可愛い|かわいい|カワイイ', "可愛い — cute"),
    "ln_hazukashii": (r'恥ずかし[いく]|はずかし[いく]', "恥ずかしい — embarrassing"),
    "ln_mendokusai": (r'面倒[くだ]|めんどう|めんどくさい', "面倒 — troublesome"),
    "ln_sonna": (r'そんな[、。こ事！]', "そんな — such a/that kind of"),
    "ln_konna": (r'こんな[、。こ事！]', "こんな — this kind of"),
    "ln_doushiyou": (r'どうしよう|どうしたらいい', "どうしよう — what should I do"),
    "ln_dame": (r'ダメ[だで。！]|だめ[だで。！]|駄目', "ダメ — no good/not allowed"),
    "ln_honto": (r'本当[にだで]|ほんと[うにだで]|ホント', "本当 — really/truly"),
    "ln_zenzen": (r'全然[、。]', "全然 — not at all/totally"),
    "ln_suki": (r'好き[だでな。！」]', "好き — like/love"),
    "ln_kirai": (r'嫌い[だでな。！」]|きらい', "嫌い — dislike/hate"),
    "ln_ureshii": (r'嬉し[いく]|うれし[いく]', "嬉しい — happy/glad"),
    "ln_kanashii": (r'悲し[いく]|かなし[いく]', "悲しい — sad"),
    "ln_kowai": (r'怖[いく]|こわ[いく]', "怖い — scary/afraid"),
    "ln_samishii": (r'寂し[いく]|さみし[いく]|さびし[いく]', "寂しい — lonely"),
    "ln_tanoshii": (r'楽し[いく]|たのし[いく]', "楽しい — fun/enjoyable"),
}

def main():
    input_dir = '/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/INPUT'
    epubs = sorted([os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith('.epub')])
    
    print(f"Scanning for {len(CANDIDATE_PATTERNS)} candidate patterns across {len(epubs)} EPUBs...")
    print(f"This may take a few minutes...\n")
    
    pattern_counts = Counter()
    pattern_examples = defaultdict(list)
    total_lines = 0
    total_chars = 0
    epubs_processed = 0
    
    for i, epub_path in enumerate(epubs):
        if (i+1) % 20 == 0:
            print(f"  Processing {i+1}/{len(epubs)}...")
        try:
            text = extract_text_from_epub(epub_path)
            if not text:
                continue
            epubs_processed += 1
            lines = text.split('\n')
            total_lines += len(lines)
            total_chars += len(text)
            
            for line in lines:
                stripped = line.strip()
                if not stripped or len(stripped) < 5:
                    continue
                for pat_name, (regex, desc) in CANDIDATE_PATTERNS.items():
                    try:
                        matches = list(re.finditer(regex, stripped))
                        if matches:
                            pattern_counts[pat_name] += len(matches)
                            if len(pattern_examples[pat_name]) < 3:
                                pattern_examples[pat_name].append(stripped[:150])
                    except:
                        continue
        except:
            continue
    
    print(f"\n{'='*90}")
    print(f"✅ Processed {epubs_processed}/{len(epubs)} EPUBs")
    print(f"📊 Total lines: {total_lines:,}")
    print(f"📊 Total chars: {total_chars:,}")
    print(f"{'='*90}")
    
    # === Group by category ===
    categories = defaultdict(list)
    for pat_name, count in pattern_counts.items():
        if pat_name.startswith('ln_'):
            category = 'LN_SPECIFIC'
        elif pat_name.startswith('ono_'):
            category = 'ONOMATOPOEIA'
        elif pat_name.startswith('mono_'):
            category = 'INNER_MONOLOGUE'
        elif pat_name.startswith('ending_'):
            category = 'SENTENCE_ENDINGS_NEW'
        elif pat_name.startswith('keigo_'):
            category = 'KEIGO'
        elif pat_name.startswith('quote_'):
            category = 'QUOTATION_HEARSAY'
        elif pat_name.startswith('hedging_'):
            category = 'HEDGING'
        elif pat_name.startswith('response_'):
            category = 'RESPONSE_PARTICLES'
        elif pat_name.startswith('transition_'):
            category = 'NATURAL_TRANSITIONS'
        elif pat_name.startswith('causative_') or pat_name.startswith('receiving_'):
            category = 'GIVING_RECEIVING'
        elif pat_name.startswith('desire_'):
            category = 'DESIRE_INTENTION'
        elif pat_name.startswith('concession_'):
            category = 'CONCESSION'
        elif pat_name.startswith('structure_'):
            category = 'STRUCTURE_PARTICLES'
        else:
            category = 'OTHER'
        categories[category].append((pat_name, count, CANDIDATE_PATTERNS[pat_name][1]))
    
    # Print results
    print(f"\n{'Category':<25} {'Pattern':<40} {'Freq':>8}  Description")
    print(f"{'-'*25} {'-'*40} {'-'*8}  {'-'*30}")
    
    grand_total = sum(pattern_counts.values())
    
    for cat in sorted(categories.keys(), key=lambda c: sum(x[1] for x in categories[c]), reverse=True):
        cat_total = sum(x[1] for x in categories[cat])
        pct = (cat_total / grand_total * 100) if grand_total else 0
        print(f"\n🔵 {cat} (Total: {cat_total:,} | {pct:.1f}%)")
        for pat_name, count, desc in sorted(categories[cat], key=lambda x: x[1], reverse=True):
            if count > 0:
                print(f"  {'':.<23} {pat_name:<40} {count:>8,}  {desc}")
    
    # === Print examples for top patterns ===
    print(f"\n{'='*90}")
    print(f"EXAMPLE LINES FOR TOP-30 PATTERNS")
    print(f"{'='*90}")
    
    top30 = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:30]
    for pat_name, count in top30:
        desc = CANDIDATE_PATTERNS[pat_name][1]
        print(f"\n📌 {pat_name} ({count:,} hits) — {desc}")
        for ex in pattern_examples.get(pat_name, []):
            print(f"   → {ex}")
    
    # === Save full results to JSON ===
    output = {
        "scan_stats": {
            "epubs_processed": epubs_processed,
            "total_lines": total_lines,
            "total_chars": total_chars,
            "patterns_scanned": len(CANDIDATE_PATTERNS)
        },
        "pattern_frequencies": dict(sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)),
        "pattern_examples": {k: v for k, v in pattern_examples.items()},
        "categories": {cat: {
            "total": sum(x[1] for x in pats),
            "patterns": {p[0]: {"count": p[1], "desc": p[2]} for p in pats}
        } for cat, pats in categories.items()}
    }
    
    out_path = '/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/scripts/corpus_scan_results.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Full results saved to: {out_path}")


if __name__ == '__main__':
    main()
