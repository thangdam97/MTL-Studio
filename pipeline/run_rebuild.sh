#!/bin/bash
cd /Users/damminhthang/Documents/WORK/AI_MODULES/MTL_STUDIO
source python_env/bin/activate
cd pipeline
python scripts/rebuild_index.py > rebuild_index.log 2>&1
echo "Done! Check rebuild_index.log for results."
