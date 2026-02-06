"""
MTL Studio Audit System V2.0
Four-Subagent Architecture for Translation Quality Assurance

Subagents:
1. FidelityAuditor - Zero tolerance for truncation/censorship
2. IntegrityAuditor - Structural validation (names, terms, formatting)
3. ProseAuditor - English naturalness via Grammar RAG
4. GapPreservationAuditor - Semantic gap preservation (A/B/C)
5. FinalAuditor - Aggregates reports and generates final verdict
"""

from .fidelity_auditor import FidelityAuditor
from .integrity_auditor import IntegrityAuditor
from .prose_auditor import ProseAuditor
from .gap_preservation_auditor import GapPreservationAuditor
from .final_auditor import FinalAuditor

__all__ = [
    'FidelityAuditor',
    'IntegrityAuditor', 
    'ProseAuditor',
    'GapPreservationAuditor',
    'FinalAuditor'
]

__version__ = '2.0.0'
