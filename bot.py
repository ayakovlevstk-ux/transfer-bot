import os
import time
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

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not TOKEN:
    raise ValueError("TOKEN не найден в переменных окружения")

# ================= STORAGE =================
orders = {}
support_users = {}

# ================= STATES =================
FROM, TO, DATE = range(3)

# ================= MENU =================
menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены"],
        ["📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот трансферов 🚕",
        reply_markup=menu_keyboard
    )

# ================= ORDER FLOW =================
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Откуда?")
    return FROM

async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("Куда?")
    return TO

async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("Когда?")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data["date"] = update.message.text

    order_id = str(user_id) + str(int(time.time()))

    orders[order_id] = {
        "from": context.user_data["from"],
        "to": context.user_data["to"],
        "date": context.user_data["date"],
        "user_id": user_id,
        "status": "NEW"
    }

    keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"accept_{order_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{order_id}")
        ],
        [
            InlineKeyboardButton("🚗 В пути", callback_data=f"progress_{order_id}"),
            InlineKeyboardButton("🏁 Завершить", callback_data=f"done_{order_id}")
        ]
    ]

    text = f"""
🚕 НОВЫЙ ЗАКАЗ #{order_id}

📍 Откуда: {orders[order_id]['from']}
📍 Куда: {orders[order_id]['to']}
📅 Когда: {orders[order_id]['date']}

📊 Статус: NEW
"""

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("✅ Заказ отправлен!")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END

# ================= MENU HANDLER =================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # SUPPORT MODE
    if user_id in support_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❓ ВОПРОС\nUser: {user_id}\n\n{text}"
        )
        await update.message.reply_text("✅ Отправлено в поддержку")
        del support_users[user_id]
        return

    if text == "💰 Цены":
        await update.message.reply_text("Керкраде → Амстердам = 120€")

    elif text == "📍 Маршруты":
        await update.message.reply_text("Керкраде → Амстердам\nКеркраде → Брюссель")

    elif text == "❓ Помощь":
        support_users[user_id] = True
        await update.message.reply_text("Напиши свой вопрос ✍️")

# ================= STATUS BUTTONS =================
async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, order_id = query.data.split("_", 1)

    if order_id not in orders:
        await query.message.edit_text("❌ Заказ не найден")
        return

    if action == "accept":
        orders[order_id]["status"] = "ACCEPTED"
    elif action == "reject":
        orders[order_id]["status"] = "REJECTED"
    elif action == "progress":
        orders[order_id]["status"] = "IN_PROGRESS"
    elif action == "done":
        orders[order_id]["status"] = "DONE"

    o = orders[order_id]

    await query.message.edit_text(
        f"""
🚕 ЗАКАЗ #{order_id}

📍 Откуда: {o['from']}
📍 Куда: {o['to']}
📅 Когда: {o['date']}

📊 Статус: {o['status']}
"""
    )

# ================= ADMIN REPLY =================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        user_id = int(context.args[0])
        text = " ".join(context.args[1:])

        await context.bot.send_message(
            chat_id=user_id,
            text=f"📩 Ответ поддержки:\n\n{text}"
        )

        await update.message.reply_text("✅ Отправлено")

    except:
        await update.message.reply_text("Ошибка /reply")

# ================= MAIN =================
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
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))
    app.add_handler(CallbackQueryHandler(status_handler))
    app.add_handler(CommandHandler("reply", reply))

    app.run_polling()

if __name__ == "__main__":
    main()