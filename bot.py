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

# 👉 сюда вставь свой Telegram ID (сделаю ниже как узнать)
ADMIN_ID = 8879032988:AAHzyQv6OdUJ0Anjah1aieMNEOhkJzVIGbQ

FROM, TO, DATE, CONFIRM = range(4)

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

# --- START ORDER ---
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📍 Откуда вас забрать?",
        reply_markup=ReplyKeyboardRemove()
    )
    return FROM

async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("📍 Куда едем?")
    return TO

async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("📅 Дата и время? (пример: 20.06 14:30)")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    summary = f"""
🚕 НОВЫЙ ЗАКАЗ:

📍 Откуда: {context.user_data['from']}
📍 Куда: {context.user_data['to']}
📅 Когда: {context.user_data['date']}

Напиши:
✔ Да — подтвердить
❌ Нет — отменить
"""
    await update.message.reply_text(summary)
    return CONFIRM

# --- CONFIRM ---
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text == "да":
        order = f"""
🚕 ЗАКАЗ ПРИНЯТ

📍 Откуда: {context.user_data['from']}
📍 Куда: {context.user_data['to']}
📅 Когда: {context.user_data['date']}
👤 User: {update.effective_user.id}
"""

        # 💾 сохраняем в файл
        with open("orders.txt", "a", encoding="utf-8") as f:
            f.write(order + "\n-----------------\n")

        # 📩 отправляем админу
        await context.bot.send_message(chat_id=ADMIN_ID, text=order)

        await update.message.reply_text(
            "✅ Заказ отправлен! Мы свяжемся с вами.",
            reply_markup=menu_keyboard
        )

    else:
        await update.message.reply_text(
            "❌ Заказ отменён",
            reply_markup=menu_keyboard
        )

    return ConversationHandler.END

# --- MENU ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🚕 Заказать трансфер":
        return await start_order(update, context)

    elif text == "💰 Цены":
        await update.message.reply_text("💰 От 80€ до 300€ в зависимости от маршрута")

    elif text == "📍 Маршруты":
        await update.message.reply_text("📍 Керкраде → Амстердам\n📍 Керкраде → Брюссель")

    elif text == "❓ Помощь":
        await update.message.reply_text("Нажми 🚕 Заказать трансфер и следуй шагам")

# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("🚕 Заказать трансфер"), start_order)],
        states={
            FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_from)],
            TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_to)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    app.run_polling()

if __name__ == "__main__":
    main()