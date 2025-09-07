#!/usr/bin/env python3
"""
WCoin Telegram Bot - full version (new.py)
- In-memory storage (replace with DB for production)
- Requires BOT_TOKEN env var
- Admins: set ADMIN_USER_IDS
- Channels: set REQUIRED_CHANNELS (bot must be admin/member to check)
- This script implements the flows described by the user:
  * Channel join gate (must join required channels before using bot)
  * Main menu with 5 user functions
  * Invite (deep-link referral) awarding after join
  * Buying machines (Basic/Common/Epic/Premium) with WavePay or WCoin per spec
  * Claim logic (12-hour windows), 30-day expiration
  * Withdraw logic with 3 rules & admin skip
  * Admin commands for payouts, orders, images, add balance, skip, stats
NOTE: This is a single-file reference implementation. It's meant for local testing.

Modified to be compatible with `python-telegram-bot` version 20+.
- Replaced `Updater` with `Application`.
- Replaced `ContextTypes.DEFAULT_TYPE` with `ContextTypes`.
- Replaced `updater.start_polling()` with `application.run_polling()`.
- Replaced `updater.idle()` with `application.idle()`.
- Replaced `ContextTypes.DEFAULT_TYPE` in all functions with `ContextTypes`.
- Modified `bot_username` and `main` functions to fit the new structure.
- Updated imports to reflect changes in `python-telegram-bot` v20.
"""

import os
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable before running")

# Put your actual channel usernames (public) here, e.g. "@yourchannel"
REQUIRED_CHANNELS = ["@your_channel"]  # users must join these channels
PAYOUT_HISTORY_CHANNEL = "@payout_history_by_waveMiner"  # channel to post payout receipts
ADMIN_USER_IDS = {123456789}  # replace with real admin telegram ids (ints)

# Machine definitions
MACHINES = {
    1: {
        "key": "Basic",
        "price_mmk": 0,
        "price_wcoin": 0,
        "daily_wcoin": 1500,
        "claim_interval_sec": 12 * 3600,
        "expire_days": 30,
        "counts_for_withdraw": False,
    },
    2: {
        "key": "Common",
        "price_mmk": 5000,
        "price_wcoin": None,
        "daily_wcoin": 3000,
        "claim_interval_sec": 12 * 3600,
        "expire_days": 30,
        "counts_for_withdraw": True,
    },
    3: {
        "key": "Epic",
        "price_mmk": 8000,
        "price_wcoin": None,
        "daily_wcoin": 4500,
        "claim_interval_sec": 12 * 3600,
        "expire_days": 30,
        "counts_for_withdraw": True,
    },
    4: {
        "key": "Premium",
        "price_mmk": 30000,
        "price_wcoin": 30000,
        "daily_wcoin": 10000,
        "claim_interval_sec": 12 * 3600,
        "expire_days": 30,
        "counts_for_withdraw": None,  # depends on payment method
    },
}

# ---------------- STORAGE (in-memory for this sample) ----------------
USERS: Dict[int, Dict[str, Any]] = {}
MACHINE_ORDERS: List[Dict[str, Any]] = []  # pending machine orders (wave pay)
WITHDRAW_REQUESTS: List[Dict[str, Any]] = []  # pending withdraw requests

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- HELPERS ----------------


def ensure_user(user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    u = USERS.get(user_id)
    if not u:
        USERS[user_id] = {
            "id": user_id,
            "username": username or f"user{user_id}",
            "balance": 0,
            "referrals": 0,
            "referred_by": None,
            "referral_credited": False,
            "machines": [],  # list of dicts: {machine_no, buy_ts, expire_ts, last_claim_ts, method}
            "withdraw_account": None,
            "withdraw_fail_count": 0,
            "awaiting": None,  # expecting 'phone','amount','transfer_no','admin_caption', etc.
            "pending_order": None,  # temp holder for machine purchase
            "skip_verified": False,
        }
        u = USERS[user_id]
    return u


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


def bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.bot.username


def has_joined_all_channels(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check membership; return False if bot cannot verify or user not joined."""
    bot = context.bot
    try:
        for ch in REQUIRED_CHANNELS:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        return True
    except Exception as e:
        logger.warning("Membership check failed: %s", e)
        return False


def build_main_menu():
    kb = [
        [InlineKeyboardButton("လက်ကျန်ငွေ", callback_data="balance")],
        [InlineKeyboardButton("ဖိတ်ခေါ်မည်", callback_data="invite")],
        [InlineKeyboardButton("စက်ဝယ်မည်", callback_data="buy_machine")],
        [InlineKeyboardButton("စက်များ", callback_data="machines")],
        [InlineKeyboardButton("ငွေထုတ်မည်", callback_data="withdraw")],
    ]
    return InlineKeyboardMarkup(kb)


async def send_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔐 Channel ဝင်ရောက်ရန် လိုအပ်ပါသည်\n\n"
        "Bot ကို အသုံးပြုရန် ကျွန်ုပ်တို့၏ Official Channel သို့ ဝင်ရောက်ရန်လိုအပ်ပါသည်\n\n"
        + "\n".join(REQUIRED_CHANNELS)
        + "\n\nChannel ဝင်ရောက်ပြီးပါက အောက်ပါ ခလုတ်ကို နှိပ်ပါ\n\n(ဝင်ရောက်ပီးပါပီ)"
    )
    kb = [[InlineKeyboardButton("ဝင်ရောက်ပြီးပါပီ ✅", callback_data="confirm_join")]]
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))


# ---------------- COMMANDS / FLOWS ----------------


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username)
    # deep-link referral handling: /start <referrer_id>
    if context.args:
        try:
            ref = int(context.args[0])
            if ref != user.id:
                USERS[user.id]["referred_by"] = ref
                USERS[user.id]["referral_credited"] = False
        except Exception:
            pass

    if not has_joined_all_channels(context, user.id):
        return await send_join_gate(update, context)
    # if joined -> possibly credit referral
    await credit_pending_referral(user.id, context)
    # show main menu
    await update.message.reply_text("Main Menu - အောက်က မီနူးမှ ရွေးပါ", reply_markup=build_main_menu())


async def confirm_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    if not has_joined_all_channels(context, user_id):
        await q.answer("Channel မဝင်ရသေးပါ", show_alert=True)
        return
    await q.answer()
    await q.message.edit_text("✅ ဝင်ရောက်ပြီးပါပြီ")
    await credit_pending_referral(user_id, context)
    await q.message.reply_text("Main Menu", reply_markup=build_main_menu())


async def credit_pending_referral(new_user_id: int, context: ContextTypes.DEFAULT_TYPE):
    u = USERS.get(new_user_id)
    if not u:
        return
    if u.get("referral_credited"):
        return
    ref = u.get("referred_by")
    if not ref or ref == new_user_id or ref not in USERS:
        return
    # credit both
    USERS[ref]["balance"] += 3000
    USERS[ref]["referrals"] += 1
    u["balance"] += 3000
    u["referral_credited"] = True
    # notify inviter
    try:
        await context.bot.send_message(ref, f"🎉 သင့်ဖိတ်ခေါ်မှုမှ အသစ်တစ်ဦး ဝင်လာပြီး WCoin 3000 ရရှိပါပြီ!\nBalance: {USERS[ref]['balance']}")
    except Exception:
        pass


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    ensure_user(uid, q.from_user.username)
    # Guard: require channel join for all menu actions
    if not has_joined_all_channels(context, uid):
        return await send_join_gate(update, context)

    await q.answer()
    if data == "balance":
        return await show_balance(q, context)
    if data == "invite":
        return await invite_cb(q, context)
    if data == "buy_machine":
        return await buy_machine_menu(q, context)
    if data == "machines":
        return await machines_menu(q, context)
    if data == "withdraw":
        return await withdraw_menu(q, context)
    # machine purchase callbacks
    if data.startswith("buy_"):  # buy_{machine_no}
        return await handle_buy_click(q, context, data)
    if data.startswith("premium_"):  # premium_wcoin / premium_wave
        return await handle_premium_choice(q, context, data)
    if data.startswith("claim::"):  # claim::{machine_idx}
        return await handle_claim(q, context, data)
    if data == "change_withdraw_account":
        return await prompt_withdraw_account(q, context)
    if data == "confirm_withdraw_account":
        return await prompt_withdraw_amount(q, context)
    if data == "cancel_withdraw":
        return await q.message.edit_text("ငွေထုတ်လုပ်ငန်းစဉ်ကို ဖျက်ပြီးပါပြီ။")
    if data == "cancel_purchase":
        return await cancel_purchase_cb(q, context)


# ---------------- UI Actions ----------------


async def show_balance(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    u = USERS[uid]
    active = active_machines_count(uid)
    total_daily = total_daily_income(uid)
    msg = (
        "သင်၏အကောင့်\n\n"
        f"နာမည်-{u['username']}\n"
        f"လက်ကျန်ငွေ-{u['balance']}\n"
        f"သင်၏ဖိတ်ခေါ်မှု-{u['referrals']}\n\n"
        "စက်အခြေအနေများ\n"
        f"စက်ပိုင်ဆိုင်မှုများ-{active}\n"
        f"ဝင်ငွေနှုန်း-{total_daily} WCoin/ရက်"
    )
    await q.message.edit_text(msg)


async def invite_cb(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    link = f"https://t.me/{bot_username(context)}?start={uid}"
    text = (
        "ငါ ဒီ Bot ကနေ သုံးပြီး လိုင်းပေါ်ကနေပိုက်ဆံတွေ ရနေတယ် 💸\n\n"
        "🛒 တူးစက်တွေ ဝယ်ပြီး လိုင်းပေါ်မှာ လွယ်လွယ်နဲ့ ငွေရှာတာ မိုက်တယ်။\n\n"
        "🫵 မင်းလည်း တူတူ လုပ်ၾကည့် ➡️ တူးစက်ဝယ် + လူခေါ် = ငွေထုတ်💸\n\n"
        f"Link 👉 {link}"
    )
    await q.message.edit_text(text)


async def buy_machine_menu(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    u = USERS[uid]
    now = int(time.time())
    
    # Send a single introductory message first
    await q.message.edit_text("⚒️ စက်ဝယ်ယူရန် မီနူး")
    
    for idx in sorted(MACHINES.keys()):
        m = MACHINES[idx]
        owned = any(mi["machine_no"] == idx and mi["expire_ts"] > now for mi in u["machines"])
        caption = (
            f"⚙️ စက်အမည်: {m['key']}\n"
            f"⛏ တူးနှုန်း: {m['daily_wcoin']} WCoin/ရက်\n"
            f"📅 Expire after: {m['expire_days']} days\n"
        )
        buttons = []
        if owned:
            caption += "\n✅ သင်ပိုင်ဆိုင်ထားပါသည်"
        else:
            if idx == 4:  # Premium - two payment methods
                buttons.append([InlineKeyboardButton("WCoin ဖြင့်ဝယ်မည်", callback_data="premium_wcoin")])
                buttons.append([InlineKeyboardButton("Wave Pay ဖြင့်ဝယ်မည်", callback_data="premium_wave")])
            else:
                price = m["price_mmk"]
                buttons.append([InlineKeyboardButton(f"Price: {price} MMK", callback_data=f"buy_{idx}")])
        
        await context.bot.send_message(
            chat_id=q.message.chat_id, 
            text=caption, 
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )


async def handle_buy_click(q, context: ContextTypes.DEFAULT_TYPE, data: str):
    uid = q.from_user.id
    ensure_user(uid)
    parts = data.split("_")
    if len(parts) != 2:
        await q.answer()
        return
    try:
        machine_no = int(parts[1])
    except Exception:
        await q.answer()
        return
    m = MACHINES.get(machine_no)
    if not m:
        await q.answer()
        return
    
    order = {
        "order_id": int(time.time() * 1000),
        "user_id": uid,
        "machine_no": machine_no,
        "price_mmk": m['price_mmk'],
        "step": "await_transfer_no",
        "created_at": datetime.now().isoformat(),
    }
    USERS[uid]["pending_order"] = order
    await q.message.edit_text(
        "သင့်အတွက် ငွေလွှဲအော်ဒါ\n\n"
        "ငွေလွှဲရန် အချက်အလက်⬇️\n"
        "———————————-\n"
        f"🌕Wave Pay - (09123456789)\n"
        f"👤နာမည် - (your name)\n"
        f"💰ပမာဏ - {m['price_mmk']} MMK\n"
        "———————————-\n"
        "✅ ငွေလွှဲပြီး 10မိနစ်အတွင်း ပြေစာပုံနှင့်သင်၏ငွေလွှဲနံပါတ်အား ပို့ပါ။\n\n"
        "📌 ငွေလွှဲနံပါတ်ကို ပထမဦးစွာ ပို့ပေးပါ။",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_purchase")]]),
    )


async def handle_premium_choice(q, context: ContextTypes.DEFAULT_TYPE, data: str):
    uid = q.from_user.id
    ensure_user(uid)
    if data == "premium_wcoin":
        price = MACHINES[4]["price_wcoin"]
        if USERS[uid]["balance"] >= price:
            if can_buy_machine_now(uid, 4):
                USERS[uid]["balance"] -= price
                install_machine(uid, 4, method="wcoin")
                await q.message.edit_text("Premium Machine ကို WCoin ဖြင့် အောင်မြင်စွာ ဝယ်ယူပြီးပါပြီ ✅")
            else:
                await q.message.edit_text("❌ ဒီစက်ကို 30 ရက်အတွင်း တစ်ခါထပ်ဝယ်လို့ မရပါ။")
        else:
            await q.message.edit_text("Balance မလုံလောက်ပါ ❌")
    elif data == "premium_wave":
        order = {
            "order_id": int(time.time() * 1000),
            "user_id": uid,
            "machine_no": 4,
            "price_mmk": MACHINES[4]["price_mmk"],
            "step": "await_transfer_no",
            "created_at": datetime.now().isoformat(),
        }
        USERS[uid]["pending_order"] = order
        await q.message.edit_text(
            "Premium (Wave Pay) — ငွေလွှဲနံပါတ် ပို့ပါ။\n\n(10 မိနစ်အတွင်း screenshot ပို့ပါ)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_purchase")]]),
        )


def can_buy_machine_now(user_id: int, machine_no: int) -> bool:
    """Return False if user already owns active machine of same type"""
    now = int(time.time())
    for mi in USERS[user_id]["machines"]:
        if mi["machine_no"] == machine_no and mi["expire_ts"] > now:
            return False
    return True


def install_machine(user_id: int, machine_no: int, method: str = "wave"):
    now = int(time.time())
    exp = now + MACHINES[machine_no]["expire_days"] * 86400
    USERS[user_id]["machines"].append(
        {
            "machine_no": machine_no,
            "buy_ts": now,
            "expire_ts": exp,
            "last_claim_ts": now,
            "method": method,
        }
    )


async def cancel_purchase_cb(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    if USERS[uid].get("pending_order"):
        USERS[uid]["pending_order"] = None
    await q.message.edit_text("စက်ဝယ်ခြင်းလုပ်ငန်းစဉ်ကို ဖျက်ပြီးပါပြီ။")


# ---------------- MESSAGE HANDLERS FOR TEXT & PHOTO ----------------


async def text_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username)
    u = USERS[user.id]
    text = update.message.text.strip()

    # If user is in pending order expecting transfer number
    po = u.get("pending_order")
    if po:
        if po["step"] == "await_transfer_no":
            po["transfer_no"] = text
            po["step"] = "await_screenshot"
            await update.message.reply_text("Transfer number သိရှိပါပြီ။ သင်၏ payment screenshot ကို ပို့ပါ။")
            return
        if po["step"] == "await_screenshot":
            # they typed something instead of photo
            await update.message.reply_text("Screenshot တင်ရန်, ဓာတ်ပုံပို့ပေးပါ။")
            return

    # Withdraw phone number set
    if u.get("awaiting") == "withdraw_account":
        u["withdraw_account"] = text
        u["awaiting"] = None
        await update.message.reply_text(f"သင့်ငွေထုတ်အကောင့်အနေနဲ့ {text} ကို သိမ်းဆည်းပြီးပါပြီ။")
        return

    # Withdraw amount
    if u.get("awaiting") == "withdraw_amount":
        if not text.replace(",", "").isdigit():
            await update.message.reply_text("ပမာဏမှန်ကန်စွာ ထည့်ပါ")
            return
        amt = int(text.replace(",", ""))
        if amt > u["balance"]:
            u["withdraw_fail_count"] = u.get("withdraw_fail_count", 0) + 1
            await update.message.reply_text("ငွေမလောက်ပါ")
            if u["withdraw_fail_count"] >= 2:
                u["awaiting"] = None
                u["withdraw_fail_count"] = 0
                await update.message.reply_text("ငွေထုတ် logic ကို ရပ်ထားလိုက်ပါသည်")
            return
        if amt < 50000:
            await update.message.reply_text("အနည်းဆုံး50000ကျပ်သာထုတ်နိုင်ပါသည်")
            return
        # create withdraw order
        order_id = int(time.time() * 1000)
        WITHDRAW_REQUESTS.append(
            {
                "order_id": order_id,
                "user_id": user.id,
                "amount": amt,
                "account": u.get("withdraw_account"),
                "created_at": datetime.now().isoformat(),
            }
        )
        u["awaiting"] = None
        await update.message.reply_text("admin သို့ ပို့လိုက်ပါပြီ ခနစောင့်ပါ")
        return

    # Admin caption for /Add_B y
    if is_admin(user.id) and u.get("awaiting") == "admin_add_caption":
        payload = u.pop("admin_add_payload", None)
        caption = text if text.strip() != "" else None
        if payload:
            target = payload["target"]
            amt = payload["amount"]
            try:
                await context.bot.send_message(target, (caption + "\n") if caption else "" + f"သင်ရငွေ: {amt}")
            except Exception:
                pass
        u["awaiting"] = None
        await update.message.reply_text("Caption ပို့ပြီးပါပြီ")
        return

    await update.message.reply_text("မသိပါ။ မီနူးမှ ရွေးပါ။")


async def photo_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username)
    u = USERS[user.id]
    # If awaiting screenshot for pending order
    po = u.get("pending_order")
    if po and po.get("step") == "await_screenshot":
        file_id = update.message.photo[-1].file_id
        po["screenshot_file_id"] = file_id
        po["step"] = "submitted"
        MACHINE_ORDERS.append(po.copy())
        u["pending_order"] = None
        await update.message.reply_text("Admin သို့ ပေးပို့ပြီးပါပြီ (pending order list တွင် ထည့်ထားပါသည်)")
        return

    # Admin handling withdraw receipt photo
    if is_admin(user.id) and u.get("awaiting") == "admin_send_withdraw_receipt":
        payload = u.pop("admin_withdraw_payload", None)
        file_id = update.message.photo[-1].file_id
        if payload:
            # post to payout channel and notify user
            try:
                await context.bot.send_photo(PAYOUT_HISTORY_CHANNEL, file_id, caption=f"order id: {payload['order_id']}, user: {payload['user_id']}, amount: {payload['amount']}, date: {payload['created_at']}")
            except Exception:
                pass
            # deduct balance if available
            target = payload["user_id"]
            amt = payload["amount"]
            if USERS.get(target) and USERS[target]["balance"] >= amt:
                USERS[target]["balance"] -= amt
            # remove from queue
            global WITHDRAW_REQUESTS
            WITHDRAW_REQUESTS[:] = [r for r in WITHDRAW_REQUESTS if r["order_id"] != payload["order_id"]]
            try:
                await context.bot.send_message(target, f"သင့်ငွေထုတ် {amt} ကို ပြီးစီးပါပြီ")
            except Exception:
                pass
            await update.message.reply_text("✅ အောင်မြင်ပါပြီ")
        u["awaiting"] = None
        return

    await update.message.reply_text("ပုံကို မလိုအပ်ပါ။")


# ---------------- MACHINE / CLAIM ----------------


async def machines_menu(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    ensure_user(uid)
    u = USERS[uid]
    now = int(time.time())
    lines = []
    
    await q.message.edit_text("⚙️ စက်များ")
    
    for idx in sorted(MACHINES.keys()):
        m = MACHINES[idx]
        owned = None
        for mi in u["machines"]:
            if mi["machine_no"] == idx and mi["expire_ts"] > now:
                owned = mi
                break
        mark = "✅" if owned else "❌"
        line = f"{mark} {m['key']}"
        if owned:
            exp_date = datetime.fromtimestamp(owned["expire_ts"]).strftime("%Y-%m-%d")
            elapsed = max(0, now - owned["last_claim_ts"])
            capped = min(elapsed, m["claim_interval_sec"])
            per_sec = m["daily_wcoin"] / 86400.0
            pending = int(per_sec * capped)
            line += f"\nExpired: {exp_date}\n({pending} WCoin pending)"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Claim", callback_data=f"claim::{idx}")]])
            await context.bot.send_message(q.message.chat_id, line, reply_markup=kb)
        else:
            lines.append(line)
            
    if lines:
        await context.bot.send_message(q.message.chat_id, "\n".join(lines))


async def handle_claim(q, context: ContextTypes.DEFAULT_TYPE, data: str):
    uid = q.from_user.id
    parts = data.split("::")
    if len(parts) != 2:
        await q.answer()
        return
    try:
        idx = int(parts[1])
    except Exception:
        await q.answer()
        return
    ensure_user(uid)
    now = int(time.time())
    mi = None
    for m in USERS[uid]["machines"]:
        if m["machine_no"] == idx:
            mi = m
            break
    if not mi or mi["expire_ts"] <= now:
        await q.message.reply_text("⏰ ဒီစက်က Expired ဖြစ်ပြီးသားပါ။")
        return
    elapsed = max(0, now - mi["last_claim_ts"])
    if elapsed < MACHINES[idx]["claim_interval_sec"]:
        remaining = MACHINES[idx]["claim_interval_sec"] - elapsed
        await q.answer(f"Claim မလုပ်ခင် {remaining//3600} နာရီ {remaining%3600//60} မိနစ် ကျန်ပါသည်", show_alert=True)
        return
    per_sec = MACHINES[idx]["daily_wcoin"] / 86400.0
    mined = int(per_sec * MACHINES[idx]["claim_interval_sec"])
    USERS[uid]["balance"] += mined
    mi["last_claim_ts"] = now
    await q.message.reply_text(f"✅ {MACHINES[idx]['key']} မှ {mined} WCoin ကို Claim လုပ်ပြီး Balance ထဲ ထည့်ပြီးပါပြီ!")


# ---------------- WITHDRAW FLOW ----------------


async def withdraw_menu(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    ensure_user(uid)
    u = USERS[uid]
    # require withdraw account
    if not u.get("withdraw_account"):
        u["awaiting"] = "withdraw_account"
        await q.message.reply_text("ငွေထုတ်အကောင့်သတ်မှတ်ရန် - ဖုန်းနံပါတ်တစ်ခု ထည့်ပေးပါ။",
                             reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_withdraw")]]))
        return
    # check rules
    ok, reason = can_withdraw(uid)
    if not ok:
        if reason == "need_rule1":
            await q.message.reply_text("အနည်းဆုံး50000ကျပ်သာထုတ်နိုင်ပါသည်")
            return
        if reason == "need_rule2":
            await q.message.reply_text(f"လူ ၁၀ယောက်ခေါ်ထားရန်လိုအပ်ပါသည်\nသင်၏ဖိတ်ခေါ်မှုများ: {u['referrals']}",
                                 reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ဖိတ်ခေါ်မည်", callback_data="invite")]]))
            return
        if reason == "need_rule3":
            await q.message.reply_text("စက်တစ်လုံးဝယ်ယူထားရန်လိုအပ်ပါသည်",
                                 reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("စက်ဝယ်မည်", callback_data="buy_machine")]]))
            return
    # all good -> confirm account
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("နံပါတ်ပြောင်းမည်", callback_data="change_withdraw_account")],
        [InlineKeyboardButton("သေချာပါသည်", callback_data="confirm_withdraw_account")]
    ])
    await q.message.reply_text(f"သင်၏ငွေထုတ်အကောင့် {u['withdraw_account']} သို့ထုတ်မည်သေချာပါသလား", reply_markup=kb)


async def prompt_withdraw_account(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    u = USERS[uid]
    u["awaiting"] = "withdraw_account"
    await q.message.reply_text("ဖုန်းနံပါတ် အသစ်ထည့်ပါ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_withdraw")]]))


async def prompt_withdraw_amount(q, context: ContextTypes.DEFAULT_TYPE):
    uid = q.from_user.id
    u = USERS[uid]
    u["awaiting"] = "withdraw_amount"
    await q.message.reply_text("ထုတ်ယူလိုသည့် ပမာဏအား ထည့်ပါ", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_withdraw")]]))


def can_withdraw(user_id: int):
    u = USERS[user_id]
    # (1) balance >= 50000
    if u["balance"] < 50000:
        return False, "need_rule1"
    # skip flag allows ignoring (2) and (3)
    if u.get("skip_verified"):
        return True, ""
    # (2) referrals >= 10
    if u["referrals"] < 10:
        return False, "need_rule2"
    # (3) bought at least one counting machine (Common/Epic/Premium by Wave)
    now = int(time.time())
    has_buy = False
    for m in u["machines"]:
        if m["expire_ts"] <= now:
            continue
        mn = m["machine_no"]
        if mn == 1:
            continue
        if mn == 4:
            if m["method"] == "wave":
                has_buy = True
                break
            else:
                continue
        has_buy = True
        break
    if not has_buy:
        return False, "need_rule3"
    return True, ""


# ---------------- ADMIN COMMANDS ----------------


async def cmd_add_b(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("You are not admin")
    args = context.args
    if len(args) != 3:
        return await update.message.reply_text("Usage: /Add_B (username|user_id) (amount) (y|n)")
    who, amt_txt, flag = args
    # resolve user id
    target_id = None
    if who.isdigit():
        target_id = int(who)
    else:
        for uid, u in USERS.items():
            if u["username"] == who.lstrip("@"):
                target_id = uid
                break
    if not target_id or target_id not in USERS:
        return await update.message.reply_text("User not found")
    try:
        amt = int(amt_txt)
    except Exception:
        return await update.message.reply_text("Invalid amount")
    USERS[target_id]["balance"] += amt
    if flag.lower() == "y":
        # ask admin for caption
        admin_u = USERS[update.effective_user.id]
        admin_u["awaiting"] = "admin_add_caption"
        admin_u["admin_add_payload"] = {"target": target_id, "amount": amt}
        await update.message.reply_text("Caption ပို့ပါ (မထည့်ချင်လျှင် space တစ်ချက်ပဲ ပို့)")
    else:
        await update.message.reply_text("Balance added silently.")


async def cmd_wreq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not WITHDRAW_REQUESTS:
        return await update.message.reply_text("No withdraw requests")
    lines = []
    for r in WITHDRAW_REQUESTS:
        lines.append(f"Order {r['order_id']} - User {r['user_id']} - {r['amount']} - {r['account']}")
    await update.message.reply_text("\n".join(lines))


async def cmd_wreq_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not context.args:
        return await update.message.reply_text("Usage: /Wreq_C order_id")
    try:
        oid = int(context.args[0])
    except Exception:
        return await update.message.reply_text("Invalid order id")
    rec = next((r for r in WITHDRAW_REQUESTS if r["order_id"] == oid), None)
    if not rec:
        return await update.message.reply_text("Order not found")
    # ask admin to send receipt photo
    admin_u = USERS[update.effective_user.id]
    admin_u["awaiting"] = "admin_send_withdraw_receipt"
    admin_u["admin_withdraw_payload"] = rec
    await update.message.reply_text("ပြေစာပုံပို့ပေးပါ")


async def cmd_mreq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not MACHINE_ORDERS:
        return await update.message.reply_text("No machine orders")
    lines = []
    for r in MACHINE_ORDERS:
        lines.append(f"Order {r['order_id']} - User {r['user_id']} - {MACHINES[r['machine_no']]['key']} - {r.get('transfer_no','N/A')}")
    await update.message.reply_text("\n".join(lines))


async def cmd_mreq_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not context.args:
        return await update.message.reply_text("Usage: /Mreq_C order_id")
    try:
        oid = int(context.args[0])
    except Exception:
        return await update.message.reply_text("Invalid order id")
    rec = next((r for r in MACHINE_ORDERS if r["order_id"] == oid), None)
    if not rec:
        return await update.message.reply_text("Order not found")
    # install machine for user
    uid = rec["user_id"]
    if can_buy_machine_now(uid, rec["machine_no"]):
        install_machine(uid, rec["machine_no"], method="wave")
        # remove order
        MACHINE_ORDERS[:] = [r for r in MACHINE_ORDERS if r["order_id"] != oid]
        try:
            await context.bot.send_message(uid, f"Order ID {oid} အောင်မြင်ပါပြီ ✅\n{MACHINES[rec['machine_no']]['key']} စက် ပေါင်းထည့်ပြီးပါပြီ။")
        except Exception:
            pass
        await update.message.reply_text("Done")
    else:
        await update.message.reply_text("User already owns this machine (active), cannot add.")


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not context.args:
        return await update.message.reply_text("Usage: /Skip user_id|username")
    who = context.args[0]
    target = None
    if who.isdigit():
        target = int(who)
    else:
        for uid, u in USERS.items():
            if u["username"] == who.lstrip("@"):
                target = uid
                break
    if not target or target not in USERS:
        return await update.message.reply_text("User not found")
    USERS[target]["skip_verified"] = True
    await update.message.reply_text(f"Skip applied for {who}")


async def cmd_total_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    await update.message.reply_text(f"Total users: {len(USERS)}")


async def cmd_mowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not context.args:
        return await update.message.reply_text("Usage: /Mowner machine_no")
    try:
        no = int(context.args[0])
    except Exception:
        return await update.message.reply_text("Invalid number")
    now = int(time.time())
    owners = []
    for uid, u in USERS.items():
        for m in u["machines"]:
            if m["machine_no"] == no and m["expire_ts"] > now:
                owners.append((uid, u["username"], u["balance"]))
                break
    if not owners:
        return await update.message.reply_text("No owners")
    lines = [f"{uid} @{name} balance={bal}" for uid, name, bal in owners]
    await update.message.reply_text("\n".join(lines))


async def cmd_topb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    top = sorted(USERS.items(), key=lambda kv: kv[1]["balance"], reverse=True)[:10]
    lines = [f"{i+1}. @{u['username']} - {u['balance']}" for i, (uid, u) in enumerate(top)]
    await update.message.reply_text("\n".join(lines))


async def cmd_topi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    top = sorted(USERS.items(), key=lambda kv: kv[1]["referrals"], reverse=True)[:10]
    lines = [f"{i+1}. @{u['username']} - {u['referrals']}" for i, (uid, u) in enumerate(top)]
    await update.message.reply_text("\n".join(lines))


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not context.args:
        return await update.message.reply_text("Usage: /About user_id|username")
    who = context.args[0]
    target = None
    if who.isdigit():
        target = int(who)
    else:
        for uid, u in USERS.items():
            if u["username"] == who.lstrip("@"):
                target = uid
                break
    if not target or target not in USERS:
        return await update.message.reply_text("User not found")
    u = USERS[target]
    now = int(time.time())
    machines = [MACHINES[m["machine_no"]]["key"] for m in u["machines"] if m["expire_ts"] > now]
    await update.message.reply_text(
        f"Username: @{u['username']}\nBalance: {u['balance']}\nMachines: {', '.join(machines) or 'None'}\nReferrals: {u['referrals']}"
    )


async def cmd_add_img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("Not admin")
    if not context.args:
        return await update.message.reply_text("Usage: /Add_img Basic|Common|Epic|Premium")
    name = context.args[0].capitalize()
    # admin will be prompted to upload photo next; we store desired name
    u = USERS[update.effective_user.id]
    u["awaiting"] = "admin_add_img"
    u["admin_img_target"] = name
    await update.message.reply_text(f"Send photo to set for {name}")


async def cmd_change_img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cmd_add_img(update, context)


# ---------------- UTIL FUNCTIONS ----------------


def active_machines_count(user_id: int) -> int:
    now = int(time.time())
    return sum(1 for m in USERS[user_id]["machines"] if m["expire_ts"] > now)


def total_daily_income(user_id: int) -> int:
    now = int(time.time())
    s = 0
    for m in USERS[user_id]["machines"]:
        if m["expire_ts"] > now:
            s += MACHINES[m["machine_no"]]["daily_wcoin"]
    return s


# ---------------- BOOT ----------------


def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # public handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router))
    application.add_handler(MessageHandler(filters.PHOTO, photo_message_router))

    # admin commands
    application.add_handler(CommandHandler("Add_B", cmd_add_b))
    application.add_handler(CommandHandler("Wreq", cmd_wreq))
    application.add_handler(CommandHandler("Wreq_C", cmd_wreq_c))
    application.add_handler(CommandHandler("Mreq", cmd_mreq))
    application.add_handler(CommandHandler("Mreq_C", cmd_mreq_c))
    application.add_handler(CommandHandler("Skip", cmd_skip))
    application.add_handler(CommandHandler("Total_user", cmd_total_user))
    application.add_handler(CommandHandler("Mowner", cmd_mowner))
    application.add_handler(CommandHandler("TopB", cmd_topb))
    application.add_handler(CommandHandler("TopI", cmd_topi))
    application.add_handler(CommandHandler("About", cmd_about))
    application.add_handler(CommandHandler("Add_img", cmd_add_img))
    application.add_handler(CommandHandler("Change_img", cmd_change_img))

    logger.info("Starting bot")
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
