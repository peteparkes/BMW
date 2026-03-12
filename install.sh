#!/usr/bin/env bash
# =============================================================================
# BMW E90 Diagnostics – Linux / macOS installer
# =============================================================================
# Creates a desktop shortcut and installs Python dependencies.
#
# Usage:
#   chmod +x install.sh && ./install.sh
#
# What it does:
#   1. Checks for Python 3.10+
#   2. Installs python-can and pyserial via pip (upgrades if missing)
#   3. Installs tkinter if missing (best-effort on Debian/Ubuntu)
#   4. Creates a desktop launcher (.desktop on Linux, .command on macOS)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="BMW E90 Diagnostics"
GUI_SCRIPT="$SCRIPT_DIR/bmw_e90_gui.py"
ICON="$SCRIPT_DIR/icon.png"

# Colour helpers
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}   BMW E90 320i N46B20B – ECU Diagnostics Installer  ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ---------------------------------------------------------------------------
# 1. Find Python 3.10+
# ---------------------------------------------------------------------------
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
        if [[ "$ver" == "True" ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    error "Python 3.10 or higher is required but was not found."
    error "Install it from https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$("$PYTHON" --version 2>&1)
success "Found $PY_VERSION at $(command -v "$PYTHON")"

# ---------------------------------------------------------------------------
# 2. Install Python packages
# ---------------------------------------------------------------------------
info "Installing / verifying Python packages…"

PACKAGES=("python-can>=4.2.0" "pyserial>=3.5")

for pkg in "${PACKAGES[@]}"; do
    pkg_name="${pkg%%[>=<]*}"
    if "$PYTHON" -c "import importlib.util; assert importlib.util.find_spec('${pkg_name//-/_}') or importlib.util.find_spec('${pkg_name}')" &>/dev/null; then
        success "Package '${pkg_name}' already installed."
    else
        info "Installing '${pkg}'…"
        "$PYTHON" -m pip install "$pkg" --quiet --upgrade
        success "Installed '${pkg}'."
    fi
done

# Verify explicitly
"$PYTHON" -m pip install python-can pyserial --quiet --upgrade
success "All Python packages installed."

# ---------------------------------------------------------------------------
# 3. Ensure tkinter is available
# ---------------------------------------------------------------------------
if ! "$PYTHON" -c "import tkinter" &>/dev/null; then
    warn "tkinter not found – attempting to install…"
    OS="$(uname -s)"
    if [[ "$OS" == "Linux" ]]; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y python3-tk 2>/dev/null && success "Installed python3-tk." \
                || warn "Could not install python3-tk automatically. Please run: sudo apt-get install python3-tk"
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3-tkinter 2>/dev/null && success "Installed python3-tkinter." \
                || warn "Could not install automatically. Please run: sudo dnf install python3-tkinter"
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm tk 2>/dev/null && success "Installed tk." \
                || warn "Could not install automatically. Please run: sudo pacman -S tk"
        else
            warn "Unknown package manager. Please install python3-tk manually."
        fi
    elif [[ "$OS" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install python-tk 2>/dev/null && success "Installed python-tk via Homebrew." \
                || warn "Could not install automatically. Please run: brew install python-tk"
        else
            warn "Homebrew not found. Install tkinter via: brew install python-tk"
        fi
    fi
else
    success "tkinter is available."
fi

# ---------------------------------------------------------------------------
# 4. Create desktop launcher
# ---------------------------------------------------------------------------
OS="$(uname -s)"

if [[ "$OS" == "Linux" ]]; then
    # XDG desktop entry
    DESKTOP_DIR="$HOME/Desktop"
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR" "$APPS_DIR"

    DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=BMW E90 N46B20B ECU Diagnostics Dashboard
Exec=$PYTHON $GUI_SCRIPT --demo
Icon=$ICON
Terminal=false
Categories=Utility;Automotive;
StartupWMClass=BmwDiagGUI
"

    DESKTOP_FILE="$DESKTOP_DIR/bmw-e90-diagnostics.desktop"
    echo "$DESKTOP_ENTRY" > "$DESKTOP_FILE"
    chmod +x "$DESKTOP_FILE"
    # Also install to applications menu
    cp "$DESKTOP_FILE" "$APPS_DIR/bmw-e90-diagnostics.desktop"

    # Trust the launcher on GNOME if gio is available
    if command -v gio &>/dev/null; then
        gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    fi

    success "Desktop shortcut created: $DESKTOP_FILE"
    info "To connect to a real K+DCAN cable, edit the shortcut and remove '--demo'."

elif [[ "$OS" == "Darwin" ]]; then
    # macOS .command file (double-clickable shell script)
    DESKTOP_DIR="$HOME/Desktop"
    LAUNCHER="$DESKTOP_DIR/BMW E90 Diagnostics.command"

    cat > "$LAUNCHER" <<MACSCRIPT
#!/bin/bash
cd "$SCRIPT_DIR"
$PYTHON "$GUI_SCRIPT" "\$@"
MACSCRIPT
    chmod +x "$LAUNCHER"
    success "Desktop launcher created: $LAUNCHER"
    info "To connect to a real K+DCAN cable, run: $PYTHON $GUI_SCRIPT --interface kdcan"

else
    warn "Unsupported OS '$OS'. Desktop shortcut not created."
    info "Run the GUI manually with: $PYTHON $GUI_SCRIPT --demo"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Installation complete!                              ║${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║  Launch GUI:  $PYTHON bmw_e90_gui.py --demo         ║${NC}"
echo -e "${GREEN}║  CLI tool:    $PYTHON bmw_e90_diagnostics.py --demo ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
