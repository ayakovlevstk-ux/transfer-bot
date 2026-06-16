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

# ================= MAIN HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # ========== SUPPORT MODE ==========
    if user_id in support_users:
        question = text

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❓ ПОДДЕРЖКА\n\n👤 User: {user_id}\n\n💬 {question}"
        )

        await update.message.reply_text("✅ Вопрос отправлен в поддержку")
        del support_users[user_id]
        return

    # ========== MENU ==========
    if text == "🚕 Заказать трансфер":
        await update.message.reply_text("Откуда → Куда → Дата")

    elif text == "💰 Цены":
        await update.message.reply_text("Керкраде → Амстердам = 120€")

    elif text == "📍 Маршруты":
        await update.message.reply_text("Керкраде → Амстердам\nКеркраде → Брюссель")

    elif text == "❓ Помощь":
        await update.message.reply_text("Напиши свой вопрос ✍️")
        support_users[user_id] = True
        return

    # ========== CREATE ORDER ==========
    else:
        try:
            parts = text.split("→")

            if len(parts) < 2:
                return await update.message.reply_text("Формат: Откуда → Куда → Дата")

            from_city = parts[0].strip()
            to_city = parts[1].strip()
            date = parts[2].strip() if len(parts) > 2 else "не указана"

            order_id = str(user_id) + str(int(time.time()))

            orders[order_id] = {
                "from": from_city,
                "to": to_city,
                "date": date,
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

            text_order = f"""
🚕 НОВЫЙ ЗАКАЗ #{order_id}

📍 Откуда: {from_city}
📍 Куда: {to_city}
📅 Дата: {date}

📊 Статус: NEW
"""

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=text_order,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            await update.message.reply_text("✅ Заказ отправлен диспетчеру!")

        except Exception as e:
            print("ORDER ERROR:", e)
            await update.message.reply_text("Ошибка заказа")

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
📅 Дата: {o['date']}

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

    except Exception as e:
        print(e)
        await update.message.reply_text("Ошибка /reply")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(status_handler))
    app.add_handler(CommandHandler("reply", reply))

    app.run_polling()

if __name__ == "__main__":
    main()