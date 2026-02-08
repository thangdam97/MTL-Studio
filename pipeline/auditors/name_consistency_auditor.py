"""
Cross-chapter name consistency auditor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class NameVariantGroup:
    canonical: str
    variants: Set[str] = field(default_factory=set)
    occurrences: Dict[str, int] = field(default_factory=dict)


@dataclass
class NameConsistencyReport:
    chapter_count: int
    groups: List[NameVariantGroup] = field(default_factory=list)

    def has_variants(self) -> bool:
        return bool(self.groups)


class NameConsistencyAuditor:
    """
    Detects likely romanization drift across EN chapter outputs.
    """

    _NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:[-'][A-Za-z]+)?\b")
    _STOPWORDS = {
        "The",
        "This",
        "That",
        "Then",
        "When",
        "Where",
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

    def audit_volume(
        self,
        en_dir: Path,
        canonical_names: Optional[List[str]] = None,
    ) -> NameConsistencyReport:
        chapters = sorted(en_dir.glob("*.md"))
        occurrences = self._collect_occurrences(chapters)
        if canonical_names:
            groups = self._find_variants_against_canonical(occurrences, canonical_names)
        else:
            groups = self.find_variants(occurrences)
        return NameConsistencyReport(chapter_count=len(chapters), groups=groups)

    def _collect_occurrences(self, chapters: List[Path]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for chapter in chapters:
            text = chapter.read_text(encoding="utf-8")
            for token in self._NAME_RE.findall(text):
                if len(token) < 4 or token in self._STOPWORDS:
                    continue
                counts[token] = counts.get(token, 0) + 1
        return counts

    def find_variants(self, occurrences: Dict[str, int]) -> List[NameVariantGroup]:
        names = sorted(occurrences.keys())
        visited: Set[str] = set()
        groups: List[NameVariantGroup] = []

        for i, base in enumerate(names):
            if occurrences.get(base, 0) < 3:
                continue
            if base in visited:
                continue
            cluster = {base}
            for candidate in names[i + 1:]:
                if candidate in visited:
                    continue
                if occurrences.get(candidate, 0) < 3:
                    continue
                if self._is_variant_pair(base, candidate):
                    cluster.add(candidate)

            if len(cluster) < 2:
                continue

            visited.update(cluster)
            canonical = max(cluster, key=lambda name: occurrences.get(name, 0))
            groups.append(
                NameVariantGroup(
                    canonical=canonical,
                    variants=cluster,
                    occurrences={name: occurrences.get(name, 0) for name in sorted(cluster)},
                )
            )

        return groups

    def _find_variants_against_canonical(
        self,
        occurrences: Dict[str, int],
        canonical_names: List[str],
    ) -> List[NameVariantGroup]:
        canonical_set = {name for name in canonical_names if self._looks_like_name(name)}
        if not canonical_set:
            return []

        groups: Dict[str, NameVariantGroup] = {
            canonical: NameVariantGroup(
                canonical=canonical,
                variants={canonical},
                occurrences={canonical: occurrences.get(canonical, 0)},
            )
            for canonical in canonical_set
        }

        for token, count in occurrences.items():
            if count < 2:
                continue
            if token in canonical_set:
                continue
            if not self._looks_like_name(token):
                continue

            token_norm = self._normalize_name(token)
            if not token_norm:
                continue
            best_canonical = None
            best_distance = 999
            for canonical in canonical_set:
                canonical_norm = self._normalize_name(canonical)
                if not canonical_norm:
                    continue
                if canonical_norm == token_norm:
                    continue
                if canonical_norm[0] != token_norm[0]:
                    continue
                if len(canonical_norm) >= 4 and len(token_norm) >= 4 and canonical_norm[:2] != token_norm[:2]:
                    continue
                distance = self._levenshtein(token_norm, canonical_norm)
                if 1 <= distance <= 2 and distance < best_distance:
                    best_distance = distance
                    best_canonical = canonical

            if best_canonical:
                group = groups[best_canonical]
                group.variants.add(token)
                group.occurrences[token] = count

        return [group for group in groups.values() if len(group.variants) > 1]

    def _is_variant_pair(self, a: str, b: str) -> bool:
        a_norm = self._normalize_name(a)
        b_norm = self._normalize_name(b)
        if not a_norm or not b_norm:
            return False
        if a_norm == b_norm:
            return False
        if a_norm[0] != b_norm[0]:
            return False
        if len(a_norm) >= 4 and len(b_norm) >= 4 and a_norm[:2] != b_norm[:2]:
            return False
        if not self._looks_like_name(a) or not self._looks_like_name(b):
            return False
        distance = self._levenshtein(a_norm, b_norm)
        return 1 <= distance <= 2

    def _looks_like_name(self, token: str) -> bool:
        if len(token) < 4:
            return False
        if token in self._STOPWORDS:
            return False
        return bool(re.fullmatch(r"[A-Z][a-zA-Z'-]+", token))

    def _normalize_name(self, token: str) -> str:
        lowered = token.lower().strip()
        if lowered.endswith("'s"):
            lowered = lowered[:-2]
        return re.sub(r"[^a-z]", "", lowered)

    def _levenshtein(self, a: str, b: str) -> int:
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)

        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            curr = [i]
            for j, cb in enumerate(b, start=1):
                cost = 0 if ca == cb else 1
                curr.append(
                    min(
                        prev[j] + 1,      # deletion
                        curr[j - 1] + 1,  # insertion
                        prev[j - 1] + cost,
                    )
                )
            prev = curr
        return prev[-1]
