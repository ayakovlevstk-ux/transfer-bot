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

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 8308540295

if not TOKEN:
    raise ValueError("TOKEN не найден")

FROM, TO, DATE, CONFIRM = range(4)

orders = {}
support_users = {}

menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📍 Маршруты"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚕 Добро пожаловать в Transfer Bot",
        reply_markup=menu_keyboard
    )

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📍 Откуда вас забрать?")
    return FROM

async def get_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("📍 Куда едем?")
    return TO

async def get_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text
    await update.message.reply_text("📅 Когда нужен трансфер?")
    return DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text

    summary = f"""
🚕 ПРОВЕРЬТЕ ЗАКАЗ

📍 Откуда: {context.user_data['from']}
📍 Куда: {context.user_data['to']}
📅 Когда: {context.user_data['date']}
"""

    keyboard = ReplyKeyboardMarkup(
        [["✅ Подтвердить"], ["❌ Отмена"]],
        resize_keyboard=True
    )

    await update.message.reply_text(summary, reply_markup=keyboard)
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "❌ Отмена":
        await update.message.reply_text("❌ Отменено", reply_markup=menu_keyboard)
        return ConversationHandler.END

    if text == "✅ Подтвердить":
        order_id = str(int(time.time()))

        orders[order_id] = {
            "from": context.user_data["from"],
            "to": context.user_data["to"],
            "date": context.user_data["date"],
            "status": "NEW",
            "user_id": user.id
        }

        admin_text = f"""
🚕 НОВЫЙ ЗАКАЗ #{order_id}

📍 Откуда: {orders[order_id]['from']}
📍 Куда: {orders[order_id]['to']}
📅 Когда: {orders[order_id]['date']}
"""

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept_{order_id}"),
                InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{order_id}")
            ],
            [
                InlineKeyboardButton("🚗 В пути", callback_data=f"progress_{order_id}"),
                InlineKeyboardButton("🏁 Завершён", callback_data=f"done_{order_id}")
            ]
        ])

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=keyboard
        )

        await update.message.reply_text("✅ Заказ отправлен")
        return ConversationHandler.END

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    lat = loc.latitude
    lon = loc.longitude

    link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    await update.message.reply_text(f"📍 Локация получена:\n{link}")

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
        orders[order_id]["status"] = "IN PROGRESS"
    elif action == "done":
        orders[order_id]["status"] = "DONE"

    await query.message.edit_text(
        f"""
🚕 ЗАКАЗ #{order_id}

📍 Откуда: {orders[order_id]['from']}
📍 Куда: {orders[order_id]['to']}
📅 Когда: {orders[order_id]['date']}

📊 Статус: {orders[order_id]['status']}
"""
    )

    try:
        status_map = {
            "ACCEPTED": "✅ Принят",
            "REJECTED": "❌ Отклонён",
            "IN PROGRESS": "🚗 В пути",
            "DONE": "🏁 Завершён"
        }

        await context.bot.send_message(
            chat_id=orders[order_id]["user_id"],
            text=status_map[orders[order_id]["status"]]
        )
    except:
        pass

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "💰 Цены":
        await update.message.reply_text("Керкраде → Амстердам 120€")

    elif text == "📍 Маршруты":
        await update.message.reply_text("Популярные маршруты:\n- Керкраде → Амстердам")

    elif text == "❓ Помощь":
        support_users[update.effective_user.id] = True
        await update.message.reply_text("Напишите ваш вопрос")

    elif update.effective_user.id in support_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❓ Вопрос:\n{text}"
        )
        await update.message.reply_text("Отправлено оператору")
        del support_users[update.effective_user.id]

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & filters.Regex("🚕 Заказать трансфер"), start_order)
        ],
        states={
            FROM: [MessageHandler(filters.TEXT, get_from)],
            TO: [MessageHandler(filters.TEXT, get_to)],
            DATE: [MessageHandler(filters.TEXT, get_date)],
            CONFIRM: [MessageHandler(filters.TEXT, confirm)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(CallbackQueryHandler(status_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

    print("BOT STARTED")
    app.run_polling()

if __name__ == "__main__":
    main()