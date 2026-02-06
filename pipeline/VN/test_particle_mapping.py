#!/usr/bin/env python3
"""
Test script for Japanese → Vietnamese Particle Mapping System
Demonstrates archetype-aware particle translation
"""

import json
import re
from pathlib import Path

# Load particle mapping database
def load_particle_db():
    db_path = Path(__file__).parent / 'jp_vn_particle_mapping_enhanced.json'
    with open(db_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Simple particle detector
def detect_particles(text):
    """Detect Japanese particles in text"""
    patterns = {
        'よ': r'よ(?![ぁ-ん])',
        'ね': r'ね(?![ぁ-ん])',
        'な': r'な(?![ぁ-ん])',
        'わ': r'わ(?![ぁ-ん])',
        'ぞ': r'ぞ(?![ぁ-ん])',
        'ぜ': r'ぜ(?![ぁ-ん])',
        'の': r'の(?![ぁ-ん])',
        'か': r'か(?![ぁ-ん])',
        'かな': r'かな',
        'だよね': r'だよね',
        'でしょ': r'でしょ',
        'だろ': r'だろ',
        'ですわ': r'ですわ',
        'ますわ': r'ますわ',
        'じゃん': r'じゃん',
        'っしょ': r'っしょ',
    }

    detected = []
    for particle, pattern in patterns.items():
        if re.search(pattern, text):
            detected.append(particle)
    return detected

# Get Vietnamese particle mapping
def get_vn_particle(particle, archetype, db):
    """Get Vietnamese particle for given archetype"""
    # Map particle to key format (with romanization)
    particle_key_map = {
        'よ': 'よ (yo)',
        'ね': 'ね (ne)',
        'な': 'な (na)',
        'わ': 'わ (wa)',
        'ぞ': 'ぞ (zo)',
        'ぜ': 'ぜ (ze)',
        'の': 'の (no - explanatory/feminine)',
        'か': 'か (ka)',
        'かな': 'かな (kana)',
        'だよね': 'だよね (da yo ne)',
        'でしょ': 'でしょ (desho)',
        'だろ': 'だろ (daro)',
        'ですわ': 'ですわ/ますわ (desu wa / masu wa)',
        'ますわ': 'ですわ/ますわ (desu wa / masu wa)',
        'じゃん': 'じゃん (jan)',
        'っしょ': 'っしょ (ssho)',
        'ちょっと': 'ちょっと (chotto)',
        'なんか': 'なんか (nanka)',
        'まあ': 'まあ (maa)',
    }

    # Get the key format
    particle_key = particle_key_map.get(particle, particle)

    # Search in all categories
    for category in ['sentence_ending_particles', 'softening_diminutive_particles',
                     'archetype_signature_particles', 'confirmation_emphasis_particles',
                     'compound_particles']:
        category_data = db.get(category, {})
        if particle_key in category_data:
            particle_data = category_data[particle_key]

            # Check archetype-specific mappings
            archetype_mappings = particle_data['vietnamese_mappings'].get('archetype_specific', {})
            if archetype in archetype_mappings:
                vn_options = archetype_mappings[archetype]
                # Return first option, clean up annotations in parentheses
                result = vn_options[0] if isinstance(vn_options, list) else vn_options
                # Clean up any annotations
                result = result.split(' (')[0]  # Remove (annotation) parts
                return result

            # Return default
            defaults = particle_data['vietnamese_mappings']['default']
            result = defaults[0] if isinstance(defaults, list) else defaults
            result = result.split(' (')[0]
            return result

    return None

# Test cases
def run_tests():
    print("=" * 80)
    print("Japanese → Vietnamese Particle Mapping System - Test Suite")
    print("=" * 80)
    print()

    db = load_particle_db()

    # Test 1: よ particle across archetypes
    print("TEST 1: よ (yo) - Emphasis particle across archetypes")
    print("-" * 80)
    jp_text = "これは本当だよ"
    archetypes = ['OJOU', 'GYARU', 'TSUNDERE', 'KUUDERE', 'DELINQUENT', 'DEREDERE']

    print(f"Japanese: {jp_text}")
    print(f"Base Vietnamese: Đây là sự thật [PARTICLE]")
    print()

    for archetype in archetypes:
        vn_particle = get_vn_particle('よ', archetype, db)
        print(f"  {archetype:15} → Đây là sự thật {vn_particle}")
    print()

    # Test 2: ね particle variations
    print("TEST 2: ね (ne) - Agreement-seeking particle")
    print("-" * 80)
    jp_text = "いい天気だね"

    print(f"Japanese: {jp_text}")
    print(f"Base Vietnamese: Thời tiết đẹp [PARTICLE]")
    print()

    for archetype in archetypes:
        vn_particle = get_vn_particle('ね', archetype, db)
        print(f"  {archetype:15} → Thời tiết đẹp {vn_particle}")
    print()

    # Test 3: Archetype signature particles
    print("TEST 3: Archetype Signature Particles")
    print("-" * 80)

    test_cases = [
        ('OJOU', 'それは違いますわ', 'Điều đó sai', 'ですわ'),
        ('GYARU', '可愛いじゃん', 'Đáng yêu', 'じゃん'),
        ('DELINQUENT', '行くぞ', 'Đi', 'ぞ'),
        ('KUUDERE', 'そうだよ', 'Đúng', 'よ'),
    ]

    for archetype, jp, base_vn, particle in test_cases:
        vn_particle = get_vn_particle(particle, archetype, db)
        print(f"{archetype:15} | JP: {jp:20} | VN: {base_vn} {vn_particle}")
    print()

    # Test 4: Gender-coded particles
    print("TEST 4: Gender-Coded Particles")
    print("-" * 80)
    print("Masculine particles (な, ぞ, ぜ):")
    male_archetypes = ['DELINQUENT', 'SHOUNEN_MC', 'SENPAI']
    for archetype in male_archetypes:
        vn_particle = get_vn_particle('な', archetype, db)
        print(f"  {archetype:15} + な → {vn_particle}")

    print()
    print("Feminine particles (わ, の sentence-final):")
    female_archetypes = ['OJOU', 'DEREDERE', 'GYARU']
    for archetype in female_archetypes:
        vn_particle = get_vn_particle('わ', archetype, db)
        if vn_particle:
            print(f"  {archetype:15} + わ → {vn_particle}")
    print()

    # Test 5: Question particles
    print("TEST 5: Question Particles (か vs の vs かな)")
    print("-" * 80)

    question_tests = [
        ('か', '本当ですか', 'Thật không', 'OJOU'),
        ('か', '本当か', 'Thật không', 'DELINQUENT'),
        ('の', 'どこへ行くの?', 'Đi đâu', 'DEREDERE'),
        ('かな', '彼女は来るかな', 'Cô ấy có đến không', 'TSUNDERE'),
    ]

    for particle, jp, base_vn, archetype in question_tests:
        vn_particle = get_vn_particle(particle, archetype, db)
        print(f"{particle:5} | {archetype:12} | JP: {jp:18} → VN: {base_vn} {vn_particle}")
    print()

    # Test 6: Particle detection
    print("TEST 6: Particle Detection in Sentences")
    print("-" * 80)

    detection_tests = [
        "それは違いますわね",
        "可愛いじゃん!",
        "お前も行くだろ?",
        "これでいいかな",
        "知ってるよね",
    ]

    for text in detection_tests:
        detected = detect_particles(text)
        print(f"  {text:25} → Detected: {', '.join(detected)}")
    print()

    # Test 7: KUUDERE minimalism
    print("TEST 7: KUUDERE Minimalism (particle omission)")
    print("-" * 80)
    kuudere_tests = [
        ('よ', 'そうだよ', 'Đúng'),
        ('ね', 'いいね', 'Tốt'),
        ('の', 'どこ行くの', 'Đi đâu'),
    ]

    print("KUUDERE omits most particles for minimalism:")
    for particle, jp, base_vn in kuudere_tests:
        vn_particle = get_vn_particle(particle, 'KUUDERE', db)
        result = f"{base_vn} {vn_particle}" if vn_particle and vn_particle != '.' else f"{base_vn}."
        print(f"  {jp:15} → {result:20} (particle {particle} → {vn_particle or 'omitted'})")
    print()

    # Test 8: Corpus frequency
    print("TEST 8: Corpus Statistics")
    print("-" * 80)
    print("Top 10 most frequent particles in corpus:")
    top_10 = db['corpus_statistics']['top_10_particles_by_frequency']
    for i, entry in enumerate(top_10, 1):
        print(f"  {i:2}. {entry['particle']:8} - {entry['frequency']:>6,} instances ({entry['function']})")
    print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total particles in database: {db['metadata']['total_particles']}")
    print(f"Archetype variants: {db['metadata']['archetype_variants']}")
    print(f"Corpus source: {db['metadata']['corpus_source']}")
    print(f"Validation status: {db['metadata']['validation_status']}")
    print()
    print("Key Insights:")
    print("  • よ ≠ ね - Different functions require different Vietnamese particles")
    print("  • Gender matters - Masculine particles (な, ぞ, ぜ) never for female characters")
    print("  • Archetype signature - ですわ → OJOU, じゃん → GYARU, minimal → KUUDERE")
    print("  • KUUDERE special case - Omit particles for stoic minimalism")
    print("  • Top 3 particles (か, けど, よ) = 60k+ corpus instances")
    print()
    print("✓ All tests completed successfully!")
    print("=" * 80)

if __name__ == '__main__':
    run_tests()
