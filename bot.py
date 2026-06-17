import os
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN не найден")

ADMIN_ID = 8308540295

# =========================
# KEYBOARDS
# =========================

MENU = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

LOCATION_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Отправить геолокацию", request_location=True)],
        ["⬅️ Назад"]
    ],
    resize_keyboard=True
)

CONFIRM_KB = ReplyKeyboardMarkup(
    [
        ["✅ Подтвердить", "❌ Отмена"],
        ["⬅️ Назад"]
    ],
    resize_keyboard=True
)

# =========================
# MEMORY (simple in-memory state)
# =========================

users = {}

def get_user(user_id: int):
    if user_id not in users:
        users[user_id] = {"step": None}
    return users[user_id]

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.message.from_user.id)
    user["step"] = None

    await update.message.reply_text(
        "Привет! 🚕 Выбери действие:",
        reply_markup=MENU
    )

# =========================
# ROUTER (ONE HANDLER RULE)
# =========================

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    user = get_user(user_id)

    step = user.get("step")

    # ================= MENU =================

    if text == "🚕 Заказать трансфер":
        user["step"] = "from"
        await update.message.reply_text("Откуда едем?")
        return

    if text == "💰 Цены":
        await update.message.reply_text("Керкраде → Амстердам = 120€")
        return

    if text == "📍 Маршруты":
        await update.message.reply_text("Керкраде → Амстердам\nКеркраде → Брюссель")
        return

    if text == "❓ Помощь":
        await update.message.reply_text("Напиши маршрут, и я помогу 🚕")
        return

    # ================= FLOW =================

    if text == "⬅️ Назад":
        user["step"] = None
        await update.message.reply_text("Меню:", reply_markup=MENU)
        return

    # FROM
    if step == "from":
        user["from"] = text
        user["step"] = "to"
        await update.message.reply_text("Куда едем?")
        return

    # TO
    if step == "to":
        user["to"] = text
        user["step"] = "location"

        await update.message.reply_text(
            "Отправь геолокацию 📍",
            reply_markup=LOCATION_KB
        )
        return

    # CONFIRM TEXT
    if step == "confirm":
        if text == "❌ Отмена":
            user["step"] = None
            await update.message.reply_text("Отменено", reply_markup=MENU)
            return

        if text == "⬅️ Назад":
            user["step"] = "location"
            await update.message.reply_text(
                "Отправь геолокацию 📍",
                reply_markup=LOCATION_KB
            )
            return

        if text == "✅ Подтвердить":
            await update.message.reply_text("Заказ принят 🚕", reply_markup=MENU)

            # optional admin notify
            print("NEW ORDER:", user)

            user["step"] = None
            return

    # fallback
    await update.message.reply_text("Используй меню 👇", reply_markup=MENU)

# =========================
# LOCATION
# =========================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = get_user(user_id)

    loc = update.message.location

    user["lat"] = loc.latitude
    user["lon"] = loc.longitude

    user["step"] = "confirm"

    map_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    text = (
        "🚕 Проверь заказ:\n\n"
        f"Откуда: {user.get('from')}\n"
        f"Куда: {user.get('to')}\n"
        f"📍 Локация: {map_link}"
    )

    await update.message.reply_text(
        text,
        reply_markup=CONFIRM_KB
    )

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # ONLY TWO HANDLERS (IMPORTANT)
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()