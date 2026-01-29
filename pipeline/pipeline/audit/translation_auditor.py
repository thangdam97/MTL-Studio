"""
Translation Auditor Module

Comprehensive audit system for JP-EN and JP-VN light novel translations.
Covers global requirements, English-specific rules, and Vietnamese-specific rules.

Anti-AI-ism patterns loaded from: config/anti_ai_ism_patterns.json
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# PATTERN LOADER - Single Source of Truth
# ============================================================

def load_anti_ai_patterns(config_path: Path = None) -> Dict:
    """Load anti-AI-ism patterns from JSON config file."""
    if config_path is None:
        # Default path relative to this file
        module_dir = Path(__file__).parent.parent.parent
        config_path = module_dir / "config" / "anti_ai_ism_patterns.json"
    
    if not config_path.exists():
        logger.warning(f"Pattern config not found at {config_path}, using built-in defaults")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_translationese_patterns(patterns_json: Dict) -> Tuple[List, List]:
    """Extract CRITICAL and MAJOR patterns in auditor tuple format."""
    critical = []
    major = []
    
    if patterns_json is None:
        return critical, major
    
    # CRITICAL patterns
    if "CRITICAL" in patterns_json:
        for p in patterns_json["CRITICAL"].get("patterns", []):
            critical.append((
                p["regex"],
                p["display"],
                p["fix"]
            ))
    
    # MAJOR patterns - flatten categories
    if "MAJOR" in patterns_json:
        for category_name, category_data in patterns_json["MAJOR"].get("categories", {}).items():
            for p in category_data.get("patterns", []):
                major.append((
                    p["regex"],
                    p["display"],
                    p["fix"]
                ))
    
    return critical, major


class Severity(Enum):
    """Issue severity levels."""
    CRITICAL = "critical"  # Blocks publication
    MAJOR = "major"        # Requires revision
    MINOR = "minor"        # Suggested improvement
    INFO = "info"          # Informational note


class IssueCategory(Enum):
    """Categories of audit issues."""
    # Global
    FIDELITY = "fidelity"
    NAME_CONSISTENCY = "name_consistency"
    TERMINOLOGY = "terminology"
    SAFETY = "safety"

    # EN-specific
    EN_AI_ISM = "en_ai_ism"
    EN_FORMALITY = "en_formality"
    EN_CONTRACTION = "en_contraction"
    EN_VOICE = "en_voice"

    # VN-specific
    VN_PRONOUN = "vn_pronoun"
    VN_PARTICLE = "vn_particle"
    VN_HAN_VIET = "vn_han_viet"
    VN_TRANSLATIONESE = "vn_translationese"
    VN_ARCHETYPE = "vn_archetype"


@dataclass
class AuditIssue:
    """Single audit issue found in translation."""
    category: IssueCategory
    severity: Severity
    message: str
    line_number: Optional[int] = None
    context: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class AuditResult:
    """Complete audit result for a chapter."""
    chapter_id: str
    target_language: str
    issues: List[AuditIssue] = field(default_factory=list)
    score: float = 100.0
    passed: bool = True

    def add_issue(self, issue: AuditIssue):
        self.issues.append(issue)
        # Deduct points based on severity
        if issue.severity == Severity.CRITICAL:
            self.score -= 20.0
            self.passed = False
        elif issue.severity == Severity.MAJOR:
            self.score -= 10.0
        elif issue.severity == Severity.MINOR:
            self.score -= 2.0
        self.score = max(0.0, self.score)

    def summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        by_severity = {}
        by_category = {}
        for issue in self.issues:
            sev = issue.severity.value
            cat = issue.category.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "chapter_id": self.chapter_id,
            "target_language": self.target_language,
            "score": round(self.score, 1),
            "passed": self.passed,
            "total_issues": len(self.issues),
            "by_severity": by_severity,
            "by_category": by_category,
        }


class TranslationAuditor:
    """
    Comprehensive translation auditor for EN and VN.

    Checks:
    - Global: Fidelity, name consistency, terminology, safety
    - EN: AI-isms, formality, contractions, character voice
    - VN: Pronouns, particles, Han-Viet ratio, translationese, archetypes
    
    Anti-AI-ism patterns loaded from: config/anti_ai_ism_patterns.json
    """

    # ============================================================
    # GLOBAL PATTERNS (Both EN and VN)
    # ============================================================

    # Safety content markers
    SAFETY_MARKERS = [
        r"\[FLAGGED:",
        r"\[UNTRANSLATABLE:",
        r"\[Content warning:",
        r"\[Canh bao noi dung:",
    ]

    # ============================================================
    # ENGLISH-SPECIFIC PATTERNS
    # ============================================================

    # AI-ism patterns to detect (EN) - Basic patterns kept as fallback
    EN_AI_ISM_PATTERNS = [
        # "A sense of" pattern
        (r"\ba sense of\b", "a sense of [emotion]", "Use direct emotion instead"),
        (r"\bfelt a sense of\b", "felt a sense of", "Use 'felt [adjective]' directly"),

        # "In a manner" pattern
        (r"\bin a \w+ manner\b", "in a [adj] manner", "Use adverb or rephrase"),

        # Hedging phrases
        (r"\bit can be said that\b", "it can be said that", "Just say it directly"),
        (r"\bone could say\b", "one could say", "Remove hedge"),
        (r"\bneedless to say\b", "needless to say", "If needless, don't say it"),
        (r"\bwithout a doubt\b", "without a doubt", "Use stronger word or delete"),

        # Formal AI-isms
        (r"\bindeed\b", "indeed", "Often unnecessary - consider removing"),
        (r"\bquite\b", "quite", "Often unnecessary - consider stronger word"),
        (r"\brather\b", "rather", "Often unnecessary in casual dialogue"),
        (r"\bI shall\b", "I shall", "Use 'I will' or 'I'll' for casual characters"),
        (r"\bmost certainly\b", "most certainly", "Too formal for most contexts"),
        (r"\bif you will\b", "if you will", "Remove this phrase"),
        (r"\bas it were\b", "as it were", "Remove this phrase"),
    ]

    def __init__(self, config_path: Path = None):
        """Initialize auditor with patterns from JSON config."""
        # Load patterns from JSON
        patterns_json = load_anti_ai_patterns(config_path)
        
        if patterns_json:
            self.EN_CRITICAL_TRANSLATIONESE, self.EN_MAJOR_TRANSLATIONESE = \
                extract_translationese_patterns(patterns_json)
            logger.info(f"Loaded {len(self.EN_CRITICAL_TRANSLATIONESE)} critical and "
                       f"{len(self.EN_MAJOR_TRANSLATIONESE)} major patterns from JSON config")
        else:
            # Fallback to hardcoded defaults
            self._load_fallback_patterns()
    
    def _load_fallback_patterns(self):
        """Load fallback patterns if JSON config not found."""
        self.EN_CRITICAL_TRANSLATIONESE = [
            (r"asserting (?:their|its|his|her) presence", 
             "asserting presence", 
             "Use: 'obvious' / 'impossible to ignore'"),
            (r"release(?:d|s|ing)? (?:their|his|her|sweet)? ?pheromones?",
             "release pheromones",
             "Use: 'ooze allure' / 'exude charm'"),
            (r"surreal (?:picture|scene|sight)",
             "surreal picture/scene",
             "Use: 'absurd situation' / 'how did I end up here?'"),
        ]
        self.EN_MAJOR_TRANSLATIONESE = [
            (r"\bit cannot be helped\b",
             "it cannot be helped",
             "Use: 'nothing I can do' / 'oh well'"),
            (r"\bas expected of\b",
             "as expected of",
             "Use: 'that's [Name] for you' / 'classic [Name]'"),
            (r"\bseemed to \w+",
             "seemed to [verb]",
             "Use direct verb: 'seemed to smile' → 'smiled'"),
        ]

    # Formal verbs to avoid in casual dialogue    # Formal verbs to avoid in casual dialogue
    EN_FORMAL_VERBS = [
        ("shall", "will/would"),
        ("procure", "get"),
        ("inquire", "ask"),
        ("purchase", "buy"),
        ("commence", "start/begin"),
        ("depart", "leave/go"),
        ("reside", "live"),
        ("obtain", "get"),
        ("require", "need"),
        ("sufficient", "enough"),
    ]

    # ============================================================
    # VIETNAMESE-SPECIFIC PATTERNS
    # ============================================================

    # VN Translationese patterns (EXPANDED)
    VN_TRANSLATIONESE_PATTERNS = [
        # ============================================================
        # SECTION 1: "Mot cam giac" - Emotion Wrapper Patterns
        # ============================================================
        (r"một cảm giác\s+\w+", "mot cam giac [emotion]", "Dung truc tiep: 'cam thay [tinh tu]'"),
        (r"cảm thấy một cảm giác", "cam thay mot cam giac", "Dung: 'cam thay [tinh tu]' truc tiep"),
        (r"có một cảm giác", "co mot cam giac", "Dung: 'cam thay' hoac hinh anh cu the"),
        (r"mang lại một cảm giác", "mang lai mot cam giac", "Dung dong tu manh hon"),
        (r"tạo ra một cảm giác", "tao ra mot cam giac", "Dung: 'khien [chu ngu] cam thay'"),
        (r"đem lại cảm giác", "dem lai cam giac", "Dung dong tu truc tiep"),

        # ============================================================
        # SECTION 2: "Mot cach" - Manner Adverb Patterns
        # ============================================================
        (r"một cách\s+\w+", "mot cach [adj]", "Dung trang tu: 'nhe nhang' thay vi 'mot cach nhe nhang'"),
        (r"theo một cách\s+\w+", "theo mot cach", "Bo 'theo mot cach', dung trang tu"),
        (r"bằng một cách", "bang mot cach", "Dung: 'bang cach' hoac cau truc lai"),

        # ============================================================
        # SECTION 3: "Viec/Dieu" - Abstract Subject Patterns
        # ============================================================
        (r"^Việc\s+\w+", "Viec [X] lam chu ngu", "Dung dong tu lam chu ngu truc tiep"),
        (r"^Điều\s+\w+\s+là", "Dieu [X] la", "Giam 'Dieu', dung cau truc truc tiep"),
        (r"điều đó\s+là\s+\w+", "dieu do la [X]", "Dung: '[X]' truc tiep, bo 'dieu do la'"),
        (r"sự\s+\w+\s+của", "su [X] cua", "Giam danh tu hoa, dung dong tu"),

        # ============================================================
        # SECTION 4: Passive Voice Overuse
        # ============================================================
        (r"bị\s+\w+\s+bởi", "bi [X] boi [Y]", "Chuyen sang chu dong: '[Y] [X] [chu ngu]'"),
        (r"được\s+\w+\s+bởi", "duoc [X] boi [Y]", "Chuyen sang chu dong: '[Y] [X] [chu ngu]'"),
        (r"đã được\s+\w+", "da duoc [X]", "Xem xet chuyen sang chu dong"),
        (r"sẽ được\s+\w+", "se duoc [X]", "Xem xet chuyen sang chu dong"),

        # ============================================================
        # SECTION 5: Hedging/Filler Phrases
        # ============================================================
        (r"có thể nói rằng", "co the noi rang", "Bo, noi truc tiep"),
        (r"người ta có thể nói", "nguoi ta co the noi", "Bo hedge, noi truc tiep"),
        (r"không cần phải nói", "khong can phai noi", "Neu khong can noi, dung noi"),
        (r"chắc chắn là", "chac chan la", "Thuong thua, xem xet bo"),
        (r"rõ ràng là", "ro rang la", "Thuong thua, dung truc tiep"),
        (r"thực sự là", "thuc su la", "Xem xet bo neu khong can thiet"),
        (r"quả thực là", "qua thuc la", "Chi dung cho OJOU archetype"),

        # ============================================================
        # SECTION 6: Redundant Constructions
        # ============================================================
        (r"bắt đầu\s+\w+", "bat dau [verb]", "Thuong thua, dung dong tu truc tiep"),
        (r"tiếp tục\s+\w+", "tiep tuc [verb]", "Xem xet co can thiet khong"),
        (r"quyết định\s+\w+", "quyet dinh [verb]", "Show action, khong can 'quyet dinh'"),
        (r"cố gắng\s+\w+", "co gang [verb]", "Thuong thua, show result"),

        # ============================================================
        # SECTION 7: Literal Japanese Structure Carry-over
        # ============================================================
        (r"đối với\s+\w+\s+mà nói", "doi voi [X] ma noi", "Cau truc JP, viet lai tu nhien"),
        (r"trong trường hợp của", "trong truong hop cua", "Don gian hoa: 'voi' hoac 'cua'"),
        (r"về phía\s+\w+", "ve phia [X]", "Don gian: 'cua [X]' hoac '[X]'"),
        (r"từ phía\s+\w+", "tu phia [X]", "Don gian: 'tu [X]'"),

        # ============================================================
        # SECTION 8: Weak Verb Patterns
        # ============================================================
        (r"thực hiện một\s+\w+", "thuc hien mot [noun]", "Dung dong tu cu the"),
        (r"tiến hành\s+\w+", "tien hanh [X]", "Dung dong tu cu the, khong 'tien hanh'"),
        (r"đưa ra một\s+\w+", "dua ra mot [noun]", "Dung dong tu cu the"),
        (r"có một\s+\w+\s+đối với", "co mot [X] doi voi", "Cau truc lai tu nhien"),

        # ============================================================
        # SECTION 9: Over-Explanation (Show Don't Tell)
        # ============================================================
        (r"bởi vì\s+\w+\s+nên", "boi vi [X] nen", "Thuong thua, ngam hieu tu context"),
        (r"do đó", "do do", "Thuong thua, ngam hieu tu context"),
        (r"vì vậy", "vi vay", "Su dung vua phai, khong lam dung"),
        (r"chính vì thế", "chinh vi the", "Qua formal, xem xet giam"),

        # ============================================================
        # SECTION 10: Literal Interjection Translation
        # ============================================================
        (r'"[Ee]e[,.]', "Ee (literal JP)", "Dung: 'A', 'Um', 'Uh'"),
        (r'"[Aa]a[,.]', "Aa (literal JP)", "Dung: 'A', 'Oi'"),
        (r'"[Uu]un[,.]', "Uun (literal JP)", "Dung: 'Khong', 'Um khong'"),
        (r'"[Hh]ai[,.]', "Hai (literal JP)", "Dung: 'Vang', 'Da', 'U'"),
        (r'"[Ee]to[,.]', "Eto (literal JP)", "Dung: 'A', 'Um', 'De xem'"),
        (r'"[Mm]aa[,.]', "Maa (literal JP)", "Dung: 'Ui', 'Thoi', 'Ma'"),
        (r'"[Hh]ora[,.]', "Hora (literal JP)", "Dung: 'Nay', 'Xem nay', 'Day'"),
        (r'"[Yy]are\s*yare', "Yare yare (literal JP)", "Dung: 'Troi oi', 'Thoi roi'"),
        (r'"[Cc]hotto', "Chotto (literal JP)", "Dung: 'Khoan', 'Oi', 'Doi da'"),

        # ============================================================
        # SECTION 11: Stiff Dialogue Patterns
        # ============================================================
        (r"tôi\s+không\s+hiểu\s+được", "toi khong hieu duoc", "Dung: 'Toi khong hieu' (tu nhien hon)"),
        (r"tôi\s+muốn\s+hỏi\s+rằng", "toi muon hoi rang", "Dung: 'Toi hoi' hoac hoi truc tiep"),
        (r"tôi\s+xin\s+phép\s+được", "toi xin phep duoc", "Qua formal tru khi OJOU"),
        (r"xin\s+hãy\s+cho\s+phép", "xin hay cho phep", "Qua formal tru khi can thiet"),

        # ============================================================
        # SECTION 12: Emotion Label Overuse
        # ============================================================
        (r"cảm thấy\s+\w+", "cam thay [emotion]", "Xem xet show qua hanh dong (>2/para = flag)"),
        (r"cảm xúc\s+\w+\s+dâng lên", "cam xuc dang len", "Dung hinh anh cu the"),
        (r"trái tim\s+\w+\s+đập", "trai tim dap", "OK neu <2/chapter, qua nhieu = AI-ism"),
        (r"lòng\s+\w+\s+trào dâng", "long trao dang", "Dung hinh anh cu the hon"),

        # ============================================================
        # SECTION 13: EN-Equivalent AI-isms (mapped from English)
        # ============================================================
        # "indeed" equivalents
        (r"\bquả thật\b", "qua that (indeed)", "Bo, tru OJOU archetype"),
        (r"\bquả thực\b", "qua thuc (indeed)", "Bo, tru OJOU archetype"),
        (r"\bthật vậy\b", "that vay (indeed)", "Xem xet bo neu khong can thiet"),

        # "quite/rather" equivalents
        (r"\bkhá là\b", "kha la (rather)", "Dung tu cu the hon, bo 'kha la'"),
        (r"\btương đối\b", "tuong doi (quite)", "Dung tu cu the: 'nhieu', 'it', v.v."),

        # "without a doubt" equivalents
        (r"không còn nghi ngờ gì", "khong con nghi ngo gi", "Dung tu manh: 'chac chan', 'ro rang'"),
        (r"không thể phủ nhận", "khong the phu nhan", "Noi truc tiep"),

        # "certainly/surely" overuse
        (r"\bchắc chắn là\b", "chac chan la", "Bo 'la', dung: 'chac chan [X]'"),
        (r"\bhẳn là\b", "han la", "Xem xet bo neu context da ro"),
        (r"\bắt hẳn\b", "at han", "Xem xet bo"),

        # "seem/appear" hedging
        (r"dường như là", "duong nhu la", "Bo 'la': 'duong nhu [X]'"),
        (r"có vẻ như là", "co ve nhu la", "Bo 'la': 'co ve [X]'"),
        (r"hình như là", "hinh nhu la", "Bo 'la': 'hinh nhu [X]'"),

        # "perhaps/maybe" overuse
        (r"có lẽ là", "co le la", "Bo 'la': 'co le [X]'"),
        (r"biết đâu là", "biet dau la", "Bo 'la'"),

        # "actually/in fact" filler
        (r"\bthực ra là\b", "thuc ra la", "Bo 'la': 'thuc ra, [X]'"),
        (r"\btrên thực tế\b", "tren thuc te", "Bo neu khong can thiet"),
        (r"\bthực chất là\b", "thuc chat la", "Don gian: 'thuc ra' hoac bo"),

        # "very/extremely" intensifier abuse
        (r"\brất là\b", "rat la", "Bo 'la': 'rat [X]'"),
        (r"\bvô cùng là\b", "vo cung la", "Bo 'la': 'vo cung [X]'"),
        (r"\bcực kỳ là\b", "cuc ky la", "Bo 'la': 'cuc ky [X]'"),

        # "of course" overuse
        (r"\bdĩ nhiên là\b", "di nhien la", "Bo 'la' hoac dung 'tat nhien'"),
        (r"\btất nhiên là\b", "tat nhien la", "Bo 'la': 'tat nhien, [X]'"),
        (r"\bđương nhiên là\b", "duong nhien la", "Bo 'la': 'duong nhien [X]'"),

        # "somehow" vagueness
        (r"bằng cách nào đó", "bang cach nao do (somehow)", "Cu the hoa hoac bo"),
        (r"không hiểu sao", "khong hieu sao", "Xem xet cu the hoa"),

        # "in order to" verbosity
        (r"để mà có thể", "de ma co the", "Rut gon: 'de [verb]'"),
        (r"nhằm mục đích", "nham muc dich", "Rut gon: 'de' hoac 'nham'"),

        # "what I mean is" padding
        (r"điều tôi muốn nói là", "dieu toi muon noi la", "Noi truc tiep"),
        (r"ý tôi là", "y toi la", "OK trong dialogue, tranh trong narration"),

        # "the fact that" nominalization
        (r"sự thật là", "su that la", "Don gian hoa cau"),
        (r"việc mà", "viec ma", "Bo 'viec ma', dung truc tiep"),
    ]

    # VN AI-ism frequency thresholds (per 1000 words)
    VN_AI_ISM_THRESHOLDS = {
        "cam_thay": 5,       # "cam thay" max 5 per 1000 words
        "mot_cach": 2,       # "mot cach" max 2 per 1000 words
        "passive": 3,        # Passive constructions max 3 per 1000 words
        "trai_tim": 2,       # Heart references max 2 per 1000 words
        "emotion_label": 8,  # Direct emotion labels max 8 per 1000 words
    }

    # VN Pronoun pairs for validation
    VN_FAMILY_PRONOUNS = {
        "sibling_younger": ("em", ["anh", "chị"]),
        "sibling_elder": (["anh", "chị"], "em"),
        "child_parent": ("con", ["ba", "mẹ", "bố"]),
    }

    # VN Banned pronoun combinations in family context
    VN_FAMILY_BANNED = ["tao", "mày", "tớ", "cậu"]

    # VN Archetype particles
    VN_ARCHETYPE_PARTICLES = {
        "OJOU": ["thưa", "ạ", "chẳng hay", "quả thật"],
        "GYARU": ["nha", "nè", "trời ơi", "đó mà"],
        "DELINQ": ["biến", "cút", "xử đẹp"],
        "KANSAI": ["nghen", "hông", "đâu có", "há"],
        "ONEE": ["nè", "nhé", "cơ mà", "bé ngoan"],
    }

    # VN RTAS warm particles (require RTAS >= 3.5)
    VN_WARM_PARTICLES = ["nha", "nè", "nhé", "nghen", "há"]

    # VN Defensive particles (TSUN mode)
    VN_DEFENSIVE_PARTICLES = ["đâu", "mà", "có gì đâu"]

    # VN Male friendship pronoun tiers
    VN_MALE_FRIENDSHIP_TIERS = {
        "tier1_distant": {
            "self": ["tớ"],
            "other": ["cậu"],
            "context": "new_classmate, acquaintance, first_meeting",
        },
        "tier2_close": {
            "self": ["tôi"],
            "other": ["ông"],
            "context": "good_friends, banter, teasing, trust",
        },
        "tier3_bros": {
            "self": ["tao"],
            "other": ["mày"],
            "context": "best_friends, very_informal, crude_jokes",
        },
    }

    # VN Female friendship pronoun tiers
    VN_FEMALE_FRIENDSHIP_TIERS = {
        "tier1_distant": {
            "self": ["tớ", "mình"],
            "other": ["cậu", "bạn"],
        },
        "tier2_close": {
            "self": ["tớ", "mình"],
            "other": ["cậu"],
        },
        "tier3_best": {
            "self": ["tao"],
            "other": ["mày"],
        },
    }

    def __init__(
        self,
        target_language: str = "en",
        glossary: Optional[Dict[str, str]] = None,
        character_profiles: Optional[Dict[str, Dict]] = None,
    ):
        """
        Initialize auditor.

        Args:
            target_language: "en" or "vn"
            glossary: Term glossary {jp_term: translated_term}
            character_profiles: Character info {name: {archetype, rtas, family_relations}}
        """
        self.target_language = target_language.lower()
        self.glossary = glossary or {}
        self.character_profiles = character_profiles or {}

        logger.info(f"Initialized TranslationAuditor for {target_language}")

    def audit_chapter(
        self,
        content: str,
        chapter_id: str,
        source_content: Optional[str] = None,
    ) -> AuditResult:
        """
        Audit a translated chapter.

        Args:
            content: Translated chapter content
            chapter_id: Chapter identifier
            source_content: Original Japanese content (for fidelity check)

        Returns:
            AuditResult with all detected issues
        """
        result = AuditResult(chapter_id=chapter_id, target_language=self.target_language)
        lines = content.split("\n")

        # Global audits
        self._audit_global(content, lines, result)

        # Language-specific audits
        if self.target_language == "en":
            self._audit_english(content, lines, result)
        elif self.target_language in ("vn", "vi"):
            self._audit_vietnamese(content, lines, result)

        # Fidelity check if source provided
        if source_content:
            self._audit_fidelity(content, source_content, result)

        logger.info(f"Audit complete for {chapter_id}: score={result.score}, issues={len(result.issues)}")
        return result

    # ============================================================
    # GLOBAL AUDITS
    # ============================================================

    def _audit_global(self, content: str, lines: List[str], result: AuditResult):
        """Run global audits (both EN and VN)."""

        # Check for safety markers
        for pattern in self.SAFETY_MARKERS:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    result.add_issue(AuditIssue(
                        category=IssueCategory.SAFETY,
                        severity=Severity.INFO,
                        message=f"Safety marker found: {pattern}",
                        line_number=i,
                        context=line.strip()[:100],
                    ))

        # Check glossary consistency
        if self.glossary:
            self._check_glossary_consistency(content, lines, result)

        # Check name consistency
        self._check_name_consistency(content, lines, result)

    def _check_glossary_consistency(self, content: str, lines: List[str], result: AuditResult):
        """Check if glossary terms are used consistently."""
        for jp_term, translated in self.glossary.items():
            if translated.lower() not in content.lower():
                # Term might be missing - check if it should appear
                pass  # Skip for now - would need source comparison

    def _check_name_consistency(self, content: str, lines: List[str], result: AuditResult):
        """Check for name order and spelling consistency."""
        # Check for Western name order (Given Surname) when should be Japanese order
        name_pattern = r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'

        for match in re.finditer(name_pattern, content):
            full_name = match.group(0)
            # This is a simplified check - real implementation would use character_profiles
            # to validate correct name order

    # ============================================================
    # ENGLISH AUDITS
    # ============================================================

    def _audit_english(self, content: str, lines: List[str], result: AuditResult):
        """Run English-specific audits."""

        # Check AI-ism patterns
        self._check_en_ai_isms(content, lines, result)

        # Check formal verbs in casual dialogue
        self._check_en_formal_verbs(content, lines, result)

        # Check contraction rate
        self._check_en_contractions(content, lines, result)

        # Check character voice consistency
        self._check_en_voice(content, lines, result)

    def _check_en_ai_isms(self, content: str, lines: List[str], result: AuditResult):
        """Detect AI-ism patterns in English text."""
        for pattern, name, suggestion in self.EN_AI_ISM_PATTERNS:
            for i, line in enumerate(lines, 1):
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    result.add_issue(AuditIssue(
                        category=IssueCategory.EN_AI_ISM,
                        severity=Severity.MAJOR,
                        message=f"AI-ism detected: '{name}'",
                        line_number=i,
                        context=line.strip()[:100],
                        suggestion=suggestion,
                    ))

    def _check_en_formal_verbs(self, content: str, lines: List[str], result: AuditResult):
        """Check for overly formal verbs in casual dialogue."""
        dialogue_pattern = r'"([^"]+)"'

        for i, line in enumerate(lines, 1):
            dialogues = re.findall(dialogue_pattern, line)
            for dialogue in dialogues:
                for formal, casual in self.EN_FORMAL_VERBS:
                    if re.search(r'\b' + formal + r'\b', dialogue, re.IGNORECASE):
                        result.add_issue(AuditIssue(
                            category=IssueCategory.EN_FORMALITY,
                            severity=Severity.MINOR,
                            message=f"Formal verb '{formal}' in dialogue",
                            line_number=i,
                            context=dialogue[:80],
                            suggestion=f"Consider using '{casual}' for casual characters",
                        ))

    def _check_en_contractions(self, content: str, lines: List[str], result: AuditResult):
        """Check contraction rate in dialogue."""
        dialogue_pattern = r'"([^"]+)"'

        total_opportunities = 0
        total_contractions = 0
        critical_violations = []
        high_priority_violations = []

        # CRITICAL: Must always contract (unless emphatic)
        critical_opportunities = [
            (r"\bit is\b", "it's"),
            (r"\bthat is\b", "that's"),
            (r"\bthere is\b", "there's"),
            (r"\bwhat is\b", "what's"),
            (r"\bdo not\b", "don't"),
            (r"\bdoes not\b", "doesn't"),
            (r"\bcannot\b", "can't"),
            (r"\bwill not\b", "won't"),
        ]
        
        # HIGH PRIORITY: Should contract in casual dialogue
        high_priority_opportunities = [
            (r"\bwas not\b", "wasn't"),
            (r"\bwere not\b", "weren't"),
            (r"\bcould not\b", "couldn't"),
            (r"\bshould not\b", "shouldn't"),
            (r"\bwould not\b", "wouldn't"),
            (r"\bdid not\b", "didn't"),
            (r"\bhas not\b", "hasn't"),
        ]
        
        # STANDARD: Common contractions
        standard_opportunities = [
            (r"\bI am\b", "I'm"),
            (r"\bI will\b", "I'll"),
            (r"\bI have\b", "I've"),
            (r"\bI would\b", "I'd"),
            (r"\byou are\b", "you're"),
            (r"\byou will\b", "you'll"),
            (r"\bwe are\b", "we're"),
            (r"\bthey are\b", "they're"),
            (r"\bis not\b", "isn't"),
            (r"\bare not\b", "aren't"),
            (r"\bhave not\b", "haven't"),
            (r"\bhad not\b", "hadn't"),
            (r"\bwho is\b", "who's"),
            (r"\bhere is\b", "here's"),
            (r"\blet us\b", "let's"),
        ]
        
        # J-Novel Club perfect tense contractions
        perfect_tense_opportunities = [
            (r"\bwould have\b", "would've"),
            (r"\bcould have\b", "could've"),
            (r"\bshould have\b", "should've"),
            (r"\bmight have\b", "might've"),
            (r"\bmust have\b", "must've"),
        ]
        
        # Combine all opportunities
        all_opportunities = (
            critical_opportunities + 
            high_priority_opportunities + 
            standard_opportunities + 
            perfect_tense_opportunities
        )

        for i, line in enumerate(lines, 1):
            dialogues = re.findall(dialogue_pattern, line)
            for dialogue in dialogues:
                # Check critical violations specifically
                for full_form, contracted in critical_opportunities:
                    matches = re.findall(full_form, dialogue, re.IGNORECASE)
                    if matches:
                        critical_violations.append({
                            'line': i,
                            'form': full_form.replace(r'\b', ''),
                            'contracted': contracted,
                            'context': dialogue[:60]
                        })
                        total_opportunities += len(matches)
                
                # Check high priority violations specifically
                for full_form, contracted in high_priority_opportunities:
                    matches = re.findall(full_form, dialogue, re.IGNORECASE)
                    if matches:
                        high_priority_violations.append({
                            'line': i,
                            'form': full_form.replace(r'\b', ''),
                            'contracted': contracted,
                            'context': dialogue[:60]
                        })
                        total_opportunities += len(matches)
                
                # Check standard opportunities
                for full_form, contracted in standard_opportunities + perfect_tense_opportunities:
                    full_matches = len(re.findall(full_form, dialogue, re.IGNORECASE))
                    total_opportunities += full_matches

                # Count actual contractions
                contraction_pattern = r"'(m|ll|ve|d|re|t|s)\b"
                total_contractions += len(re.findall(contraction_pattern, dialogue))

        if total_opportunities > 0:
            contraction_rate = total_contractions / (total_opportunities + total_contractions) if (total_opportunities + total_contractions) > 0 else 0

            # Gold Standard: 99%+ for Yen Press/J-Novel Club quality
            # Tiered severity based on rate
            if contraction_rate < 0.95:
                # Critical: Below professional standard
                result.add_issue(AuditIssue(
                    category=IssueCategory.EN_CONTRACTION,
                    severity=Severity.CRITICAL,
                    message=f"Low contraction rate: {contraction_rate:.1%} (Gold Standard: 99%+)",
                    suggestion="Apply contractions to all casual dialogue for natural speech",
                ))
            elif contraction_rate < 0.99:
                # Major: Meets basic standard but not gold
                result.add_issue(AuditIssue(
                    category=IssueCategory.EN_CONTRACTION,
                    severity=Severity.MAJOR,
                    message=f"Contraction rate {contraction_rate:.1%} below gold standard (99%+)",
                    suggestion="Review borderline cases to reach Yen Press/J-Novel Club level",
                ))
        
        # Report critical violations specifically
        if critical_violations:
            for v in critical_violations[:5]:  # Limit to first 5
                result.add_issue(AuditIssue(
                    category=IssueCategory.EN_CONTRACTION,
                    severity=Severity.MAJOR,
                    message=f"Critical: '{v['form']}' should be '{v['contracted']}'",
                    line_number=v['line'],
                    context=v['context'],
                    suggestion=f"Contract '{v['form']}' → '{v['contracted']}' (required in casual dialogue)",
                ))
        
        # Report high-priority violations
        if high_priority_violations:
            for v in high_priority_violations[:3]:  # Limit to first 3
                result.add_issue(AuditIssue(
                    category=IssueCategory.EN_CONTRACTION,
                    severity=Severity.MINOR,
                    message=f"High priority: '{v['form']}' → '{v['contracted']}'",
                    line_number=v['line'],
                    context=v['context'],
                    suggestion=f"Contract unless emphatic or formal context",
                ))

    def _check_en_voice(self, content: str, lines: List[str], result: AuditResult):
        """Check character voice consistency."""
        # This would need character_profiles to be meaningful
        # Placeholder for voice consistency checks
        pass

    # ============================================================
    # VIETNAMESE AUDITS
    # ============================================================

    def _audit_vietnamese(self, content: str, lines: List[str], result: AuditResult):
        """Run Vietnamese-specific audits."""

        # Check translationese patterns
        self._check_vn_translationese(content, lines, result)

        # Check AI-ism frequency thresholds
        self._check_vn_ai_ism_frequency(content, result)

        # Check pronoun consistency
        self._check_vn_pronouns(content, lines, result)

        # Check particle usage
        self._check_vn_particles(content, lines, result)

        # Check family pronoun violations
        self._check_vn_family_pronouns(content, lines, result)

    def _check_vn_ai_ism_frequency(self, content: str, result: AuditResult):
        """Check for overuse of common AI-ism patterns based on frequency thresholds."""
        # Normalize content for counting
        content_lower = content.lower()

        # Count words (rough estimate for Vietnamese)
        word_count = len(content.split())
        if word_count == 0:
            return

        # Calculate per-1000-word ratio
        ratio_multiplier = 1000 / word_count

        # Frequency patterns to check
        frequency_checks = [
            # (pattern, threshold_key, name, suggestion)
            (r"cảm thấy", "cam_thay", "cam thay",
             "Qua nhieu 'cam thay' - dung hinh anh/hanh dong the hien cam xuc"),
            (r"một cách", "mot_cach", "mot cach",
             "Qua nhieu 'mot cach' - dung trang tu truc tiep"),
            (r"(bị|được)\s+\w+\s+bởi", "passive", "cau truc bi dong",
             "Qua nhieu bi dong - chuyen sang chu dong"),
            (r"trái tim", "trai_tim", "trai tim",
             "Qua nhieu 'trai tim' - dung hinh anh da dang hon"),
            (r"(vui|buồn|giận|sợ|lo|hạnh phúc|đau|khổ)", "emotion_label", "nhan cam xuc",
             "Qua nhieu nhan cam xuc truc tiep - show don't tell"),
        ]

        for pattern, threshold_key, name, suggestion in frequency_checks:
            matches = len(re.findall(pattern, content_lower, re.IGNORECASE))
            normalized_count = matches * ratio_multiplier
            threshold = self.VN_AI_ISM_THRESHOLDS.get(threshold_key, 999)

            if normalized_count > threshold:
                severity = Severity.CRITICAL if normalized_count > threshold * 2 else Severity.MAJOR
                result.add_issue(AuditIssue(
                    category=IssueCategory.VN_TRANSLATIONESE,
                    severity=severity,
                    message=f"AI-ism frequency exceeded: '{name}' = {matches}x ({normalized_count:.1f}/1000 words, max: {threshold})",
                    suggestion=suggestion,
                ))

    def _check_vn_translationese(self, content: str, lines: List[str], result: AuditResult):
        """Detect translationese patterns in Vietnamese text."""
        for pattern, name, suggestion in self.VN_TRANSLATIONESE_PATTERNS:
            for i, line in enumerate(lines, 1):
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    result.add_issue(AuditIssue(
                        category=IssueCategory.VN_TRANSLATIONESE,
                        severity=Severity.MAJOR,
                        message=f"Translationese detected: '{name}'",
                        line_number=i,
                        context=line.strip()[:100],
                        suggestion=suggestion,
                    ))

    def _check_vn_pronouns(self, content: str, lines: List[str], result: AuditResult):
        """Check for pronoun consistency issues."""
        # Check for mixed pronouns in same paragraph
        pronoun_sets = [
            (r'\btôi\b', r'\bmình\b'),  # toi vs minh mixing
            (r'\btớ\b', r'\btui\b'),     # to vs tui mixing
        ]

        paragraphs = content.split("\n\n")
        for para_idx, para in enumerate(paragraphs):
            for p1, p2 in pronoun_sets:
                has_p1 = bool(re.search(p1, para, re.IGNORECASE))
                has_p2 = bool(re.search(p2, para, re.IGNORECASE))

                if has_p1 and has_p2:
                    # Could be valid (narrative override) - check context
                    result.add_issue(AuditIssue(
                        category=IssueCategory.VN_PRONOUN,
                        severity=Severity.MINOR,
                        message=f"Mixed first-person pronouns in paragraph {para_idx + 1}",
                        context=para[:100],
                        suggestion="Check if mixing is intentional (narrative override) or error",
                    ))

    def _check_vn_particles(self, content: str, lines: List[str], result: AuditResult):
        """Check particle usage matches character context."""
        dialogue_pattern = r'"([^"]+)"'

        for i, line in enumerate(lines, 1):
            dialogues = re.findall(dialogue_pattern, line)
            for dialogue in dialogues:
                # Check for warm particles that might be misplaced
                warm_count = sum(1 for p in self.VN_WARM_PARTICLES if p in dialogue.lower())

                # Check for defensive particles
                defensive_count = sum(1 for p in self.VN_DEFENSIVE_PARTICLES if p in dialogue.lower())

                # Flag if both warm and defensive in same dialogue (potential inconsistency)
                if warm_count > 0 and defensive_count > 0:
                    result.add_issue(AuditIssue(
                        category=IssueCategory.VN_PARTICLE,
                        severity=Severity.MINOR,
                        message="Mixed warm and defensive particles in same dialogue",
                        line_number=i,
                        context=dialogue[:80],
                        suggestion="Check if character state (TSUN/DERE) is consistent",
                    ))

    def _check_vn_family_pronouns(self, content: str, lines: List[str], result: AuditResult):
        """Check for banned pronouns in family context."""
        # This needs character_profiles to identify family relationships
        # For now, check for obvious violations

        family_indicators = [
            r'\bem\s+gái\b',
            r'\banh\s+trai\b',
            r'\bchị\s+gái\b',
            r'\bba\b',
            r'\bmẹ\b',
            r'\bcon\s+trai\b',
            r'\bcon\s+gái\b',
        ]

        for i, line in enumerate(lines, 1):
            # Check if line has family context
            has_family = any(re.search(ind, line, re.IGNORECASE) for ind in family_indicators)

            if has_family:
                # Check for banned pronouns
                for banned in self.VN_FAMILY_BANNED:
                    if re.search(r'\b' + banned + r'\b', line, re.IGNORECASE):
                        result.add_issue(AuditIssue(
                            category=IssueCategory.VN_PRONOUN,
                            severity=Severity.CRITICAL,
                            message=f"Banned pronoun '{banned}' used in family context",
                            line_number=i,
                            context=line.strip()[:100],
                            suggestion="Use family pronouns (anh/chi/em) for family members",
                        ))

    # ============================================================
    # FIDELITY AUDITS
    # ============================================================

    def _audit_fidelity(self, content: str, source: str, result: AuditResult):
        """Check translation fidelity against source."""
        # Count sentences roughly
        source_sentences = len(re.findall(r'[。！？]', source))

        if self.target_language == "en":
            target_sentences = len(re.findall(r'[.!?](?:\s|$)', content))
        else:  # VN
            target_sentences = len(re.findall(r'[.!?](?:\s|$)', content))

        # Allow 10% variance
        if source_sentences > 0:
            ratio = target_sentences / source_sentences
            if ratio < 0.9 or ratio > 1.1:
                result.add_issue(AuditIssue(
                    category=IssueCategory.FIDELITY,
                    severity=Severity.MAJOR if abs(1 - ratio) < 0.2 else Severity.CRITICAL,
                    message=f"Sentence count mismatch: source={source_sentences}, target={target_sentences} (ratio: {ratio:.2f})",
                    suggestion="Check for missing or added content",
                ))


def audit_translation(
    content: str,
    chapter_id: str,
    target_language: str = "en",
    source_content: Optional[str] = None,
    glossary: Optional[Dict[str, str]] = None,
    character_profiles: Optional[Dict[str, Dict]] = None,
) -> AuditResult:
    """
    Convenience function to audit a translation.

    Args:
        content: Translated chapter content
        chapter_id: Chapter identifier
        target_language: "en" or "vn"
        source_content: Original Japanese content
        glossary: Term glossary
        character_profiles: Character info

    Returns:
        AuditResult with all detected issues
    """
    auditor = TranslationAuditor(
        target_language=target_language,
        glossary=glossary,
        character_profiles=character_profiles,
    )
    return auditor.audit_chapter(content, chapter_id, source_content)
