import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

TOKEN = os.getenv("TOKEN")

# этапы диалога
FROM, TO, DATE = range(3)

menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены"],
        ["📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот трансферов 🚕\nВыбери действие:",
        reply_markup=menu_keyboard
    )

# --- НАЧАЛО ЗАКАЗА ---
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📍 Откуда вас забрать?",
        reply_markup=ReplyKeyboardRemove()
    )
    return FROM

# --- ОТКУДА ---
async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("📍 Куда едем?")
    return TO

# --- КУДА ---
async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("📅 Укажи дату и время (например: 20.06 14:30)")
    return DATE

# --- ДАТА ---
async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    summary = f"""
🚕 Ваш заказ:

📍 Откуда: {context.user_data['from']}
📍 Куда: {context.user_data['to']}
📅 Когда: {context.user_data['date']}

Подтвердить? (напиши Да / Нет)
"""
    await update.message.reply_text(summary)
    return ConversationHandler.END

# --- ОБЫЧНЫЕ КНОПКИ ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🚕 Заказать трансфер":
        return await start_order(update, context)

    elif text == "💰 Цены":
        await update.message.reply_text("Цены от 80€ до 300€ в зависимости от маршрута 🚕")

    elif text == "📍 Маршруты":
        await update.message.reply_text("Популярные маршруты:\n- Керкраде → Амстердам\n- Керкраде → Брюссель")

    elif text == "❓ Помощь":
        await update.message.reply_text("Нажми 🚕 Заказать трансфер и следуй шагам")

# --- СТАРТ БОТА ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("🚕 Заказать трансфер"), start_order)
        ],
        states={
            FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_from)],
            TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_to)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    app.run_polling()

if __name__ == "__main__":
    main()