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
echo "║          📱 ربات پیشرفته رفرال و دعوت ایرانسل‌من                   ║"
echo "║       Irancell Referral Bot (Pyrogram MTProto / Split-Route)      ║"
echo "║           Author: Mohammad Yousef (@EINDRAL)                      ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Python Check
echo -e "${BLUE}[1/5] بررسی پایتون سیستم...${NC}"
if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    echo -e "${GREEN}✓ پایتون نسخه $PY_VER یافت شد.${NC}"
else
    echo -e "${RED}✗ پایتون ۳ یافت نشد! در حال نصب...${NC}"
    if command -v apt-get &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip curl gcc
    elif command -v pacman &>/dev/null; then
        pacman -Sy --noconfirm --needed python python-pip curl gcc
    fi
fi

# 2. Virtual Environment
echo -e "${BLUE}[2/5] راه‌اندازی محیط ایزوله پایتون (venv)...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv || {
        echo -e "${RED}✗ خطا در ساخت venv. لطفاً بسته python3-venv را نصب کنید.${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ محیط مجازی با موفقیت در .venv ساخته شد.${NC}"
else
    echo -e "${GREEN}✓ محیط مجازی موجود است.${NC}"
fi

VENV_PY="$SCRIPT_DIR/.venv/bin/python"

# 3. Dependencies
echo -e "${BLUE}[3/5] نصب و بررسی نیازمندی‌ها از requirements.txt...${NC}"
"$VENV_PY" -m pip install --upgrade pip -q >/dev/null 2>&1 || true
"$VENV_PY" -m pip install -r requirements.txt -q
echo -e "${GREEN}✓ تمام وابستگی‌ها با موفقیت نصب شدند.${NC}"

# 4. Interactive Configuration (.env) & Proxy Checker
echo -e "${BLUE}[4/5] پیکربندی و بررسی هوشمند سلامت شبکه (.env)...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}فایل تنظیمات یافت نشد. لطفاً اطلاعات ربات را وارد کنید:${NC}\n"
    
    # Bot Token Validation
    while true; do
        read -rp "👉 توکن ربات تلگرام (از @BotFather): " BOT_TOKEN
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[a-zA-Z0-9_-]+$ ]]; then
            break
        else
            echo -e "${RED}✗ فرمت توکن نامعتبر است. نمونه صحیح: 123456789:ABCdefGhI...${NC}"
        fi
    done

    # Numeric Admin ID Validation
    while true; do
        read -rp "👉 آیدی عددی ادمین تلگرام (از @userinfobot): " ADMIN_ID
        if [[ "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
            break
        else
            echo -e "${RED}✗ آیدی ادمین باید صرفاً یک عدد باشد (مثلاً 1429926943).${NC}"
        fi
    done

    # Proxy / V2Ray Config with Live Health Checking
    echo -e "\n${CYAN}🌐 تنظیم پروکسی تلگرام (مخصوص سرورهای داخل ایران):${NC}"
    echo -e "می‌توانید یکی از موارد زیر را وارد کنید:"
    echo -e " • لینک V2Ray (VLESS / VMess / Trojan / Shadowsocks)"
    echo -e " • آدرس پروکسی (socks5://127.0.0.1:1080 یا http://...)"
    echo -e " • اینتر خالی (اتصال مستقیم - اگر سرور شما فیلتر نیست)"

    TELEGRAM_PROXY=""
    while true; do
        read -rp "👉 پروکسی یا لینک کانفیگ را وارد کنید: " PROXY_INPUT
        PROXY_INPUT=$(echo "$PROXY_INPUT" | xargs)

        # If user entered a V2Ray link, ensure Xray is available
        if [[ "$PROXY_INPUT" =~ ^(vless|vmess|trojan|ss):// ]]; then
            if ! command -v xray &>/dev/null && [ ! -f "/usr/local/bin/xray" ] && [ ! -f "$SCRIPT_DIR/bin/xray" ]; then
                echo -e "${YELLOW}[!] کانفیگ V2Ray شناسایی شد اما هسته Xray نصب نیست.${NC}"
                echo -e "${BLUE}در حال دانلود و نصب هسته رسمی Xray...${NC}"
                bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install >/dev/null 2>&1 || true
            fi
        fi

        echo -e "${BLUE}⏳ در حال بررسی و تست اتصال به دیتاسنترهای تلگرام...${NC}"
        CHECK_OUT=$("$VENV_PY" proxy_manager.py --check "$PROXY_INPUT" 2>&1 || true)
        
        if echo "$CHECK_OUT" | grep -q "SUCCESS"; then
            REASON=$(echo "$CHECK_OUT" | sed 's/SUCCESS: //')
            echo -e "${GREEN}✓ ${REASON}${NC}"
            TELEGRAM_PROXY="$PROXY_INPUT"
            break
        else
            ERR=$(echo "$CHECK_OUT" | sed 's/FAILED: //')
            echo -e "${RED}✗ خطا در اتصال به تلگرام: ${ERR}${NC}"
            read -rp "آیا مایلید کانفیگ دیگری وارد کنید؟ [Y/n]: " RETRY_CHOICE
            RETRY_CHOICE=${RETRY_CHOICE:-Y}
            if [[ "$RETRY_CHOICE" =~ ^[Nn] ]]; then
                TELEGRAM_PROXY="$PROXY_INPUT"
                echo -e "${YELLOW}کانفیگ با وجود خطا ذخیره شد.${NC}"
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
    echo -e "\n${GREEN}✓ فایل .env با موفقیت ایجاد و ذخیره شد!${NC}"
else
    echo -e "${GREEN}✓ فایل .env از قبل موجود است.${NC}"
fi

# 5. Launch Option
echo -e "\n${BLUE}[5/5] نحوه اجرای ربات:${NC}"
echo "1) نصب و فعال‌سازی به صورت سرویس دائمی (systemd - پیشنهادی برای سرور)"
echo "2) اجرای مستقیم در ترمینال (Foreground / مشاهده لاگ زنده)"
echo "3) اجرای در پس‌زمینه (nohup)"
echo "4) خروج از نصب"
read -rp "گزینه مورد نظر را انتخاب کنید [1-4] (پیش‌فرض 1): " LAUNCH_CHOICE
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
            echo -e "\n${GREEN}✓ سرویس irancell-bot فعال شد و ۲۴ ساعته در پس‌زمینه اجرا می‌شود.${NC}"
            echo -e " • وضعیت سرویس: ${YELLOW}systemctl status irancell-bot.service${NC}"
            echo -e " • مشاهده لاگ زنده: ${YELLOW}journalctl -u irancell-bot.service -f${NC}"
        else
            echo -e "${YELLOW}توجه: برای ایجاد سرویس systemd دسترسی root لازم است. ربات با nohup اجرا می‌شود.${NC}"
            nohup "$VENV_PY" bot.py > bot.log 2>&1 &
            echo -e "${GREEN}✓ ربات در پس‌زمینه اجرا شد (PID: $!). لاگ‌ها در bot.log ذخیره می‌شوند.${NC}"
        fi
        ;;
    2)
        echo -e "${GREEN}در حال اجرای ربات... برای توقف کلیدهای Ctrl+C را بزنید.${NC}"
        "$VENV_PY" bot.py
        ;;
    3)
        nohup "$VENV_PY" bot.py > bot.log 2>&1 &
        echo -e "${GREEN}✓ ربات در پس‌زمینه اجرا شد (PID: $!).${NC}"
        echo -e "برای مشاهده لاگ‌ها: ${YELLOW}tail -f bot.log${NC}"
        ;;
    *)
        echo -e "${YELLOW}نصب به اتمام رسید. هر زمان مایل بودید می‌توانید با دستور زیر ربات را اجرا کنید:${NC}"
        echo "  $VENV_PY bot.py"
        ;;
esac
