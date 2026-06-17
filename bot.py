import os
import time

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
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

# =========================
# STORAGE
# =========================

orders = {}
support_users = {}

# =========================
# KEYBOARDS
# =========================

menu_keyboard = ReplyKeyboardMarkup(
    [
        ["🚕 Заказать трансфер"],
        ["💰 Цены", "📍 Маршруты"],
        ["❓ Помощь"],
    ],
    resize_keyboard=True,
)

confirm_keyboard = ReplyKeyboardMarkup(
    [
        ["✅ Подтвердить"],
        ["❌ Отмена"],
    ],
    resize_keyboard=True,
)

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚕 Добро пожаловать в Transfer Bot",
        reply_markup=menu_keyboard,
    )

# =========================
# ORDER FLOW
# =========================

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


async def get_date(update, context):
    context.user_data["date"] = update.message.text

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Отправь геолокацию 📍",
        reply_markup=keyboard
    )

    return LOCATION

await update.message.reply_text("🚕 ПРОВЕРЬТЕ ЗАКАЗ")

text = (
    f"📍 Откуда: {context.user_data['from']}\n"
    f"📍 Куда: {context.user_data['to']}\n"
    f"📅 Дата: {context.user_data['date']}"
)

await update.message.reply_text(text)
"""

    await update.message.reply_text(summary, reply_markup=confirm_keyboard)
    return CONFIRM

# =========================
# CONFIRM ORDER
# =========================

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "❌ Отмена":
        await update.message.reply_text("❌ Заказ отменён", reply_markup=menu_keyboard)
        return ConversationHandler.END

    if text == "✅ Подтвердить":
        order_id = str(int(time.time()))

        orders[order_id] = {
            "from": context.user_data["from"],
            "to": context.user_data["to"],
            "date": context.user_data["date"],
            "status": "NEW",
            "user_id": user.id,
            "lat": None,
            "lon": None,
        }

        order_text = f"""
🚕 НОВЫЙ ЗАКАЗ #{order_id}

👤 @{user.username or "no_username"}
🆔 {user.id}

📍 Откуда: {orders[order_id]['from']}
📍 Куда: {orders[order_id]['to']}
📅 Когда: {orders[order_id]['date']}

📊 Статус: NEW
"""

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept_{order_id}"),
                InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{order_id}")
            ],
            [
                InlineKeyboardButton("🚗 В пути", callback_data=f"progress_{order_id}"),
                InlineKeyboardButton("🏁 Завершён", callback_data=f"done_{order_id}")
            ],
        ])

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=order_text,
                reply_markup=keyboard,
            )
        except Exception as e:
            print("ADMIN ERROR:", e)

        await update.message.reply_text("✅ Заказ отправлен диспетчеру", reply_markup=menu_keyboard)
        return ConversationHandler.END

# =========================
# LOCATION HANDLER
# =========================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    loc = update.message.location

    # ищем последний заказ пользователя
    for oid, order in orders.items():
        if order["user_id"] == user.id:
            order["lat"] = loc.latitude
            order["lon"] = loc.longitude

            maps = f"https://www.google.com/maps/search/?api=1&query={loc.latitude},{loc.longitude}"

            await update.message.reply_text(
                f"📍 Геолокация получена\n\n🗺 Открыть: {maps}"
            )
            return

# =========================
# STATUS CALLBACKS
# =========================

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, order_id = query.data.split("_", 1)

    if order_id not in orders:
        await query.message.edit_text("❌ Заказ не найден")
        return

    if action == "accept":
        orders[order_id]["status"] = "ACCEPTED"
        status_text = "✅ Принят"

    elif action == "reject":
        orders[order_id]["status"] = "REJECTED"
        status_text = "❌ Отклонён"

    elif action == "progress":
        orders[order_id]["status"] = "IN PROGRESS"
        status_text = "🚗 В пути"

    elif action == "done":
        orders[order_id]["status"] = "DONE"
        status_text = "🏁 Завершён"

    o = orders[order_id]

    new_text = f"""
🚕 ЗАКАЗ #{order_id}

📍 Откуда: {o['from']}
📍 Куда: {o['to']}
📅 Когда: {o['date']}

📊 Статус: {status_text}
"""

    await query.message.edit_text(new_text)

    # notify client
    try:
        await context.bot.send_message(
            chat_id=o["user_id"],
            text=f"📊 Статус заказа: {status_text}",
        )
    except Exception as e:
        print("CLIENT ERROR:", e)

# =========================
# MENU
# =========================

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "💰 Цены":
        await update.message.reply_text(
            "💰 Цены:\n\nКеркраде → Амстердам — 120€\nКеркраде → Брюссель — 140€"
        )

    elif text == "📍 Маршруты":
        await update.message.reply_text(
            "📍 Маршруты:\n\n• Керкраде → Амстердам\n• Керкраде → Брюссель"
        )

    elif text == "❓ Помощь":
        support_users[user_id] = True
        await update.message.reply_text("✍️ Напишите ваш вопрос")

    elif user_id in support_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❓ Вопрос:\n\n{text}",
        )
        await update.message.reply_text("✅ Отправлено оператору")
        del support_users[user_id]

async def get_location(update, context):
    loc = update.message.location

    context.user_data["lat"] = loc.latitude
    context.user_data["lon"] = loc.longitude

    maps_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    await update.message.reply_text(
        f"📍 Геолокация получена\n{maps_link}\n\nПодтверждаем заказ?"
    )

    return CONFIRM

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
            FROM: [MessageHandler(filters.TEXT, get_from)],
            TO: [MessageHandler(filters.TEXT, get_to)],
            DATE: [MessageHandler(filters.TEXT, get_date)],
            CONFIRM: [MessageHandler(filters.TEXT, confirm)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(status_handler))
    states={
    FROM: [MessageHandler(filters.TEXT, get_from)],
    TO: [MessageHandler(filters.TEXT, get_to)],
    DATE: [MessageHandler(filters.TEXT, get_date)],
    LOCATION: [MessageHandler(filters.LOCATION, location_handler)],
    CONFIRM: [MessageHandler(filters.TEXT, confirm)],
}
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()