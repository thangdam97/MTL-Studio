#!/usr/bin/env python3
"""
VN Corpus Pattern Scanner
=========================
Scans 103 VN-translated chapters + 148 JP EPUBs to extract:
1. JP source pattern frequencies (per detector category)
2. Real VN translation examples for each pattern
3. VN-specific anti-AI-ism detection
4. VN particle density statistics

Output: corpus_scan_results_vn.json
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter
import zipfile
from html.parser import HTMLParser

# ============================================================================
# HTML STRIPPER (for EPUB extraction)
# ============================================================================

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'head', 'rt', 'rp'}
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self._skip = True
        if tag in ('br', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'li'):
            self.text_parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.text_parts.append(data)

    def get_text(self):
        return ''.join(self.text_parts)


def strip_html(html_text):
    stripper = HTMLStripper()
    stripper.feed(html_text)
    return stripper.get_text()


# ============================================================================
# JP SOURCE PATTERN DEFINITIONS (matching grammar_pattern_detector.py)
# ============================================================================

JP_PATTERNS = {
    # --- 16 categories from grammar_pattern_detector.py ---
    "contrastive_comparison": [
        (r"けど|けれど|だけど", "kedo_contrast"),
        (r"が、|だが", "ga_contrast"),
        (r"でも", "demo_contrast"),
        (r"も", "mo_also"),
        (r"のに", "noni_despite"),
    ],
    "dismissive_acknowledgment": [
        (r"はともかく|はさておき", "tomo_kaku"),
        (r"はいいとして", "wa_ii_toshite"),
        (r"は置いておいて", "wa_oite"),
    ],
    "intensifiers": [
        (r"結構|けっこう", "kekkou"),
        (r"かなり", "kanari"),
        (r"めちゃ|めっちゃ", "mecha"),
        (r"超|ちょう", "chou"),
        (r"すごく|すごい|凄い", "sugoku"),
    ],
    "hedging": [
        (r"だろう|でしょう", "darou"),
        (r"と思う|と思った", "to_omou"),
        (r"ようだ|ような", "you_da"),
        (r"みたい", "mitai"),
        (r"かもしれない|かも", "kamoshirenai"),
        (r"らしい", "rashii"),
        (r"気がする", "ki_ga_suru"),
    ],
    "response_particles": [
        (r"そう(?:だね|ですね)?", "sou_response"),
        (r"うん", "un_response"),
        (r"ほら", "hora"),
        (r"ああ|あぁ", "aa_response"),
        (r"ええ", "ee_response"),
        (r"ねえ|ねぇ", "nee_response"),
        (r"おい", "oi_response"),
        (r"へえ|へぇ", "hee_response"),
    ],
    "natural_transitions": [
        (r"だから", "dakara"),
        (r"でも", "demo_transition"),
        (r"ところで", "tokoro_de"),
        (r"だって", "datte"),
        (r"しかし", "shikashi"),
        (r"つまり", "tsumari"),
        (r"とにかく", "tonikaku"),
        (r"それに", "soreni"),
        (r"さて", "sate"),
        (r"そこで", "sokode"),
        (r"それで", "sorede"),
    ],
    "sentence_endings": [
        (r"な[ぁあ]?(?:[。！？」]|$)", "ending_na"),
        (r"のだ|んだ|んです", "ending_noda"),
        (r"でしょ(?:う)?(?:[。！？」]|$)", "ending_desho"),
        (r"って(?:[。！？」]|$)", "ending_tte"),
        (r"ぞ(?:[。！？」]|$)", "ending_zo"),
        (r"さ(?:[。！？」]|$)", "ending_sa"),
        (r"かな(?:[。！？」]|$)", "ending_kana"),
        (r"かしら(?:[。！？」]|$)", "ending_kashira"),
        (r"わよ(?:[。！？」]|$)", "ending_wa_yo"),
        (r"もの?(?:[。！？」]|$)", "ending_mono"),
        (r"なの(?:[。！？」]|$)", "ending_nano"),
    ],
    "emotional_nuance": [
        (r"ちょっと", "chotto"),
        (r"なんだか|何だか|なんか", "nandaka"),
        (r"やっぱり|やはり|やっぱ", "yappari"),
        (r"まさか", "masaka"),
        (r"さすが|流石", "sasuga"),
        (r"まあ|まぁ", "maa"),
        (r"別に", "betsu_ni"),
        (r"確かに|たしかに", "tashika_ni"),
        (r"もしかして|ひょっとして", "moshikashite"),
    ],
    "action_emphasis": [
        (r"てしまった|ちゃった", "te_shimatta"),
        (r"ている|てる", "te_iru"),
        (r"てみる|てみた", "te_miru"),
        (r"ておく|とく", "te_oku"),
        (r"てくる|てきた", "te_kuru"),
        (r"ていく|てく", "te_iku"),
        (r"てある", "te_aru"),
        (r"始める|出す", "hajimeru_dasu"),
    ],
    "onomatopoeia": [
        (r"ドキドキ|どきどき", "dokidoki"),
        (r"ニヤリ|にやり|ニヤ", "niyari"),
        (r"チラ|ちら", "chira"),
        (r"はっきり", "hakkiri"),
        (r"しっかり", "shikkari"),
        (r"キラキラ|きらきら", "kirakira"),
        (r"ワクワク|わくわく", "wakuwaku"),
        (r"ソワソワ|そわそわ", "sowasowa"),
        (r"モジモジ|もじもじ", "mojimuji"),
        (r"ガッカリ|がっかり", "gakkari"),
        (r"イライラ|いらいら", "iraira"),
        (r"フワフワ|ふわふわ", "fuwafuwa"),
        (r"ボーッ|ぼーっ|ぼやっ", "boyatto"),
        (r"ピッタリ|ぴったり", "pittari"),
        (r"グッスリ|ぐっすり", "gussuri"),
    ],
    "giving_receiving": [
        (r"くれる|くれた|くれない", "kureru"),
        (r"もらう|もらった|もらえ", "morau"),
        (r"あげる|あげた", "ageru"),
        (r"いただく|いただい", "itadaku"),
    ],
    "inner_monologue": [
        (r"思わず", "omowazu"),
        (r"ふと", "futo"),
        (r"なぜか|何故か", "naze_ka"),
        (r"どうやら", "douyara"),
        (r"そして", "soushite"),
        (r"それでも", "sore_demo"),
        (r"どうしても", "doushitemo"),
        (r"まさに", "masani"),
        (r"つい", "tsui"),
        (r"いかにも", "ikanimo"),
    ],
    "quotation_hearsay": [
        (r"って言う|っていう", "tte_iu"),
        (r"という|と言う", "to_iu"),
        (r"とかいう|とか言う", "toka_iu"),
        (r"そうだ(?!ね)", "sou_da_hearsay"),
    ],
    "desire_intention": [
        (r"たい(?:[。！？」\s]|$)", "tai_want"),
        (r"欲しい|ほしい", "hoshii"),
        (r"つもり", "tsumori"),
        (r"ようとする", "you_to_suru"),
        (r"気になる", "ki_ni_naru"),
    ],
    "structure_particles": [
        (r"わけ(?:だ|が|で|に|の|は|じゃ|ない)", "wake"),
        (r"はず(?:だ|が|の|な)", "hazu"),
        (r"こそ", "koso"),
        (r"しかない|ほかない", "shika_nai"),
        (r"ばかり|ばっかり", "bakari"),
        (r"ところ(?:だ|で|が|に)", "tokoro"),
    ],
    "concession_contrast": [
        (r"のに", "noni_concession"),
        (r"としても|にしても", "toshitemo"),
        (r"ながらも|ながら", "nagara_mo"),
        (r"くせに|くせして", "kuse_ni"),
    ],
    # --- VN-SPECIFIC: additional patterns ---
    "keigo_register": [
        (r"です(?:が|か|ね|よ)?", "desu"),
        (r"ます(?:が|か|ね|よ)?", "masu"),
        (r"ください|下さい", "kudasai"),
        (r"いただ[くき]", "itadaku_keigo"),
        (r"ございます", "gozaimasu"),
        (r"いらっしゃ[るい]", "irassharu"),
        (r"おっしゃ[るい]", "ossharu"),
    ],
    "ln_specific_expressions": [
        (r"本当|ほんと", "honto"),
        (r"好き(?:だ|な|に|で)", "suki"),
        (r"そんな", "sonna"),
        (r"可愛い|かわいい", "kawaii"),
        (r"嬉しい|うれしい", "ureshii"),
        (r"ダメ|だめ|駄目", "dame"),
        (r"すごい|凄い", "sugoi"),
        (r"恥ずかしい", "hazukashii"),
        (r"怖い|こわい", "kowai"),
        (r"楽しい|たのしい", "tanoshii"),
        (r"寂しい|さみしい|さびしい", "samishii"),
        (r"やばい|ヤバい", "yabai"),
        (r"嫌い|きらい", "kirai"),
        (r"面倒|めんどう|めんどくさい", "mendokusai"),
        (r"どうしよう", "doushiyou"),
        (r"無理|むり", "muri"),
        (r"嘘|うそ", "uso"),
        (r"こんな", "konna"),
        (r"全然", "zenzen"),
    ],
}

# ============================================================================
# VN ANTI-AI-ISM DETECTION PATTERNS
# ============================================================================

VN_AI_ISM_PATTERNS = {
    "mot_cam_giac": (r"(?:một )?cảm giác (?:như |là |bất an|nhẹ nhõm|căng thẳng|hoài niệm|tội lỗi)", "một cảm giác [X]"),
    "mot_cach": (r"một cách [a-zA-ZÀ-ỹ]+", "một cách [adj]"),
    "viec_subject": (r"(?:^|\. )Việc [a-zA-ZÀ-ỹ]+", "Việc [noun] as subject"),
    "su_nominalization": (r"(?:^|\. )Sự [a-zA-ZÀ-ỹ]+", "Sự [noun] nominalization"),
    "dieu_overuse": (r"(?:^|\. )Điều (?:đó|này|ấy)", "Điều [demonstrative]"),
    "khong_the_phu_nhan": (r"không thể phủ nhận", "không thể phủ nhận"),
    "nhan_ra_rang": (r"nhận ra rằng", "nhận ra rằng"),
    "tran_ngap": (r"tràn ngập", "tràn ngập"),
    "bao_phu": (r"bao phủ", "bao phủ"),
    "day_ap": (r"đầy ắp", "đầy ắp"),
}

# ============================================================================
# VN PARTICLE INVENTORY
# ============================================================================

VN_PARTICLES = {
    "conversational": ["mà", "rồi", "thì", "nên", "vì", "với lại", "cho nên", "thế nên"],
    "emphasis": ["chứ", "đấy", "nhé", "nha", "đâu", "cơ", "kia", "mà"],
    "question": ["à", "ạ", "hả", "nhỉ", "chứ", "sao"],
    "trailing": ["thôi", "đi", "nào", "vậy", "thế", "đó"],
    "interjection": ["ôi", "trời", "chà", "ủa", "hử", "ể", "á", "ơ"],
    "hedging": ["chắc", "có lẽ", "hình như", "dường như", "chắc hẳn"],
    "intensifier": ["quá", "lắm", "thật", "cực kỳ", "vô cùng", "siêu"],
}


# ============================================================================
# SCANNER FUNCTIONS
# ============================================================================

def extract_epub_text(epub_path):
    """Extract text from EPUB file."""
    lines = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            for name in sorted(z.namelist()):
                if name.endswith(('.xhtml', '.html', '.htm')):
                    try:
                        html = z.read(name).decode('utf-8', errors='replace')
                        text = strip_html(html)
                        for line in text.split('\n'):
                            line = line.strip()
                            if line and len(line) > 2:
                                lines.append(line)
                    except Exception:
                        continue
    except Exception as e:
        print(f"  ⚠ Error reading {epub_path}: {e}")
    return lines


def scan_jp_patterns(lines):
    """Scan JP text for pattern frequencies."""
    results = defaultdict(lambda: defaultdict(int))
    examples = defaultdict(lambda: defaultdict(list))
    
    for line in lines:
        for category, patterns in JP_PATTERNS.items():
            for regex, pattern_id in patterns:
                if re.search(regex, line):
                    results[category][pattern_id] += 1
                    if len(examples[category][pattern_id]) < 3:
                        examples[category][pattern_id].append(line[:200])
    
    return results, examples


def scan_vn_patterns(lines):
    """Scan VN text for particle density and AI-isms."""
    total_words = 0
    particle_counts = defaultdict(int)
    ai_ism_counts = defaultdict(int)
    ai_ism_examples = defaultdict(list)
    
    for line in lines:
        words = line.split()
        total_words += len(words)
        
        # Count particles
        for category, particles in VN_PARTICLES.items():
            for particle in particles:
                count = len(re.findall(r'\b' + re.escape(particle) + r'\b', line, re.IGNORECASE))
                particle_counts[f"{category}:{particle}"] += count
        
        # Detect AI-isms
        for ai_id, (regex, desc) in VN_AI_ISM_PATTERNS.items():
            matches = re.findall(regex, line, re.IGNORECASE)
            if matches:
                ai_ism_counts[ai_id] += len(matches)
                if len(ai_ism_examples[ai_id]) < 3:
                    ai_ism_examples[ai_id].append(line[:200])
    
    return {
        "total_words": total_words,
        "particle_counts": dict(particle_counts),
        "ai_ism_counts": dict(ai_ism_counts),
        "ai_ism_examples": dict(ai_ism_examples),
    }


def scan_vn_chapters(work_dir):
    """Scan all VN chapter files in WORK directory."""
    vn_files = []
    for root, dirs, files in os.walk(work_dir):
        for f in files:
            if f.endswith("_VN.md") and "/VN/" in os.path.join(root, f):
                vn_files.append(os.path.join(root, f))
    
    print(f"\n📖 Found {len(vn_files)} VN chapter files")
    
    all_lines = []
    for vf in vn_files:
        try:
            with open(vf, 'r', encoding='utf-8') as fh:
                lines = [l.strip() for l in fh.readlines() if l.strip() and len(l.strip()) > 2]
                all_lines.extend(lines)
        except Exception as e:
            print(f"  ⚠ Error reading {vf}: {e}")
    
    print(f"  Total VN lines: {len(all_lines)}")
    print(f"  Total VN chars: {sum(len(l) for l in all_lines)}")
    
    return all_lines, vn_files


def scan_jp_epubs(input_dir):
    """Scan all JP EPUB files in INPUT directory."""
    epub_files = sorted(Path(input_dir).glob("*.epub"))
    print(f"\n📚 Found {len(epub_files)} JP EPUB files")
    
    all_lines = []
    for i, epub in enumerate(epub_files):
        if (i + 1) % 20 == 0:
            print(f"  Progress: {i + 1}/{len(epub_files)}")
        lines = extract_epub_text(str(epub))
        all_lines.extend(lines)
    
    print(f"  Total JP lines: {len(all_lines)}")
    print(f"  Total JP chars: {sum(len(l) for l in all_lines)}")
    
    return all_lines, epub_files


# ============================================================================
# JP-VN PAIRED EXAMPLE EXTRACTOR
# ============================================================================

def extract_paired_examples(work_dir):
    """
    Extract JP-VN paired examples from WORK directories.
    Looks for matching JP/VN chapter pairs.
    """
    paired_examples = defaultdict(list)
    pair_count = 0
    
    for project_dir in Path(work_dir).iterdir():
        if not project_dir.is_dir():
            continue
        
        vn_dir = project_dir / "VN"
        # Look for JP chapters in multiple possible locations
        jp_dirs = [project_dir / "JP", project_dir / "chapters", project_dir]
        
        if not vn_dir.exists():
            continue
        
        vn_chapters = sorted(vn_dir.glob("CHAPTER_*_VN.md"))
        
        for vn_chapter in vn_chapters:
            # Extract chapter number
            match = re.search(r'CHAPTER_(\d+)', vn_chapter.name)
            if not match:
                continue
            ch_num = match.group(1)
            
            # Find matching JP chapter
            jp_chapter = None
            for jp_dir in jp_dirs:
                candidates = [
                    jp_dir / f"CHAPTER_{ch_num}.md",
                    jp_dir / f"CHAPTER_{ch_num}_JP.md",
                    jp_dir / f"chapter_{ch_num}.md",
                ]
                for c in candidates:
                    if c.exists():
                        jp_chapter = c
                        break
                if jp_chapter:
                    break
            
            if not jp_chapter:
                continue
            
            try:
                with open(jp_chapter, 'r', encoding='utf-8') as f:
                    jp_lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')]
                with open(vn_chapter, 'r', encoding='utf-8') as f:
                    vn_lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')]
                
                # Align by paragraph index (rough alignment)
                min_len = min(len(jp_lines), len(vn_lines))
                for idx in range(min_len):
                    jp_line = jp_lines[idx]
                    vn_line = vn_lines[idx]
                    
                    # Check if JP line contains interesting patterns
                    for category, patterns in JP_PATTERNS.items():
                        for regex, pattern_id in patterns:
                            if re.search(regex, jp_line):
                                if len(paired_examples[pattern_id]) < 5:
                                    paired_examples[pattern_id].append({
                                        "jp": jp_line[:300],
                                        "vn": vn_line[:300],
                                        "source": f"{project_dir.name}/{vn_chapter.name}"
                                    })
                                    pair_count += 1
                
            except Exception:
                continue
    
    print(f"\n🔗 Extracted {pair_count} JP-VN paired examples across {len(paired_examples)} patterns")
    return dict(paired_examples)


# ============================================================================
# MAIN
# ============================================================================

def main():
    base_dir = Path(__file__).parent.parent
    input_dir = base_dir / "INPUT"
    work_dir = base_dir / "WORK"
    output_file = base_dir / "scripts" / "corpus_scan_results_vn.json"
    
    print("=" * 70)
    print("VN CORPUS PATTERN SCANNER")
    print("=" * 70)
    
    results = {
        "scan_stats": {},
        "jp_pattern_frequencies": {},
        "jp_pattern_examples": {},
        "jp_category_totals": {},
        "vn_analysis": {},
        "paired_examples": {},
    }
    
    # 1. Scan JP EPUBs
    print("\n" + "=" * 40)
    print("PHASE 1: JP Source Patterns (148 EPUBs)")
    print("=" * 40)
    jp_lines, epub_files = scan_jp_epubs(input_dir)
    
    jp_freqs, jp_examples = scan_jp_patterns(jp_lines)
    
    # Flatten frequencies
    flat_freqs = {}
    category_totals = {}
    for cat, patterns in jp_freqs.items():
        cat_total = 0
        for pid, count in patterns.items():
            flat_freqs[pid] = count
            cat_total += count
        category_totals[cat] = cat_total
    
    # Sort by frequency
    flat_freqs = dict(sorted(flat_freqs.items(), key=lambda x: x[1], reverse=True))
    category_totals = dict(sorted(category_totals.items(), key=lambda x: x[1], reverse=True))
    
    results["jp_pattern_frequencies"] = flat_freqs
    results["jp_category_totals"] = category_totals
    
    # Flatten examples
    flat_examples = {}
    for cat, patterns in jp_examples.items():
        for pid, exs in patterns.items():
            flat_examples[pid] = exs
    results["jp_pattern_examples"] = flat_examples
    
    print(f"\n  Total JP patterns found: {sum(flat_freqs.values())}")
    print(f"  Categories: {len(category_totals)}")
    print(f"\n  Top 15 categories by frequency:")
    for cat, total in list(category_totals.items())[:15]:
        print(f"    {cat}: {total:,}")
    
    # 2. Scan VN Chapters
    print("\n" + "=" * 40)
    print("PHASE 2: VN Output Analysis (103 chapters)")
    print("=" * 40)
    vn_lines, vn_files = scan_vn_chapters(work_dir)
    
    vn_analysis = scan_vn_patterns(vn_lines)
    results["vn_analysis"] = vn_analysis
    
    # VN stats
    total_words = vn_analysis["total_words"]
    print(f"\n  Total VN words: {total_words:,}")
    
    # Particle density
    total_particles = sum(vn_analysis["particle_counts"].values())
    if total_words > 0:
        density = (total_particles / total_words) * 1000
        print(f"  Particle density: {density:.1f} per 1000 words")
    
    # AI-ism report
    print(f"\n  AI-ism detections:")
    for ai_id, count in sorted(vn_analysis["ai_ism_counts"].items(), key=lambda x: x[1], reverse=True):
        desc = VN_AI_ISM_PATTERNS[ai_id][1]
        print(f"    {desc}: {count}")
    
    # Top particles
    print(f"\n  Top 20 VN particles:")
    sorted_particles = sorted(vn_analysis["particle_counts"].items(), key=lambda x: x[1], reverse=True)[:20]
    for particle, count in sorted_particles:
        print(f"    {particle}: {count}")
    
    # 3. Extract JP-VN pairs
    print("\n" + "=" * 40)
    print("PHASE 3: JP-VN Paired Examples")
    print("=" * 40)
    paired = extract_paired_examples(work_dir)
    results["paired_examples"] = paired
    
    # Stats
    results["scan_stats"] = {
        "jp_epubs_processed": len(epub_files),
        "jp_total_lines": len(jp_lines),
        "jp_total_chars": sum(len(l) for l in jp_lines),
        "vn_chapters_processed": len(vn_files),
        "vn_total_lines": len(vn_lines),
        "vn_total_chars": sum(len(l) for l in vn_lines),
        "vn_total_words": total_words,
        "jp_patterns_scanned": len(flat_freqs),
        "jp_categories": len(category_totals),
        "paired_examples_extracted": sum(len(v) for v in paired.values()),
    }
    
    # Save
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Results saved to {output_file}")
    print(f"   JP patterns: {len(flat_freqs)} unique, {sum(flat_freqs.values()):,} total hits")
    print(f"   VN words: {total_words:,}, particles: {total_particles:,}")
    print(f"   Paired examples: {sum(len(v) for v in paired.values())}")


if __name__ == "__main__":
    main()
