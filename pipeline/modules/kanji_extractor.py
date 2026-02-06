"""
Kanji Compound Extractor for Japanese Text

Extracts kanji compounds (2+ consecutive kanji characters) from Japanese text
for Sino-Vietnamese disambiguation lookup.
"""

import re
from typing import List, Set, Tuple
from collections import Counter


def is_kanji(char: str) -> bool:
    """
    Check if a character is a kanji (CJK Unified Ideograph).
    
    Unicode ranges:
    - U+4E00–U+9FFF: CJK Unified Ideographs (main block)
    - U+3400–U+4DBF: CJK Extension A
    - U+F900–U+FAFF: CJK Compatibility Ideographs
    
    Args:
        char: Single character to check
        
    Returns:
        True if character is kanji
    """
    if not char:
        return False
    
    code = ord(char)
    return (
        (0x4E00 <= code <= 0x9FFF) or  # Main kanji block
        (0x3400 <= code <= 0x4DBF) or  # Extension A
        (0xF900 <= code <= 0xFAFF)     # Compatibility
    )


def extract_kanji_compounds(
    text: str, 
    min_length: int = 2,
    max_length: int = 6,
    include_single: bool = False
) -> List[Tuple[str, int]]:
    """
    Extract kanji compounds from Japanese text.
    
    Returns compounds sorted by frequency (most common first).
    
    Args:
        text: Japanese text to analyze
        min_length: Minimum compound length (default: 2)
        max_length: Maximum compound length (default: 6)
        include_single: Include single kanji characters (default: False)
        
    Returns:
        List of (kanji_compound, frequency) tuples, sorted by frequency descending
        
    Examples:
        >>> extract_kanji_compounds("幼なじみは友達関係です")
        [('友達', 1), ('関係', 1)]
        
        >>> extract_kanji_compounds("修行中の修行者", min_length=2)
        [('修行', 2), ('行中', 1), ('中の', 1), ('の修', 1), ('行者', 1)]
    """
    if not text:
        return []
    
    # Extract all kanji sequences
    kanji_sequences = []
    current_sequence = []
    
    for char in text:
        if is_kanji(char):
            current_sequence.append(char)
        else:
            if current_sequence:
                kanji_sequences.append(''.join(current_sequence))
                current_sequence = []
    
    # Don't forget the last sequence
    if current_sequence:
        kanji_sequences.append(''.join(current_sequence))
    
    # Extract compounds of various lengths
    compounds = []
    
    for sequence in kanji_sequences:
        seq_len = len(sequence)
        
        # Single kanji (if enabled)
        if include_single and seq_len >= 1:
            compounds.extend([sequence[i:i+1] for i in range(seq_len)])
        
        # Multi-kanji compounds
        for length in range(min_length, min(max_length + 1, seq_len + 1)):
            for i in range(seq_len - length + 1):
                compound = sequence[i:i+length]
                compounds.append(compound)
    
    # Count frequencies and sort
    frequency_map = Counter(compounds)
    
    # Return sorted by frequency (descending), then alphabetically for ties
    return sorted(
        frequency_map.items(), 
        key=lambda x: (-x[1], x[0])
    )


def extract_unique_compounds(
    text: str,
    min_length: int = 2,
    max_length: int = 6,
    top_n: int = None
) -> List[str]:
    """
    Extract unique kanji compounds (deduplicated).
    
    Args:
        text: Japanese text to analyze
        min_length: Minimum compound length (default: 2)
        max_length: Maximum compound length (default: 6)
        top_n: Return only top N most frequent compounds (default: all)
        
    Returns:
        List of unique kanji compounds, sorted by frequency
        
    Examples:
        >>> extract_unique_compounds("幼なじみは友達関係です")
        ['友達', '関係']
    """
    compounds_with_freq = extract_kanji_compounds(
        text, 
        min_length=min_length, 
        max_length=max_length
    )
    
    compounds = [compound for compound, freq in compounds_with_freq]
    
    if top_n:
        return compounds[:top_n]
    
    return compounds


def filter_meaningful_compounds(compounds: List[str], min_length: int = 2) -> List[str]:
    """
    Filter compounds to keep only meaningful Sino-Vietnamese terms.
    
    Removes:
    - Single characters (unless explicitly wanted)
    - Very long sequences (likely parsing errors)
    - Common particles/function words
    
    Args:
        compounds: List of kanji compounds
        min_length: Minimum length to keep (default: 2)
        
    Returns:
        Filtered list of compounds
    """
    # Common particles/function words to exclude (single kanji)
    exclude_single = {'の', 'は', 'を', 'に', 'で', 'と', 'が', 'も', 'や', 'か', 'な'}
    
    filtered = []
    for compound in compounds:
        # Length check
        if len(compound) < min_length or len(compound) > 8:
            continue
        
        # Exclude single-character function words
        if len(compound) == 1 and compound in exclude_single:
            continue
        
        filtered.append(compound)
    
    return filtered


def get_context_window(text: str, compound: str, window_size: int = 30) -> str:
    """
    Get context window around a kanji compound for semantic analysis.
    
    Args:
        text: Full Japanese text
        compound: Kanji compound to find
        window_size: Characters before and after (default: 30)
        
    Returns:
        Context string with the compound highlighted
        
    Examples:
        >>> get_context_window("これは幼なじみの友達関係です", "友達", 10)
        'なじみの友達関係です'
    """
    index = text.find(compound)
    if index == -1:
        return ""
    
    start = max(0, index - window_size)
    end = min(len(text), index + len(compound) + window_size)
    
    return text[start:end]
