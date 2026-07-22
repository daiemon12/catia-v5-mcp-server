#!/bin/bash
# ============================================================================
#  CATIA V5 MCP Server - Auto Setup Script
#  Run this script on Windows (Git Bash, WSL, or MSYS2)
#  Or run with: bash setup.sh
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "=============================================="
echo "   CATIA V5 MCP Server - Installation"
echo "=============================================="
echo -e "${NC}"

# ── Step 1: Check OS ──
echo -e "${YELLOW}[1/6] Checking environment...${NC}"
if [[ "$OSTYPE" != "msys" && "$OSTYPE" != "cygwin" && "$OSTYPE" != "win32" ]]; then
    if command -v cmd.exe &>/dev/null; then
        echo -e "${GREEN}  WSL detected - OK (will configure Windows side)${NC}"
        IS_WSL=true
    else
        echo -e "${RED}  WARNING: This MCP server requires Windows (COM automation).${NC}"
        echo -e "${RED}  You can still install, but it will only run on Windows.${NC}"
        read -p "  Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    echo -e "${GREEN}  Windows detected - OK${NC}"
fi

# ── Step 2: Check Python ──
echo -e "${YELLOW}[2/6] Checking Python...${NC}"
PYTHON_CMD=""
for cmd in python python3 py; do
    if command -v $cmd &>/dev/null; then
        version=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
            PYTHON_CMD=$cmd
            echo -e "${GREEN}  Found $cmd ($($cmd --version))${NC}"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    echo -e "${RED}  Python 3.10+ not found!${NC}"
    echo -e "${RED}  Download from: https://www.python.org/downloads/${NC}"
    echo -e "${RED}  Make sure to check 'Add Python to PATH' during install.${NC}"
    exit 1
fi

# ── Step 3: Clone or update repo ──
echo -e "${YELLOW}[3/6] Setting up repository...${NC}"
INSTALL_DIR="$HOME/catia-v5-mcp-server"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo -e "${GREEN}  Repository already exists at $INSTALL_DIR${NC}"
    echo "  Pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || echo -e "${YELLOW}  Could not pull (offline?) - using existing files${NC}"
else
    if [[ -d "$INSTALL_DIR" ]]; then
        echo -e "${YELLOW}  Directory exists but no git repo, backing up...${NC}"
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
    fi
    echo "  Cloning from GitHub..."
    git clone https://github.com/daiemon12/catia-v5-mcp-server.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── Step 4: Install Python dependencies ──
echo -e "${YELLOW}[4/6] Installing Python dependencies...${NC}"
$PYTHON_CMD -m pip install --upgrade pip 2>/dev/null || true
$PYTHON_CMD -m pip install -e "$INSTALL_DIR"
echo -e "${GREEN}  Dependencies installed (mcp, pywin32)${NC}"

# ── Step 5: Configure Claude Desktop ──
echo -e "${YELLOW}[5/6] Configuring Claude Desktop...${NC}"

# Find Claude Desktop config path
if [[ "$IS_WSL" == true ]]; then
    WIN_APPDATA=$(cmd.exe /C "echo %APPDATA%" 2>/dev/null | tr -d '\r')
    CLAUDE_CONFIG_DIR=$(wslpath "$WIN_APPDATA/Claude" 2>/dev/null || echo "")
else
    CLAUDE_CONFIG_DIR="${APPDATA}/Claude"
fi

CLAUDE_CONFIG="${CLAUDE_CONFIG_DIR}/claude_desktop_config.json"

# Get the Python path for the config
if [[ "$IS_WSL" == true ]]; then
    PYTHON_WIN_PATH=$(which $PYTHON_CMD | sed 's|/mnt/c|C:|; s|/|\\|g')
    SERVER_WIN_PATH=$(wslpath -w "$INSTALL_DIR/catia_mcp/server.py" 2>/dev/null || echo "")
else
    PYTHON_WIN_PATH=$($PYTHON_CMD -c "import sys; print(sys.executable)" 2>/dev/null | tr '/' '\\')
    SERVER_WIN_PATH=$(cd "$INSTALL_DIR" && pwd -W 2>/dev/null || pwd)/catia_mcp/server.py
    SERVER_WIN_PATH=$(echo "$SERVER_WIN_PATH" | tr '/' '\\')
fi

if [[ -n "$CLAUDE_CONFIG_DIR" && -d "$CLAUDE_CONFIG_DIR" ]]; then
    # Create or update config
    if [[ -f "$CLAUDE_CONFIG" ]]; then
        echo -e "${YELLOW}  Existing config found. Checking for catia-v5 entry...${NC}"
        if grep -q "catia-v5" "$CLAUDE_CONFIG" 2>/dev/null; then
            echo -e "${GREEN}  catia-v5 already configured in Claude Desktop!${NC}"
        else
            echo -e "${YELLOW}  Adding catia-v5 to existing config...${NC}"
            # Use Python to safely merge JSON
            $PYTHON_CMD -c "
import json, sys
config_path = r'''$CLAUDE_CONFIG'''
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except:
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

config['mcpServers']['catia-v5'] = {
    'command': 'python',
    'args': ['-m', 'catia_mcp']
}

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print('  Config updated successfully!')
"
        fi
    else
        echo "  Creating Claude Desktop config..."
        mkdir -p "$CLAUDE_CONFIG_DIR"
        cat > "$CLAUDE_CONFIG" << 'JSONEOF'
{
  "mcpServers": {
    "catia-v5": {
      "command": "python",
      "args": ["-m", "catia_mcp"]
    }
  }
}
JSONEOF
        echo -e "${GREEN}  Config created at: $CLAUDE_CONFIG${NC}"
    fi
else
    echo -e "${YELLOW}  Claude Desktop config directory not found.${NC}"
    echo -e "${YELLOW}  You'll need to manually configure it.${NC}"
    echo ""
    echo -e "  Add this to ${CYAN}%APPDATA%\\Claude\\claude_desktop_config.json${NC}:"
    echo ""
    echo -e "${CYAN}  {${NC}"
    echo -e "${CYAN}    \"mcpServers\": {${NC}"
    echo -e "${CYAN}      \"catia-v5\": {${NC}"
    echo -e "${CYAN}        \"command\": \"python\",${NC}"
    echo -e "${CYAN}        \"args\": [\"-m\", \"catia_mcp\"]${NC}"
    echo -e "${CYAN}      }${NC}"
    echo -e "${CYAN}    }${NC}"
    echo -e "${CYAN}  }${NC}"
fi

# ── Step 6: Verification ──
echo -e "${YELLOW}[6/6] Verifying installation...${NC}"

# Check if mcp is importable
if $PYTHON_CMD -c "import mcp" 2>/dev/null; then
    echo -e "${GREEN}  mcp package ........... OK${NC}"
else
    echo -e "${RED}  mcp package ........... FAILED${NC}"
fi

# Check if catia_mcp is importable
if $PYTHON_CMD -c "import catia_mcp" 2>/dev/null; then
    echo -e "${GREEN}  catia_mcp package ..... OK${NC}"
else
    echo -e "${RED}  catia_mcp package ..... FAILED${NC}"
fi

# Check pywin32 (will fail on non-Windows, that's expected)
if $PYTHON_CMD -c "import win32com" 2>/dev/null; then
    echo -e "${GREEN}  pywin32 (COM) ......... OK${NC}"
else
    echo -e "${YELLOW}  pywin32 (COM) ......... SKIPPED (requires Windows)${NC}"
fi

echo ""
echo -e "${GREEN}=============================================="
echo "   Installation complete!"
echo "==============================================${NC}"
echo ""
echo -e "  ${CYAN}Next steps:${NC}"
echo "  1. Make sure CATIA V5 is running"
echo "  2. Restart Claude Desktop"
echo "  3. Talk to Claude: \"Create a new CATIA part\""
echo ""
echo -e "  ${CYAN}Register from the Claude CLI:${NC}"
echo "  claude mcp add catia-v5 python -- -m catia_mcp"
echo ""
echo -e "  ${CYAN}Manual test:${NC}"
echo "  $PYTHON_CMD -m catia_mcp"
echo ""
