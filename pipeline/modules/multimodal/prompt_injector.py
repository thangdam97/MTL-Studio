"""
Prompt Injector for Multimodal Translation.

Builds visual context blocks that get injected into the translation prompt,
allowing Gemini 2.5 Pro to translate with awareness of illustration context
even without seeing the images directly.

This is the "Context Handoff" mechanism: Gemini 3 Pro's visual analysis
becomes Gemini 2.5 Pro's "Art Director's Notes".

Canon Name Enforcement:
- CanonNameEnforcer is instantiated locally (no global state)
- build_chapter_visual_guidance(manifest=...) creates enforcer on demand
- Canon names from manifest.json character_profiles are applied to visual context
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class CanonNameEnforcer:
    """
    Enforces canonical character names from manifest.json.
    
    Ensures the Multimodal Processor uses consistent names that match
    the Librarian's ruby text extraction.
    """
    
    def __init__(self, manifest: Optional[Dict[str, Any]] = None):
        self.manifest = manifest or {}
        self.canon_map: Dict[str, str] = {}  # Japanese → English
        self.nickname_map: Dict[str, str] = {}  # Japanese → Nickname
        self.visual_identity_map: Dict[str, Dict[str, Any]] = {}  # Japanese → non-color visual identity
        self._load_canon_names()

    @staticmethod
    def _first_nickname(nickname: str) -> str:
        """Return first nickname token from a comma-separated nickname field."""
        if not isinstance(nickname, str):
            return ""
        primary = nickname.split(",", 1)[0].strip()
        return primary

    @staticmethod
    def _extract_relation_label(
        japanese_name: str,
        relationship_to_protagonist: str,
    ) -> str:
        """
        Infer familial relation label from JP key and/or relationship text.

        Returns values like "Mother", "Father", "Older Sister", etc.
        """
        jp = japanese_name or ""
        rel = relationship_to_protagonist or ""
        rel_l = rel.lower()

        suffix_map = [
            ("母親", "Mother"),
            ("父親", "Father"),
            ("祖母", "Grandmother"),
            ("祖父", "Grandfather"),
            ("姉", "Older Sister"),
            ("兄", "Older Brother"),
            ("妹", "Younger Sister"),
            ("弟", "Younger Brother"),
            ("先生", "Teacher"),
        ]
        for suffix, label in suffix_map:
            if jp.endswith(f"の{suffix}") or jp.endswith(suffix):
                return label

        text_map = [
            ("mother", "Mother"),
            ("father", "Father"),
            ("grandmother", "Grandmother"),
            ("grandfather", "Grandfather"),
            ("older sister", "Older Sister"),
            ("older brother", "Older Brother"),
            ("younger sister", "Younger Sister"),
            ("younger brother", "Younger Brother"),
            ("sister", "Sister"),
            ("brother", "Brother"),
            ("teacher", "Teacher"),
        ]
        for token, label in text_map:
            if token in rel_l:
                return label
        return ""

    @classmethod
    def build_canonical_label(
        cls,
        japanese_name: str,
        profile: Dict[str, Any],
    ) -> str:
        """
        Build a stable canonical label for prompt/cache use.

        Improves ambiguous one-token names for relation roles, e.g.:
        - "玉置の母親" + "Tamaki" + "Ako's mother" -> "Ako's Mother"
        """
        if not isinstance(profile, dict):
            return ""

        full_name = str(profile.get("full_name", "")).strip()
        nickname = cls._first_nickname(str(profile.get("nickname", "")))
        rel_to_protag = str(profile.get("relationship_to_protagonist", "")).strip()

        relation_label = cls._extract_relation_label(japanese_name, rel_to_protag)
        if relation_label:
            # Preferred: explicit "<Name>'s <Relation>" from relationship text.
            # Example: "Ako's mother" -> "Ako's Mother"
            rel_match = re.search(
                r"([A-Za-z][A-Za-z -]{0,40})'s\s+(mother|father|sister|brother|grandmother|grandfather|teacher)",
                rel_to_protag,
                flags=re.IGNORECASE,
            )
            if rel_match:
                owner = rel_match.group(1).strip()
                return f"{owner}'s {relation_label}"

            if full_name:
                suffix = "'" if full_name.endswith("s") else "'s"
                return f"{full_name}{suffix} {relation_label}"
            if nickname:
                suffix = "'" if nickname.endswith("s") else "'s"
                return f"{nickname}{suffix} {relation_label}"
            return relation_label

        if full_name:
            return full_name
        return nickname
    
    def _load_canon_names(self) -> None:
        """Load canon names from manifest character_profiles."""
        metadata_en = self.manifest.get("metadata_en", {})
        if not isinstance(metadata_en, dict):
            metadata_en = {}
        profiles = metadata_en.get("character_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        
        for kanji_name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            full_name = self.build_canonical_label(kanji_name, profile)
            nickname = profile.get("nickname", "")
            
            if full_name:
                self.canon_map[kanji_name] = full_name
            if nickname:
                self.nickname_map[kanji_name] = nickname
            visual_identity = self._normalize_visual_identity(
                profile.get("visual_identity_non_color"),
                profile.get("appearance", "")
            )
            if visual_identity:
                self.visual_identity_map[kanji_name] = visual_identity
        
        if self.canon_map:
            logger.debug(f"[CANON] Loaded {len(self.canon_map)} character names")

    @staticmethod
    def _normalize_visual_identity(identity: Any, appearance: str = "") -> Dict[str, Any]:
        """Normalize visual identity payload to a stable non-color dict shape."""
        if isinstance(identity, str) and identity.strip():
            return {"identity_summary": identity.strip()}
        if isinstance(identity, list):
            markers = [str(v).strip() for v in identity if str(v).strip()]
            if markers:
                return {"non_color_markers": markers[:8]}
        if isinstance(identity, dict):
            cleaned: Dict[str, Any] = {}
            for key in (
                "hairstyle",
                "clothing_signature",
                "expression_signature",
                "posture_signature",
                "accessory_signature",
                "identity_summary",
                "body_silhouette",
                "non_color_markers",
            ):
                value = identity.get(key)
                if isinstance(value, str) and value.strip():
                    cleaned[key] = value.strip()
                elif isinstance(value, list):
                    values = [str(v).strip() for v in value if str(v).strip()]
                    if values:
                        cleaned[key] = values[:8]
            if cleaned:
                return cleaned
        if isinstance(appearance, str) and appearance.strip():
            return {"identity_summary": appearance.strip()}
        return {}

    @staticmethod
    def _format_visual_identity_short(identity: Dict[str, Any]) -> str:
        """Format non-color identity to one compact line for prompts."""
        if not identity:
            return ""
        mapping = [
            ("hair", "hairstyle"),
            ("outfit", "clothing_signature"),
            ("expr", "expression_signature"),
            ("pose", "posture_signature"),
            ("acc", "accessory_signature"),
            ("id", "identity_summary"),
        ]
        chunks: List[str] = []
        for label, key in mapping:
            value = identity.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(f"{label}:{value.strip()}")
            elif isinstance(value, list):
                items = [str(v).strip() for v in value if str(v).strip()]
                if items:
                    chunks.append(f"{label}:{', '.join(items[:3])}")
        if not chunks:
            markers = identity.get("non_color_markers", [])
            if isinstance(markers, list):
                items = [str(v).strip() for v in markers if str(v).strip()]
                if items:
                    chunks.append("markers:" + ", ".join(items[:4]))
        return " | ".join(chunks)[:220]
    
    def enforce_in_text(self, text: str) -> str:
        """Replace any Japanese character names with their English canon names."""
        result = text
        for jp_name, en_name in self.canon_map.items():
            result = result.replace(jp_name, en_name)
        return result
    
    def enforce_in_visual_context(self, visual_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively enforce canon names in visual context dict.
        
        This ensures Art Director's Notes use consistent character names.
        """
        if not self.canon_map:
            return visual_context
        
        def process_value(value: Any) -> Any:
            if isinstance(value, str):
                return self.enforce_in_text(value)
            elif isinstance(value, dict):
                return {k: process_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [process_value(item) for item in value]
            return value
        
        return process_value(visual_context)
    
    def get_character_reference(self) -> str:
        """Build a character name reference block for prompt injection."""
        if not self.canon_map:
            return ""
        
        lines = ["=== CHARACTER NAME REFERENCE (Canon from Ruby Text) ==="]
        for jp_name, en_name in self.canon_map.items():
            nickname = self.nickname_map.get(jp_name, "")
            visual_identity = self.visual_identity_map.get(jp_name, {})
            visual_hint = self._format_visual_identity_short(visual_identity)
            if nickname and nickname != en_name:
                lines.append(f"  {jp_name} → {en_name} (nickname: {nickname})")
            else:
                lines.append(f"  {jp_name} → {en_name}")
            if visual_hint:
                lines.append(f"    non-color-id: {visual_hint}")
        lines.append("Use these canonical names consistently in all translations.")
        lines.append("=== END CHARACTER REFERENCE ===\n")
        
        return "\n".join(lines)


def build_multimodal_identity_lock(
    manifest: Optional[Dict[str, Any]],
    max_characters: int = 24,
    bible_characters: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build identity lock block for multimodal analysis prompts.

    Includes canonical real names and non-color visual markers to reduce
    identity guessing in scene analysis.
    """
    if not manifest:
        return ""

    enforcer = CanonNameEnforcer(manifest)
    identity_records: Dict[str, Dict[str, Any]] = {}

    for jp_name, en_name in enforcer.canon_map.items():
        identity_records[jp_name] = {
            "canonical_name": en_name,
            "nickname": enforcer.nickname_map.get(jp_name, ""),
            "visual_identity": enforcer.visual_identity_map.get(jp_name, {}),
        }

    if isinstance(bible_characters, dict):
        for jp_name, char_data in bible_characters.items():
            if not isinstance(char_data, dict):
                continue
            canonical_name = str(char_data.get("canonical_en", "")).strip()
            if not canonical_name:
                continue
            existing = identity_records.get(jp_name, {})
            if not existing:
                identity_records[jp_name] = {
                    "canonical_name": canonical_name,
                    "nickname": str(char_data.get("short_name", "")).strip(),
                    "visual_identity": CanonNameEnforcer._normalize_visual_identity(
                        char_data.get("visual_identity_non_color"), ""
                    ),
                }
            else:
                if not existing.get("nickname"):
                    existing["nickname"] = str(char_data.get("short_name", "")).strip()
                if not existing.get("visual_identity"):
                    existing["visual_identity"] = CanonNameEnforcer._normalize_visual_identity(
                        char_data.get("visual_identity_non_color"), ""
                    )

    if not identity_records:
        return ""

    lines = [
        "=== CHARACTER IDENTITY LOCK (NON-COLOR) ===",
        "Use this registry before any scene analysis.",
        "If a visible character matches markers below, use canonical_en immediately.",
        "Do NOT guess alternate names when a canonical match exists.",
    ]

    for i, (jp_name, record) in enumerate(identity_records.items()):
        if i >= max_characters:
            lines.append(f"... ({len(identity_records) - max_characters} more omitted)")
            break
        en_name = str(record.get("canonical_name", "")).strip()
        if not en_name:
            continue
        nickname = str(record.get("nickname", "")).strip()
        display = f"{en_name} [{jp_name}]"
        if nickname and nickname != en_name:
            display += f" / nickname={nickname}"
        lines.append(f"- {display}")
        visual_identity = record.get("visual_identity", {})
        visual_hint = CanonNameEnforcer._format_visual_identity_short(visual_identity)
        if visual_hint:
            lines.append(f"  non-color-id: {visual_hint}")

    lines.extend([
        "If uncertain, mark as unresolved_character and continue scene analysis.",
        "=== END IDENTITY LOCK ===",
    ])
    return "\n".join(lines)


# Removed: Global _canon_enforcer state (hygiene pass)
# Canon enforcement is now handled via explicit parameter passing:
#   - build_chapter_visual_guidance(manifest=...) creates a local enforcer
#   - cache_manager passes manifest to prompt_injector directly


# Strict output requirement to prevent analysis leaks
MULTIMODAL_STRICT_SUFFIX = """

CRITICAL OUTPUT REQUIREMENT:
Your response MUST be ONLY the translated text.
DO NOT output any analysis, planning, thinking process, or commentary.
DO NOT describe what you're going to do or what you observed.
DO NOT explain your translation choices.
ONLY output the final translated text, maintaining all formatting
including all illustration markers (e.g. [ILLUSTRATION: xxx] or ![illustration](xxx)) in their original positions.
Begin your response with the translated text immediately.
"""

# Canon Event Fidelity constraint for visual context integration
CANON_EVENT_FIDELITY_DIRECTIVE = """
=== CANON EVENT FIDELITY (ABSOLUTE PRIORITY) ===

The Art Director's Notes above provide STYLISTIC guidance only (vocabulary, atmosphere, emotional tone).

**STRICT 1:1 CANON EVENT RULES:**
1. NEVER add events, actions, or dialogue that appear in illustrations but NOT in the source text
2. NEVER alter the sequence or timing of events based on what illustrations show
3. NEVER describe visual details that the source text does not describe
4. If an illustration shows a character crying but the text only mentions they "looked sad", translate as "looked sad"
5. If an illustration shows physical contact but the text only implies it, maintain the implication
6. The illustration INFORMS your vocabulary choice, NOT your content invention

**WHAT TO USE FROM ART DIRECTOR'S NOTES:**
✓ Emotional tone vocabulary ("cold", "distant", "frozen" vs generic "sad")
✓ Atmosphere descriptors matching visual mood
✓ Character expression adjectives that fit the scene
✗ Adding unwritten actions visible in the illustration
✗ Describing unmentioned clothing/accessories details
✗ Revealing plot points the text hasn't confirmed

**SPOILER PREVENTION:**
The "do_not_reveal_before_text" list contains visual spoilers.
Even if you SEE it in the Art Director's Notes, DO NOT translate it until the SOURCE TEXT confirms it.

=== END CANON EVENT FIDELITY ===
"""


def build_visual_context_block(
    illustration_id: str,
    visual_context: Dict[str, Any],
    spoiler_prevention: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build a visual context block for injection into the translation prompt.

    This formats the cached Gemini 3 Pro analysis as "Art Director's Notes"
    that guide Gemini 2.5 Pro's prose decisions.

    Args:
        illustration_id: ID of the illustration (e.g., 'illust-001').
        visual_context: The visual_ground_truth dict from cache.
        spoiler_prevention: Optional spoiler prevention rules.

    Returns:
        Formatted string block for prompt injection.
    """
    if not visual_context:
        return ""

    composition = visual_context.get("composition", "N/A")
    emotional_delta = visual_context.get("emotional_delta", "N/A")
    key_details = visual_context.get("key_details", {})
    directives = visual_context.get("narrative_directives") or []

    lines = [
        f"--- ART DIRECTOR'S NOTES [{illustration_id}] ---",
        f"Scene Composition: {composition}",
        f"Emotional Context: {emotional_delta}",
    ]

    if key_details:
        lines.append("Key Visual Details:")
        for key, value in key_details.items():
            lines.append(f"  - {key}: {value}")

    if directives:
        lines.append("Translation Directives:")
        for d in directives:
            lines.append(f"  - {d}")

    if spoiler_prevention:
        do_not_reveal = spoiler_prevention.get("do_not_reveal_before_text", [])
        if do_not_reveal:
            lines.append(f"SPOILER PREVENTION: Do not mention: {', '.join(do_not_reveal)}")

    lines.append("--- END ART DIRECTOR'S NOTES ---")

    return "\n".join(lines)


def build_lookahead_block(
    illustration_id: str,
    visual_context: Dict[str, Any]
) -> str:
    """
    Build a lighter visual context block for upcoming illustrations.

    Used for segments that appear BEFORE an illustration to allow
    emotional momentum buildup without spoiling the visual.

    Args:
        illustration_id: ID of the upcoming illustration.
        visual_context: The visual_ground_truth dict from cache.

    Returns:
        Formatted string block for prompt injection (lighter than full).
    """
    if not visual_context:
        return ""

    composition = visual_context.get("composition", "N/A")
    emotional_delta = visual_context.get("emotional_delta", "N/A")

    return (
        f"--- UPCOMING VISUAL CONTEXT [{illustration_id}] ---\n"
        f"Composition: {composition}\n"
        f"Emotional Tone: {emotional_delta}\n"
        f"Build emotional momentum toward this visual. Set the tone without spoiling.\n"
        f"--- END UPCOMING CONTEXT ---"
    )


def build_chapter_visual_guidance(
    illustration_ids: List[str],
    cache_manager: Any,
    enable_lookahead: bool = True,
    manifest: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build aggregated visual guidance for an entire chapter.

    Collects all visual context blocks for illustrations found in the chapter
    and returns a single formatted string for prompt injection.
    
    Now integrates with Librarian's ruby extraction to enforce canon names.

    Args:
        illustration_ids: List of illustration IDs found in the chapter.
        cache_manager: VisualCacheManager instance with loaded cache.
        enable_lookahead: Whether to include lookahead context.
        manifest: Optional manifest dict for canon name enforcement.

    Returns:
        Combined visual guidance string, or empty string if no context.
    """
    if not illustration_ids:
        return ""

    # Initialize canon enforcer if manifest provided
    enforcer = None
    if manifest:
        enforcer = CanonNameEnforcer(manifest)

    blocks = []
    found_count = 0

    for illust_id in illustration_ids:
        visual_ctx = cache_manager.get_visual_context(illust_id)
        spoiler = cache_manager.get_spoiler_prevention(illust_id)

        if visual_ctx:
            # Enforce canon names in visual context
            if enforcer:
                visual_ctx = enforcer.enforce_in_visual_context(visual_ctx)
                if spoiler:
                    spoiler = enforcer.enforce_in_visual_context(spoiler)
            
            block = build_visual_context_block(illust_id, visual_ctx, spoiler)
            blocks.append(block)
            found_count += 1
        else:
            logger.debug(f"[MULTIMODAL] No cached context for {illust_id}")

    if not blocks:
        return ""

    # Build header with Canon Event Fidelity directive and optional character reference
    header_lines = [
        CANON_EVENT_FIDELITY_DIRECTIVE,  # Add fidelity rules FIRST
        f"\n=== VISUAL CONTEXT (Pre-Analyzed by Art Director) ===",
        f"Illustrations with cached analysis: {found_count}/{len(illustration_ids)}",
        f"Apply these insights to enhance prose quality for illustrated scenes.",
        f"REMINDER: Art Director's Notes are STYLISTIC guides only. Do NOT add events from illustrations.",
    ]
    
    # Add character reference if available
    if enforcer and enforcer.canon_map:
        header_lines.append("")
        header_lines.append(enforcer.get_character_reference())
    
    header = "\n".join(header_lines) + "\n\n"

    return header + "\n\n".join(blocks) + "\n=== END VISUAL CONTEXT ===\n"


def build_visual_thinking_log(
    illustration_ids: List[str],
    volume_path: Path,
) -> str:
    """
    Build a visual thinking log section for THINKING markdown files.
    
    Retrieves the Gemini 3 Pro thought summaries from cache/thoughts/*.json
    and formats them for inclusion in translation THINKING logs.
    
    Args:
        illustration_ids: List of illustration IDs processed in the chapter.
        volume_path: Path to the volume directory.
        
    Returns:
        Formatted markdown section with Gemini 3 Pro visual reasoning.
    """
    from modules.multimodal.thought_logger import ThoughtLogger
    
    if not illustration_ids:
        return ""
    
    thought_logger = ThoughtLogger(volume_path)
    sections = []
    
    for illust_id in illustration_ids:
        log_entry = thought_logger.get_log(illust_id)
        
        if log_entry and log_entry.thoughts:
            section_lines = [
                f"### 🖼️ {illust_id}",
                f"**Model**: {log_entry.model}",
                f"**Thinking Level**: {log_entry.thinking_level}",
                f"**Processing Time**: {log_entry.processing_time_seconds:.1f}s",
                "",
            ]
            
            for i, thought in enumerate(log_entry.thoughts):
                if i > 0:
                    section_lines.append("")
                section_lines.append("**Gemini 3 Pro Visual Reasoning:**")
                section_lines.append("```")
                # Truncate very long thoughts for readability
                if len(thought) > 3000:
                    section_lines.append(thought[:3000] + "...")
                else:
                    section_lines.append(thought)
                section_lines.append("```")
            
            sections.append("\n".join(section_lines))
    
    if not sections:
        return ""
    
    header = [
        "## 🧠 Gemini 3 Pro Visual Thinking Log",
        "",
        "The following captures Gemini 3 Pro's internal reasoning during Phase 1.6",
        "visual analysis. These thought summaries reveal how the model interpreted",
        "each illustration before generating Art Director's Notes.",
        "",
    ]
    
    return "\n".join(header) + "\n\n".join(sections)
