"""
Euphemism Injection Module for Explicit Content Navigation

Pre-emptively softens explicit content using graduated euphemism levels
to prevent PROHIBITED_CONTENT blocks while maintaining translation quality.
"""

import logging
import re
from enum import Enum
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class EuphemismLevel(Enum):
    """Euphemism strength levels for explicit content handling."""
    DIRECT = 0        # No euphemism (standard translation)
    MILD = 1          # Implied language, avoid explicit anatomical terms
    MODERATE = 2      # Focus on emotions, euphemize physical acts
    STRONG = 3        # Abstract sentiment only, skip graphic details


class ExplicitContentDetector:
    """Detects explicit content markers in Japanese text."""
    
    # Explicit content markers (ordered by severity)
    EXPLICIT_MARKERS = {
        'sexual_acts': [
            'キス', 'くわえ', '舐め', '吸い', '挿入',
            'ちゅっ', 'ぺろぺろ', 'レロレロ',
            '絶頂', 'イく', 'イっ'
        ],
        'anatomy': [
            '乳首', '胸', 'おっぱい', '乳房',
            'ペニス', 'ちんこ', 'おちんちん',
            '性器', 'アソコ', '秘部'
        ],
        'clothing_removal': [
            'パンツを脱', '下着を外', '服を脱',
            'ブラを外', '裸になる'
        ],
        'positions': [
            '馬乗り', '騎乗位', '正常位',
            '後背位', 'バック'
        ]
    }
    
    def analyze_explicit_density(self, text: str) -> float:
        """
        Calculate explicit content density (0.0 to 1.0).
        
        Args:
            text: Japanese text to analyze
            
        Returns:
            Ratio of explicit markers to total text length
        """
        marker_count = 0
        
        for category, markers in self.EXPLICIT_MARKERS.items():
            for marker in markers:
                marker_count += text.count(marker)
        
        # Normalize by character count (higher density = more explicit)
        if len(text) == 0:
            return 0.0
        
        density = marker_count / (len(text) / 100)  # Per 100 chars
        return min(1.0, density)  # Cap at 1.0
    
    def recommend_euphemism_level(self, text: str) -> EuphemismLevel:
        """
        Recommend euphemism level based on content analysis.
        
        Args:
            text: Japanese text to analyze
            
        Returns:
            Recommended euphemism level
        """
        density = self.analyze_explicit_density(text)
        
        if density < 0.02:  # <2 markers per 100 chars
            return EuphemismLevel.DIRECT
        elif density < 0.05:  # 2-5 markers per 100 chars
            return EuphemismLevel.MILD
        elif density < 0.08:  # 5-8 markers per 100 chars
            return EuphemismLevel.MODERATE
        else:  # >8 markers per 100 chars
            return EuphemismLevel.STRONG
    
    def contains_explicit_content(self, text: str) -> bool:
        """Quick check if text contains any explicit markers."""
        for markers in self.EXPLICIT_MARKERS.values():
            if any(marker in text for marker in markers):
                return True
        return False


class EuphemismInjector:
    """Injects euphemism guidance into translation prompts."""
    
    EUPHEMISM_PROMPTS = {
        EuphemismLevel.MILD: """
[CONTENT GUIDANCE - Mild Euphemism]
For intimate scenes in this text:
- Use IMPLIED language instead of explicit descriptions
- Avoid graphic anatomical terms (use "chest" not specific anatomy)
- Focus on actions and sensations, not graphic details
- Example: "touched her intimately" instead of explicit descriptions

Maintain the emotional intensity and character reactions while using tasteful language.
""",
        
        EuphemismLevel.MODERATE: """
[CONTENT GUIDANCE - Moderate Euphemism]
For intimate scenes in this text:
- Focus on CHARACTER EMOTIONS and reactions
- Use euphemisms for physical acts (e.g., "grew closer", "shared intimacy")
- Avoid detailed descriptions of explicit actions
- Emphasize the relationship dynamic over physical details
- Example: "They crossed a line that had been building between them" instead of explicit acts

Keep the narrative flow and emotional impact without graphic descriptions.
""",
        
        EuphemismLevel.STRONG: """
[CONTENT GUIDANCE - Strong Euphemism]
For intimate scenes in this text:
- Translate SENTIMENT and EMOTIONAL EXPERIENCE only
- Use highly abstract language for intimate moments
- Skip graphic physical descriptions entirely
- Frame as "fade to black" style narrative
- Example: "What happened between them felt natural, inevitable" instead of scene details

Preserve the story progression and character development while minimizing explicit content.
"""
    }
    
    def __init__(self):
        self.detector = ExplicitContentDetector()
        logger.info("[EUPHEMISM] Injector initialized")
    
    def inject_guidance(
        self,
        text: str,
        level: EuphemismLevel = None,
        auto_detect: bool = True
    ) -> Tuple[str, EuphemismLevel]:
        """
        Inject euphemism guidance into translation prompt.
        
        Args:
            text: Original Japanese text to translate
            level: Explicit euphemism level (if None, auto-detect)
            auto_detect: Whether to auto-detect appropriate level
            
        Returns:
            (modified_prompt, applied_level) tuple
        """
        # Auto-detect if not specified
        if level is None and auto_detect:
            level = self.detector.recommend_euphemism_level(text)
        
        # No euphemism needed for direct translation
        if level == EuphemismLevel.DIRECT:
            logger.info("[EUPHEMISM] No euphemism needed (density < 2%)")
            return text, level
        
        # Inject appropriate guidance
        guidance = self.EUPHEMISM_PROMPTS.get(level, "")
        
        if guidance:
            modified_prompt = f"{guidance}\n\n[JAPANESE SOURCE TEXT]\n{text}"
            logger.info(f"[EUPHEMISM] Applied {level.name} euphemism (density: {self.detector.analyze_explicit_density(text):.1%})")
            return modified_prompt, level
        
        return text, EuphemismLevel.DIRECT
    
    def analyze_and_report(self, text: str) -> Dict:
        """
        Analyze text and return detailed report.
        
        Args:
            text: Japanese text to analyze
            
        Returns:
            Dictionary with analysis results
        """
        density = self.detector.analyze_explicit_density(text)
        recommended = self.detector.recommend_euphemism_level(text)
        contains_explicit = self.detector.contains_explicit_content(text)
        
        # Count markers by category
        marker_counts = {}
        for category, markers in self.detector.EXPLICIT_MARKERS.items():
            count = sum(text.count(marker) for marker in markers)
            if count > 0:
                marker_counts[category] = count
        
        return {
            'explicit_density': density,
            'recommended_level': recommended.name,
            'contains_explicit': contains_explicit,
            'marker_counts': marker_counts,
            'total_markers': sum(marker_counts.values()),
            'text_length': len(text)
        }


def create_euphemism_injector() -> EuphemismInjector:
    """Factory function to create EuphemismInjector instance."""
    return EuphemismInjector()


# Quick test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with sample explicit text
    injector = EuphemismInjector()
    
    test_text = """
    真理亜の乳首をくわえ、強く吸い上げる。
    彼女は小さく喘ぎ声を上げた。
    """
    
    analysis = injector.analyze_and_report(test_text)
    print("\nContent Analysis:")
    print(f"  Explicit density: {analysis['explicit_density']:.1%}")
    print(f"  Recommended level: {analysis['recommended_level']}")
    print(f"  Marker counts: {analysis['marker_counts']}")
    
    modified, level = injector.inject_guidance(test_text)
    print(f"\nApplied level: {level.name}")
    print(f"Modified prompt length: {len(modified)} chars")
