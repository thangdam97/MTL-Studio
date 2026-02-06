#!/usr/bin/env python3
"""
Pre-Phase 4 Manifest Schema Validator
=====================================

Validates manifest.json compatibility before EPUB build.
Checks for v3.0 vs v3.5 schema differences and ensures all required
fields are present for the Builder agent.

Usage:
    python scripts/validate_manifest_schema.py <volume_id>
    python scripts/validate_manifest_schema.py 095d
    python scripts/validate_manifest_schema.py --all  # Check all volumes

Author: MTL Studio
Version: 1.0
"""

import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent
WORK_DIR = PIPELINE_DIR / "WORK"


@dataclass
class ValidationResult:
    """Result of a single validation check"""
    check_name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning, info
    fix_suggestion: Optional[str] = None


class ManifestSchemaValidator:
    """
    Validates manifest.json for Phase 4 compatibility.
    
    Detects:
    - Schema version (v3.0 vs v3.5)
    - Required fields for EPUB build
    - Kuchie field consistency (file vs image_path)
    - Chapter array location (root vs structure.chapters)
    - Metadata structure (flat vs nested)
    """
    
    # Required fields for Builder agent
    REQUIRED_ROOT_FIELDS = ['volume_id', 'version', 'metadata', 'assets']
    REQUIRED_METADATA_FIELDS_V30 = ['title', 'author']
    REQUIRED_METADATA_FIELDS_V35 = ['series']  # Nested structure
    REQUIRED_ASSET_FIELDS = ['cover']
    
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.manifest = self._load_manifest()
        self.results: List[ValidationResult] = []
        self.schema_version = "unknown"
    
    def _load_manifest(self) -> Dict[str, Any]:
        """Load manifest.json"""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")
        
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def validate_all(self) -> Tuple[bool, List[ValidationResult]]:
        """Run all validations"""
        self._detect_schema_version()
        self._validate_root_fields()
        self._validate_metadata_structure()
        self._validate_chapters()
        self._validate_kuchie_fields()
        self._validate_pipeline_state()
        self._validate_assets()
        
        # Check for any errors
        has_errors = any(r.severity == "error" and not r.passed for r in self.results)
        
        return not has_errors, self.results
    
    def _add_result(self, check_name: str, passed: bool, message: str, 
                   severity: str = "error", fix_suggestion: str = None):
        """Add a validation result"""
        self.results.append(ValidationResult(
            check_name=check_name,
            passed=passed,
            message=message,
            severity=severity,
            fix_suggestion=fix_suggestion
        ))
    
    def _detect_schema_version(self):
        """Detect manifest schema version (v3.0 vs v3.5)"""
        # v3.5 indicators
        has_structure = 'structure' in self.manifest
        has_nested_series = 'series' in self.manifest.get('metadata', {})
        has_nested_title = isinstance(
            self.manifest.get('metadata', {}).get('series', {}).get('title'), 
            dict
        )
        
        if has_structure and has_nested_series and has_nested_title:
            self.schema_version = "3.5"
            self._add_result(
                "schema_detection",
                True,
                f"Schema v3.5 detected (nested structure)",
                "info"
            )
        elif has_structure or has_nested_series:
            self.schema_version = "3.5-partial"
            self._add_result(
                "schema_detection",
                True,
                f"Schema v3.5 (partial) detected - some fields may use old format",
                "warning"
            )
        else:
            self.schema_version = "3.0"
            self._add_result(
                "schema_detection",
                True,
                f"Schema v3.0 detected (flat structure)",
                "info"
            )
    
    def _validate_root_fields(self):
        """Validate required root-level fields"""
        for field in self.REQUIRED_ROOT_FIELDS:
            if field not in self.manifest:
                self._add_result(
                    f"root_field_{field}",
                    False,
                    f"Missing required field: '{field}'",
                    "error",
                    f"Add '{field}' to manifest root"
                )
            else:
                self._add_result(
                    f"root_field_{field}",
                    True,
                    f"Field '{field}' present",
                    "info"
                )
    
    def _validate_metadata_structure(self):
        """Validate metadata structure based on schema version"""
        metadata = self.manifest.get('metadata', {})
        
        if self.schema_version.startswith("3.5"):
            # v3.5: Check nested structure
            series = metadata.get('series', {})
            if not series:
                self._add_result(
                    "metadata_series",
                    False,
                    "v3.5 schema requires 'metadata.series' object",
                    "error",
                    "Add nested 'series' object with title, author, publisher"
                )
                return
            
            # Check nested title
            title_obj = series.get('title', {})
            if isinstance(title_obj, dict):
                has_title = 'japanese' in title_obj or 'english' in title_obj
                if not has_title:
                    self._add_result(
                        "metadata_title",
                        False,
                        "v3.5 schema requires 'series.title.japanese' or 'series.title.english'",
                        "error"
                    )
                else:
                    self._add_result(
                        "metadata_title",
                        True,
                        f"Title found: {title_obj.get('english') or title_obj.get('japanese')}",
                        "info"
                    )
            else:
                self._add_result(
                    "metadata_title",
                    False,
                    "v3.5 schema requires 'series.title' to be an object with language keys",
                    "error",
                    "Convert title to: {\"japanese\": \"...\", \"english\": \"...\"}"
                )
        else:
            # v3.0: Check flat structure
            if 'title' not in metadata:
                self._add_result(
                    "metadata_title",
                    False,
                    "v3.0 schema requires 'metadata.title'",
                    "error"
                )
            else:
                self._add_result(
                    "metadata_title",
                    True,
                    f"Title found: {metadata.get('title')}",
                    "info"
                )
    
    def _validate_chapters(self):
        """Validate chapters array location and content"""
        # Check both locations
        root_chapters = self.manifest.get('chapters', [])
        structure_chapters = self.manifest.get('structure', {}).get('chapters', [])
        
        if not root_chapters and not structure_chapters:
            self._add_result(
                "chapters_exist",
                False,
                "No chapters found (checked both 'chapters' and 'structure.chapters')",
                "error",
                "Ensure chapters are defined in manifest"
            )
            return
        
        chapters = structure_chapters if structure_chapters else root_chapters
        location = "structure.chapters" if structure_chapters else "chapters"
        
        self._add_result(
            "chapters_exist",
            True,
            f"Found {len(chapters)} chapters at '{location}'",
            "info"
        )
        
        # Validate chapter structure
        for i, chapter in enumerate(chapters):
            # Check required chapter fields
            required = ['source_file', 'title_en' if self.schema_version.startswith("3.5") else 'title']
            title_field = 'title_en' if 'title_en' in chapter else 'title'
            
            if 'source_file' not in chapter:
                self._add_result(
                    f"chapter_{i+1}_source",
                    False,
                    f"Chapter {i+1} missing 'source_file'",
                    "error"
                )
            
            if title_field not in chapter:
                self._add_result(
                    f"chapter_{i+1}_title",
                    False,
                    f"Chapter {i+1} missing title field",
                    "warning"
                )
    
    def _validate_kuchie_fields(self):
        """Validate kuchie field naming consistency"""
        assets = self.manifest.get('assets', {})
        kuchie = assets.get('kuchie', [])
        
        if not kuchie:
            self._add_result(
                "kuchie_exist",
                True,
                "No kuchie images defined (optional)",
                "info"
            )
            return
        
        # Check if kuchie are dicts with proper fields
        if isinstance(kuchie[0], dict):
            has_file = 'file' in kuchie[0]
            has_image_path = 'image_path' in kuchie[0]
            
            if has_file:
                self._add_result(
                    "kuchie_field_naming",
                    True,
                    f"Kuchie uses correct 'file' field ({len(kuchie)} images)",
                    "info"
                )
            elif has_image_path and not has_file:
                self._add_result(
                    "kuchie_field_naming",
                    False,
                    "Kuchie missing 'file' field (Builder expects 'file', found 'image_path')",
                    "error",
                    "Add 'file' field to each kuchie entry (extract filename from 'image_path')"
                )
            else:
                self._add_result(
                    "kuchie_field_naming",
                    False,
                    "Kuchie entries missing both 'file' and 'image_path' fields",
                    "error"
                )
        else:
            # Old format: list of strings
            self._add_result(
                "kuchie_field_naming",
                True,
                f"Kuchie uses legacy string format ({len(kuchie)} images)",
                "info"
            )
    
    def _validate_pipeline_state(self):
        """Validate pipeline state for builder readiness"""
        state = self.manifest.get('pipeline_state', {})
        
        # Check librarian completed
        librarian = state.get('librarian', {})
        if librarian.get('status') != 'completed':
            self._add_result(
                "pipeline_librarian",
                False,
                "Librarian stage not completed",
                "error",
                "Run Phase 1 (Librarian) first"
            )
        else:
            self._add_result(
                "pipeline_librarian",
                True,
                "Librarian completed",
                "info"
            )
        
        # Check translator status
        translator = state.get('translator', {})
        chapters_done = translator.get('chapters_completed', 0)
        chapters_total = translator.get('chapters_total', 0)
        
        if translator.get('status') == 'completed':
            self._add_result(
                "pipeline_translator",
                True,
                f"Translator completed ({chapters_done}/{chapters_total} chapters)",
                "info"
            )
        elif chapters_done > 0:
            self._add_result(
                "pipeline_translator",
                True,
                f"Translator partial ({chapters_done}/{chapters_total} chapters) - can build",
                "warning"
            )
        else:
            self._add_result(
                "pipeline_translator",
                False,
                "No chapters translated yet",
                "error",
                "Run Phase 2 (Translator) first"
            )
    
    def _validate_assets(self):
        """Validate asset references"""
        assets = self.manifest.get('assets', {})
        
        # Check cover
        cover = assets.get('cover')
        if not cover:
            self._add_result(
                "asset_cover",
                False,
                "No cover image specified",
                "warning",
                "Add 'cover' field to assets"
            )
        else:
            self._add_result(
                "asset_cover",
                True,
                f"Cover: {cover}",
                "info"
            )


def validate_volume(volume_id: str) -> bool:
    """Validate a single volume"""
    # Find work directory
    work_dirs = list(WORK_DIR.glob(f"*{volume_id}*"))
    
    if not work_dirs:
        print(f"❌ Volume not found: {volume_id}")
        return False
    
    work_dir = work_dirs[0]
    manifest_path = work_dir / "manifest.json"
    
    print(f"\n{'='*60}")
    print(f"MANIFEST SCHEMA VALIDATOR")
    print(f"{'='*60}")
    print(f"Volume: {work_dir.name}")
    print(f"{'='*60}\n")
    
    try:
        validator = ManifestSchemaValidator(manifest_path)
        passed, results = validator.validate_all()
        
        # Group results by severity
        errors = [r for r in results if r.severity == "error" and not r.passed]
        warnings = [r for r in results if r.severity == "warning" and not r.passed]
        info = [r for r in results if r.passed or r.severity == "info"]
        
        # Print results
        print(f"Schema Version: {validator.schema_version}")
        print()
        
        if errors:
            print("❌ ERRORS (must fix before Phase 4):")
            for r in errors:
                print(f"   • {r.check_name}: {r.message}")
                if r.fix_suggestion:
                    print(f"     → Fix: {r.fix_suggestion}")
            print()
        
        if warnings:
            print("⚠️  WARNINGS (recommended fixes):")
            for r in warnings:
                print(f"   • {r.check_name}: {r.message}")
                if r.fix_suggestion:
                    print(f"     → Fix: {r.fix_suggestion}")
            print()
        
        print(f"✓ PASSED CHECKS: {len(info)}")
        
        print()
        print("="*60)
        if passed:
            print("✅ VALIDATION PASSED - Ready for Phase 4")
        else:
            print("❌ VALIDATION FAILED - Fix errors before Phase 4")
        print("="*60)
        
        return passed
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False


def validate_all_volumes() -> Dict[str, bool]:
    """Validate all volumes in WORK directory"""
    results = {}
    
    for work_dir in sorted(WORK_DIR.iterdir()):
        if work_dir.is_dir() and (work_dir / "manifest.json").exists():
            volume_id = work_dir.name
            results[volume_id] = validate_volume(volume_id)
    
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_manifest_schema.py <volume_id>")
        print("       python validate_manifest_schema.py --all")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == "--all":
        results = validate_all_volumes()
        
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        print(f"Passed: {passed}/{total}")
        
        if passed < total:
            print("\nFailed volumes:")
            for vol, ok in results.items():
                if not ok:
                    print(f"  ❌ {vol}")
        
        sys.exit(0 if passed == total else 1)
    else:
        success = validate_volume(arg)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
