#!/usr/bin/env python3
"""
Update Novel 1a87 to v3.8 Schema with Vietnamese Support
Scans JP raw content and generates complete character metadata
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Base paths
WORK_DIR = Path("/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/2nd cutest v4 JP_20260208_1a87")
MANIFEST_PATH = WORK_DIR / "manifest.json"
METADATA_VN_PATH = WORK_DIR / "metadata_vn.json"

# Character data extracted from JP raw analysis
CHARACTERS = {
    "前原真樹": {
        "name_vn": "Maehara Maki",
        "nickname": None,
        "age": 16,
        "gender": "male",
        "role": "protagonist",
        "description": "Introverted high school student who transformed from a loner to a devoted boyfriend. Currently dating Asanagi Umi.",
        "is_pov_character": True,
        "speech_pattern": "masculine_casual",
        "keigo_switch": {
            "default_register": "casual",
            "situations": {
                "with_girlfriend": "casual",
                "with_friends": "casual",
                "with_teachers": "polite",
                "internal_monologue": "casual"
            }
        },
        "personality_traits": ["introverted", "self-deprecating", "loyal", "thoughtful", "anxious"],
        "first_appearance_chapter": 1
    },
    "朝凪海": {
        "name_vn": "Asanagi Umi",
        "nickname": None,
        "age": 16,
        "gender": "female",
        "role": "deuteragonist",
        "description": "Academically gifted student ranked in top 5 of her year. Dating Maehara Maki. Caring but slightly possessive girlfriend.",
        "is_pov_character": False,
        "speech_pattern": "feminine_polite",
        "keigo_switch": {
            "default_register": "casual",
            "situations": {
                "with_boyfriend": "casual",
                "with_friends": "casual",
                "with_teachers": "polite",
                "when_teasing": "casual"
            }
        },
        "personality_traits": ["intelligent", "caring", "possessive", "athletic", "protective"],
        "first_appearance_chapter": 1
    },
    "天海夕": {
        "name_vn": "Amami Yuu",
        "nickname": None,
        "age": 16,
        "gender": "female",
        "role": "supporting",
        "description": "Popular blonde-haired girl (quarter-foreign). Best friend of Asanagi Umi. Bright, energetic, and kind-hearted.",
        "is_pov_character": False,
        "speech_pattern": "energetic",
        "keigo_switch": {
            "default_register": "casual",
            "situations": {
                "with_friends": "casual",
                "with_teachers": "casual",
                "when_cheerful": "casual"
            }
        },
        "personality_traits": ["cheerful", "popular", "kind", "energetic", "optimistic"],
        "first_appearance_chapter": 1
    },
    "新田新奈": {
        "name_vn": "Nitta Nina",
        "nickname": "ニナち (Nina-chi)",
        "age": 16,
        "gender": "female",
        "role": "supporting",
        "description": "Straightforward friend of the group. Observant and slightly blunt in her speech.",
        "is_pov_character": False,
        "speech_pattern": "casual",
        "keigo_switch": {
            "default_register": "casual",
            "situations": {
                "with_friends": "casual",
                "with_teachers": "casual"
            }
        },
        "personality_traits": ["straightforward", "observant", "blunt", "loyal"],
        "first_appearance_chapter": 1
    },
    "関望": {
        "name_vn": "Seki Nozomu",
        "nickname": None,
        "age": 16,
        "gender": "male",
        "role": "supporting",
        "description": "Athletic male friend of Maehara. Good-natured and part of the friend group.",
        "is_pov_character": False,
        "speech_pattern": "masculine_casual",
        "keigo_switch": {
            "default_register": "casual",
            "situations": {
                "with_friends": "casual",
                "with_teachers": "casual"
            }
        },
        "personality_traits": ["athletic", "good-natured", "friendly", "casual"],
        "first_appearance_chapter": 1
    },
    "荒江渚": {
        "name_vn": "Arae Nagisa",
        "nickname": None,
        "age": 16,
        "gender": "female",
        "role": "antagonist",
        "description": "New classmate with rebellious attitude. Standoffish and cynical. Has light brown wavy hair, tanned skin, and piercings.",
        "is_pov_character": False,
        "speech_pattern": "casual",
        "keigo_switch": {
            "default_register": "casual",
            "situations": {
                "with_teachers": "dismissive",
                "with_classmates": "cold"
            }
        },
        "personality_traits": ["rebellious", "standoffish", "cynical", "perceptive", "defensive"],
        "first_appearance_chapter": 2
    }
}

def load_current_manifest():
    """Load existing manifest.json"""
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_current_metadata_vn():
    """Load existing metadata_vn.json"""
    with open(METADATA_VN_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def create_v38_manifest(current_manifest):
    """Create v3.8 schema manifest with Vietnamese support"""
    
    # Create new v3.8 structure
    v38_manifest = {
        "version": "3.8",
        "volume_id": current_manifest["volume_id"],
        "created_at": current_manifest["created_at"],
        "updated_at": datetime.now().isoformat(),
        
        "metadata": {
            "series": {
                "title": {
                    "japanese": "クラスで２番目に可愛い女の子と友だちになった",
                    "vietnamese": "Tôi Kết Bạn Với Cô Gái Xinh Thứ Hai Trong Lớp",
                    "romaji": "Kura de 2-banme ni Kawaii Onnanoko to Tomodachi ni Natta"
                },
                "author": "たかた (Takata)",
                "illustrator": "Unknown",
                "publisher": "株式会社KADOKAWA",
                "publication_date": "2026-02-08",
                "isbn": "",
                "volume_number": 4,
                "total_volumes": None
            },
            "translation": {
                "translator": "MTL Studio v3.8",
                "translation_date": datetime.now().strftime("%Y-%m-%d"),
                "source_language": "ja",
                "target_language": "vi",
                "translation_notes": "Vietnamese translation maintaining Japanese name order (family-first). Preserves honorifics in dialogue for cultural authenticity."
            },
            "characters": [],
            "content_info": {
                "genre": ["romcom", "school_life", "slice_of_life"],
                "tags": ["romance", "comedy", "high_school", "relationships", "friendship"],
                "content_warnings": [],
                "target_audience": "young_adult",
                "synopsis": "Volume 4 of the romantic comedy series following Maehara Maki and his girlfriend Asanagi Umi as they navigate their second year of high school in separate classes. New challenges arise with the introduction of problem student Arae Nagisa.",
                "chapter_count": 9,
                "word_count": 4357,
                "has_illustrations": True,
                "illustration_count": 8
            },
            "translation_guidance": {
                "genres": ["romcom", "school_life", "slice_of_life"],
                "translator_notes": {
                    "priority_patterns": [
                        "contemporary_teen_voice",
                        "romantic_tension",
                        "comedic_timing",
                        "internal_monologue_rhythm"
                    ],
                    "tone": "Light-hearted romantic comedy with slice-of-life elements. First-person POV from introverted protagonist.",
                    "character_voice_priorities": {
                        "Maehara Maki": "Casual masculine, self-deprecating internal monologue, devoted boyfriend",
                        "Asanagi Umi": "Refined but casual, caring with possessive undertones",
                        "Amami Yuu": "Bright and energetic, cheerful speech patterns",
                        "Arae Nagisa": "Dismissive and cynical, rebellious attitude"
                    },
                    "avoid": [
                        "AI-isms: 'couldn't help but', 'seemed to', 'little did I know'",
                        "Over-explaining emotions already shown through actions",
                        "Formal contractions in Vietnamese (not applicable)"
                    ]
                }
            }
        },
        
        # Vietnamese-specific localization
        "localization_vn": {
            "name_order": "family_first",
            "name_order_note": "All character names maintain Japanese order: Family name + Given name",
            "honorific_preservation": True,
            "honorific_note": "Preserve -san, -kun, -chan, -senpai in dialogue for cultural authenticity",
            "character_names_vn": {},
            "cultural_notes": {
                "school_system": "Japanese high school system (年生 = năm học)",
                "cultural_references": "Preserve Japanese cultural context",
                "class_system": "Class numbering (組 = lớp)",
                "sports_events": "クラスマッチ = Class Match (giải thi đấu liên lớp)"
            }
        },
        
        # Preserve existing structure
        "chapters": current_manifest["chapters"],
        "assets": current_manifest["assets"],
        "toc": current_manifest["toc"],
        "ruby_names": current_manifest["ruby_names"],
        "pipeline_state": current_manifest["pipeline_state"]
    }
    
    # Add character profiles
    for jp_name, char_data in CHARACTERS.items():
        character = {
            "name": {
                "japanese": jp_name,
                "vietnamese": char_data["name_vn"],
                "display": char_data["name_vn"]
            },
            "nickname": char_data["nickname"],
            "age": char_data["age"],
            "gender": char_data["gender"],
            "role": char_data["role"],
            "description": char_data["description"],
            "is_pov_character": char_data["is_pov_character"],
            "speech_pattern": char_data["speech_pattern"],
            "keigo_switch": char_data["keigo_switch"],
            "personality_traits": char_data["personality_traits"],
            "first_appearance_chapter": char_data["first_appearance_chapter"]
        }
        v38_manifest["metadata"]["characters"].append(character)
        
        # Add to Vietnamese name mapping
        v38_manifest["localization_vn"]["character_names_vn"][jp_name] = char_data["name_vn"]
    
    # Update metadata_en for backward compatibility
    v38_manifest["metadata_en"] = current_manifest["metadata_en"]
    
    return v38_manifest

def update_metadata_vn(current_metadata):
    """Update metadata_vn.json with character names"""
    
    current_metadata["character_names_vn"] = {}
    for jp_name, char_data in CHARACTERS.items():
        current_metadata["character_names_vn"][jp_name] = char_data["name_vn"]
    
    current_metadata["name_order"] = "family_first"
    current_metadata["name_order_note"] = "All character names follow Japanese order: Family name + Given name"
    
    return current_metadata

def main():
    print("🔄 Loading current manifest and metadata...")
    current_manifest = load_current_manifest()
    current_metadata_vn = load_current_metadata_vn()
    
    print("✨ Creating v3.8 schema manifest...")
    v38_manifest = create_v38_manifest(current_manifest)
    
    print("📝 Updating Vietnamese metadata...")
    updated_metadata_vn = update_metadata_vn(current_metadata_vn)
    
    print("💾 Writing updated files...")
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(v38_manifest, f, ensure_ascii=False, indent=2)
    
    with open(METADATA_VN_PATH, 'w', encoding='utf-8') as f:
        json.dump(updated_metadata_vn, f, ensure_ascii=False, indent=2)
    
    print("\n✅ Successfully updated to v3.8 schema!")
    print(f"   - {len(CHARACTERS)} characters added")
    print(f"   - All names in family-first order")
    print(f"   - Vietnamese-specific arrays injected")
    print(f"\n📁 Files updated:")
    print(f"   - {MANIFEST_PATH}")
    print(f"   - {METADATA_VN_PATH}")
    print(f"\n💾 Backups created:")
    print(f"   - {MANIFEST_PATH}.backup")
    print(f"   - {METADATA_VN_PATH}.backup")

if __name__ == "__main__":
    main()
