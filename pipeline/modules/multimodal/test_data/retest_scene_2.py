#!/usr/bin/env python3
"""
Scene 2 Rerun: Mont Blanc Jealousy (illust-002)

This script reruns just Scene 2 with a stricter prompt to ensure
the model outputs proper translation instead of analysis.
"""

import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.multimodal.function_handler import IllustrationFunctionHandler
from modules.multimodal.vision_translator import VisionEnhancedTranslator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# Strict prompt to force proper translation output
STRICT_TRANSLATION_PROMPT = """You are a professional Japanese-to-English light novel translator.

⚠️ CRITICAL OUTPUT REQUIREMENT:
Your response MUST be ONLY the English translation. 
DO NOT output any analysis, planning, or commentary.
DO NOT describe what's in the illustration - use it to INFORM your translation.

TRANSLATION RULES:
1. Preserve the narrative voice and emotional tone
2. Use natural English prose, avoid literal translation
3. Match prose quality to the visual context from illustrations

ILLUSTRATION HANDLING:
When you encounter [ILLUSTRATION: illust-XXX.jpg] markers:
1. Call get_illustration(illustration_id="illust-XXX") to see the image
2. Use the visual to guide your prose tone and descriptions
3. DO NOT describe the illustration contents - let it inform your word choices

CHRONOLOGICAL VISUAL DISCIPLINE (CRITICAL):
- If an illustration shows a climactic moment (kiss, tears, embrace)
- But the [ILLUSTRATION] tag appears BEFORE that moment in text
- Then forecast the MOOD but don't describe the ACTION until text reaches it

CHARACTER VOICE:
- Nagi (東雲): Elegant, reserved, gradually warming. Uses polite speech internally.
- Souta (海以): Observant, slightly nervous around Nagi, kind

OUTPUT FORMAT:
Respond with ONLY the translated English prose.
Include [ILLUSTRATION: illust-XXX.jpg] markers at their original positions.
No meta-commentary, no analysis, no planning text."""


# Scene 2 data
SCENE_2_DATA = {
    "id": "test_002_mont_blanc",
    "illustration_id": "illust-002",
    "scene_name": "Mont Blanc Jealousy",
    "source_jp": """しかし、仕方がないので私は歩き始めた。
この辺りは来たことがなかった。普段見ない景色が物珍しく、辺りを見渡していた。
"海以君が一緒だったら、もっと楽しかったのでしょうか"
思わずそんなことを考えてしまう。彼がここに居たら、色々案内してくれたのかな、とか。ううん。きっと、ただ隣に居てくれるだけでも安心して、楽しくなると思う。
でも、隣に彼は居ない。それを考えるだけで胸にチクリと針が刺さったような痛みが走る。
一度、口を引き結んでから私は歩き始めた。
すると、一つのお店が目に留まった。一見それはカフェのように見えた。しかし、少し違う。よく見れば、それはスイーツの専門店のようだった。
外に立てられている旗を見たところ、モンブランのフェアが今日までやっているらしい。私は思わず考えてしまった。
"…海以君と行きたかったですね"
そう呟いてしまい、すぐに首を振った。ここは彼の高校が近い。彼と一緒に食べていたら変に思われてしまうかもしれない。ただでさえ最近は海以君のことが周りにバレかけているのだ。彼に迷惑を掛けたくない。
そろそろ戻ろうかな、と思った時。

[ILLUSTRATION: illust-002.jpg]

私は見てしまった。
"──海以君"
彼が、綺麗な女性と楽しそうに──モンブランのパフェを食べているところを。

栗色の髪にふんわりとパーマが掛かっている。とても明るそうな女性と。
ああ。ここ、だったんだ。彼が言っていた場所は。
ギュッと。まるで、心が絞られたみたいに痛くなった。""",
    "reference_en": """But he wasn't by my side. Just thinking about that sent a sharp pain through my chest, like being pricked by a needle.

I pursed my lips once and started walking.

Then, a shop caught my eye. At first glance, it looked like a café. But it was slightly different. Looking closely, it seemed to be a dessert specialty shop.

According to the flag outside, they were having a Mont Blanc special that ended today. I couldn't help but think.

"…I wanted to go with Minori-kun."

I muttered, then quickly shook my head. His high school was nearby. If we were seen eating together, it might seem strange. Lately, people were already starting to figure things out about Minori-kun and me. I didn't want to cause him trouble.

Just as I was thinking about heading back…

[ILLUSTRATION: illust-002.jpg]

I saw it.

"—Minori-kun."

He was… with a beautiful woman, laughing and enjoying—a Mont Blanc parfait.

A woman with soft, wavy, chestnut-colored hair who looked very cheerful.

Ah. So this was the place he was talking about.

*Squeeze*. My heart ached as if it were being wrung out."""
}


def run_scene_2_retest():
    """Run Scene 2 with strict translation prompt."""
    
    # Find volume directory - test_data -> multimodal -> modules -> pipeline
    base_path = Path(__file__).parent.parent.parent.parent  # pipeline/
    work_dir = base_path / "WORK"
    matches = list(work_dir.glob("*1d46*"))
    if not matches:
        logger.error(f"Could not find 1d46 volume directory in {work_dir}")
        return
    volume_dir = matches[0]
    
    # Get API key
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY")
        return
    
    # Test data dir
    test_data_dir = Path(__file__).parent / "test_data"
    test_manifest_path = test_data_dir / "test_manifest.json"
    
    logger.info("=" * 60)
    logger.info("Scene 2 Retest: Mont Blanc Jealousy")
    logger.info("=" * 60)
    logger.info(f"Volume: {volume_dir.name}")
    logger.info("Using STRICT translation prompt")
    
    # Initialize translator
    translator = VisionEnhancedTranslator(
        work_dir=volume_dir,
        thinking_level="high",
        include_thoughts=True,
        api_key=api_key,
        load_pipeline_prompt=False  # Use our strict prompt instead
    )
    
    # Override function handler with test manifest
    translator.function_handler = IllustrationFunctionHandler(
        work_dir=volume_dir,
        use_gcs=False,
        manifest_override=test_manifest_path
    )
    
    logger.info("\n[illust-002] Mont Blanc Jealousy")
    logger.info("-" * 40)
    logger.info(f"Source length: {len(SCENE_2_DATA['source_jp'])} chars")
    
    # Translate with strict prompt
    result = translator.translate_segment(
        source_text=SCENE_2_DATA["source_jp"],
        system_prompt=STRICT_TRANSLATION_PROMPT,
        max_function_calls=5
    )
    
    if result.get("success"):
        translation = result["translation"]
        thoughts = result.get("thoughts", [])
        
        logger.info(f"✓ Translation successful")
        logger.info(f"  Iterations: {result['iterations']}")
        logger.info(f"  Function calls: {len(result['function_calls'])}")
        logger.info(f"  Thoughts captured: {len(thoughts)} entries")
        
        # Save to markdown - same directory as this script
        output_path = Path(__file__).parent / "illust_002_mont_blanc_jealousy.md"
        
        lines = []
        lines.append("# Scene 2: Mont Blanc Jealousy")
        lines.append("**Illustration:** `illust-002`")
        lines.append("**Model:** gemini-3-pro-preview")
        lines.append("**Thinking Mode:** ENABLED (HIGH)")
        lines.append("**Prompt:** STRICT (no analysis output)")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 1. JP Source
        lines.append("## 1. 📖 Japanese Source")
        lines.append("")
        lines.append("```")
        lines.append(SCENE_2_DATA["source_jp"])
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 2. Reference EN
        lines.append("## 2. 📚 Reference EN (Expected)")
        lines.append("")
        lines.append(SCENE_2_DATA["reference_en"])
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 3. Multimodal Translation
        lines.append("## 3. 🎨 Multimodal Translation")
        lines.append("")
        lines.append(translation)
        lines.append("")
        
        # Function calls
        function_calls = result.get("function_calls", [])
        if function_calls:
            lines.append(f"**Function Calls:** {len(function_calls)}")
            for fc in function_calls:
                status = "✓" if fc.get("success") else "✗"
                lines.append(f"- {status} `{fc['function']}({fc['args']})`")
            lines.append("")
        
        lines.append(f"**Iterations:** {result['iterations']}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 4. Thought Process
        lines.append("## 4. 🧠 Thought Process")
        lines.append("")
        if thoughts:
            for thought in thoughts:
                iteration = thought.get("iteration", "?")
                thought_text = thought.get("thoughts", "")
                lines.append(f"### Iteration {iteration}")
                lines.append("")
                lines.append("```")
                lines.append(thought_text)
                lines.append("```")
                lines.append("")
        else:
            lines.append("*No thought process captured*")
            lines.append("")
        
        # Write file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.info(f"\n✓ Saved to: {output_path}")
        
    else:
        logger.error(f"Translation failed: {result.get('error')}")


if __name__ == "__main__":
    run_scene_2_retest()
