# 📱 ربات پیشرفته رفرال و دعوت ایرانسل‌من (Irancell Referral Bot)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Pyrogram-v2.0-green?style=for-the-badge&logo=telegram" alt="Pyrogram">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License">
  <img src="https://img.shields.io/badge/Platform-Iran%20VPS-orange?style=for-the-badge&logo=linux" alt="Linux">
</p>

ربات هوشمند و کاملاً خودکار تلگرامی برای ارسال و ثبت دعوت‌نامه‌های طرح هدیه **ایرانسل‌من** به همراه مدیریت هوشمند اتصال شبکه، دور زدن محدودیت‌های تلگرام روی سرورهای داخلی و پشتیبانی مستقیم از انواع کانفیگ‌های **V2Ray**.

---

## 🌟 قابلیت‌های کلیدی

- ⚡️ **معماری تفکیک مسیر (Split Routing):** ارسال مستقیم درخواست‌های ایرانسل از آی‌پی تمیز سرور ایران + ارسال ترافیک تلگرام از پروکسی.
- 🛡 **پشتیبانی مستقیم از V2Ray:** بدون نیاز به نصب دستی پنل! کافی است لینک کانفیگ خود را بدهید:
  - `VLESS` (با پشتیبانی کامل از Reality, TLS, WS, gRPC)
  - `VMess`
  - `Trojan`
  - `Shadowsocks`
  - `SOCKS5` و `HTTP`
- 🔍 **چکر و اعتبارسنج زنده شبکه (Live Health Checker):** تست آنی پینگ و سلامت اتصال کانفیگ به سرورهای رسمی تلگرام در هنگام نصب با اعلام زمان تاخیر (Latency ms).
- 🎯 **پوشش ۱۰۰٪ پیش‌شماره‌های ایرانسل:** شامل تمام رنج‌های سراسری (`0930` تا `0939`، `0900` تا `0905` و `0941`).
- ⏱ **مدیریت وقفه و خنک‌سازی خودکار:** تنظیم هوشمند فاصله زمانی برای جلوگیری از خطای ۴۲۹ (Rate Limit) ایرانسل.
- 🚨 **سیستم هشدارهای هوشمند (Smart Alerts):** اطلاع‌رسانی فوری در صورت انقضای توکن ایرانسل (۴۰۱) یا قطعی شبکه.
- 📥 **خروجی شماره‌های موفق:** دریافت فایل متنی (`.txt`) شامل تاریخچه کامل تمام شماره‌های ثبت‌شده با یک کلیک.
- 👤 **استعلام زنده مشخصات سیم‌کارت:** مشاهده نام و نام خانوادگی، شماره و وضعیت سیم‌کارت متصل به توکن.
- 🗄 **دیتابیس ایزوله SQLite:** نگهداری بدون تداخل و بدون نیاز به نصب پایگاه‌داده‌های سنگین.

---

## 🚀 نصب و راه‌اندازی سریع (روی سرور لینوکس ایران)

فقط با اجرای یک دستور، تمام پیش‌نیازها، پایتون و سرویس دائم به صورت خودکار نصب و فعال می‌شود:

```bash
git clone https://github.com/EINDRAL/irancell-referral-bot.git
cd irancell-referral-bot
chmod +x install.sh
sudo ./install.sh
```

اسکریپت اطلاعات زیر را از شما درخواست می‌کند:
1. **توکن ربات تلگرام (BOT_TOKEN):** دریافت از [@BotFather](https://t.me/BotFather)
2. **آیدی عددی ادمین (ADMIN_ID):** دریافت از [@userinfobot](https://t.me/userinfobot)
3. **پروکسی یا کانفیگ V2Ray (اختیاری):** کپی کردن هر مدل لینک VLESS/VMess/Trojan/Socks5

---

## ⚙️ پیکربندی دستی (`.env`)

در صورتی که مایل به راه‌اندازی دستی هستید:

```env
# توکن ربات تلگرام
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# آیدی عددی اکانت تلگرام شما
ADMIN_ID=1429926943

# پروکسی برای اتصال به تلگرام از سرور ایران (یکی از فرمت‌های زیر):
# SOCKS5:
# TELEGRAM_PROXY=socks5://127.0.0.1:1080
# VLESS (Reality / WS):
# TELEGRAM_PROXY=vless://uuid@host:443?security=reality&sni=example.com...
# VMess:
# TELEGRAM_PROXY=vmess://eyJhZGQiOiIxLjIuMy40I...
TELEGRAM_PROXY=
```

سپس نیازمندی‌ها را نصب کرده و اجرا کنید:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

---

## 🛠 دستورات مدیریت سرویس

اگر ربات را با اسکریپت نصب کرده‌اید، به صورت سرویس `systemd` اجرا می‌شود:

```bash
# بررسی وضعیت
systemctl status irancell-bot.service

# مشاهده لاگ‌های زنده
journalctl -u irancell-bot.service -f

# ری‌استارت
systemctl restart irancell-bot.service

# توقف سرویس
systemctl stop irancell-bot.service
```

---

## 🙏 تقدیر، تشکر و منابع (Credits & Acknowledgements)

ایده و ساختار اولیه ارتباط با وب‌سرویس ایرانسل بر پایه کارهای ارزشمند توسعه‌دهنده گرامی **عرفان ([@NOMASKERFAN](https://github.com/NOMASKERFAN))** در پروژه‌های [pyrancell](https://github.com/NOMASKERFAN/pyrancell) و [Irancell_internet-Free](https://github.com/NOMASKERFAN/Irancell_internet-Free) شکل گرفته است.  
با احترام کامل و کسب اجازه از ایشان، این پروژه به عنوان یک نسخه پیشرفته با رابط کاربری کامل تلگرام، سیستم هوشمند ضد فیلتر و معماری تفکیک مسیر (Split-Routing) بازنویسی و توسعه یافته است. لطفاً جهت حمایت از ایشان، به ریپازیتوری‌های نام‌برده ستاره (⭐️) دهید.

---

## 📄 لایسنس

این پروژه تحت لایسنس [MIT](LICENSE) منتشر شده است و استفاده یا شخصی‌سازی آن با ذکر منبع آزاد است.

**Developer:** Mohammad Yousef Morovajnia ([@EINDRAL](https://github.com/EINDRAL))
