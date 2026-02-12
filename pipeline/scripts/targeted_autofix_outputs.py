#!/usr/bin/env python3
"""Targeted high-confidence grammar auto-fix pass for EN outputs.

Fix categories:
1) CJK leaks (only exact known substitution mappings)
2) "would of" -> "would have"
3) obvious a/an errors before vowel-initial words
4) Name smile/voice possessives (e.g., "Nagi smile" -> "Nagi's smile")
5) AI-ism: "I couldn't help but [verb]" -> "I [verb]" (confidence: 0.95)

Scope by default: pipeline/WORK/*/EN/*.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


CJK_PATTERN = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]+")


@dataclass
class FileFixResult:
    file_path: str
    fixes: Dict[str, int]
    unresolved_cjk_after: int


def iter_en_files(work_root: Path) -> Iterable[Path]:
    for p in sorted(work_root.glob("*/EN/*.md")):
        if p.is_file():
            yield p


def load_cjk_mappings(repo_root: Path) -> Dict[str, str]:
    mappings: Dict[str, str] = {}

    rules_path = repo_root / "pipeline" / "config" / "cjk_validation_rules.json"
    if rules_path.exists():
        data = json.loads(rules_path.read_text(encoding="utf-8"))
        rep = data.get("replacement_mappings", {})
        for section in ("common_chinese_leaks", "common_japanese_leaks", "common_korean_leaks", "punctuation_replacements"):
            mappings.update(rep.get(section, {}))

    rag_path = repo_root / "pipeline" / "prompts" / "modules" / "rag" / "cjk_prevention_schema_en.json"
    if rag_path.exists():
        rag = json.loads(rag_path.read_text(encoding="utf-8"))
        subs = rag.get("common_substitutions", {})
        for bucket in subs.values():
            if not isinstance(bucket, dict):
                continue
            for term, info in bucket.items():
                if not isinstance(info, dict):
                    continue
                english = info.get("english")
                if isinstance(english, list) and english:
                    mappings.setdefault(term, english[0])

    # Normalize spacing in mapped replacements for text flow.
    normalized: Dict[str, str] = {}
    for k, v in mappings.items():
        if not k or not isinstance(k, str) or not isinstance(v, str):
            continue
        normalized[k] = v.strip()

    return normalized


def fix_would_of(text: str) -> Tuple[str, int]:
    pat = re.compile(r"\bwould\s+of\b", re.IGNORECASE)

    def repl(m: re.Match[str]) -> str:
        src = m.group(0)
        if src[0].isupper():
            return "Would have"
        return "would have"

    new_text, n = pat.subn(repl, text)
    return new_text, n


def fix_a_an(text: str) -> Tuple[str, int]:
    # obvious: "a" + vowel-leading token; skip consonant-sound exceptions
    pat = re.compile(r"\b([Aa])\s+([aeiouAEIOU][A-Za-z'-]*)\b")
    exceptions = (
        "user", "use", "util", "usual", "uni", "unanim", "one", "once",
        "euro", "ewe", "ufo", "uk", "u-sh", "usb", "usage",
    )

    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        art = m.group(1)
        word = m.group(2)
        lw = word.lower()
        if lw.startswith(exceptions):
            return m.group(0)
        count += 1
        return ("An" if art == "A" else "an") + " " + word

    out = pat.sub(repl, text)
    return out, count


def fix_name_smile_voice(text: str) -> Tuple[str, int]:
    pat = re.compile(r"\b([A-Z][a-z]+)\s+(smile|voice)\b")
    excluded = {
        "Her", "His", "My", "Your", "Our", "Their", "Its",
        "The", "This", "That", "These", "Those", "A", "An",
        "In", "On", "At", "To", "From", "For", "By", "With", "Without",
        "And", "But", "Or", "Nor", "Yet", "So", "If", "When", "While", "Though",
        "Because", "Since", "As", "After", "Before", "Until", "Unless",
        "Then", "Now", "Today", "Tomorrow", "Yesterday", "Welcome",
    }

    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        name = m.group(1)
        noun = m.group(2)
        if name in excluded:
            return m.group(0)
        # Already possessive in source text
        prev_idx = m.start()
        if prev_idx > 0 and text[prev_idx - 1] == "'":
            return m.group(0)
        count += 1
        return f"{name}'s {noun}"

    out = pat.sub(repl, text)
    return out, count


def fix_couldnt_help_but(text: str) -> Tuple[str, int]:
    """Fix AI-ism: 'I couldn't help but [verb]' -> 'I [verb]'

    Confidence: 0.95 (high - safe for auto-fix)
    From english_grammar_validation_t1.json v1.3 Phase 2 blocklist
    """
    pat = re.compile(r"\bI couldn't help but (\w+)")

    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        verb = m.group(1)
        count += 1
        return f"I {verb}"

    out = pat.sub(repl, text)
    return out, count


def fix_cjk_known_mappings(text: str, mappings: Dict[str, str]) -> Tuple[str, int]:
    # Apply longest keys first to avoid partial collisions.
    keys = [k for k in mappings.keys() if CJK_PATTERN.search(k)]
    keys.sort(key=len, reverse=True)

    total = 0
    out = text
    for key in keys:
        val = mappings[key]
        if not val:
            continue
        escaped = re.escape(key)
        pat = re.compile(escaped)
        out, n = pat.subn(val, out)
        total += n
    return out, total


def count_cjk_sequences(text: str) -> int:
    return len(CJK_PATTERN.findall(text))


def run_fix_on_file(path: Path, cjk_mappings: Dict[str, str], apply: bool) -> FileFixResult:
    original = path.read_text(encoding="utf-8")
    text = original

    fixes: Dict[str, int] = {
        "cjk_known_mapping": 0,
        "would_of": 0,
        "a_an": 0,
        "name_smile_voice_possessive": 0,
        "ai_ism_couldnt_help_but": 0,
    }

    text, n_cjk = fix_cjk_known_mappings(text, cjk_mappings)
    fixes["cjk_known_mapping"] = n_cjk

    text, n_would = fix_would_of(text)
    fixes["would_of"] = n_would

    text, n_aan = fix_a_an(text)
    fixes["a_an"] = n_aan

    text, n_pos = fix_name_smile_voice(text)
    fixes["name_smile_voice_possessive"] = n_pos

    text, n_ai_ism = fix_couldnt_help_but(text)
    fixes["ai_ism_couldnt_help_but"] = n_ai_ism

    unresolved = count_cjk_sequences(text)

    if apply and text != original:
        path.write_text(text, encoding="utf-8")

    return FileFixResult(
        file_path=str(path),
        fixes=fixes,
        unresolved_cjk_after=unresolved,
    )


def write_reports(results: List[FileFixResult], json_out: Path, md_out: Path, apply: bool) -> None:
    totals = Counter()
    modified = []
    unresolved_files = []

    for r in results:
        file_total = sum(r.fixes.values())
        totals.update(r.fixes)
        if file_total > 0:
            modified.append((r.file_path, file_total, r.fixes))
        if r.unresolved_cjk_after > 0:
            unresolved_files.append((r.file_path, r.unresolved_cjk_after))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if apply else "dry-run",
        "files_scanned": len(results),
        "files_modified": len(modified),
        "total_fixes": dict(totals),
        "top_modified_files": [
            {
                "file": p,
                "total_fixes": t,
                "breakdown": b,
            }
            for p, t, b in sorted(modified, key=lambda x: x[1], reverse=True)[:50]
        ],
        "files_with_unresolved_cjk": [
            {"file": p, "unresolved_cjk_sequences": c}
            for p, c in sorted(unresolved_files, key=lambda x: x[1], reverse=True)[:100]
        ],
    }

    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Targeted Auto-Fix Report (High-Confidence Categories)")
    lines.append("")
    lines.append(f"Generated: {payload['generated_at']}")
    lines.append(f"Mode: **{payload['mode']}**")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Target: `pipeline/WORK/*/EN/*.md`")
    lines.append(f"- Files scanned: **{payload['files_scanned']}**")
    lines.append(f"- Files modified: **{payload['files_modified']}**")
    lines.append("")
    lines.append("## Fix Totals")
    for k, v in payload["total_fixes"].items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")

    lines.append("## Top Modified Files")
    for item in payload["top_modified_files"][:25]:
        lines.append(f"- `{item['file']}`: {item['total_fixes']} fixes")
        b = item["breakdown"]
        lines.append(
            f"  - cjk={b['cjk_known_mapping']}, would_of={b['would_of']}, a_an={b['a_an']}, possessive={b['name_smile_voice_possessive']}, ai_ism={b['ai_ism_couldnt_help_but']}"
        )
    lines.append("")

    lines.append("## Remaining CJK (Needs Manual or Expanded Mapping)")
    if payload["files_with_unresolved_cjk"]:
        for item in payload["files_with_unresolved_cjk"][:30]:
            lines.append(f"- `{item['file']}`: {item['unresolved_cjk_sequences']} sequences")
    else:
        lines.append("- None")

    md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Targeted high-confidence auto-fix pass for EN output files")
    parser.add_argument("--work-root", default="pipeline/WORK", help="Root folder for volume outputs")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only; do not write changes")
    parser.add_argument("--json-out", default="pipeline/TARGETED_AUTOFIX_REPORT.json", help="JSON report path")
    parser.add_argument("--md-out", default="pipeline/TARGETED_AUTOFIX_REPORT.md", help="Markdown report path")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    work_root = repo_root / args.work_root
    apply = not args.dry_run

    cjk_mappings = load_cjk_mappings(repo_root)
    files = list(iter_en_files(work_root))

    results = [run_fix_on_file(p, cjk_mappings, apply=apply) for p in files]

    json_out = repo_root / args.json_out
    md_out = repo_root / args.md_out
    write_reports(results, json_out, md_out, apply=apply)

    totals = Counter()
    modified = 0
    for r in results:
        totals.update(r.fixes)
        if sum(r.fixes.values()) > 0:
            modified += 1

    print(f"Files scanned: {len(results)}")
    print(f"Files modified: {modified}")
    print(f"Fix totals: {dict(totals)}")
    print(f"Report JSON: {json_out}")
    print(f"Report MD: {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
