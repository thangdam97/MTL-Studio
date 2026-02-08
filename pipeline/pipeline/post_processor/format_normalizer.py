"""
Format Normalizer - Clean up Japanese formatting in translations.

Automatically detects and converts Japanese typographic conventions
that may leak through translation to international standards.

Runs after Phase 2 translation, works on all configured target languages.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


class FormatNormalizer:
    """
    Normalize Japanese formatting artifacts in translated output.
    
    Handles:
    - Japanese quotation marks (「」) → International quotes ("")
    - Japanese double ellipsis (……) → Single ellipsis (…)
    - Full-width punctuation → Half-width (optional)
    - Japanese spaces → Regular spaces
    """
    
    # Japanese formatting patterns
    JAPANESE_QUOTES_OPEN = '「'
    JAPANESE_QUOTES_CLOSE = '」'
    JAPANESE_ANGLE_QUOTES_OPEN = '《'  # Double angle brackets (Japanese thought/emphasis quotes)
    JAPANESE_ANGLE_QUOTES_CLOSE = '》'
    JAPANESE_DOUBLE_ELLIPSIS = '……'
    JAPANESE_ELLIPSIS_VARIANTS = ['．．．', '。。。', '...']  # Sometimes these appear
    JAPANESE_SPACE = '　'  # Full-width space (U+3000)
    
    # International replacements
    STANDARD_QUOTE = '"'
    STANDARD_ELLIPSIS = '…'
    STANDARD_SPACE = ' '
    
    # Additional full-width punctuation that might leak
    FULLWIDTH_PUNCTUATION = {
        '！': '!',
        '？': '?',
        '，': ',',
        '．': '.',
        '：': ':',
        '；': ';',
        '（': '(',
        '）': ')',
        '｛': '{',
        '｝': '}',
        '［': '[',
        '］': ']',
        '　': ' ',  # Full-width space
    }
    
    def __init__(self, aggressive: bool = False):
        """
        Initialize format normalizer.
        
        Args:
            aggressive: If True, also convert full-width punctuation.
                       Default False to preserve intentional full-width usage.
        """
        self.aggressive = aggressive
        self.stats = {
            'files_processed': 0,
            'files_modified': 0,
            'japanese_quotes': 0,
            'japanese_angle_quotes': 0,
            'double_ellipsis': 0,
            'fullwidth_punct': 0,
            'japanese_spaces': 0
        }
    
    def normalize_file(self, file_path: Path) -> Tuple[bool, Dict[str, int]]:
        """
        Normalize formatting in a single file.
        
        Args:
            file_path: Path to markdown file
            
        Returns:
            Tuple of (was_modified, change_counts)
        """
        if not file_path.exists() or file_path.suffix != '.md':
            return False, {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            local_stats = {
                'japanese_quotes': 0,
                'japanese_angle_quotes': 0,
                'double_ellipsis': 0,
                'fullwidth_punct': 0,
                'japanese_spaces': 0
            }
            
            # 1. Convert Japanese quotation marks 「」
            quote_open_count = content.count(self.JAPANESE_QUOTES_OPEN)
            quote_close_count = content.count(self.JAPANESE_QUOTES_CLOSE)
            if quote_open_count > 0 or quote_close_count > 0:
                content = content.replace(self.JAPANESE_QUOTES_OPEN, self.STANDARD_QUOTE)
                content = content.replace(self.JAPANESE_QUOTES_CLOSE, self.STANDARD_QUOTE)
                local_stats['japanese_quotes'] = quote_open_count + quote_close_count
            
            # 2. Convert Japanese angle quotation marks 《》
            angle_open_count = content.count(self.JAPANESE_ANGLE_QUOTES_OPEN)
            angle_close_count = content.count(self.JAPANESE_ANGLE_QUOTES_CLOSE)
            if angle_open_count > 0 or angle_close_count > 0:
                content = content.replace(self.JAPANESE_ANGLE_QUOTES_OPEN, self.STANDARD_QUOTE)
                content = content.replace(self.JAPANESE_ANGLE_QUOTES_CLOSE, self.STANDARD_QUOTE)
                local_stats['japanese_angle_quotes'] = angle_open_count + angle_close_count
            
            # 3. Convert double ellipsis to single
            ellipsis_count = content.count(self.JAPANESE_DOUBLE_ELLIPSIS)
            if ellipsis_count > 0:
                content = content.replace(self.JAPANESE_DOUBLE_ELLIPSIS, self.STANDARD_ELLIPSIS)
                local_stats['double_ellipsis'] = ellipsis_count
            
            # 4. Convert other ellipsis variants
            for variant in self.JAPANESE_ELLIPSIS_VARIANTS:
                if variant in content:
                    content = content.replace(variant, self.STANDARD_ELLIPSIS)
            
            # 5. Convert Japanese full-width spaces
            space_count = content.count(self.JAPANESE_SPACE)
            if space_count > 0:
                # Preserve in code blocks and between CJK characters
                content = self._normalize_spaces(content)
                local_stats['japanese_spaces'] = space_count
            
            # 6. Optional: Convert full-width punctuation (if aggressive mode)
            if self.aggressive:
                punct_count = 0
                for fw, hw in self.FULLWIDTH_PUNCTUATION.items():
                    if fw in content:
                        punct_count += content.count(fw)
                        content = content.replace(fw, hw)
                local_stats['fullwidth_punct'] = punct_count
            
            # Write back if modified
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True, local_stats
            
            return False, local_stats
            
        except Exception as e:
            print(f"     [WARNING] Error processing {file_path.name}: {e}")
            return False, {}
    
    def _normalize_spaces(self, content: str) -> str:
        """
        Normalize Japanese full-width spaces intelligently.
        
        Preserves spaces between CJK characters where they might be intentional,
        but converts to regular spaces in Latin text context.
        """
        # For now, simple replacement - can be made smarter later
        return content.replace(self.JAPANESE_SPACE, self.STANDARD_SPACE)
    
    def normalize_directory(self, directory: Path, pattern: str = "CHAPTER_*.md") -> Dict[str, int]:
        """
        Normalize all matching files in a directory.
        
        Args:
            directory: Directory containing markdown files
            pattern: Glob pattern for files to process
            
        Returns:
            Dictionary of aggregate statistics
        """
        if not directory.exists():
            return self.stats
        
        files = sorted(directory.glob(pattern))
        
        print(f"\n[FORMAT NORMALIZER] Processing {len(files)} files...")
        
        for file_path in files:
            self.stats['files_processed'] += 1
            was_modified, local_stats = self.normalize_file(file_path)
            
            if was_modified:
                self.stats['files_modified'] += 1
                # Aggregate stats
                for key, value in local_stats.items():
                    self.stats[key] = self.stats.get(key, 0) + value
                
                # Report changes
                changes = []
                if local_stats.get('japanese_quotes', 0) > 0:
                    changes.append(f"{local_stats['japanese_quotes']} quotes 「」")
                if local_stats.get('japanese_angle_quotes', 0) > 0:
                    changes.append(f"{local_stats['japanese_angle_quotes']} quotes 《》")
                if local_stats.get('double_ellipsis', 0) > 0:
                    changes.append(f"{local_stats['double_ellipsis']} ellipses")
                if local_stats.get('japanese_spaces', 0) > 0:
                    changes.append(f"{local_stats['japanese_spaces']} spaces")
                if local_stats.get('fullwidth_punct', 0) > 0:
                    changes.append(f"{local_stats['fullwidth_punct']} punctuation")
                
                if changes:
                    print(f"     ✓ {file_path.name}: Fixed {', '.join(changes)}")
        
        return self.stats
    
    def normalize_volume(self, work_dir: Path, target_languages: List[str] = None) -> Dict[str, Dict[str, int]]:
        """
        Normalize formatting across all target language directories in a volume.
        
        Args:
            work_dir: Volume work directory (contains EN/, VN/, etc.)
            target_languages: List of language codes to process. If None, auto-detect.
            
        Returns:
            Dictionary mapping language code to statistics
        """
        results = {}
        
        # Auto-detect language directories if not specified
        if target_languages is None:
            target_languages = []
            for item in work_dir.iterdir():
                if item.is_dir() and item.name.isupper() and len(item.name) == 2:
                    target_languages.append(item.name)
        
        for lang_code in target_languages:
            lang_dir = work_dir / lang_code.upper()
            if not lang_dir.exists():
                continue
            
            print(f"\n{'='*60}")
            print(f"Processing {lang_code.upper()} output...")
            print(f"{'='*60}")
            
            # Reset stats for this language
            self.stats = {
                'files_processed': 0,
                'files_modified': 0,
                'japanese_quotes': 0,
                'japanese_angle_quotes': 0,
                'double_ellipsis': 0,
                'fullwidth_punct': 0,
                'japanese_spaces': 0
            }
            
            self.normalize_directory(lang_dir)
            results[lang_code.upper()] = dict(self.stats)
            
            # Print summary for this language
            if self.stats['files_modified'] > 0:
                print(f"\n[SUMMARY] {lang_code.upper()}: Fixed {self.stats['files_modified']}/{self.stats['files_processed']} files")
                if self.stats['japanese_quotes'] > 0:
                    print(f"          → {self.stats['japanese_quotes']} Japanese quotes 「」 converted")
                if self.stats['japanese_angle_quotes'] > 0:
                    print(f"          → {self.stats['japanese_angle_quotes']} Japanese angle quotes 《》 converted")
                if self.stats['double_ellipsis'] > 0:
                    print(f"          → {self.stats['double_ellipsis']} double ellipses normalized")
                if self.stats['japanese_spaces'] > 0:
                    print(f"          → {self.stats['japanese_spaces']} full-width spaces converted")
                if self.stats['fullwidth_punct'] > 0:
                    print(f"          → {self.stats['fullwidth_punct']} full-width punctuation converted")
            else:
                print(f"\n[SUMMARY] {lang_code.upper()}: No formatting issues detected")
        
        return results
    

    def deduplicate_headers(self, file_path: Path) -> int:
        """Remove consecutive duplicate H1 headers from a markdown file.

        Returns the number of duplicate headers removed.
        """
        if not file_path.exists() or file_path.suffix != '.md':
            return 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            removed = 0
            cleaned: list[str] = []
            prev_header = None

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    if stripped == prev_header:
                        removed += 1
                        continue
                    prev_header = stripped
                else:
                    if stripped:  # non-blank, non-header resets tracking
                        prev_header = None

                cleaned.append(line)

            if removed > 0:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(cleaned)

            return removed

        except Exception as e:
            print(f"     [WARNING] deduplicate_headers error on {file_path.name}: {e}")
            return 0

    def deduplicate_headers_in_directory(self, directory: Path, pattern: str = "CHAPTER_*.md") -> int:
        """Remove duplicate H1 headers across all matching files. Returns total removed."""
        if not directory.exists():
            return 0

        total = 0
        for file_path in sorted(directory.glob(pattern)):
            count = self.deduplicate_headers(file_path)
            if count > 0:
                print(f"     \u2713 {file_path.name}: removed {count} duplicate H1 header(s)")
                total += count
        return total

    def get_summary(self) -> str:
        """Get human-readable summary of last operation."""
        if self.stats['files_processed'] == 0:
            return "No files processed"
        
        if self.stats['files_modified'] == 0:
            return f"Processed {self.stats['files_processed']} files - No issues found"
        
        lines = [
            f"Processed {self.stats['files_processed']} files",
            f"Modified: {self.stats['files_modified']} files",
            ""
        ]
        
        if self.stats['japanese_quotes'] > 0:
            lines.append(f"  • Japanese quotes (「」): {self.stats['japanese_quotes']} converted")
        if self.stats['japanese_angle_quotes'] > 0:
            lines.append(f"  • Japanese angle quotes (《》): {self.stats['japanese_angle_quotes']} converted")
        if self.stats['double_ellipsis'] > 0:
            lines.append(f"  • Double ellipsis (……): {self.stats['double_ellipsis']} normalized")
        if self.stats['japanese_spaces'] > 0:
            lines.append(f"  • Full-width spaces: {self.stats['japanese_spaces']} converted")
        if self.stats['fullwidth_punct'] > 0:
            lines.append(f"  • Full-width punctuation: {self.stats['fullwidth_punct']} converted")
        
        return "\n".join(lines)


def normalize_volume_formatting(work_dir: Path, aggressive: bool = False) -> Dict[str, Dict[str, int]]:
    """
    Convenience function to normalize formatting in a volume's output.
    
    Args:
        work_dir: Volume work directory path
        aggressive: Enable aggressive full-width punctuation conversion
        
    Returns:
        Statistics dictionary per language
    """
    normalizer = FormatNormalizer(aggressive=aggressive)
    return normalizer.normalize_volume(work_dir)
