#!/bin/bash
# Quick validation script for 1a60 baseline vs optimized

WORK_DIR="WORK/他校の氷姫を助けたら、お友達から始める事になりました３_20260209_1a60"

echo "════════════════════════════════════════════════════════════"
echo "  VALIDATION SCRIPT: 1a60 Baseline vs Optimized"
echo "════════════════════════════════════════════════════════════"
echo ""

# Step 1: Backup old output
echo "Step 1: Backing up old baseline..."
if [ -d "$WORK_DIR/EN" ] && [ ! -d "$WORK_DIR/EN_baseline_old_prompts" ]; then
    cp -r "$WORK_DIR/EN" "$WORK_DIR/EN_baseline_old_prompts"
    echo "✓ Backup created: EN_baseline_old_prompts"
else
    echo "✓ Backup already exists or EN/ not found"
fi
echo ""

# Step 2: Show current file sizes
echo "Step 2: Current file sizes..."
echo "OLD Baseline:"
if [ -d "$WORK_DIR/EN_baseline_old_prompts" ]; then
    ls -lh "$WORK_DIR/EN_baseline_old_prompts/" | tail -n +2
else
    echo "  (Not backed up yet)"
fi
echo ""

# Step 3: Ready for new translation
echo "Step 3: Ready for optimized translation"
echo "Run: python scripts/mtl.py --volume 1a60"
echo ""

# Step 4: Validation commands (to run after translation)
echo "Step 4: After translation completes, run grammar validation:"
echo ""
echo "# Check OLD baseline:"
echo "python -c \"from pipeline.post_processor.grammar_validator import GrammarValidator; \\"
echo "validator = GrammarValidator(auto_fix=False); \\"
echo "results = validator.validate_volume('$WORK_DIR/EN_baseline_old_prompts'); \\"
echo "total = sum(r.total_violations for r in results.values()); \\"
echo "print(f'OLD Baseline: {total} total violations')\""
echo ""
echo "# Check NEW optimized:"
echo "python -c \"from pipeline.post_processor.grammar_validator import GrammarValidator; \\"
echo "validator = GrammarValidator(auto_fix=False); \\"
echo "results = validator.validate_volume('$WORK_DIR/EN'); \\"
echo "total = sum(r.total_violations for r in results.values()); \\"
echo "print(f'NEW Optimized: {total} total violations')\""
echo ""

# Step 5: Manual comparison
echo "Step 5: Manual comparison:"
echo "diff -u <(head -100 '$WORK_DIR/EN_baseline_old_prompts/CHAPTER_01_EN.md') \\"
echo "        <(head -100 '$WORK_DIR/EN/CHAPTER_01_EN.md') | head -50"
echo ""

echo "════════════════════════════════════════════════════════════"
echo "  Ready for validation!"
echo "════════════════════════════════════════════════════════════"
