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
    ConversationHandler,
    ContextTypes,
    filters
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

BACK = "⬅️ Назад"

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [["🚕 Заказать трансфер"]],
        resize_keyboard=True
    )

    await update.message.reply_text(
        "Привет! Нажми кнопку чтобы начать заказ.",
        reply_markup=keyboard
    )

# =========================
# ORDER FLOW
# =========================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Откуда едем?")
    return FROM


async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text == BACK:
        await update.message.reply_text("Откуда едем?")
        return FROM

    context.user_data["from"] = update.message.text
    await update.message.reply_text("Куда едем?")
    return TO


async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text == BACK:
        await update.message.reply_text("Откуда едем?")
        return FROM

    context.user_data["to"] = update.message.text
    await update.message.reply_text("Дата поездки?")
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text == BACK:
        await update.message.reply_text("Куда едем?")
        return TO

    context.user_data["date"] = update.message.text

    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(BACK)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Отправь геолокацию кнопкой:",
        reply_markup=keyboard
    )

    return LOCATION


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text == BACK:
        await update.message.reply_text("Введите дату снова:")
        return DATE

    loc = update.message.location

    context.user_data["lat"] = loc.latitude
    context.user_data["lon"] = loc.longitude

    maps_link = f"https://maps.google.com/?q={loc.latitude},{loc.longitude}"

    text = (
        "Проверь заказ:\n\n"
        f"Откуда: {context.user_data['from']}\n"
        f"Куда: {context.user_data['to']}\n"
        f"Дата: {context.user_data['date']}\n"
        f"Локация: {maps_link}"
    )

    keyboard = ReplyKeyboardMarkup(
        [
            ["✅ Подтвердить", "❌ Отмена"],
            [BACK]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(text, reply_markup=keyboard)

    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.lower()

    if text == BACK:
        await update.message.reply_text("Отправьте геолокацию снова:")
        return LOCATION

    if "подтверд" in text:
        await update.message.reply_text("Заказ создан 🚕")
    else:
        await update.message.reply_text("Отменено")

    return ConversationHandler.END

# =========================
# CANCEL
# =========================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
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
            LOCATION: [MessageHandler(filters.LOCATION | (filters.TEXT & ~filters.COMMAND), get_location)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()