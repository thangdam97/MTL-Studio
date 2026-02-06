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

    def __init__(self, config_path: str = None, particle_mapping_path: str = None):
        """
        Initialize Vietnamese Grammar RAG module.

        Args:
            config_path: Optional path to vietnamese_grammar_rag.json.
                        If None, auto-detects from VN/ directory.
            particle_mapping_path: Optional path to jp_vn_particle_mapping_enhanced.json.
                                  If None, auto-detects from VN/ directory.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "VN" / "vietnamese_grammar_rag.json"

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Load JP→VN particle mapping (Tier 1 RAG)
        if particle_mapping_path is None:
            particle_mapping_path = Path(__file__).parent.parent / "VN" / "jp_vn_particle_mapping_enhanced.json"

        self.particle_mapping = {}
        if Path(particle_mapping_path).exists():
            with open(particle_mapping_path, 'r', encoding='utf-8') as f:
                particle_data = json.load(f)
                # Extract all particle categories
                self.particle_mapping = {
                    'sentence_ending': particle_data.get('sentence_ending_particles', {}),
                    'question': particle_data.get('question_particles', {}),
                    'softening': particle_data.get('softening_particles', {}),
                    'confirmation': particle_data.get('confirmation_particles', {}),
                    'archetype_signatures': particle_data.get('archetype_signature_particles', {}),
                    'compound': particle_data.get('compound_particles', {}),
                    'metadata': particle_data.get('metadata', {})
                }

        # Load primary pattern sections
        self.ai_isms = self.config.get("sentence_structure_ai_isms", {}).get("patterns", [])
        self.dialogue_ai_isms = self.config.get("dialogue_ai_isms", {}).get("patterns", [])
        self.particle_system = self.config.get("particle_system", {})
        self.archetype_matrix = self.config.get("archetype_register_matrix", {}).get("archetypes", {})
        self.pronoun_tiers = self.config.get("pronoun_tiers", {})
        self.rtas_evolution = self.config.get("rtas_particle_evolution", {}).get("scale", [])
        self.frequency_thresholds = self.config.get("frequency_thresholds", {}).get("thresholds_per_1000_words", {})
        self.rhythm_rules = self.config.get("rhythm_rules", {})

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
    # JP→VN PARTICLE MAPPING (TIER 1 RAG)
    # =========================================================================

    def detect_japanese_particles(self, japanese_text: str) -> List[Dict]:
        """
        Detect Japanese sentence-ending particles in source text.

        Args:
            japanese_text: Japanese source text to analyze

        Returns:
            List of detected particles with positions and categories
        """
        if not self.particle_mapping or not japanese_text:
            return []

        detected = []

        # Search all particle categories
        for category_name, particles in self.particle_mapping.items():
            if category_name == 'metadata':
                continue

            for jp_particle, particle_data in particles.items():
                # Handle compound particles with regex
                if '(' in jp_particle:
                    # Extract base form from notation like よ (yo)
                    base_form = jp_particle.split('(')[0].strip()
                else:
                    base_form = jp_particle

                # Find all occurrences
                pattern = re.escape(base_form)
                for match in re.finditer(pattern, japanese_text):
                    detected.append({
                        'particle': jp_particle,
                        'position': match.start(),
                        'category': category_name,
                        'function': particle_data.get('function', ''),
                        'frequency': particle_data.get('corpus_frequency', 0)
                    })

        # Sort by position
        detected.sort(key=lambda x: x['position'])
        return detected

    def get_vietnamese_particle_for_japanese(
        self,
        jp_particle: str,
        archetype: str = "NEUTRAL",
        rtas: float = 3.0,
        gender: str = "neutral",
        context: str = ""
    ) -> Dict:
        """
        Get Vietnamese particle mapping for a Japanese particle.

        Args:
            jp_particle: Japanese particle (e.g., 'よ', 'ね', 'わ')
            archetype: Character archetype (OJOU, TSUNDERE, GYARU, etc.)
            rtas: RTAS score (0.0-5.0)
            gender: Character gender ('male', 'female', 'neutral')
            context: Additional context for disambiguation

        Returns:
            Dict with Vietnamese particle suggestions and metadata
        """
        if not self.particle_mapping:
            return {
                'vietnamese_particles': [],
                'error': 'Particle mapping not loaded'
            }

        # Search all categories for the Japanese particle
        particle_data = None
        category = None

        for cat_name, particles in self.particle_mapping.items():
            if cat_name == 'metadata':
                continue
            if jp_particle in particles:
                particle_data = particles[jp_particle]
                category = cat_name
                break

        if not particle_data:
            return {
                'vietnamese_particles': [],
                'error': f'Japanese particle "{jp_particle}" not found in database'
            }

        # Get Vietnamese mappings
        vn_mappings = particle_data.get('vietnamese_mappings', {})

        # Start with default mappings
        suggestions = vn_mappings.get('default', [])

        # Apply archetype-specific mappings
        archetype_mappings = vn_mappings.get('archetype_specific', {})
        archetype_upper = archetype.upper()

        if archetype_upper in archetype_mappings:
            archetype_specific = archetype_mappings[archetype_upper]
            # Archetype-specific mappings take priority
            suggestions = archetype_specific + suggestions

        # Apply gender filters
        gender_restrictions = particle_data.get('gender_restrictions', {})
        if gender == 'male' and 'male_forbidden' in gender_restrictions:
            forbidden = gender_restrictions['male_forbidden']
            suggestions = [s for s in suggestions if not any(f in s for f in forbidden)]
        elif gender == 'female' and 'female_forbidden' in gender_restrictions:
            forbidden = gender_restrictions['female_forbidden']
            suggestions = [s for s in suggestions if not any(f in s for f in forbidden)]

        # Apply RTAS filtering
        rtas_guidance = vn_mappings.get('rtas_guidance', {})
        if rtas_guidance:
            if rtas < 2.0 and 'hostile_cold' in rtas_guidance:
                suggestions = rtas_guidance['hostile_cold'] + suggestions
            elif rtas >= 4.0 and 'intimate_warm' in rtas_guidance:
                suggestions = rtas_guidance['intimate_warm'] + suggestions

        # Remove duplicates while preserving order
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        return {
            'japanese_particle': jp_particle,
            'function': particle_data.get('function', ''),
            'category': category,
            'vietnamese_particles': unique_suggestions[:5],  # Top 5 suggestions
            'corpus_frequency': particle_data.get('corpus_frequency', 0),
            'archetype_used': archetype_upper,
            'rtas_used': rtas,
            'gender_used': gender,
            'usage_notes': particle_data.get('usage_notes', ''),
            'common_mistakes': particle_data.get('common_mistakes', [])
        }

    def get_archetype_signature_particles(self, archetype: str) -> Dict:
        """
        Get signature Japanese→Vietnamese particle patterns for an archetype.

        Args:
            archetype: Character archetype

        Returns:
            Dict with signature patterns and detection rules
        """
        if not self.particle_mapping:
            return {}

        archetype_sigs = self.particle_mapping.get('archetype_signatures', {})
        archetype_upper = archetype.upper()

        if archetype_upper in archetype_sigs:
            return archetype_sigs[archetype_upper]

        return {
            'signature_patterns': [],
            'archetype': archetype_upper,
            'note': 'No signature patterns defined for this archetype'
        }

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
    # RHYTHM ANALYSIS
    # =========================================================================
    
    def detect_character_archetype(self, personality_traits: List[str], explicit_archetype: str = None) -> str:
        """
        Detect character archetype from personality traits for rhythm adaptation.
        
        Args:
            personality_traits: List of character personality traits from manifest
            explicit_archetype: Optional explicit archetype override
            
        Returns:
            Archetype name (warrior_soldier, scholar_intellectual, etc.)
        """
        if explicit_archetype:
            return explicit_archetype
        
        archetype_detection = self.rhythm_rules.get("archetype_detection", {})
        priority_traits = archetype_detection.get("priority_traits", {})
        min_overlap = archetype_detection.get("minimum_trait_overlap", 2)
        
        # Calculate trait overlap for each archetype
        scores = {}
        for archetype, required_traits in priority_traits.items():
            overlap = len(set(personality_traits) & set(required_traits))
            if overlap >= min_overlap:
                scores[archetype] = overlap
        
        # Return highest scoring archetype
        if scores:
            return max(scores, key=scores.get)
        
        return archetype_detection.get("fallback", "narrator_default")
    
    def get_archetype_rhythm_profile(self, archetype: str) -> Dict:
        """
        Get rhythm profile for specific character archetype.
        
        Args:
            archetype: Character archetype name
            
        Returns:
            Dict with rhythm profile settings
        """
        character_archetypes = self.rhythm_rules.get("character_archetypes", {})
        archetype_data = character_archetypes.get(archetype, character_archetypes.get("narrator_default", {}))
        return archetype_data.get("rhythm_profile", {})
    
    def check_rhythm_violations(self, vietnamese_text: str, character_archetype: str = None) -> List[Dict]:
        """
        Check for Vietnamese rhythm and flow violations.
        
        Vietnamese thrives on short, punchy sentences with natural syllable rhythm.
        Long sequential Japanese sentences need "amputation" for Vietnamese flow.
        Character archetype determines expected rhythm pattern.
        
        Args:
            vietnamese_text: Translated Vietnamese text
            character_archetype: Optional character archetype (warrior_soldier, scholar_intellectual, etc.)
            
        Returns:
            List of rhythm violations with archetype-aware suggestions
        """
        violations = []
        rhythm_patterns = self.rhythm_rules.get("patterns", [])
        
        # Get archetype-specific rhythm profile
        if character_archetype:
            rhythm_profile = self.get_archetype_rhythm_profile(character_archetype)
            max_length = rhythm_profile.get("max_length", 25)
            ideal_range = rhythm_profile.get("ideal_range", [8, 20])
            amputation_style = rhythm_profile.get("amputation_style", "contextual")
        else:
            max_length = self.rhythm_rules.get("max_sentence_length", 25)
            ideal_range = self.rhythm_rules.get("ideal_sentence_range", [8, 20])
            amputation_style = "contextual"
        
        # Split into sentences
        sentences = re.split(r'[.!?。！？]', vietnamese_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        for idx, sentence in enumerate(sentences):
            words = sentence.split()
            word_count = len(words)
            
            # Check sentence length against archetype expectations
            if word_count > max_length:
                violation = {
                    "type": "sentence_too_long",
                    "sentence_index": idx,
                    "word_count": word_count,
                    "max_allowed": max_length,
                    "ideal_range": ideal_range,
                    "suggestion": f"Break into 2-3 shorter sentences. {amputation_style.replace('_', ' ').title()} expected.",
                    "severity": "medium"
                }
                
                if character_archetype:
                    violation["archetype"] = character_archetype
                    violation["archetype_expectation"] = f"{character_archetype.replace('_', ' ').title()} rhythm: {ideal_range[0]}-{ideal_range[1]} words"
                
                violations.append(violation)
            
            # Check for rhythm-breaking patterns
            for pattern in rhythm_patterns:
                pattern_regex = pattern.get("detection_regex", "")
                if pattern_regex and re.search(pattern_regex, sentence, re.IGNORECASE):
                    violations.append({
                        "type": pattern.get("id", "rhythm_violation"),
                        "sentence_index": idx,
                        "rule": pattern.get("rule", ""),
                        "suggestion": pattern.get("fix", ""),
                        "severity": pattern.get("severity", "medium")
                    })
            
            # Check syllable rhythm (Vietnamese monosyllabic nature)
            # Long compound words break rhythm
            long_words = [w for w in words if len(w) > 15]
            if long_words:
                violations.append({
                    "type": "syllable_rhythm_break",
                    "sentence_index": idx,
                    "long_words": long_words,
                    "suggestion": "Vietnamese prefers short syllables - break compound phrases",
                    "severity": "low"
                })
        
        # Check paragraph-level rhythm (alternating short/long pattern)
        if len(sentences) >= 3:
            sentence_lengths = [len(s.split()) for s in sentences]
            # Detect monotonous rhythm (all similar length)
            avg_length = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((l - avg_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)
            
            if variance < 4:  # Very low variance = monotonous
                violations.append({
                    "type": "monotonous_rhythm",
                    "sentence_lengths": sentence_lengths,
                    "suggestion": "Vietnamese prose thrives on rhythm variation - alternate short punchy sentences with longer descriptive ones",
                    "severity": "low"
                })
        
        return violations
    
    def suggest_rhythm_improvements(self, sentence: str) -> Dict:
        """
        Suggest rhythm improvements for a single sentence.
        
        Args:
            sentence: Vietnamese sentence to analyze
            
        Returns:
            Dict with improvement suggestions
        """
        words = sentence.split()
        word_count = len(words)
        
        suggestions = {
            "original_length": word_count,
            "improvements": []
        }
        
        # Check for amputation opportunities (Japanese sequential patterns)
        amputation_patterns = self.rhythm_rules.get("amputation_patterns", [])
        for pattern in amputation_patterns:
            marker = pattern.get("marker", "")
            if marker and marker in sentence:
                suggestions["improvements"].append({
                    "type": "amputation",
                    "pattern": pattern.get("id", ""),
                    "explanation": pattern.get("explanation", ""),
                    "example_before": pattern.get("before", ""),
                    "example_after": pattern.get("after", "")
                })
        
        # Suggest particle-based natural breaks
        if word_count > 20:
            particle_breaks = self.rhythm_rules.get("natural_break_particles", [])
            found_breaks = [p for p in particle_breaks if p in sentence]
            if found_breaks:
                suggestions["improvements"].append({
                    "type": "particle_break",
                    "break_points": found_breaks,
                    "explanation": "Use these particles as natural sentence breaks"
                })
        
        return suggestions
    
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

        # Include JP→VN particle mapping guidance (Tier 1 RAG)
        if self.particle_mapping and context:
            injection += "\n### JP→VN Particle Translation (Corpus-Validated):\n"

            # Show archetype-specific particle guidance if archetype provided
            archetype = context.get("archetype", context.get("character_archetype", "NEUTRAL"))

            # Get signature patterns for this archetype
            signature_patterns = self.get_archetype_signature_particles(archetype)
            if signature_patterns.get('signature_patterns'):
                injection += f"\n**{archetype} Signature Particles:**\n"
                for pattern in signature_patterns['signature_patterns'][:3]:  # Top 3
                    jp = pattern.get('japanese_pattern', '')
                    vn = pattern.get('vietnamese_equivalent', '')
                    injection += f"- `{jp}` → `{vn}`\n"

            # Show common particle mappings
            injection += "\n**High-Frequency Particles:**\n"
            common_particles = ['よ (yo)', 'ね (ne)', 'な (na)', 'わ (wa)']
            for jp_particle in common_particles:
                if context.get("archetype") and context.get("rtas") and context.get("gender"):
                    mapping = self.get_vietnamese_particle_for_japanese(
                        jp_particle,
                        archetype=context.get("archetype", "NEUTRAL"),
                        rtas=context.get("rtas", 3.0),
                        gender=context.get("gender", "neutral")
                    )
                    if mapping.get('vietnamese_particles'):
                        vn_particles = mapping['vietnamese_particles'][:2]  # Top 2
                        injection += f"- `{jp_particle}` → {', '.join(vn_particles)}\n"

            # Add gender restrictions warning if applicable
            gender = context.get("gender")
            if gender == "male":
                injection += "\n⚠️ **Gender Filter Active (Male)**: Avoid わ, の (feminine particles)\n"
            elif gender == "female":
                injection += "\n⚠️ **Gender Filter Active (Female)**: Avoid ぞ, ぜ, な (masculine particles)\n"

        # Include rhythm rules for Vietnamese flow
        injection += "\n### Vietnamese Rhythm Rules (Critical for Natural Flow):\n"
        
        # Archetype-specific rhythm if character provided
        if context and context.get("character_archetype"):
            archetype = context["character_archetype"]
            rhythm_profile = self.get_archetype_rhythm_profile(archetype)
            character_archetypes = self.rhythm_rules.get("character_archetypes", {})
            archetype_data = character_archetypes.get(archetype, {})
            
            injection += f"\n**CHARACTER ARCHETYPE: {archetype.replace('_', ' ').upper()}**\n"
            injection += f"- **Description**: {archetype_data.get('description', 'N/A')}\n"
            injection += f"- **Ideal sentence length**: {rhythm_profile.get('ideal_range', [8, 20])[0]}-{rhythm_profile.get('ideal_range', [8, 20])[1]} words\n"
            injection += f"- **Max length**: {rhythm_profile.get('max_length', 25)} words\n"
            injection += f"- **Rhythm pattern**: {rhythm_profile.get('pattern', 'natural').replace('_', ' ')}\n"
            injection += f"- **Amputation style**: {rhythm_profile.get('amputation_style', 'contextual').replace('_', ' ')}\n"
            
            # Add archetype-specific speech patterns
            speech_patterns = archetype_data.get("speech_patterns", {})
            if speech_patterns:
                injection += "\n**Speech Pattern Guidance:**\n"
                for pattern_type, guidance in speech_patterns.items():
                    injection += f"- {pattern_type.replace('_', ' ').title()}: {guidance}\n"
            
            # Add archetype example
            examples = archetype_data.get("examples", {})
            if examples:
                injection += f"\n**Archetype Example:**\n"
                injection += f"- JP: `{examples.get('jp', 'N/A')}`\n"
                injection += f"- ❌ Default VN: `{examples.get('vn_default', 'N/A')}`\n"
                injection += f"- ✅ {archetype} VN: `{examples.get('vn_archetype', 'N/A')}`\n"
                injection += f"- Analysis: {examples.get('analysis', 'N/A')}\n"
        
        else:
            # General rhythm rules for narrator/default
            core_principles = self.rhythm_rules.get("core_principles", [])
            for principle in core_principles[:4]:  # Top 4 principles
                injection += f"- **{principle.get('rule', '')}**: {principle.get('explanation', '')}\n"
                if principle.get('example'):
                    injection += f"  - Example: {principle['example']}\n"
        
        # Include amputation guidance
        amputation_note = self.rhythm_rules.get("amputation_philosophy", "")
        if amputation_note:
            injection += f"\n💡 **Amputation Strategy**: {amputation_note}\n"
        
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
            "rhythm_violations": self.check_rhythm_violations(vietnamese_text),
            "particle_issues": [],
            "score": 100,
            "issues": []
        }

        # Check particle usage if context provided
        if context and context.get("archetype"):
            archetype = context.get("archetype")
            archetype_config = self.get_particles_for_archetype(archetype)
            forbidden_particles = set(archetype_config.get("forbidden", []))

            # Scan Vietnamese text for forbidden particles
            for particle in forbidden_particles:
                if particle in vietnamese_text:
                    report["particle_issues"].append({
                        "particle": particle,
                        "type": "forbidden",
                        "archetype": archetype,
                        "severity": "high"
                    })

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
        
        for rhythm_issue in report["rhythm_violations"]:
            severity_penalty = {"critical": 5, "high": 3, "medium": 2, "low": 1}.get(
                rhythm_issue.get("severity", "medium"), 2
            )
            report["score"] -= severity_penalty
            report["issues"].append(f"Rhythm: {rhythm_issue.get('type', 'violation')}")

        for particle_issue in report["particle_issues"]:
            severity_penalty = {"critical": 8, "high": 5, "medium": 3}.get(
                particle_issue.get("severity", "medium"), 3
            )
            report["score"] -= severity_penalty
            report["issues"].append(
                f"Forbidden particle '{particle_issue['particle']}' for {particle_issue['archetype']}"
            )

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
    
    print("\n=== Rhythm Analysis ===")
    long_sentence = ("Khi anh ấy bước vào phòng, anh ấy nhận thấy rằng không khí trong căn phòng "
                    "đã trở nên căng thẳng và mọi người đều im lặng nhìn vào anh ấy với ánh mắt "
                    "đầy nghi hoặc và không ai dám nói một lời nào cả.")
    rhythm_issues = rag.check_rhythm_violations(long_sentence)
    print(f"Found {len(rhythm_issues)} rhythm violations:")
    for issue in rhythm_issues:
        print(f"  🎵 [{issue.get('severity', 'medium')}] {issue.get('type', 'unknown')}")
        print(f"     💡 {issue.get('suggestion', 'N/A')}")

    
    print("\n=== Prompt Injection Sample ===")
    injection = rag.generate_prompt_injection({
        "archetype": "GYARU",
        "rtas": 4.2,
        "gender": "female"
    })
    print(injection[:500] + "...")

    # Test JP→VN particle mapping (NEW in v4.1)
    if rag.particle_mapping:
        print("\n=== JP→VN Particle Mapping (Tier 1 RAG) ===")

        # Test よ (yo) particle for different archetypes
        print("\nよ (yo) - Emphasis particle:")
        for archetype in ["OJOU", "GYARU", "TSUNDERE", "KUUDERE"]:
            mapping = rag.get_vietnamese_particle_for_japanese(
                "よ (yo)",
                archetype=archetype,
                rtas=3.5,
                gender="female"
            )
            vn_particles = mapping.get('vietnamese_particles', [])
            print(f"  {archetype}: {', '.join(vn_particles[:3])}")

        # Test ね (ne) particle
        print("\nね (ne) - Agreement-seeking particle:")
        mapping = rag.get_vietnamese_particle_for_japanese(
            "ね (ne)",
            archetype="NEUTRAL",
            rtas=3.0,
            gender="neutral"
        )
        print(f"  Function: {mapping.get('function', 'N/A')}")
        print(f"  Vietnamese: {', '.join(mapping.get('vietnamese_particles', [])[:3])}")
        print(f"  Corpus frequency: {mapping.get('corpus_frequency', 0):,}")

        # Test archetype signature detection
        print("\n=== Archetype Signature Particles ===")
        ojou_sig = rag.get_archetype_signature_particles("OJOU")
        if ojou_sig.get('signature_patterns'):
            print("OJOU signatures:")
            for pattern in ojou_sig['signature_patterns'][:3]:
                jp = pattern.get('japanese_pattern', '')
                vn = pattern.get('vietnamese_equivalent', '')
                print(f"  {jp} → {vn}")

        # Test Japanese particle detection
        print("\n=== Japanese Particle Detection ===")
        jp_text = "そうだよ！知ってるわよね。"
        detected = rag.detect_japanese_particles(jp_text)
        print(f"Source: {jp_text}")
        print(f"Detected {len(detected)} particles:")
        for p in detected:
            print(f"  - {p['particle']} (position {p['position']}, {p['category']})")
    else:
        print("\n⚠️  JP→VN particle mapping not loaded (file not found)")
