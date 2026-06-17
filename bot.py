import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")

# --- КНОПКИ МЕНЮ ---
menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены"],
        ["📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот трансферов 🚕\nВыбери действие:",
        reply_markup=menu_keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🚕 Заказать трансфер":
        await update.message.reply_text("Напиши: откуда и куда ты хочешь поехать 🚕")

    elif text == "💰 Цены":
        await update.message.reply_text("Цены зависят от маршрута. Пример: Керкраде → Амстердам = 120€")

    elif text == "📍 Маршруты":
        await update.message.reply_text("Доступные маршруты:\n- Керкраде → Амстердам\n- Керкраде → Брюссель")

    elif text == "❓ Помощь":
        await update.message.reply_text("Напиши свой маршрут, и я рассчитаю стоимость 🚕")

    else:
        await update.message.reply_text("Я не понял сообщение. Выбери пункт меню 👇", reply_markup=menu_keyboard)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()