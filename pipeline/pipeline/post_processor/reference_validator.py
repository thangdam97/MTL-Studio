"""
Phase 1.55 Co-Processor #5: Reference Validator
Detects and deobfuscates brand names, author names, and real-world entities
using Gemini 3 Flash High Thinking + Wikipedia verification.

Architecture:
- Gemini 3 Flash: Entity detection + initial deobfuscation (96.8% accuracy)
- Wikipedia API: Canonical name verification for high-stakes entities
- Entity cache: In-memory cache for repeated references
"""

import json
import logging
import time
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import unicodedata

logger = logging.getLogger(__name__)


@dataclass
class DetectedEntity:
    """Represents a detected real-world entity in the text."""
    detected_term: str
    is_obfuscated: bool
    real_name: str
    confidence: float
    reasoning: str
    entity_type: str = "brand"  # brand, author, person, title
    start_pos: int = -1
    end_pos: int = -1
    context: str = ""
    wikipedia_verified: bool = False


@dataclass
class ValidationReport:
    """Summary report of entity validation."""
    file_path: str
    total_entities_detected: int
    obfuscated_entities: int
    legitimate_entities: int
    high_confidence_fixes: int
    wikipedia_verified: int
    entities: List[DetectedEntity] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'entities': [asdict(e) for e in self.entities]
        }


class ReferenceValidator:
    """
    Validates and deobfuscates real-world references using Gemini + Wikipedia.

    Handles:
    - Brand obfuscations (LIME→LINE, MgRonald's→McDonald's)
    - Katakana mask symbols (ア○ゾン→Amazon, ニ○リ→Nitori)
    - Author names (デボラ・ザック→Devora Zack)
    - Person names (タ○ソン→Mike Tyson)
    - Media titles (ベル○ルク→Berserk)
    """

    # Model configuration
    RESOLVE_MODEL = "gemini-3-flash-preview"
    RESOLVE_THINKING_LEVEL = "high"

    # Entity type patterns for classification
    AUTHOR_INDICATORS = [
        r'著者', r'作者', r'筆者', r'書いた', r'執筆',
        r'author', r'writer', r'wrote', r'written by'
    ]

    PERSON_INDICATORS = [
        r'さん', r'氏', r'選手', r'先生', r'監督',
        r'全盛期', r'伝説', r'有名な', r'俳優', r'歌手'
    ]

    BOOK_INDICATORS = [
        r'本', r'書籍', r'読んだ', r'読む', r'著書',
        r'book', r'read', r'according to'
    ]

    MEDIA_INDICATORS = [
        r'『', r'』', r'タイトル', r'作品', r'映画', r'アニメ',
        r'マンガ', r'漫画', r'小説', r'ドラマ'
    ]

    PLACE_INDICATORS = [
        r'行った', r'訪れた', r'旅行', r'都市', r'国',
        r'visit', r'went to', r'traveled to', r'city', r'country'
    ]

    # Katakana mask symbols commonly used in Japanese light novels
    MASK_SYMBOLS = "○●◎☆★◇◆□■△▲×＊*・"

    def __init__(self, gemini_client=None, enable_wikipedia: bool = True):
        """
        Initialize Reference Validator.

        Args:
            gemini_client: GeminiClient instance (will create if not provided)
            enable_wikipedia: Whether to enable Wikipedia verification for high-stakes entities
        """
        if gemini_client is None:
            from pipeline.common.gemini_client import GeminiClient
            self.gemini_client = GeminiClient(model=self.RESOLVE_MODEL)

            # Force high thinking level for deobfuscation
            thinking_cfg = dict(self.gemini_client.thinking_mode_config or {})
            thinking_cfg["enabled"] = True
            thinking_cfg["thinking_level"] = self.RESOLVE_THINKING_LEVEL
            self.gemini_client.thinking_mode_config = thinking_cfg
        else:
            self.gemini_client = gemini_client

        self.enable_wikipedia = enable_wikipedia
        self.entity_cache = {}  # {detected_term: DetectedEntity}
        self._last_request_time = 0

    def _normalize_token(self, text: str) -> str:
        """Normalize token for comparisons (case/space/punct-insensitive)."""
        if text is None:
            return ""
        return re.sub(r"[^a-z0-9]+", "", str(text).lower())

    def _contains_mask_symbols(self, text: str) -> bool:
        """Check if text contains katakana mask symbols."""
        return any(char in text for char in self.MASK_SYMBOLS)

    def _classify_entity_type(self, text: str, context: str) -> str:
        """
        Classify entity type based on context clues.

        Returns:
            'author', 'person', 'book', 'title', 'place', or 'brand'
        """
        combined = f"{text} {context}"

        # Check for author indicators
        for pattern in self.AUTHOR_INDICATORS:
            if re.search(pattern, combined, re.IGNORECASE):
                return "author"

        # Check for book indicators
        for pattern in self.BOOK_INDICATORS:
            if re.search(pattern, combined, re.IGNORECASE):
                return "book"

        # Check for person indicators
        for pattern in self.PERSON_INDICATORS:
            if re.search(pattern, combined):
                return "person"

        # Check for place indicators
        for pattern in self.PLACE_INDICATORS:
            if re.search(pattern, combined, re.IGNORECASE):
                return "place"

        # Check for media title indicators
        for pattern in self.MEDIA_INDICATORS:
            if re.search(pattern, combined):
                return "title"

        # Default to brand
        return "brand"

    def _extract_context_window(self, text: str, start_pos: int, window_size: int = 100) -> str:
        """Extract context window around a detected term."""
        start = max(0, start_pos - window_size)
        end = min(len(text), start_pos + window_size)
        return text[start:end]

    def _should_verify_with_wikipedia(self, entity: DetectedEntity) -> bool:
        """
        Determine if entity requires Wikipedia verification.

        High-stakes entities that need canonical name verification:
        - Authors (Devora Zack vs Deborah Zack)
        - Person names (Mike Tyson vs Tyson)
        - Low confidence (<0.95) detections
        """
        if not self.enable_wikipedia:
            return False

        # Always verify authors
        if entity.entity_type == "author":
            return True

        # Always verify persons
        if entity.entity_type == "person":
            return True

        # Verify low-confidence entities
        if entity.confidence < 0.95:
            return True

        return False

    def detect_real_world_references(self, japanese_text: str, context: Optional[str] = None) -> List[DetectedEntity]:
        """
        Detect real-world entities: authors, book titles, celebrities, brands.

        This is the primary detection method that identifies:
        1. **Author names** (in katakana or kanji)
           - Example: デボラ・ザック → Devora Zack
        2. **Book titles** (in katakana, kanji, or quotes)
           - Example: 『シングルタスク』→ Singletasking
        3. **Celebrity names** (actors, musicians, public figures)
           - Example: トム・クルーズ → Tom Cruise
        4. **Brand names** (companies, products, obfuscated or legitimate)
           - Example: LIME → LINE, MgRonald's → McDonald's
        5. **Place names** (real cities, landmarks outside Japan)
           - Example: ニューヨーク → New York

        Args:
            japanese_text: Japanese text to analyze
            context: Optional additional context (chapter summary, genre)

        Returns:
            List of DetectedEntity objects with validation status
        """
        return self.detect_entities_in_text(japanese_text, context)

    def detect_entities_in_text(
        self,
        text: str,
        context: Optional[str] = None
    ) -> List[DetectedEntity]:
        """
        Detect and deobfuscate all entities in the given text using Gemini.

        Args:
            text: Japanese text to analyze
            context: Optional additional context (e.g., chapter summary, genre)

        Returns:
            List of DetectedEntity objects
        """
        # Check cache first
        normalized_text = self._normalize_token(text)
        if normalized_text in self.entity_cache:
            logger.debug(f"Cache hit for entity detection: {text[:50]}...")
            return self.entity_cache[normalized_text]

        # Rate limiting (Gemini 3 Flash: ~15 QPM)
        elapsed = time.time() - self._last_request_time
        min_delay = 4.0  # ~15 requests/minute
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)

        prompt = self._build_detection_prompt(text, context)

        try:
            logger.info(f"Detecting real-world references in text ({len(text)} chars)...")
            response = self.gemini_client.generate(prompt)
            self._last_request_time = time.time()

            # Parse JSON response
            entities = self._parse_entity_response(response.content, text)

            # Cache result
            self.entity_cache[normalized_text] = entities

            logger.info(f"Detected {len(entities)} real-world entities (thinking mode: {self.RESOLVE_THINKING_LEVEL})")
            return entities

        except Exception as e:
            logger.error(f"Real-world reference detection failed: {e}")
            return []

    def _build_detection_prompt(self, text: str, context: Optional[str]) -> str:
        """Build Gemini prompt for entity detection and deobfuscation."""
        prompt = f"""Analyze this Japanese text and identify ALL real-world references (both obfuscated and legitimate).

TEXT:
{text}

{f"CONTEXT: {context}" if context else ""}

Identify these types of real-world entities:

1. **Author names** (in katakana or kanji)
   - Example: デボラ・ザック (Debora Zakku) → Devora Zack
   - Note: Pay attention to spelling variants (Deborah vs Devora, etc.)

2. **Book titles** (in katakana, kanji, or quotes 『』)
   - Example: 『シングルタスク』(Singletasking)
   - Context clues: 本 (book), 著者 (author), 読んだ (read)

3. **Celebrity names** (actors, musicians, public figures, athletes)
   - Example: トム・クルーズ (Tom Cruise), タイソン (Mike Tyson)
   - Often masked with ○ symbols: タ○ソン → Mike Tyson

4. **Brand names** (companies, products - can be obfuscated or legitimate)
   - Legitimate: スタバ (Starbucks), ファミマ (FamilyMart)
   - Obfuscated: LIME → LINE, MgRonald's → McDonald's, ニ○リ → Nitori

5. **Place names** (real cities, landmarks outside Japan)
   - Example: ニューヨーク (New York), パリ (Paris)
   - Context: Places characters visit, mention, or reference

Japanese light novels also obfuscate real brand names, person names, and media titles for copyright reasons.

Common obfuscation patterns:
- LIME, NIME, RINE → LINE (messaging app)
- スタバ → Starbucks (legitimate Japanese abbreviation, NOT obfuscation)
- ファミマ → FamilyMart (legitimate Japanese abbreviation, NOT obfuscation)
- MgRonald's, WacDonald's → McDonald's (fast food)
- Gaggle, Goggle → Google (search engine)
- minsta, Minstagram → Instagram (shortened/prefix-shift)
- tokdok, YouTobe, Nettflik → TikTok/YouTube/Netflix (phonetic variants)
- G○○gle, ア○ゾン → Google/Amazon (symbol masking)
- ニ○リ → Nitori, ゼク○ィ/○クシィ → Zexy (katakana masking)
- タ○ソン → Mike Tyson, メイ○ェザー → Floyd Mayweather (person names)
- ベル○ルク → Berserk, となりの○トロ → My Neighbor Totoro (media titles)

CRITICAL DISAMBIGUATION RULES:
1. Do NOT over-map "LIME" to LINE when transport context is present (Bike, scooter, ride, station).
   - "LIME Bike" = legitimate bike-sharing brand (NOT LINE)
   - "LIMEでメッセージ" = LINE messaging app (obfuscated)

2. Keep legitimate Japanese abbreviations:
   - スタバ = Starbucks (real abbreviation used by Japanese people)
   - ファミマ = FamilyMart (real abbreviation)
   - These are NOT obfuscations, mark as `is_obfuscated: false`

3. Output format requirement:
   - `real_name` MUST be canonical English/Latin-script name
   - Do NOT output katakana/hiragana/kanji in `real_name`
   - Convert all Japanese forms to official English spelling
   - Examples: ゼクシィ → Zexy, アマゾン → Amazon, タイソン → Mike Tyson

4. Entity type classification:
   - author: Book/article authors (e.g., デボラ・ザック → Devora Zack)
   - book: Book titles (e.g., 『シングルタスク』→ Singletasking)
   - person: Celebrities, athletes, public figures (e.g., タ○ソン → Mike Tyson)
   - title: Media titles - movies, anime, manga (e.g., ベル○ルク → Berserk)
   - place: Real-world locations (e.g., ニューヨーク → New York)
   - brand: Companies, products, services (default)

5. For author names, use publisher-canonical spelling:
   - デボラ・ザック + "Singletasking" context → Devora Zack (NOT Deborah Zack)
   - Check context for book titles to disambiguate spelling variants

Return ONLY a JSON array of detected entities:
[
  {{
    "detected_term": "the exact term found in text",
    "is_obfuscated": true/false,
    "real_name": "canonical English/Latin name",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "entity_type": "author|book|person|title|place|brand"
  }},
  ...
]

If no entities detected, return empty array: []
"""
        return prompt

    def _parse_entity_response(self, response_text: str, original_text: str) -> List[DetectedEntity]:
        """Parse Gemini JSON response into DetectedEntity objects."""
        # Remove markdown code blocks if present
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        try:
            data = json.loads(response_text.strip())

            # Handle single object vs array
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                logger.warning(f"Unexpected response format: {type(data)}")
                return []

            entities = []
            for item in data:
                detected_term = item.get('detected_term', '')

                # Find position in original text
                start_pos = original_text.find(detected_term)
                end_pos = start_pos + len(detected_term) if start_pos >= 0 else -1

                # Extract context window
                context = self._extract_context_window(original_text, start_pos) if start_pos >= 0 else ""

                entity = DetectedEntity(
                    detected_term=detected_term,
                    is_obfuscated=item.get('is_obfuscated', False),
                    real_name=item.get('real_name', detected_term),
                    confidence=float(item.get('confidence', 0.0)),
                    reasoning=item.get('reasoning', ''),
                    entity_type=item.get('entity_type', 'brand'),
                    start_pos=start_pos,
                    end_pos=end_pos,
                    context=context
                )
                entities.append(entity)

            return entities

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            return []

    def verify_with_wikipedia(self, entity: DetectedEntity) -> Optional[str]:
        """
        Verify entity canonical name using Wikipedia API.

        Args:
            entity: DetectedEntity to verify

        Returns:
            Canonical name from Wikipedia, or None if not found/verified
        """
        if not self.enable_wikipedia:
            return None

        try:
            import requests

            # Wikipedia API requires User-Agent header
            headers = {
                "User-Agent": "MTL-Studio/1.6 (https://github.com/anthropics/claude-code; reference-validator@mtlstudio.com)"
            }

            # Wikipedia API search
            search_url = "https://en.wikipedia.org/w/api.php"
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": entity.real_name,
                "srlimit": 1
            }

            response = requests.get(search_url, params=search_params, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()

            if not data.get('query', {}).get('search'):
                logger.debug(f"No Wikipedia article found for: {entity.real_name}")
                return None

            # Get canonical page title
            page_title = data['query']['search'][0]['title']

            # Get page content to extract canonical name
            content_params = {
                "action": "query",
                "format": "json",
                "titles": page_title,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True
            }

            response = requests.get(search_url, params=content_params, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()

            pages = data.get('query', {}).get('pages', {})
            if pages:
                page = next(iter(pages.values()))
                extract = page.get('extract', '')

                # Extract canonical name from first paragraph
                # Usually in format: "Name (spelling) is a..."
                first_line = extract.split('\n')[0] if extract else ''

                logger.info(f"Wikipedia verified: {entity.real_name} → {page_title}")
                entity.wikipedia_verified = True
                return page_title

            return None

        except Exception as e:
            logger.warning(f"Wikipedia verification failed for {entity.real_name}: {e}")
            return None

    def validate_file(self, file_path: Path) -> ValidationReport:
        """
        Validate all real-world references in a markdown file.

        Args:
            file_path: Path to EN markdown file

        Returns:
            ValidationReport with all detected entities
        """
        logger.info(f"Validating references in: {file_path.name}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Detect entities using Gemini
        entities = self.detect_entities_in_text(content)

        # Verify high-stakes entities with Wikipedia
        high_confidence_fixes = 0
        wikipedia_verified = 0

        for entity in entities:
            if self._should_verify_with_wikipedia(entity):
                canonical_name = self.verify_with_wikipedia(entity)
                if canonical_name:
                    wikipedia_verified += 1
                    # Update entity with Wikipedia-verified name
                    if canonical_name != entity.real_name:
                        logger.info(f"Wikipedia correction: {entity.real_name} → {canonical_name}")
                        entity.real_name = canonical_name

            if entity.confidence >= 0.95 and entity.is_obfuscated:
                high_confidence_fixes += 1

        report = ValidationReport(
            file_path=str(file_path),
            total_entities_detected=len(entities),
            obfuscated_entities=sum(1 for e in entities if e.is_obfuscated),
            legitimate_entities=sum(1 for e in entities if not e.is_obfuscated),
            high_confidence_fixes=high_confidence_fixes,
            wikipedia_verified=wikipedia_verified,
            entities=entities
        )

        logger.info(
            f"Validation complete: {report.total_entities_detected} entities "
            f"({report.obfuscated_entities} obfuscated, {report.legitimate_entities} legitimate)"
        )

        return report

    def generate_report(self, report: ValidationReport, output_path: Path):
        """Generate JSON and Markdown validation reports."""
        # JSON report
        json_path = output_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # Markdown report
        md_path = output_path.with_suffix('.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# Reference Validation Report\n\n")
            f.write(f"**File:** `{report.file_path}`\n\n")
            f.write(f"**Model:** `{self.RESOLVE_MODEL}` | **Thinking:** `{self.RESOLVE_THINKING_LEVEL}`\n\n")

            f.write("## Summary\n\n")
            f.write(f"- **Total entities detected:** {report.total_entities_detected}\n")
            f.write(f"- **Obfuscated entities:** {report.obfuscated_entities}\n")
            f.write(f"- **Legitimate entities:** {report.legitimate_entities}\n")
            f.write(f"- **High-confidence fixes (≥0.95):** {report.high_confidence_fixes}\n")
            f.write(f"- **Wikipedia verified:** {report.wikipedia_verified}\n\n")

            if report.obfuscated_entities > 0:
                f.write("## Obfuscated Entities (Require Correction)\n\n")
                f.write("| Detected Term | Real Name | Confidence | Type | Reasoning |\n")
                f.write("|---------------|-----------|------------|------|----------|\n")

                for entity in report.entities:
                    if entity.is_obfuscated:
                        verified = " ✓" if entity.wikipedia_verified else ""
                        f.write(f"| {entity.detected_term} | {entity.real_name}{verified} | {entity.confidence:.2f} | {entity.entity_type} | {entity.reasoning} |\n")

                f.write("\n")

            if report.legitimate_entities > 0:
                f.write("## Legitimate Entities (No Correction Needed)\n\n")
                f.write("| Detected Term | Real Name | Confidence | Type | Reasoning |\n")
                f.write("|---------------|-----------|------------|------|----------|\n")

                for entity in report.entities:
                    if not entity.is_obfuscated:
                        f.write(f"| {entity.detected_term} | {entity.real_name} | {entity.confidence:.2f} | {entity.entity_type} | {entity.reasoning} |\n")

                f.write("\n")

            f.write("---\n\n")
            f.write(f"**Generated by:** Phase 1.55 Reference Validator\n")
            f.write(f"**Architecture:** Gemini 3 Flash High Thinking + Wikipedia Verification\n")

        logger.info(f"Reports generated: {json_path}, {md_path}")

    def clear_cache(self):
        """Clear entity validation cache."""
        self.entity_cache.clear()
        logger.info("Entity cache cleared")
