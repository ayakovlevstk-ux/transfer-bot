import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 8308540295

if not TOKEN:
    raise ValueError("TOKEN не найден")

# =========================
# STATES
# =========================
FROM, TO, DATE, LOCATION, CONFIRM = range(5)

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Нажми 🚕 Заказать трансфер"
    )

# =========================
# ORDER START
# =========================
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Откуда едем?")
    return FROM

# =========================
# FROM
# =========================
async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("Куда едем?")
    return TO

# =========================
# TO
# =========================
async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("Введите дату поездки (например 20.06 14:00)")
    return DATE

# =========================
# DATE -> LOCATION BUTTON
# =========================
async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Отправьте геолокацию 📍",
        reply_markup=keyboard
    )

    return LOCATION

# =========================
# LOCATION
# =========================
async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location

    context.user_data["lat"] = loc.latitude
    context.user_data["lon"] = loc.longitude

    maps_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    text = (
        "📍 Геолокация получена\n"
        f"{maps_link}\n\n"
        "Проверьте заказ и подтвердите"
    )

    await update.message.reply_text(text)
    return CONFIRM

# =========================
# CONFIRM
# =========================
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_text = (
        "🚕 НОВЫЙ ЗАКАЗ\n\n"
        f"📍 Откуда: {context.user_data.get('from')}\n"
        f"📍 Куда: {context.user_data.get('to')}\n"
        f"📅 Дата: {context.user_data.get('date')}\n"
        f"🌍 Координаты: {context.user_data.get('lat')}, {context.user_data.get('lon')}"
    )

    await update.message.reply_text("Заказ принят!")
    await context.bot.send_message(chat_id=ADMIN_ID, text=order_text)

    return ConversationHandler.END

# =========================
# CANCEL
# =========================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено")
    return ConversationHandler.END

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("🚕 Заказать трансфер"), start_order)
        ],
        states={
            FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_from)],
            TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_to)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            LOCATION: [MessageHandler(filters.LOCATION, get_location)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()