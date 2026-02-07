#!/usr/bin/env python3
"""
Sino-Vietnamese Corpus Scanner
===============================
Scans 148 JP EPUBs + 103 VN chapters to extract:
1. Kanji compound frequency across the full JP corpus
2. JP-VN compound pairs (which compounds appear in VN as Sino-Vietnamese vs native)
3. Register distribution (formal Hán Việt vs casual native VN)
4. False cognate candidates (same kanji, different meaning by context)
5. Coverage gaps vs current sino_vietnamese_rag.json

Output: pipeline/scripts/corpus_scan_sino_vn.json
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
# CONSTANTS
# ============================================================================

WORK_DIR = Path(__file__).parent.parent / "WORK"
INPUT_DIR = Path(__file__).parent.parent / "INPUT"
CONFIG_DIR = Path(__file__).parent.parent / "config"
VN_DIR = Path(__file__).parent.parent / "VN"

# Hán Việt reading table — curated from production data
# Maps common kanji → known Sino-Vietnamese readings
# This allows us to detect when VN output uses the Hán Việt form vs native VN
HAN_VIET_READINGS = {
    # From sino_vietnamese_rag.json (700 JP LN patterns)
    # Will be loaded dynamically from RAG + kanji_difficult
}

# Common Sino-Vietnamese markers in VN text
# When these appear in VN output, it signals Hán Việt usage
SINO_VN_MARKERS = [
    # Formal/literary Hán Việt that should be natural VN in romcom
    "huyền quan", "thiếu nữ", "mỹ thiếu nữ", "phụ thân", "mẫu thân",
    "hữu nhân", "đệ", "muội", "huynh", "tỷ", "bỉ nữ", "bỉ thị",
    "học hiệu", "thực sự", "đài sở", "bộ ốc",
    # Formal Hán Việt that IS appropriate in formal contexts
    "chính trị", "kinh tế", "khoa học", "giáo dục", "pháp luật",
    "chẩn đoán", "cung điện", "thanh niên",
]

# Native VN alternatives (paired with above)
NATIVE_VN_ALTERNATIVES = {
    "huyền quan": "cửa chính",
    "thiếu nữ": "cô gái",
    "mỹ thiếu nữ": "cô gái xinh đẹp",
    "phụ thân": "bố/ba",
    "mẫu thân": "mẹ",
    "hữu nhân": "bạn",
    "học hiệu": "trường học",
    "bộ ốc": "phòng",
    "đài sở": "bếp",
}


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
# KANJI DETECTION
# ============================================================================

def is_kanji(char):
    code = ord(char)
    return (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0xF900 <= code <= 0xFAFF)


def extract_kanji_compounds(text, min_len=2, max_len=4):
    """Extract kanji compounds from JP text. Returns Counter."""
    compounds = Counter()
    current_seq = []
    
    for char in text:
        if is_kanji(char):
            current_seq.append(char)
        else:
            if current_seq:
                seq = ''.join(current_seq)
                seq_len = len(seq)
                # Extract all sub-compounds
                for length in range(min_len, min(max_len + 1, seq_len + 1)):
                    for i in range(seq_len - length + 1):
                        compounds[seq[i:i+length]] += 1
                # Also keep full sequence if it's a valid compound
                if seq_len >= min_len:
                    compounds[seq] += 1
                current_seq = []
    
    # Final sequence
    if current_seq:
        seq = ''.join(current_seq)
        seq_len = len(seq)
        for length in range(min_len, min(max_len + 1, seq_len + 1)):
            for i in range(seq_len - length + 1):
                compounds[seq[i:i+length]] += 1
    
    return compounds


def extract_single_kanji(text):
    """Extract all single kanji characters from JP text. Returns Counter."""
    kanji = Counter()
    for char in text:
        if is_kanji(char):
            kanji[char] += 1
    return kanji


# ============================================================================
# EPUB READER
# ============================================================================

def read_epub_text(epub_path):
    """Extract plain text from an EPUB file."""
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            text_parts = []
            html_files = sorted([
                f for f in zf.namelist()
                if f.endswith(('.xhtml', '.html', '.htm'))
                and 'toc' not in f.lower()
                and 'nav' not in f.lower()
                and 'cover' not in f.lower()
            ])
            
            for html_file in html_files:
                try:
                    content = zf.read(html_file).decode('utf-8', errors='replace')
                    text = strip_html(content)
                    if text.strip():
                        text_parts.append(text)
                except Exception:
                    continue
            
            return '\n'.join(text_parts)
    except Exception as e:
        print(f"  ⚠ Failed to read {epub_path}: {e}")
        return ""


# ============================================================================
# VN CHAPTER READER
# ============================================================================

def read_vn_chapters():
    """Read all VN translation chapters from WORK directories."""
    vn_texts = {}  # {work_id: {chapter_id: text}}
    total_files = 0
    
    for work_dir in sorted(WORK_DIR.iterdir()):
        if not work_dir.is_dir():
            continue
        vn_dir = work_dir / "VN"
        if not vn_dir.exists():
            continue
        
        work_id = work_dir.name
        vn_texts[work_id] = {}
        
        for vn_file in sorted(vn_dir.glob("*.md")):
            chapter_id = vn_file.stem
            text = vn_file.read_text(encoding='utf-8', errors='replace')
            if text.strip():
                vn_texts[work_id][chapter_id] = text
                total_files += 1
    
    return vn_texts, total_files


def read_jp_chapters():
    """Read all JP source chapters from WORK directories."""
    jp_texts = {}  # {work_id: {chapter_id: text}}
    total_files = 0
    
    for work_dir in sorted(WORK_DIR.iterdir()):
        if not work_dir.is_dir():
            continue
        jp_dir = work_dir / "JP"
        if not jp_dir.exists():
            continue
        
        work_id = work_dir.name
        jp_texts[work_id] = {}
        
        for jp_file in sorted(jp_dir.glob("*.md")):
            chapter_id = jp_file.stem
            text = jp_file.read_text(encoding='utf-8', errors='replace')
            if text.strip():
                jp_texts[work_id][chapter_id] = text
                total_files += 1
    
    return jp_texts, total_files


# ============================================================================
# LOAD EXISTING RAG DATA (for coverage comparison)
# ============================================================================

def load_existing_rag():
    """Load all existing Sino-VN data sources."""
    data = {}
    
    # 1. Main RAG
    rag_path = CONFIG_DIR / "sino_vietnamese_rag.json"
    if rag_path.exists():
        with open(rag_path) as f:
            rag = json.load(f)
        # Extract all hanzi from patterns
        rag_hanzi = {}
        for cat, val in rag.get("pattern_categories", {}).items():
            for p in val.get("patterns", []):
                h = p.get("hanzi", "")
                if h:
                    rag_hanzi[h] = {
                        "primary_reading": p.get("primary_reading", ""),
                        "category": cat,
                        "corpus_frequency": p.get("corpus_frequency", 0)
                    }
        data["rag_hanzi"] = rag_hanzi
        data["rag_categories"] = list(rag.get("pattern_categories", {}).keys())
    
    # 2. Kanji difficult
    kd_path = VN_DIR / "kanji_difficult.json"
    if kd_path.exists():
        with open(kd_path) as f:
            kd = json.load(f)
        kd_entries = {}
        kd_compounds = {}
        for e in kd.get("kanji_entries", []):
            k = e.get("kanji", "")
            if k:
                kd_entries[k] = {
                    "han_viet": e.get("han_viet", "N/A"),
                    "meaning": e.get("meaning", ""),
                    "priority": e.get("priority", ""),
                    "category": e.get("difficulty_category", "")
                }
            for c in e.get("common_compounds", []):
                comp = c.get("compound", "")
                if comp:
                    kd_compounds[comp] = {
                        "reading": c.get("reading", ""),
                        "vn_translation": c.get("vn_translation", ""),
                        "parent_kanji": k
                    }
        data["kd_entries"] = kd_entries
        data["kd_compounds"] = kd_compounds
    
    # 3. Context rules
    cr_path = CONFIG_DIR / "sino_vietnamese_context_rules.json"
    if cr_path.exists():
        with open(cr_path) as f:
            cr = json.load(f)
        cr_terms = {}
        for tier_key in ["tier_1_technical_formal", "tier_2_historical_formal", "tier_3_modern_casual"]:
            tier = cr.get(tier_key, {})
            for ex in tier.get("examples", []) + tier.get("mandatory_substitutions", []):
                kanji = ex.get("kanji", "")
                if kanji:
                    cr_terms[kanji] = {
                        "sino_vietnamese": ex.get("sino_vietnamese", ""),
                        "natural_vietnamese": ex.get("natural_vietnamese", ""),
                        "use": ex.get("use", ""),
                        "tier": tier_key
                    }
        data["cr_terms"] = cr_terms
    
    return data


# ============================================================================
# SINO-VN DETECTION IN VN TEXT
# ============================================================================

def detect_sino_vn_usage(vn_text):
    """
    Detect Sino-Vietnamese (Hán Việt) vs native Vietnamese word usage.
    Returns counts of formal Hán Việt terms found in VN text.
    """
    findings = defaultdict(int)
    vn_lower = vn_text.lower()
    
    for marker in SINO_VN_MARKERS:
        count = vn_lower.count(marker.lower())
        if count > 0:
            findings[marker] = count
    
    # Also detect native VN alternatives
    native_found = defaultdict(int)
    for sino, native in NATIVE_VN_ALTERNATIVES.items():
        for alt in native.split("/"):
            alt = alt.strip()
            count = vn_lower.count(alt.lower())
            if count > 0:
                native_found[f"{sino}→{alt}"] = count
    
    return dict(findings), dict(native_found)


# ============================================================================
# JP-VN COMPOUND PAIRING
# ============================================================================

def extract_paired_examples(jp_text, vn_text, top_compounds):
    """
    For top kanji compounds found in JP text, extract the corresponding
    VN sentence to create paired examples.
    
    Returns list of {jp_compound, jp_sentence, vn_sentence} dicts.
    """
    pairs = []
    jp_lines = [l.strip() for l in jp_text.split('\n') if l.strip() and len(l.strip()) > 5]
    vn_lines = [l.strip() for l in vn_text.split('\n') if l.strip() and len(l.strip()) > 5]
    
    # Simple positional pairing: JP line N roughly corresponds to VN line N
    # Filter to content lines only (skip headers, etc.)
    jp_content = [l for l in jp_lines if not l.startswith('#') and not l.startswith('---')]
    vn_content = [l for l in vn_lines if not l.startswith('#') and not l.startswith('---')]
    
    min_lines = min(len(jp_content), len(vn_content))
    
    for compound, _freq in top_compounds[:50]:  # Check top 50 compounds
        for i in range(min_lines):
            if compound in jp_content[i]:
                pairs.append({
                    "kanji_compound": compound,
                    "jp_sentence": jp_content[i][:200],  # Truncate long lines
                    "vn_sentence": vn_content[i][:200] if i < len(vn_content) else "",
                    "line_index": i
                })
                break  # One example per compound
    
    return pairs


# ============================================================================
# MAIN SCANNER
# ============================================================================

def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Sino-Vietnamese Corpus Scanner                        ║")
    print("║  148 EPUBs + JP/VN paired chapters                     ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    # --- Phase 1: Load existing data ---
    print("Phase 1: Loading existing Sino-VN data sources...")
    existing = load_existing_rag()
    print(f"  RAG hanzi: {len(existing.get('rag_hanzi', {}))}")
    print(f"  Kanji difficult entries: {len(existing.get('kd_entries', {}))}")
    print(f"  Kanji difficult compounds: {len(existing.get('kd_compounds', {}))}")
    print(f"  Context rule terms: {len(existing.get('cr_terms', {}))}")
    
    # --- Phase 2: Scan 148 EPUBs for kanji compound frequency ---
    print("\nPhase 2: Scanning 148 EPUBs for kanji compound frequency...")
    epub_files = sorted(INPUT_DIR.glob("*.epub"))
    print(f"  Found {len(epub_files)} EPUB files")
    
    global_compound_freq = Counter()
    global_single_kanji = Counter()
    epub_stats = {
        "total_epubs": len(epub_files),
        "total_lines": 0,
        "total_chars": 0,
        "epubs_processed": 0
    }
    
    for i, epub_path in enumerate(epub_files):
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{len(epub_files)} EPUBs...")
        
        text = read_epub_text(epub_path)
        if not text:
            continue
        
        epub_stats["total_lines"] += text.count('\n')
        epub_stats["total_chars"] += len(text)
        epub_stats["epubs_processed"] += 1
        
        # Extract compounds (2-4 chars — covers 99% of meaningful compounds)
        compounds = extract_kanji_compounds(text, min_len=2, max_len=4)
        global_compound_freq.update(compounds)
        
        # Extract single kanji
        single = extract_single_kanji(text)
        global_single_kanji.update(single)
    
    print(f"  ✓ Processed {epub_stats['epubs_processed']} EPUBs")
    print(f"  ✓ {epub_stats['total_lines']:,} lines, {epub_stats['total_chars']:,} chars")
    print(f"  ✓ {len(global_compound_freq):,} unique compounds")
    print(f"  ✓ {len(global_single_kanji):,} unique single kanji")
    
    # --- Phase 3: Read JP/VN paired chapters ---
    print("\nPhase 3: Reading JP/VN paired chapters...")
    jp_texts, jp_count = read_jp_chapters()
    vn_texts, vn_count = read_vn_chapters()
    print(f"  JP chapters: {jp_count}")
    print(f"  VN chapters: {vn_count}")
    
    # Find works that have both JP and VN
    paired_works = set(jp_texts.keys()) & set(vn_texts.keys())
    print(f"  Paired works (both JP+VN): {len(paired_works)}")
    
    # --- Phase 4: Extract JP-VN paired compound examples ---
    print("\nPhase 4: Extracting JP-VN compound pairs from paired works...")
    all_pairs = []
    paired_compound_freq = Counter()
    
    for work_id in sorted(paired_works):
        jp_chapters = jp_texts[work_id]
        vn_chapters = vn_texts[work_id]
        
        # Match chapter IDs (JP: CHAPTER_01.md, VN: CHAPTER_01_VN.md)
        for jp_ch_id, jp_ch_text in jp_chapters.items():
            # Try matching VN chapter (may have _VN suffix)
            vn_ch_id = jp_ch_id + "_VN"
            vn_ch_text = vn_chapters.get(vn_ch_id, "")
            if not vn_ch_text:
                # Try without _VN suffix
                vn_ch_text = vn_chapters.get(jp_ch_id, "")
            if not vn_ch_text:
                continue
            
            # Get top compounds for this chapter
            ch_compounds = extract_kanji_compounds(jp_ch_text, min_len=2, max_len=4)
            top_ch = ch_compounds.most_common(30)
            
            # Extract paired examples
            pairs = extract_paired_examples(jp_ch_text, vn_ch_text, top_ch)
            for p in pairs:
                p["work_id"] = work_id[:50]  # Truncate long dir names
                p["chapter"] = jp_ch_id
            all_pairs.extend(pairs)
            
            # Track compound frequency in paired contexts
            for compound, freq in top_ch:
                paired_compound_freq[compound] += freq
    
    print(f"  ✓ Extracted {len(all_pairs)} JP-VN compound pairs")
    
    # --- Phase 5: Detect Sino-VN usage in VN output ---
    print("\nPhase 5: Analyzing Sino-VN usage in VN output...")
    
    all_sino_findings = Counter()
    all_native_findings = Counter()
    vn_word_count = 0
    
    for work_id, chapters in vn_texts.items():
        for ch_id, ch_text in chapters.items():
            vn_word_count += len(ch_text.split())
            sino, native = detect_sino_vn_usage(ch_text)
            for marker, count in sino.items():
                all_sino_findings[marker] += count
            for marker, count in native.items():
                all_native_findings[marker] += count
    
    print(f"  VN word count: {vn_word_count:,}")
    print(f"  Sino-VN markers found: {sum(all_sino_findings.values())}")
    if all_sino_findings:
        print(f"  Top markers:")
        for marker, count in all_sino_findings.most_common(10):
            print(f"    {marker}: {count}")
    if all_native_findings:
        print(f"  Native alternatives found:")
        for marker, count in all_native_findings.most_common(10):
            print(f"    {marker}: {count}")
    
    # --- Phase 6: Coverage analysis ---
    print("\nPhase 6: Coverage analysis vs existing RAG...")
    
    rag_hanzi = existing.get("rag_hanzi", {})
    kd_entries = existing.get("kd_entries", {})
    kd_compounds = existing.get("kd_compounds", {})
    cr_terms = existing.get("cr_terms", {})
    
    # Top 200 compounds by frequency
    top_200 = global_compound_freq.most_common(200)
    
    covered_by_rag = 0
    covered_by_kd = 0
    covered_by_cr = 0
    not_covered = []
    
    for compound, freq in top_200:
        in_rag = compound in rag_hanzi
        in_kd = compound in kd_compounds
        in_cr = compound in cr_terms
        
        if in_rag:
            covered_by_rag += 1
        elif in_kd:
            covered_by_kd += 1
        elif in_cr:
            covered_by_cr += 1
        else:
            not_covered.append((compound, freq))
    
    print(f"  Top 200 compounds coverage:")
    print(f"    In RAG: {covered_by_rag}")
    print(f"    In kanji_difficult compounds: {covered_by_kd}")
    print(f"    In context_rules: {covered_by_cr}")
    print(f"    NOT COVERED: {len(not_covered)}")
    
    if not_covered[:20]:
        print(f"  Top uncovered compounds:")
        for compound, freq in not_covered[:20]:
            print(f"    {compound}: {freq:,}")
    
    # --- Phase 7: Single kanji coverage ---
    print("\nPhase 7: Single kanji coverage analysis...")
    top_100_kanji = global_single_kanji.most_common(100)
    
    kanji_in_rag = 0
    kanji_in_kd = 0
    kanji_uncovered = []
    
    for kanji, freq in top_100_kanji:
        if kanji in rag_hanzi:
            kanji_in_rag += 1
        elif kanji in kd_entries:
            kanji_in_kd += 1
        else:
            kanji_uncovered.append((kanji, freq))
    
    print(f"  Top 100 single kanji coverage:")
    print(f"    In RAG: {kanji_in_rag}")
    print(f"    In kanji_difficult: {kanji_in_kd}")
    print(f"    NOT COVERED: {len(kanji_uncovered)}")
    
    # --- Build output ---
    print("\nPhase 8: Building output JSON...")
    
    output = {
        "metadata": {
            "scanner_version": "1.0",
            "scan_date": "2026-02-07",
            "epub_count": epub_stats["epubs_processed"],
            "total_lines": epub_stats["total_lines"],
            "total_chars": epub_stats["total_chars"],
            "jp_chapters": jp_count,
            "vn_chapters": vn_count,
            "paired_works": len(paired_works),
            "vn_word_count": vn_word_count
        },
        "compound_frequency": {
            "top_500": [{"compound": c, "frequency": f} for c, f in global_compound_freq.most_common(500)],
            "total_unique": len(global_compound_freq)
        },
        "single_kanji_frequency": {
            "top_200": [{"kanji": k, "frequency": f} for k, f in global_single_kanji.most_common(200)],
            "total_unique": len(global_single_kanji)
        },
        "paired_examples": all_pairs[:500],  # Cap at 500
        "sino_vn_usage": {
            "sino_markers": dict(all_sino_findings.most_common(50)),
            "native_alternatives": dict(all_native_findings.most_common(50)),
            "vn_word_count": vn_word_count
        },
        "coverage_analysis": {
            "top_200_compounds": {
                "in_rag": covered_by_rag,
                "in_kanji_difficult": covered_by_kd,
                "in_context_rules": covered_by_cr,
                "not_covered": len(not_covered),
                "uncovered_list": [{"compound": c, "frequency": f} for c, f in not_covered[:50]]
            },
            "top_100_single_kanji": {
                "in_rag": kanji_in_rag,
                "in_kanji_difficult": kanji_in_kd,
                "not_covered": len(kanji_uncovered),
                "uncovered_list": [{"kanji": k, "frequency": f} for k, f in kanji_uncovered[:30]]
            }
        },
        "existing_source_stats": {
            "rag_hanzi_count": len(rag_hanzi),
            "kd_entry_count": len(kd_entries),
            "kd_compound_count": len(kd_compounds),
            "cr_term_count": len(cr_terms)
        }
    }
    
    # Save output
    output_path = Path(__file__).parent / "corpus_scan_sino_vn.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    file_size = output_path.stat().st_size / 1024
    print(f"\n  ✓ Output saved: {output_path}")
    print(f"  ✓ Size: {file_size:.1f} KB")
    
    # --- Summary ---
    print("\n" + "=" * 60)
    print("SCAN SUMMARY")
    print("=" * 60)
    print(f"  EPUBs scanned: {epub_stats['epubs_processed']}")
    print(f"  JP lines: {epub_stats['total_lines']:,}")
    print(f"  JP chars: {epub_stats['total_chars']:,}")
    print(f"  Unique compounds: {len(global_compound_freq):,}")
    print(f"  Unique single kanji: {len(global_single_kanji):,}")
    print(f"  JP-VN paired examples: {len(all_pairs)}")
    print(f"  VN Sino markers found: {sum(all_sino_findings.values())}")
    print(f"  Coverage gaps (top 200): {len(not_covered)} compounds uncovered")
    

if __name__ == "__main__":
    main()
