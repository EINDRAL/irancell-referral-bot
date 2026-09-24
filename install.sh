#!/usr/bin/env bash
# ==============================================================================
# 🚀 Irancell Referral Bot - One-Click Installer & Runner
# Fully Rootless/Root Compatible, Portable & Open-Source
# Author: Mohammad Yousef (@EINDRAL)
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║             📱 Irancell Referral & Inviter Bot                    ║"
echo "║          Telegram Bot with V2Ray Split-Routing Support            ║"
echo "║               Author: Mohammad Yousef (@EINDRAL)                  ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Python Check
echo -e "${BLUE}[1/5] Checking Python installation...${NC}"
if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    echo -e "${GREEN}✓ Found Python $PY_VER${NC}"
else
    echo -e "${RED}✗ Python 3 not found! Installing prerequisites...${NC}"
    if command -v apt-get &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip curl gcc
    elif command -v pacman &>/dev/null; then
        pacman -Sy --noconfirm --needed python python-pip curl gcc
    fi
fi

# 2. Virtual Environment
echo -e "${BLUE}[2/5] Setting up isolated Python virtual environment (.venv)...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv || {
        echo -e "${RED}✗ Failed to create venv. Make sure python3-venv is installed.${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Virtual environment created successfully under ./.venv${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists.${NC}"
fi

VENV_PY="$SCRIPT_DIR/.venv/bin/python"

# 3. Dependencies
echo -e "${BLUE}[3/5] Installing dependencies from requirements.txt...${NC}"
"$VENV_PY" -m pip install --upgrade pip -q >/dev/null 2>&1 || true
"$VENV_PY" -m pip install -r requirements.txt -q
echo -e "${GREEN}✓ All dependencies installed successfully.${NC}"

# 4. Interactive Configuration (.env) & Proxy Checker
echo -e "${BLUE}[4/5] Checking configuration (.env) & testing connectivity...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}No .env found. Let's configure your bot settings:${NC}\n"
    
    # Bot Token Validation
    while true; do
        read -rp "👉 Enter Telegram Bot Token (from @BotFather): " BOT_TOKEN
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[a-zA-Z0-9_-]+$ ]]; then
            break
        else
            echo -e "${RED}✗ Invalid bot token format. Example: 123456789:ABCdefGhI...${NC}"
        fi
    done

    # Numeric Admin ID Validation
    while true; do
        read -rp "👉 Enter Numeric Telegram Admin ID (from @userinfobot): " ADMIN_ID
        if [[ "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
            break
        else
            echo -e "${RED}✗ Admin ID must be numeric (e.g. 1429926943).${NC}"
        fi
    done

    # Proxy / V2Ray Config with Live Health Checking
    echo -e "\n${CYAN}🌐 Telegram Proxy Configuration (Required for Iran VPS):${NC}"
    echo -e "You can provide any of the following:"
    echo -e " • V2Ray Link (vless://, vmess://, trojan://, ss://)"
    echo -e " • Standard Proxy (socks5://127.0.0.1:1080 or http://...)"
    echo -e " • Press Enter for Direct Connection (if Telegram is not filtered on your server)"

    TELEGRAM_PROXY=""
    while true; do
        read -rp "👉 Enter proxy URL or V2Ray config link: " PROXY_INPUT
        PROXY_INPUT=$(echo "$PROXY_INPUT" | xargs)

        # If user entered a V2Ray link, ensure Xray is available
        if [[ "$PROXY_INPUT" =~ ^(vless|vmess|trojan|ss):// ]]; then
            if ! command -v xray &>/dev/null && [ ! -f "/usr/local/bin/xray" ] && [ ! -f "$SCRIPT_DIR/bin/xray" ]; then
                echo -e "${YELLOW}[!] V2Ray config detected but Xray-core is not installed.${NC}"
                echo -e "${BLUE}Downloading and installing official Xray-core...${NC}"
                bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install >/dev/null 2>&1 || true
            fi
        fi

        echo -e "${BLUE}⏳ Testing connection to Telegram Data Centers...${NC}"
        CHECK_OUT=$("$VENV_PY" proxy_manager.py --check "$PROXY_INPUT" 2>&1 || true)
        
        if echo "$CHECK_OUT" | grep -q "SUCCESS"; then
            REASON=$(echo "$CHECK_OUT" | sed 's/SUCCESS: //')
            echo -e "${GREEN}✓ ${REASON}${NC}"
            TELEGRAM_PROXY="$PROXY_INPUT"
            break
        else
            ERR=$(echo "$CHECK_OUT" | sed 's/FAILED: //')
            echo -e "${RED}✗ Connection failed: ${ERR}${NC}"
            read -rp "Would you like to try another proxy/config? [Y/n]: " RETRY_CHOICE
            RETRY_CHOICE=${RETRY_CHOICE:-Y}
            if [[ "$RETRY_CHOICE" =~ ^[Nn] ]]; then
                TELEGRAM_PROXY="$PROXY_INPUT"
                echo -e "${YELLOW}Warning: Proceeding with unverified proxy.${NC}"
                break
            fi
        fi
    done

    cat <<EOF > .env
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
API_ID=2040
API_HASH=b18441a1ff607e10a989891a5462e627
TELEGRAM_PROXY=$TELEGRAM_PROXY
EOF
    echo -e "\n${GREEN}✓ Configuration saved to .env successfully!${NC}"
else
    echo -e "${GREEN}✓ Existing .env configuration found.${NC}"
fi

# 5. Launch Option
echo -e "\n${BLUE}[5/5] Launch options:${NC}"
echo "1) Install & start as 24/7 background service (systemd - Recommended)"
echo "2) Run in foreground now (Interactive / Live logs)"
echo "3) Run in background with nohup"
echo "4) Exit setup"
read -rp "Select option [1-4] (Default: 1): " LAUNCH_CHOICE
LAUNCH_CHOICE=${LAUNCH_CHOICE:-1}

case "$LAUNCH_CHOICE" in
    1)
        if [ "$EUID" -eq 0 ]; then
            SERVICE_FILE="/etc/systemd/system/irancell-bot.service"
            cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Irancell Referral Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_PY $SCRIPT_DIR/bot.py
Restart=always
RestartSec=5
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
EOF
            systemctl daemon-reload
            systemctl enable irancell-bot.service >/dev/null 2>&1
            systemctl restart irancell-bot.service
            echo -e "\n${GREEN}✓ irancell-bot.service is active and running 24/7 in background.${NC}"
            echo -e " • Check status: ${YELLOW}systemctl status irancell-bot.service${NC}"
            echo -e " • Monitor logs: ${YELLOW}journalctl -u irancell-bot.service -f${NC}"
        else
            echo -e "${YELLOW}Note: Root privileges required for systemd. Starting with nohup instead...${NC}"
            nohup "$VENV_PY" bot.py > bot.log 2>&1 &
            echo -e "${GREEN}✓ Bot started in background (PID: $!). Logs written to bot.log${NC}"
        fi
        ;;
    2)
        echo -e "${GREEN}Starting bot in foreground... Press Ctrl+C to stop.${NC}"
        "$VENV_PY" bot.py
        ;;
    3)
        nohup "$VENV_PY" bot.py > bot.log 2>&1 &
        echo -e "${GREEN}✓ Bot started in background (PID: $!).${NC}"
        echo -e "Monitor logs anytime with: ${YELLOW}tail -f bot.log${NC}"
        ;;
    *)
        echo -e "${YELLOW}Setup complete. You can run the bot anytime using:${NC}"
        echo "  $VENV_PY bot.py"
        ;;
esac