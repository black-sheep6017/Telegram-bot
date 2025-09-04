from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import datetime

# ---------------- In-memory stores ----------------
users = {}  # {user_id: {...}}
withdrawal_requests = []  # [{"id":1,"user_id":..,"amount":..,"account":..}]
machine_requests = []  # [{"id":1,"user_id":..,"machine":..,"payment_number":..}]
order_counter = 1
machine_order_counter = 1

# Channels list
CHANNELS = ["@wave_mining_myanmar", "@anime_World_6017"]

# Conversation states
SET_NUMBER, WITHDRAW_AMOUNT, BUY_MACHINE_NUMBER, CLAIM_MACHINE = range(4)

# Admin IDs
ADMIN_IDS = [8461315389]

# Bonuses
NEW_USER_BONUS = 2000
REFERRAL_BONUS = 3000

# Machine definitions
MACHINES = [
    {"name": "Basic", "price": 0, "wcoin_per_day": 1000, "admin_confirm": False},
    {"name": "Common", "price": 5000, "wcoin_per_day": 2000, "admin_confirm": True},
    {"name": "Epic", "price": 8000, "wcoin_per_day": 3000, "admin_confirm": True},
    {"name": "Legend", "price": 12000, "wcoin_per_day": 4500, "admin_confirm": True},
    {"name": "Premium", "price": 30000, "wcoin_per_day": 9000, "admin_confirm": False}
]

# ---------------- Helper functions ----------------
def get_balance(user_id):
    return users.get(user_id, {}).get("balance", 0)

def is_admin(user_id):
    return user_id in ADMIN_IDS

async def check_all_channels(user_id, context):
    missing_channels = []
    for ch in CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ["left", "kicked"]:
                missing_channels.append(ch)
        except:
            missing_channels.append(ch)
    return len(missing_channels) == 0, missing_channels

async def send_main_menu(chat_id, context):
    keyboard = [
        ["💰 လက်ကျန်ငွေ", "👥 ဖိတ်ခေါ်မည်"],
        ["🛒 စက်ဝယ်ယူမည်", "🌑 စက်များ"],
        ["💸 ငွေထုတ်မည်"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(chat_id=chat_id, text="ရွေးချယ်ပါ:", reply_markup=markup)

# ---------------- /start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global order_counter
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args

    if user.id not in users:
        users[user.id] = {
            "balance": NEW_USER_BONUS,
            "payment_number": None,
            "invite_code": f"invite_{user.id}",
            "referrer": None,
            "referred_users": [],
            "machines": [],
            "machine_claims": [],
            "history": []
        }
        users[user.id]["history"].append(f"{NEW_USER_BONUS} MConi bonus for joining")

        # Handle referral
        if args and args[0].startswith("invite_"):
            ref_code = args[0]
            ref_id = int(ref_code.split("_")[1])
            if ref_id in users and ref_id != user.id:
                users[user.id]["referrer"] = ref_id
                users[ref_id]["referred_users"].append(user.id)
                users[ref_id]["balance"] += REFERRAL_BONUS
                users[ref_id]["history"].append(
                    f"{REFERRAL_BONUS} MConi from referral {user.username or user.full_name}"
                )

    # Check channels
    all_joined, missing = await check_all_channels(user.id, context)
    if not all_joined:
        btn = [[InlineKeyboardButton("✅ Check Join", callback_data="check_join")]]
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ You must join all channels to use this bot.\n"
                 + "\n".join(missing)
                 + "\nThen press Check.",
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return

    await send_main_menu(chat_id, context)

# ---------------- check join ----------------
async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    all_joined, missing = await check_all_channels(user_id, context)
    if all_joined:
        try:
            await query.message.delete()
        except:
            pass
        await send_main_menu(query.message.chat.id, context)
    else:
        await query.edit_message_text(
            f"⚠️ You still haven't joined:\n" + "\n".join(missing),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Check Join", callback_data="check_join")]])
        )
# ---------------- message handler ----------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text

    # init user if not exist
    if user_id not in users:
        users[user_id] = {
            "balance": NEW_USER_BONUS,
            "payment_number": None,
            "invite_code": f"invite_{user_id}",
            "referrer": None,
            "referred_users": [],
            "machines": [],
            "machine_claims": [],
            "history": []
        }

    # ----- Balance -----
    if text == "💰 လက်ကျန်ငွေ":
        balance = get_balance(user_id)
        await update.message.reply_text(f"💰 သင့်လက်ကျန်ငွေ: {balance} MConi")

    # ----- Invite -----
    elif text == "👥 ဖိတ်ခေါ်မည်":
        invite_link = f"https://t.me/{context.bot.username}?start={users[user_id]['invite_code']}"
        refs = len(users[user_id]["referred_users"])
        await update.message.reply_text(
            f"👥 Invite link: {invite_link}\n📌 သင့်ဖိတ်ခေါ်သူအရေအတွက်: {refs}"
        )

    # ----- Add/Change Payment Number -----
    elif text == "🏦 ငွေထုတ်အကောင့်":
        if users[user_id]["payment_number"]:
            await update.message.reply_text(
                f"🏦 သင့် Wave Pay အကောင့်: {users[user_id]['payment_number']}\n"
                f"ပြင်ဆင်လိုပါက /editNumber"
            )
        else:
            await update.message.reply_text("🏦 Wave Pay နံပါတ်ထည့်ပါ:")
            return SET_NUMBER

    # ----- Withdraw -----
    elif text == "💸 ငွေထုတ်မည်":
        balance = get_balance(user_id)
        if not users[user_id]["payment_number"]:
            await update.message.reply_text("⚠️ ငွေထုတ်အကောင့်မရှိပါ။ /editNumber ဖြင့် ထည့်ပါ")
            return
        min_withdraw = 50000
        await update.message.reply_text(
            f"💰 သင့်လက်ကျန်ငွေ: {balance} MConi\n"
            f"Minimum withdrawal: {min_withdraw} MCoin\n"
            f"ထုတ်ယူလိုသော ပမာဏကို ထည့်ပါ:"
        )
        return WITHDRAW_AMOUNT

# ---------------- Withdraw flow ----------------
async def set_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    number = update.message.text.strip()
    users[user_id]["payment_number"] = number
    await update.message.reply_text(f"✅ Wave Pay နံပါတ်သိမ်းပြီး: {number}")
    return ConversationHandler.END

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global order_counter
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
    except:
        await update.message.reply_text("⚠️ ဂဏန်းမမှန်ပါ")
        return WITHDRAW_AMOUNT

    min_withdraw = 50000
    if amount < min_withdraw:
        await update.message.reply_text(f"⚠️ Minimum withdrawal is {min_withdraw} MCoin")
        return ConversationHandler.END

    # Check referrals
    if len(users[user_id]["referred_users"]) < 10:
        await update.message.reply_text("⚠️ You need at least 10 referrals to withdraw")
        return ConversationHandler.END

    # Check machine buy requirement
    bought_machines = [
        m for m in users[user_id]["machines"]
        if m.get("admin_confirmed", False) and m.get("name") in ["Common", "Epic", "Legend"]
    ]
    if not bought_machines:
        await update.message.reply_text("⚠️ You must buy and activate at least one machine (Common/Epic/Legend)")
        return ConversationHandler.END

    users[user_id]["balance"] -= amount
    withdrawal_requests.append({
        "id": order_counter,
        "user_id": user_id,
        "amount": amount,
        "account": users[user_id]["payment_number"]
    })
    await update.message.reply_text(f"✅ Withdraw request submitted to admin (Order ID: {order_counter})")
    order_counter += 1
    return ConversationHandler.END

# ---------------- Machine Buy Flow ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    buttons = []
    message_text = "Available Machines:\n"
    for idx, m in enumerate(MACHINES):
        message_text += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(f"{m['name']} ({m['price']} MCoin)", callback_data=f"buy_{idx}")])
    await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(buttons))# ---------------- Callback handler ----------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # ----- Check Join -----
    if data == "check_join":
        await check_join(update, context)
        return

    # ----- Buy Machine -----
    elif data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine = MACHINES[idx]
        context.user_data["buy_machine_idx"] = idx
        await query.edit_message_text(
            f"You chose {machine['name']} ({machine['price']} MCoin)\n"
            "Send your payment/phone number to confirm purchase:"
        )
        return ADD_PAYMENT

    # ----- Confirm Buy -----
    elif data.startswith("confirm_buy_"):
        idx = context.user_data.get("buy_machine_idx")
        if idx is None:
            await query.edit_message_text("⚠️ Error: No machine selected")
            return
        machine = MACHINES[idx]
        # Add to user buy request for admin confirm
        order_id = order_counter
        context.user_data["buy_order_id"] = order_id
        order_counter += 1

        users[user_id].setdefault("buy_requests", []).append({
            "order_id": order_id,
            "machine_idx": idx,
            "payment_number": users[user_id].get("payment_number"),
            "confirmed": False
        })

        await query.edit_message_text(
            f"✅ Your request for {machine['name']} is sent to admin.\n"
            f"Order ID: {order_id}"
        )

# ---------------- Admin Functions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Dismiss_All <username or user_id>")
        return
    target = context.args[0]
    # Find user
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, udata in users.items():
            if udata.get("username") == target:
                target_id = uid
                break
    if target_id and target_id in users:
        # Remove pending withdraw requirements except minimum amount
        users[target_id]["referred_users"] = users[target_id]["referred_users"][:10]
        users[target_id]["machines"] = [m for m in users[target_id]["machines"] if m.get("name")=="Basic"]
        await update.message.reply_text(f"✅ Dismissed referral and machine requirements for {target}")
    else:
        await update.message.reply_text("User not found")

async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "Pending machine buy requests:\n"
    for uid, udata in users.items():
        for req in udata.get("buy_requests", []):
            if not req["confirmed"]:
                machine = MACHINES[req["machine_idx"]]
                text += f"Order {req['order_id']} | Machine: {machine['name']} | Payment: {req['payment_number']}\n"
    await update.message.reply_text(text or "No pending buy requests")

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(context.args[0])
    found = False
    for uid, udata in users.items():
        for req in udata.get("buy_requests", []):
            if req["order_id"] == order_id and not req["confirmed"]:
                req["confirmed"] = True
                machine = MACHINES[req["machine_idx"]]
                # Add machine to user's active machines
                udata.setdefault("machines", []).append({
                    "name": machine["name"],
                    "wcoin_per_day": machine["wcoin_per_day"],
                    "last_claim": None,
                    "expire_date": datetime.datetime.now() + datetime.timedelta(days=30),
                    "admin_confirmed": True,
                    "mine_left": machine["wcoin_per_day"]
                })
                await update.message.reply_text(f"✅ Order {order_id} confirmed. {machine['name']} added to user.")
                found = True
                break
        if found:
            break
    if not found:
        await update.message.reply_text("Order ID not found or already confirmed")
# ---------------- User Machine Functions ----------------
async def show_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "Your active machines:\n"
    now = datetime.datetime.now()
    for idx, m in enumerate(users[user_id].get("machines", [])):
        status = "Active" if m.get("admin_confirmed") else "Pending"
        expire = m.get("expire_date").strftime("%Y-%m-%d")
        last_claim = m.get("last_claim").strftime("%Y-%m-%d %H:%M") if m.get("last_claim") else "Never"
        text += (f"{idx+1}. {m['name']} | Status: {status} | Mine Left: {m['mine_left']} | "
                 f"Last Claim: {last_claim} | Expire: {expire}\n")
        if status == "Active":
            text += f"   [Claim] /claim_{idx}\n"
    await update.message.reply_text(text or "No active machines.")

async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cmd = update.message.text
    if not cmd.startswith("/claim_"):
        return
    idx = int(cmd.split("_")[1])
    machines = users[user_id].get("machines", [])
    if idx >= len(machines):
        await update.message.reply_text("Invalid machine index")
        return
    m = machines[idx]
    now = datetime.datetime.now()
    last_claim = m.get("last_claim")
    expire = m.get("expire_date")
    if expire < now:
        await update.message.reply_text(f"{m['name']} has expired.")
        machines.pop(idx)
        return
    if last_claim and (now - last_claim).total_seconds() < 12*3600:
        await update.message.reply_text("⚠️ You can claim only once per 12 hours")
        return
    # Add mined WCoin to user balance
    mine_amount = m["mine_left"]
    users[user_id]["balance"] += mine_amount
    m["mine_left"] = m["wcoin_per_day"]  # reset mine left after claim
    m["last_claim"] = now
    await update.message.reply_text(f"✅ Claimed {mine_amount} WCoin from {m['name']}. Balance updated.")

# ---------------- Buy Machine Flow ----------------
async def buy_machine_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "Available Machines:\n"
    buttons = []
    for idx, m in enumerate(MACHINES):
        text += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(m['name'], callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def add_payment_for_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payment_number = update.message.text.strip()
    users[user_id]["payment_number"] = payment_number
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        await update.message.reply_text("⚠️ No machine selected")
        return
    machine = MACHINES[idx]
    # Send confirm button
    btn = [[InlineKeyboardButton("Confirm", callback_data=f"confirm_buy_{idx}")]]
    await update.message.reply_text(
        f"Machine: {machine['name']} ({machine['price']} MCoin)\nPayment Number: {payment_number}\nPress Confirm to send request to admin",
        reply_markup=InlineKeyboardMarkup(btn)
    )
# ---------------- Buy Machine Callback ----------------
async def buy_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        context.user_data["buy_machine_idx"] = idx
        await query.edit_message_text(f"Send your payment number for {MACHINES[idx]['name']} ({MACHINES[idx]['price']} MCoin)")

    elif data.startswith("confirm_buy_"):
        idx = int(data.split("_")[2])
        machine = MACHINES[idx]
        payment_number = users[user_id].get("payment_number")
        if not payment_number:
            await query.edit_message_text("⚠️ Payment number not set")
            return
        # create admin request
        order_id = len(withdrawal_requests) + 1
        withdrawal_requests.append({
            "id": order_id,
            "user_id": user_id,
            "machine_idx": idx,
            "payment_number": payment_number,
            "confirmed": False
        })
        await query.edit_message_text(f"✅ Your order {order_id} for {machine['name']} has been sent to admin for confirmation.")

# ---------------- Withdraw Flow ----------------
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = users[user_id]["balance"]
    min_withdraw = 50000
    if balance < min_withdraw:
        await update.message.reply_text(f"⚠️ Minimum withdrawal is {min_withdraw} MCoin")
        return
    if users[user_id].get("referrals", 0) < 10:
        await update.message.reply_text("⚠️ You need at least 10 referrals to withdraw")
        return
    # check admin-confirmed machine
    machine_ok = any(m.get("admin_confirmed") for m in users[user_id].get("machines", []))
    if not machine_ok:
        await update.message.reply_text("⚠️ You must buy and have admin-confirmed at least one machine to withdraw")
        return
    await update.message.reply_text(f"💰 Your balance: {balance} MCoin\nEnter amount to withdraw (min {min_withdraw}):")
    return WITHDRAW_AMOUNT

async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
    except:
        await update.message.reply_text("⚠️ Invalid number")
        return WITHDRAW_AMOUNT
    balance = users[user_id]["balance"]
    if amount < 50000:
        await update.message.reply_text("⚠️ Minimum withdrawal is 50000 MCoin")
        return ConversationHandler.END
    if amount > balance:
        await update.message.reply_text("⚠️ Not enough balance")
        return ConversationHandler.END
    # store withdraw request
    order_id = len(withdrawal_requests) + 1
    withdrawal_requests.append({
        "id": order_id,
        "user_id": user_id,
        "amount": amount,
        "confirmed": False
    })
    await update.message.reply_text(f"✅ Withdraw request #{order_id} submittted to admin")
    return ConversationHandler.END
# ---------------- Admin Functions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <username_or_userid>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, data in users.items():
            if data.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return
    # dismiss all restrictions
    user_data = users[target_id]
    user_data["dismissed"] = True
    await update.message.reply_text(f"✅ Dismissed restrictions for {target}")

async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    text = "Machine Buy Requests:\n"
    for r in withdrawal_requests:
        if "machine_idx" in r and not r["confirmed"]:
            user = users[r["user_id"]]
            machine = MACHINES[r["machine_idx"]]
            text += f"Order ID:{r['id']} | Machine:{machine['name']} | Payment:{r['payment_number']}\n"
    await update.message.reply_text(text)

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in withdrawal_requests if r["id"] == order_id and "machine_idx" in r), None)
    if not req:
        await update.message.reply_text("Request not found")
        return
    req["confirmed"] = True
    user_id = req["user_id"]
    machine_idx = req["machine_idx"]
    # add machine to user's machines
    machine_data = MACHINES[machine_idx].copy()
    machine_data.update({"active": True, "admin_confirmed": True, "last_claim": None,
                         "start_date": datetime.datetime.now(),
                         "expire_date": datetime.datetime.now() + datetime.timedelta(days=30)})
    users[user_id].setdefault("machines", []).append(machine_data)
    await update.message.reply_text(f"✅ Machine {machine_data['name']} assigned to user {user_id}")

# ---------------- Machine Claim ----------------
async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.datetime.now()
    user_machines = users[user_id].get("machines", [])
    if not user_machines:
        await update.message.reply_text("No active machines")
        return
    text = ""
    for idx, m in enumerate(user_machines):
        expire_date = m["expire_date"]
        last_claim = m.get("last_claim")
        can_claim = False
        if last_claim is None or (now - last_claim).total_seconds() >= 12 * 3600:
            can_claim = True
        text += f"{idx+1}. {m['name']} | Daily: {m['wcoin_per_day']} | Exp: {expire_date.strftime('%Y-%m-%d')}\n"
        if can_claim:
            text += f"💎 Can claim now! Use /claim {idx+1}\n"
    await update.message.reply_text(text)

async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /claim <machine_number>")
        return
    m_idx = int(args[0]) - 1
    machines_list = users[user_id].get("machines", [])
    if m_idx < 0 or m_idx >= len(machines_list):
        await update.message.reply_text("Invalid machine number")
        return
    m = machines_list[m_idx]
    now = datetime.datetime.now()
    last_claim = m.get("last_claim")
    if last_claim and (now - last_claim).total_seconds() < 12 * 3600:
        await update.message.reply_text("⚠️ Cannot claim yet, 12h not passed")
        return
    # add wcoin
    users[user_id]["balance"] += m["wcoin_per_day"]
    m["last_claim"] = now
    await update.message.reply_text(f"✅ Claimed {m['wcoin_per_day']} WCoin from {m['name']}")
# ---------------- Buy Machine ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "Available Machines:\n"
    buttons = []
    for idx, m in enumerate(MACHINES):
        text += f"{idx+1}. {m['name']} - Price: {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(m['name'], callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def buy_machine_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        await update.message.reply_text("⚠️ Error: machine not selected")
        return
    machine = MACHINES[idx]
    text = update.message.text.strip()
    # save payment number
    context.user_data["buy_machine_payment"] = text
    # confirm button
    btn = [[InlineKeyboardButton("✅ Confirm Purchase", callback_data=f"confirm_buy_{idx}")]]
    await update.message.reply_text(
        f"You are buying {machine['name']} ({machine['price']} MCoin). Payment/Phone: {text}\nPress Confirm to submit request.",
        reply_markup=InlineKeyboardMarkup(btn)
    )

async def buy_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        context.user_data["buy_machine_idx"] = idx
        await query.edit_message_text(f"Send your payment/phone number for {MACHINES[idx]['name']} ({MACHINES[idx]['price']} MCoin)")
    elif data.startswith("confirm_buy_"):
        idx = int(data.split("_")[2])
        payment = context.user_data.get("buy_machine_payment")
        if not payment:
            await query.edit_message_text("⚠️ Payment not provided")
            return
        # send request to admin
        order_id = order_counter
        global order_counter
        order_counter += 1
        withdrawal_requests.append({
            "id": order_id,
            "user_id": user_id,
            "machine_idx": idx,
            "payment_number": payment,
            "confirmed": False
        })
        await query.edit_message_text(f"✅ Purchase request submitted. Your Order ID: {order_id}")
        context.user_data.pop("buy_machine_idx", None)
        context.user_data.pop("buy_machine_payment", None)

# ---------------- Machine expiration check ----------------
async def check_expired_machines():
    now = datetime.datetime.now()
    for user_data in users.values():
        machines_list = user_data.get("machines", [])
        for m in machines_list[:]:
            if now >= m["expire_date"]:
                machines_list.remove(m)

# ---------------- Bot Setup ----------------
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
app = ApplicationBuilder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
    states={
        SET_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_number)],
        WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
        BUY_MACHINE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_machine_number)],
    },
    fallbacks=[CommandHandler("editNumber", edit_number)]
)

# ---------------- Command Handlers ----------------
app.add_handler(CommandHandler("start", start))
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(callback_handler))
app.add_handler(CallbackQueryHandler(buy_machine_callback))
app.add_handler(CommandHandler("editNumber", edit_number))
app.add_handler(CommandHandler("Wreq", wreq))
app.add_handler(CommandHandler("Wreq_C", wreq_c))
app.add_handler(CommandHandler("Add_B", add_b))
app.add_handler(CommandHandler("Dismiss_All", dismiss_all))
app.add_handler(CommandHandler("Req_Mbuy", req_mbuy))
app.add_handler(CommandHandler("Access_buy", access_buy))
app.add_handler(CommandHandler("claim_machine", claim_machine))
app.add_handler(CommandHandler("claim", claim_command))
# ---------------- Admin functions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <username|user_id>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, udata in users.items():
            if udata.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return
    # dismiss requirements
    users[target_id]["balance"] = max(users[target_id]["balance"], 50000)
    users[target_id]["referrals"] = 10
    machines_list = users[target_id].get("machines", [])
    for m in machines_list:
        if not m.get("admin_confirmed", True):
            m["admin_confirmed"] = True
    await update.message.reply_text(f"✅ All restrictions dismissed for {target}")

async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "Pending Machine Purchases:\n"
    for r in withdrawal_requests:
        if r.get("machine_idx") is not None and not r.get("confirmed"):
            user_id = r["user_id"]
            machine_no = r["machine_idx"]
            payment = r["payment_number"]
            text += f"Order ID: {r['id']} | Machine: {MACHINES[machine_no]['name']} | Payment: {payment}\n"
    await update.message.reply_text(text or "No pending machine requests")

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in withdrawal_requests if r["id"] == order_id), None)
    if not req:
        await update.message.reply_text("Order not found")
        return
    user_id = req["user_id"]
    machine_idx = req["machine_idx"]
    expire_date = datetime.datetime.now() + datetime.timedelta(days=30)
    machine_data = {
        "machine_idx": machine_idx,
        "name": MACHINES[machine_idx]["name"],
        "wcoin_per_day": MACHINES[machine_idx]["wcoin_per_day"],
        "last_claim": datetime.datetime.now(),
        "expire_date": expire_date,
        "admin_confirmed": True
    }
    users[user_id].setdefault("machines", []).append(machine_data)
    req["confirmed"] = True
    await update.message.reply_text(f"✅ Machine {MACHINES[machine_idx]['name']} assigned to user {user_id}")
    await context.bot.send_message(chat_id=user_id, text=f"✅ Your machine {MACHINES[machine_idx]['name']} is now active! Order ID: {order_id}")

# ---------------- Claiming machines ----------------
async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    machines_list = users[user_id].get("machines", [])
    text = "Your Active Machines:\n"
    buttons = []
    for idx, m in enumerate(machines_list):
        text += f"{idx+1}. {m['name']} | Expire: {m['expire_date'].strftime('%Y-%m-%d')}\n"
        buttons.append([InlineKeyboardButton(f"Claim {m['name']}", callback_data=f"claim_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("claim_"):
        idx = int(data.split("_")[1])
        machines_list = users[user_id].get("machines", [])
        if idx >= len(machines_list):
            await query.edit_message_text("⚠️ Machine not found")
            return
        m = machines_list[idx]
        now = datetime.datetime.now()
        delta = now - m["last_claim"]
        if delta.total_seconds() < 12*3600:
            await query.edit_message_text("⚠️ You can only claim every 12 hours")
            return
        days_passed = delta.total_seconds() // (12*3600)
        earned = int(days_passed * m["wcoin_per_day"] / 2)  # half per 12h
        users[user_id]["balance"] += earned
        m["last_claim"] = now
        await query.edit_message_text(f"✅ You claimed {earned} WCoin from {m['name']}")
# ---------------- Buy Machine flow ----------------
async def buy_machine_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    # Show machine list
    msg_text = "Available Machines:\n"
    buttons = []
    for idx, m in enumerate(MACHINES):
        msg_text += f"{idx+1}. {m['name']} - Price: {m['price']} WCoin/day\n"
        buttons.append([InlineKeyboardButton(f"{m['name']}", callback_data=f"buy_{idx}")])
    await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(buttons))

async def buy_machine_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine = MACHINES[idx]
        context.user_data["buy_machine_idx"] = idx
        await query.edit_message_text(
            f"You selected {machine['name']} (Price: {machine['price']} WCoin).\nSend your payment/phone number to proceed."
        )

async def buy_machine_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        await update.message.reply_text("⚠️ No machine selected")
        return
    machine = MACHINES[idx]
    # Save payment number and create order
    order_id = len(withdrawal_requests) + 1
    withdrawal_requests.append({
        "id": order_id,
        "user_id": user_id,
        "machine_idx": idx,
        "payment_number": text,
        "confirmed": False
    })
    await update.message.reply_text(f"✅ Your order ID is {order_id}. Awaiting admin confirmation.")
# ---------------- Claim Machine ----------------
async def user_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = users.get(user_id, {})
    machines_owned = user_data.get("machines", [])
    if not machines_owned:
        await update.message.reply_text("You don't have any active machines.")
        return
    msg_text = "Your Active Machines:\n"
    buttons = []
    for idx, m in enumerate(machines_owned):
        exp = m.get("expire_date")
        msg_text += f"{idx+1}. {m['name']} | Expire: {exp}\n"
        buttons.append([InlineKeyboardButton(f"Claim {m['name']}", callback_data=f"claim_{idx}")])
    await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(buttons))

async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("claim_"):
        idx = int(data.split("_")[1])
        machine = users[user_id]["machines"][idx]
        now = datetime.datetime.now()
        last_claim = machine.get("last_claim", machine.get("start_date", now))
        diff = (now - last_claim).total_seconds()
        if diff < 12 * 3600:  # 12 hours not passed
            await query.edit_message_text("⏳ Claim not ready yet. Wait for 12 hours from last claim.")
            return
        # Add WCoin to user balance
        amount = machine["wcoin_per_day"] // 2  # half day reward
        users[user_id]["balance"] += amount
        machine["last_claim"] = now
        await query.edit_message_text(f"✅ Claimed {amount} WCoin from {machine['name']}.")                                                
# ---------------- Admin Functions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <username or user_id>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, udata in users.items():
            if udata.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return
    # Remove referral & machine restrictions for withdraw
    udata = users[target_id]
    udata["referrals"] = 0
    for m in udata.get("machines", []):
        m["admin_confirm"] = True
    await update.message.reply_text(f"Dismissed restrictions for user {target}")

# ---------------- Request Machine Buy ----------------
machine_buy_requests = []

async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not machine_buy_requests:
        await update.message.reply_text("No machine buy requests.")
        return
    msg = "Machine Buy Requests:\n"
    for req in machine_buy_requests:
        msg += f"Order ID: {req['order_id']} | Machine: {req['machine_name']} | Payment: {req['payment_number']} | User: {req['user_id']}\n"
    await update.message.reply_text(msg)

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in machine_buy_requests if r["order_id"] == order_id), None)
    if not req:
        await update.message.reply_text("Request not found")
        return
    # Confirm machine buy
    user_id = req["user_id"]
    machine_name = req["machine_name"]
    for m in users[user_id]["machines"]:
        if m["name"] == machine_name:
            m["admin_confirm"] = True
            break
    machine_buy_requests.remove(req)
    await update.message.reply_text(f"Order {order_id} confirmed and machine activated for user {user_id}")
# ---------------- User Buy Machine ----------------
order_counter_machine = 1

async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    keyboard = []
    text = "Available Machines:\n"
    for idx, m in enumerate(machines):
        text += f"{idx+1}. {m['name']} - {m['price']} MCoin - {m['wcoin_per_day']} WCoin/day\n"
        keyboard.append([InlineKeyboardButton(m['name'], callback_data=f"buy_{idx}")])
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    idx = int(query.data.split("_")[1])
    machine = machines[idx]

    if machine["price"] <= users[user_id]["balance"] or not machine["admin_confirm"]:
        # Premium machine can buy directly
        if machine["name"] == "Premium" and users[user_id]["balance"] >= machine["price"]:
            users[user_id]["balance"] -= machine["price"]
            users[user_id]["machines"].append({
                "name": machine["name"],
                "active": True,
                "start_time": datetime.datetime.now(),
                "last_claim": datetime.datetime.now(),
                "expire_time": datetime.datetime.now() + datetime.timedelta(days=30),
                "admin_confirm": True
            })
            await query.edit_message_text(f"✅ You bought {machine['name']} directly. Balance deducted {machine['price']} MCoin.")
        else:
            # Ask for payment number for admin confirm machines
            context.user_data["buy_machine_idx"] = idx
            await query.edit_message_text(f"Send your payment/phone number for {machine['name']} ({machine['price']} MCoin)")
    else:
        await query.edit_message_text("⚠️ Not enough balance to buy this machine.")

async def buy_machine_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        return
    machine = machines[idx]
    payment_number = update.message.text.strip()
    global order_counter_machine
    order_id = order_counter_machine
    order_counter_machine += 1

    machine_buy_requests.append({
        "order_id": order_id,
        "user_id": user_id,
        "machine_name": machine["name"],
        "payment_number": payment_number
    })
    await update.message.reply_text(f"✅ Your request for {machine['name']} is submitted. Order ID: {order_id}. Admin will confirm.")
    context.user_data["buy_machine_idx"] = None
# ---------------- Machine Claim ----------------
async def show_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or not users[user_id]["machines"]:
        await update.message.reply_text("No active machines.")
        return

    text = "Your Machines:\n"
    keyboard = []
    for idx, m in enumerate(users[user_id]["machines"]):
        status = "Active" if m["active"] else "Expired"
        text += f"{idx+1}. {m['name']} - {status} - Exp: {m['expire_time'].strftime('%Y-%m-%d')}\n"
        if m["active"]:
            keyboard.append([InlineKeyboardButton(f"Claim {m['name']}", callback_data=f"claim_{idx}")])
    if keyboard:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text)

async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    idx = int(query.data.split("_")[1])
    machine = users[user_id]["machines"][idx]

    if not machine["active"]:
        await query.edit_message_text(f"{machine['name']} is expired.")
        return

    now = datetime.datetime.now()
    diff = now - machine["last_claim"]
    if diff.total_seconds() < 12*3600:
        await query.edit_message_text("⚠️ You can claim only every 12 hours.")
        return

    # Add WCoin to balance
    users[user_id]["balance"] += machine["wcoin_per_day"]
    machine["last_claim"] = now

    # Check expiry
    if now >= machine["expire_time"]:
        machine["active"] = False
        await query.edit_message_text(f"✅ Claimed {machine['wcoin_per_day']} WCoin. {machine['name']} expired.")
    else:
        await query.edit_message_text(f"✅ Claimed {machine['wcoin_per_day']} WCoin from {machine['name']}.\nNext claim after 12 hours.")
# ---------------- Machine Buy Flow ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # list machines
    buttons = []
    msg = "Select a machine to buy:\n"
    for idx, m in enumerate(machines):
        msg += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(m['name'], callback_data=f"buy_{idx}")])
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))

async def buy_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine = machines[idx]
        context.user_data["buy_machine_idx"] = idx

        # premium machine can buy from balance
        if machine["name"].lower() == "premium":
            balance = get_balance(user_id)
            if balance < machine["price"]:
                await query.edit_message_text(f"⚠️ Insufficient balance for {machine['name']}")
                return
            users[user_id]["balance"] -= machine["price"]
            users[user_id]["machines"].append({"machine": machine["name"], "active": True, "start": datetime.datetime.now(), "last_claim": datetime.datetime.now()})
            await query.edit_message_text(f"✅ Purchased {machine['name']} from balance.")
            return

        # other machines require phone/payment input
        await query.edit_message_text(f"Send your payment number for {machine['name']} ({machine['price']} MCoin)")

# Next step: handle payment number input     
# ---------------- Receive Payment Number for Machine ----------------
async def machine_payment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        await update.message.reply_text("⚠️ Error: No machine selected.")
        return ConversationHandler.END

    machine = machines[idx]
    payment_number = update.message.text.strip()
    context.user_data["payment_number"] = payment_number

    # create order
    global order_counter
    order_id = order_counter
    order_counter += 1

    buy_machine_list.append({
        "order_id": order_id,
        "user_id": user_id,
        "machine_idx": idx,
        "payment_number": payment_number,
        "confirmed": False
    })

    await update.message.reply_text(
        f"✅ Your order id is {order_id} for {machine['name']} ({machine['price']} MCoin).\n"
        f"Admin will confirm your purchase."
    )
    return ConversationHandler.END

# ---------------- Claim Machine ----------------
async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_machines = users[user_id].get("machines", [])
    now = datetime.datetime.now()
    msg = "🔹 Active Machines:\n"
    buttons = []

    for idx, m in enumerate(user_machines):
        machine_name = m["machine"]
        last_claim = m["last_claim"]
        active = m["active"]
        expire_date = m["start"] + datetime.timedelta(days=30)
        status = "Active" if active else "Expired"
        msg += f"{idx+1}. {machine_name} | Status: {status} | Expire: {expire_date.date()}\n"
        if active and (now - last_claim).total_seconds() >= 12*3600:
            buttons.append([InlineKeyboardButton(f"Claim {machine_name}", callback_data=f"claim_{idx}")])

    if not buttons:
        await update.message.reply_text(msg + "\nNo machines available for claim now.")
        return

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))

async def claim_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if not data.startswith("claim_"):
        return

    idx = int(data.split("_")[1])
    m = users[user_id]["machines"][idx]
    machine_name = m["machine"]
    now = datetime.datetime.now()
    last_claim = m["last_claim"]

    # check 12 hour cooldown
    if (now - last_claim).total_seconds() < 12*3600:
        await query.edit_message_text(f"⚠️ {machine_name} is not ready for claim yet.")
        return

    # compute coins based on machine type
    machine_info = next((x for x in machines if x["name"] == machine_name), None)
    if not machine_info:
        await query.edit_message_text("⚠️ Error fetching machine info.")
        return

    wcoin_amount = machine_info["wcoin_per_day"] // 2  # half-day per 12h
    users[user_id]["balance"] += wcoin_amount
    m["last_claim"] = now

    await query.edit_message_text(f"✅ {wcoin_amount} WCoin claimed from {machine_name}.\nYour balance: {get_balance(user_id)} WCoin")

# ---------------- Admin: View Machine Requests ----------------
async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not buy_machine_list:
        await update.message.reply_text("No machine buy requests.")
        return
    text = "Machine Buy Requests:\n"
    for o in buy_machine_list:
        user = users[o["user_id"]]
        m_idx = o["machine_idx"]
        m_name = machines[m_idx]["name"]
        text += f"Order ID:{o['order_id']} | User:{user.get('username') or o['user_id']} | Machine:{m_name} | Payment:{o['payment_number']} | Confirmed:{o['confirmed']}\n"
    await update.message.reply_text(text)

# ---------------- Admin: Confirm Buy ----------------
async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    order = next((x for x in buy_machine_list if x["order_id"] == order_id), None)
    if not order:
        await update.message.reply_text("Order not found.")
        return
    order["confirmed"] = True
    user_id = order["user_id"]
    m_idx = order["machine_idx"]
    machine_name = machines[m_idx]["name"]
    users[user_id]["machines"].append({"machine": machine_name, "active": True, "start": datetime.datetime.now(), "last_claim": datetime.datetime.now()})
    await update.message.reply_text(f"✅ Machine {machine_name} assigned to user {user_id}.")
# ---------------- Withdraw with Conditions ----------------
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        amount = int(text)
    except:
        await update.message.reply_text("⚠️ ဂဏန်းမမှန်ပါ။")
        return WITHDRAW_AMOUNT

    # Minimum check
    MIN_WITHDRAW = 50000
    if amount < MIN_WITHDRAW:
        await update.message.reply_text(f"⚠️ Minimum withdrawal is {MIN_WITHDRAW} MCoin.")
        return WITHDRAW_AMOUNT

    # Referral check
    if users[user_id].get("referrals", 0) < 10:
        await update.message.reply_text("⚠️ You need at least 10 referrals to withdraw.")
        return WITHDRAW_AMOUNT

    # Check machine buy & admin confirmed
    user_machines = users[user_id].get("machines", [])
    has_valid_machine = any(m["active"] for m in user_machines if m.get("admin_confirm", True))
    if not has_valid_machine:
        await update.message.reply_text("⚠️ You must buy and have an admin-confirmed machine to withdraw.")
        return WITHDRAW_AMOUNT

    # Deduct balance and send request
    if amount > get_balance(user_id):
        await update.message.reply_text("⚠️ Not enough balance.")
        return ConversationHandler.END

    users[user_id]["balance"] -= amount
    global order_counter
    order_id = order_counter
    order_counter += 1

    withdrawal_requests.append({
        "id": order_id,
        "user_id": user_id,
        "amount": amount,
        "account": users[user_id]["payment_number"]
    })

    await update.message.reply_text(f"✅ Withdrawal request {amount} MCoin submitted (Order ID: {order_id}). Admin will confirm.")
    return ConversationHandler.END

# ---------------- Admin: Dismiss All ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Dismiss_All <user_id or username>")
        return
    target = context.args[0]

    # Find user
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, u in users.items():
            if u.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found.")
        return

    # Dismiss conditions (referrals and machine buy requirement)
    u = users[target_id]
    u["referrals"] = 0
    u["machines"] = [m for m in u.get("machines", []) if m.get("admin_confirm", False)]
    await update.message.reply_text(f"✅ All referral and unconfirmed machine requirements dismissed for user {target_id}.")
# ---------------- Machine purchase ----------------
order_counter = 1
buy_requests = []  # {order_id, user_id, machine_idx, payment_number, confirmed}

async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    keyboard = []
    text_msg = "🛒 Available Machines:\n"
    for idx, m in enumerate(machines):
        text_msg += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        keyboard.append([InlineKeyboardButton(m['name'], callback_data=f"buy_{idx}")])
    await update.message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine = machines[idx]
        context.user_data["buy_machine_idx"] = idx
        await query.edit_message_text(f"{machine['name']} price: {machine['price']} MCoin\nSend your payment/phone number:")

async def confirm_machine_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        await update.message.reply_text("Select machine first.")
        return
    global order_counter
    machine = machines[idx]
    if machine['price'] <= users[user_id]['balance'] and not machine['admin_confirm']:
        # Premium or free machine, deduct balance
        users[user_id]['balance'] -= machine['price']
        users[user_id]['machines'].append({
            "idx": idx,
            "name": machine['name'],
            "active": True,
            "start_time": datetime.datetime.now(),
            "last_claim": datetime.datetime.now(),
            "expire_time": datetime.datetime.now() + datetime.timedelta(days=30)
        })
        await update.message.reply_text(f"✅ Bought {machine['name']} successfully!")
        return
    # For machines requiring admin
    buy_requests.append({
        "order_id": order_counter,
        "user_id": user_id,
        "machine_idx": idx,
        "payment_number": text,
        "confirmed": False
    })
    await update.message.reply_text(f"✅ Request submitted! Your order id is {order_counter}")
    order_counter += 1               
                                                                                    # ---------------- Admin Functions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <user_id or username>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, udata in users.items():
            if udata.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return
    # reset withdraw conditions except minimum
    users[target_id]['referrals'] = 0
    users[target_id]['machines'] = []
    await update.message.reply_text(f"✅ Dismissed withdraw requirements for {target}")

async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not buy_requests:
        await update.message.reply_text("No pending machine buy requests")
        return
    text = "Pending machine buy requests:\n"
    for r in buy_requests:
        user = users[r['user_id']]
        machine = machines[r['machine_idx']]
        text += f"Order {r['order_id']} | {machine['name']} | Payment: {r['payment_number']} | User: {user.get('username') or r['user_id']}\n"
    await update.message.reply_text(text)

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in buy_requests if r['order_id']==order_id), None)
    if not req:
        await update.message.reply_text("Order not found")
        return
    user_id = req['user_id']
    idx = req['machine_idx']
    machine = machines[idx]
    users[user_id]['machines'].append({
        "idx": idx,
        "name": machine['name'],
        "active": True,
        "start_time": datetime.datetime.now(),
        "last_claim": datetime.datetime.now(),
        "expire_time": datetime.datetime.now() + datetime.timedelta(days=30)
    })
    req['confirmed'] = True
    await update.message.reply_text(f"✅ Machine {machine['name']} assigned to user {user_id}")
# ---------------- User Machine Functions ----------------
async def buy_machine_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = []
    text = "Available Machines:\n"
    for idx, m in enumerate(machines):
        text += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        keyboard.append([InlineKeyboardButton(f"{m['name']} ({m['price']})", callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_machine_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine = machines[idx]
        context.user_data['buy_machine_idx'] = idx
        await query.edit_message_text(
            f"You selected {machine['name']} ({machine['price']} MCoin).\nSend your payment/phone number."
        )

async def buy_machine_receive_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    idx = context.user_data.get('buy_machine_idx')
    if idx is None:
        await update.message.reply_text("Please select a machine first.")
        return
    payment_number = update.message.text.strip()
    order_id = order_counter
    global order_counter
    order_counter += 1
    buy_requests.append({
        "order_id": order_id,
        "user_id": user_id,
        "machine_idx": idx,
        "payment_number": payment_number,
        "confirmed": False
    })
    machine = machines[idx]
    await update.message.reply_text(
        f"✅ Your order for {machine['name']} is submitted.\nOrder ID: {order_id}\nAdmin will confirm shortly."
    )
# ---------------- Machine Claim / Expire ----------------
async def user_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_machines = [m for m in users[user_id].get("machines", []) if m["active"]]
    if not user_machines:
        await update.message.reply_text("You have no active machines.")
        return
    text = "Your Active Machines:\n"
    keyboard = []
    for idx, m in enumerate(user_machines):
        expire_str = m['expire_date'].strftime('%Y-%m-%d')
        text += f"{idx+1}. {m['name']} | Exp: {expire_str} | Mine: {m['mine_balance']}\n"
        keyboard.append([InlineKeyboardButton(f"Claim {m['name']}", callback_data=f"claim_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    idx = int(query.data.split("_")[1])
    machine = users[user_id]["machines"][idx]
    now = datetime.datetime.now()
    last_claim = machine["last_claim"]
    delta = now - last_claim
    if delta.total_seconds() < 12*3600:
        await query.edit_message_text("⚠️ You can claim only every 12 hours.")
        return
    users[user_id]["balance"] += machine["wcoin_per_claim"]
    machine["mine_balance"] = 0
    machine["last_claim"] = now
    await query.edit_message_text(f"✅ Claimed {machine['wcoin_per_claim']} WCoin from {machine['name']}.")

# ---------------- Withdraw Condition Check ----------------
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
    except:
        await update.message.reply_text("⚠️ Invalid number.")
        return WITHDRAW_AMOUNT
    if amount < 50000:
        await update.message.reply_text("⚠️ Minimum withdrawal is 50,000 MCoin.")
        return WITHDRAW_AMOUNT
    if users[user_id].get("referrals", 0) < 10:
        await update.message.reply_text("⚠️ You need at least 10 referrals to withdraw.")
        return WITHDRAW_AMOUNT
    # Check machine condition
    machine_ok = any(m.get("admin_confirm") and m.get("active") for m in users[user_id].get("machines", []))
    if not machine_ok:
        await update.message.reply_text("⚠️ You must have at least one admin-confirmed machine to withdraw.")
        return WITHDRAW_AMOUNT
    account = users[user_id]["payment_number"]
    global order_counter
    order_id = order_counter
    order_counter += 1
    context.user_data["withdraw"] = {"id": order_id, "amount": amount, "account": account}
    btn = [[InlineKeyboardButton("✔️ Confirm", callback_data=f"confirm_withdraw_{order_id}")]]
    await update.message.reply_text(
        f"💰 Withdraw {amount} MCoin to {account}?",
        reply_markup=InlineKeyboardMarkup(btn)
    )
# ---------------- Admin Functions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <username|user_id>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, data in users.items():
            if data.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found.")
        return
    user = users[target_id]
    if user["balance"] < 50000 or user.get("referrals", 0) < 10 or not any(m.get("admin_confirm") for m in user.get("machines", [])):
        user["withdraw_dismissed"] = True
        await update.message.reply_text(f"✅ Withdraw conditions dismissed for {target}.")
    else:
        await update.message.reply_text("User meets all withdraw conditions, nothing dismissed.")

async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    requests = []
    for uid, data in users.items():
        for m in data.get("machines", []):
            if not m.get("admin_confirm") and m.get("requested", False):
                requests.append(f"Order ID: {m['order_id']} | Machine: {m['name']} | Payment: {m['payment_number']}")
    if not requests:
        await update.message.reply_text("No machine buy requests.")
        return
    await update.message.reply_text("\n".join(requests))

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(context.args[0])
    for uid, data in users.items():
        for m in data.get("machines", []):
            if m.get("order_id") == order_id and not m.get("admin_confirm"):
                m["admin_confirm"] = True
                await update.message.reply_text(f"✅ Machine {m['name']} for user {uid} confirmed.")
                return
    await update.message.reply_text("Order not found or already confirmed.")
# ---------------- User Machine Functions ----------------
import time

MACHINE_TYPES = [
    {"name": "Basic", "price": 0, "wcoin_per_day": 1000},
    {"name": "Common", "price": 5000, "wcoin_per_day": 2000},
    {"name": "Epic", "price": 8000, "wcoin_per_day": 3000},
    {"name": "Legend", "price": 12000, "wcoin_per_day": 4500},
    {"name": "Premium", "price": 30000, "wcoin_per_day": 9000},
]

def create_machine_record(machine_type, order_id, payment_number):
    now = time.time()
    return {
        "name": machine_type["name"],
        "price": machine_type["price"],
        "wcoin_per_day": machine_type["wcoin_per_day"],
        "last_claim": now,
        "expired": now + 30*24*3600,  # 30 days
        "active": False if machine_type["name"] != "Basic" else True,
        "order_id": order_id,
        "payment_number": payment_number,
        "requested": True if machine_type["name"] != "Basic" else False,
        "mine_balance": 0
    }

async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("User not found.")
        return
    text = "Available Machines:\n"
    buttons = []
    for idx, m in enumerate(MACHINE_TYPES):
        text += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(m['name'], callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine_type = MACHINE_TYPES[idx]
        if users[user_id]["balance"] < machine_type["price"]:
            await query.edit_message_text(f"⚠️ Not enough balance for {machine_type['name']}")
            return
        if machine_type["price"] > 0:
            await query.edit_message_text(f"Send your payment/phone number for {machine_type['name']} ({machine_type['price']} MCoin)")
            context.user_data["buy_machine_idx"] = idx
        else:
            order_id = int(time.time())
            m_record = create_machine_record(machine_type, order_id, None)
            users[user_id]["machines"].append(m_record)
            await query.edit_message_text(f"✅ {machine_type['name']} purchased successfully! Active now.")

async def buy_machine_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if "buy_machine_idx" not in context.user_data:
        return
    idx = context.user_data["buy_machine_idx"]
    machine_type = MACHINE_TYPES[idx]
    payment_number = update.message.text.strip()
    users[user_id]["balance"] -= machine_type["price"]
    order_id = int(time.time())
    m_record = create_machine_record(machine_type, order_id, payment_number)
    users[user_id]["machines"].append(m_record)
    await update.message.reply_text(f"✅ Your order for {machine_type['name']} is sent to admin. Order ID: {order_id}")
    context.user_data.pop("buy_machine_idx", None)

async def show_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = "Active Machines:\n"
    now = time.time()
    for idx, m in enumerate(users[user_id].get("machines", []), start=1):
        if m["expired"] < now:
            m["active"] = False
        status = "Active" if m["active"] else "Inactive/Expired"
        msg += f"{idx}. {m['name']} - {status}\n"
        msg += f"   Exp: {datetime.datetime.fromtimestamp(m['expired']).strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"   Mine Balance: {m['mine_balance']} MCoin\n"
        msg += f"   Claim: /claim_{idx}\n"
    await update.message.reply_text(msg)

async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if not text.startswith("/claim_"):
        return
    idx = int(text.split("_")[1]) - 1
    if idx >= len(users[user_id]["machines"]):
        await update.message.reply_text("Invalid machine.")
        return
    m = users[user_id]["machines"][idx]
    if not m["active"]:
        await update.message.reply_text("Machine inactive or expired.")
        return
    now = time.time()
    if now - m["last_claim"] < 12*3600:
        await update.message.reply_text("⚠️ You can claim only every 12 hours.")
        return
    m["mine_balance"] += m["wcoin_per_day"]/2  # 12h
    m["last_claim"] = now
    users[user_id]["balance"] += m["mine_balance"]
    await update.message.reply_text(f"✅ Claimed {m['mine_balance']} MCoin from {m['name']}")
    m["mine_balance"] = 0
# ---------------- Admin Machine Functions ----------------
async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "Machine Buy Requests:\n"
    for u_id, data in users.items():
        for m in data.get("machines", []):
            if m.get("requested") and not m.get("active"):
                text += f"OrderID:{m['order_id']} | Machine:{m['name']} | Payment:{m['payment_number']} | User:{u_id}\n"
    await update.message.reply_text(text)

async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(context.args[0])
    found = False
    for u_id, data in users.items():
        for m in data.get("machines", []):
            if m.get("order_id") == order_id and not m.get("active"):
                m["active"] = True
                m["requested"] = False
                found = True
                await update.message.reply_text(f"✅ Machine {m['name']} activated for user {u_id}")
    if not found:
        await update.message.reply_text("Order not found.")

async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Dismiss_All <user_id or username>")
        return
    target = context.args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for u_id, data in users.items():
            if data.get("username") == target:
                target_id = u_id
                break
    if target_id is None or target_id not in users:
        await update.message.reply_text("User not found.")
        return
    # Dismiss all restrictions: min amount, referrals, machine requirement
    for m in users[target_id].get("machines", []):
        m["requested"] = False
    await update.message.reply_text(f"✅ All restrictions dismissed for user {target_id}")
# ---------------- User Machine Buy ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "Available Machines:\n"
    buttons = []
    for idx, m in enumerate(machines):
        text += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(f"{m['name']} ({m['price']} MCoin)", callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def buy_machine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        m = machines[idx]
        context.user_data["buy_machine_idx"] = idx
        await query.edit_message_text(f"Send your payment/phone number for {m['name']} ({m['price']} MCoin)")

async def buy_machine_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        return
    m = machines[idx]
    order_id = order_counter
    context.user_data["order_id"] = order_id
    users[user_id].setdefault("machines", []).append({
        "name": m["name"],
        "price": m["price"],
        "wcoin_per_day": m["wcoin_per_day"],
        "payment_number": text,
        "order_id": order_id,
        "active": False,
        "requested": True,
        "created_at": datetime.datetime.now(),
        "last_claim": None,
        "expired_at": datetime.datetime.now() + datetime.timedelta(days=30)
    })
    global order_counter
    order_counter += 1
    await update.message.reply_text(f"✅ Your order id is {order_id}. Admin will confirm the purchase during working hours.")
# ---------------- Machine definitions ----------------
machines_data = [
    {"name": "Basic", "price": 0, "wcoin_per_day": 1000, "admin_confirm": False},
    {"name": "Common", "price": 5000, "wcoin_per_day": 2000, "admin_confirm": True},
    {"name": "Epic", "price": 8000, "wcoin_per_day": 3000, "admin_confirm": True},
    {"name": "Legend", "price": 12000, "wcoin_per_day": 4500, "admin_confirm": True},
    {"name": "Premium", "price": 30000, "wcoin_per_day": 9000, "admin_confirm": False},
]

# ---------------- Machine purchase requests ----------------
machine_requests = []  # {order_id, user_id, machine_idx, payment_number, status}

order_machine_counter = 1

# ---------------- User functions: Buy Machine ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text not in [m["name"] for m in machines_data]:
        await update.message.reply_text("Invalid machine selection")
        return
    idx = next(i for i, m in enumerate(machines_data) if m["name"] == text)
    machine = machines_data[idx]
    user_balance = users[user_id]["balance"]

    if machine["price"] > user_balance and machine["admin_confirm"] is False:
        await update.message.reply_text("Not enough balance for this machine.")
        return

    if machine["admin_confirm"] is False:
        users[user_id]["balance"] -= machine["price"]
        users[user_id]["machines"].append({
            "name": machine["name"],
            "idx": idx,
            "start_time": datetime.datetime.now(),
            "last_claim": datetime.datetime.now(),
            "expired": datetime.datetime.now() + datetime.timedelta(days=30),
            "mine_left": machine["wcoin_per_day"]
        })
        await update.message.reply_text(f"✅ {machine['name']} machine purchased successfully.")
        return

    # admin confirmation machines
    global order_machine_counter
    order_id = order_machine_counter
    order_machine_counter += 1
    machine_requests.append({
        "order_id": order_id,
        "user_id": user_id,
        "machine_idx": idx,
        "payment_number": None,
        "status": "pending"
    })
    await update.message.reply_text(f"Please send payment number for {machine['name']}. Your order id is {order_id}.")
# ---------------- Receive payment number for machine ----------------
async def machine_payment_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    pending_order = next((r for r in machine_requests if r["user_id"] == user_id and r["status"] == "pending"), None)
    if not pending_order:
        await update.message.reply_text("No pending machine order found.")
        return
    pending_order["payment_number"] = text
    await update.message.reply_text(
        f"Payment number received for order {pending_order['order_id']}. Admin will confirm soon."
    )

# ---------------- User function: View machines ----------------
async def view_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_machines = users[user_id].get("machines", [])
    if not user_machines:
        await update.message.reply_text("You have no active machines.")
        return
    text = "Your active machines:\n"
    for m in user_machines:
        claim_ready = datetime.datetime.now() >= m["last_claim"] + datetime.timedelta(hours=12)
        expired = datetime.datetime.now() >= m["expired"]
        text += f"{m['name']} | Mine Left: {m['mine_left']} WCoin | Expired: {'Yes' if expired else 'No'} | Claim Ready: {'Yes' if claim_ready else 'No'}\n"
    await update.message.reply_text(text)

# ---------------- Claim machine mining ----------------
async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    machine_name = update.message.text.strip()
    machine = next((m for m in users[user_id].get("machines", []) if m["name"] == machine_name), None)
    if not machine:
        await update.message.reply_text("Machine not found.")
        return
    if datetime.datetime.now() < machine["last_claim"] + datetime.timedelta(hours=12):
        await update.message.reply_text("Claim not ready yet.")
        return
    users[user_id]["balance"] += machine["mine_left"]
    machine["mine_left"] = machines_data[machine["idx"]]["wcoin_per_day"]
    machine["last_claim"] = datetime.datetime.now()
    await update.message.reply_text(f"✅ Claimed {machines_data[machine['idx']]['wcoin_per_day']} WCoin from {machine_name}.")
# ---------------- Admin: Dismiss all restrictions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /Dismiss_All <user_id or username>")
        return
    target = context.args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, data in users.items():
            if data.get("username") == target or str(uid) == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return
    user = users[target_id]
    # Reset referral and machine buy restrictions
    user["referrals"] = max(user.get("referrals",0), 10)
    for m in user.get("machines", []):
        m["admin_confirm"] = True
    await update.message.reply_text(f"All restrictions dismissed for user {target}")
# ---------------- Admin: View machine buy requests ----------------
async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not buy_machine_list:
        await update.message.reply_text("No pending machine buy requests")
        return
    text = "Pending Machine Buy Requests:\n"
    for req in buy_machine_list:
        user = users.get(req["user_id"], {})
        text += f"Order ID:{req['order_id']} | Machine:{req['machine_name']} | Payment:{req['payment_number']} | User:{user.get('username') or req['user_id']}\n"
    await update.message.reply_text(text)

# ---------------- Admin: Confirm machine buy ----------------
async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in buy_machine_list if r["order_id"] == order_id), None)
    if not req:
        await update.message.reply_text("Request not found")
        return
    user_id = req["user_id"]
    machine_idx = req["machine_idx"]
    users[user_id]["machines"].append({
        "name": machines[machine_idx]["name"],
        "price": machines[machine_idx]["price"],
        "wcoin_per_day": machines[machine_idx]["wcoin_per_day"],
        "admin_confirm": True,
        "active": True,
        "last_claim": None,
        "expire": datetime.datetime.now() + datetime.timedelta(days=30)
    })
    buy_machine_list.remove(req)
    await update.message.reply_text(f"Machine {machines[machine_idx]['name']} assigned to user {user_id}")
# ---------------- Admin: Dismiss all restrictions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <username or user_id>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, data in users.items():
            if data.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return

    # reset restrictions
    user = users[target_id]
    user["balance"] = max(user.get("balance",0),50000)  # minimum amount restriction
    user["referrals"] = max(user.get("referrals",0),10) # referral restriction
    # machine buy requirement reset
    for m in user.get("machines", []):
        m["admin_confirm"] = True
    await update.message.reply_text(f"Restrictions dismissed for user {target}")
# ---------------- Admin: Machine buy requests ----------------
async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "Machine buy requests:\n"
    found = False
    for req in buy_machine_list:
        text += f"Order ID:{req['order_id']} | Machine:{req['machine_name']} | User:{req['user_id']} | Payment:{req['payment_number']}\n"
        found = True
    if not found:
        text += "No pending requests."
    await update.message.reply_text(text)


async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in buy_machine_list if r["order_id"] == order_id), None)
    if not req:
        await update.message.reply_text("Order not found")
        return
    user_id = req["user_id"]
    # Confirm machine
    for m in users[user_id]["machines"]:
        if m["order_id"] == order_id:
            m["admin_confirm"] = True
            break
    buy_machine_list.remove(req)
    await update.message.reply_text(f"Machine {req['machine_name']} confirmed for user {user_id}")
# ---------------- User: Buy machine ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Please /start first")
        return
    text = "Available Machines:\n"
    buttons = []
    for idx, m in enumerate(machines):
        text += f"{idx+1}. {m['name']} - Price: {m['price']} MCoin/day\n"
        buttons.append([InlineKeyboardButton(f"{m['name']} ({m['price']} MCoin)", callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def buy_machine_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if not data.startswith("buy_"):
        return
    idx = int(data.split("_")[1])
    machine = machines[idx]
    if get_balance(user_id) < machine["price"]:
        await query.edit_message_text(f"⚠️ Not enough balance for {machine['name']} ({machine['price']} MCoin)")
        return
    context.user_data["buy_machine_idx"] = idx
    await query.edit_message_text(f"Send your payment/phone number for {machine['name']} ({machine['price']} MCoin):")


# ---------------- User: Payment number for machine ----------------
async def machine_payment_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        return
    machine = machines[idx]
    payment_number = update.message.text.strip()
    # create order
    order_id = order_counter
    global order_counter
    order_counter += 1
    buy_machine_list.append({
        "order_id": order_id,
        "user_id": user_id,
        "machine_idx": idx,
        "machine_name": machine["name"],
        "payment_number": payment_number,
        "admin_confirm": False
    })
    await update.message.reply_text(f"✅ Your order ID is {order_id}. Sent to admin for confirmation.")
    context.user_data["buy_machine_idx"] = None
# ---------------- User: Active machines & claim ----------------
async def show_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Please /start first")
        return
    text = "🛠️ Active Machines:\n"
    now = datetime.datetime.now()
    for m in users[user_id]["machines"]:
        exp_date = m["expire_date"]
        active_status = "Active" if m.get("active", False) else "Inactive"
        text += f"Machine: {m['name']} | Status: {active_status} | Expire: {exp_date.strftime('%Y-%m-%d')}\n"
        if active_status == "Active":
            text += f"/claim_{m['order_id']} - Claim WCoin\n"
    if not users[user_id]["machines"]:
        text += "No machines yet."
    await update.message.reply_text(text)


async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = update.message.text
    if not data.startswith("/claim_"):
        return
    order_id = int(data.split("_")[1])
    machine = next((m for m in users[user_id]["machines"] if m["order_id"] == order_id), None)
    if not machine:
        await update.message.reply_text("Machine not found.")
        return
    now = datetime.datetime.now()
    last_claim = machine.get("last_claim", machine["start_date"])
    if (now - last_claim).total_seconds() < 12*3600:
        await update.message.reply_text("⚠️ You can claim only every 12 hours.")
        return
    wcoin = machine["wcoin_per_day"] // 2  # since claim is 12 hours
    users[user_id]["balance"] += wcoin
    machine["last_claim"] = now
    await update.message.reply_text(f"✅ You claimed {wcoin} WCoin from {machine['name']}.")


# ---------------- Admin: Dismiss all ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <user_id or username>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, data in users.items():
            if data.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found.")
        return
    # dismiss rules for withdraw
    users[target_id]["withdraw_minimum"] = 50000
    users[target_id]["referral_requirement"] = 10
    users[target_id]["machine_required"] = None
    await update.message.reply_text(f"✅ Dismissed withdraw restrictions for user {target_id}")


# ---------------- Admin: Req machine buy ----------------
async def req_mbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "Machine buy requests:\n"
    found = False
    for req in buy_machine_list:
        text += f"Order ID:{req['order_id']} | Machine:{req['machine_name']} | User:{req['user_id']} | Payment:{req['payment_number']}\n"
        found = True
    if not found:
        text += "No pending requests."
    await update.message.reply_text(text)


async def access_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Access_buy <order_id>")
        return
    order_id = int(args[0])
    req = next((r for r in buy_machine_list if r["order_id"] == order_id), None)
    if not req:
        await update.message.reply_text("Order not found")
        return
    user_id = req["user_id"]
    # Confirm machine
    for m in users[user_id]["machines"]:
        if m["order_id"] == order_id:
            m["admin_confirm"] = True
            break
    buy_machine_list.remove(req)
    await update.message.reply_text(f"Machine {req['machine_name']} confirmed for user {user_id}")
# ---------------- Withdraw flow with machine & referral check ----------------
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    try:
        amount = int(text)
    except:
        await update.message.reply_text("⚠️ Please enter a valid number.")
        return WITHDRAW_AMOUNT

    if amount < 50000:
        await update.message.reply_text("⚠️ Minimum withdrawal is 50,000 MCoin.")
        return WITHDRAW_AMOUNT

    # Check referrals
    if users[user_id].get("referrals", 0) < 10:
        await update.message.reply_text("⚠️ You need at least 10 referrals to withdraw.")
        return ConversationHandler.END

    # Check machine requirement (only admin confirmed machines)
    has_machine = any(m.get("admin_confirm") for m in users[user_id]["machines"] if m["name"] != "Basic")
    if not has_machine:
        await update.message.reply_text("⚠️ You must have at least one admin-confirmed mining machine (Common/Epic/Legend) to withdraw.")
        return ConversationHandler.END

    # All checks passed, create withdrawal request
    account = users[user_id]["payment_number"]
    global order_counter
    order_id = order_counter
    order_counter += 1

    context.user_data["withdraw"] = {"id": order_id, "amount": amount, "account": account}
    withdrawal_requests.append({
        "id": order_id,
        "user_id": user_id,
        "amount": amount,
        "account": account
    })
    await update.message.reply_text(f"✅ Withdrawal request #{order_id} submitted for admin approval.")
    return ConversationHandler.END


# ---------------- Machine purchase flow ----------------
async def buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = []
    text = "🛒 Available Machines:\n"
    for idx, m in enumerate(machines):
        text += f"{idx+1}. {m['name']} - {m['price']} MCoin/day\n"
        keyboard.append([InlineKeyboardButton(f"{m['name']} ({m['price']} MCoin)", callback_data=f"buy_{idx}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data
    if data.startswith("buy_"):
        idx = int(data.split("_")[1])
        machine = machines[idx]
        context.user_data["buy_machine_idx"] = idx
        await query.message.edit_text(f"You selected {machine['name']} costing {machine['price']} MCoin.\nPlease send your payment number or transaction info.")


async def confirm_buy_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    idx = context.user_data.get("buy_machine_idx")
    if idx is None:
        return
    machine = machines[idx]
    payment_number = update.message.text.strip()

    order_id = order_counter
    global order_counter
    order_counter += 1

    buy_machine_list.append({
        "order_id": order_id,
        "user_id": user_id,
        "machine_name": machine["name"],
        "payment_number": payment_number
    })

    await update.message.reply_text(f"✅ Your order for {machine['name']} submitted. Order ID: {order_id}\nAdmin will confirm shortly.")
    return ConversationHandler.END
# ---------------- User: Claim machine rewards ----------------
async def claim_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("User not found.")
        return
    text = "Your active machines:\n"
    now = datetime.datetime.now()
    for m in users[user_id]["machines"]:
        if m.get("admin_confirm", False):
            last_claim = m.get("last_claim", m["start_date"])
            exp_date = m["start_date"] + datetime.timedelta(days=30)
            can_claim = (now - last_claim).total_seconds() >= 12*3600
            status = "✅ Can claim" if can_claim else "⏳ Wait"
            text += f"Machine: {m['name']} | Daily: {m['wcoin_per_day']} MCoin | Exp: {exp_date.strftime('%Y-%m-%d')} | Status: {status}\n"
    await update.message.reply_text(text)

async def claim_specific_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Claim <machine_index>")
        return
    idx = int(args[0])-1
    if idx < 0 or idx >= len(users[user_id]["machines"]):
        await update.message.reply_text("Invalid machine index.")
        return
    m = users[user_id]["machines"][idx]
    now = datetime.datetime.now()
    last_claim = m.get("last_claim", m["start_date"])
    if (now - last_claim).total_seconds() < 12*3600:
        await update.message.reply_text("⏳ 12 hours not passed yet.")
        return
    users[user_id]["balance"] += m["wcoin_per_day"]
    m["last_claim"] = now
    await update.message.reply_text(f"✅ Claimed {m['wcoin_per_day']} MCoin from {m['name']}. Current balance: {users[user_id]['balance']} MCoin")
# ---------------- Machine expiration check ----------------
def check_machine_expiry(user_id):
    now = datetime.datetime.now()
    for m in users[user_id]["machines"][:]:
        exp_date = m["start_date"] + datetime.timedelta(days=30)
        if now >= exp_date:
            users[user_id]["machines"].remove(m)

# ---------------- Admin: Dismiss all restrictions ----------------
async def dismiss_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /Dismiss_All <username or user_id>")
        return
    target = args[0]
    target_id = None
    if target.isdigit():
        target_id = int(target)
    else:
        for uid, data in users.items():
            if data.get("username") == target:
                target_id = uid
                break
    if not target_id or target_id not in users:
        await update.message.reply_text("User not found")
        return
    # Dismiss restrictions
    users[target_id]["balance"] = max(users[target_id]["balance"], 50000)
    users[target_id]["referrals"] = max(users[target_id].get("referrals",0), 10)
    for m in users[target_id]["machines"]:
        m["admin_confirm"] = True
    await update.message.reply_text(f"Restrictions dismissed for user {target_id}")

# ---------------- Conversation handlers update ----------------
conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
    states={
        SET_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_number)],
        WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
    },
    fallbacks=[CommandHandler("editNumber", edit_number)],
    per_user=True
)

# ---------------- Bot handlers ----------------
app.add_handler(CommandHandler("start", start))
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(callback_handler))
app.add_handler(CommandHandler("editNumber", edit_number))
app.add_handler(CommandHandler("Wreq", wreq))
app.add_handler(CommandHandler("Wreq_C", wreq_c))
app.add_handler(CommandHandler("Add_B", add_b))
app.add_handler(CommandHandler("Req_Mbuy", req_mbuy))
app.add_handler(CommandHandler("Access_buy", access_buy))
app.add_handler(CommandHandler("Dismiss_All", dismiss_all))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(CommandHandler("Claim", claim_specific_machine))
app.add_handler(CommandHandler("Machines", claim_machine))

# ---------------- Bot setup ----------------
BOT_TOKEN = "7381601059:AAHO5SG4dm-22KxhOfkxbv1VSlCRbVl9oDA"

if __name__ == "__main__":
    print("Bot started...")
    app.run_polling()                                                                                                                                                                                                                          
