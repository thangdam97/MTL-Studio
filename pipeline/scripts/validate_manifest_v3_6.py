#!/usr/bin/env python3
"""
Manifest JSON Validator for MTL Studio v3.6 Enhanced Schema
Validates manifest structure and metadata completeness before translation.
Ensures all required arrays and fields are present for quality translation runs.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any


class ManifestValidator:
    """Validates v3.6 enhanced schema manifests."""
    
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.manifest = None
        self.errors = []
        self.warnings = []
        self.info = []
        
    def load_manifest(self) -> bool:
        """Load and parse manifest JSON."""
        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                self.manifest = json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.errors.append(f"JSON parsing error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Failed to load manifest: {e}")
            return False
    
    def validate_schema_version(self) -> bool:
        """Validate schema version is v3.6_enhanced."""
        schema_version = self.manifest.get("schema_version")
        if not schema_version:
            self.errors.append("Missing 'schema_version' field")
            return False
        
        if schema_version != "v3.6_enhanced":
            self.warnings.append(f"Schema version is '{schema_version}', expected 'v3.6_enhanced'")
            return False
        
        self.info.append(f"✓ Schema version: {schema_version}")
        return True
    
    def validate_metadata_structure(self) -> bool:
        """Validate metadata root structure."""
        if "metadata" not in self.manifest:
            self.errors.append("Missing 'metadata' section")
            return False
        
        metadata = self.manifest["metadata"]
        
        # Check for new v3.6 structure
        has_series = "series" in metadata
        has_publication = "publication" in metadata
        has_content_info = "content_info" in metadata
        
        if has_series and has_publication and has_content_info:
            self.info.append("✓ Metadata structure: v3.6 enhanced format")
            return True
        elif "title" in metadata:  # Old format
            self.warnings.append("Metadata using legacy format, recommend upgrading to v3.6 structure")
            return True
        else:
            self.errors.append("Invalid metadata structure")
            return False
    
    def validate_character_profiles(self) -> bool:
        """Validate character_profiles array completeness."""
        metadata = self.manifest.get("metadata", {})
        profiles = metadata.get("character_profiles", {})
        
        if not profiles:
            self.errors.append("Missing 'character_profiles' - required for v3.6")
            return False
        
        required_fields = [
            "ruby_base", "ruby_reading", "name_en", "first_person_pronoun",
            "speech_pattern", "personality_traits", "keigo_switch"
        ]
        
        profile_count = len(profiles)
        complete_profiles = 0
        
        for char_name, profile in profiles.items():
            missing = [f for f in required_fields if f not in profile]
            if not missing:
                complete_profiles += 1
            else:
                self.warnings.append(f"Character '{char_name}' missing fields: {', '.join(missing)}")
        
        self.info.append(f"✓ Character profiles: {complete_profiles}/{profile_count} complete")
        return profile_count > 0
    
    def validate_pov_tracking(self) -> bool:
        """Validate POV tracking for all chapters."""
        metadata = self.manifest.get("metadata", {})
        pov_tracking = metadata.get("pov_tracking", {})
        
        if not pov_tracking:
            self.errors.append("Missing 'pov_tracking' - required for v3.6")
            return False
        
        chapters = self.manifest.get("chapters", [])
        content_chapters = [c for c in chapters if not c.get("is_pre_toc_content", False)]
        
        tracked_count = len(pov_tracking)
        expected_count = len(content_chapters)
        
        if tracked_count == 0:
            self.errors.append("POV tracking is empty")
            return False
        
        # Validate each POV entry has required fields
        required_pov_fields = ["primary_pov", "pov_shifts", "narrative_style"]
        incomplete = []
        
        for chapter_id, pov_data in pov_tracking.items():
            missing = [f for f in required_pov_fields if f not in pov_data]
            if missing:
                incomplete.append(f"{chapter_id}: {', '.join(missing)}")
        
        if incomplete:
            self.warnings.append(f"Incomplete POV tracking: {'; '.join(incomplete)}")
        
        self.info.append(f"✓ POV tracking: {tracked_count} chapters tracked")
        return True
    
    def validate_translation_guidance(self) -> bool:
        """Validate translation_guidance array and genre modifiers."""
        metadata = self.manifest.get("metadata", {})
        guidance = metadata.get("translation_guidance", {})
        
        if not guidance:
            self.errors.append("Missing 'translation_guidance' - required for v3.6")
            return False
        
        # Check genres array
        genres = guidance.get("genres", [])
        if not genres:
            self.errors.append("Missing 'genres' array in translation_guidance")
            return False
        
        # Check for quality-enhancing genre modifiers
        quality_modifiers = ["wholesome", "jealousy_comedy", "domestic", "tension", "mystery"]
        has_modifiers = any(m in genres for m in quality_modifiers)
        
        if not has_modifiers:
            self.warnings.append(
                "No quality-enhancing genre modifiers found. "
                "Consider adding: wholesome, jealousy_comedy, domestic, etc."
            )
        
        # Check translator_notes
        translator_notes = guidance.get("translator_notes", {})
        if not translator_notes:
            self.warnings.append("Missing 'translator_notes' in translation_guidance")
        else:
            required_note_fields = ["priority_patterns", "tone", "character_voice_priorities", "avoid"]
            missing_notes = [f for f in required_note_fields if f not in translator_notes]
            if missing_notes:
                self.warnings.append(f"translator_notes missing: {', '.join(missing_notes)}")
        
        self.info.append(f"✓ Translation guidance: {len(genres)} genres defined")
        if has_modifiers:
            present = [m for m in quality_modifiers if m in genres]
            self.info.append(f"  Genre modifiers: {', '.join(present)}")
        
        return True
    
    def validate_content_info(self) -> bool:
        """Validate content_info metadata."""
        metadata = self.manifest.get("metadata", {})
        content_info = metadata.get("content_info", {})
        
        if not content_info:
            self.warnings.append("Missing 'content_info' section")
            return False
        
        # Check basic fields
        has_genre = "genre" in content_info and content_info["genre"]
        has_tags = "tags" in content_info and content_info["tags"]
        has_synopsis = "synopsis_en" in content_info
        
        if not has_genre:
            self.warnings.append("Missing 'genre' array in content_info")
        if not has_tags:
            self.warnings.append("Missing 'tags' array in content_info")
        if not has_synopsis:
            self.warnings.append("Missing 'synopsis_en' in content_info")
        
        if has_genre:
            genre_count = len(content_info["genre"])
            self.info.append(f"✓ Content genres: {genre_count} defined")
        if has_tags:
            tag_count = len(content_info["tags"])
            self.info.append(f"✓ Content tags: {tag_count} defined")
        
        return has_genre or has_tags
    
    def validate_chapters(self) -> bool:
        """Validate chapters array completeness."""
        chapters = self.manifest.get("chapters", [])
        
        if not chapters:
            self.errors.append("Missing 'chapters' array")
            return False
        
        required_chapter_fields = [
            "id", "title", "title_en", "toc_order", "toc_level",
            "illustrations", "translation_status", "is_pre_toc_content"
        ]
        
        # Separate cover/kuchie from content chapters
        pre_toc = [c for c in chapters if c.get("is_pre_toc_content", False)]
        content = [c for c in chapters if not c.get("is_pre_toc_content", False)]
        
        # Check for cover and kuchie
        has_cover = any(c.get("id") == "cover" for c in pre_toc)
        has_kuchie = any(c.get("id") == "kuchie" for c in pre_toc)
        
        if not has_cover:
            self.warnings.append("No 'cover' entry found (recommended)")
        if not has_kuchie:
            self.warnings.append("No 'kuchie' entry found (recommended for illustrated volumes)")
        
        # Validate content chapters
        incomplete_chapters = []
        for chapter in content:
            missing = [f for f in required_chapter_fields if f not in chapter]
            if missing:
                chapter_id = chapter.get("id", "unknown")
                incomplete_chapters.append(f"{chapter_id}: {', '.join(missing)}")
        
        if incomplete_chapters:
            self.warnings.append(f"Incomplete chapters: {'; '.join(incomplete_chapters)}")
        
        self.info.append(f"✓ Chapters: {len(content)} content + {len(pre_toc)} pre-TOC")
        return len(content) > 0
    
    def validate_localization_notes(self) -> bool:
        """Validate localization_notes completeness."""
        metadata = self.manifest.get("metadata", {})
        loc_notes = metadata.get("localization_notes", {})
        
        if not loc_notes:
            self.warnings.append("Missing 'localization_notes' (recommended for v3.6)")
            return False
        
        recommended_fields = [
            "cultural_adaptations", "naming_conventions",
            "key_phrases", "scene_markers"
        ]
        
        present = [f for f in recommended_fields if f in loc_notes and loc_notes[f]]
        if len(present) < 2:
            self.warnings.append(
                f"localization_notes incomplete - has {len(present)}/4 recommended sections"
            )
        
        self.info.append(f"✓ Localization notes: {len(present)}/4 sections defined")
        return True
    
    def validate_sequel_continuity(self) -> bool:
        """Validate sequel_continuity for volume series."""
        metadata = self.manifest.get("metadata", {})
        sequel = metadata.get("sequel_continuity", {})
        
        # Check if this is a sequel (volume > 1)
        series = metadata.get("series", {})
        volume_number = series.get("volume_number", 1)
        
        if volume_number > 1 and not sequel:
            self.warnings.append(
                f"Volume {volume_number} should have 'sequel_continuity' section "
                "for character/relationship consistency"
            )
            return False
        
        if sequel:
            required_fields = [
                "previous_volume", "established_relationships",
                "character_development_carryover", "voice_consistency_critical"
            ]
            missing = [f for f in required_fields if f not in sequel]
            if missing:
                self.warnings.append(f"sequel_continuity missing: {', '.join(missing)}")
            
            self.info.append(f"✓ Sequel continuity defined for Volume {volume_number}")
        
        return True
    
    def validate_illustration_references(self) -> bool:
        """Validate illustration and kuchie file references with detailed tracking."""
        chapters = self.manifest.get("chapters", [])
        base_path = self.manifest_path.parent
        metadata = self.manifest.get("metadata", {})
        content_info = metadata.get("content_info", {})
        
        # Separate tracking for different illustration types
        cover_files = []
        kuchie_files = []
        illustration_files = []
        missing_files = []
        duplicate_usage = {}
        
        # Track appearances
        for chapter in chapters:
            chapter_id = chapter.get("id", "unknown")
            illustrations = chapter.get("illustrations", [])
            is_pre_toc = chapter.get("is_pre_toc_content", False)
            
            for illust in illustrations:
                # Categorize by type
                if chapter_id == "cover" or "cover" in illust.lower():
                    cover_files.append(illust)
                elif chapter_id == "kuchie" or "kuchie" in illust.lower():
                    kuchie_files.append(illust)
                else:
                    illustration_files.append(illust)
                
                # Track duplicates
                if illust not in duplicate_usage:
                    duplicate_usage[illust] = []
                duplicate_usage[illust].append(chapter_id)
                
                # Check file existence in multiple possible locations
                possible_paths = [
                    base_path / "assets" / "illustrations" / illust,
                    base_path / "assets" / "kuchie" / illust,
                    base_path / "assets" / illust,
                    base_path / illust,
                    base_path / "_epub_extracted" / "OEBPS" / "Images" / illust,
                ]
                
                if not any(p.exists() for p in possible_paths):
                    missing_files.append(f"{chapter_id}: {illust}")
        
        # Count validation
        total_referenced = len(cover_files) + len(kuchie_files) + len(illustration_files)
        declared_count = content_info.get("illustration_count", 0)
        
        if declared_count != total_referenced:
            self.warnings.append(
                f"Illustration count mismatch: content_info declares {declared_count}, "
                f"but {total_referenced} files referenced in chapters"
            )
        
        # Path validation
        if missing_files:
            self.warnings.append(
                f"Illustration files not found: {', '.join(missing_files[:5])}"
                + (f" (+{len(missing_files)-5} more)" if len(missing_files) > 5 else "")
            )
        
        # Duplicate usage detection (usually valid but worth noting)
        duplicates = {k: v for k, v in duplicate_usage.items() if len(v) > 1}
        if duplicates:
            dup_summary = [f"{illust} ({len(chapters)}x)" for illust, chapters in list(duplicates.items())[:3]]
            self.info.append(f"  Note: {len(duplicates)} illustrations used multiple times: {', '.join(dup_summary)}")
        
        # Naming convention check
        illust_pattern_issues = []
        for illust in illustration_files:
            # Expected patterns: illust-001.jpg, illust-002.jpg, etc.
            if not (illust.startswith("illust-") and illust.endswith((".jpg", ".png"))):
                illust_pattern_issues.append(illust)
        
        kuchie_pattern_issues = []
        for kuchie in kuchie_files:
            # Expected patterns: kuchie-001.jpg, kuchie-002.jpg, etc.
            if not (kuchie.startswith("kuchie-") and kuchie.endswith((".jpg", ".png"))):
                kuchie_pattern_issues.append(kuchie)
        
        if illust_pattern_issues:
            self.warnings.append(
                f"Illustrations with non-standard naming: {', '.join(illust_pattern_issues[:3])}"
                + (f" (+{len(illust_pattern_issues)-3} more)" if len(illust_pattern_issues) > 3 else "")
            )
        if kuchie_pattern_issues:
            self.warnings.append(
                f"Kuchie with non-standard naming: {', '.join(kuchie_pattern_issues[:3])}"
                + (f" (+{len(kuchie_pattern_issues)-3} more)" if len(kuchie_pattern_issues) > 3 else "")
            )
        
        # Summary reporting
        self.info.append(f"✓ Illustrations: {len(illustration_files)} in-chapter illustrations")
        if len(kuchie_files) > 0:
            self.info.append(f"  Kuchie: {len(kuchie_files)} color illustration pages")
        if len(cover_files) > 0:
            self.info.append(f"  Cover: {len(cover_files)} cover image(s)")
        self.info.append(f"  Total referenced: {total_referenced} files")
        
        if declared_count == total_referenced and len(missing_files) == 0:
            self.info.append(f"  ✓ All illustration references validated")
        
        return len(missing_files) == 0 and declared_count == total_referenced
    
    def run_validation(self) -> bool:
        """Run all validation checks."""
        if not self.load_manifest():
            return False
        
        # Critical validations (must pass)
        critical_checks = [
            ("Schema Version", self.validate_schema_version),
            ("Metadata Structure", self.validate_metadata_structure),
            ("Chapters Array", self.validate_chapters),
        ]
        
        # Quality validations (recommended)
        quality_checks = [
            ("Character Profiles", self.validate_character_profiles),
            ("POV Tracking", self.validate_pov_tracking),
            ("Translation Guidance", self.validate_translation_guidance),
            ("Content Info", self.validate_content_info),
            ("Localization Notes", self.validate_localization_notes),
            ("Sequel Continuity", self.validate_sequel_continuity),
            ("Illustration References", self.validate_illustration_references),
        ]
        
        print("=" * 70)
        print("MTL STUDIO v3.6 MANIFEST VALIDATOR")
        print("=" * 70)
        print(f"Validating: {self.manifest_path.name}")
        print()
        
        # Run critical checks
        print("CRITICAL VALIDATIONS:")
        critical_passed = True
        for name, check_func in critical_checks:
            try:
                result = check_func()
                status = "✓ PASS" if result else "✗ FAIL"
                print(f"  {status}: {name}")
                if not result:
                    critical_passed = False
            except Exception as e:
                print(f"  ✗ ERROR: {name} - {e}")
                self.errors.append(f"{name} validation error: {e}")
                critical_passed = False
        
        print()
        
        # Run quality checks
        print("QUALITY VALIDATIONS:")
        quality_passed = 0
        for name, check_func in quality_checks:
            try:
                result = check_func()
                status = "✓ PASS" if result else "⚠ WARN"
                print(f"  {status}: {name}")
                if result:
                    quality_passed += 1
            except Exception as e:
                print(f"  ⚠ WARN: {name} - {e}")
                self.warnings.append(f"{name} validation warning: {e}")
        
        quality_score = (quality_passed / len(quality_checks)) * 100
        
        print()
        print("-" * 70)
        print("VALIDATION SUMMARY:")
        print(f"  Quality Score: {quality_score:.0f}% ({quality_passed}/{len(quality_checks)} checks passed)")
        print()
        
        # Show details
        if self.info:
            print("DETAILS:")
            for msg in self.info:
                print(f"  {msg}")
            print()
        
        if self.warnings:
            print(f"WARNINGS ({len(self.warnings)}):")
            for msg in self.warnings[:10]:  # Show first 10
                print(f"  ⚠ {msg}")
            if len(self.warnings) > 10:
                print(f"  ... and {len(self.warnings) - 10} more warnings")
            print()
        
        if self.errors:
            print(f"ERRORS ({len(self.errors)}):")
            for msg in self.errors:
                print(f"  ✗ {msg}")
            print()
        
        # Final verdict
        print("=" * 70)
        if critical_passed and quality_score >= 80:
            print("VERDICT: ✓ READY FOR TRANSLATION")
            print("Manifest meets v3.6 enhanced schema requirements.")
            return True
        elif critical_passed and quality_score >= 60:
            print("VERDICT: ⚠ ACCEPTABLE (with warnings)")
            print("Manifest passes critical checks but has quality gaps.")
            print("Translation can proceed but quality may be suboptimal.")
            return True
        elif critical_passed:
            print("VERDICT: ⚠ MINIMAL (proceed with caution)")
            print("Manifest passes critical checks but lacks many v3.6 features.")
            print("Translation quality will be limited.")
            return True
        else:
            print("VERDICT: ✗ FAILED")
            print("Manifest has critical errors. Fix errors before translation.")
            return False
    
    def print_report(self):
        """Print detailed validation report."""
        print()
        print("=" * 70)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python validate_manifest_v3_6.py <path_to_manifest.json>")
        sys.exit(1)
    
    manifest_path = Path(sys.argv[1])
    if not manifest_path.exists():
        print(f"Error: Manifest file not found: {manifest_path}")
        sys.exit(1)
    
    validator = ManifestValidator(manifest_path)
    success = validator.run_validation()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
