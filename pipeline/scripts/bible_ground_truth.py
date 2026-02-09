#!/usr/bin/env python3
"""
Bible Ground-Truth Verifier — Google Search Grounding via Gemini 2.5 Flash
==========================================================================

Sends every bible entry (characters, geography, weapons, orgs, cultural terms,
mythology) through Gemini with Google Search to verify against official sources:
  1st priority: Official English localization (anime, manga, licensed LN)
  2nd priority: Fan translations / wiki consensus

Outputs:
  - Per-series JSON reports in  scripts/ground_truth_reports/
  - Merged markdown report at   scripts/ground_truth_reports/REPORT.md
"""

import json
import os
import sys
import time
import re
import textwrap
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# SDK
# ---------------------------------------------------------------------------
from google import genai
from google.genai import types
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
BIBLES_DIR = PIPELINE_ROOT / "bibles"
INDEX_PATH = BIBLES_DIR / "index.json"
REPORT_DIR = SCRIPT_DIR / "ground_truth_reports"

load_dotenv(PIPELINE_ROOT / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL       = "gemini-2.5-flash"
TEMPERATURE = 0.5
BATCH_SIZE  = 40        # entries per API call (fit inside context window)
RATE_SLEEP  = 2.0       # seconds between calls (respect quota)

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set. Add it to pipeline/.env or export it.")
        sys.exit(1)
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Bible loading
# ---------------------------------------------------------------------------
def load_all_bibles() -> list[dict]:
    """Load index + every bible JSON. Returns list of bible dicts."""
    with open(INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)

    bibles = []
    for sid, meta in index["series"].items():
        bible_path = BIBLES_DIR / meta["bible_file"]
        if not bible_path.exists():
            print(f"  WARN: missing {meta['bible_file']}, skipping")
            continue
        with open(bible_path, encoding="utf-8") as f:
            bible = json.load(f)
        bible["_index_meta"] = meta
        bibles.append(bible)
    return bibles


def extract_entries(bible: dict) -> list[dict]:
    """Flatten a single bible into a list of verifiable entries."""
    series_ja = bible["series_title"].get("ja", "")
    series_en = bible["series_title"].get("en", "") or series_ja
    sid = bible.get("series_id", "")
    world_type = bible.get("world_setting", {}).get("type", "modern_japan")

    entries = []

    # Characters
    for jp, data in bible.get("characters", {}).items():
        if not isinstance(data, dict):
            continue
        entries.append({
            "category": "character",
            "jp": jp,
            "current_en": data.get("canonical_en", ""),
            "notes": data.get("notes", ""),
            "series_ja": series_ja,
            "series_en": series_en,
            "world_type": world_type,
        })

    # Geography
    for sub_cat in ["countries", "regions", "cities"]:
        geo = bible.get("geography", {}).get(sub_cat, {})
        for jp, data in geo.items():
            if not isinstance(data, dict):
                continue
            entries.append({
                "category": f"geography/{sub_cat}",
                "jp": jp,
                "current_en": data.get("canonical_en", ""),
                "notes": data.get("notes", ""),
                "series_ja": series_ja,
                "series_en": series_en,
                "world_type": world_type,
            })

    # Weapons / Artifacts
    for sub_cat, items in bible.get("weapons_artifacts", {}).items():
        if not isinstance(items, dict):
            continue
        for jp, data in items.items():
            if not isinstance(data, dict):
                continue
            entries.append({
                "category": f"weapon/{sub_cat}",
                "jp": jp,
                "current_en": data.get("canonical_en", ""),
                "notes": data.get("notes", ""),
                "series_ja": series_ja,
                "series_en": series_en,
                "world_type": world_type,
            })

    # Organizations
    for jp, data in bible.get("organizations", {}).items():
        if not isinstance(data, dict):
            continue
        entries.append({
            "category": "organization",
            "jp": jp,
            "current_en": data.get("canonical_en", ""),
            "notes": data.get("notes", ""),
            "series_ja": series_ja,
            "series_en": series_en,
            "world_type": world_type,
        })

    # Cultural Terms
    for jp, data in bible.get("cultural_terms", {}).items():
        if not isinstance(data, dict):
            continue
        entries.append({
            "category": "cultural_term",
            "jp": jp,
            "current_en": data.get("canonical_en", ""),
            "notes": data.get("notes", ""),
            "series_ja": series_ja,
            "series_en": series_en,
            "world_type": world_type,
        })

    # Mythology
    for jp, data in bible.get("mythology", {}).items():
        if not isinstance(data, dict):
            continue
        entries.append({
            "category": "mythology",
            "jp": jp,
            "current_en": data.get("canonical_en", ""),
            "notes": data.get("notes", ""),
            "series_ja": series_ja,
            "series_en": series_en,
            "world_type": world_type,
        })

    return entries


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = textwrap.dedent("""\
You are a Japanese Light Novel metadata verifier. For each entry I give you,
use Google Search to find the OFFICIAL English translation of the Japanese
term in the context of the specified series.

Priority order for "official" source:
  1. Licensed English light novel (Yen Press, Seven Seas, J-Novel Club, etc.)
  2. Official anime English subtitles / dub (Crunchyroll, Funimation, etc.)
  3. Official manga English release
  4. Fan translation wiki consensus (MAL, Fandom wiki, NovelUpdates, etc.)

For each entry, return a JSON object:
{
  "jp": "<original JP>",
  "current_en": "<what our bible currently has>",
  "verified_en": "<official EN from search, or current_en if already correct>",
  "source": "<where you found it: e.g. 'Yen Press LN Vol.1', 'Crunchyroll anime', 'Fandom wiki', 'no source found'>",
  "confidence": "<high|medium|low|unverifiable>",
  "status": "<correct|incorrect|unverifiable>",
  "note": "<brief explanation if incorrect or unverifiable>"
}

Rules:
- If the current_en is already the official name, set status="correct".
- If you find a DIFFERENT official name, set status="incorrect" and put the
  correct one in verified_en.
- If you cannot find any source, set status="unverifiable" and keep current_en.
- Short-name entries (e.g. surname-only, given-name-only) that are just
  substrings of a full-name entry: mark status="correct" with note="alias".
- Furigana-annotated variants (containing 《》) that map to the same canonical
  name: mark status="correct" with note="furigana variant".
- Return ONLY a JSON array of objects. No markdown, no explanation outside JSON.
""")


def build_batch_prompt(entries: list[dict]) -> str:
    """Build user prompt for a batch of entries."""
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(
            f"{i}. Series: {e['series_en']} ({e['series_ja']}) | "
            f"Category: {e['category']} | "
            f"JP: {e['jp']} | "
            f"Current EN: {e['current_en']} | "
            f"Notes: {e.get('notes', '')}"
        )
    return (
        f"Verify the following {len(entries)} entries. "
        f"Return a JSON array of {len(entries)} objects.\n\n"
        + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# API call with grounding
# ---------------------------------------------------------------------------
def call_gemini(client: genai.Client, prompt: str) -> str | None:
    """Call Gemini 2.5 Flash with Google Search grounding."""
    tools = [types.Tool(google_search=types.GoogleSearch())]
    config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tools,
    )
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=config,
        )
        return response.text
    except Exception as e:
        print(f"    API ERROR: {e}")
        return None


def parse_json_response(text: str) -> list[dict]:
    """Extract JSON array from model response (handles markdown fences)."""
    if not text:
        return []
    # Strip markdown code fences
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    print(f"    WARN: Could not parse JSON from response ({len(text)} chars)")
    return []


# ---------------------------------------------------------------------------
# Verification engine
# ---------------------------------------------------------------------------
def verify_bible(client: genai.Client, bible: dict) -> dict:
    """Verify all entries in a single bible. Returns report dict."""
    sid = bible.get("series_id", "unknown")
    series_en = bible["series_title"].get("en", "") or sid
    entries = extract_entries(bible)

    if not entries:
        return {
            "series_id": sid,
            "series_title": bible["series_title"],
            "total_entries": 0,
            "results": [],
            "summary": {"correct": 0, "incorrect": 0, "unverifiable": 0},
        }

    print(f"\n  [{sid}] {series_en}")
    print(f"    {len(entries)} entries to verify")

    all_results = []

    # Process in batches
    for i in range(0, len(entries), BATCH_SIZE):
        batch = entries[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(entries) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"    Batch {batch_num}/{total_batches} ({len(batch)} entries)...", end=" ", flush=True)

        prompt = build_batch_prompt(batch)
        raw = call_gemini(client, prompt)
        results = parse_json_response(raw)

        if results:
            all_results.extend(results)
            print(f"OK ({len(results)} parsed)")
        else:
            # Create unverifiable stubs for failed batch
            for e in batch:
                all_results.append({
                    "jp": e["jp"],
                    "current_en": e["current_en"],
                    "verified_en": e["current_en"],
                    "source": "API call failed",
                    "confidence": "unverifiable",
                    "status": "unverifiable",
                    "note": "API returned unparseable response",
                })
            print("FAILED (stub entries created)")

        if i + BATCH_SIZE < len(entries):
            time.sleep(RATE_SLEEP)

    # Tally
    summary = {"correct": 0, "incorrect": 0, "unverifiable": 0}
    for r in all_results:
        s = r.get("status", "unverifiable")
        if s in summary:
            summary[s] += 1
        else:
            summary["unverifiable"] += 1

    return {
        "series_id": sid,
        "series_title": bible["series_title"],
        "world_type": bible.get("world_setting", {}).get("type", "unknown"),
        "total_entries": len(entries),
        "results": all_results,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def render_markdown(reports: list[dict]) -> str:
    """Render all reports into a single Markdown document."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Bible Ground-Truth Verification Report",
        "",
        f"**Generated:** {now}  ",
        f"**Model:** {MODEL} (temp={TEMPERATURE}) + Google Search Grounding  ",
        f"**Series checked:** {len(reports)}  ",
        "",
    ]

    # Global summary
    g_total = sum(r["total_entries"] for r in reports)
    g_correct = sum(r["summary"]["correct"] for r in reports)
    g_incorrect = sum(r["summary"]["incorrect"] for r in reports)
    g_unverifiable = sum(r["summary"]["unverifiable"] for r in reports)

    lines.extend([
        "## Global Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total entries verified | {g_total} |",
        f"| Correct | {g_correct} |",
        f"| **Incorrect (needs fix)** | **{g_incorrect}** |",
        f"| Unverifiable | {g_unverifiable} |",
        f"| Accuracy rate | {g_correct / max(g_total, 1) * 100:.1f}% |",
        "",
        "---",
        "",
    ])

    # Incorrect entries table (high priority)
    incorrect_all = []
    for r in reports:
        for entry in r["results"]:
            if entry.get("status") == "incorrect":
                incorrect_all.append({**entry, "_series": r["series_title"].get("en", r["series_id"])})

    if incorrect_all:
        lines.extend([
            "## Entries Requiring Correction",
            "",
            "| Series | Category | JP | Current EN | Official EN | Source | Note |",
            "|--------|----------|----|------------|-------------|--------|------|",
        ])
        for e in incorrect_all:
            cat = e.get("category", "")
            lines.append(
                f"| {e['_series'][:30]} | {cat} | {e['jp']} | {e['current_en']} "
                f"| **{e.get('verified_en', '')}** | {e.get('source', '')} | {e.get('note', '')} |"
            )
        lines.extend(["", "---", ""])

    # Per-series sections
    for r in sorted(reports, key=lambda x: -x["summary"]["incorrect"]):
        sid = r["series_id"]
        title_en = r["series_title"].get("en", sid)
        title_ja = r["series_title"].get("ja", "")
        s = r["summary"]
        wtype = r.get("world_type", "")

        lines.extend([
            f"## {title_en}",
            "",
            f"**JP:** {title_ja}  ",
            f"**World:** {wtype} | **Entries:** {r['total_entries']}  ",
            f"**Correct:** {s['correct']} | **Incorrect:** {s['incorrect']} | **Unverifiable:** {s['unverifiable']}  ",
            "",
        ])

        # Only show non-correct entries in detail
        flagged = [e for e in r["results"] if e.get("status") != "correct"]
        if flagged:
            lines.append("| JP | Current EN | Verified EN | Status | Source | Note |")
            lines.append("|----|------------|-------------|--------|--------|------|")
            for e in flagged:
                lines.append(
                    f"| {e['jp']} | {e['current_en']} | {e.get('verified_en', '')} "
                    f"| {e.get('status', '')} | {e.get('source', '')} | {e.get('note', '')} |"
                )
            lines.append("")
        else:
            lines.append("All entries verified correct.")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify bible entries via Gemini + Google Search grounding"
    )
    parser.add_argument(
        "--series", "-s",
        help="Verify only this series_id (default: all)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be verified without calling Gemini",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("BIBLE GROUND-TRUTH VERIFIER")
    print(f"  Model: {MODEL} | Temp: {TEMPERATURE} | Grounding: Google Search")
    print("=" * 70)

    # Load
    print("\n[1/4] Loading bibles...")
    bibles = load_all_bibles()
    print(f"  Loaded {len(bibles)} bibles")

    # Filter
    if args.series:
        bibles = [b for b in bibles if b.get("series_id") == args.series]
        if not bibles:
            print(f"  ERROR: series '{args.series}' not found")
            sys.exit(1)

    # Count total entries
    total = sum(len(extract_entries(b)) for b in bibles)
    print(f"  Total entries to verify: {total}")
    est_calls = sum((len(extract_entries(b)) + BATCH_SIZE - 1) // BATCH_SIZE for b in bibles)
    est_time = est_calls * (RATE_SLEEP + 8)  # ~8s per call average
    print(f"  Estimated API calls: {est_calls} (~{est_time / 60:.1f} min)")

    if args.dry_run:
        print("\n[DRY RUN] Showing entry breakdown:")
        for b in bibles:
            entries = extract_entries(b)
            sid = b.get("series_id", "?")
            title = b["series_title"].get("en", sid)
            cats = {}
            for e in entries:
                cats[e["category"]] = cats.get(e["category"], 0) + 1
            cat_str = ", ".join(f"{k}:{v}" for k, v in sorted(cats.items()))
            print(f"  {title[:50]}: {len(entries)} entries ({cat_str})")
        print(f"\nTotal: {total} entries in {est_calls} batches")
        return

    # Verify
    print("\n[2/4] Verifying with Gemini + Google Search...")
    client = get_client()
    reports = []
    for b in bibles:
        report = verify_bible(client, b)
        reports.append(report)

    # Save JSON reports
    print("\n[3/4] Saving JSON reports...")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for r in reports:
        sid = r["series_id"]
        # Truncate filename to avoid filesystem issues
        safe_name = re.sub(r'[^\w\-]', '_', sid)[:60]
        json_path = REPORT_DIR / f"{safe_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        s = r["summary"]
        print(f"  {safe_name}.json — {s['correct']}✓ {s['incorrect']}✗ {s['unverifiable']}?")

    # Render markdown
    print("\n[4/4] Generating markdown report...")
    md = render_markdown(reports)
    md_path = REPORT_DIR / "REPORT.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  Written to {md_path}")

    # Final summary
    g_correct = sum(r["summary"]["correct"] for r in reports)
    g_incorrect = sum(r["summary"]["incorrect"] for r in reports)
    g_unverifiable = sum(r["summary"]["unverifiable"] for r in reports)
    print(f"\n{'=' * 70}")
    print(f"COMPLETE — {total} entries across {len(reports)} series")
    print(f"  Correct:      {g_correct}")
    print(f"  Incorrect:    {g_incorrect}")
    print(f"  Unverifiable: {g_unverifiable}")
    print(f"  Accuracy:     {g_correct / max(total, 1) * 100:.1f}%")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
