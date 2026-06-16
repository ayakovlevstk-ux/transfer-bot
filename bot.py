import os
import time

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
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

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not TOKEN:
    raise ValueError("TOKEN не найден")

# =========================
# STATES
# =========================

FROM, TO, DATE = range(3)

# =========================
# STORAGE
# =========================

orders = {}
support_users = {}

# =========================
# MENU
# =========================

menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🚕 Добро пожаловать в Transfer Bot",
        reply_markup=menu_keyboard
    )

# =========================
# ORDER FLOW
# =========================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📍 Откуда вас забрать?"
    )

    return FROM

# =========================

async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["from"] = update.message.text

    await update.message.reply_text(
        "📍 Куда едем?"
    )

    return TO

# =========================

async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["to"] = update.message.text

    await update.message.reply_text(
        "📅 Когда нужен трансфер?"
    )

    return DATE

# =========================

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    context.user_data["date"] = update.message.text

    order_id = str(int(time.time()))

    orders[order_id] = {
        "from": context.user_data["from"],
        "to": context.user_data["to"],
        "date": context.user_data["date"],
        "status": "NEW",
        "user_id": user.id
    }

    order_text = f"""
🚕 НОВЫЙ ЗАКАЗ #{order_id}

👤 Клиент: @{user.username}
🆔 ID: {user.id}

📍 Откуда: {orders[order_id]['from']}
📍 Куда: {orders[order_id]['to']}
📅 Когда: {orders[order_id]['date']}

📊 Статус: NEW
"""

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Принять",
                callback_data=f"accept_{order_id}"
            ),

            InlineKeyboardButton(
                "❌ Отказать",
                callback_data=f"reject_{order_id}"
            )
        ],

        [
            InlineKeyboardButton(
                "🚗 В пути",
                callback_data=f"progress_{order_id}"
            ),

            InlineKeyboardButton(
                "🏁 Завершён",
                callback_data=f"done_{order_id}"
            )
        ]
    ]

    # ===== SEND TO ADMIN =====

    try:

        await context.bot.send_message(
            chat_id=8308540295,
            text=order_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        print("ORDER SENT TO ADMIN")

    except Exception as e:

        print("ADMIN ERROR:", e)

    # ===== CLIENT CONFIRM =====

    await update.message.reply_text(
        "✅ Заказ отправлен диспетчеру!",
        reply_markup=menu_keyboard
    )

    return ConversationHandler.END

# =========================
# CANCEL
# =========================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "❌ Заказ отменён",
        reply_markup=menu_keyboard
    )

    return ConversationHandler.END

# =========================
# MENU
# =========================

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.effective_user.id

    # ================= SUPPORT =================

    if user_id in support_users:

        await context.bot.send_message(
            chat_id=8308540295,
            text=f"""
❓ ВОПРОС ОТ КЛИЕНТА

👤 USER ID: {user_id}

💬 {text}
"""
        )

        await update.message.reply_text(
            "✅ Сообщение отправлено оператору"
        )

        del support_users[user_id]

        return

    # ================= MENU BUTTONS =================

    if text == "💰 Цены":

        await update.message.reply_text(
            "💰 Пример цен:\n\n"
            "Керкраде → Амстердам — 120€\n"
            "Керкраде → Брюссель — 140€"
        )

    elif text == "📍 Маршруты":

        await update.message.reply_text(
            "📍 Популярные маршруты:\n\n"
            "• Керкраде → Амстердам\n"
            "• Керкраде → Брюссель\n"
            "• Керкраде → Аэропорт"
        )

    elif text == "❓ Помощь":

        support_users[user_id] = True

        await update.message.reply_text(
            "✍️ Напишите ваш вопрос"
        )

# =========================
# STATUS BUTTONS
# =========================

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    action, order_id = query.data.split("_", 1)

    if order_id not in orders:

        await query.message.edit_text(
            "❌ Заказ не найден"
        )

        return

    if action == "accept":

        orders[order_id]["status"] = "ACCEPTED"

    elif action == "reject":

        orders[order_id]["status"] = "REJECTED"

    elif action == "progress":

        orders[order_id]["status"] = "IN PROGRESS"

    elif action == "done":

        orders[order_id]["status"] = "DONE"

    o = orders[order_id]

    new_text = f"""
🚕 ЗАКАЗ #{order_id}

📍 Откуда: {o['from']}
📍 Куда: {o['to']}
📅 Когда: {o['date']}

📊 Статус: {o['status']}
"""

    await query.message.edit_text(
        new_text
    )

# =========================
# ADMIN REPLY
# =========================

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

        await update.message.reply_text(
            "✅ Ответ отправлен"
        )

    except:

        await update.message.reply_text(
            "Использование:\n/reply USER_ID текст"
        )

# =========================
# MAIN
# =========================

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    # ===== ORDER CONVERSATION =====

    conv_handler = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.TEXT & filters.Regex("^🚕 Заказать трансфер$"),
                start_order
            )
        ],

        states={

            FROM: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    get_from
                )
            ],

            TO: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    get_to
                )
            ],

            DATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    get_date
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ]
    )

    # ⚠️ Conversation FIRST
    app.add_handler(conv_handler)

    # other handlers
    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            menu
        )
    )

    app.add_handler(
        CallbackQueryHandler(status_handler)
    )

    app.add_handler(
        CommandHandler("reply", reply)
    )

    print("BOT STARTED")

    app.run_polling()

# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()