"""
Content Splitter - Split large chapters into manageable parts for translation.

Used for publishers with minimal TOC structures (e.g., Hifumi Shobo) where
entire volumes get merged into single chapters that exceed API token limits.
"""

import re
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ChapterPart:
    """Represents a split part of a chapter."""
    content: str
    part_number: int
    word_count: int
    estimated_tokens: int
    illustrations: List[str]
    start_line: int
    end_line: int


class ContentSplitter:
    """Split large chapter content into translation-safe parts."""
    
    def __init__(
        self,
        max_tokens: int = 2000,
        min_tokens: int = 800,
        scene_break_patterns: Optional[List[str]] = None
    ):
        """
        Initialize content splitter.
        
        Args:
            max_tokens: Maximum tokens per part (default: 2000)
            min_tokens: Minimum tokens per part to avoid tiny splits (default: 800)
            scene_break_patterns: Regex patterns for scene breaks
        """
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        
        # Default scene break patterns
        self.scene_break_patterns = scene_break_patterns or [
            r'^\s*[\*◇◆]{3,}\s*$',    # ***, ◇◇◇, ◆◆◆
            r'^\s*＊{3,}\s*$',          # ＊＊＊ (full-width)
            r'^―{5,}$',                 # ―――――
            r'^\s*\*\s*\*\s*\*\s*$',   # * * *
        ]
        
        # Compile patterns
        self.scene_break_regex = [re.compile(p, re.MULTILINE) for p in self.scene_break_patterns]
        
        # Illustration marker pattern
        self.illust_pattern = re.compile(r'\[ILLUSTRATION:\s*([^\]]+)\]')
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for Japanese text.
        
        Rough heuristic: 1 token ≈ 0.7 words for Japanese
        (More accurate than 1:1 due to multi-byte characters)
        """
        words = len(re.findall(r'\S+', text))
        return int(words * 0.7)
    
    def extract_illustrations(self, text: str) -> List[str]:
        """Extract illustration references from text."""
        return self.illust_pattern.findall(text)
    
    def detect_scene_breaks(self, lines: List[str]) -> List[int]:
        """
        Detect scene break line numbers.
        
        Returns:
            List of line indices where scene breaks occur
        """
        breaks = []
        
        for idx, line in enumerate(lines):
            # Check each pattern
            for pattern in self.scene_break_regex:
                if pattern.match(line):
                    breaks.append(idx)
                    break
        
        return breaks
    
    def detect_paragraph_clusters(self, lines: List[str]) -> List[int]:
        """
        Detect natural breaking points based on empty line clusters.
        
        Returns:
            List of line indices where 3+ consecutive empty lines occur
        """
        breaks = []
        empty_count = 0
        
        for idx, line in enumerate(lines):
            if not line.strip():
                empty_count += 1
            else:
                if empty_count >= 3:
                    breaks.append(idx - empty_count // 2)  # Mid-point of empty cluster
                empty_count = 0
        
        return breaks
    
    def split_by_token_limit(
        self,
        content: str,
        break_points: List[int]
    ) -> List[Tuple[int, int]]:
        """
        Split content into parts based on token limits and break points.
        
        Args:
            content: Full chapter content
            break_points: Sorted list of potential split line numbers
        
        Returns:
            List of (start_line, end_line) tuples for each part
        """
        lines = content.split('\n')
        parts = []
        current_start = 0
        current_tokens = 0
        
        for idx, line in enumerate(lines):
            line_tokens = self.estimate_tokens(line)
            
            # Check if adding this line would exceed limit
            if current_tokens + line_tokens > self.max_tokens and current_tokens >= self.min_tokens:
                # Look for nearest break point
                nearest_break = None
                for bp in break_points:
                    if current_start < bp <= idx:
                        nearest_break = bp
                
                # Use break point if found, otherwise split at current line
                split_line = nearest_break if nearest_break else idx
                parts.append((current_start, split_line))
                current_start = split_line
                current_tokens = 0
            
            current_tokens += line_tokens
        
        # Add final part
        if current_start < len(lines):
            parts.append((current_start, len(lines)))
        
        return parts
    
    def split_chapter(self, content: str) -> List[ChapterPart]:
        """
        Split chapter content into parts.
        
        Args:
            content: Full chapter markdown content
        
        Returns:
            List of ChapterPart objects
        """
        # Quick check: does this need splitting?
        total_tokens = self.estimate_tokens(content)
        if total_tokens <= self.max_tokens:
            return [ChapterPart(
                content=content,
                part_number=1,
                word_count=len(re.findall(r'\S+', content)),
                estimated_tokens=total_tokens,
                illustrations=self.extract_illustrations(content),
                start_line=0,
                end_line=len(content.split('\n'))
            )]
        
        lines = content.split('\n')
        
        # Detect scene breaks
        scene_breaks = self.detect_scene_breaks(lines)
        
        # If no scene breaks, use paragraph clusters
        if not scene_breaks:
            scene_breaks = self.detect_paragraph_clusters(lines)
        
        # Split by token limits using break points
        split_ranges = self.split_by_token_limit(content, scene_breaks)
        
        # Build ChapterPart objects
        parts = []
        for part_num, (start, end) in enumerate(split_ranges, 1):
            part_lines = lines[start:end]
            part_content = '\n'.join(part_lines)
            
            parts.append(ChapterPart(
                content=part_content,
                part_number=part_num,
                word_count=len(re.findall(r'\S+', part_content)),
                estimated_tokens=self.estimate_tokens(part_content),
                illustrations=self.extract_illustrations(part_content),
                start_line=start,
                end_line=end
            ))
        
        return parts
    
    def split_with_title(
        self,
        content: str,
        base_title: str
    ) -> List[Tuple[str, str]]:
        """
        Split chapter and generate titles for each part.
        
        Args:
            content: Full chapter content
            base_title: Original chapter title
        
        Returns:
            List of (title, content) tuples
        """
        parts = self.split_chapter(content)
        
        if len(parts) == 1:
            return [(base_title, content)]
        
        result = []
        for part in parts:
            part_title = f"{base_title} - Part {part.part_number}"
            result.append((part_title, part.content))
        
        return result


def split_large_chapter(
    content: str,
    max_tokens: int = 2000,
    min_tokens: int = 800,
    scene_break_patterns: Optional[List[str]] = None
) -> List[ChapterPart]:
    """
    Convenience function to split a large chapter.
    
    Args:
        content: Chapter markdown content
        max_tokens: Maximum tokens per part
        min_tokens: Minimum tokens per part
        scene_break_patterns: Custom scene break patterns
    
    Returns:
        List of ChapterPart objects
    """
    splitter = ContentSplitter(max_tokens, min_tokens, scene_break_patterns)
    return splitter.split_chapter(content)


# =============================================================================
# KODANSHA HEADING-BASED CHAPTER SPLITTER
# =============================================================================

@dataclass
class SplitChapter:
    """Represents a chapter extracted from heading-based splitting."""
    id: str
    title: str
    content: str
    word_count: int
    illustrations: List[str]
    toc_order: int


class KodanshaSplitter:
    """
    Split Kodansha-style continuous chapters based on heading markers.
    
    Kodansha EPUBs often merge all content into one file with ### N markers.
    This splitter:
    1. Filters out copyright/credits content
    2. Filters out 目次 (table of contents) headers
    3. Splits chapters by ### heading patterns
    """
    
    # Default heading patterns for Kodansha
    DEFAULT_HEADING_PATTERNS = [
        r'^###\s+[１２３４５６７８９０]+$',  # Full-width numbers: ### １
        r'^###\s+\d+$',                      # Half-width numbers: ### 1
        r'^###\s+プロローグ$',                # Prologue
        r'^###\s+エピローグ$',                # Epilogue
        r'^###\s+あとがき$',                  # Afterword
        r'^###\s+序章$',                      # Opening chapter
        r'^###\s+終章$',                      # Closing chapter
    ]
    
    # Patterns to filter out (copyright, credits, TOC)
    FILTER_PATTERNS = [
        r'^#\s*目次\s*$',                    # # 目次 (TOC header)
        r'^口絵.*イラスト[／/]',              # 口絵・本文イラスト／xxx
        r'^デザイン[／/]',                   # デザイン／xxx  
        r'^装丁[／/]',                       # 装丁／xxx
        r'^カバーイラスト[／/]',              # カバーイラスト／xxx
        r'^本文イラスト[／/]',                # 本文イラスト／xxx
        r'^©\s*\d{4}',                       # © 2024 copyright lines
        r'^\d{4}年\d{1,2}月.*発行',          # Publication date lines
        r'^発行.*株式会社',                   # Publisher lines
        r'^印刷.*株式会社',                   # Printer lines
        r'^ISBN',                            # ISBN lines
    ]
    
    def __init__(
        self,
        heading_patterns: Optional[List[str]] = None,
        filter_patterns: Optional[List[str]] = None
    ):
        """
        Initialize Kodansha splitter.
        
        Args:
            heading_patterns: Custom heading patterns (uses defaults if None)
            filter_patterns: Custom filter patterns (uses defaults if None)
        """
        self.heading_patterns = heading_patterns or self.DEFAULT_HEADING_PATTERNS
        self.filter_patterns = filter_patterns or self.FILTER_PATTERNS
        
        # Compile patterns
        self.heading_regex = [re.compile(p, re.MULTILINE) for p in self.heading_patterns]
        self.filter_regex = [re.compile(p, re.MULTILINE) for p in self.filter_patterns]
        
        # Illustration pattern
        self.illust_pattern = re.compile(r'!\[illustration\]\(([^)]+)\)')
    
    def _should_filter_line(self, line: str) -> bool:
        """Check if a line should be filtered out."""
        stripped = line.strip()
        if not stripped:
            return False
        
        for pattern in self.filter_regex:
            if pattern.match(stripped):
                return True
        return False
    
    def _is_heading_line(self, line: str) -> Optional[str]:
        """
        Check if line is a chapter heading.
        
        Returns the heading title if matched, None otherwise.
        """
        stripped = line.strip()
        for pattern in self.heading_regex:
            if pattern.match(stripped):
                # Extract the title (everything after ###)
                match = re.match(r'^###\s+(.+)$', stripped)
                if match:
                    return match.group(1)
        return None
    
    def _extract_illustrations(self, text: str) -> List[str]:
        """Extract illustration references from text."""
        return self.illust_pattern.findall(text)
    
    def _clean_content(self, lines: List[str]) -> List[str]:
        """
        Clean content by filtering lines that match filter patterns.
        
        Also removes any content before the first chapter heading.
        """
        cleaned = []
        found_first_heading = False
        
        for line in lines:
            # Check if this is a chapter heading
            if self._is_heading_line(line):
                found_first_heading = True
                cleaned.append(line)
                continue
            
            # Before first heading: only keep illustrations
            if not found_first_heading:
                # Skip non-illustration content before first heading
                if self.illust_pattern.search(line):
                    continue  # Skip standalone illustrations in header area
                continue
            
            # After first heading: filter specific patterns
            if self._should_filter_line(line):
                continue
            
            cleaned.append(line)
        
        return cleaned
    
    def detect_chapters(self, content: str) -> int:
        """
        Detect how many chapter markers exist in content.
        
        Args:
            content: Markdown content
        
        Returns:
            Number of chapter markers found
        """
        count = 0
        for line in content.split('\n'):
            if self._is_heading_line(line):
                count += 1
        return count
    
    def split_chapters(
        self,
        content: str,
        base_chapter_num: int = 1
    ) -> List[SplitChapter]:
        """
        Split content by heading markers into separate chapters.
        
        Args:
            content: Full markdown content with multiple ### headings
            base_chapter_num: Starting chapter number (default: 1)
        
        Returns:
            List of SplitChapter objects
        """
        lines = content.split('\n')
        
        # Clean content first
        cleaned_lines = self._clean_content(lines)
        
        if not cleaned_lines:
            return []
        
        # Find chapter boundaries
        chapters = []
        current_title = None
        current_lines = []
        chapter_num = base_chapter_num
        
        for line in cleaned_lines:
            heading_title = self._is_heading_line(line)
            
            if heading_title:
                # Save previous chapter if exists
                if current_title is not None and current_lines:
                    chapter_content = '\n'.join(current_lines).strip()
                    if chapter_content:  # Only add non-empty chapters
                        illustrations = self._extract_illustrations(chapter_content)
                        chapters.append(SplitChapter(
                            id=f"chapter_{chapter_num:02d}",
                            title=current_title,
                            content=chapter_content,
                            word_count=len(chapter_content.split()),
                            illustrations=illustrations,
                            toc_order=chapter_num
                        ))
                        chapter_num += 1
                
                # Start new chapter
                current_title = heading_title
                current_lines = [line]  # Include heading in content
            else:
                current_lines.append(line)
        
        # Don't forget the last chapter
        if current_title is not None and current_lines:
            chapter_content = '\n'.join(current_lines).strip()
            if chapter_content:
                illustrations = self._extract_illustrations(chapter_content)
                chapters.append(SplitChapter(
                    id=f"chapter_{chapter_num:02d}",
                    title=current_title,
                    content=chapter_content,
                    word_count=len(chapter_content.split()),
                    illustrations=illustrations,
                    toc_order=chapter_num
                ))
        
        return chapters
    
    def should_split(self, content: str, min_chapters: int = 2) -> bool:
        """
        Check if content should be split (has multiple chapter markers).
        
        Args:
            content: Markdown content
            min_chapters: Minimum chapters to trigger split
        
        Returns:
            True if content has enough chapter markers
        """
        return self.detect_chapters(content) >= min_chapters


def create_kodansha_splitter(heading_patterns: Optional[List[str]] = None) -> KodanshaSplitter:
    """
    Factory function to create a Kodansha splitter.
    
    Args:
        heading_patterns: Custom heading patterns (uses defaults if None)
    
    Returns:
        Configured KodanshaSplitter instance
    """
    return KodanshaSplitter(heading_patterns=heading_patterns)
