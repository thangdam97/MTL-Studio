"""
Japanese Grammar Pattern Detector for English Vector Search
Detects common Japanese grammar structures that have idiomatic English equivalents

This module scans Japanese source text for patterns like:
- けど + も (contrastive comparison)
- はともかく (dismissive acknowledgment)
- だけでなく (not just X but Y)
- どころか (let alone)

And returns structured data for vector search matching.
"""

import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# Pattern indicators mapping
# Each category maps to regex patterns that detect Japanese grammar structures
GRAMMAR_INDICATORS = {
    "contrastive_comparison": [
        (r"[がけ]ど.*?も", "けど...も"),          # けど + も, が + も
        (r"だけでなく|ばかりでなく", "だけでなく"),   # not just X but Y
        (r"のみならず", "のみならず"),              # not only X but Y (formal)
        (r"どころか|はおろか", "どころか"),          # let alone, much less
        (r"まして[やは]?", "まして"),              # much less, let alone
    ],
    "dismissive_acknowledgment": [
        (r"はともかく", "はともかく"),              # X aside
        (r"は置いといて|は置いておいて", "は置いといて"), # putting X aside
        (r"はさておき", "はさておき"),              # setting X aside
        (r"はいいとして", "はいいとして"),          # X is fine, but...
    ],
    "intensifiers": [
        (r"めっちゃ|めちゃくちゃ", "めっちゃ"),      # super, really
        (r"すごく|すっごく", "すごく"),            # very, really
        (r"かなり", "かなり"),                    # quite, pretty
        (r"やばい", "やばい"),                    # crazy, insane
        (r"マジで|マジ", "マジで"),               # seriously, really
    ],
    "hedging": [
        (r"かもしれない", "かもしれない"),          # might, maybe
        (r"だろう[か]?", "だろう"),               # probably
        (r"[のん]じゃないかな", "じゃないかな"),    # I think, maybe
        (r"気がする", "気がする"),                 # I feel like
        (r"ような気がする", "ような気がする"),      # seems like
    ],
    "response_particles": [
        (r"^[ああ]あ[、。]", "ああ"),              # Ah, oh
        (r"^う[んー]", "うん"),                   # Yeah, uh-huh
        (r"^そ[うー]だね", "そうだね"),            # Right, yeah
        (r"^なるほど", "なるほど"),                # I see, makes sense
        (r"^へえ[ー]?", "へえ"),                  # Huh, wow
    ],
    "natural_transitions": [
        (r"とにかく", "とにかく"),                 # Anyway, in any case
        (r"ところで", "ところで"),                 # By the way
        (r"それはそうと", "それはそうと"),          # Speaking of which
        (r"まあ[、。]", "まあ"),                  # Well, anyway
    ],
    "sentence_endings": [
        (r"[だよ]ね[え]?", "だよね"),              # Right?, Don't you think?
        (r"じゃない[？]?", "じゃない"),            # Isn't it?, Right?
        (r"[かな]な[あ]?", "かな"),               # I wonder, maybe
        (r"んだ[よね]?", "んだ"),                 # Explanatory ending
        (r"だろ[う]?", "だろう"),                 # Probably, right?
        (r"のか[な]?", "のか"),                   # I wonder if
        (r"っけ[？]?", "っけ"),                   # Was it...? (recall)
        (r"わけ[だよね]?", "わけ"),               # That's why, naturally
    ],
    "emotional_nuance": [
        (r"なんか", "なんか"),                     # kind of, somehow (uncertainty)
        (r"ちょっと", "ちょっと"),                 # a bit, kinda (softener)
        (r"やっぱり", "やっぱり"),                 # as expected, I knew it
        (r"さすがに", "さすがに"),                 # even so, as expected
        (r"まさか", "まさか"),                     # no way, surely not
        (r"もしかして", "もしかして"),             # could it be, maybe
        (r"どうせ", "どうせ"),                     # anyway, might as well
        (r"一応", "一応"),                         # just in case, for now
        (r"とりあえず", "とりあえず"),             # for now, anyway
    ],
    "action_emphasis": [
        (r"てしまう|ちゃう|じゃう", "てしまう"),    # ended up, accidentally
        (r"てみる", "てみる"),                     # try doing
        (r"てくる", "てくる"),                     # go/come and do
        (r"ていく", "ていく"),                     # keep doing, go and do
        (r"てくれる", "てくれる"),                 # do for me (gratitude)
        (r"てあげる", "てあげる"),                 # do for someone
        (r"ておく", "ておく"),                     # do in advance
        (r"てしまった", "てしまった"),             # ended up doing (past)
    ]
}


# High-priority patterns (more likely to need natural English equivalents)
HIGH_PRIORITY_PATTERNS = {
    "contrastive_comparison",
    "dismissive_acknowledgment"
}


def detect_grammar_patterns(
    japanese_text: str,
    top_n: int = 15,
    include_line_numbers: bool = True
) -> List[Dict[str, Any]]:
    """
    Detect Japanese grammar patterns in source text.

    This function scans the Japanese text for grammar structures that typically
    have idiomatic English equivalents, allowing the translator to use natural
    phrasing instead of literal translations.

    Args:
        japanese_text: Source Japanese text (full chapter or paragraph)
        top_n: Maximum number of patterns to return (prioritized by importance)
        include_line_numbers: If True, includes line numbers in results

    Returns:
        List of detected patterns, each containing:
        - category: Pattern category (e.g., "contrastive_comparison")
        - indicator: The specific grammar marker detected (e.g., "けど...も")
        - line_number: Line number where pattern was found (if enabled)
        - context: The full line containing the pattern
        - match: The exact matched text
        - priority: "high" or "normal"

    Example:
        patterns = detect_grammar_patterns("真理亜は変だが、如月さんも結構変だ")
        # Returns: [{"category": "contrastive_comparison", "indicator": "けど...も", ...}]
    """
    patterns = []
    lines = japanese_text.split('\n')

    for line_num, line in enumerate(lines, start=1):
        # Skip empty lines and lines with only punctuation
        if not line.strip() or len(line.strip()) < 3:
            continue

        for category, indicators in GRAMMAR_INDICATORS.items():
            for pattern_regex, pattern_name in indicators:
                try:
                    matches = re.finditer(pattern_regex, line, re.IGNORECASE)
                    for match in matches:
                        # Determine priority
                        priority = "high" if category in HIGH_PRIORITY_PATTERNS else "normal"

                        pattern_entry = {
                            "category": category,
                            "indicator": pattern_name,
                            "context": line.strip(),
                            "match": match.group(0),
                            "priority": priority,
                            "match_start": match.start(),
                            "match_end": match.end()
                        }

                        if include_line_numbers:
                            pattern_entry["line_number"] = line_num

                        patterns.append(pattern_entry)

                except re.error as e:
                    logger.warning(f"Regex error for pattern '{pattern_regex}': {e}")
                    continue

    # Sort by priority (high first), then by line number
    patterns.sort(key=lambda x: (
        0 if x["priority"] == "high" else 1,
        x.get("line_number", 0)
    ))

    # Return top N patterns
    return patterns[:top_n]


def extract_context_window(
    japanese_text: str,
    line_number: int,
    window_size: int = 2
) -> Dict[str, str]:
    """
    Extract surrounding context for a detected pattern.

    Args:
        japanese_text: Full Japanese text
        line_number: Line number of the pattern (1-indexed)
        window_size: Number of lines before/after to include

    Returns:
        Dictionary with:
        - prev: Previous lines (joined)
        - current: Current line
        - next: Next lines (joined)
    """
    lines = japanese_text.split('\n')
    idx = line_number - 1  # Convert to 0-indexed

    if idx < 0 or idx >= len(lines):
        return {"prev": "", "current": "", "next": ""}

    prev_start = max(0, idx - window_size)
    next_end = min(len(lines), idx + window_size + 1)

    return {
        "prev": "\n".join(lines[prev_start:idx]),
        "current": lines[idx],
        "next": "\n".join(lines[idx + 1:next_end])
    }


def get_pattern_statistics(patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get statistics about detected patterns.

    Args:
        patterns: List of detected patterns from detect_grammar_patterns()

    Returns:
        Dictionary with counts by category and priority
    """
    stats = {
        "total": len(patterns),
        "by_category": {},
        "by_priority": {"high": 0, "normal": 0},
        "unique_indicators": set()
    }

    for pattern in patterns:
        category = pattern.get("category", "unknown")
        priority = pattern.get("priority", "normal")
        indicator = pattern.get("indicator", "")

        # Count by category
        stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

        # Count by priority
        stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

        # Track unique indicators
        if indicator:
            stats["unique_indicators"].add(indicator)

    # Convert set to list for JSON serialization
    stats["unique_indicators"] = list(stats["unique_indicators"])

    return stats


def filter_patterns_by_category(
    patterns: List[Dict[str, Any]],
    categories: List[str]
) -> List[Dict[str, Any]]:
    """
    Filter patterns to only include specific categories.

    Args:
        patterns: List of detected patterns
        categories: List of category names to keep

    Returns:
        Filtered list of patterns
    """
    return [p for p in patterns if p.get("category") in categories]


def deduplicate_patterns(
    patterns: List[Dict[str, Any]],
    max_per_category: int = 5
) -> List[Dict[str, Any]]:
    """
    Remove duplicate patterns and limit per category.

    Args:
        patterns: List of detected patterns
        max_per_category: Maximum patterns to keep per category

    Returns:
        Deduplicated list of patterns
    """
    seen_contexts = set()
    category_counts = {}
    deduplicated = []

    for pattern in patterns:
        context = pattern.get("context", "")
        category = pattern.get("category", "unknown")

        # Skip if exact context already seen
        if context in seen_contexts:
            continue

        # Skip if category limit reached
        if category_counts.get(category, 0) >= max_per_category:
            continue

        seen_contexts.add(context)
        category_counts[category] = category_counts.get(category, 0) + 1
        deduplicated.append(pattern)

    return deduplicated


# Convenience function for quick testing
def quick_detect(japanese_text: str, verbose: bool = True) -> Dict[str, Any]:
    """
    Quick pattern detection with statistics.

    Args:
        japanese_text: Japanese text to analyze
        verbose: If True, prints results

    Returns:
        Dictionary with patterns and statistics
    """
    patterns = detect_grammar_patterns(japanese_text, top_n=20)
    stats = get_pattern_statistics(patterns)

    result = {
        "patterns": patterns,
        "statistics": stats
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"Pattern Detection Results")
        print(f"{'='*60}")
        print(f"Total patterns detected: {stats['total']}")
        print(f"\nBy Category:")
        for category, count in stats['by_category'].items():
            print(f"  - {category}: {count}")
        print(f"\nBy Priority:")
        print(f"  - High: {stats['by_priority']['high']}")
        print(f"  - Normal: {stats['by_priority']['normal']}")
        print(f"\nTop 5 Patterns:")
        for i, pattern in enumerate(patterns[:5], 1):
            print(f"  {i}. [{pattern['category']}] {pattern['indicator']}")
            print(f"     Context: {pattern['context'][:60]}...")

    return result


if __name__ == "__main__":
    # Test with sample Japanese text
    test_text = """
    真理亜は変だが、如月さんも結構変だ。
    それはともかく、今日の授業はどうだった？
    彼女は美しいだけでなく、頭もいい。
    歩くどころか、立つこともできない。
    """

    print("Grammar Pattern Detector Module")
    print("="*60)
    quick_detect(test_text, verbose=True)
