import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

# =========================
# MENU
# =========================

menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены"],
        ["📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

location_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Отправить геолокацию", request_location=True)],
        ["⬅️ Назад"]
    ],
    resize_keyboard=True
)

confirm_keyboard = ReplyKeyboardMarkup(
    [
        ["✅ Подтвердить", "❌ Отмена"],
        ["⬅️ Назад"]
    ],
    resize_keyboard=True
)

# =========================
# STATE STORAGE (простое)
# =========================

user_data = {}

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот трансферов 🚕\nВыбери действие:",
        reply_markup=menu_keyboard
    )

# =========================
# MAIN HANDLER
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    if user_id not in user_data:
        user_data[user_id] = {}

    # ================= MENU =================

    if text == "🚕 Заказать трансфер":
        await update.message.reply_text("Откуда едем?")
        user_data[user_id]["step"] = "from"
        return

    if text == "💰 Цены":
        await update.message.reply_text("Керкраде → Амстердам = 120€")
        return

    if text == "📍 Маршруты":
        await update.message.reply_text("Керкраде → Амстердам\nКеркраде → Брюссель")
        return

    if text == "❓ Помощь":
        await update.message.reply_text("Напиши маршрут и я помогу 🚕")
        return

    # ================= FLOW =================

    step = user_data[user_id].get("step")

    # FROM
    if step == "from":
        user_data[user_id]["from"] = text
        user_data[user_id]["step"] = "to"
        await update.message.reply_text("Куда едем?")
        return

    # TO
    if step == "to":
        user_data[user_id]["to"] = text
        user_data[user_id]["step"] = "location"
        await update.message.reply_text(
            "Отправь геолокацию 📍",
            reply_markup=location_keyboard
        )
        return

    # BACK
    if text == "⬅️ Назад":
        user_data[user_id]["step"] = None
        await update.message.reply_text("Главное меню:", reply_markup=menu_keyboard)
        return

    await update.message.reply_text("Выбери пункт меню 👇", reply_markup=menu_keyboard)

# =========================
# LOCATION HANDLER
# =========================

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    loc = update.message.location

    if user_id not in user_data:
        user_data[user_id] = {}

    user_data[user_id]["lat"] = loc.latitude
    user_data[user_id]["lon"] = loc.longitude

    link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    text = (
        "🚕 Проверь заказ:\n\n"
        f"Откуда: {user_data[user_id].get('from')}\n"
        f"Куда: {user_data[user_id].get('to')}\n"
        f"Локация: {link}"
    )

    user_data[user_id]["step"] = "confirm"

    await update.message.reply_text(text, reply_markup=confirm_keyboard)

# =========================
# CONFIRM
# =========================

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    if text == "✅ Подтвердить":
        await update.message.reply_text("Заказ принят 🚕", reply_markup=menu_keyboard)

    elif text == "❌ Отмена":
        await update.message.reply_text("Отменено", reply_markup=menu_keyboard)

    elif text == "⬅️ Назад":
        user_data[user_id]["step"] = "location"
        await update.message.reply_text("Отправь геолокацию снова 📍", reply_markup=location_keyboard)

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirm))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()