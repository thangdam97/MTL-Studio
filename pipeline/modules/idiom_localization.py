"""
Idiom Localization Decision Module
Simple, lightweight system that trusts Gemini's zero-shot idiom knowledge
Provides WHEN to localize, Gemini decides HOW
"""

import json
from pathlib import Path
from typing import Dict, Optional, List


class IdiomLocalizationMatrix:
    """
    Determines when to activate idiom localization based on:
    - Character archetype
    - Scene context
    - Literacy technique triggers
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with idiom localization matrix config

        Args:
            config_path: Path to idiom_localization_matrix.json
                        (defaults to config/idiom_localization_matrix.json)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "idiom_localization_matrix.json"

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.archetype_bias = self.config["activation_rules"]["archetype_bias"]["rules"]
        self.context_multipliers = self.config["activation_rules"]["context_multipliers"]["rules"]
        self.literacy_triggers = self.config["activation_rules"]["literacy_technique_triggers"]["rules"]
        self.prompt_template = self.config["prompt_injection_template"]["template"]
        self.weight_interpretations = self.config["prompt_injection_template"]["weight_interpretations"]

    def calculate_localization_weight(
        self,
        archetype: str,
        scene_context: Optional[str] = None,
        is_dialogue: bool = True,
        has_sentence_particle: bool = False,
        is_emotional_reaction: bool = False
    ) -> Dict[str, any]:
        """
        Calculate final localization weight and generate Gemini instructions

        Args:
            archetype: Character archetype (gyaru, tsundere, ojou_sama, etc.)
            scene_context: Scene description or keywords
            is_dialogue: Whether this is a dialogue line
            has_sentence_particle: Whether Japanese has particle (よ、ね、な)
            is_emotional_reaction: Whether this is an emotional idiom

        Returns:
            Dict with:
                - weight: Final localization weight (0.0-1.0)
                - instruction: Gemini prompt injection text
                - rationale: Why this weight was chosen
        """

        # 1. Get base weight from archetype
        archetype_lower = archetype.lower().replace(" ", "_")
        archetype_data = self.archetype_bias.get(
            archetype_lower,
            self.archetype_bias.get("default_casual")
        )
        base_weight = archetype_data["localization_weight"]
        rationale_parts = [archetype_data["rationale"]]
        examples = archetype_data.get("examples", [])

        # 2. Apply context multiplier
        context_multiplier = 1.0
        context_matched = None
        if scene_context:
            scene_lower = scene_context.lower()
            for context_name, context_rule in self.context_multipliers.items():
                keywords = context_rule["trigger_keywords"]
                if any(keyword in scene_lower for keyword in keywords):
                    context_multiplier = context_rule["multiplier"]
                    context_matched = context_name
                    rationale_parts.append(context_rule["rationale"])
                    break

        adjusted_weight = base_weight * context_multiplier

        # 3. Check literacy technique triggers
        literacy_trigger = None
        gemini_instruction_parts = []

        if is_dialogue and self.literacy_triggers.get("natural_dialogue_flow"):
            trigger = self.literacy_triggers["natural_dialogue_flow"]
            adjusted_weight = max(adjusted_weight, trigger["localization_weight"])
            literacy_trigger = "natural_dialogue_flow"
            gemini_instruction_parts.append(trigger["gemini_instruction"])
            rationale_parts.append(trigger["rationale"])

        if has_sentence_particle and self.literacy_triggers.get("pseudo_particle_compatibility"):
            trigger = self.literacy_triggers["pseudo_particle_compatibility"]
            adjusted_weight = max(adjusted_weight, trigger["localization_weight"])
            literacy_trigger = "pseudo_particle_compatibility"
            gemini_instruction_parts.append(trigger["gemini_instruction"])
            rationale_parts.append(trigger["rationale"])
            examples.extend(trigger.get("examples", []))

        if is_emotional_reaction and self.literacy_triggers.get("show_dont_tell"):
            trigger = self.literacy_triggers["show_dont_tell"]
            adjusted_weight = max(adjusted_weight, trigger["localization_weight"])
            literacy_trigger = "show_dont_tell"
            gemini_instruction_parts.append(trigger["gemini_instruction"])
            rationale_parts.append(trigger["rationale"])
            examples.extend(trigger.get("examples", []))

        # Cap weight at 1.0
        final_weight = min(adjusted_weight, 1.0)

        # 4. Generate Gemini instruction
        weight_range_key = self._get_weight_range_key(final_weight)
        weight_interpretation = self.weight_interpretations[weight_range_key]

        gemini_instruction = "\n".join(gemini_instruction_parts) if gemini_instruction_parts else \
            "Translate idioms naturally according to the localization weight."

        prompt_injection = self.prompt_template.format(
            archetype=archetype,
            weight=f"{final_weight:.2f}",
            interpretation=weight_interpretation,
            scene_context=scene_context or "General",
            literacy_trigger=literacy_trigger or "None",
            gemini_instruction=gemini_instruction,
            examples="\n".join(f"  - {ex}" for ex in examples[:3])  # Top 3 examples
        )

        return {
            "weight": final_weight,
            "instruction": prompt_injection,
            "rationale": " | ".join(rationale_parts),
            "components": {
                "base_weight": base_weight,
                "archetype": archetype_lower,
                "context_multiplier": context_multiplier,
                "context_matched": context_matched,
                "literacy_trigger": literacy_trigger,
                "final_weight": final_weight
            }
        }

    def _get_weight_range_key(self, weight: float) -> str:
        """Map weight to interpretation range key"""
        if weight < 0.3:
            return "0.0_to_0.3"
        elif weight < 0.5:
            return "0.3_to_0.5"
        elif weight < 0.7:
            return "0.5_to_0.7"
        elif weight < 0.85:
            return "0.7_to_0.85"
        else:
            return "0.85_to_1.0"

    def generate_prompt_injection(
        self,
        character_name: str,
        archetype: str,
        scene_description: Optional[str] = None,
        is_dialogue: bool = True
    ) -> str:
        """
        Generate prompt injection text for Gemini translation

        Args:
            character_name: Name of speaking character
            archetype: Character archetype
            scene_description: Optional scene context
            is_dialogue: Whether this is dialogue

        Returns:
            String to inject into Gemini translation prompt
        """
        result = self.calculate_localization_weight(
            archetype=archetype,
            scene_context=scene_description,
            is_dialogue=is_dialogue
        )

        return result["instruction"]


# Example usage
if __name__ == "__main__":
    matrix = IdiomLocalizationMatrix()

    # Test case 1: Gyaru in comedic scene with particle
    print("=== Test 1: Gyaru in Comedic Scene ===")
    result = matrix.calculate_localization_weight(
        archetype="gyaru",
        scene_context="funny comedic moment with joke",
        is_dialogue=True,
        has_sentence_particle=True
    )
    print(f"Weight: {result['weight']:.2f}")
    print(f"Rationale: {result['rationale']}")
    print(f"\nInstruction:\n{result['instruction'][:200]}...")

    # Test case 2: Ojou-sama in serious scene
    print("\n=== Test 2: Ojou-sama in Serious Scene ===")
    result = matrix.calculate_localization_weight(
        archetype="ojou_sama",
        scene_context="serious important moment",
        is_dialogue=True,
        has_sentence_particle=False
    )
    print(f"Weight: {result['weight']:.2f}")
    print(f"Rationale: {result['rationale']}")

    # Test case 3: Tsundere with emotional reaction
    print("\n=== Test 3: Tsundere Emotional Reaction ===")
    result = matrix.calculate_localization_weight(
        archetype="tsundere",
        scene_context="romantic confession",
        is_dialogue=True,
        has_sentence_particle=True,
        is_emotional_reaction=True
    )
    print(f"Weight: {result['weight']:.2f}")
    print(f"Rationale: {result['rationale']}")
    print(f"Components: {result['components']}")
