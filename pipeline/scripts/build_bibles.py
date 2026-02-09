#!/usr/bin/env python3
"""
Bible Database Builder — Scans WORK/ manifests, groups by series,
creates bible JSON files for all multi-volume series.
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PIPELINE_ROOT / "WORK"
BIBLES_DIR = PIPELINE_ROOT / "bibles"
INDEX_PATH = BIBLES_DIR / "index.json"

def scan_volumes():
    """Scan all WORK/ directories and extract manifest data."""
    volumes = []
    for d in sorted(WORK_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest_path = d / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                m = json.load(f)
            
            meta = m.get("metadata", {})
            meta_en = m.get("metadata_en", {})
            
            # Extract volume ID from dir name (last segment after _)
            parts = d.name.rsplit("_", 1)
            vol_id = parts[-1] if len(parts) > 1 else d.name[:4]
            
            char_names = meta_en.get("character_names", {})
            char_profiles = meta_en.get("character_profiles", {})
            
            title_ja = meta.get("title", "")
            title_en = meta_en.get("title_en", "") or meta.get("title_en", "") or ""
            series_raw = meta.get("series", "") or meta_en.get("series", "") or ""
            # Normalize: series can be a dict like {"ja":"...", "en":"..."}
            if isinstance(series_raw, dict):
                series = series_raw.get("en", "") or series_raw.get("ja", "") or ""
            else:
                series = str(series_raw) if series_raw else ""
            series_idx = meta.get("series_index", None)
            bible_id = m.get("bible_id", "")
            target_lang = m.get("target_language", "en")
            
            volumes.append({
                "dir": d.name,
                "dir_path": str(d),
                "vol_id": vol_id,
                "title_ja": title_ja,
                "title_en": title_en,
                "series": series,
                "series_index": series_idx,
                "bible_id": bible_id,
                "target_lang": target_lang,
                "char_names": char_names,
                "char_profiles": char_profiles,
                "char_names_count": len(char_names),
                "char_profiles_count": len(char_profiles),
                "metadata_en": meta_en,
                "metadata": meta,
            })
        except Exception as e:
            print(f"  ERROR reading {d.name}: {e}")
    
    return volumes


def group_by_series(volumes):
    """Group volumes into series by matching titles/series fields."""
    
    # Known series patterns (JP title prefix -> series_id)
    # We'll auto-detect by looking at common prefixes and series fields
    series_map = {}  # series_id -> [volumes]
    standalone = []
    
    # First pass: group by explicit series field
    by_series_field = {}
    no_series = []
    for v in volumes:
        s = v["series"] if isinstance(v["series"], str) else ""
        s = s.strip()
        if s:
            by_series_field.setdefault(s, []).append(v)
        else:
            no_series.append(v)
    
    # Second pass: for volumes without series field, try title matching
    # We check BOTH jp and en titles for common prefixes
    title_groups = {}  # representative_key -> [volumes]
    
    def _match_prefix(candidate, existing_key, min_jp=6, min_en=20):
        """Check if any title variant shares a long prefix.
        JP titles: 6 chars minimum (each kanji/kana ≈ 1 word).
        EN titles: 20 chars minimum (avoid short-prefix false positives).
        """
        for c_title in candidate:
            for e_title in existing_key:
                if not c_title or not e_title:
                    continue
                common = os.path.commonprefix([c_title, e_title])
                # Determine threshold: if mostly ASCII → EN threshold
                ascii_ratio = sum(1 for ch in common if ord(ch) < 128) / max(len(common), 1)
                threshold = min_en if ascii_ratio > 0.7 else min_jp
                if len(common) >= threshold:
                    return True
        return False
    
    for v in no_series:
        titles = [v["title_ja"], v["title_en"]]
        matched = False
        for existing_key in list(title_groups.keys()):
            existing_titles = title_groups[existing_key]["titles"]
            if _match_prefix(titles, existing_titles):
                title_groups[existing_key]["vols"].append(v)
                # Extend title variants for future matching
                for t in titles:
                    if t and t not in existing_titles:
                        existing_titles.append(t)
                matched = True
                break
        if not matched:
            title_groups[v["vol_id"]] = {"titles": [t for t in titles if t], "vols": [v]}
    
    # Merge title groups into series_map
    for key, group in title_groups.items():
        vols = group["vols"]
        if len(vols) >= 2:
            # Pick best name: prefer JP title from first vol
            best_name = vols[0]["title_ja"] or vols[0]["title_en"] or key
            by_series_field.setdefault(best_name, []).extend(vols)
        else:
            standalone.extend(vols)
    
    # Also check by_series_field for groups with series field
    for series_name, vols in by_series_field.items():
        if len(vols) >= 2:
            series_map[series_name] = vols
        else:
            standalone.extend(vols)
    
    return series_map, standalone


def make_series_id(series_name):
    """Convert series name to a filesystem-safe ID."""
    # Try to use English name if available
    # Remove special chars, lowercase, replace spaces with underscores
    sid = series_name.lower()
    sid = re.sub(r'[^\w\s]', '', sid)
    sid = re.sub(r'\s+', '_', sid.strip())
    sid = sid[:60]  # Truncate
    return sid


def detect_world_setting(title_en, title_ja, char_names):
    """Infer world_setting type from title and character data."""
    title = (title_en + " " + title_ja).lower()
    
    # Fantasy/Isekai indicators
    fantasy_keywords = ["fantasy", "knight", "princess", "kingdom", "sword", "magic",
                        "dragon", "isekai", "reincarnated", "villainess", "marquis",
                        "duke", "earl", "count", "lord", "marksman", "vanadis",
                        "村", "姫", "騎士", "剣", "魔", "王", "転生", "令嬢", "辺境"]
    
    if any(kw in title for kw in fantasy_keywords):
        return {
            "type": "fantasy",
            "label": "Fantasy Setting",
            "honorifics": {
                "mode": "localize",
                "policy": "Drop all JP honorifics. Use English equivalents (Lord, Lady, Sir, etc.)."
            },
            "name_order": {
                "default": "given_family",
                "policy": "Western first-name order for all characters."
            },
            "exceptions": []
        }
    
    # Default: modern Japan
    return {
        "type": "modern_japan",
        "label": "Contemporary Japanese Setting",
        "honorifics": {
            "mode": "retain",
            "policy": "Keep all JP honorifics (-san, -kun, -chan, -sama, -senpai, -sensei)."
        },
        "name_order": {
            "default": "family_given",
            "policy": "Japanese surname-first order for Japanese characters."
        },
        "exceptions": []
    }


def build_bible(series_id, series_name, volumes):
    """Build a bible JSON from grouped volumes."""
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Merge all character_names across volumes (first volume wins for conflicts)
    all_char_names = {}
    all_volumes_registered = []
    
    # Sort volumes by series_index or by vol_id
    def sort_key(v):
        idx = v.get("series_index")
        if idx is not None:
            try:
                return (0, float(idx))
            except:
                pass
        return (1, v["vol_id"])
    
    sorted_vols = sorted(volumes, key=sort_key)
    
    for i, v in enumerate(sorted_vols, 1):
        # Register volume
        idx = v.get("series_index")
        if idx is None:
            idx = i
        all_volumes_registered.append({
            "volume_id": v["vol_id"],
            "title": v["title_en"] or v["title_ja"],
            "index": idx
        })
        
        # Merge character names (first defined wins = canonical)
        for jp, en in v["char_names"].items():
            if jp not in all_char_names and isinstance(en, str):
                all_char_names[jp] = en
    
    # Build characters dict
    characters = {}
    for jp, en in all_char_names.items():
        characters[jp] = {
            "canonical_en": en,
        }
    
    # Detect title_en from first volume
    first_vol = sorted_vols[0]
    title_en = first_vol["title_en"] or series_name
    title_ja = first_vol["title_ja"] or series_name
    
    # Clean up series title (remove volume numbers)
    for pattern in [r'\s*Vol\.?\s*\d+', r'\s*[Vv]\d+', r'\s*第\d+[章巻]', r'\s+\d+$']:
        title_en = re.sub(pattern, '', title_en).strip()
        title_ja = re.sub(pattern, '', title_ja).strip()
    
    # Detect world setting
    world_setting = detect_world_setting(title_en, title_ja, all_char_names)
    
    # Build match patterns
    match_patterns = list(set(filter(None, [
        title_ja,
        title_en,
        series_name if series_name != title_ja and series_name != title_en else None,
    ])))
    
    bible = {
        "bible_version": "1.0",
        "series_id": series_id,
        "series_title": {
            "ja": title_ja,
            "en": title_en,
            "romaji": ""
        },
        "last_updated": now,
        "volumes_registered": all_volumes_registered,
        "characters": characters,
        "geography": {
            "countries": {},
            "regions": {},
            "cities": {}
        },
        "weapons_artifacts": {},
        "organizations": {},
        "cultural_terms": {},
        "mythology": {},
        "world_setting": world_setting,
        "translation_rules": {
            "style": "Natural English prose matching the genre tone."
        }
    }
    
    return bible, match_patterns


def load_index():
    """Load existing index.json."""
    if INDEX_PATH.exists():
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1.0", "last_updated": "", "series": {}}


def save_index(index):
    """Save index.json."""
    index["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    
    print("=" * 70)
    print("BIBLE DATABASE BUILDER")
    print("=" * 70)
    
    # Step 1: Scan
    print("\n[1/4] Scanning WORK/ directories...")
    volumes = scan_volumes()
    print(f"  Found {len(volumes)} volumes with manifests")
    
    # Step 2: Group
    print("\n[2/4] Grouping volumes by series...")
    series_map, standalone = group_by_series(volumes)
    
    print(f"\n  MULTI-VOLUME SERIES ({len(series_map)}):")
    for sname, vols in sorted(series_map.items(), key=lambda x: -len(x[1])):
        vol_ids = [v["vol_id"] for v in vols]
        names_total = sum(v["char_names_count"] for v in vols)
        lang = vols[0]["target_lang"]
        has_bible = any(v["bible_id"] for v in vols)
        status = " [BIBLE EXISTS]" if has_bible else ""
        print(f"    {len(vols)} vols | {names_total:3d} names | {lang} | {sname[:60]}{status}")
        for v in vols:
            print(f"      - {v['vol_id']}: {v['title_en'] or v['title_ja'][:50]} ({v['char_names_count']} names)")
    
    print(f"\n  STANDALONE ({len(standalone)}):")
    for v in standalone:
        print(f"    {v['vol_id']}: {v['title_en'] or v['title_ja'][:50]} ({v['char_names_count']} names, {v['target_lang']})")
    
    if mode == "scan":
        print("\n  Run with 'build' argument to create bibles.")
        return
    
    # Step 3: Build bibles
    print("\n[3/4] Building bible databases...")
    index = load_index()
    created = 0
    skipped = 0
    total_entries = 0
    
    for series_name, vols in sorted(series_map.items(), key=lambda x: -len(x[1])):
        # Skip if already has bible
        if any(v["bible_id"] for v in vols):
            existing_id = next(v["bible_id"] for v in vols if v["bible_id"])
            print(f"  SKIP (bible exists): {series_name[:50]} -> {existing_id}")
            skipped += 1
            continue
        
        # Skip VN-only series (target_lang == 'vi')
        # Actually include all — they still benefit from glossary lock
        
        series_id = make_series_id(series_name)
        if not series_id:
            series_id = make_series_id(vols[0]["title_en"] or vols[0]["title_ja"])
        
        # Skip if series_id already in index
        if series_id in index["series"]:
            print(f"  SKIP (in index): {series_id}")
            skipped += 1
            continue
        
        bible, match_patterns = build_bible(series_id, series_name, vols)
        
        # Save bible file
        bible_file = f"{series_id}.json"
        bible_path = BIBLES_DIR / bible_file
        with open(bible_path, "w", encoding="utf-8") as f:
            json.dump(bible, f, ensure_ascii=False, indent=2)
        
        entry_count = len(bible["characters"])
        total_entries += entry_count
        
        # Register in index
        vol_ids = [v["vol_id"] for v in vols]
        index["series"][series_id] = {
            "bible_file": bible_file,
            "match_patterns": match_patterns,
            "volumes": vol_ids,
            "entry_count": entry_count,
            "last_updated": bible["last_updated"]
        }
        
        created += 1
        print(f"  CREATED: {series_id}")
        print(f"    File: {bible_file}")
        print(f"    Volumes: {vol_ids}")
        print(f"    Characters: {entry_count}")
        print(f"    World: {bible['world_setting']['type']}")
        print(f"    Match: {match_patterns}")
    
    # Step 4: Save index
    print(f"\n[4/4] Saving index.json...")
    save_index(index)
    
    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"  Created: {created} new bibles")
    print(f"  Skipped: {skipped} (already exist)")
    print(f"  Total entries: {total_entries} characters")
    print(f"  Total series in index: {len(index['series'])}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
