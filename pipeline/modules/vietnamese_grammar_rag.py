#!/usr/bin/env python3
"""
Vietnamese Grammar RAG Module
Retrieves and applies natural Vietnamese patterns during JP→VN translation.
Loaded automatically when target_language is set to 'vn' in config.yaml.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re


class VietnameseGrammarRAG:
    """RAG system for Vietnamese grammar patterns, particles, and anti-AI-ism rules."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize Vietnamese Grammar RAG module.
        
        Args:
            config_path: Optional path to vietnamese_grammar_rag.json.
                        If None, auto-detects from VN/ directory.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "VN" / "vietnamese_grammar_rag.json"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Load primary pattern sections
        self.ai_isms = self.config.get("sentence_structure_ai_isms", {}).get("patterns", [])
        self.dialogue_ai_isms = self.config.get("dialogue_ai_isms", {}).get("patterns", [])
        self.particle_system = self.config.get("particle_system", {})
        self.archetype_matrix = self.config.get("archetype_register_matrix", {}).get("archetypes", {})
        self.pronoun_tiers = self.config.get("pronoun_tiers", {})
        self.rtas_evolution = self.config.get("rtas_particle_evolution", {}).get("scale", [])
        self.frequency_thresholds = self.config.get("frequency_thresholds", {}).get("thresholds_per_1000_words", {})
        
        # Build lookup indices for fast access
        self._build_indices()
    
    def _build_indices(self):
        """Build lookup indices for particle and archetype queries."""
        # Index particles by type
        self.question_particles = {p["particle"]: p for p in self.particle_system.get("question_particles", [])}
        self.affirmation_particles = {p["particle"]: p for p in self.particle_system.get("affirmation_particles", [])}
        self.softening_particles = {p["particle"]: p for p in self.particle_system.get("softening_particles", [])}
        self.exclamation_particles = {p["particle"]: p for p in self.particle_system.get("exclamation_particles", [])}
        self.combination_patterns = self.particle_system.get("combination_patterns", [])
        
        # All particles combined for quick lookup
        self.all_particles = {}
        self.all_particles.update(self.question_particles)
        self.all_particles.update(self.affirmation_particles)
        self.all_particles.update(self.softening_particles)
        self.all_particles.update(self.exclamation_particles)
    
    # =========================================================================
    # PARTICLE SELECTION
    # =========================================================================
    
    def get_particles_for_archetype(self, archetype: str) -> Dict[str, List[str]]:
        """
        Get allowed and forbidden particles for a character archetype.
        
        Args:
            archetype: Character archetype (e.g., 'TSUNDERE', 'OJOU', 'GYARU')
            
        Returns:
            Dict with 'formal', 'casual', 'forbidden' particle lists
        """
        archetype_upper = archetype.upper()
        if archetype_upper not in self.archetype_matrix:
            return {
                "formal": [],
                "casual": [],
                "forbidden": [],
                "preferred_register": "neutral"
            }
        
        arch_config = self.archetype_matrix[archetype_upper]
        return {
            "formal": arch_config.get("formal_particles", []),
            "casual": arch_config.get("casual_particles", []),
            "forbidden": arch_config.get("forbidden_particles", []),
            "preferred_register": arch_config.get("preferred_register", "neutral"),
            "state_override": arch_config.get("state_override", {}),
            "note": arch_config.get("note", "")
        }
    
    def get_particles_for_rtas(self, rtas: float) -> Dict:
        """
        Get appropriate particle style based on RTAS score.
        
        Args:
            rtas: Relationship Tension & Affection Score (1.0-5.0)
            
        Returns:
            Dict with particle_style and examples
        """
        for tier in self.rtas_evolution:
            rtas_range = tier.get("rtas_range", "0-5.0")
            low, high = map(float, rtas_range.split("-"))
            
            if low <= rtas <= high:
                return {
                    "particle_style": tier.get("particle_style", "neutral"),
                    "examples": tier.get("examples", [])
                }
        
        return {"particle_style": "neutral", "examples": []}
    
    def suggest_particles(self, archetype: str, rtas: float, 
                         sentence_type: str = "statement",
                         gender: str = "neutral") -> List[Dict]:
        """
        Suggest appropriate particles for a dialogue line.
        
        Args:
            archetype: Character archetype
            rtas: RTAS score
            sentence_type: 'question', 'statement', 'exclamation', 'suggestion'
            gender: 'male', 'female', 'neutral'
            
        Returns:
            List of particle suggestions with priority scores
        """
        archetype_config = self.get_particles_for_archetype(archetype)
        rtas_config = self.get_particles_for_rtas(rtas)
        
        forbidden = set(archetype_config.get("forbidden", []))
        suggestions = []
        
        # Select particle pool based on sentence type
        if sentence_type == "question":
            pool = self.question_particles
        elif sentence_type == "exclamation":
            pool = self.exclamation_particles
        elif sentence_type == "suggestion":
            pool = self.softening_particles
        else:
            pool = self.affirmation_particles
        
        for particle, config in pool.items():
            # Skip forbidden particles
            if particle in forbidden:
                continue
            
            # Check RTAS range
            rtas_range = config.get("rtas_range", [0, 5.0])
            if not (rtas_range[0] <= rtas <= rtas_range[1]):
                continue
            
            # Check gender preference
            particle_gender = config.get("gender", "both")
            if particle_gender != "both":
                if gender == "male" and particle_gender == "female_leaning":
                    continue
                if gender == "female" and particle_gender == "male_leaning":
                    continue
            
            # Calculate priority score
            score = 5  # Base score
            
            # Boost if in archetype's preferred list
            if particle in archetype_config.get("casual", []):
                score += 3
            if particle in archetype_config.get("formal", []):
                score += 2
            
            # Boost if archetype affinity matches
            affinity = config.get("archetype_affinity", [])
            if archetype.upper() in [a.upper() for a in affinity]:
                score += 3
            
            suggestions.append({
                "particle": particle,
                "score": score,
                "register": config.get("register", "neutral"),
                "examples": config.get("examples", [])
            })
        
        # Sort by score descending
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:5]  # Return top 5
    
    # =========================================================================
    # PRONOUN SELECTION
    # =========================================================================
    
    def get_pronoun_pair(self, relationship_type: str, tier: int = 2, 
                        rtas: float = None) -> Dict[str, str]:
        """
        Get appropriate pronoun pair for a relationship.
        
        Args:
            relationship_type: 'male_friendship', 'female_friendship', 
                              'mixed_gender', 'romantic', 'family'
            tier: Intimacy tier (1-3) for friendships
            rtas: RTAS score for romantic relationships
            
        Returns:
            Dict with 'self' and 'other' pronouns
        """
        if relationship_type == "family":
            # Family is handled separately - return family override note
            return {
                "note": "FAMILY_OVERRIDE - Use explicit family pronouns",
                "mappings": self.pronoun_tiers.get("family_override", {}).get("mappings", {})
            }
        
        if relationship_type == "romantic" and rtas is not None:
            # Use RTAS scale
            rtas_scale = self.pronoun_tiers.get("romantic_rtas_scale", {})
            for range_key, pronouns in rtas_scale.items():
                low, high = map(float, range_key.split("-"))
                if low <= rtas <= high:
                    return pronouns
        
        # Friendship tiers
        tier_map = {
            "male_friendship": self.pronoun_tiers.get("male_friendship", {}),
            "female_friendship": self.pronoun_tiers.get("female_friendship", {}),
            "mixed_gender": self.pronoun_tiers.get("mixed_gender_friendship", {})
        }
        
        friendship_config = tier_map.get(relationship_type, {})
        tier_key = f"tier_{tier}_{'distant' if tier == 1 else 'close' if tier == 2 else 'bros'}"
        
        for key, config in friendship_config.items():
            if f"tier_{tier}" in key:
                return config
        
        return {"self": "Tôi", "other": "Anh/Chị"}  # Default fallback
    
    # =========================================================================
    # AI-ISM DETECTION
    # =========================================================================
    
    def detect_ai_isms(self, vietnamese_text: str) -> List[Dict]:
        """
        Detect AI-ism patterns in Vietnamese text.
        
        Args:
            vietnamese_text: Translated Vietnamese text
            
        Returns:
            List of detected AI-isms with corrections
        """
        detections = []
        seen_phrases = set()  # Track what we've already flagged
        
        for pattern in self.ai_isms:
            # Check forbidden phrases
            for forbidden in pattern.get("forbidden", []):
                if forbidden.lower() in vietnamese_text.lower():
                    # Avoid duplicate detections
                    if forbidden.lower() in seen_phrases:
                        continue
                    seen_phrases.add(forbidden.lower())
                    
                    # Find the correction if available
                    corrections = pattern.get("corrections", {})
                    suggestion = None
                    for bad, good in corrections.items():
                        if forbidden.lower() in bad.lower():
                            suggestion = good
                            break
                    
                    detections.append({
                        "pattern_id": pattern.get("id", "unknown"),
                        "severity": pattern.get("severity", "medium"),
                        "found": forbidden,
                        "rule": pattern.get("rule", ""),
                        "suggestion": suggestion
                    })
            
            # Skip regex if we already found this pattern type via forbidden list
            pattern_id = pattern.get("id", "unknown")
            if any(d["pattern_id"] == pattern_id for d in detections):
                continue
            
            # Check regex patterns (only if no forbidden phrase matched)
            if "detection_regex" in pattern:
                regex = pattern["detection_regex"]
                matches = re.findall(regex, vietnamese_text, re.IGNORECASE)
                for match in matches:
                    # Handle tuple results from regex groups
                    if isinstance(match, tuple):
                        match = "".join(m for m in match if m)
                    
                    match_lower = match.lower().strip()
                    if match_lower and match_lower not in seen_phrases:
                        seen_phrases.add(match_lower)
                        detections.append({
                            "pattern_id": pattern_id,
                            "severity": pattern.get("severity", "medium"),
                            "found": match.strip(),
                            "rule": pattern.get("rule", ""),
                            "suggestion": "Review and restructure"
                        })
        
        return detections
    
    def check_frequency_violations(self, vietnamese_text: str) -> List[Dict]:
        """
        Check for frequency threshold violations.
        
        Args:
            vietnamese_text: Translated Vietnamese text
            
        Returns:
            List of frequency violations
        """
        word_count = len(vietnamese_text.split())
        scale_factor = word_count / 1000
        
        violations = []
        
        for marker, max_count in self.frequency_thresholds.items():
            # Count occurrences (case insensitive)
            count = vietnamese_text.lower().count(marker.lower())
            allowed = max(1, int(max_count * scale_factor))
            
            if count > allowed:
                violations.append({
                    "marker": marker,
                    "found": count,
                    "allowed": allowed,
                    "excess": count - allowed
                })
        
        return violations
    
    # =========================================================================
    # PROMPT INJECTION
    # =========================================================================
    
    def generate_prompt_injection(self, context: Dict = None) -> str:
        """
        Generate prompt injection block for translator.
        
        Args:
            context: Optional context dict with:
                    - archetype: Character archetype
                    - rtas: RTAS score
                    - scene_type: Scene type (dialogue, action, etc.)
                    
        Returns:
            Formatted prompt injection string
        """
        injection = "\n## Vietnamese Grammar RAG - Anti-AI-ism Rules\n\n"
        
        # Always include critical AI-isms
        injection += "### FORBIDDEN Patterns (Eliminate on sight):\n"
        for pattern in self.ai_isms[:4]:  # Top 4 critical patterns
            injection += f"- **{pattern.get('id', '')}**: {pattern.get('rule', '')}\n"
            if pattern.get("corrections"):
                example = list(pattern["corrections"].items())[0]
                injection += f"  - ❌ `{example[0]}` → ✅ `{example[1]}`\n"
        
        # Include archetype-specific rules if provided
        if context and context.get("archetype"):
            arch = context["archetype"]
            arch_config = self.get_particles_for_archetype(arch)
            
            injection += f"\n### Character Voice: {arch}\n"
            injection += f"- **Register**: {arch_config.get('preferred_register', 'neutral')}\n"
            
            if arch_config.get("casual"):
                injection += f"- **Allowed particles**: {', '.join(arch_config['casual'])}\n"
            if arch_config.get("forbidden"):
                injection += f"- **FORBIDDEN particles**: {', '.join(arch_config['forbidden'])}\n"
        
        # Include RTAS-based guidance if provided
        if context and context.get("rtas"):
            rtas = context["rtas"]
            rtas_config = self.get_particles_for_rtas(rtas)
            injection += f"\n### RTAS {rtas}: {rtas_config.get('particle_style', 'neutral')}\n"
            if rtas_config.get("examples"):
                injection += f"- Example: `{rtas_config['examples'][0]}`\n"
        
        # Include particle combination patterns
        injection += "\n### Natural Particle Combinations:\n"
        for combo in self.combination_patterns[:3]:
            injection += f"- `{combo['combination']}`: {combo['function']} → \"{combo['example']}\"\n"
        
        return injection
    
    def generate_dialogue_guidelines(self, characters: List[Dict]) -> str:
        """
        Generate dialogue-specific guidelines for multiple characters.
        
        Args:
            characters: List of character dicts with 'name', 'archetype', 'gender'
            
        Returns:
            Formatted guidelines string
        """
        guidelines = "\n## Character-Specific Dialogue Rules\n\n"
        
        for char in characters:
            name = char.get("name", "Unknown")
            archetype = char.get("archetype", "universal")
            gender = char.get("gender", "neutral")
            
            config = self.get_particles_for_archetype(archetype)
            
            guidelines += f"### {name} ({archetype})\n"
            guidelines += f"- Register: {config.get('preferred_register', 'neutral')}\n"
            
            if config.get("casual"):
                guidelines += f"- Use: {', '.join(config['casual'][:3])}\n"
            if config.get("forbidden"):
                guidelines += f"- NEVER: {', '.join(config['forbidden'][:3])}\n"
            
            guidelines += "\n"
        
        return guidelines
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def validate_translation(self, vietnamese_text: str, context: Dict = None) -> Dict:
        """
        Comprehensive validation of Vietnamese translation.
        
        Args:
            vietnamese_text: Translated text to validate
            context: Optional context for archetype/RTAS checks
            
        Returns:
            Validation report dict
        """
        report = {
            "ai_isms": self.detect_ai_isms(vietnamese_text),
            "frequency_violations": self.check_frequency_violations(vietnamese_text),
            "score": 100,
            "issues": []
        }
        
        # Calculate score deductions
        for ai_ism in report["ai_isms"]:
            severity_penalty = {"critical": 10, "high": 5, "medium": 2}.get(
                ai_ism.get("severity", "medium"), 2
            )
            report["score"] -= severity_penalty
            report["issues"].append(f"AI-ism: {ai_ism['found']}")
        
        for violation in report["frequency_violations"]:
            report["score"] -= violation["excess"] * 2
            report["issues"].append(f"Frequency: '{violation['marker']}' x{violation['found']}")
        
        report["score"] = max(0, report["score"])
        report["passed"] = report["score"] >= 70
        
        return report


# =========================================================================
# USAGE EXAMPLE
# =========================================================================

if __name__ == "__main__":
    rag = VietnameseGrammarRAG()
    
    print("=== Vietnamese Grammar RAG Loaded ===")
    print(f"AI-ism patterns: {len(rag.ai_isms)}")
    print(f"Dialogue AI-isms: {len(rag.dialogue_ai_isms)}")
    print(f"Archetypes: {len(rag.archetype_matrix)}")
    print(f"Particles: {len(rag.all_particles)}")
    
    print("\n=== Particle Suggestions for TSUNDERE (RTAS 3.8) ===")
    suggestions = rag.suggest_particles("TSUNDERE", 3.8, "statement", "female")
    for s in suggestions:
        print(f"  {s['particle']}: score={s['score']}, register={s['register']}")
    
    print("\n=== Pronoun Pair for Close Male Friends ===")
    pronouns = rag.get_pronoun_pair("male_friendship", tier=2)
    print(f"  Self: {pronouns.get('self', 'N/A')}, Other: {pronouns.get('other', 'N/A')}")
    
    print("\n=== AI-ism Detection ===")
    test_text = "Một cảm giác bất an tràn ngập căn phòng. Anh ấy nói một cách trang trọng."
    detections = rag.detect_ai_isms(test_text)
    print(f"Found {len(detections)} AI-isms:")
    for d in detections:
        print(f"  ⚠️  [{d['severity']}] {d['found']}")
        if d.get("suggestion"):
            print(f"     💡 {d['suggestion']}")
    
    print("\n=== Prompt Injection Sample ===")
    injection = rag.generate_prompt_injection({
        "archetype": "GYARU",
        "rtas": 4.2
    })
    print(injection[:500] + "...")
