#!/usr/bin/env python3
"""
Post-Translation Formatting Validator
======================================

Validates translated chapters for common formatting issues BEFORE audit.
Catches problems that are auto-fixable, reducing audit friction.

Issues detected:
- Duplicate chapter headers
- Missing/malformed scene breaks
- Trailing whitespace issues
- Inconsistent heading levels
- Empty/placeholder content
- CJK character leaks (for non-CJK targets)

Usage:
    python scripts/validate_translation_formatting.py <volume_id>
    python scripts/validate_translation_formatting.py 095d --fix  # Auto-fix issues

Author: MTL Studio
Version: 1.0
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent
WORK_DIR = PIPELINE_DIR / "WORK"


@dataclass
class FormattingIssue:
    """A single formatting issue found in a chapter"""
    file_path: Path
    line_number: int
    issue_type: str
    description: str
    severity: str  # error, warning
    auto_fixable: bool
    suggested_fix: Optional[str] = None


@dataclass
class ValidationReport:
    """Summary of formatting validation for a volume"""
    volume_id: str
    chapters_scanned: int
    total_issues: int
    errors: int
    warnings: int
    auto_fixable: int
    issues: List[FormattingIssue]


class TranslationFormattingValidator:
    """
    Validates translated chapter files for formatting issues.
    
    Detects:
    - Duplicate headers (same line appearing twice)
    - Malformed markdown headers (# vs ## inconsistency)
    - Scene break issues (missing or inconsistent)
    - Empty content between headers
    - CJK leaks in non-CJK translations
    - Trailing/leading whitespace issues
    """
    
    # CJK character ranges
    CJK_PATTERN = re.compile(
        r'[\u4e00-\u9fff'  # CJK Unified Ideographs
        r'\u3400-\u4dbf'   # CJK Extension A
        r'\u3040-\u309f'   # Hiragana
        r'\u30a0-\u30ff'   # Katakana
        r'\uff00-\uffef]'  # Fullwidth forms
    )
    
    # Scene break patterns (various styles)
    SCENE_BREAK_PATTERNS = [
        r'^[\*]{1,5}$',           # *, **, ***
        r'^◆+$',                  # ◆, ◆◆◆
        r'^─+$',                  # ───
        r'^[☆★]+$',              # ☆☆☆
        r'^\*\s*\*\s*\*$',       # * * *
    ]
    
    def __init__(self, target_language: str = "en"):
        self.target_language = target_language.lower()
        self.issues: List[FormattingIssue] = []
    
    def validate_file(self, file_path: Path) -> List[FormattingIssue]:
        """Validate a single chapter file"""
        self.issues = []
        
        if not file_path.exists():
            return self.issues
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        self._check_duplicate_headers(file_path, lines)
        self._check_heading_consistency(file_path, lines)
        self._check_empty_content(file_path, lines)
        self._check_scene_breaks(file_path, lines)
        self._check_whitespace_issues(file_path, lines)
        
        # CJK leak detection for non-CJK languages
        if self.target_language not in ['ja', 'zh', 'ko', 'vi', 'vn']:
            self._check_cjk_leaks(file_path, lines)
        
        return self.issues
    
    def _check_duplicate_headers(self, file_path: Path, lines: List[str]):
        """Check for duplicate consecutive headers"""
        prev_line = None
        prev_was_header = False
        
        for i, line in enumerate(lines, 1):
            is_header = line.strip().startswith('#')
            
            if is_header and prev_was_header:
                # Check if it's the same header
                if line.strip() == prev_line:
                    self.issues.append(FormattingIssue(
                        file_path=file_path,
                        line_number=i,
                        issue_type="DUPLICATE_HEADER",
                        description=f"Duplicate header: '{line.strip()[:50]}...'",
                        severity="error",
                        auto_fixable=True,
                        suggested_fix="Remove the duplicate line"
                    ))
            
            prev_line = line.strip() if is_header else prev_line
            prev_was_header = is_header
        
        # Also check for header at line 1 and line 3 with blank between
        if len(lines) >= 3:
            line1 = lines[0].strip()
            line2 = lines[1].strip() if len(lines) > 1 else ""
            line3 = lines[2].strip() if len(lines) > 2 else ""
            
            if (line1.startswith('#') and line3.startswith('#') and 
                line2 == "" and line1 == line3):
                self.issues.append(FormattingIssue(
                    file_path=file_path,
                    line_number=3,
                    issue_type="DUPLICATE_HEADER_SEPARATED",
                    description=f"Duplicate header at lines 1 and 3: '{line1[:50]}...'",
                    severity="error",
                    auto_fixable=True,
                    suggested_fix="Remove line 3 and the preceding blank line"
                ))
    
    def _check_heading_consistency(self, file_path: Path, lines: List[str]):
        """Check for inconsistent heading levels"""
        heading_levels = []
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('#'):
                # Count # symbols
                level = len(line) - len(line.lstrip('#'))
                heading_levels.append((i, level, line.strip()))
        
        # Check for jumps (e.g., # to ### without ##)
        prev_level = 0
        for line_num, level, text in heading_levels:
            if level > prev_level + 1 and prev_level > 0:
                self.issues.append(FormattingIssue(
                    file_path=file_path,
                    line_number=line_num,
                    issue_type="HEADING_LEVEL_SKIP",
                    description=f"Heading level jump from {prev_level} to {level}: '{text[:40]}...'",
                    severity="warning",
                    auto_fixable=False,
                    suggested_fix=f"Consider using {'#' * (prev_level + 1)} instead"
                ))
            prev_level = level
    
    def _check_empty_content(self, file_path: Path, lines: List[str]):
        """Check for empty content sections"""
        in_content = False
        content_start = 0
        blank_count = 0
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('#'):
                if in_content and blank_count > 5:
                    self.issues.append(FormattingIssue(
                        file_path=file_path,
                        line_number=content_start,
                        issue_type="EXCESSIVE_BLANKS",
                        description=f"Excessive blank lines ({blank_count}) after line {content_start}",
                        severity="warning",
                        auto_fixable=True,
                        suggested_fix="Reduce to 1-2 blank lines"
                    ))
                in_content = True
                content_start = i
                blank_count = 0
            elif line.strip() == "":
                blank_count += 1
            else:
                blank_count = 0
    
    def _check_scene_breaks(self, file_path: Path, lines: List[str]):
        """Check scene break formatting"""
        scene_break_styles = set()
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern in self.SCENE_BREAK_PATTERNS:
                if re.match(pattern, stripped):
                    scene_break_styles.add(pattern)
                    break
        
        # Warn if multiple styles used
        if len(scene_break_styles) > 1:
            self.issues.append(FormattingIssue(
                file_path=file_path,
                line_number=0,  # File-wide issue
                issue_type="INCONSISTENT_SCENE_BREAKS",
                description=f"Multiple scene break styles detected: {len(scene_break_styles)} different patterns",
                severity="warning",
                auto_fixable=True,
                suggested_fix="Standardize all scene breaks to ◆"
            ))
    
    def _check_whitespace_issues(self, file_path: Path, lines: List[str]):
        """Check for whitespace problems"""
        trailing_count = 0
        
        for i, line in enumerate(lines, 1):
            # Trailing whitespace
            if line != line.rstrip():
                trailing_count += 1
        
        if trailing_count > 10:
            self.issues.append(FormattingIssue(
                file_path=file_path,
                line_number=0,
                issue_type="TRAILING_WHITESPACE",
                description=f"{trailing_count} lines with trailing whitespace",
                severity="warning",
                auto_fixable=True,
                suggested_fix="Remove trailing whitespace from all lines"
            ))
    
    def _check_cjk_leaks(self, file_path: Path, lines: List[str]):
        """Check for CJK character leaks in non-CJK translations"""
        leaks = []
        
        for i, line in enumerate(lines, 1):
            # Skip lines that are clearly metadata or comments
            if line.strip().startswith('#') or line.strip().startswith('<!--'):
                continue
            
            matches = self.CJK_PATTERN.findall(line)
            if matches:
                leaks.append((i, matches[:5]))  # First 5 chars
        
        if leaks:
            sample = leaks[:3]
            self.issues.append(FormattingIssue(
                file_path=file_path,
                line_number=sample[0][0] if sample else 0,
                issue_type="CJK_LEAK",
                description=f"{len(leaks)} lines with CJK characters (e.g., line {sample[0][0]}: {''.join(sample[0][1])})",
                severity="error",
                auto_fixable=False,
                suggested_fix="Review and translate remaining CJK text"
            ))


def fix_duplicate_headers(file_path: Path) -> bool:
    """Auto-fix duplicate header issues in a file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    
    # Fix header at line 1 and 3 with blank between
    if len(lines) >= 3:
        line1 = lines[0].strip()
        line2 = lines[1].strip() if len(lines) > 1 else ""
        line3 = lines[2].strip() if len(lines) > 2 else ""
        
        if (line1.startswith('#') and line3.startswith('#') and 
            line2 == "" and line1 == line3):
            # Remove line 3 and the blank line 2
            del lines[2]
            del lines[1]
            modified = True
    
    # Fix consecutive duplicate headers
    i = 1
    while i < len(lines):
        if (lines[i].strip().startswith('#') and 
            lines[i-1].strip().startswith('#') and 
            lines[i].strip() == lines[i-1].strip()):
            del lines[i]
            modified = True
        else:
            i += 1
    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    
    return modified


def fix_scene_breaks(file_path: Path) -> bool:
    """Standardize scene breaks to ◆"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Replace various scene break patterns with ◆
    patterns = [
        (r'^[\*]{3,}$', '◆', re.MULTILINE),
        (r'^\*\s*\*\s*\*$', '◆', re.MULTILINE),
        (r'^─{3,}$', '◆', re.MULTILINE),
        (r'^[☆★]{3,}$', '◆', re.MULTILINE),
    ]
    
    for pattern, replacement, flags in patterns:
        content = re.sub(pattern, replacement, content, flags=flags)
    
    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    
    return False


def fix_trailing_whitespace(file_path: Path) -> bool:
    """Remove trailing whitespace from all lines"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    cleaned = []
    
    for line in lines:
        stripped = line.rstrip() + '\n' if line.endswith('\n') else line.rstrip()
        if stripped != line:
            modified = True
        cleaned.append(stripped if line.endswith('\n') else stripped)
    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(cleaned)
    
    return modified


def validate_volume(volume_id: str, auto_fix: bool = False) -> ValidationReport:
    """Validate all translated chapters in a volume"""
    # Find work directory
    work_dirs = list(WORK_DIR.glob(f"*{volume_id}*"))
    
    if not work_dirs:
        print(f"❌ Volume not found: {volume_id}")
        return None
    
    work_dir = work_dirs[0]
    
    # Find EN directory
    en_dir = work_dir / "EN"
    if not en_dir.exists():
        print(f"❌ No EN directory found in {work_dir.name}")
        return None
    
    print(f"\n{'='*60}")
    print(f"POST-TRANSLATION FORMATTING VALIDATOR")
    print(f"{'='*60}")
    print(f"Volume: {work_dir.name}")
    print(f"Mode: {'AUTO-FIX' if auto_fix else 'SCAN ONLY'}")
    print(f"{'='*60}\n")
    
    # Get target language from manifest
    manifest_path = work_dir / "manifest.json"
    target_lang = "en"
    if manifest_path.exists():
        import json
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        target_lang = manifest.get('pipeline_state', {}).get('translator', {}).get('target_language', 'en')
    
    validator = TranslationFormattingValidator(target_language=target_lang)
    all_issues: List[FormattingIssue] = []
    chapters_scanned = 0
    fixes_applied = 0
    
    # Scan all chapter files
    chapter_files = sorted(en_dir.glob("CHAPTER_*_EN.md"))
    
    for chapter_file in chapter_files:
        chapters_scanned += 1
        issues = validator.validate_file(chapter_file)
        
        if issues:
            print(f"📄 {chapter_file.name}: {len(issues)} issue(s)")
            for issue in issues:
                icon = "❌" if issue.severity == "error" else "⚠️"
                fix_tag = " [AUTO-FIXABLE]" if issue.auto_fixable else ""
                print(f"   {icon} Line {issue.line_number}: {issue.issue_type}{fix_tag}")
                print(f"      {issue.description}")
            
            # Auto-fix if requested
            if auto_fix:
                fixed_something = False
                
                for issue in issues:
                    if issue.auto_fixable:
                        if issue.issue_type in ["DUPLICATE_HEADER", "DUPLICATE_HEADER_SEPARATED"]:
                            if fix_duplicate_headers(chapter_file):
                                fixed_something = True
                                fixes_applied += 1
                        elif issue.issue_type == "INCONSISTENT_SCENE_BREAKS":
                            if fix_scene_breaks(chapter_file):
                                fixed_something = True
                                fixes_applied += 1
                        elif issue.issue_type == "TRAILING_WHITESPACE":
                            if fix_trailing_whitespace(chapter_file):
                                fixed_something = True
                                fixes_applied += 1
                
                if fixed_something:
                    print(f"   ✅ Auto-fixes applied to {chapter_file.name}")
        else:
            print(f"✓ {chapter_file.name}: OK")
        
        all_issues.extend(issues)
    
    # Summary
    errors = sum(1 for i in all_issues if i.severity == "error")
    warnings = sum(1 for i in all_issues if i.severity == "warning")
    auto_fixable = sum(1 for i in all_issues if i.auto_fixable)
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Chapters scanned: {chapters_scanned}")
    print(f"Total issues: {len(all_issues)}")
    print(f"  Errors: {errors}")
    print(f"  Warnings: {warnings}")
    print(f"  Auto-fixable: {auto_fixable}")
    
    if auto_fix:
        print(f"  Fixes applied: {fixes_applied}")
    
    print()
    if errors == 0:
        print("✅ No blocking issues - ready for audit")
    else:
        print("❌ Errors found - fix before audit")
        if auto_fixable > 0 and not auto_fix:
            print(f"   Run with --fix to auto-fix {auto_fixable} issue(s)")
    print(f"{'='*60}")
    
    return ValidationReport(
        volume_id=volume_id,
        chapters_scanned=chapters_scanned,
        total_issues=len(all_issues),
        errors=errors,
        warnings=warnings,
        auto_fixable=auto_fixable,
        issues=all_issues
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_translation_formatting.py <volume_id> [--fix]")
        print("       python validate_translation_formatting.py 095d")
        print("       python validate_translation_formatting.py 095d --fix  # Auto-fix issues")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    auto_fix = "--fix" in sys.argv
    
    report = validate_volume(volume_id, auto_fix)
    
    if report is None:
        sys.exit(1)
    
    sys.exit(0 if report.errors == 0 else 1)


if __name__ == "__main__":
    main()
