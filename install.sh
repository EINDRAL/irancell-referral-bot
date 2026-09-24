#!/usr/bin/env bash
# ==============================================================================
# Irancell Referral Bot - Automated Installer for Linux / Iran VPS
# Author: Mohammad Yousef (@EINDRAL)
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}====================================================${NC}"
echo -e "${GREEN}   🤖 ربات رفرال و دعوت ایرانسل‌من (Irancell Inviter)   ${NC}"
echo -e "${GREEN}   نصب‌کننده خودکار برای سرور لینوکس ایران          ${NC}"
echo -e "${BLUE}====================================================${NC}\n"

# 1. Root / Privileges Check
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️ توجه: برای ایجاد سرویس systemd و نصب پکیج‌ها، دسترسی root پیشنهاد می‌شود.${NC}"
fi

# 2. Package Manager & Dependencies
echo -e "${BLUE}[1/5] بررسی و نصب پیش‌نیازهای سیستمی...${NC}"
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip curl gcc >/dev/null 2>&1
elif command -v pacman &>/dev/null; then
    pacman -Sy --noconfirm --needed python python-pip curl gcc >/dev/null 2>&1
elif command -v dnf &>/dev/null; then
    dnf install -y python3 python3-pip curl gcc >/dev/null 2>&1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 3. Virtual Environment
echo -e "${BLUE}[2/5] ایجاد محیط ایزوله پایتون (venv)...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# 4. Configuration (.env)
echo -e "${BLUE}[3/5] پیکربندی متغیرهای محیطی (.env)...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}لطفاً اطلاعات زیر را با دقت وارد کنید:${NC}"
    read -rp "🔑 توکن ربات تلگرام (از @BotFather): " BOT_TOKEN
    read -rp "👤 عددی آیدی عددی ادمین تلگرام (از @userinfobot): " ADMIN_ID
    
    echo -e "\n${YELLOW}🌐 تنظیم پروکسی تلگرام (مخصوص سرورهای ایران):${NC}"
    echo -e "می‌توانید یکی از فرمت‌های زیر را وارد کنید:"
    echo -e " • SOCKS5: socks5://127.0.0.1:1080"
    echo -e " • V2Ray VLESS: vless://uuid@host:port?security=reality..."
    echo -e " • V2Ray VMess: vmess://eyJhZGQiOi..."
    echo -e " • Trojan:      trojan://pass@host:port..."
    echo -e " • Shadowsocks: ss://base64..."
    read -rp "پروکسی یا کانفیگ را وارد کنید (اگر نیاز ندارید اینتر بزنید): " TELEGRAM_PROXY

    cat <<EOF > .env
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
API_ID=2040
API_HASH=b18441a1ff607e10a989891a5462e627
TELEGRAM_PROXY=$TELEGRAM_PROXY
EOF
    echo -e "${GREEN}✅ فایل .env با موفقیت ایجاد شد.${NC}"
else
    echo -e "${GREEN}فایل .env از قبل موجود است.${NC}"
fi

# 5. Check if Xray is needed for V2Ray links
PROXY_VAL=$(grep "^TELEGRAM_PROXY=" .env | cut -d '=' -f2- | tr -d ' "')
if [[ "$PROXY_VAL" =~ ^(vless|vmess|trojan|ss):// ]]; then
    if ! command -v xray &>/dev/null && [ ! -f "/usr/local/bin/xray" ]; then
        echo -e "${YELLOW}[!] کانفیگ V2Ray شناسایی شد اما هسته Xray نصب نیست.${NC}"
        echo -e "${BLUE}در حال دانلود و نصب خودکار Xray-core...${NC}"
        bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install >/dev/null 2>&1 || true
        if command -v xray &>/dev/null; then
            echo -e "${GREEN}✅ هسته Xray با موفقیت نصب شد.${NC}"
        else
            echo -e "${YELLOW}⚠️ نتوانستیم خودکار نصب کنیم؛ لطفاً دستی با دستور زیر نصب کنید:${NC}"
            echo -e "bash -c \"\$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)\" @ install"
        fi
    fi
fi

# 6. Systemd Service Creation
if [ "$EUID" -eq 0 ]; then
    echo -e "${BLUE}[4/5] ساخت سرویس دائمی systemd...${NC}"
    SERVICE_FILE="/etc/systemd/system/irancell-bot.service"
    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Irancell Referral Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/bot.py
Restart=always
RestartSec=5
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable irancell-bot.service >/dev/null 2>&1
    systemctl restart irancell-bot.service
    echo -e "${GREEN}✅ سرویس irancell-bot با موفقیت فعال و اجرا شد.${NC}"
else
    echo -e "${YELLOW}اجرا بدون روت: برای اجرا در پس‌زمینه می‌توانید از tmux یا nohup استفاده کنید:${NC}"
    echo -e "nohup $PROJECT_DIR/.venv/bin/python $PROJECT_DIR/bot.py > bot.log 2>&1 &"
fi

echo -e "\n${BLUE}====================================================${NC}"
echo -e "${GREEN}🎉 نصب با موفقیت پایان یافت!${NC}"
echo -e "برای مدیریت ربات می‌توانید دستورات زیر را استفاده کنید:"
echo -e " • بررسی وضعیت: ${YELLOW}systemctl status irancell-bot.service${NC}"
echo -e " • مشاهده لاگ‌ها: ${YELLOW}journalctl -u irancell-bot.service -f${NC}"
echo -e " • ری‌استارت:   ${YELLOW}systemctl restart irancell-bot.service${NC}"
echo -e "${BLUE}====================================================${NC}"
