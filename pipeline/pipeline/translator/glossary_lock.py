"""
Manifest-backed glossary lock for name consistency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class GlossaryIssue:
    variant: str
    expected: str
    similarity: float
    severity: str = "CRITICAL"


@dataclass
class ValidationReport:
    issues: List[GlossaryIssue] = field(default_factory=list)

    def has_critical(self) -> bool:
        return any(issue.severity == "CRITICAL" for issue in self.issues)

    @property
    def critical(self) -> List[GlossaryIssue]:
        return [issue for issue in self.issues if issue.severity == "CRITICAL"]

    def has_any(self) -> bool:
        return bool(self.issues)


class GlossaryLock:
    """
    Enforces manifest-defined romanizations as canonical names.

    The lock is loaded once at translator startup and reused for each chapter.
    """

    _NAME_TOKEN_RE = re.compile(r"\b[A-Z][a-z]+(?:[-'][A-Za-z]+)?\b")
    _STOP_WORDS = {
        "The",
        "This",
        "That",
        "When",
        "Where",
        "Then",
        "After",
        "Before",
        "Chapter",
        "Act",
        "Prologue",
        "Epilogue",
        "Lord",
        "Lady",
        "Sir",
        "King",
        "Queen",
    }

    def __init__(self, work_dir: Path, target_language: str = "en"):
        self.work_dir = work_dir
        self.target_language = target_language.lower()
        self.manifest_path = work_dir / "manifest.json"
        self.locked_names = self._load_from_manifest()
        self._canonical_names = {self._normalize(name): name for name in self.locked_names.values()}
        self._locked = True

    def _load_from_manifest(self) -> Dict[str, str]:
        if not self.manifest_path.exists():
            return {}

        with self.manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        metadata_lang = manifest.get(f"metadata_{self.target_language}", {})
        metadata_en = manifest.get("metadata_en", {})

        # 1) Explicit character_names dict (best source).
        candidates = [
            metadata_lang.get("character_names", {}),
            metadata_en.get("character_names", {}),
            manifest.get("character_names", {}),
        ]

        for mapping in candidates:
            if isinstance(mapping, dict) and mapping:
                extracted = self._extract_name_mapping(mapping)
                if extracted:
                    return extracted

        # 2) Fallback: derive from character_profiles.
        profiles = metadata_lang.get("character_profiles") or metadata_en.get("character_profiles") or {}
        if isinstance(profiles, dict) and profiles:
            derived: Dict[str, str] = {}
            for key, profile in profiles.items():
                if not isinstance(profile, dict):
                    continue
                full_name = profile.get("full_name")
                ruby_reading = profile.get("ruby_reading")
                nickname = profile.get("nickname")
                if isinstance(full_name, str) and full_name.strip():
                    derived[str(key)] = full_name.strip()
                elif isinstance(ruby_reading, str) and ruby_reading.strip():
                    derived[str(key)] = ruby_reading.strip()
                if isinstance(nickname, str) and nickname.strip():
                    derived[f"{key}_nickname"] = nickname.strip()
            return derived

        return {}

    def _extract_name_mapping(self, mapping: Dict[str, object]) -> Dict[str, str]:
        extracted: Dict[str, str] = {}
        for jp_name, value in mapping.items():
            if isinstance(value, str) and value.strip():
                extracted[str(jp_name)] = value.strip()
                continue
            if isinstance(value, dict):
                name_en = value.get("name_en")
                if isinstance(name_en, str) and name_en.strip():
                    extracted[str(jp_name)] = name_en.strip()
        return extracted

    def validate_output(self, text: str) -> ValidationReport:
        if not self.locked_names:
            return ValidationReport()

        issues: List[GlossaryIssue] = []
        seen_pairs: Set[str] = set()

        for token in self._NAME_TOKEN_RE.findall(text):
            if len(token) < 4 or token in self._STOP_WORDS:
                continue

            token_norm = self._normalize(token)
            if token_norm in self._canonical_names:
                continue

            closest_name, score = self._closest_locked_name(token_norm)
            if closest_name and score >= 0.82:
                dedupe_key = f"{token_norm}:{self._normalize(closest_name)}"
                if dedupe_key in seen_pairs:
                    continue
                seen_pairs.add(dedupe_key)
                issues.append(
                    GlossaryIssue(
                        variant=token,
                        expected=closest_name,
                        similarity=score,
                        severity="CRITICAL",
                    )
                )

        return ValidationReport(issues=issues)

    def _closest_locked_name(self, token_norm: str) -> tuple[Optional[str], float]:
        best_name: Optional[str] = None
        best_score = 0.0

        for normalized, canonical in self._canonical_names.items():
            score = SequenceMatcher(None, token_norm, normalized).ratio()
            if score > best_score:
                best_score = score
                best_name = canonical

        return best_name, best_score

    @staticmethod
    def _normalize(name: str) -> str:
        return re.sub(r"[^a-z]", "", name.lower())


    def auto_fix_output(self, text: str) -> tuple[str, int]:
        """Replace detected name variants with canonical forms.

        Returns (fixed_text, replacement_count).
        """
        if not self.locked_names:
            return text, 0

        report = self.validate_output(text)
        if not report.has_any():
            return text, 0

        fixed = text
        total_replacements = 0
        for issue in report.issues:
            # Word-boundary replacement: variant -> expected
            pattern = re.compile(r"\b" + re.escape(issue.variant) + r"\b")
            fixed, count = pattern.subn(issue.expected, fixed)
            total_replacements += count

        return fixed, total_replacements

    def get_locked_names(self) -> Dict[str, str]:
        return dict(self.locked_names)

    def is_locked(self) -> bool:
        return self._locked
