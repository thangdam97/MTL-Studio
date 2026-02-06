#!/bin/bash
# ============================================
# MT Publishing Pipeline - VSCodium Startup
# ============================================
# Clean startup script with main menu
# Launches from a single terminal with interactive menu
#
# To use in VSCodium:
#   1. Open terminal (Ctrl+`)
#   2. Run: ./start.sh
# ============================================

# CRITICAL: Clear any buffered input from shell auto-execution IMMEDIATELY
# This prevents shell init code (venv activation, etc.) from being captured as menu input
while IFS= read -r -t 0.1 -u 0 line 2>/dev/null; do :; done || true
# Also clear any control sequences in the terminal
stty -f /dev/tty -icanon 2>/dev/null || true

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Clear screen and show header
clear
echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       MTL PUBLISHING PIPELINE - MAIN MENU                    ║"
echo "║       Japanese Light Novel Translation System                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check Python
find_python() {
    if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
        echo "$SCRIPT_DIR/venv/bin/python"
    elif command -v python3 &> /dev/null; then
        echo "python3"
    elif command -v python &> /dev/null; then
        if python --version 2>&1 | grep -q "Python 3"; then
            echo "python"
        fi
    fi
}

PYTHON_CMD=$(find_python)

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}✗ Error: Python 3.10+ not found${NC}"
    echo ""
    echo "Install Python:"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓${NC} Python: $($PYTHON_CMD --version)"

# Check/install dependencies
if ! $PYTHON_CMD -c "import questionary; import rich" 2>/dev/null; then
    echo -e "${YELLOW}⟳ Installing dependencies...${NC}"
    $PYTHON_CMD -m pip install questionary rich -q

    if ! $PYTHON_CMD -c "import questionary; import rich" 2>/dev/null; then
        echo -e "${RED}✗ Failed to install dependencies${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓${NC} Dependencies ready"

# Show current config
echo ""
echo -e "${CYAN}Current Configuration:${NC}"
$PYTHON_CMD -c "
from pipeline.cli.utils.config_bridge import ConfigBridge
config = ConfigBridge()
config.load()
lang = config.target_language
lang_name = config.get_language_config(lang).get('language_name', lang.upper())
print(f'  Language: {lang_name} ({lang.upper()})')
print(f'  Model: {config.model}')
print(f'  Caching: {\"Enabled\" if config.caching_enabled else \"Disabled\"}')
" 2>/dev/null || echo "  (Could not load config)"

echo ""

# FINAL cleanup: drain any remaining input before menu starts
while IFS= read -r -t 0.05 -u 0 line 2>/dev/null; do :; done || true

# Main Menu Loop
while true; do
    clear
    echo ""
    echo -e "${BLUE}${BOLD}═══ MAIN MENU ═══${NC}"
    echo ""
    echo -e "  ${GREEN}1${NC}  Start Full Pipeline"
    echo -e "  ${GREEN}2${NC}  Phase 1: Extract EPUB"
    echo -e "  ${GREEN}3${NC}  Phase 1.6: Multimodal Processor"
    echo -e "  ${GREEN}4${NC}  Phase 2: Translate Chapters"
    echo -e "  ${GREEN}5${NC}  Phase 4: Build EPUB"
    echo -e "  ${GREEN}6${NC}  Check Volume Status"
    echo -e "  ${GREEN}7${NC}  List All Volumes"
    echo -e "  ${GREEN}8${NC}  Configuration"
    echo -e "  ${GREEN}9${NC}  Exit"
    echo ""
    # Clear stdin buffer completely before reading
    while IFS= read -r -t 0 line; do :; done 2>/dev/null || true
    # Read choice
    read -r -p "Select option (1-9): " choice
    # Remove any leading/trailing whitespace and ensure valid input
    choice=$(echo "$choice" | xargs)
    echo ""

    case $choice in
        1)
            echo -e "${CYAN}Starting Full Pipeline...${NC}"
            echo ""
            
            # List available EPUB files
            INPUT_DIR="$SCRIPT_DIR/INPUT"
            if [ ! -d "$INPUT_DIR" ] || [ -z "$(ls -A "$INPUT_DIR"/*.epub 2>/dev/null)" ]; then
                echo -e "${RED}✗ No EPUB files found in INPUT/ directory${NC}"
                read -r -p "Press Enter to continue..."
                continue
            fi
            
            echo -e "${CYAN}Available EPUB files:${NC}"
            epub_files=()
            while IFS= read -r file; do
                epub_files+=("$file")
            done < <(ls "$INPUT_DIR"/*.epub 2>/dev/null)
            
            for i in "${!epub_files[@]}"; do
                filename=$(basename "${epub_files[$i]}")
                echo -e "  ${GREEN}$((i+1))${NC}  $filename"
            done
            echo ""
            
            read -r -p "Select file number (or 0 to cancel): " file_num
            if [ "$file_num" = "0" ] || [ -z "$file_num" ]; then
                continue
            fi
            
            if ! [[ "$file_num" =~ ^[0-9]+$ ]] || [ "$file_num" -lt 1 ] || [ "$file_num" -gt "${#epub_files[@]}" ]; then
                echo -e "${RED}✗ Invalid selection${NC}"
                read -r -p "Press Enter to continue..."
                continue
            fi
            
            epub_path="${epub_files[$((file_num-1))]}"
            echo -e "${GREEN}Selected: $(basename "$epub_path")${NC}"
            echo ""
            
            read -r -p "Enter volume ID (or press Enter for auto-generate): " vol_id
            
            if [ -z "$vol_id" ]; then
                $PYTHON_CMD "$SCRIPT_DIR/mtl.py" run "$epub_path" --verbose
            else
                $PYTHON_CMD "$SCRIPT_DIR/mtl.py" run "$epub_path" --id "$vol_id" --verbose
            fi
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        2)
            echo -e "${CYAN}Phase 1: Extract EPUB${NC}"
            echo ""
            
            # List available EPUB files
            INPUT_DIR="$SCRIPT_DIR/INPUT"
            if [ ! -d "$INPUT_DIR" ] || [ -z "$(ls -A "$INPUT_DIR"/*.epub 2>/dev/null)" ]; then
                echo -e "${RED}✗ No EPUB files found in INPUT/ directory${NC}"
                read -r -p "Press Enter to continue..."
                continue
            fi
            
            echo -e "${CYAN}Available EPUB files:${NC}"
            epub_files=()
            while IFS= read -r file; do
                epub_files+=("$file")
            done < <(ls "$INPUT_DIR"/*.epub 2>/dev/null)
            
            for i in "${!epub_files[@]}"; do
                filename=$(basename "${epub_files[$i]}")
                echo -e "  ${GREEN}$((i+1))${NC}  $filename"
            done
            echo ""
            
            read -r -p "Select file number (or 0 to cancel): " file_num
            if [ "$file_num" = "0" ] || [ -z "$file_num" ]; then
                continue
            fi
            
            if ! [[ "$file_num" =~ ^[0-9]+$ ]] || [ "$file_num" -lt 1 ] || [ "$file_num" -gt "${#epub_files[@]}" ]; then
                echo -e "${RED}✗ Invalid selection${NC}"
                read -r -p "Press Enter to continue..."
                continue
            fi
            
            epub_path="${epub_files[$((file_num-1))]}"
            echo -e "${GREEN}Selected: $(basename "$epub_path")${NC}"
            echo ""
            
            # Clear input buffer before prompting
            while IFS= read -r -t 0.1 -u 0 line 2>/dev/null; do :; done || true
            
            read -r -p "Enter volume ID (optional): " vol_id
            
            if [ -z "$vol_id" ]; then
                $PYTHON_CMD "$SCRIPT_DIR/mtl.py" phase1 "$epub_path"
            else
                $PYTHON_CMD "$SCRIPT_DIR/mtl.py" phase1 "$epub_path" --id "$vol_id"
            fi
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        3)
            echo -e "${CYAN}Phase 1.6: Multimodal Processor (Illustration Analysis)${NC}"
            echo -e "${YELLOW}Pre-bakes visual analysis for illustrations using Gemini 3 Pro Vision.${NC}"
            echo -e "${YELLOW}Run this AFTER Phase 1 and BEFORE Phase 2 for visual-enhanced translation.${NC}"
            echo ""
            
            # Auto-detect latest volume from WORK directory
            latest_vol=$(ls -1t "$SCRIPT_DIR/WORK" | grep -E ".*_[0-9]{8}_[a-z0-9]{4}$" | head -1)
            
            if [ -z "$latest_vol" ]; then
                echo -e "${RED}✗ No volumes found in WORK directory${NC}"
                read -r -p "Enter volume ID manually: " vol_id
                if [ -z "$vol_id" ]; then
                    echo -e "${RED}✗ Volume ID required${NC}"
                    read -r -p "Press Enter to continue..."
                    continue
                fi
            else
                echo -e "${GREEN}✓ Auto-detected latest volume:${NC} $latest_vol"
                read -r -p "Use this volume? (Y/n): " confirm
                if [[ "$confirm" =~ ^[Nn] ]]; then
                    read -r -p "Enter volume ID: " vol_id
                else
                    vol_id="$latest_vol"
                fi
            fi
            
            $PYTHON_CMD "$SCRIPT_DIR/mtl.py" phase1.6 "$vol_id"
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        4)
            echo -e "${CYAN}Phase 2: Translate Chapters${NC}"
            
            # Auto-detect latest volume from WORK directory
            latest_vol=$(ls -1t "$SCRIPT_DIR/WORK" | grep -E ".*_[0-9]{8}_[a-z0-9]{4}$" | head -1)
            
            if [ -z "$latest_vol" ]; then
                echo -e "${RED}✗ No volumes found in WORK directory${NC}"
                read -r -p "Enter volume ID manually: " vol_id
                if [ -z "$vol_id" ]; then
                    echo -e "${RED}✗ Volume ID required${NC}"
                    read -r -p "Press Enter to continue..."
                    continue
                fi
            else
                echo -e "${GREEN}✓ Auto-detected latest volume:${NC} $latest_vol"
                read -r -p "Use this volume? (Y/n): " confirm
                if [[ "$confirm" =~ ^[Nn] ]]; then
                    read -r -p "Enter volume ID: " vol_id
                else
                    vol_id="$latest_vol"
                fi
            fi
            
            $PYTHON_CMD "$SCRIPT_DIR/mtl.py" phase2 "$vol_id"
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        5)
            echo -e "${CYAN}Phase 4: Build EPUB${NC}"
            
            # Auto-detect latest volume from WORK directory
            latest_vol=$(ls -1t "$SCRIPT_DIR/WORK" | grep -E ".*_[0-9]{8}_[a-z0-9]{4}$" | head -1)
            
            if [ -z "$latest_vol" ]; then
                echo -e "${RED}✗ No volumes found in WORK directory${NC}"
                read -r -p "Enter volume ID manually: " vol_id
                if [ -z "$vol_id" ]; then
                    echo -e "${RED}✗ Volume ID required${NC}"
                    read -r -p "Press Enter to continue..."
                    continue
                fi
            else
                echo -e "${GREEN}✓ Auto-detected latest volume:${NC} $latest_vol"
                read -r -p "Use this volume? (Y/n): " confirm
                if [[ "$confirm" =~ ^[Nn] ]]; then
                    read -r -p "Enter volume ID: " vol_id
                else
                    vol_id="$latest_vol"
                fi
            fi
            
            $PYTHON_CMD "$SCRIPT_DIR/mtl.py" phase4 "$vol_id"
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        6)
            echo -e "${CYAN}Check Volume Status${NC}"
            read -r -p "Enter volume ID: " vol_id
            $PYTHON_CMD "$SCRIPT_DIR/mtl.py" status "$vol_id"
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        7)
            echo -e "${CYAN}List All Volumes${NC}"
            $PYTHON_CMD "$SCRIPT_DIR/mtl.py" list
            echo ""
            read -r -p "Press Enter to continue..."
            ;;
        8)
            echo -e "${CYAN}${BOLD}Configuration Menu${NC}"
            echo ""
            echo -e "  ${GREEN}a${NC}  Show Current Config"
            echo -e "  ${GREEN}b${NC}  Set Target Language"
            echo -e "  ${GREEN}c${NC}  Set Model"
            echo -e "  ${GREEN}d${NC}  Set Temperature"
            echo -e "  ${GREEN}e${NC}  Back to Main Menu"
            echo ""
            # Clear stdin buffer
            while IFS= read -r -t 0 line; do :; done 2>/dev/null || true
            read -r -p "Select option (a-e): " config_choice
            
            case $config_choice in
                a)
                    $PYTHON_CMD "$SCRIPT_DIR/mtl.py" config --show
                    echo ""
                    read -r -p "Press Enter to continue..."
                    ;;
                b)
                    echo "Available languages: en, vn"
                    read -r -p "Enter language code: " lang
                    $PYTHON_CMD "$SCRIPT_DIR/mtl.py" config --language "$lang"
                    echo ""
                    read -r -p "Press Enter to continue..."
                    ;;
                c)
                    echo "Available models: flash, pro, 2.5-pro"
                    read -r -p "Enter model: " model
                    $PYTHON_CMD "$SCRIPT_DIR/mtl.py" config --model "$model"
                    echo ""
                    read -r -p "Press Enter to continue..."
                    ;;
                d)
                    read -r -p "Enter temperature (0.0-2.0): " temp
                    $PYTHON_CMD "$SCRIPT_DIR/mtl.py" config --temperature "$temp"
                    echo ""
                    read -r -p "Press Enter to continue..."
                    ;;
                e)
                    continue
                    ;;
                *)
                    echo -e "${RED}✗ Invalid option. Please select a-e.${NC}"
                    read -r -p "Press Enter to continue..."
                    ;;
            esac
            ;;
        9)
            echo -e "${CYAN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            if [ -n "$choice" ]; then
                echo -e "${RED}✗ Invalid option: $choice. Please select 1-9.${NC}"
            fi
            ;;
    esac
done

