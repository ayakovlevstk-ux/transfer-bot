import os
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not TOKEN:
    raise ValueError("TOKEN не найден")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# STATES
# =========================

FROM, TO, DATE, LOCATION, CONFIRM = range(5)

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🚕 Заказать трансфер"]]

    await update.message.reply_text(
        "Добро пожаловать! Нажмите кнопку ниже:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# =========================
# ORDER FLOW
# =========================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Откуда едем?")
    return FROM


async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("Куда едем?")
    return TO


async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("Укажите дату поездки:")
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Отправьте геолокацию:",
        reply_markup=keyboard
    )

    return LOCATION


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location

    context.user_data["lat"] = loc.latitude
    context.user_data["lon"] = loc.longitude

    maps_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    summary = (
        "Проверьте заказ:\n\n"
        f"Откуда: {context.user_data['from']}\n"
        f"Куда: {context.user_data['to']}\n"
        f"Дата: {context.user_data['date']}\n"
        f"Локация: {maps_link}"
    )

    await update.message.reply_text(summary)
    await update.message.reply_text("Подтвердить заказ? (да/нет)")

    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text not in ["да", "yes", "y"]:
        await update.message.reply_text("Заказ отменён")
        return ConversationHandler.END

    order_text = (
        "НОВЫЙ ЗАКАЗ\n\n"
        f"Откуда: {context.user_data['from']}\n"
        f"Куда: {context.user_data['to']}\n"
        f"Дата: {context.user_data['date']}\n"
        f"Координаты: {context.user_data.get('lat')}, {context.user_data.get('lon')}"
    )

    await update.message.reply_text("Заказ принят!")

    if ADMIN_ID:
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
    app = Application.builder().token(TOKEN).build()

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
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()