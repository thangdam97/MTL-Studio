#!/usr/bin/env python3
"""
Fix two minor issues in Novel 1a87 Vietnamese translation:
1. Untranslated Japanese interjection まあ at line 207
2. Incomplete sentence at lines 257-259
"""

import sys

def fix_chapter_01():
    """Fix CHAPTER_01_VN.md issues"""
    file_path = "/Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO/pipeline/WORK/2nd cutest v4 JP_20260208_1a87/VN/CHAPTER_01_VN.md"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Issue 1: Fix untranslated まあ at line 207 (index 206)
    if len(lines) > 206:
        original_line = lines[206]
        if 'まあ' in original_line:
            lines[206] = original_line.replace('まあ', 'mà thôi')
            print(f"✓ Fixed untranslated interjection at line 207")
            print(f"  Before: {original_line.strip()}")
            print(f"  After:  {lines[206].strip()}")
        else:
            print(f"⚠ Line 207 doesn't contain まあ, may have been fixed already")
    
    # Issue 2: Fix incomplete sentence at lines 257-259 (indices 256-258)
    if len(lines) > 258:
        # Check if lines 257-259 contain the incomplete sentence
        line_257 = lines[256].strip()
        line_259 = lines[258].strip()
        
        if 'Càng trải qua nhiều thời gian bên nhau' in line_257 and 'Và thế là, tôi đã trải' in line_259:
            # Replace lines 257-259 with complete translation
            # Japanese source:
            # 恋人としての時間を重ねる度、どんどん海の尻に敷かれているような感じだが、こうして手のひらの上で転がされるのも、それほど悪くない。
            # こうして、俺の春休み最終日は賑やかに過ぎていく。
            
            complete_translation = [
                "Càng trải qua nhiều thời gian bên nhau với tư cách người yêu, tôi càng cảm thấy mình đang bị Umi đè đầu cưỡi cổ, nhưng việc bị cô ấy điều khiển như thế này cũng chẳng tệ lắm.\n",
                "\n",
                "Và thế là, ngày cuối cùng của kỳ nghỉ xuân của tôi đã trôi qua một cách náo nhiệt.\n"
            ]
            
            # Replace lines 257-259
            lines[256:259] = complete_translation
            
            print(f"\n✓ Fixed incomplete sentence at lines 257-259")
            print(f"  Before (line 257): {line_257}")
            print(f"  Before (line 259): {line_259}")
            print(f"  After: Càng trải qua nhiều thời gian bên nhau với tư cách người yêu...")
        else:
            print(f"\n⚠ Lines 257-259 don't match expected incomplete sentence, may have been fixed already")
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"\n✅ Fixes applied to {file_path}")
    return True

if __name__ == "__main__":
    try:
        fix_chapter_01()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
