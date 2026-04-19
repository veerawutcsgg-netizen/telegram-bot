# -*- coding: utf-8 -*-
# pip install python-telegram-bot==21.5
import os, json, logging, threading, asyncio, re
from datetime import datetime
from typing import Dict, Any, Optional, List, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForumTopic
from telegram.ext import (
    Application, ApplicationBuilder, ContextTypes,
    CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ChatMemberHandler, filters
)

# ================== CONFIG ==================
TOKEN = os.getenv("TELEGRAM_TOKEN", "7503001560:AAEQy446AUdVSbtfLp1W0_PC1HzD4Ungd3E")
# กลุ่มซัพพอร์ต (Supergroup ที่เปิด Topics) ใช้เลขติดลบเท่านั้น
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "-1003040238418"))

# ช่องทางเซลส์ (username ไม่ต้องใส่ @)
SALES_USERNAME = os.getenv("SALES_USERNAME", "icggame")

if ADMIN_CHAT_ID >= 0:
    raise SystemExit("ADMIN_CHAT_ID ต้องเป็นเลขติดลบของ supergroup ที่เปิด Topics เท่านั้น")

# ================== LOG ==================
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("icg-bot")

# ================== STORAGE ==================
DATA_DIR = "data"; os.makedirs(DATA_DIR, exist_ok=True)
STATE_PATH = os.path.join(DATA_DIR, "state.json")
_lock = threading.Lock()

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH): return {"users": {}, "broadcast_chats": []}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "users" not in data: data["users"] = {}
            if "broadcast_chats" not in data: data["broadcast_chats"] = []
            return data
    except Exception:
        return {"users": {}, "broadcast_chats": []}

def save_state(state: Dict[str, Any]):
    with _lock:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

STATE = load_state()
STATE.setdefault("users", {})
STATE.setdefault("broadcast_chats", [])  # <- ที่นี่จะเก็บ chat id ของผู้ใช้/กลุ่มที่ใช้ส่ง broadcast

def ustate(uid: int) -> Dict[str, Any]:
    return STATE["users"].setdefault(str(uid), {"lang": "th", "selected_package": None, "log": []})

def set_lang(uid: int, lang: str):
    ustate(uid)["lang"] = "en" if lang == "en" else "th"; save_state(STATE)

def get_lang(uid: int) -> str:
    return ustate(uid).get("lang", "th")

def ulog(uid: int, text: str):
    s = ustate(uid); s["log"].append({"ts": _now(), "text": text}); save_state(STATE)

# ======== Broadcast chat list helpers ========
def _get_broadcast_set() -> Set[int]:
    try:
        return set(int(x) for x in STATE.get("broadcast_chats", []))
    except Exception:
        return set()

def _save_broadcast_set(s: Set[int]):
    STATE["broadcast_chats"] = [int(x) for x in sorted(s)]
    save_state(STATE)

def add_broadcast_chat(chat_id: int):
    s = _get_broadcast_set()
    if chat_id not in s:
        s.add(chat_id)
        _save_broadcast_set(s)
        log.info("Add broadcast chat_id=%s", chat_id)

def remove_broadcast_chat(chat_id: int):
    s = _get_broadcast_set()
    if chat_id in s:
        s.remove(chat_id)
        _save_broadcast_set(s)
        log.info("Remove broadcast chat_id=%s", chat_id)

# mapping ลูกค้า <-> topic
CUSTOMER_TO_TOPIC: Dict[int, int] = {}
TOPIC_TO_CUSTOMER: Dict[int, int] = {}

# ================== WEBSITE WHITELIST ==================
SITE_WHITELIST = {
    "FAFA88","FAFA138","FAFA678","FAFAS1788","FAFA365","FAFAS6668","FAFA456","FAFA567",
    "FAFA100","FAFA987","FAFA123","FAFA1X2","FAFA118","FAFA168","FAFA188","FAFA555",
    "FAFA888","FAFA191","FAFA855","FAFA117","FAFA212","FAFA800","FAFA789","FAFA368",
    "LYNSBOBET"
}
def normalize_site(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()

# ================== TEXTS (TH/EN) ==================
TXT = {
    "th": {
        "choose_language": "โปรดเลือกภาษา / Please choose language",
        "lang_th": "ภาษาไทย 🇹🇭",
        "lang_en": "English 🇬🇧",
        "welcome": "📣📣ICG สวัสดีครับ สนใจบริการด้านไหนสามารถสอบถามได้เลย📌📌\nA : สนใจเปิดเว็บไซต์เป็นของตัวเอง🎰\nB : สนใจเป้นตัวแทนของ FAFA🎯",
        "menu_A": "A : เปิดเว็บไซต์ของตัวเอง 🎰",
        "menu_B": "B : สมัครตัวแทน FAFA 🎯",

        "pkg_head": "📊ด้านล่างรายละเอียดแพ็กเกจของเราสำหรับปี 2025\n\n= >> ปัจจุบันเรามีแพ็กเกจ 4 แพ็กเกจ A, B, C และ D",
        "pkg_A_btn": "แพ็คเกจ A",
        "pkg_B_btn": "แพ็คเกจ B",
        "pkg_C_btn": "แพ็คเกจ C",
        "pkg_D_btn": "แพ็คเกจ D",
        "confirm_pkg_btn": "ยืนยันเลือกแพ็คเกจ {code}",
        "back_home": "กลับเมนูหลัก ⬅️",

        "demo_line1": "1. สามารถดูตัวอย่างและเลือกธีมทีคุณชอบ\n\nhttps://icgdemoweb.thisisanurl.xyz/",
        "demo_line2": "2. Official Website:\nhttps://icggaming.com",

        "contact_desc": "หากต้องการข้อมูลเพิ่มเติม กดปุ่ม \"ติดต่อแอดมิน\" หรือติดต่อพนักงานขายได้โดยตรง แล้วพิมพ์รายละเอียด/คำถามของคุณได้เลย",
        "contact_admin": "ติดต่อแอดมิน 📩",
        "contact_sales": "ติดต่อพนักงานขาย 🧑‍💼 (@icggame)",
        "contact_hint": "พิมพ์รายละเอียด/คำถามของคุณเพื่อส่งถึงแอดมินได้เลยครับ\n(พิมพ์ /cancel เพื่อยกเลิก)",
        "contact_sent": "ส่งข้อความถึงแอดมินเรียบร้อย ✅",

        "agent_info": (
            "B: - ฟรีค่าใช้จ่ายในการสมัครตัวแทน\n"
            "- ผลตอบแทนจะได้จากยอดเสียของสมาชิกที่หามาได้เท่านั้นและสามารถเบิกได้เป็นรายเดือนเบิกได้ทุกวันที่ 1-5 ของแต่ละเดือน\n"
            "คุณต้องมียอดยูสเซอร์ที่หาได้ขั้นต่ำ 5 ยูสเซอร์และฝากเงินขั้นต่ำยูสละ 300 บาทขึ้นไปถึงจะนับเป็น 1 ยูสเซอร์ใช้งาน\n"
            "หรือมียอดฝากอย่างน้อย 1500 บาท"
        ),
        "agent_apply": "ต้องการสมัคร ✅",
        "ask_name": "กรุณากรอกข้อมูลสมัครตัวแทนตามลำดับครับ\n1/4) ชื่อ - นามสกุล :",
        "ask_bank": "2/4) ธนาคาร :",
        "ask_acc": "3/4) เลขบัญชีธนาคาร :",
        "ask_site": "4/4) คุณต้องการสมัครเป็นตัวแทนของเว็บไซต์ :\n(โปรดระบุชื่อเว็บไซต์ให้ถูกต้อง เช่น FAFAxxx)",
        "site_invalid": "คุณแจ้งชื่อเว็บไซต์ไม่ถูกต้อง กรุณาระบุเว็บไซต์ที่คุณต้องการลงทะเบียน",
        "agent_sent": "ส่งใบสมัครถึงแอดมินเรียบร้อย ✅",
        "whoami": "chat_id ห้องนี้: {id}",
        "lang_switched": "สลับภาษาเป็นภาษาไทยแล้ว 🇹🇭",
    },
    "en": {
        "choose_language": "Please choose your language / โปรดเลือกภาษา",
        "lang_th": "ภาษาไทย 🇹🇭",
        "lang_en": "English 🇬🇧",
        "welcome": "📣 Welcome to ICG! How can we help you today? 📌📌\nA: Build your own website 🎰\nB: Become FAFA affiliate 🎯",
        "menu_A": "A : Build your own website 🎰",
        "menu_B": "B : Become FAFA affiliate 🎯",

        "pkg_head": "📊 Our 2025 packages below\n\n= >> We currently offer 4 packages: A, B, C and D",
        "pkg_A_btn": "Package A",
        "pkg_B_btn": "Package B",
        "pkg_C_btn": "Package C",
        "pkg_D_btn": "Package D",
        "confirm_pkg_btn": "Confirm package {code}",
        "back_home": "Back to main ⬅️",

        "demo_line1": "1. You can preview and choose the theme you like\n\nhttps://icgdemoweb.thisisanurl.xyz/",
        "demo_line2": "2. Official Website:\nhttps://icggaming.com/",

        "contact_desc": "Need more info? Press \"Contact admin\" or message sales directly, then type your questions.",
        "contact_admin": "Contact admin 📩",
        "contact_sales": "Contact sales 🧑‍💼 (@icggame)",
        "contact_hint": "Type your details/questions and I’ll forward them to admin.\n(Type /cancel to cancel)",
        "contact_sent": "Your message has been sent to admin ✅",

        "agent_info": (
            "B: - Free to apply as affiliate\n"
            "- Commission is paid monthly from net losses of your referred users (withdraw 1st–5th each month)\n"
            "Requirement: at least 5 active users (≥ THB 300 first deposit each) or total deposit ≥ THB 1,500."
        ),
        "agent_apply": "Apply now ✅",
        "ask_name": "Please fill affiliate form\n1/4) Full name :",
        "ask_bank": "2/4) Bank :",
        "ask_acc": "3/4) Bank account number :",
        "ask_site": "4/4) Which website do you want to be an affiliate of :\n(Please enter the exact brand name, e.g., FAFAxxx)",
        "site_invalid": "Invalid website name. Please enter the exact brand you want to register.",
        "agent_sent": "Your application has been sent to admin ✅",
        "whoami": "This chat_id: {id}",
        "lang_switched": "Language switched to English 🇬🇧",
    }
}

PKG_TH = {
    "A": "แพ็คเกจ A. \"90%\"\n\n-ค่าติดตั้ง: 70,000 บาท (ครั้งเดียว)\n-ค่าบำรุงรักษา: 58,000 บาท/เดือน\n\n- ชำระค่าบำรุงรักษา 3 เดือนแรก (174,000) เพื่อรับฟรีเดือนที่ 4\n* ยอดชำระเริ่มต้น: 244,000 บาท\n\n- เดือนที่ 5 เป็นต้นไป 58,000/เดือน\n- เติมเครดิตชำระเพียง 10% (เช่น เติม 100,000 เครดิต จ่าย 10,000 บาท)\n* รองรับหลายสกุลเงิน (1 เว็บไซต์)\nหมายเหตุ: โอนแล้วไม่สามารถคืนเงินได้",
    "B": "แพ็คเกจ B \"80%\"\n\n-ค่าติดตั้ง: 30,000 บาท (ครั้งเดียว)\n-ค่าบำรุงรักษา: 15,000 บาท/เดือน\n\n- ชำระค่าบำรุงรักษา 3 เดือนแรก (45,000) เพื่อรับฟรีเดือนที่ 4\n* ยอดชำระเริ่มต้น: 75,000 บาท\n\n- เดือนที่ 5 เป็นต้นไป 15,000/เดือน\n- เติมเครดิตชำระเพียง 20%\n* รองรับสกุลเงินเดียว (1 เว็บไซต์)\nหมายเหตุ: โอนแล้วไม่สามารถคืนเงินได้",
    "C": "แพ็คเกจ C \"90%\"\n\n-ค่าติดตั้ง: 200,000 บาท (ครั้งเดียว)\n-ค่าบำรุงรักษา: 175,000 บาท/เดือน\n\n- ชำระค่าบำรุง 3 เดือนแรก (525,000) เพื่อรับฟรีเดือนที่ 4\n* ยอดชำระเริ่มต้น: 725,000 บาท\n\n- เดือนที่ 5 เป็นต้นไป 175,000/เดือน\n- เติมเครดิตชำระ 10%\n> ให้ 3 เว็บไซต์/แบรนด์, หลายสกุลเงินต่อเว็บ, มีหลังบ้านแยก, ปล่อยเช่าได้ (B2C)\n> เว็บที่ 4 ติดตั้งฟรี ค่าบำรุง $500/เดือน\nหมายเหตุ: โอนแล้วไม่สามารถคืนเงินได้",
    "D": "แพ็คเกจ D \"85%\"\n\n-ค่าติดตั้ง: 55,000 บาท (ครั้งเดียว)\n-ค่าบำรุงรักษา: 35,000 บาท/เดือน\n\n- ชำระค่าบำรุง 3 เดือนแรก (105,000) เพื่อรับฟรีเดือนที่ 4\n* ยอดชำระเริ่มต้น: 160,000 บาท\n\n- เดือนที่ 5 เป็นต้นไป 35,000/เดือน\n- เติมเครดิตชำระ 15%\n* รองรับสกุลเงินเดียว (1 เว็บไซต์)\nหมายเหตุ: โอนแล้วไม่สามารถคืนเงินได้",
}
PKG_EN = {
    "A": "Package A \"90%\"\n\n- Setup: 70,000 THB (one-time)\n- Maintenance: 58,000 THB/month\n\n- Pay first 3 months (174,000) to get month 4 free\n* Initial payment: 244,000 THB\n\n- From month 5: 58,000/month\n- Credit top-up pay 10% (e.g., 100,000 credit → pay 10,000)\n* Multi-currency (single website)\nNote: non-refundable.",
    "B": "Package B \"80%\"\n\n- Setup: 30,000 THB (one-time)\n- Maintenance: 15,000 THB/month\n\n- Pay first 3 months (45,000) to get month 4 free\n* Initial payment: 75,000 THB\n\n- From month 5: 15,000/month\n- Credit top-up pay 20%\n* Single currency (single website)\nNote: non-refundable.",
    "C": "Package C \"90%\"\n\n- Setup: 200,000 THB (one-time)\n- Maintenance: 175,000 THB/month\n\n- Pay first 3 months (525,000) to get month 4 free\n* Initial payment: 725,000 THB\n\n- From month 5: 175,000/month\n- Credit top-up pay 10%\n> 3 websites/brands, multi-currency per site, separate admin panels, can sub-lease (B2C)\n> 4th site install free, maintenance $500/month\nNote: non-refundable.",
    "D": "Package D \"85%\"\n\n- Setup: 55,000 THB (one-time)\n- Maintenance: 35,000 THB/month\n\n- Pay first 3 months (105,000) to get month 4 free\n* Initial payment: 160,000 THB\n\n- From month 5: 35,000/month\n- Credit top-up pay 15%\n* Single currency (single website)\nNote: non-refundable.",
}

def T(uid: int, key: str, **kw) -> str:
    lang = get_lang(uid)
    s = TXT[lang][key]
    return s.format(**kw)

def PKG(uid: int, code: str) -> str:
    return (PKG_EN if get_lang(uid) == "en" else PKG_TH)[code]

# ================== HELPERS: ALWAYS NO LINK PREVIEW ==================
async def send_text(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs):
    kwargs.setdefault("disable_web_page_preview", True)
    await context.bot.send_message(chat_id, text, **kwargs)

async def reply_text(update: Update, text: str, **kwargs):
    kwargs.setdefault("disable_web_page_preview", True)
    await update.effective_message.reply_text(text, **kwargs)

# ================== KEYBOARDS ==================
def kb_lang(uid: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T(uid, "lang_th"), callback_data="lang_th"),
         InlineKeyboardButton(T(uid, "lang_en"), callback_data="lang_en")]
    ])

def kb_home(uid: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T(uid, "menu_A"), callback_data="choose_A")],
        [InlineKeyboardButton(T(uid, "menu_B"), callback_data="choose_B")]
    ])

def kb_packages(uid: int, selected: Optional[str] = None):
    rows = [
        [InlineKeyboardButton(T(uid, "pkg_A_btn"), callback_data="pkg_A"),
         InlineKeyboardButton(T(uid, "pkg_B_btn"), callback_data="pkg_B")],
        [InlineKeyboardButton(T(uid, "pkg_C_btn"), callback_data="pkg_C"),
         InlineKeyboardButton(T(uid, "pkg_D_btn"), callback_data="pkg_D")],
    ]
    if selected:
        rows.append([InlineKeyboardButton(T(uid, "confirm_pkg_btn", code=selected), callback_data="confirm_pkg")])
    rows.append([InlineKeyboardButton(T(uid, "back_home"), callback_data="back_home")])
    return InlineKeyboardMarkup(rows)

def kb_contact(uid: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T(uid, "contact_admin"), callback_data="contact_admin")],
        [InlineKeyboardButton(T(uid, "contact_sales"), url=f"https://t.me/{SALES_USERNAME}")],
        [InlineKeyboardButton(T(uid, "back_home"), callback_data="back_home")],
    ])

# ================== TOPIC UTILS ==================
async def ensure_topic(context: ContextTypes.DEFAULT_TYPE, user, customer_id: int) -> int:
    if customer_id in CUSTOMER_TO_TOPIC:
        return CUSTOMER_TO_TOPIC[customer_id]

    topic_name = f"{user.full_name or 'User'} | {customer_id}"
    tid = 0
    try:
        topic: ForumTopic = await context.bot.create_forum_topic(ADMIN_CHAT_ID, topic_name)
        tid = topic.message_thread_id
    except Exception as e:
        log.exception("create_forum_topic failed: %s", e)

    CUSTOMER_TO_TOPIC[customer_id] = tid
    if tid: TOPIC_TO_CUSTOMER[tid] = customer_id

    await send_text(context, ADMIN_CHAT_ID,
        (f"🧵 เธรดลูกค้าใหม่\n"
         f"- name: {user.full_name}\n"
         f"- username: @{user.username or '-'}\n"
         f"- user_id: {user.id}\n"
         f"- chat_id: {customer_id}"),
        message_thread_id=tid or None
    )

    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            sent = await context.bot.send_photo(
                ADMIN_CHAT_ID, message_thread_id=tid or None,
                photo=photos.photos[0][0].file_id, caption="รูปโปรไฟล์ล่าสุด / Latest profile photo"
            )
            await context.bot.pin_chat_message(ADMIN_CHAT_ID, sent.message_id, message_thread_id=tid or None)
    except Exception as e:
        log.exception("profile photo send/pin failed: %s", e)

    return tid

# ================== COMMANDS ==================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    # เก็บผู้ใช้สำหรับ broadcast (ทุกครั้งที่ /start)
    ustate(uid); save_state(STATE)
    add_broadcast_chat(uid)
    await send_text(context, uid, T(uid, "choose_language"), reply_markup=kb_lang(uid))

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    await send_text(context, uid, T(uid, "choose_language"), reply_markup=kb_lang(uid))

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_text(update, T(update.effective_chat.id, "whoami", id=update.effective_chat.id))

# ----- Broadcast (เฉพาะแอดมิน) -----
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    reply = update.message.reply_to_message
    text = " ".join(context.args) if context.args else None
    if not reply and not text:
        await update.message.reply_text("ใช้แบบใดแบบหนึ่ง:\n1) /broadcast ข้อความ...\n2) ตอบกลับ (reply) ข้อความ/รูป/วิดีโอ แล้วพิมพ์ /broadcast")
        return

    # รวมเป้าหมาย: ผู้ใช้ทั้งหมด + แชท (กลุ่ม/ผู้ใช้) ที่เก็บไว้
    user_ids = [int(x) for x in STATE["users"].keys()]
    chat_ids = list(_get_broadcast_set())
    targets = sorted(set(user_ids) | set(chat_ids))

    success, fail = 0, 0
    for cid in targets:
        try:
            if reply:
                await context.bot.copy_message(
                    chat_id=cid,
                    from_chat_id=ADMIN_CHAT_ID,
                    message_id=reply.message_id
                )
            else:
                await context.bot.send_message(
                    chat_id=cid,
                    text=text,
                    disable_web_page_preview=True
                )
            success += 1
        except Exception as e:
            log.warning(f"Broadcast ส่งไม่ถึง {cid}: {e}")
            fail += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(f"📣 Broadcast: ✅ ส่งสำเร็จ {success} | ❌ ไม่สำเร็จ {fail}")

# ================== CALLBACKS (LANG) ==================
async def cb_lang_th(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    set_lang(uid, "th")
    await send_text(context, uid, TXT["th"]["welcome"], reply_markup=kb_home(uid))

async def cb_lang_en(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    set_lang(uid, "en")
    await send_text(context, uid, TXT["en"]["welcome"], reply_markup=kb_home(uid))

# ================== MENUS ==================
async def cb_choose_A(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    await send_text(context, uid, T(uid, "pkg_head"), reply_markup=kb_packages(uid))
    ulog(uid, "choose A")

async def cb_choose_B(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    await send_text(context, uid, T(uid, "agent_info"), reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(T(uid,"agent_apply"), callback_data="agent_apply")],
        [InlineKeyboardButton(T(uid,"back_home"), callback_data="back_home")]
    ]))
    ulog(uid, "choose B")

async def _show_pkg(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    ustate(uid)["selected_package"] = code; save_state(STATE)
    ulog(uid, f"view package {code}")
    await send_text(context, uid, PKG(uid, code), reply_markup=kb_packages(uid, code))

async def cb_pkg_A(u,c): await _show_pkg(u,c,"A")
async def cb_pkg_B(u,c): await _show_pkg(u,c,"B")
async def cb_pkg_C(u,c): await _show_pkg(u,c,"C")
async def cb_pkg_D(u,c): await _show_pkg(u,c,"D")

async def cb_confirm_pkg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    sel = ustate(uid).get("selected_package") or "-"
    ulog(uid, f"confirm package {sel}")
    await send_text(context, uid, T(uid, "demo_line1"))
    await send_text(context, uid, T(uid, "demo_line2"))
    await send_text(context, uid, T(uid, "contact_desc"), reply_markup=kb_contact(uid))

async def cb_back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    await send_text(context, uid, T(uid, "back_home"), reply_markup=kb_home(uid))

# ================== CONTACT & AGENT FLOWS ==================
class ST:
    CONTACT = 1
    AGENT_NAME = 2
    AGENT_BANK = 3
    AGENT_ACC  = 4
    AGENT_SITE = 5

async def cb_contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    await send_text(context, uid, T(uid, "contact_hint"))
    return ST.CONTACT

async def submit_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; uid = update.effective_chat.id
    msg  = update.effective_message
    ulog(uid, f"[contact] {msg.text if msg.text else '(media)'}")
    tid = await ensure_topic(context, user, uid)
    await context.bot.copy_message(ADMIN_CHAT_ID, uid, msg.message_id, message_thread_id=tid or None)
    await reply_text(update, T(uid, "contact_sent"), reply_markup=kb_home(uid))
    return ConversationHandler.END

async def cb_agent_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.message.chat_id
    await send_text(context, uid, TXT[get_lang(uid)]["ask_name"])
    return ST.AGENT_NAME

async def ag_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    ustate(uid)["ag_name"] = update.message.text.strip(); save_state(STATE)
    await reply_text(update, T(uid, "ask_bank")); return ST.AGENT_BANK

async def ag_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    ustate(uid)["ag_bank"] = update.message.text.strip(); save_state(STATE)
    await reply_text(update, T(uid, "ask_acc")); return ST.AGENT_ACC

async def ag_acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    ustate(uid)["ag_acc"] = update.message.text.strip(); save_state(STATE)
    await reply_text(update, T(uid, "ask_site")); return ST.AGENT_SITE

async def ag_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; uid = update.effective_chat.id
    raw_site = (update.message.text or "").strip()
    site_norm = normalize_site(raw_site)

    if site_norm not in SITE_WHITELIST:
        await reply_text(update, T(uid, "site_invalid"))
        return ST.AGENT_SITE

    u = ustate(uid)
    u["ag_site"] = raw_site
    u["ag_site_norm"] = site_norm
    save_state(STATE)

    tid = await ensure_topic(context, user, uid)
    admin_text = (
        "📝 New affiliate application\n"
        f"- name: {u.get('ag_name')}\n"
        f"- bank: {u.get('ag_bank')}\n"
        f"- account: {u.get('ag_acc')}\n"
        f"- site: {u.get('ag_site')} (norm: {u.get('ag_site_norm')})\n"
        f"- chat_id: {uid}"
    )
    await send_text(context, ADMIN_CHAT_ID, admin_text, message_thread_id=tid or None)
    await reply_text(update, T(uid, "agent_sent"), reply_markup=kb_home(uid))
    return ConversationHandler.END

# ============ FORWARD EVERYTHING ============
async def user_any_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_CHAT_ID: return
    user = update.effective_user
    uid  = update.effective_chat.id
    msg  = update.effective_message
    tid  = await ensure_topic(context, user, uid)
    try:
        await context.bot.copy_message(
            chat_id=ADMIN_CHAT_ID,
            from_chat_id=uid,
            message_id=msg.message_id,
            message_thread_id=tid or None
        )
    except Exception as e:
        log.exception("copy user->admin failed: %s", e)

async def admin_any_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID: return
    msg = update.effective_message
    tid = msg.message_thread_id or 0
    uid = TOPIC_TO_CUSTOMER.get(tid)
    if not uid: return
    try:
        if msg.text and not (msg.photo or msg.document or msg.video or msg.audio or msg.voice or msg.sticker or msg.animation):
            await send_text(context, uid, msg.text)
        else:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=ADMIN_CHAT_ID,
                message_id=msg.message_id
            )
    except Exception as e:
        log.exception("copy admin->user failed: %s", e)

# ============ CHAT MEMBER (เชิญ/เตะบอทในกลุ่ม) ============
async def my_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    เรียกเมื่อสถานะ 'บอท' ในแชทใด ๆ ถูกเปลี่ยน (ถูกเชิญเข้ากลุ่ม / ถูกเตะออก เป็นต้น)
    """
    cm = update.my_chat_member
    if not cm: return
    chat = cm.chat                      # กลุ่ม/ซุปเปอร์กรุ๊ป/แชทส่วนตัว
    new_status = cm.new_chat_member.status  # 'member' | 'administrator' | 'kicked' | 'left' | ...
    is_about_this_bot = (cm.new_chat_member.user.id == context.bot.id)

    if not is_about_this_bot:
        return

    if new_status in ("member", "administrator"):
        # บอทถูกเพิ่มเข้ามา → เก็บ chat id นี้ไว้ broadcast
        add_broadcast_chat(chat.id)
        log.info("Bot added to chat %s (%s)", chat.id, chat.type)
    elif new_status in ("kicked", "left"):
        # บอทถูกเตะออก/ออกเอง → ลบออกจากรายการ broadcast
        remove_broadcast_chat(chat.id)
        log.info("Bot removed from chat %s (%s)", chat.id, chat.type)

# ================== MAIN ==================
def main():
    app: Application = ApplicationBuilder().token(TOKEN).build()

    # คำสั่งทั่วไป
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("lang",  lang_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))

    # เฉพาะแอดมิน (ส่งจากห้อง ADMIN_CHAT_ID เท่านั้น)
    app.add_handler(CommandHandler("broadcast", broadcast_cmd, filters=filters.Chat(ADMIN_CHAT_ID)))

    # ปุ่ม/เมนู
    app.add_handler(CallbackQueryHandler(cb_lang_th, pattern="^lang_th$"))
    app.add_handler(CallbackQueryHandler(cb_lang_en, pattern="^lang_en$"))
    app.add_handler(CallbackQueryHandler(cb_choose_A,   pattern="^choose_A$"))
    app.add_handler(CallbackQueryHandler(cb_choose_B,   pattern="^choose_B$"))
    app.add_handler(CallbackQueryHandler(cb_pkg_A,      pattern="^pkg_A$"))
    app.add_handler(CallbackQueryHandler(cb_pkg_B,      pattern="^pkg_B$"))
    app.add_handler(CallbackQueryHandler(cb_pkg_C,      pattern="^pkg_C$"))
    app.add_handler(CallbackQueryHandler(cb_pkg_D,      pattern="^pkg_D$"))
    app.add_handler(CallbackQueryHandler(cb_confirm_pkg,pattern="^confirm_pkg$"))
    app.add_handler(CallbackQueryHandler(cb_back_home,  pattern="^back_home$"))

    # Contact flow (1:1 admin)
    contact_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_contact_admin, pattern="^contact_admin$")],
        states={ 1: [MessageHandler(~filters.COMMAND, submit_contact)] },
        fallbacks=[CommandHandler("start", start_cmd)],
        name="CONTACT_FLOW", persistent=False
    )
    app.add_handler(contact_conv)

    # Agent flow
    agent_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_agent_apply, pattern="^agent_apply$")],
        states={
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_name)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_bank)],
            4: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_acc)],
            5: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_finish)],
        },
        fallbacks=[CommandHandler("start", start_cmd)],
        name="AGENT_FLOW", persistent=False
    )
    app.add_handler(agent_conv)

    # Forward media/text ทั้งหมด
    app.add_handler(MessageHandler(~filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND, user_any_to_admin))
    app.add_handler(MessageHandler(filters.Chat(ADMIN_CHAT_ID) & ~filters.COMMAND,  admin_any_to_user))

    # สำคัญ: จับเหตุการณ์เชิญ/เตะบอทในกลุ่ม (เก็บ/ลบ chat id อัตโนมัติ)
    app.add_handler(ChatMemberHandler(my_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))

    log.info("✅ bot started (bilingual + topics + media + broadcast + validation + sales=@%s)", SALES_USERNAME)
    app.run_polling()

if __name__ == "__main__":
    main()
