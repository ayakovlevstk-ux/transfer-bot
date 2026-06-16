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

# ВСТАВЬ СВОЙ TELEGRAM ID
ADMIN_ID = 8308540295

if not TOKEN:
    raise ValueError("TOKEN не найден")

# =========================
# STATES
# =========================

FROM, TO, DATE, CONFIRM = range(4)

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
# ORDER START
# =========================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📍 Откуда вас забрать?"
    )

    return FROM

# =========================
# FROM
# =========================

async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["from"] = update.message.text

    await update.message.reply_text(
        "📍 Куда едем?"
    )

    return TO

# =========================
# TO
# =========================

async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["to"] = update.message.text

    await update.message.reply_text(
        "📅 Когда нужен трансфер?"
    )

    return DATE

# =========================
# DATE
# =========================

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["date"] = update.message.text

    summary = f"""
🚕 ПРОВЕРЬТЕ ЗАКАЗ

📍 Откуда: {context.user_data['from']}
📍 Куда: {context.user_data['to']}
📅 Когда: {context.user_data['date']}

Подтвердить заказ?
"""

    keyboard = ReplyKeyboardMarkup(
        [
            ["✅ Подтвердить"],
            ["❌ Отмена"]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(
        summary,
        reply_markup=keyboard
    )

    return CONFIRM

# =========================
# CONFIRM
# =========================

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user = update.effective_user

    # CANCEL
    if text == "❌ Отмена":

        await update.message.reply_text(
            "❌ Заказ отменён",
            reply_markup=menu_keyboard
        )

        return ConversationHandler.END

    # CONFIRM
    if text == "✅ Подтвердить":

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

        # =========================
        # SEND TO ADMIN
        # =========================

        try:

            print("ADMIN_ID =", ADMIN_ID)
            print("TRY SEND ORDER")

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=order_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            print("ORDER SENT SUCCESS")

        except Exception as e:

            print("ADMIN SEND ERROR:", e)

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

    # SUPPORT

    if user_id in support_users:

        try:

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"""
❓ ВОПРОС ОТ КЛИЕНТА

👤 USER ID: {user_id}

💬 {text}
"""
            )

        except Exception as e:

            print("SUPPORT ERROR:", e)

        await update.message.reply_text(
            "✅ Сообщение отправлено оператору"
        )

        del support_users[user_id]

        return

    # BUTTONS

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
# STATUS HANDLER
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

    await query.message.edit_text(new_text)

    # CLIENT STATUS MESSAGE

    try:

        status_map = {
            "ACCEPTED": "✅ Ваш заказ принят",
            "REJECTED": "❌ Ваш заказ отклонён",
            "IN PROGRESS": "🚗 Водитель выехал",
            "DONE": "🏁 Заказ завершён"
        }

        await context.bot.send_message(
            chat_id=o["user_id"],
            text=status_map[o["status"]]
        )

    except Exception as e:

        print("CLIENT STATUS ERROR:", e)

# =========================
# REPLY TO CLIENT
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
            ],

            CONFIRM: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    confirm
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ]
    )

    app.add_handler(conv_handler)

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