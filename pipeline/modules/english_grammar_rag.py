#!/usr/bin/env python3
"""
English Grammar RAG Module
Retrieves and applies natural English idiom patterns during JP→EN translation.
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple
import re

class EnglishGrammarRAG:
    """RAG system for retrieving English grammar restructuring patterns."""
    
    def __init__(self, config_path: str = None):
        """Initialize RAG module with pattern database."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "english_grammar_rag.json"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.patterns = self._flatten_patterns()
    
    def _flatten_patterns(self) -> List[Dict]:
        """Flatten nested pattern structure for easier searching."""
        flat_patterns = []
        for category_name, category_data in self.config["pattern_categories"].items():
            for pattern in category_data["patterns"]:
                pattern["category"] = category_name
                flat_patterns.append(pattern)
        return flat_patterns
    
    def detect_patterns(self, japanese_text: str) -> List[Dict]:
        """
        Detect which grammar patterns are present in Japanese text.
        
        Args:
            japanese_text: Source Japanese text
            
        Returns:
            List of matched patterns with relevance scores
        """
        matches = []
        
        for pattern in self.patterns:
            indicators = pattern.get("japanese_indicators", [])
            score = 0
            matched_indicators = []
            
            # Check for indicator presence
            for indicator in indicators:
                if indicator in japanese_text:
                    score += 1
                    matched_indicators.append(indicator)
            
            if score > 0:
                # Adjust score by priority
                priority_weight = {
                    "high": 3,
                    "medium": 2,
                    "low": 1
                }.get(pattern.get("priority", "medium"), 2)
                
                matches.append({
                    "pattern": pattern,
                    "score": score * priority_weight,
                    "matched_indicators": matched_indicators
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches
    
    def generate_few_shot_examples(self, japanese_text: str, max_examples: int = 5) -> str:
        """
        Generate few-shot examples based on detected patterns.
        
        Args:
            japanese_text: Source Japanese text to analyze
            max_examples: Maximum number of examples to include
            
        Returns:
            Formatted few-shot examples string for prompt injection
        """
        matches = self.detect_patterns(japanese_text)
        
        if not matches:
            return ""
        
        examples_text = "\n## Natural English Grammar Patterns\n\n"
        examples_text += "Apply these idiomatic patterns when translating:\n\n"
        
        included_patterns = set()
        example_count = 0
        
        for match in matches:
            if example_count >= max_examples:
                break
            
            pattern = match["pattern"]
            pattern_id = pattern["id"]
            
            # Avoid duplicate pattern types
            if pattern_id in included_patterns:
                continue
            
            included_patterns.add(pattern_id)
            
            # Add pattern explanation
            examples_text += f"### Pattern: {pattern['english_pattern']}\n"
            examples_text += f"**When to use:** {pattern.get('usage_rules', ['Context-dependent'])[0]}\n\n"
            
            # Add examples
            if "examples" in pattern and pattern["examples"]:
                example = pattern["examples"][0]  # Use first example
                examples_text += "❌ **Literal:** " + example.get("literal", "") + "\n"
                examples_text += "✅ **Natural:** " + example.get("natural", "") + "\n\n"
                
                example_count += 1
        
        return examples_text
    
    def validate_translation(self, japanese_text: str, english_text: str) -> List[Dict]:
        """
        Check if translation missed opportunities for natural idioms.
        
        Args:
            japanese_text: Source Japanese
            english_text: Translated English
            
        Returns:
            List of suggestions for improvement
        """
        suggestions = []
        matches = self.detect_patterns(japanese_text)
        
        for match in matches:
            pattern = match["pattern"]
            
            # Check if pattern's literal form appears in translation
            if "examples" in pattern:
                for example in pattern["examples"]:
                    literal = example.get("literal", "")
                    natural = example.get("natural", "")
                    
                    # Simple substring check (could be improved with fuzzy matching)
                    if literal and literal.lower() in english_text.lower():
                        suggestions.append({
                            "type": "grammar_restructuring",
                            "pattern_id": pattern["id"],
                            "issue": f"Literal translation detected: '{literal}'",
                            "suggestion": f"Consider natural idiom: '{natural}'",
                            "priority": pattern.get("priority", "medium"),
                            "japanese_source": example.get("jp", "")
                        })
        
        return suggestions
    
    def get_pattern_by_id(self, pattern_id: str) -> Dict:
        """Retrieve specific pattern by ID."""
        for pattern in self.patterns:
            if pattern["id"] == pattern_id:
                return pattern
        return None
    
    def search_patterns(self, query: str, category: str = None) -> List[Dict]:
        """
        Search patterns by keyword or category.
        
        Args:
            query: Search term
            category: Optional category filter
            
        Returns:
            List of matching patterns
        """
        results = []
        
        for pattern in self.patterns:
            if category and pattern["category"] != category:
                continue
            
            # Search in multiple fields
            searchable_text = " ".join([
                pattern.get("id", ""),
                pattern.get("japanese_structure", ""),
                pattern.get("english_pattern", ""),
                " ".join(pattern.get("japanese_indicators", [])),
                " ".join(pattern.get("usage_rules", []))
            ]).lower()
            
            if query.lower() in searchable_text:
                results.append(pattern)
        
        return results


# Usage example
if __name__ == "__main__":
    rag = EnglishGrammarRAG()
    
    # Test with sample text
    test_text = "真理亜は変だが、如月さんも結構変だ"
    
    print("=== Pattern Detection ===")
    matches = rag.detect_patterns(test_text)
    print(f"Found {len(matches)} matching patterns:")
    for match in matches:
        print(f"  - {match['pattern']['id']} (score: {match['score']})")
        print(f"    Indicators: {', '.join(match['matched_indicators'])}")
    
    print("\n=== Few-Shot Examples ===")
    examples = rag.generate_few_shot_examples(test_text)
    print(examples)
    
    print("\n=== Validation ===")
    bad_translation = "Maria's weird, but Kisaragi-san is pretty weird in her own right."
    suggestions = rag.validate_translation(test_text, bad_translation)
    
    if suggestions:
        print(f"Found {len(suggestions)} improvement suggestions:")
        for suggestion in suggestions:
            print(f"  ⚠️  {suggestion['issue']}")
            print(f"     💡 {suggestion['suggestion']}")
    else:
        print("Translation looks good!")
