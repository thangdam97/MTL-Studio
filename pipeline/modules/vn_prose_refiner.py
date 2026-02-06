"""
VN Prose Refiner - Post-processor for Vietnamese AI-ism elimination
Transforms AI-sounding Vietnamese into natural prose

Based on vietnamese_grammar_rag.json patterns:
1. "một cách [adj]" → direct adverb or vivid verb
2. "một cảm giác" → direct emotion
3. "sự [noun] của" → use verb form
4. Missing particles → add natural Vietnamese particles

Author: MTL Studio
Version: 1.0
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json


@dataclass
class Refinement:
    """Single refinement applied"""
    pattern: str
    original: str
    replacement: str
    line_num: int
    category: str


class VNProseRefiner:
    """
    Post-processor to eliminate AI-isms from Vietnamese translations
    """
    
    def __init__(self):
        """Initialize with Vietnamese AI-ism patterns and their fixes"""
        
        # "một cách [adj]" replacements - most common AI-ism
        self.mot_cach_map = {
            # Food/eating context
            "một cách thanh đạm": "thanh đạm",
            "một cách tĩnh lặng": "lặng lẽ",
            "một cách từ tốn": "từ tốn",
            "một cách mềm mại": "mềm mại",
            "một cách ngon lành": "ngon lành",
            "một cách đầy thưởng thức": "đầy thưởng thức",
            "một cách say mê": "say mê",
            "một cách đầy thỏa mãn": "thỏa mãn",
            "một cách trọn vẹn": "trọn vẹn",
            
            # Emotional/behavioral context
            "một cách nghiêm túc": "nghiêm túc",
            "một cách xuất sắc": "xuất sắc",
            "một cách đầy thách thức": "đầy thách thức",
            "một cách bí ẩn": "bí ẩn",
            "một cách đột ngột": "đột ngột",
            "một cách chậm rãi": "chậm rãi",
            "một cách vội vàng": "vội vã",
            "một cách cẩn thận": "cẩn thận",
            "một cách tự nhiên": "tự nhiên",
            "một cách kỳ lạ": "kỳ lạ",
            "một cách đáng ngạc nhiên": "đáng ngạc nhiên",
            "một cách nửa vời": "nửa vời",
            "một cách trìu mến": "trìu mến",
            "một cách dịu dàng": "dịu dàng",
            "một cách mạnh mẽ": "mạnh mẽ",
            "một cách nhẹ nhàng": "nhẹ nhàng",
            "một cách hoàn hảo": "hoàn hảo",
            "một cách tuyệt vời": "tuyệt vời",
            "một cách đẹp đẽ": "đẹp đẽ",
            "một cách lặng lẽ": "lặng lẽ",
            "một cách âm thầm": "âm thầm",
            "một cách rõ ràng": "rõ ràng",
            "một cách mơ hồ": "mơ hồ",
            "một cách chân thành": "chân thành",
            "một cách trung thực": "trung thực",
            "một cách khéo léo": "khéo léo",
            "một cách tinh tế": "tinh tế",
            "một cách sâu sắc": "sâu sắc",
            "một cách toàn diện": "toàn diện",
            "một cách triệt để": "triệt để",
            "một cách kiên quyết": "kiên quyết",
            "một cách dứt khoát": "dứt khoát",
            "một cách táo bạo": "táo bạo",
            "một cách liều lĩnh": "liều lĩnh",
            "một cách khác thường": "khác thường",
            "một cách phi thường": "phi thường",
            "một cách bất ngờ": "bất ngờ",
            "một cách đáng sợ": "đáng sợ",
            "một cách đáng yêu": "đáng yêu",
            
            # From 2218 remaining patterns (round 2)
            "một cách lạ thường": "lạ thường",
            "một cách ngoạn mục": "ngoạn mục",
            "một cách đúng đắn": "đúng đắn",
            "một cách vô ích": "vô ích",
            "một cách thuần túy": "thuần túy",
            "một cách thận trọng": "thận trọng",
            "một cách thản nhiên": "thản nhiên",
            "một cách tao nhã": "tao nhã",
            "một cách suôn sẻ": "suôn sẻ",
            "một cách say sưa": "say sưa",
            "một cách não nề": "não nề",
            "một cách mãn nguyện": "mãn nguyện",
            "một cách lịch sự": "lịch sự",
            "một cách khỏe mạnh": "khỏe mạnh",
            "một cách hào phóng": "hào phóng",
            "một cách gượng gạo": "gượng gạo",
            "một cách dữ dội": "dữ dội",
            "một cách dễ hiểu": "dễ hiểu",
            "một cách dè dặt": "dè dặt",
            "một cách đầy phô trương": "phô trương",
            "một cách đầy mong đợi": "đầy mong đợi",
            "một cách đầy khí thế": "đầy khí thế",
            "một cách đáng ngờ": "đáng ngờ",
            "một cách cứng đờ": "cứng đờ",
            "một cách chăm chú": "chăm chú",
            "một cách bình thản": "bình thản",
            "một cách bản năng": "theo bản năng",
        }
        
        # "một cảm giác" replacements
        self.cam_giac_map = {
            "một cảm giác bất an": "sự bất an",
            "một cảm giác nhẹ nhõm": "sự nhẹ nhõm",
            "một cảm giác căng thẳng": "sự căng thẳng",
            "một cảm giác hoài niệm": "nỗi hoài niệm",
            "một cảm giác tội lỗi": "cảm giác tội lỗi",
            "một cảm giác kỳ lạ": "cảm giác kỳ lạ",
            "một cảm giác quen thuộc": "cảm giác quen thuộc",
            "một cảm giác ấm áp": "sự ấm áp",
            "một cảm giác hạnh phúc": "niềm hạnh phúc",
            "một cảm giác cô đơn": "nỗi cô đơn",
            "một cảm giác buồn bã": "nỗi buồn",
        }
        
        # Context-aware sentence patterns
        self.sentence_patterns = [
            # "tôi có cảm giác như" patterns
            (r"[Tt]ôi có cảm giác như", "Tựa như"),
            (r"[Cc]ó cảm giác như", "Như thể"),
            
            # "sự xuất hiện của X" → "X xuất hiện"
            (r"[Ss]ự xuất hiện của ([a-zA-ZÀ-ỹ\s]+) khiến", r"\1 xuất hiện khiến"),
            (r"[Ss]ự ra đi của ([a-zA-ZÀ-ỹ\s]+) khiến", r"\1 ra đi khiến"),
            (r"[Ss]ự thay đổi của ([a-zA-ZÀ-ỹ\s]+)", r"\1 thay đổi"),
            
            # "Việc X là Y" → "X là Y"
            (r"^Việc ([a-zA-ZÀ-ỹ\s]+) là", r"\1 là"),
            (r"^Việc này giúp", "Điều này giúp"),
        ]
        
        # Statistics
        self.stats = {
            "total_refinements": 0,
            "by_category": {},
            "by_chapter": {}
        }
    
    def refine_text(self, text: str, chapter_id: str = "00") -> Tuple[str, List[Refinement]]:
        """
        Refine Vietnamese text to eliminate AI-isms
        
        Args:
            text: Vietnamese text content
            chapter_id: Chapter identifier for tracking
            
        Returns:
            Tuple of (refined_text, list_of_refinements)
        """
        refinements = []
        lines = text.split('\n')
        refined_lines = []
        
        for line_num, line in enumerate(lines, 1):
            original_line = line
            
            # Apply "một cách" fixes
            for pattern, replacement in self.mot_cach_map.items():
                if pattern in line:
                    line = line.replace(pattern, replacement)
                    refinements.append(Refinement(
                        pattern=pattern,
                        original=original_line,
                        replacement=replacement,
                        line_num=line_num,
                        category="mot-cach"
                    ))
            
            # Apply "một cảm giác" fixes
            for pattern, replacement in self.cam_giac_map.items():
                if pattern in line:
                    line = line.replace(pattern, replacement)
                    refinements.append(Refinement(
                        pattern=pattern,
                        original=original_line,
                        replacement=replacement,
                        line_num=line_num,
                        category="mot-cam-giac"
                    ))
            
            # Apply sentence-level patterns (regex)
            for pattern, replacement in self.sentence_patterns:
                if re.search(pattern, line):
                    new_line = re.sub(pattern, replacement, line)
                    if new_line != line:
                        refinements.append(Refinement(
                            pattern=pattern,
                            original=line,
                            replacement=new_line,
                            line_num=line_num,
                            category="sentence-pattern"
                        ))
                        line = new_line
            
            refined_lines.append(line)
        
        # Update stats
        self.stats["total_refinements"] += len(refinements)
        self.stats["by_chapter"][chapter_id] = len(refinements)
        for r in refinements:
            self.stats["by_category"][r.category] = self.stats["by_category"].get(r.category, 0) + 1
        
        return '\n'.join(refined_lines), refinements
    
    def refine_chapter_file(self, file_path: str, dry_run: bool = False) -> Dict:
        """
        Refine a single chapter file
        
        Args:
            file_path: Path to VN chapter file
            dry_run: If True, don't write changes
            
        Returns:
            Dict with refinement results
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        
        # Extract chapter ID
        match = re.search(r'CHAPTER_(\d+)', path.name)
        chapter_id = match.group(1) if match else "00"
        
        # Read content
        content = path.read_text(encoding='utf-8')
        
        # Refine
        refined_content, refinements = self.refine_text(content, chapter_id)
        
        # Write if not dry run and changes were made
        if not dry_run and refinements:
            path.write_text(refined_content, encoding='utf-8')
        
        return {
            "file": path.name,
            "chapter": chapter_id,
            "refinements_count": len(refinements),
            "refinements": [
                {
                    "line": r.line_num,
                    "category": r.category,
                    "pattern": r.pattern,
                    "fixed": r.replacement
                }
                for r in refinements
            ],
            "dry_run": dry_run
        }
    
    def refine_volume(self, volume_path: str, dry_run: bool = False) -> Dict:
        """
        Refine all VN chapters in a volume
        
        Args:
            volume_path: Path to volume directory
            dry_run: If True, don't write changes
            
        Returns:
            Dict with all refinement results
        """
        path = Path(volume_path)
        vn_dir = path / "VN"
        
        if not vn_dir.exists():
            return {"error": f"VN directory not found: {vn_dir}"}
        
        results = {
            "volume": path.name,
            "dry_run": dry_run,
            "chapters": [],
            "summary": {
                "total_files": 0,
                "total_refinements": 0,
                "by_category": {}
            }
        }
        
        # Reset stats
        self.stats = {
            "total_refinements": 0,
            "by_category": {},
            "by_chapter": {}
        }
        
        # Process each chapter
        for vn_file in sorted(vn_dir.glob("CHAPTER_*_VN.md")):
            result = self.refine_chapter_file(str(vn_file), dry_run)
            results["chapters"].append(result)
            results["summary"]["total_files"] += 1
            results["summary"]["total_refinements"] += result.get("refinements_count", 0)
        
        # Add category breakdown
        results["summary"]["by_category"] = self.stats["by_category"]
        
        return results


def run_vn_prose_refiner(volume_id: str, dry_run: bool = False):
    """
    CLI entry point for VN Prose Refiner
    
    Args:
        volume_id: Volume to refine (e.g., "2218")
        dry_run: If True, show changes without applying
    """
    # Find volume path
    work_dir = Path(__file__).parent.parent / "WORK"
    
    volume_path = None
    for folder in work_dir.iterdir():
        if folder.is_dir() and volume_id in folder.name:
            volume_path = folder
            break
    
    if not volume_path:
        print(f"❌ Volume {volume_id} not found in WORK directory")
        return
    
    print(f"{'🔍 DRY RUN:' if dry_run else '✏️ REFINING:'} Vietnamese prose for volume {volume_id}")
    print(f"   Path: {volume_path.name}")
    print()
    
    # Create refiner and run
    refiner = VNProseRefiner()
    results = refiner.refine_volume(str(volume_path), dry_run)
    
    # Print results
    print("=" * 60)
    print("REFINEMENT SUMMARY")
    print("=" * 60)
    print(f"Files processed: {results['summary']['total_files']}")
    print(f"Total refinements: {results['summary']['total_refinements']}")
    print()
    
    print("By Category:")
    for cat, count in sorted(results['summary']['by_category'].items(), key=lambda x: -x[1]):
        print(f"  - {cat}: {count}")
    print()
    
    print("By Chapter:")
    for chapter in results['chapters']:
        if chapter.get('refinements_count', 0) > 0:
            print(f"  - Chapter {chapter['chapter']}: {chapter['refinements_count']} refinements")
    
    # Save detailed results
    if not dry_run:
        results_path = volume_path / "audits" / "prose_refinements.json"
        results_path.parent.mkdir(exist_ok=True)
        results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"\n📄 Details saved to: {results_path}")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vn_prose_refiner.py <volume_id> [--dry-run]")
        print("Example: python vn_prose_refiner.py 2218 --dry-run")
        sys.exit(1)
    
    volume_id = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    
    run_vn_prose_refiner(volume_id, dry_run)
