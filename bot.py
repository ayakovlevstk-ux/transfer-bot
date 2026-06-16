import os
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8308540295"))

# --- STATES ---
FROM, TO, DATE = range(3)

# --- MENU ---
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

# --- MENU HANDLER ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🚕 Заказать трансфер":
        await update.message.reply_text("📍 Откуда ты едешь?")
        return FROM

    elif text == "💰 Цены":
        await update.message.reply_text("💰 Пример: Керкраде → Амстердам = 120€")
    elif text == "📍 Маршруты":
        await update.message.reply_text("📍 Керкраде → Амстердам\n📍 Керкраде → Брюссель")
    elif text == "❓ Помощь":
        await update.message.reply_text("Напиши маршрут и дату — я оформлю заказ 🚕")

    return ConversationHandler.END

# --- STEP 1 ---
async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("📍 Куда едем?")
    return TO

# --- STEP 2 ---
async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("📅 Когда поездка? (Пример 01.01.26 00:00)")
    return DATE

# --- STEP 3 + CONFIRM BUTTONS ---
async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Отменить", callback_data="confirm_no")
        ]
    ]

    summary = f"""
🚕 НОВЫЙ ЗАКАЗ

📍 Откуда: {context.user_data['from']}
📍 Куда: {context.user_data['to']}
📅 Когда: {context.user_data['date']}
"""

    await update.message.reply_text(
        summary,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ConversationHandler.END

# --- CALLBACK BUTTONS ---
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_yes":

        order = f"""
🚕 ЗАКАЗ ПРИНЯТ

📍 Откуда: {context.user_data.get('from')}
📍 Куда: {context.user_data.get('to')}
📅 Когда: {context.user_data.get('date')}
👤 User: {query.from_user.id}
"""

        # save file
        with open("orders.txt", "a", encoding="utf-8") as f:
            f.write(order + "\n-----------------\n")

        # send admin
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=order)
        except Exception as e:
            print("ADMIN ERROR:", e)

        await query.message.edit_text("✅ Заказ подтверждён!")

    else:
        await query.message.edit_text("❌ Заказ отменён")

# --- MAIN ---
def main():
    if not TOKEN:
        raise ValueError("TOKEN не найден в переменных окружения Render")

    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("🚕 Заказать трансфер"), handle_menu)
        ],
        states={
            FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_from)],
            TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_to)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_confirm))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    app.run_polling()

if __name__ == "__main__":
    main()