"""
RTAS Calculator - Derives voice settings from manifest.json via fuzzy matching.

Uses rtas_config.json patterns to calculate:
- RTAS score (1.0-5.0) from relationship + personality
- Contraction rate from RTAS tier
- Forbidden/required vocabulary from archetype match
"""

import json
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class VoiceSettings:
    """Calculated voice settings for a character."""
    character_id: str
    rtas_score: float
    contraction_rate: int  # 0-100
    archetype: str
    forbidden_vocab: Set[str] = field(default_factory=set)
    required_vocab: Set[str] = field(default_factory=set)
    sentence_length: str = "normal"  # short, normal, long
    filler_density: str = "normal"  # low, normal, high
    
    def to_prompt_instruction(self) -> str:
        """Generate prompt instruction for this character's voice."""
        lines = [
            f"CHARACTER: {self.character_id}",
            f"  RTAS: {self.rtas_score:.1f} ({self._rtas_description()})",
            f"  Contraction rate: {self.contraction_rate}%",
        ]
        if self.forbidden_vocab:
            lines.append(f"  FORBIDDEN: {', '.join(sorted(self.forbidden_vocab)[:10])}")
        if self.required_vocab:
            lines.append(f"  USE: {', '.join(sorted(self.required_vocab)[:5])}")
        return "\n".join(lines)
    
    def _rtas_description(self) -> str:
        if self.rtas_score < 2.0:
            return "formal/hostile"
        elif self.rtas_score < 3.0:
            return "professional/neutral"
        elif self.rtas_score < 4.0:
            return "friendly/casual"
        elif self.rtas_score < 4.5:
            return "intimate/close"
        else:
            return "peak intimacy"


class RTASCalculator:
    """
    Calculate RTAS and voice settings from manifest.json character metadata.
    
    Algorithm:
    1. Load character profiles from manifest
    2. Fuzzy-match relationship_to_protagonist → baseline shift
    3. Fuzzy-match personality_traits → personality modifier
    4. If keigo_switch.[speaking_to][target] exists → direct RTAS override
    5. Derive contraction rate and vocab constraints from archetype
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize with config. Falls back to default config location.
        """
        if config_path is None:
            # Default: pipeline/config/rtas_config.json
            config_path = Path(__file__).parent.parent / "config" / "rtas_config.json"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            logger.warning(f"RTAS config not found at {config_path}, using defaults")
            self.config = self._default_config()
        
        self.baseline = self.config.get("baseline", 3.0)
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for fuzzy matching."""
        self.relationship_patterns = []
        rel_patterns = self.config.get("relationship_patterns", {})
        # Handle both nested {"patterns": {...}} and flat {...} formats
        if "patterns" in rel_patterns:
            rel_patterns = rel_patterns["patterns"]
        for pattern, values in rel_patterns.items():
            if pattern.startswith("_"):
                continue
            regex = re.compile(pattern, re.IGNORECASE)
            self.relationship_patterns.append((regex, values))
        
        self.personality_patterns = []
        pers_patterns = self.config.get("personality_modifiers", {})
        if "patterns" in pers_patterns:
            pers_patterns = pers_patterns["patterns"]
        for pattern, values in pers_patterns.items():
            if pattern.startswith("_"):
                continue
            regex = re.compile(pattern, re.IGNORECASE)
            self.personality_patterns.append((regex, values))
        
        self.keigo_patterns = []
        keigo_patterns = self.config.get("keigo_switch_mappings", {})
        if "patterns" in keigo_patterns:
            keigo_patterns = keigo_patterns["patterns"]
        for pattern, values in keigo_patterns.items():
            if pattern.startswith("_"):
                continue
            regex = re.compile(pattern, re.IGNORECASE)
            self.keigo_patterns.append((regex, values))
        
        self.archetype_patterns = []
        for pattern, values in self.config.get("archetype_forbidden_vocab", {}).items():
            if not pattern.startswith("_"):
                regex = re.compile(pattern, re.IGNORECASE)
                self.archetype_patterns.append((regex, values))
    
    def calculate_from_manifest(self, manifest: dict) -> Dict[str, VoiceSettings]:
        """
        Calculate VoiceSettings for all characters in manifest.
        
        Args:
            manifest: Loaded manifest.json dict
            
        Returns:
            Dict mapping character_id → VoiceSettings
        """
        profiles = manifest.get("metadata_en", {}).get("character_profiles", {})
        
        results = {}
        for char_id, profile in profiles.items():
            settings = self._calculate_for_character(char_id, profile)
            results[char_id] = settings
            logger.debug(f"[RTAS] {char_id}: {settings.rtas_score:.1f} ({settings.archetype})")
        
        return results
    
    def _calculate_for_character(self, char_id: str, profile: dict) -> VoiceSettings:
        """Calculate RTAS and voice settings for a single character."""
        
        # 1. Start with baseline
        rtas = self.baseline
        contraction_shift = 0
        
        # 2. Match relationship_to_protagonist
        relationship = profile.get("relationship_to_protagonist", "")
        for pattern, values in self.relationship_patterns:
            if pattern.search(relationship):
                rtas += values.get("baseline_shift", 0)
                # Clamp to pattern's min/max if specified
                rtas = max(rtas, values.get("min", 1.0))
                rtas = min(rtas, values.get("max", 5.0))
                break
        
        # 3. Match personality_traits
        personality = profile.get("personality_traits", "")
        detected_archetype = "neutral"
        for pattern, values in self.personality_patterns:
            if pattern.search(personality):
                contraction_shift += values.get("contraction_rate_shift", 0)
                detected_archetype = pattern.pattern.split("|")[0]  # First term
                break
        
        # 4. Get forbidden/required vocab from archetype
        forbidden = set()
        required = set()
        for pattern, values in self.archetype_patterns:
            if pattern.search(personality) or pattern.search(detected_archetype):
                forbidden.update(values.get("forbidden", []))
                required.update(values.get("required", []))
                break
        
        # 5. Calculate contraction rate from RTAS tier
        contraction_tiers = self.config.get("contraction_tiers", {})
        base_rate = 60  # default
        for tier_range, tier_config in contraction_tiers.items():
            if not tier_range.startswith("_"):
                low, high = map(float, tier_range.split("-"))
                if low <= rtas <= high:
                    base_rate = tier_config.get("base_rate", 60)
                    break
        
        final_contraction = max(0, min(100, base_rate + contraction_shift))
        
        return VoiceSettings(
            character_id=char_id,
            rtas_score=round(rtas, 1),
            contraction_rate=final_contraction,
            archetype=detected_archetype,
            forbidden_vocab=forbidden,
            required_vocab=required
        )
    
    def calculate_pairwise_rtas(
        self, 
        manifest: dict, 
        speaker_id: str, 
        addressee_id: str
    ) -> float:
        """
        Calculate RTAS for a specific speaker→addressee pair.
        
        Uses keigo_switch.speaking_to[addressee] if available,
        otherwise falls back to general RTAS.
        """
        profiles = manifest.get("metadata_en", {}).get("character_profiles", {})
        speaker = profiles.get(speaker_id, {})
        
        # Check for direct keigo_switch override
        keigo_switch = speaker.get("keigo_switch", {})
        speaking_to = keigo_switch.get("speaking_to", {})
        
        # Try to find addressee by various name formats
        addressee_profile = profiles.get(addressee_id, {})
        addressee_names = [
            addressee_id,
            addressee_profile.get("nickname", ""),
            addressee_profile.get("full_name", "").split()[0]  # First name
        ]
        
        for name in addressee_names:
            if name and name in speaking_to:
                register = speaking_to[name]
                # Fuzzy match register → RTAS
                for pattern, values in self.keigo_patterns:
                    if pattern.search(register):
                        return values.get("rtas_tier", 3.0)
        
        # Fallback to speaker's general RTAS
        settings = self._calculate_for_character(speaker_id, speaker)
        return settings.rtas_score
    
    def generate_prompt_context(self, manifest: dict) -> str:
        """
        Generate RTAS context for injection into translation prompt.
        
        Returns:
            Formatted string with all character voice settings
        """
        settings = self.calculate_from_manifest(manifest)
        
        lines = ["=== CHARACTER VOICE SETTINGS (AUTO-DERIVED FROM MANIFEST) ==="]
        for char_id, setting in settings.items():
            lines.append(setting.to_prompt_instruction())
            lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def _default_config() -> dict:
        """Return minimal default config if no file found."""
        return {
            "baseline": 3.0,
            "relationship_patterns": {"patterns": {}},
            "personality_modifiers": {"patterns": {}},
            "keigo_switch_mappings": {"patterns": {}},
            "contraction_tiers": {
                "1.0-2.9": {"base_rate": 30},
                "3.0-3.9": {"base_rate": 60},
                "4.0-5.0": {"base_rate": 85}
            },
            "archetype_forbidden_vocab": {}
        }


# CLI for testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python rtas_calculator.py <manifest.json>")
        sys.exit(1)
    
    manifest_path = Path(sys.argv[1])
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    calc = RTASCalculator()
    settings = calc.calculate_from_manifest(manifest)
    
    print("\n=== RTAS CALCULATION RESULTS ===\n")
    for char_id, setting in settings.items():
        print(setting.to_prompt_instruction())
        print()
