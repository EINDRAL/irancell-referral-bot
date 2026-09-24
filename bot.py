import os
import sys
import time
import asyncio
import logging
import tempfile
from email.utils import parsedate_to_datetime
import urllib.request
from pathlib import Path
from dotenv import load_dotenv
import pyrogram.session.internals.msg_id as msg_id_mod
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)

import database as db
import proxy_manager
from irancell_client import IrancellClient, generate_random_phone

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("IrancellBot")

def sync_telegram_time_skew():
    """Compensates for local RTC / clock skew against Telegram server time without modifying system settings."""
    skew = 0
    try:
        req = urllib.request.Request("https://api.telegram.org", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as r:
            date_str = r.headers.get("Date")
            if date_str:
                server_time = parsedate_to_datetime(date_str).timestamp()
                skew = time.time() - server_time
                logger.info(f"Telegram server sync: skew is {skew:.1f}s")
    except Exception as e:
        logger.warning(f"Could not calculate clock skew via HTTP: {e}")

    if abs(skew) > 10:
        def patched_new(cls):
            now = int(time.time() - skew)
            cls.offset = (cls.offset + 4) if now == cls.last_time else 0
            msg_id = (now * 2 ** 32) + cls.offset
            cls.last_time = now
            return msg_id

        msg_id_mod.MsgId.__new__ = patched_new
        logger.info(f"Applied Pyrogram MsgId time skew correction of {skew:.1f}s.")

# Apply clock skew compensation if needed
sync_telegram_time_skew()

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "2040"))
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1429926943"))

USE_IPV6 = os.getenv("USE_IPV6", "1") == "1"

# Proxy configuration (supports SOCKS5, HTTP, and V2Ray: VLESS / VMess / Trojan / Shadowsocks)
raw_proxy = os.getenv("TELEGRAM_PROXY", "").strip()
if not raw_proxy and os.getenv("USE_PROXY", "0") == "1":
    p_host = os.getenv("PROXY_HOST", "127.0.0.1")
    p_port = os.getenv("PROXY_PORT", "1085")
    raw_proxy = f"socks5://{p_host}:{p_port}"

proxy_dict = proxy_manager.setup_telegram_proxy(raw_proxy)

if not BOT_TOKEN:
    logger.warning("BOT_TOKEN is not set in .env! Please create .env first.")

# Initialize database
db.init_db()

app = Client(
    name="irancell_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN or "DUMMY_TOKEN",
    workdir=str(Path(__file__).resolve().parent),
    proxy=proxy_dict,
    ipv6=USE_IPV6
)

# User state storage for text inputs
USER_STATES = {}
WORKER_TASK: asyncio.Task = None

async def safe_answer(query: CallbackQuery, *args, **kwargs):
    try:
        await query.answer(*args, **kwargs)
    except Exception:
        pass

def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Returns the persistent bottom keyboard."""
    return ReplyKeyboardMarkup(
        [
            ["⚡️ کنترل ربات (روشن/خاموش)", "📊 وضعیت و آمار"],
            ["👤 مشخصات خط", "📜 آخرین شماره‌ها"],
            ["📥 خروجی لیست شماره‌ها"],
            ["🔑 تنظیم توکن", "⏱ تنظیم تایمر"]
        ],
        resize_keyboard=True
    )

def get_toggle_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline button specifically for toggling start/stop in-place."""
    is_running = db.get_setting("is_running", "0") == "1"
    status_btn = (
        InlineKeyboardButton("⏸ توقف عملیات", callback_data="toggle_worker")
        if is_running
        else InlineKeyboardButton("🚀 شروع عملیات", callback_data="toggle_worker")
    )
    return InlineKeyboardMarkup([[status_btn]])

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return get_reply_keyboard()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def referral_worker():
    """Background asynchronous task that executes referral invitations safely."""
    logger.info("Background referral worker started.")
    consecutive_net_errors = 0
    consecutive_rate_limits = 0

    while True:
        try:
            if db.get_setting("is_running", "0") != "1":
                await asyncio.sleep(2)
                continue

            token = db.get_setting("token", "")
            if not token:
                db.set_setting("is_running", "0")
                await app.send_message(
                    ADMIN_ID,
                    "⚠️ **توکن ایرانسل تنظیم نشده است!**\nلطفاً از منوی زیر ابتدا توکن حساب خود را ثبت کنید.",
                    reply_markup=get_main_keyboard()
                )
                await asyncio.sleep(3)
                continue

            client = IrancellClient(token)
            delay = db.get_delay()
            allowed_prefixes = db.get_prefixes()

            # Find a non-duplicate candidate phone
            candidate = None
            for _ in range(20):
                phone = generate_random_phone(allowed_prefixes=allowed_prefixes)
                if not db.is_phone_sent(phone):
                    candidate = phone
                    break

            if not candidate:
                await asyncio.sleep(2)
                continue

            success, msg, status_code = await client.invite_friend(candidate)

            if success:
                consecutive_net_errors = 0
                consecutive_rate_limits = 0
                db.record_sent(candidate, "success")
                logger.info(f"Invite sent successfully to 0{candidate}. Waiting {delay}s...")
                
                # Silent mode: No spam message to Telegram on every invite!
                
                # Cooldown between successful SMS invites
                for _ in range(delay):
                    if db.get_setting("is_running", "0") != "1":
                        break
                    await asyncio.sleep(1)

            elif status_code == 401:
                logger.warning("Token expired (401). Pausing worker.")
                db.set_setting("is_running", "0")
                try:
                    await app.send_message(
                        ADMIN_ID,
                        "🚨 **هشدار مهم: توکن ایرانسل‌من منقضی شد!**\n\n"
                        "عملیات ارسال متوقف گردید. لطفاً از طریق دکمه «🔑 تنظیم توکن» توکن جدید را ثبت کنید.",
                        reply_markup=get_main_keyboard()
                    )
                except Exception:
                    pass
                await asyncio.sleep(5)

            elif status_code == 429:
                consecutive_rate_limits += 1
                logger.warning(f"Rate limited / Irancell cooldown ({consecutive_rate_limits}). Waiting 65s...")
                if consecutive_rate_limits == 3:
                    try:
                        await app.send_message(
                            ADMIN_ID,
                            "⚠️ **هشدار محدودیت ایرانسل (Rate Limit):**\n"
                            "ایرانسل محدودیت سرعت اعمال کرده است. ربات در حال خنک‌سازی خودکار است..."
                        )
                    except Exception:
                        pass
                await asyncio.sleep(65)

            elif status_code == -1:
                consecutive_net_errors += 1
                logger.warning(f"Network error with Irancell ({consecutive_net_errors}/5): {msg}")
                if consecutive_net_errors == 5:
                    try:
                        await app.send_message(
                            ADMIN_ID,
                            f"⚠️ **هشدار اتصال به شبکه ایرانسل:**\n\n"
                            f"۵ تلاش متوالی با خطای شبکه مواجه شد:\n`{msg}`\n\n"
                            "ربات متوقف نشده و همچنان با وقفه ۲۰ ثانیه‌ای در حال تلاش مجدد است."
                        )
                    except Exception:
                        pass
                await asyncio.sleep(20)

            else:
                # Number was ineligible or already invited; fast scan next random number
                consecutive_net_errors = 0
                await asyncio.sleep(0.3)

        except asyncio.CancelledError:
            logger.info("Worker task cancelled.")
            break
        except Exception as e:
            logger.error(f"Worker exception: {e}")
            await asyncio.sleep(5)

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔️ این ربات به صورت اختصاصی برای مدیریت رفرال ایرانسل تنظیم شده است.")
        return

    USER_STATES.pop(message.from_user.id, None)
    text = (
        "🧡 **ربات هوشمند رفرال ایرانسل‌من**\n\n"
        "با این ربات می‌توانید به صورت خودکار و با رعایت دقیق لیمیت‌های امنیتی، "
        "دعوت‌نامه‌های ایرانسل‌من را ارسال کرده و جوایز اینترنت هدیه را دریافت کنید.\n\n"
        "⚙️ **تنظیمات فعلی:**\n"
        f"• وضعیت: {'🟢 در حال ارسال' if db.get_setting('is_running') == '1' else '🔴 متوقف'}\n"
        f"• تایمر بین ارسال‌ها: **{db.get_delay()} ثانیه** (حداقل ۷۵ ثانیه)\n"
        f"• توکن: {'✅ تنظیم شده' if db.get_setting('token') else '❌ تنظیم نشده'}\n\n"
        "👇 **از منوی زیر برای کنترل و بررسی ربات استفاده کنید:**"
    )
    await message.reply(text, reply_markup=get_reply_keyboard())

@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await safe_answer(query, "دسترسی مجاز نیست.", show_alert=True)
        return

    data = query.data

    if data in ("toggle_worker", "start_worker", "stop_worker"):
        is_running = db.get_setting("is_running", "0") == "1"
        if data == "start_worker" or (data == "toggle_worker" and not is_running):
            if not db.get_setting("token"):
                await safe_answer(query, "ابتدا باید توکن حساب ایرانسل را تنظیم کنید!", show_alert=True)
                return
            db.set_setting("is_running", "1")
            await safe_answer(query, "🚀 عملیات ارسال فعال شد.", show_alert=False)
        else:
            db.set_setting("is_running", "0")
            await safe_answer(query, "⏸ عملیات ارسال متوقف شد.", show_alert=False)
            
        new_running = db.get_setting("is_running", "0") == "1"
        status_str = "🟢 در حال ارسال" if new_running else "🔴 متوقف"
        try:
            await query.message.edit_text(
                f"⚡️ **مدیریت وضعیت ربات:**\n\n"
                f"• وضعیت فعلی: **{status_str}**\n\n"
                "برای تغییر وضعیت، روی کلید زیر بزنید:",
                reply_markup=get_toggle_inline_keyboard()
            )
        except Exception:
            pass

    elif data == "btn_set_token":
        USER_STATES[query.from_user.id] = "WAITING_FOR_TOKEN"
        await query.message.reply(
            "🔑 **لطفاً توکن Authorization ایرانسل‌من را ارسال کنید:**\n\n"
            "*(برای لغو، دستور /start را ارسال کنید)*"
        )
        await safe_answer(query)

    elif data == "btn_set_delay":
        USER_STATES[query.from_user.id] = "WAITING_FOR_DELAY"
        cur_delay = db.get_delay()
        await query.message.reply(
            f"⏱ **تنظیم زمان وقفه بین هر ارسال:**\n\n"
            f"• زمان فعلی: **{cur_delay} ثانیه**\n"
            f"• حداقل مجاز: **۷۵ ثانیه** (جهت جلوگیری از لیمیت)\n"
            f"• مقدار پیشنهادی: **۱۲۰ ثانیه (۲ دقیقه)**\n\n"
            "لطفاً عدد جدید را به ثانیه بفرستید (مثلاً: `120`):"
        )
        await safe_answer(query)

    elif data == "btn_stats":
        stats = db.get_stats()
        text = (
            "📊 **آمار و وضعیت سیستم:**\n\n"
            f"• مجموع دعوت‌های موفق: **{stats['total_sent']}** عدد\n"
            f"• ارسال‌های موفق امروز: **{stats['today_sent']}** عدد\n"
            f"• وقفه بین ارسال‌ها: **{db.get_delay()}** ثانیه\n"
            f"• وضعیت پروسس: {'🟢 فعال' if db.get_setting('is_running') == '1' else '🔴 غیرفعال'}"
        )
        await query.message.reply(text, reply_markup=get_reply_keyboard())
        await safe_answer(query)

    elif data == "btn_profile":
        token = db.get_setting("token", "")
        if not token:
            await safe_answer(query, "توکن ایرانسل تنظیم نشده است!", show_alert=True)
            return
        await safe_answer(query, "در حال استعلام از ایرانسل...", show_alert=False)
        c = IrancellClient(token)
        ok, prof = await c.get_profile()
        if ok and isinstance(prof, dict):
            fn = prof.get("first_name") or ""
            ln = prof.get("last_name") or ""
            num = prof.get("contact_number") or ""
            ctype = "اعتباری" if prof.get("customer_type") == "prepaid" else "دائمی" if prof.get("customer_type") == "postpaid" else (prof.get("customer_type") or "-")
            status = "فعال 🟢" if prof.get("operation_status") == "active" else (prof.get("operation_status") or "-")
            act_date = prof.get("activation_date") or "-"
            text = (
                "👤 **مشخصات سیم‌کارت متصل:**\n\n"
                f"• نام و نام خانوادگی: **{fn} {ln}**\n"
                f"• شماره سیم‌کارت: `{num}`\n"
                f"• نوع خط: **{ctype}**\n"
                f"• وضعیت: **{status}**\n"
                f"• تاریخ فعال‌سازی: `{act_date}`"
            )
            await query.message.reply(text, reply_markup=get_reply_keyboard())
        else:
            err = prof if isinstance(prof, str) else "خطا در دریافت اطلاعات"
            await query.message.reply(
                f"⚠️ **عدم دریافت مشخصات:** {err}",
                reply_markup=get_reply_keyboard()
            )

    elif data == "btn_recent":
        stats = db.get_stats()
        recent = stats.get("recent", [])
        if not recent:
            await safe_answer(query, "هنوز شماره‌ای با موفقیت ارسال نشده است.", show_alert=True)
            return
        lines = ["📜 آخرین شماره‌های ارسالی:"]
        for p, dt in recent[:5]:
            time_part = dt.split()[1] if " " in dt else dt
            lines.append(f"• 0{p} ({time_part})")
        alert_text = "\n".join(lines)
        await safe_answer(query, alert_text, show_alert=True)

@app.on_message(filters.text & filters.private)
async def text_input_handler(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return

    raw_text = (message.text or "").strip()
    state = USER_STATES.get(message.from_user.id)

    # Permanent reply keyboard menu actions
    if raw_text == "⚡️ کنترل ربات (روشن/خاموش)":
        USER_STATES.pop(message.from_user.id, None)
        is_running = db.get_setting("is_running", "0") == "1"
        status_str = "🟢 در حال ارسال" if is_running else "🔴 متوقف"
        await message.reply(
            f"⚡️ **مدیریت وضعیت ربات:**\n\n"
            f"• وضعیت فعلی: **{status_str}**\n\n"
            "برای تغییر وضعیت، روی کلید زیر بزنید:",
            reply_markup=get_toggle_inline_keyboard()
        )
        return

    elif raw_text == "📊 وضعیت و آمار":
        USER_STATES.pop(message.from_user.id, None)
        stats = db.get_stats()
        status_str = "🟢 فعال" if db.get_setting("is_running") == "1" else "🔴 غیرفعال"
        rep = (
            "📊 **آمار و وضعیت سیستم:**\n\n"
            f"• مجموع دعوت‌های موفق: **{stats['total_sent']}** عدد\n"
            f"• ارسال‌های موفق امروز: **{stats['today_sent']}** عدد\n"
            f"• وقفه بین ارسال‌ها: **{db.get_delay()}** ثانیه\n"
            f"• وضعیت پروسس: {status_str}"
        )
        await message.reply(rep, reply_markup=get_reply_keyboard())
        return

    elif raw_text == "👤 مشخصات خط":
        USER_STATES.pop(message.from_user.id, None)
        token = db.get_setting("token", "")
        if not token:
            await message.reply(
                "⚠️ **توکن ایرانسل تنظیم نشده است!**\nلطفاً از کلید «🔑 تنظیم توکن» استفاده کنید.",
                reply_markup=get_reply_keyboard()
            )
            return
        wait_msg = await message.reply("⏳ در حال استعلام از ایرانسل...")
        c = IrancellClient(token)
        ok, prof = await c.get_profile()
        if ok and isinstance(prof, dict):
            fn = prof.get("first_name") or ""
            ln = prof.get("last_name") or ""
            num = prof.get("contact_number") or ""
            ctype = "اعتباری" if prof.get("customer_type") == "prepaid" else "دائمی" if prof.get("customer_type") == "postpaid" else (prof.get("customer_type") or "-")
            status = "فعال 🟢" if prof.get("operation_status") == "active" else (prof.get("operation_status") or "-")
            act_date = prof.get("activation_date") or "-"
            rep = (
                "👤 **مشخصات سیم‌کارت متصل:**\n\n"
                f"• نام و نام خانوادگی: **{fn} {ln}**\n"
                f"• شماره سیم‌کارت: `{num}`\n"
                f"• نوع خط: **{ctype}**\n"
                f"• وضعیت: **{status}**\n"
                f"• تاریخ فعال‌سازی: `{act_date}`"
            )
            await wait_msg.edit_text(rep)
        else:
            err = prof if isinstance(prof, str) else "خطا در دریافت اطلاعات"
            await wait_msg.edit_text(f"⚠️ **عدم دریافت مشخصات:** {err}")
        return

    elif raw_text == "📜 آخرین شماره‌ها":
        USER_STATES.pop(message.from_user.id, None)
        stats = db.get_stats()
        recent = stats.get("recent", [])
        if not recent:
            await message.reply("هنوز شماره‌ای با موفقیت ارسال نشده است.", reply_markup=get_reply_keyboard())
            return
        lines = ["📜 **آخرین شماره‌های ارسالی:**\n"]
        for p, dt in recent:
            lines.append(f"• `0{p}` — {dt}")
        await message.reply("\n".join(lines), reply_markup=get_reply_keyboard())
        return

    elif raw_text == "🔑 تنظیم توکن":
        USER_STATES[message.from_user.id] = "WAITING_FOR_TOKEN"
        await message.reply(
            "🔑 **لطفاً توکن Authorization ایرانسل‌من را ارسال کنید:**\n\n"
            "*(برای لغو، دستور /start را ارسال کنید)*"
        )
        return

    elif raw_text == "⏱ تنظیم تایمر":
        USER_STATES[message.from_user.id] = "WAITING_FOR_DELAY"
        cur_delay = db.get_delay()
        await message.reply(
            f"⏱ **تنظیم زمان وقفه بین هر ارسال:**\n\n"
            f"• زمان فعلی: **{cur_delay} ثانیه**\n"
            f"• حداقل مجاز: **۷۵ ثانیه** (جهت جلوگیری از لیمیت)\n"
            f"• مقدار پیشنهادی: **۱۲۰ ثانیه (۲ دقیقه)**\n\n"
            "لطفاً عدد جدید را به ثانیه بفرستید (مثلاً: `120`):"
        )
        return

    elif raw_text == "📥 خروجی لیست شماره‌ها":
        USER_STATES.pop(message.from_user.id, None)
        all_records = db.get_all_sent_numbers()
        if not all_records:
            await message.reply("هنوز شماره‌ای با موفقیت ارسال نشده است.", reply_markup=get_reply_keyboard())
            return

        wait_m = await message.reply("⏳ در حال استخراج و ایجاد فایل خروجی...")
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write(f"=== لیست شماره‌های موفق ایرانسل ===\n")
            f.write(f"تعداد کل شماره‌ها: {len(all_records)}\n")
            f.write(f"تاریخ استخراج: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 40 + "\n\n")
            for num, dt in all_records:
                f.write(f"0{num}\t{dt}\n")
            tmp_path = f.name

        try:
            await app.send_document(
                chat_id=message.chat.id,
                document=tmp_path,
                file_name=f"irancell_referrals_{len(all_records)}.txt",
                caption=(
                    f"📁 **خروجی شماره‌های دعوت‌شده ایرانسل**\n\n"
                    f"• مجموع: **{len(all_records)}** شماره موفق\n"
                    f"• فرمت: فایل متنی (TXT)"
                ),
                reply_markup=get_reply_keyboard()
            )
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            await wait_m.delete()
        return

    # User input states
    if state == "WAITING_FOR_TOKEN":
        token = raw_text
        db.set_setting("token", token)
        USER_STATES.pop(message.from_user.id, None)

        c = IrancellClient(token)
        ok, prof = await c.get_profile()
        if ok and isinstance(prof, dict):
            fn = prof.get("first_name") or ""
            ln = prof.get("last_name") or ""
            num = prof.get("contact_number") or ""
            await message.reply(
                f"✅ **توکن ایرانسل‌من با موفقیت تایید و ذخیره شد.**\n\n"
                f"👤 خط: **{fn} {ln}** (`{num}`)\n"
                "اکنون می‌توانید عملیات را آغاز کنید.",
                reply_markup=get_reply_keyboard()
            )
        else:
            await message.reply(
                "✅ **توکن ایرانسل‌من با موفقیت ذخیره شد.**\nاکنون می‌توانید عملیات را آغاز کنید.",
                reply_markup=get_reply_keyboard()
            )

    elif state == "WAITING_FOR_DELAY":
        try:
            val = int(raw_text)
            saved_val = db.set_delay(val)
            USER_STATES.pop(message.from_user.id, None)
            notice = ""
            if val < 75:
                notice = "\n⚠️ *مقدار ورودی کمتر از ۷۵ ثانیه بود، به صورت خودکار روی حداقل مجاز (۷۵ ثانیه) تنظیم شد.*"
            await message.reply(
                f"✅ **تایمر وقفه روی {saved_val} ثانیه تنظیم شد.**{notice}",
                reply_markup=get_reply_keyboard()
            )
        except ValueError:
            await message.reply("❌ لطفاً فقط یک عدد معتبر به ثانیه وارد کنید (مثلاً `120`).")

@app.on_message(group=-1)
async def log_incoming(client: Client, message: Message):
    sender = message.from_user.id if message.from_user else "Unknown"
    logger.info(f"Incoming message from {sender}: {message.text}")
    message.continue_propagation()

async def start_bot():
    global WORKER_TASK
    logger.info("Starting Irancell Referral Bot...")
    await app.start()
    WORKER_TASK = asyncio.create_task(referral_worker())
    logger.info("Bot is running and ready for messages!")
    await idle()
    await app.stop()

def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not found in .env. Please configure .env first.")
        sys.exit(1)
    try:
        app.run(start_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")

if __name__ == "__main__":
    main()
