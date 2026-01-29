"""
Translation Quality Metrics.
Calculates metrics for self-auditing translation quality.
"""

import re
import logging
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from pipeline.translator.config import get_quality_threshold, get_translation_config

logger = logging.getLogger(__name__)

@dataclass
class AuditResult:
    contraction_rate: float
    ai_ism_count: int
    ai_isms_found: List[str]
    illustrations_preserved: bool
    missing_illustrations: List[str]
    warnings: List[str]
    passed: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "contraction_rate": self.contraction_rate,
            "ai_ism_count": self.ai_ism_count,
            "ai_isms_found": self.ai_isms_found,
            "illustrations_preserved": self.illustrations_preserved,
            "missing_illustrations": self.missing_illustrations,
            "warnings": self.warnings,
            "passed": self.passed
        }

class QualityMetrics:
    # Critical contraction patterns (Yen Press/J-Novel Club Gold Standard)
    # Priority 1: MUST contract in casual contexts - "it is", "that is", "there is"
    CRITICAL_CONTRACTIBLE = [
        (r"\bit is\b", "it's"),
        (r"\bthat is\b", "that's"),
        (r"\bthere is\b", "there's"),
        (r"\bhere is\b", "here's"),
        (r"\bwhat is\b", "what's"),
        (r"\bwho is\b", "who's"),
        (r"\bdo not\b", "don't"),
        (r"\bdoes not\b", "doesn't"),
    ]
    
    # Priority 2: High priority - negative contractions
    HIGH_PRIORITY_CONTRACTIBLE = [
        (r"\bwas not\b", "wasn't"),
        (r"\bwere not\b", "weren't"),
        (r"\bcould not\b", "couldn't"),
        (r"\bshould not\b", "shouldn't"),
        (r"\bwould not\b", "wouldn't"),
        (r"\bdid not\b", "didn't"),
        (r"\bhad not\b", "hadn't"),
    ]
    
    # Priority 3: Standard contractions
    STANDARD_CONTRACTIBLE = [
        (r"\bis not\b", "isn't"),
        (r"\bare not\b", "aren't"),
        (r"\bhave not\b", "haven't"),
        (r"\bhas not\b", "hasn't"),
        (r"\bwill not\b", "won't"),
        (r"\bcannot\b", "can't"),
        (r"\bI am\b", "I'm"),
        (r"\byou are\b", "you're"),
        (r"\bwe are\b", "we're"),
        (r"\bthey are\b", "they're"),
        (r"\bI will\b", "I'll"),
        (r"\byou will\b", "you'll"),
        (r"\bI have\b", "I've"),
        (r"\byou have\b", "you've"),
        (r"\blet us\b", "let's"),
    ]
    
    # J-Novel Club perfect tense contractions (internal monologue)
    PERFECT_TENSE_CONTRACTIBLE = [
        (r"\bwould have\b", "would've"),
        (r"\bcould have\b", "could've"),
        (r"\bshould have\b", "should've"),
        (r"\bmight have\b", "might've"),
        (r"\bmust have\b", "must've"),
    ]
    
    # Combined pattern list (all priorities)
    CONTRACTIBLE_PATTERNS = (
        CRITICAL_CONTRACTIBLE + 
        HIGH_PRIORITY_CONTRACTIBLE + 
        STANDARD_CONTRACTIBLE + 
        PERFECT_TENSE_CONTRACTIBLE
    )
    
    # Default AI-isms if not in config
    DEFAULT_AI_ISMS = [
        "indeed", "quite", "rather", "I shall",
        "most certainly", "if you will", "as it were",
        "one might say", "it would seem", "I daresay",
        "it cannot be helped", "shikatanai"
    ]

    @staticmethod
    def calculate_contraction_rate(text: str) -> float:
        """
        Calculate contraction rate in dialogue.
        Rate = (contracted forms) / (contracted forms + uncontracted content words)
        
        This is a heuristic. A better approach is:
        Rate = (actual contractions) / (actual contractions + missed contraction opportunities)
        """
        if not text:
            return 0.0
            
        contracted_count = 0
        missed_count = 0
        
        # Simple tokenization for analysis
        # We focus on dialogue only if possible, but full text is okay for rough metric
        
        # Count actual contractions (apostrophe + s/t/re/ll/ve/m/d)
        contracted_count += len(re.findall(r"\w+'(?:t|s|re|ll|ve|m|d)\b", text, re.IGNORECASE))
        contracted_count += len(re.findall(r"\bwonna\b|\bgonna\b", text, re.IGNORECASE))

        # Count missed opportunities
        for pattern, _ in QualityMetrics.CONTRACTIBLE_PATTERNS:
            missed_count += len(re.findall(pattern, text, re.IGNORECASE))
            
        total_opportunities = contracted_count + missed_count
        if total_opportunities == 0:
            return 1.0 # No opportunities = good (avoid division by zero)
            
        return contracted_count / total_opportunities

    @staticmethod
    def count_ai_isms(text: str, patterns: List[str] = None) -> Tuple[int, List[str]]:
        """Count occurrences of known AI-ism patterns."""
        if not patterns:
            # Load from config or use defaults
            config = get_translation_config()
            # Try to get from critics config if available, else translation
            # For now use hardcoded defaults + generic list
            patterns = QualityMetrics.DEFAULT_AI_ISMS

        found = []
        count = 0
        
        for pattern in patterns:
            matches = re.findall(r"\b" + re.escape(pattern) + r"\b", text, re.IGNORECASE)
            if matches:
                count += len(matches)
                found.extend(matches)
                
        return count, list(set(found)) # Unique types found

    @staticmethod
    def check_illustration_preservation(source: str, translated: str) -> Tuple[bool, List[str]]:
        """
        Verify all [ILLUSTRATION: ...] tags in source appear in translation.
        Robust against whitespace differences.
        """
        # Extract tags: [ILLUSTRATION: filename.jpg]
        tag_pattern = r"\[ILLUSTRATION:\s*(.*?)\]"
        
        source_tags = re.findall(tag_pattern, source)
        translated_tags = re.findall(tag_pattern, translated)
        
        # Normalize for comparison (remove whitespace, lowercase)
        src_norm = [t.strip().lower() for t in source_tags]
        trans_norm = [t.strip().lower() for t in translated_tags]
        
        missing = []
        for tag, norm in zip(source_tags, src_norm):
            if norm not in trans_norm:
                missing.append(tag)
                
        return (len(missing) == 0), missing

    @staticmethod
    def quick_audit(translated_text: str, source_text: str = "") -> AuditResult:
        """Perform a quick quality audit on the translated text."""
        
        # 1. Contraction Rate
        contraction_rate = QualityMetrics.calculate_contraction_rate(translated_text)
        
        # 2. AI-isms
        ai_ism_count, ai_isms_found = QualityMetrics.count_ai_isms(translated_text)
        
        # 3. Illustration Check
        ills_preserved = True
        missing_ills = []
        if source_text:
            ills_preserved, missing_ills = QualityMetrics.check_illustration_preservation(
                source_text, translated_text
            )
            
        # 4. Determine warnings & pass/fail
        warnings = []
        threshold = get_quality_threshold()
        
        if contraction_rate < threshold:
            warnings.append(f"Low contraction rate: {contraction_rate:.2f} (Target: {threshold})")
            
        if ai_ism_count > 5:
            warnings.append(f"High AI-ism count: {ai_ism_count} found")
            
        if not ills_preserved:
            warnings.append(f"Missing illustrations: {len(missing_ills)}")
            
        # Logic for 'passed' - loose for translator phase (just warnings), strictest for Critics
        # For Translator: Fail only on missing illustrations or critical errors
        passed = ills_preserved
        
        return AuditResult(
            contraction_rate=contraction_rate,
            ai_ism_count=ai_ism_count,
            ai_isms_found=ai_isms_found,
            illustrations_preserved=ills_preserved,
            missing_illustrations=missing_ills,
            warnings=warnings,
            passed=passed
        )
