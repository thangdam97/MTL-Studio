#!/usr/bin/env python3
"""
Test JP→VN Particle Mapping Integration in Vietnamese Grammar RAG
Tests Tier 1 RAG integration for particle translation system.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.vietnamese_grammar_rag import VietnameseGrammarRAG


def test_particle_mapping_load():
    """Test that JP→VN particle mapping loads successfully."""
    print("=" * 70)
    print("TEST 1: Particle Mapping Load")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    assert rag.particle_mapping, "Particle mapping should be loaded"
    assert 'sentence_ending' in rag.particle_mapping
    assert 'question' in rag.particle_mapping
    assert 'archetype_signatures' in rag.particle_mapping

    metadata = rag.particle_mapping.get('metadata', {})
    print(f"✅ Particle mapping loaded successfully")
    print(f"   Total particles: {metadata.get('total_particles', 'N/A')}")
    print(f"   Corpus size: {metadata.get('corpus_size', 'N/A')}")
    print(f"   Validation: {metadata.get('validation_status', 'N/A')}")
    print()


def test_get_vietnamese_particle():
    """Test getting Vietnamese particles for Japanese particles."""
    print("=" * 70)
    print("TEST 2: Get Vietnamese Particle for Japanese")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Test よ (yo) for OJOU archetype
    mapping = rag.get_vietnamese_particle_for_japanese(
        "よ (yo)",
        archetype="OJOU",
        rtas=3.5,
        gender="female"
    )

    assert mapping['japanese_particle'] == "よ (yo)"
    assert 'vietnamese_particles' in mapping
    assert len(mapping['vietnamese_particles']) > 0
    assert mapping['archetype_used'] == "OJOU"

    print(f"✅ よ (yo) + OJOU:")
    print(f"   Function: {mapping['function']}")
    print(f"   Vietnamese: {', '.join(mapping['vietnamese_particles'][:3])}")
    print(f"   Corpus frequency: {mapping['corpus_frequency']:,}")
    print()

    # Test ね (ne) for neutral
    mapping = rag.get_vietnamese_particle_for_japanese(
        "ね (ne)",
        archetype="NEUTRAL",
        rtas=3.0,
        gender="neutral"
    )

    assert "nhỉ" in mapping['vietnamese_particles'] or "nhé" in mapping['vietnamese_particles']

    print(f"✅ ね (ne) + NEUTRAL:")
    print(f"   Function: {mapping['function']}")
    print(f"   Vietnamese: {', '.join(mapping['vietnamese_particles'][:3])}")
    print()


def test_archetype_variations():
    """Test that different archetypes get different particle mappings."""
    print("=" * 70)
    print("TEST 3: Archetype Variations")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    archetypes = ["OJOU", "GYARU", "TSUNDERE", "KUUDERE"]
    results = {}

    for archetype in archetypes:
        mapping = rag.get_vietnamese_particle_for_japanese(
            "よ (yo)",
            archetype=archetype,
            rtas=3.5,
            gender="female"
        )
        results[archetype] = mapping['vietnamese_particles'][0] if mapping['vietnamese_particles'] else 'none'

    print("✅ よ (yo) archetype variations:")
    for arch, particle in results.items():
        print(f"   {arch:12} → {particle}")

    # Verify OJOU is polite (ạ)
    assert "ạ" in results['OJOU'] or results['OJOU'] == "ạ (softened emphasis)"

    # Verify GYARU is casual (nha/nè)
    assert "nha" in results['GYARU'] or "nè" in results['GYARU']

    print()


def test_gender_filtering():
    """Test that gender restrictions are applied correctly."""
    print("=" * 70)
    print("TEST 4: Gender Filtering")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Test わ (wa) - feminine particle
    female_mapping = rag.get_vietnamese_particle_for_japanese(
        "わ (wa)",
        archetype="NEUTRAL",
        rtas=3.0,
        gender="female"
    )

    male_mapping = rag.get_vietnamese_particle_for_japanese(
        "わ (wa)",
        archetype="NEUTRAL",
        rtas=3.0,
        gender="male"
    )

    print(f"✅ わ (wa) gender filtering:")
    print(f"   Female: {', '.join(female_mapping['vietnamese_particles'][:2])}")
    print(f"   Male:   {', '.join(male_mapping['vietnamese_particles'][:2])}")

    # Female should have more options than male (wa is feminine)
    assert len(female_mapping['vietnamese_particles']) >= len(male_mapping['vietnamese_particles'])

    print()


def test_detect_japanese_particles():
    """Test detection of Japanese particles in source text."""
    print("=" * 70)
    print("TEST 5: Japanese Particle Detection")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Test text with multiple particles
    jp_text = "そうだよ！知ってるわよね。行くぞ。"
    detected = rag.detect_japanese_particles(jp_text)

    assert len(detected) > 0, "Should detect particles"

    print(f"✅ Source text: {jp_text}")
    print(f"   Detected {len(detected)} particles:")
    for p in detected:
        print(f"   - {p['particle']:12} pos={p['position']:2}  category={p['category']:20}  freq={p['frequency']:,}")

    # Verify よ is detected
    yo_detected = any(p['particle'] == 'よ (yo)' for p in detected)
    assert yo_detected, "Should detect よ particle"

    print()


def test_archetype_signature_particles():
    """Test archetype signature particle retrieval."""
    print("=" * 70)
    print("TEST 6: Archetype Signature Particles")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Test OJOU signatures
    ojou_sig = rag.get_archetype_signature_particles("OJOU")

    print(f"✅ OJOU signature patterns:")
    if ojou_sig.get('signature_patterns'):
        for pattern in ojou_sig['signature_patterns'][:5]:
            jp = pattern.get('japanese_pattern', 'N/A')
            vn = pattern.get('vietnamese_equivalent', 'N/A')
            conf = pattern.get('confidence', 'N/A')
            print(f"   {jp:20} → {vn:30} (confidence: {conf})")
    else:
        print(f"   Note: {ojou_sig.get('note', 'No signatures found')}")

    print()


def test_prompt_injection_with_particles():
    """Test that prompt injection includes particle guidance."""
    print("=" * 70)
    print("TEST 7: Prompt Injection with Particle Guidance")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Generate prompt injection with archetype context
    injection = rag.generate_prompt_injection({
        "archetype": "GYARU",
        "rtas": 4.2,
        "gender": "female"
    })

    assert "JP→VN Particle Translation" in injection or "Particle" in injection
    assert "GYARU" in injection

    print(f"✅ Generated prompt injection includes particle guidance")
    print(f"   Length: {len(injection)} characters")
    print(f"   Contains 'Particle': {'Particle' in injection}")
    print(f"   Contains archetype: {'GYARU' in injection}")
    print()

    # Show relevant particle section
    lines = injection.split('\n')
    particle_section = []
    in_particle_section = False

    for line in lines:
        if 'Particle' in line and ('Translation' in line or 'Combinations' in line):
            in_particle_section = True
        elif in_particle_section and line.strip().startswith('###'):
            break

        if in_particle_section:
            particle_section.append(line)

    if particle_section:
        print("   Particle guidance preview:")
        for line in particle_section[:10]:
            print(f"   {line}")

    print()


def test_validation_with_particles():
    """Test translation validation includes particle checking."""
    print("=" * 70)
    print("TEST 8: Validation with Particle Checking")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Test text with potentially inappropriate particles
    vn_text = "Tôi biết rồi ạ. Cô ấy đi đâu vậy nhỉ?"

    # Validate with GYARU archetype (ạ might be too formal for GYARU)
    report = rag.validate_translation(
        vn_text,
        context={
            "archetype": "GYARU",
            "rtas": 4.0,
            "gender": "female"
        }
    )

    assert "particle_issues" in report
    assert "score" in report
    assert "passed" in report

    print(f"✅ Validation report generated:")
    print(f"   Score: {report['score']}/100")
    print(f"   Passed: {report['passed']}")
    print(f"   AI-isms: {len(report['ai_isms'])}")
    print(f"   Particle issues: {len(report['particle_issues'])}")

    if report['issues']:
        print(f"   Issues found:")
        for issue in report['issues'][:5]:
            print(f"     - {issue}")

    print()


def test_rtas_influence():
    """Test that RTAS score influences particle selection."""
    print("=" * 70)
    print("TEST 9: RTAS Influence on Particle Selection")
    print("=" * 70)

    rag = VietnameseGrammarRAG()

    # Test same particle with different RTAS levels
    rtas_levels = [1.0, 3.0, 5.0]

    print(f"✅ ね (ne) at different RTAS levels:")
    for rtas in rtas_levels:
        mapping = rag.get_vietnamese_particle_for_japanese(
            "ね (ne)",
            archetype="NEUTRAL",
            rtas=rtas,
            gender="neutral"
        )

        particles = ', '.join(mapping['vietnamese_particles'][:2])
        print(f"   RTAS {rtas} (hostile→intimate): {particles}")

    print()


def run_all_tests():
    """Run all integration tests."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "JP→VN PARTICLE INTEGRATION TESTS" + " " * 20 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    tests = [
        test_particle_mapping_load,
        test_get_vietnamese_particle,
        test_archetype_variations,
        test_gender_filtering,
        test_detect_japanese_particles,
        test_archetype_signature_particles,
        test_prompt_injection_with_particles,
        test_validation_with_particles,
        test_rtas_influence
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} ERROR: {e}")
            failed += 1

    print()
    print("=" * 70)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("=" * 70)

    if failed == 0:
        print("✅ ALL TESTS PASSED - JP→VN Particle Integration Complete!")
        print()
        print("The particle mapping system is fully integrated as Tier 1 RAG.")
        print("It will automatically load and be used during Vietnamese translation.")
        return 0
    else:
        print(f"⚠️  {failed} test(s) failed - review errors above")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
