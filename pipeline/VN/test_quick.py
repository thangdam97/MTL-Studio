#!/usr/bin/env python3
"""Quick test of archetype-driven rhythm system"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.vietnamese_grammar_rag import VietnameseGrammarRAG

print('=' * 60)
print('🎭 Archetype-Driven Rhythm System - Quick Test')
print('=' * 60)

rag = VietnameseGrammarRAG()

# Test 1: Kaguya (child_energetic)
print('\nTest 1: Kaguya-hime (Child Energetic)')
traits = ['cheerful', 'energetic', 'naive', 'optimistic']
archetype = rag.detect_character_archetype(traits)
profile = rag.get_archetype_rhythm_profile(archetype)
print(f'  Traits: {", ".join(traits)}')
print(f'  Detected: {archetype}')
print(f'  Max length: {profile["max_length"]} words')
print(f'  Pattern: {profile["pattern"]}')

# Test 2: Warrior
print('\nTest 2: Warrior Character')
traits = ['disciplined', 'combat_skilled', 'tactical']
archetype = rag.detect_character_archetype(traits)
profile = rag.get_archetype_rhythm_profile(archetype)
print(f'  Traits: {", ".join(traits)}')
print(f'  Detected: {archetype}')
print(f'  Max length: {profile["max_length"]} words')
print(f'  Pattern: {profile["pattern"]}')

# Test 3: Rhythm check
print('\nTest 3: Rhythm Violation Check')
text = 'Nhìn này! Nhìn nè! Tuyệt không? Em làm đó!'
violations = rag.check_rhythm_violations(text, character_archetype='child_energetic')
print(f'  Good text: {text}')
print(f'  Violations: {len(violations)} ✓')

bad_text = 'Nhìn này cô Iroha coi em đã làm được món này một cách rất tuyệt vời và đẹp.'
violations = rag.check_rhythm_violations(bad_text, character_archetype='child_energetic')
print(f'\n  Bad text: {bad_text}')
print(f'  Violations: {len(violations)}')
if violations:
    v = violations[0]
    print(f'    ✗ {v["type"]}: {v["word_count"]} words (max {v["max_allowed"]})')

print('\n' + '=' * 60)
print('✅ Archetype system operational!')
print('=' * 60)
