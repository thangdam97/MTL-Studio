"""
Scene Break Formatter.
Automatically replaces various scene break markers with the standard markdown format.
Runs immediately after AI translation completes.

Supported proprietary patterns (discovered from OUTPUT analysis):
- Asterisks: *, **, ***, * * *, ***
- Diamonds: ◆, ◇, ◆◇◆, ◆　◇　◆　◇, ◆　　　　　　◆
- Stars: ★, ☆, ★ ★ ★, ☆ ☆ ☆, ☆☆
- Triangles: ▼▽
- Circles: ●, ○
- Ampersand: & (discovered in 0dad)
- Others: ※※※, §, ◇ ◇ ◇, ◇　　　◇　　　◇
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class SceneBreakFormatter:
    """Formats scene breaks in translated markdown files."""
    
    # Comprehensive pattern to match various scene break styles
    # These patterns must be on their own line with optional whitespace
    SCENE_BREAK_PATTERNS = [
        # Asterisk variations (most common)
        r'^\s*\*{1,5}\s*$',                          # *, **, ***, ****, *****
        r'^\s*\*\s+\*\s+\*\s*$',                     # * * *
        r'^\s*\*\s*\*\s*\*\s*$',                     # * * * (no strict spacing)
        
        # Diamond variations (◆◇)
        r'^\s*◆\s*$',                                # ◆
        r'^\s*◇\s*$',                                # ◇
        r'^\s*◆◇◆\s*$',                              # ◆◇◆
        r'^\s*◇◆◇\s*$',                              # ◇◆◇
        r'^\s*◆[\s　]*◇[\s　]*◆[\s　]*◇?\s*$',       # ◆　◇　◆　◇ (with JP spaces)
        r'^\s*◇[\s　]*◆[\s　]*◇[\s　]*◆?\s*$',       # ◇　◆　◇　◆
        r'^\s*◆[\s　]+◆\s*$',                        # ◆　　　　　　◆ (spaced diamonds)
        r'^\s*◇[\s　]+◇[\s　]+◇\s*$',                # ◇　　　◇　　　◇
        r'^\s*◇\s+◇\s+◇\s*$',                        # ◇ ◇ ◇
        
        # Star variations (★☆)
        r'^\s*★\s*$',                                # ★
        r'^\s*☆\s*$',                                # ☆
        r'^\s*★\s+★\s+★\s*$',                        # ★ ★ ★
        r'^\s*☆\s+☆\s+☆\s*$',                        # ☆ ☆ ☆
        r'^\s*☆☆+\s*$',                              # ☆☆, ☆☆☆
        r'^\s*★★+\s*$',                              # ★★, ★★★
        
        # Triangle variations (▼▽△▲)
        r'^\s*▼▽\s*$',                               # ▼▽
        r'^\s*▽▼\s*$',                               # ▽▼
        r'^\s*[▼▽△▲]{2,}\s*$',                       # Any triangle combo
        
        # Circle variations (●○)
        r'^\s*●\s*$',                                # ●
        r'^\s*○\s*$',                                # ○
        r'^\s*[●○]{2,}\s*$',                         # ●○, ○●, etc.
        
        # Other symbols
        r'^\s*※※※\s*$',                              # ※※※
        r'^\s*※[\s　]*※[\s　]*※\s*$',                 # ※ ※ ※
        r'^\s*§\s*$',                                # §
        r'^\s*§§+\s*$',                              # §§, §§§
        r'^\s*&\s*$',                                # & (discovered in 0dad)
        r'^\s*❖\s*$',                                # ❖
        r'^\s*◈\s*$',                                # ◈
        r'^\s*⬥\s*$',                                # ⬥
        r'^\s*✦\s*$',                                # ✦
        r'^\s*⁂\s*$',                                # ⁂ (asterism)
    ]
    
    # Compile all patterns into one regex with OR
    SCENE_BREAK_PATTERN = re.compile(
        '|'.join(SCENE_BREAK_PATTERNS),
        re.MULTILINE
    )
    
    # Replacement: Standard markdown scene break format (Builder will convert to XHTML)
    # The Builder expects "* * *" format and will render it as centered diamond
    REPLACEMENT = '\n* * *\n'
    
    @staticmethod
    def format_scene_breaks(content: str) -> tuple[str, int]:
        """
        Replace asterisk scene breaks with standard markdown format.
        
        Args:
            content: The markdown content to process
            
        Returns:
            Tuple of (formatted_content, number_of_replacements)
        """
        # Count replacements for logging
        matches = SceneBreakFormatter.SCENE_BREAK_PATTERN.findall(content)
        count = len(matches)
        
        # Perform replacement
        formatted_content = SceneBreakFormatter.SCENE_BREAK_PATTERN.sub(
            SceneBreakFormatter.REPLACEMENT,
            content
        )
        
        return formatted_content, count
    
    @staticmethod
    def format_file(file_path: Path) -> Optional[int]:
        """
        Format scene breaks in a markdown file.
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            Number of scene breaks replaced, or None if error
        """
        try:
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None
            
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Format scene breaks
            formatted_content, count = SceneBreakFormatter.format_scene_breaks(content)
            
            # Only write if changes were made
            if count > 0:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(formatted_content)
                logger.info(f"Formatted {count} scene break(s) in {file_path.name}")
            else:
                logger.debug(f"No scene breaks found in {file_path.name}")
            
            return count
            
        except Exception as e:
            logger.error(f"Error formatting scene breaks in {file_path}: {e}")
            return None
