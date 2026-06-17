import os
import random
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================

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
    await update.message.reply_text("🚕 Бот запущен. Нажми '🚕 Заказать трансфер'")
    return ConversationHandler.END


async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text("🚕 Новый заказ\n\nОткуда поедем?")
    return FROM


# =========================
# FROM
# =========================

async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text

    await update.message.reply_text("📍 Куда едем?")
    return TO


# =========================
# TO
# =========================

async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text

    await update.message.reply_text("📅 Укажи дату поездки")
    return DATE


# =========================
# DATE → LOCATION REQUEST
# =========================

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text("📍 Отправь геолокацию", reply_markup=keyboard)
    return LOCATION


# =========================
# LOCATION FIX (GOOGLE MAPS)
# =========================

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location

    if not loc:
        await update.message.reply_text("❌ Геолокация не получена")
        return LOCATION

    context.user_data["lat"] = loc.latitude
    context.user_data["lon"] = loc.longitude

    maps_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    text = (
        "🚕 ПРОВЕРЬТЕ ЗАКАЗ\n\n"
        f"📍 Откуда: {context.user_data.get('from', '')}\n"
        f"📍 Куда: {context.user_data.get('to', '')}\n"
        f"📅 Дата: {context.user_data.get('date', '')}\n\n"
        f"🗺 Локация:\n{maps_link}\n\n"
        "Напишите 'да' для подтверждения"
    )

    await update.message.reply_text(text)

    return CONFIRM


# =========================
# CONFIRM
# =========================

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_msg = update.message.text.lower()

    if text_msg in ["да", "yes", "ок", "confirm"]:
        order_id = random.randint(1000, 9999)

        await update.message.reply_text(
            f"🚕 ЗАКАЗ #{order_id} ПРИНЯТ\n\nОжидайте подтверждение"
        )

        await context.bot.send_message(
            ADMIN_ID,
            f"🚕 НОВЫЙ ЗАКАЗ #{order_id}\n\n"
            f"📍 Откуда: {context.user_data.get('from')}\n"
            f"📍 Куда: {context.user_data.get('to')}\n"
            f"📅 Дата: {context.user_data.get('date')}"
        )

        return ConversationHandler.END

    await update.message.reply_text("❌ Заказ отменён")
    return ConversationHandler.END


# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🚕 Заказать трансфер$"), start_order)
        ],
        states={
            FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_from)],
            TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_to)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            LOCATION: [MessageHandler(filters.LOCATION, get_location)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", start)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()