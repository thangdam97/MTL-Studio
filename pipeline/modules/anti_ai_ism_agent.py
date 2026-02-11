#!/usr/bin/env python3
"""
Self-Healing Anti-AI-ism Agent v1.0
====================================
Automated post-processor that detects and corrects AI-generated prose artifacts
using a three-layer architecture:

Layer 1 — Regex Scanner: 65+ patterns from anti_ai_ism_patterns.json
           (CRITICAL/MAJOR/MINOR/VN severity tiers with echo detection)

Layer 2 — Vector Bad Prose DB: Embeds every output sentence via gemini-embedding-001,
           compares against a ChromaDB collection of "known bad" AI prose examples.
           Sentences with cosine similarity ≥ 0.80 to any bad example get flagged.

Layer 3 — Psychic Distance Filter: LLM-powered (Gemini Flash) analysis of
           filter words, nominalizations, and prepositional bloat that create
           narrative distance in first-person POV.

Self-Healing: Flagged sentences are sent to Gemini Flash for rewrite with
              the specific issue category + fix guidance. Corrections are
              applied in-place with a full audit trail.

Author: MTL Studio
Version: 1.0
Date: 2026-02-07
"""

import re
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pipeline.common.genai_factory import create_genai_client, resolve_api_key

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# ChromaDB for vector Bad Prose DB
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Gemini for embeddings + LLM correction
try:
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class AIismIssue:
    """Single detected AI-ism issue."""
    issue_id: str
    layer: str              # "regex", "vector", "psychic_distance"
    severity: str           # CRITICAL, MAJOR, MINOR
    category: str           # e.g., "filter_phrases", "nominalization", "bad_prose_match"
    line_number: int
    sentence: str           # The flagged sentence
    matched_pattern: str    # What triggered the flag
    fix_guidance: str       # Instructions for the LLM rewriter
    confidence: float       # 0.0-1.0
    corrected: Optional[str] = None  # LLM-generated correction (None if not yet healed)
    vector_similarity: Optional[float] = None  # Only for Layer 2 hits


@dataclass
class HealingReport:
    """Full report from a healing run."""
    volume_id: str
    target_language: str
    timestamp: str
    files_processed: int
    total_sentences: int
    # Layer stats
    layer1_regex_hits: int = 0
    layer2_vector_hits: int = 0
    layer3_psychic_hits: int = 0
    total_issues: int = 0
    total_healed: int = 0
    total_skipped: int = 0
    # Per-severity
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    # Details
    issues: List[Dict] = field(default_factory=list)
    per_file: Dict[str, Dict] = field(default_factory=dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Bad Prose Database — Seed Examples
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BAD_PROSE_SEEDS = [
    # Filter words — psychic distance violations
    {"text": "I felt a sense of anger rising within me.", "category": "filter_word", "fix": "Anger rose within me."},
    {"text": "I heard the sound of the door opening.", "category": "filter_word", "fix": "The door clicked open."},
    {"text": "I saw her figure standing by the window.", "category": "filter_word", "fix": "She stood by the window."},
    {"text": "I noticed that his expression had changed.", "category": "filter_word", "fix": "His expression changed."},
    {"text": "I could feel the tension in the air.", "category": "filter_word", "fix": "The tension was palpable."},
    {"text": "I decided to walk toward the station.", "category": "filter_word", "fix": "I walked toward the station."},
    {"text": "I started to feel a creeping sense of dread.", "category": "filter_word", "fix": "Dread crept through me."},
    {"text": "I began to realize what she meant.", "category": "filter_word", "fix": "It hit me — that's what she meant."},
    {"text": "I found myself staring at the ceiling.", "category": "filter_word", "fix": "I stared at the ceiling."},
    {"text": "I seemed to sense something was wrong.", "category": "filter_word", "fix": "Something was wrong."},
    
    # Nominalization traps — weak verb + abstract noun
    {"text": "She gave a small nod of understanding.", "category": "nominalization", "fix": "She nodded."},
    {"text": "He let out a sigh of resignation.", "category": "nominalization", "fix": "He sighed."},
    {"text": "I came to a realization that I was wrong.", "category": "nominalization", "fix": "I realized I was wrong."},
    {"text": "She made a decision to leave early.", "category": "nominalization", "fix": "She decided to leave early."},
    {"text": "He gave a shake of his head.", "category": "nominalization", "fix": "He shook his head."},
    {"text": "I took a deep breath of determination.", "category": "nominalization", "fix": "I took a deep breath."},
    {"text": "She offered a smile of reassurance.", "category": "nominalization", "fix": "She smiled reassuringly."},
    {"text": "He gave a wave of his hand dismissively.", "category": "nominalization", "fix": "He waved dismissively."},
    
    # Prepositional bloat — robot-like spatial descriptions
    {"text": "He turned his head in the direction of the voice.", "category": "prepositional_bloat", "fix": "He turned toward the voice."},
    {"text": "She moved her gaze in the direction of the window.", "category": "prepositional_bloat", "fix": "She looked at the window."},
    {"text": "The building was located at the center of the campus.", "category": "prepositional_bloat", "fix": "The building sat at the center of campus."},
    {"text": "He positioned himself at a spot near the entrance.", "category": "prepositional_bloat", "fix": "He stood near the entrance."},
    
    # AI crutch phrases — overused sentence constructions
    {"text": "A shiver ran down my spine at the sight.", "category": "ai_crutch", "fix": "Context-dependent: use specific physical reaction."},
    {"text": "The weight of his words hung heavy in the air.", "category": "ai_crutch", "fix": "Silence after his words. / That landed hard."},
    {"text": "Something stirred deep within me.", "category": "ai_crutch", "fix": "Use specific emotion, not vague 'stirring'."},
    {"text": "The world seemed to slow down around me.", "category": "ai_crutch", "fix": "Time slowed. / Everything went still."},
    {"text": "I couldn't help but feel a warmth spreading through my chest.", "category": "ai_crutch", "fix": "Warmth spread through my chest."},
    {"text": "Her words cut through the silence like a knife.", "category": "ai_crutch", "fix": "Her voice broke the silence."},
    {"text": "A bittersweet feeling washed over me.", "category": "ai_crutch", "fix": "Use specific emotion, not 'bittersweet feeling washed'."},
    {"text": "The air between us was thick with unspoken words.", "category": "ai_crutch", "fix": "Neither of us spoke."},
    
    # Vietnamese AI-isms — "một cách" and "một cảm giác"
    {"text": "Cô ấy mỉm cười một cách dịu dàng.", "category": "vn_mot_cach", "fix": "Cô ấy dịu dàng mỉm cười."},
    {"text": "Anh ấy nhìn tôi một cách nghiêm túc.", "category": "vn_mot_cach", "fix": "Anh ấy nghiêm túc nhìn tôi."},
    {"text": "Một cảm giác bất an dâng lên trong lòng tôi.", "category": "vn_mot_cam_giac", "fix": "Tôi thấy bất an."},
    {"text": "Tôi cảm thấy một cảm giác ấm áp lan tỏa.", "category": "vn_mot_cam_giac", "fix": "Hơi ấm lan tỏa trong tôi."},
    {"text": "Sự im lặng của cô ấy khiến tôi lo lắng.", "category": "vn_su_nominalization", "fix": "Cô ấy im lặng, khiến tôi lo."},
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Agent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AntiAIismAgent:
    """
    Self-Healing Anti-AI-ism Agent.
    
    Three-layer detection + LLM auto-correction:
    
    Layer 1: Regex patterns (65+ from anti_ai_ism_patterns.json)
    Layer 2: Vector Bad Prose DB (ChromaDB semantic matching)
    Layer 3: Psychic Distance Filter (LLM analysis)
    
    Self-Healing: Gemini Flash rewrites flagged sentences with category-specific guidance.
    """
    
    # Vector thresholds
    VECTOR_FLAG_THRESHOLD = 0.80   # Flag sentence if cosine sim ≥ 0.80 to bad prose
    VECTOR_WARN_THRESHOLD = 0.70   # Log for review if ≥ 0.70
    
    # Psychic distance filter words (Layer 3 regex pre-filter before LLM)
    FILTER_WORDS = re.compile(
        r'\b(?:I\s+(?:felt|heard|saw|noticed|sensed|seemed|decided|started|began|found myself|could (?:feel|see|hear|sense)))\b',
        re.IGNORECASE
    )
    NOMINALIZATION_PATTERNS = re.compile(
        r'\b(?:gave a (?:nod|shake|wave|shrug|smile|sigh|laugh|glance)|'
        r'let out a (?:sigh|breath|groan|laugh|cry)|'
        r'(?:came to|reached) a (?:realization|decision|conclusion)|'
        r'made a (?:decision|realization|choice)|'
        r'offered a (?:smile|nod|wave|shrug))\b',
        re.IGNORECASE
    )
    PREPOSITIONAL_BLOAT = re.compile(
        r'\b(?:in the direction of|located at|positioned (?:at|on|near)|'
        r'situated (?:at|in|near)|in the vicinity of|'
        r'turned (?:his|her|their) (?:head|gaze|eyes) in the direction)\b',
        re.IGNORECASE
    )
    
    # VN-specific filter patterns
    VN_MOT_CACH = re.compile(r'một cách\s+\w+', re.IGNORECASE)
    VN_MOT_CAM_GIAC = re.compile(r'một cảm giác\s+\w+', re.IGNORECASE)
    VN_SU_NOMINAL = re.compile(r'(?:sự|việc)\s+\w+\s+của', re.IGNORECASE)
    
    def __init__(
        self,
        config_dir: Optional[Path] = None,
        persist_directory: Optional[str] = None,
        auto_heal: bool = True,
        dry_run: bool = False,
        target_language: str = "en",
        gemini_api_key: Optional[str] = None,
        use_vector: bool = True,
    ):
        """
        Initialize the Anti-AI-ism Agent.
        
        Args:
            config_dir: Path to config/ directory containing anti_ai_ism_patterns.json
            persist_directory: ChromaDB persistence path for Bad Prose DB
            auto_heal: If True, auto-correct flagged sentences via Gemini Flash
            dry_run: If True, report issues but don't modify files
            target_language: "en" or "vn" — determines which patterns to activate
            gemini_api_key: Gemini API key (uses env var if not provided)
            use_vector: If False, skip Layer 2 vector DB initialization (faster startup)
        """
        self.auto_heal = auto_heal
        self.dry_run = dry_run
        self.target_language = target_language
        self.use_vector = use_vector
        self._issues: List[AIismIssue] = []
        self._issue_counter = 0
        
        # Resolve paths
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        self.config_dir = Path(config_dir)
        
        if persist_directory is None:
            persist_directory = str(Path(__file__).parent.parent / "chroma_bad_prose")
        
        # ── Layer 1: Load regex patterns ──
        self.regex_patterns = self._load_regex_patterns()
        logger.info(f"[HEAL] Layer 1: {sum(len(v) for v in self.regex_patterns.values())} regex patterns loaded")
        
        # ── Layer 2: Initialize Vector Bad Prose DB ──
        self.vector_store = None
        self.gemini_client = None
        api_key = resolve_api_key(api_key=gemini_api_key, required=False)
        
        if self.use_vector and CHROMADB_AVAILABLE and GEMINI_AVAILABLE and api_key:
            try:
                self.gemini_client = create_genai_client(api_key=api_key)
                self._embedding_model = "gemini-embedding-001"
                
                db_client = chromadb.PersistentClient(
                    path=persist_directory,
                    settings=Settings(anonymized_telemetry=False)
                )
                self.vector_store = db_client.get_or_create_collection(
                    name="bad_prose_examples",
                    metadata={"hnsw:space": "cosine"}
                )
                
                # Auto-seed if empty
                if self.vector_store.count() == 0:
                    self._seed_bad_prose_db()
                
                logger.info(f"[HEAL] Layer 2: Bad Prose DB loaded ({self.vector_store.count()} vectors)")
            except Exception as e:
                logger.warning(f"[HEAL] Layer 2 init failed: {e}. Falling back to regex-only mode.")
                self.vector_store = None
        else:
            missing = []
            if not CHROMADB_AVAILABLE:
                missing.append("chromadb")
            if not GEMINI_AVAILABLE:
                missing.append("google-genai")
            if not api_key:
                missing.append("GOOGLE_API_KEY (or GEMINI_API_KEY)")
            logger.warning(f"[HEAL] Layer 2 disabled (missing: {', '.join(missing)})")
        
        # ── Layer 3: LLM client for psychic distance + healing ──
        self.llm_client = None
        if GEMINI_AVAILABLE and api_key and auto_heal:
            try:
                self.llm_client = create_genai_client(api_key=api_key)
                self._flash_model = "gemini-2.5-flash"
                logger.info(f"[HEAL] Layer 3 + Self-Healing: Gemini Flash active ({self._flash_model})")
            except Exception as e:
                logger.warning(f"[HEAL] Layer 3 init failed: {e}. LLM correction disabled.")
        
        if not self.llm_client:
            logger.info("[HEAL] Layer 3: Psychic distance check via regex only (no LLM)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Layer 1: Regex Pattern Loading
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _load_regex_patterns(self) -> Dict[str, List[Dict]]:
        """Load patterns from anti_ai_ism_patterns.json."""
        patterns = {"CRITICAL": [], "MAJOR": [], "MINOR": [], "VIETNAMESE_CRITICAL": []}
        
        json_path = self.config_dir / "anti_ai_ism_patterns.json"
        if not json_path.exists():
            logger.warning(f"[HEAL] Pattern file not found: {json_path}")
            return patterns
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # CRITICAL — flat list
            for sev in ["CRITICAL", "VIETNAMESE_CRITICAL"]:
                if sev in data and "patterns" in data[sev]:
                    for p in data[sev]["patterns"]:
                        patterns[sev].append({
                            "id": p.get("id", "unknown"),
                            "regex": re.compile(p["regex"], re.IGNORECASE),
                            "display": p.get("display", p["regex"]),
                            "fix": p.get("fix", "Rephrase naturally"),
                            "source": p.get("source", ""),
                        })
            
            # MAJOR / MINOR — nested under categories
            for sev in ["MAJOR", "MINOR"]:
                if sev in data and "categories" in data[sev]:
                    for cat_name, cat_data in data[sev]["categories"].items():
                        for p in cat_data.get("patterns", []):
                            patterns[sev].append({
                                "id": p.get("id", "unknown"),
                                "regex": re.compile(p["regex"], re.IGNORECASE),
                                "display": p.get("display", p["regex"]),
                                "fix": p.get("fix", "Rephrase naturally"),
                                "category": cat_name,
                                "source": p.get("source", ""),
                                "exceptions": p.get("japanese_grammar_exceptions", []),
                            })
            
            total = sum(len(v) for v in patterns.values())
            logger.info(f"[HEAL] Loaded {total} patterns: "
                       f"CRIT={len(patterns['CRITICAL'])}, "
                       f"MAJOR={len(patterns['MAJOR'])}, "
                       f"MINOR={len(patterns['MINOR'])}, "
                       f"VN_CRIT={len(patterns['VIETNAMESE_CRITICAL'])}")
            
        except Exception as e:
            logger.error(f"[HEAL] Failed to load patterns: {e}")
        
        return patterns
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Layer 2: Vector Bad Prose DB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _seed_bad_prose_db(self):
        """Seed ChromaDB with bad prose examples + embeddings."""
        if not self.vector_store or not self.gemini_client:
            return
        
        logger.info(f"[HEAL] Seeding Bad Prose DB with {len(BAD_PROSE_SEEDS)} examples...")
        
        # Filter seeds by target language
        if self.target_language == "en":
            seeds = [s for s in BAD_PROSE_SEEDS if not s["category"].startswith("vn_")]
        elif self.target_language == "vn":
            seeds = BAD_PROSE_SEEDS  # Include both EN and VN patterns
        else:
            seeds = BAD_PROSE_SEEDS
        
        texts = [s["text"] for s in seeds]
        ids = [f"bad_prose_{i:03d}" for i in range(len(seeds))]
        metadatas = [{"category": s["category"], "fix": s["fix"]} for s in seeds]
        
        # Batch embed
        try:
            result = self.gemini_client.models.embed_content(
                model=self._embedding_model,
                contents=texts
            )
            embeddings = [list(e.values) for e in result.embeddings]
            
            self.vector_store.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            logger.info(f"[HEAL] ✓ Seeded {len(seeds)} bad prose vectors ({len(embeddings[0])}D)")
        except Exception as e:
            logger.error(f"[HEAL] Failed to seed Bad Prose DB: {e}")
    
    def _check_vector_similarity(self, sentence: str) -> Optional[Tuple[float, str, str]]:
        """
        Check a sentence against the Bad Prose DB.
        
        Returns:
            (similarity, matched_text, fix_guidance) if ≥ threshold, else None
        """
        if not self.vector_store or not self.gemini_client:
            return None
        
        try:
            result = self.gemini_client.models.embed_content(
                model=self._embedding_model,
                contents=sentence
            )
            query_embedding = list(result.embeddings[0].values)
            
            results = self.vector_store.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["documents", "metadatas", "distances"]
            )
            
            if results and results["distances"] and results["distances"][0]:
                # ChromaDB returns distance; cosine similarity = 1 - distance
                distance = results["distances"][0][0]
                similarity = 1.0 - distance
                
                if similarity >= self.VECTOR_FLAG_THRESHOLD:
                    matched = results["documents"][0][0]
                    meta = results["metadatas"][0][0]
                    return (similarity, matched, meta.get("fix", "Rephrase naturally"))
                elif similarity >= self.VECTOR_WARN_THRESHOLD:
                    matched = results["documents"][0][0]
                    logger.debug(f"[HEAL] Vector WARN (sim={similarity:.3f}): {sentence[:60]}...")
        
        except Exception as e:
            logger.debug(f"[HEAL] Vector check failed: {e}")
        
        return None
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Layer 3: Psychic Distance Filter
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _check_psychic_distance(self, sentence: str) -> Optional[Tuple[str, str]]:
        """
        Check for psychic distance violations via regex.
        
        Returns:
            (category, fix_guidance) if violation found, else None
        """
        if self.target_language == "vn":
            # VN-specific patterns
            if self.VN_MOT_CACH.search(sentence):
                match = self.VN_MOT_CACH.search(sentence)
                return ("vn_mot_cach", f"Drop '{match.group()}' → move adjective before verb")
            if self.VN_MOT_CAM_GIAC.search(sentence):
                return ("vn_mot_cam_giac", "Drop 'một cảm giác' → express emotion directly")
            if self.VN_SU_NOMINAL.search(sentence):
                return ("vn_su_nominalization", "Drop 'sự/việc...của' → use verb form")
        
        # EN patterns
        if self.FILTER_WORDS.search(sentence):
            return ("filter_word", "Remove perception mediator — describe the experience directly, not the act of perceiving")
        if self.NOMINALIZATION_PATTERNS.search(sentence):
            return ("nominalization", "Replace weak verb + abstract noun with a strong verb")
        if self.PREPOSITIONAL_BLOAT.search(sentence):
            return ("prepositional_bloat", "Simplify spatial description — remove unnecessary prepositions")
        
        return None
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Self-Healing: LLM Correction
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _heal_sentence(self, sentence: str, category: str, fix_guidance: str, 
                       context_before: str = "", context_after: str = "") -> Optional[str]:
        """
        Use Gemini Flash to rewrite a flagged sentence.
        
        Args:
            sentence: The problematic sentence
            category: Issue category (for targeted prompting)
            fix_guidance: Specific fix instructions
            context_before: Previous 1-2 sentences for continuity
            context_after: Next 1-2 sentences for continuity
            
        Returns:
            Corrected sentence, or None if healing fails
        """
        if not self.llm_client:
            return None
        
        lang = "Vietnamese" if self.target_language == "vn" else "English"
        
        prompt = f"""You are a prose quality editor for {lang} light novel translations.

TASK: Rewrite ONLY the flagged sentence to fix the specific issue. Preserve meaning, tone, and character voice.

ISSUE CATEGORY: {category}
FIX GUIDANCE: {fix_guidance}

CONTEXT (do NOT modify these, only use for continuity):
Before: {context_before if context_before else "(start of paragraph)"}
After: {context_after if context_after else "(end of paragraph)"}

FLAGGED SENTENCE: {sentence}

RULES:
- Output ONLY the corrected sentence, nothing else
- Preserve the same tense, POV, and register
- Do NOT add new information or change meaning
- Do NOT wrap in quotes or add explanations
- Keep approximately the same sentence length
- If the sentence is actually fine in context, output it unchanged"""

        try:
            response = self.llm_client.models.generate_content(
                model=self._flash_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,  # Conservative for corrections
                    max_output_tokens=256,
                )
            )
            
            if response and response.text:
                corrected = response.text.strip()
                # Sanity check: correction shouldn't be radically different in length
                if len(corrected) > len(sentence) * 3 or len(corrected) < len(sentence) * 0.2:
                    logger.warning(f"[HEAL] Correction rejected (length mismatch): {len(corrected)} vs {len(sentence)}")
                    return None
                return corrected
            
        except Exception as e:
            logger.warning(f"[HEAL] LLM correction failed: {e}")
        
        return None
    
    def _heal_batch(self, issues: List[AIismIssue], sentences: List[str]) -> int:
        """
        Heal a batch of issues using batched LLM calls.
        
        Returns: Number of successfully healed issues
        """
        if not self.llm_client or not issues:
            return 0
        
        healed_count = 0
        
        # Group by severity: heal CRITICAL first, then MAJOR, then MINOR
        for severity in ["CRITICAL", "MAJOR", "MINOR"]:
            batch = [i for i in issues if i.severity == severity and i.corrected is None]
            
            for issue in batch:
                # Find context (previous and next sentences)
                ctx_before = ""
                ctx_after = ""
                line_idx = issue.line_number - 1
                if line_idx > 0 and line_idx - 1 < len(sentences):
                    ctx_before = sentences[line_idx - 1] if line_idx > 0 else ""
                if line_idx + 1 < len(sentences):
                    ctx_after = sentences[line_idx + 1]
                
                corrected = self._heal_sentence(
                    issue.sentence, issue.category, issue.fix_guidance,
                    ctx_before, ctx_after
                )
                
                if corrected and corrected != issue.sentence:
                    issue.corrected = corrected
                    healed_count += 1
                
                # Rate limiting
                time.sleep(0.5)
        
        return healed_count
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Main Processing
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _next_id(self) -> str:
        self._issue_counter += 1
        return f"AI_{self._issue_counter:04d}"
    
    def scan_text(self, text: str, filename: str = "") -> List[AIismIssue]:
        """
        Scan a text through all three detection layers.
        
        Args:
            text: Full chapter text
            filename: Source filename for reporting
            
        Returns:
            List of detected issues
        """
        issues = []
        lines = text.split('\n')
        
        # Track which lines already have issues (avoid duplicates across layers)
        flagged_lines: Dict[int, str] = {}  # line_num → highest severity
        
        severity_rank = {"CRITICAL": 3, "MAJOR": 2, "MINOR": 1}
        
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('[ILLUSTRATION'):
                continue
            
            # ── Layer 1: Regex scan ──
            severities_to_check = ["CRITICAL", "MAJOR", "MINOR"]
            if self.target_language == "vn":
                severities_to_check.append("VIETNAMESE_CRITICAL")
            
            for severity in severities_to_check:
                effective_sev = "CRITICAL" if severity == "VIETNAMESE_CRITICAL" else severity
                for pattern in self.regex_patterns.get(severity, []):
                    match = pattern["regex"].search(stripped)
                    if match:
                        # Check exceptions
                        exceptions = pattern.get("exceptions", [])
                        if any(exc.lower() in stripped.lower() for exc in exceptions):
                            continue
                        
                        # Only keep highest severity per line
                        existing = flagged_lines.get(line_num)
                        if existing and severity_rank.get(existing, 0) >= severity_rank.get(effective_sev, 0):
                            continue
                        
                        flagged_lines[line_num] = effective_sev
                        issues.append(AIismIssue(
                            issue_id=self._next_id(),
                            layer="regex",
                            severity=effective_sev,
                            category=pattern.get("category", severity.lower()),
                            line_number=line_num,
                            sentence=stripped,
                            matched_pattern=pattern["display"],
                            fix_guidance=pattern["fix"],
                            confidence=1.0,  # Regex = exact match
                        ))
                        break  # One hit per severity tier per line
            
            # ── Layer 2: Vector similarity (skip if already CRITICAL from regex) ──
            if line_num not in flagged_lines or flagged_lines[line_num] != "CRITICAL":
                if len(stripped) > 20:  # Skip very short lines
                    vector_result = self._check_vector_similarity(stripped)
                    if vector_result:
                        sim, matched_text, fix = vector_result
                        # Don't override existing regex hits of same or higher severity
                        if line_num not in flagged_lines:
                            sev = "MAJOR" if sim >= 0.88 else "MINOR"
                            flagged_lines[line_num] = sev
                            issues.append(AIismIssue(
                                issue_id=self._next_id(),
                                layer="vector",
                                severity=sev,
                                category="bad_prose_match",
                                line_number=line_num,
                                sentence=stripped,
                                matched_pattern=f"sim={sim:.3f} → {matched_text[:60]}...",
                                fix_guidance=fix,
                                confidence=sim,
                                vector_similarity=sim,
                            ))
            
            # ── Layer 3: Psychic distance (skip if already flagged) ──
            if line_num not in flagged_lines:
                pd_result = self._check_psychic_distance(stripped)
                if pd_result:
                    category, fix = pd_result
                    issues.append(AIismIssue(
                        issue_id=self._next_id(),
                        layer="psychic_distance",
                        severity="MINOR",
                        category=category,
                        line_number=line_num,
                        sentence=stripped,
                        matched_pattern=category,
                        fix_guidance=fix,
                        confidence=0.85,
                    ))
        
        return issues
    
    def heal_file(self, file_path: Path) -> Tuple[List[AIismIssue], int]:
        """
        Scan and optionally heal a single file.
        
        Returns:
            (issues, healed_count)
        """
        text = file_path.read_text(encoding='utf-8')
        lines = text.split('\n')
        
        # Scan
        issues = self.scan_text(text, file_path.name)
        
        if not issues:
            return issues, 0
        
        # Heal
        healed_count = 0
        if self.auto_heal and not self.dry_run:
            healed_count = self._heal_batch(issues, lines)
            
            # Apply corrections to text
            if healed_count > 0:
                corrected_lines = list(lines)
                for issue in issues:
                    if issue.corrected:
                        idx = issue.line_number - 1
                        if 0 <= idx < len(corrected_lines):
                            # Preserve leading whitespace
                            leading = len(corrected_lines[idx]) - len(corrected_lines[idx].lstrip())
                            corrected_lines[idx] = corrected_lines[idx][:leading] + issue.corrected
                
                # Write back
                file_path.write_text('\n'.join(corrected_lines), encoding='utf-8')
                logger.info(f"[HEAL] ✓ Applied {healed_count} corrections to {file_path.name}")
        
        return issues, healed_count
    
    def heal_volume(self, volume_path: Path) -> HealingReport:
        """
        Scan and heal all translated chapter files in a volume.
        
        Args:
            volume_path: Path to volume working directory
            
        Returns:
            HealingReport with full details
        """
        lang_dir = "VN" if self.target_language == "vn" else "EN"
        chapter_dir = volume_path / lang_dir
        
        if not chapter_dir.exists():
            logger.error(f"[HEAL] {lang_dir} directory not found: {chapter_dir}")
            return HealingReport(
                volume_id=volume_path.name,
                target_language=self.target_language,
                timestamp=datetime.now().isoformat(),
                files_processed=0,
                total_sentences=0,
            )
        
        # Find chapter files
        pattern = "CHAPTER_*_VN.md" if self.target_language == "vn" else "CHAPTER_*_EN.md"
        chapter_files = sorted(chapter_dir.glob(pattern))
        
        if not chapter_files:
            logger.warning(f"[HEAL] No chapter files found in {chapter_dir}")
            return HealingReport(
                volume_id=volume_path.name,
                target_language=self.target_language,
                timestamp=datetime.now().isoformat(),
                files_processed=0,
                total_sentences=0,
            )
        
        logger.info(f"[HEAL] Processing {len(chapter_files)} chapters in {chapter_dir}")
        
        all_issues = []
        total_healed = 0
        total_sentences = 0
        per_file = {}
        
        for chapter_file in chapter_files:
            text = chapter_file.read_text(encoding='utf-8')
            total_sentences += len([l for l in text.split('\n') if l.strip()])
            
            issues, healed = self.heal_file(chapter_file)
            all_issues.extend(issues)
            total_healed += healed
            
            per_file[chapter_file.name] = {
                "issues": len(issues),
                "healed": healed,
                "critical": sum(1 for i in issues if i.severity == "CRITICAL"),
                "major": sum(1 for i in issues if i.severity == "MAJOR"),
                "minor": sum(1 for i in issues if i.severity == "MINOR"),
            }
            
            status = "✓" if not issues else f"⚠ {len(issues)} issues ({healed} healed)"
            logger.info(f"  {chapter_file.name}: {status}")
        
        # Build report
        report = HealingReport(
            volume_id=volume_path.name,
            target_language=self.target_language,
            timestamp=datetime.now().isoformat(),
            files_processed=len(chapter_files),
            total_sentences=total_sentences,
            layer1_regex_hits=sum(1 for i in all_issues if i.layer == "regex"),
            layer2_vector_hits=sum(1 for i in all_issues if i.layer == "vector"),
            layer3_psychic_hits=sum(1 for i in all_issues if i.layer == "psychic_distance"),
            total_issues=len(all_issues),
            total_healed=total_healed,
            total_skipped=len(all_issues) - total_healed,
            critical_count=sum(1 for i in all_issues if i.severity == "CRITICAL"),
            major_count=sum(1 for i in all_issues if i.severity == "MAJOR"),
            minor_count=sum(1 for i in all_issues if i.severity == "MINOR"),
            issues=[asdict(i) for i in all_issues],
            per_file=per_file,
        )
        
        return report
    
    def save_report(self, report: HealingReport, output_dir: Path) -> Path:
        """Save healing report to JSON and markdown."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON report
        json_path = output_dir / "healing_report.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
        
        # Markdown summary
        md_path = output_dir / "HEALING_REPORT.md"
        md = self._generate_markdown_report(report)
        md_path.write_text(md, encoding='utf-8')
        
        logger.info(f"[HEAL] Reports saved to {output_dir}")
        return json_path
    
    def _generate_markdown_report(self, report: HealingReport) -> str:
        """Generate human-readable markdown report."""
        mode = "DRY RUN" if self.dry_run else "AUTO-HEAL"
        
        md = f"""# Self-Healing Anti-AI-ism Report

**Volume**: {report.volume_id}
**Language**: {report.target_language.upper()}
**Mode**: {mode}
**Timestamp**: {report.timestamp}

---

## Summary

| Metric | Count |
|--------|-------|
| Files processed | {report.files_processed} |
| Total sentences scanned | {report.total_sentences} |
| **Total issues found** | **{report.total_issues}** |
| Issues healed | {report.total_healed} |
| Issues remaining | {report.total_skipped} |

### By Severity

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | {report.critical_count} |
| 🟡 MAJOR | {report.major_count} |
| 🔵 MINOR | {report.minor_count} |

### By Detection Layer

| Layer | Hits | Description |
|-------|------|-------------|
| Layer 1: Regex | {report.layer1_regex_hits} | Pattern matching (65+ rules) |
| Layer 2: Vector | {report.layer2_vector_hits} | Bad Prose DB (cosine ≥ {self.VECTOR_FLAG_THRESHOLD}) |
| Layer 3: Psychic Distance | {report.layer3_psychic_hits} | Filter words, nominalizations, bloat |

### AI-ism Density

**{report.total_issues / max(report.total_sentences, 1) * 1000:.2f} per 1,000 lines** (target: < 0.02 per 1,000 words)

---

## Per-File Breakdown

| File | Issues | Healed | Critical | Major | Minor |
|------|--------|--------|----------|-------|-------|
"""
        for filename, stats in report.per_file.items():
            md += f"| {filename} | {stats['issues']} | {stats['healed']} | {stats['critical']} | {stats['major']} | {stats['minor']} |\n"
        
        # Show first 20 issues with details
        if report.issues:
            md += "\n---\n\n## Issue Details (first 20)\n\n"
            for issue in report.issues[:20]:
                sev_icon = {"CRITICAL": "🔴", "MAJOR": "🟡", "MINOR": "🔵"}.get(issue["severity"], "⚪")
                healed = "✅ HEALED" if issue.get("corrected") else "⏳ UNHEALED"
                
                md += f"### {sev_icon} {issue['issue_id']} [{issue['layer']}] {issue['category']}\n\n"
                md += f"**Line {issue['line_number']}**: `{issue['sentence'][:100]}`\n\n"
                md += f"**Pattern**: {issue['matched_pattern']}\n\n"
                md += f"**Fix**: {issue['fix_guidance']}\n\n"
                
                if issue.get("corrected"):
                    md += f"**Correction**: `{issue['corrected'][:100]}`\n\n"
                
                if issue.get("vector_similarity"):
                    md += f"**Vector similarity**: {issue['vector_similarity']:.3f}\n\n"
                
                md += f"**Status**: {healed}\n\n---\n\n"
        
        return md
    
    def print_summary(self, report: HealingReport):
        """Print a concise summary to console."""
        print()
        print("=" * 60)
        print("SELF-HEALING ANTI-AI-ISM REPORT")
        print("=" * 60)
        print(f"  Volume:    {report.volume_id}")
        print(f"  Language:  {report.target_language.upper()}")
        print(f"  Mode:      {'DRY RUN' if self.dry_run else 'AUTO-HEAL'}")
        print(f"  Files:     {report.files_processed}")
        print(f"  Sentences: {report.total_sentences}")
        print()
        print(f"  🔴 CRITICAL:  {report.critical_count}")
        print(f"  🟡 MAJOR:     {report.major_count}")
        print(f"  🔵 MINOR:     {report.minor_count}")
        print(f"  ─────────────────")
        print(f"  Total:     {report.total_issues}")
        print(f"  Healed:    {report.total_healed}")
        print(f"  Remaining: {report.total_skipped}")
        print()
        print(f"  Layer 1 (Regex):    {report.layer1_regex_hits} hits")
        print(f"  Layer 2 (Vector):   {report.layer2_vector_hits} hits")
        print(f"  Layer 3 (Psychic):  {report.layer3_psychic_hits} hits")
        print()
        
        density = report.total_issues / max(report.total_sentences, 1) * 1000
        if density < 0.5:
            print(f"  ✅ AI-ism density: {density:.2f}/1K lines — CLEAN")
        elif density < 2.0:
            print(f"  ⚠️  AI-ism density: {density:.2f}/1K lines — ACCEPTABLE")
        else:
            print(f"  🔴 AI-ism density: {density:.2f}/1K lines — NEEDS WORK")
        
        print("=" * 60)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """Standalone CLI for the Anti-AI-ism Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Self-Healing Anti-AI-ism Agent v1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python anti_ai_ism_agent.py /path/to/volume          # Scan + heal EN chapters
  python anti_ai_ism_agent.py /path/to/volume --vn     # Scan + heal VN chapters
  python anti_ai_ism_agent.py /path/to/volume --dry-run # Scan only, no changes
  python anti_ai_ism_agent.py /path/to/volume --no-vector # Skip Layer 2 (faster)
        """
    )
    parser.add_argument("volume_path", type=Path, help="Path to volume working directory")
    parser.add_argument("--vn", action="store_true", help="Target Vietnamese (default: English)")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, don't modify files")
    parser.add_argument("--no-heal", action="store_true", help="Disable LLM auto-correction")
    parser.add_argument("--no-vector", action="store_true", help="Disable Layer 2 (vector)")

    args = parser.parse_args()
    
    target_lang = "vn" if args.vn else "en"
    
    agent = AntiAIismAgent(
        auto_heal=not args.no_heal and not args.dry_run,
        dry_run=args.dry_run,
        target_language=target_lang,
        persist_directory=None if args.no_vector else None,
    )
    
    report = agent.heal_volume(args.volume_path)
    agent.print_summary(report)
    
    # Save report
    audit_dir = args.volume_path / "audits"
    agent.save_report(report, audit_dir)


if __name__ == "__main__":
    main()
