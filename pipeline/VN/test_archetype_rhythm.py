#!/usr/bin/env python3
"""
Archetype-Driven Rhythm Checking - Usage Examples

Demonstrates how to use Vietnamese Grammar RAG with character archetypes
from manifest.json for rhythm-aware translation validation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.vietnamese_grammar_rag import VietnameseGrammarRAG


def example_1_warrior_character():
    """Example: Warrior character with staccato rhythm"""
    print("=" * 80)
    print("EXAMPLE 1: Warrior Character - Staccato Rhythm")
    print("=" * 80)
    
    rag = VietnameseGrammarRAG()
    
    # Character data from manifest.json
    character = {
        "name": "田中剣",
        "name_en": "Tanaka Ken",
        "personality_traits": ["disciplined", "combat_skilled", "tactical", "protective"],
        "archetype": "warrior_soldier"
    }
    
    # Detect archetype
    archetype = rag.detect_character_archetype(
        character["personality_traits"],
        character.get("archetype")
    )
    print(f"\n✓ Detected archetype: {archetype}")
    
    # Get rhythm profile
    profile = rag.get_archetype_rhythm_profile(archetype)
    print(f"✓ Rhythm profile: {profile['ideal_range'][0]}-{profile['ideal_range'][1]} words, max {profile['max_length']}")
    print(f"✓ Pattern: {profile['pattern']}")
    
    # Bad translation - too long for warrior
    bad_text = "Anh ta rút kiếm ra và nhìn kẻ địch và bước về phía trước với sự quyết tâm cao độ để bảo vệ những người đằng sau."
    
    print(f"\n❌ BAD TRANSLATION ({len(bad_text.split())} words):")
    print(f"   {bad_text}")
    
    violations = rag.check_rhythm_violations(bad_text, character_archetype=archetype)
    print(f"\n🔍 Found {len(violations)} violations:")
    for v in violations:
        print(f"   - {v['type']}: {v['word_count']} words (max {v['max_allowed']})")
        print(f"     Archetype expectation: {v.get('archetype_expectation', 'N/A')}")
        print(f"     Suggestion: {v['suggestion']}")
    
    # Good translation - warrior rhythm
    good_text = "Rút kiếm. Nhìn địch. Tiến. Bảo vệ."
    
    print(f"\n✅ GOOD TRANSLATION ({len(good_text.split())} words):")
    print(f"   {good_text}")
    
    violations = rag.check_rhythm_violations(good_text, character_archetype=archetype)
    print(f"\n✓ Clean! {len(violations)} violations")
    

def example_2_scholar_character():
    """Example: Scholar character with measured cadence"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Scholar Character - Measured Cadence")
    print("=" * 80)
    
    rag = VietnameseGrammarRAG()
    
    # Character data
    character = {
        "name": "白石美咲",
        "name_en": "Shiraishi Misaki",
        "personality_traits": ["intelligent", "analytical", "bookish", "methodical"],
    }
    
    # Detect archetype (no explicit, rely on traits)
    archetype = rag.detect_character_archetype(character["personality_traits"])
    print(f"\n✓ Auto-detected archetype: {archetype}")
    
    profile = rag.get_archetype_rhythm_profile(archetype)
    print(f"✓ Rhythm profile: {profile['ideal_range'][0]}-{profile['ideal_range'][1]} words")
    
    # Bad - too short for scholar
    bad_text = "Có ba cách. Mỗi cách có lỗi."
    
    print(f"\n❌ BAD TRANSLATION (too terse for scholar):")
    print(f"   {bad_text}")
    
    violations = rag.check_rhythm_violations(bad_text, character_archetype=archetype)
    print(f"\n🔍 Found {len(violations)} violations:")
    for v in violations:
        print(f"   - {v['type']}: {v['word_count']} words (ideal: {v.get('ideal_range', 'N/A')})")
        print(f"     Suggestion: {v['suggestion']}")
    
    # Good - measured scholarly rhythm
    good_text = "Vấn đề này có ba giải pháp khả thi. Mỗi giải pháp đều có điểm mạnh và yếu riêng. Chúng ta cần cân nhắc kỹ lưỡng trước khi quyết định."
    
    print(f"\n✅ GOOD TRANSLATION (measured, analytical):")
    print(f"   {good_text}")
    
    violations = rag.check_rhythm_violations(good_text, character_archetype=archetype)
    print(f"\n✓ {len(violations)} violations - scholarly rhythm maintained!")
    

def example_3_tsundere_character():
    """Example: Tsundere character with defensive then soft rhythm"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Tsundere Character - Defensive → Soft Rhythm")
    print("=" * 80)
    
    rag = VietnameseGrammarRAG()
    
    # Character data
    character = {
        "name": "山田愛子",
        "name_en": "Yamada Aiko",
        "personality_traits": ["tsundere", "emotionally_guarded", "prideful", "secretly_caring"],
    }
    
    archetype = rag.detect_character_archetype(character["personality_traits"])
    print(f"\n✓ Detected archetype: {archetype}")
    
    profile = rag.get_archetype_rhythm_profile(archetype)
    print(f"✓ Rhythm pattern: {profile['pattern']} ({profile['amputation_style']})")
    
    # Bad - smooth flow doesn't capture tsundere spikes
    bad_text = "Không phải vì cậu đâu nhé vì em chỉ làm nhiều quá thôi nên mang cho cậu."
    
    print(f"\n❌ BAD TRANSLATION (no emotional rhythm breaks):")
    print(f"   {bad_text}")
    
    # Good - spike-spike-soften rhythm
    good_text = "Không phải vì cậu. Đừng hiểu lầm. Chỉ là... Làm nhiều. Thế thôi."
    
    print(f"\n✅ GOOD TRANSLATION (tsundere rhythm):")
    print(f"   {good_text}")
    print(f"   Analysis: Sharp denial → Pause → Hesitation → Soft admission")
    

def example_4_kuudere_character():
    """Example: Kuudere character with ultra-minimal rhythm"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Kuudere Character - Ultra-Minimal Rhythm")
    print("=" * 80)
    
    rag = VietnameseGrammarRAG()
    
    # Character data
    character = {
        "name": "黒崎零",
        "name_en": "Kurosaki Rei",
        "personality_traits": ["stoic", "emotionless", "detached", "observant"],
    }
    
    archetype = rag.detect_character_archetype(character["personality_traits"])
    print(f"\n✓ Detected archetype: {archetype}")
    
    profile = rag.get_archetype_rhythm_profile(archetype)
    print(f"✓ Max sentence length: {profile['max_length']} words (ultra-short)")
    
    # Bad - too elaborate for kuudere
    bad_text = "Ừ thì em hiểu rồi và em sẽ đi với cậu."
    
    print(f"\n❌ BAD TRANSLATION (too many words):")
    print(f"   {bad_text}")
    
    # Good - absolute minimum
    good_text = "Ừ. Hiểu. Đi."
    
    print(f"\n✅ GOOD TRANSLATION (kuudere minimal):")
    print(f"   {good_text}")
    print(f"   Analysis: 1-word sentences. Zero elaboration. Pure kuudere.")
    

def example_5_prompt_injection():
    """Example: Generate archetype-aware translation prompt"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Archetype-Aware Prompt Injection")
    print("=" * 80)
    
    rag = VietnameseGrammarRAG()
    
    # Warrior character context
    context = {
        "character_archetype": "warrior_soldier",
        "character_name": "Ken"
    }
    
    print("\n📝 Generating prompt injection for warrior character...\n")
    
    prompt_injection = rag.generate_prompt_injection(context=context)
    
    # Show relevant sections
    lines = prompt_injection.split('\n')
    start_idx = None
    for i, line in enumerate(lines):
        if 'CHARACTER ARCHETYPE:' in line:
            start_idx = i
            break
    
    if start_idx:
        print("=" * 60)
        print('\n'.join(lines[start_idx:start_idx+20]))
        print("=" * 60)
    
    print("\n✓ This prompt injection will guide LLM to use warrior rhythm:")
    print("  - Short staccato sentences (3-10 words)")
    print("  - Minimal conjunctions")
    print("  - Action-focused vocabulary")
    print("  - Hard cuts instead of smooth transitions")


def example_6_mixed_archetypes():
    """Example: Text with multiple character archetypes"""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Multiple Characters - Different Rhythms")
    print("=" * 80)
    
    rag = VietnameseGrammarRAG()
    
    # Warrior dialogue
    warrior_text = "Rút kiếm. Chuẩn bị. Chiến đấu."
    print("\n🗡️  WARRIOR (Ken):")
    print(f"   {warrior_text}")
    violations = rag.check_rhythm_violations(warrior_text, character_archetype="warrior_soldier")
    print(f"   ✓ {len(violations)} violations")
    
    # Scholar response
    scholar_text = "Khoan đã. Chúng ta cần phân tích tình hình trước. Địch quân có thể đã đặt phục kích."
    print("\n📚 SCHOLAR (Misaki):")
    print(f"   {scholar_text}")
    violations = rag.check_rhythm_violations(scholar_text, character_archetype="scholar_intellectual")
    print(f"   ✓ {len(violations)} violations")
    
    # Tsundere interruption
    tsundere_text = "Không phải lo cho cậu đâu. Chỉ là... Chiến thuật hợp lý. Thế thôi."
    print("\n💢 TSUNDERE (Aiko):")
    print(f"   {tsundere_text}")
    violations = rag.check_rhythm_violations(tsundere_text, character_archetype="tsundere_guarded")
    print(f"   ✓ {len(violations)} violations")
    
    # Kuudere observation
    kuudere_text = "Địch. Phía đông. Ba người."
    print("\n❄️  KUUDERE (Rei):")
    print(f"   {kuudere_text}")
    violations = rag.check_rhythm_violations(kuudere_text, character_archetype="kuudere_stoic")
    print(f"   ✓ {len(violations)} violations")
    
    print("\n✓ Each character maintains their unique rhythm archetype!")


def main():
    """Run all examples"""
    print("\n" + "🎭" * 40)
    print("VIETNAMESE GRAMMAR RAG - ARCHETYPE-DRIVEN RHYTHM SYSTEM")
    print("Usage Examples with Character Personalities from manifest.json")
    print("🎭" * 40)
    
    example_1_warrior_character()
    example_2_scholar_character()
    example_3_tsundere_character()
    example_4_kuudere_character()
    example_5_prompt_injection()
    example_6_mixed_archetypes()
    
    print("\n" + "=" * 80)
    print("✅ All examples complete!")
    print("=" * 80)
    print("\nKey Takeaways:")
    print("  1. Different archetypes = different rhythm patterns")
    print("  2. personality_traits from manifest.json → auto-detect archetype")
    print("  3. Rhythm violations checked against archetype expectations")
    print("  4. Prompt injection includes archetype-specific guidance")
    print("  5. Multi-character scenes maintain unique rhythms per character")
    print("\n💡 Use explicit 'archetype' field in manifest.json to override auto-detection")
    print("💡 Add 'rhythm_profile.custom_max_length' for character-specific limits")
    print("\n")


if __name__ == "__main__":
    main()
